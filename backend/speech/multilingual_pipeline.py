"""
EduMentor Voice — Multilingual Pipeline Orchestrator

Implements the full multilingual routing loop:
  STT (multilingual Whisper) → Language Router → {
    english/hindi  →  Agent LLM  →  Kokoro TTS
    kannada/marathi →  [translate to EN] → Agent LLM → [translate back] → MMS-TTS
  }

Only activated when Config.MULTILINGUAL_ENABLED is True.
English-only behavior is completely unchanged when the flag is False.
"""

import logging
import time
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import numpy as np

from config import Config

logger = logging.getLogger("edumentor.speech.multilingual_pipeline")

# ──────────────────────────────────────────────────────────────
# NLLB language code constants
# ──────────────────────────────────────────────────────────────

NLLB_LANG_MAP = {
    "kannada": "kan_Knda",
    "marathi": "mar_Deva",
    "hindi": "hin_Deva",
    "english": "eng_Latn",
}

# MMS-TTS language code map (Meta model identifier)
MMS_TTS_LANG_MAP = {
    "hindi": "hin",
    "kannada": "kan",
    "marathi": "mar",
}


class MultilingualPipeline:
    """
    Orchestrates the multilingual STT → route → LLM → TTS pipeline.
    Instantiated once at startup (when MULTILINGUAL_ENABLED=true).
    """

    def __init__(self, whisper_engine, agent_controller, llm_engine) -> None:
        """
        Args:
            whisper_engine:   The existing WhisperEngine singleton.
            agent_controller: The existing AgentController singleton.
            llm_engine:       The existing LLMEngine singleton (fallback when agent disabled).
        """
        self.whisper_engine = whisper_engine
        self.agent_controller = agent_controller
        self.llm_engine = llm_engine

        # Lazy-load translation & MMS-TTS modules
        from speech.nllb_translator import get_translator
        from speech.mms_tts import get_mms_tts_engine
        from speech.language_router import LanguageRouter

        self.translator = get_translator()
        self.mms_tts = get_mms_tts_engine()
        self.router = LanguageRouter()

        # Warm up all MMS-TTS models in a background thread to avoid cold-start on first Indic request
        import threading
        threading.Thread(target=self._warmup_mms_models, daemon=True).start()

        logger.info("[OK] MultilingualPipeline initialized.")

    def _warmup_mms_models(self) -> None:
        """Pre-load all three MMS-TTS language models to avoid 45s cold-start."""
        for lang, mms_lang in MMS_TTS_LANG_MAP.items():
            try:
                logger.info("[warmup] Loading MMS-TTS model for '%s' ...", lang)
                self.mms_tts.synthesize("test", mms_lang)  # short dummy synthesis
                logger.info("[warmup] MMS-TTS '%s' warm.", lang)
            except Exception as e:
                logger.warning("[warmup] MMS-TTS '%s' warmup failed: %s", lang, e)

    def transcribe_multilingual(
        self,
        audio_array: np.ndarray,
        initial_prompt: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        """
        Transcribes with Whisper in multilingual mode (no forced language).
        Returns (transcript, detected_language, latency_seconds).
        """
        import faster_whisper
        t_start = time.time()

        # Run without language="en" forcing so Whisper can detect non-English
        segments, info = self.whisper_engine.model.transcribe(
            audio_array,
            task="transcribe",
            vad_filter=Config.WHISPER_VAD_FILTER,
            beam_size=Config.WHISPER_BEAM_SIZE,
            best_of=Config.WHISPER_BEAM_SIZE,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )

        parts = []
        for seg in segments:
            text = seg.text.strip()
            if text and not self.whisper_engine._is_hallucination(text):
                parts.append(text)

        transcript = " ".join(parts).strip()
        detected_lang = info.language  # Whisper's best guess (unreliable for code-mix)
        latency = time.time() - t_start

        logger.info(
            "Multilingual STT: %r | whisper_lang=%s (prob=%.2f) | latency=%.2fs",
            transcript, detected_lang, info.language_probability, latency
        )
        return transcript, detected_lang, latency

    def translate_to_english(self, text: str, source_lang: str) -> Tuple[str, float]:
        """
        Translates text from source_lang (kannada/marathi/hindi) into English.
        Returns (english_text, latency_seconds).
        """
        src_code = NLLB_LANG_MAP.get(source_lang, "hin_Deva")
        english_text, latency = self.translator.translate(text, src_code, "eng_Latn")
        logger.info("Translated to EN in %.2fs: %r -> %r", latency, text[:60], english_text[:60])
        return english_text, latency

    def translate_from_english(self, text: str, target_lang: str) -> Tuple[str, float]:
        """
        Translates text from English into target_lang (kannada/marathi/hindi).
        Returns (translated_text, latency_seconds).
        """
        tgt_code = NLLB_LANG_MAP.get(target_lang, "hin_Deva")
        translated_text, latency = self.translator.translate(text, "eng_Latn", tgt_code)
        logger.info("Translated from EN in %.2fs: %r -> %r", latency, text[:60], translated_text[:60])
        return translated_text, latency

    def synthesize_indic(self, text: str, lang: str) -> Tuple[bytes, float]:
        """
        Synthesizes native Indic TTS audio for hindi/kannada/marathi.
        Returns (wav_bytes, latency_seconds).
        """
        mms_lang = MMS_TTS_LANG_MAP.get(lang)
        if not mms_lang:
            logger.error("Unknown Indic TTS language: %s, falling back to empty bytes", lang)
            return b"", 0.0

        t_start = time.time()
        wav_bytes = self.mms_tts.synthesize(text, mms_lang)
        latency = time.time() - t_start
        return wav_bytes, latency

    async def run_pipeline(
        self,
        audio_array: np.ndarray,
        session_id: str,
        user_id: str,
        initial_prompt: Optional[str] = None,
        voice_style: Optional[str] = None,
        ip_address: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Run one full multilingual turn end-to-end.
        Returns a dictionary with all stage results and latency timings.

        Stages:
          1. STT (multilingual Whisper)
          2. Language Router (script + lexical)
          3a. If english/hindi → agent LLM (unchanged path, response in English)
          3b. If kannada/marathi → translate to EN → agent LLM → translate back
          4. TTS routing: english → Kokoro (caller handles), indic → MMS-TTS

        Note: This method does NOT send over WebSocket — the caller handles that.
        It returns all stage outputs so the caller can stream/send as appropriate.
        """
        timings: Dict[str, float] = {}
        result: Dict[str, Any] = {
            "timings": timings,
            "route_lang": None,
            "route_metadata": None,
            "stt_transcript": None,
            "whisper_detected_lang": None,
            "translated_to_en": None,
            "llm_english_response": None,
            "translated_from_en": None,
            "tts_wav_bytes": None,
            "tts_engine": None,
        }

        t_total_start = time.time()

        # ── Stage 1: STT ─────────────────────────────────────────────────────
        t_stt = time.time()
        transcript, whisper_lang, stt_latency = self.transcribe_multilingual(
            audio_array, initial_prompt=initial_prompt
        )
        timings["stt"] = round(stt_latency, 3)
        result["stt_transcript"] = transcript
        result["whisper_detected_lang"] = whisper_lang

        if not transcript:
            timings["total"] = round(time.time() - t_total_start, 3)
            return result

        # ── Stage 2: Language Router ─────────────────────────────────────────
        t_route = time.time()
        route_lang, route_meta = self.router.route(transcript)
        timings["router"] = round(time.time() - t_route, 3)
        result["route_lang"] = route_lang
        result["route_metadata"] = route_meta
        logger.info("Router decision: %s | reason: %s", route_lang, route_meta.get("reason"))

        # ── Stage 3: Input translation (only for kannada / marathi) ──────────
        llm_input = transcript
        needs_translation = route_lang in ("kannada", "marathi")
        back_translate_lang = None

        # Determine if we need back-translation for TTS:
        # - kannada / marathi always go through translation bridge
        # - hindi uses MMS-TTS ONLY if the transcript contained actual Devanagari
        #   (i.e. the user spoke Hindi, not romanized Hinglish / English)
        has_devanagari = self.router.contains_devanagari_script(transcript)
        use_mms_for_hindi = (route_lang == "hindi" and has_devanagari)

        if needs_translation:
            t_translate_in = time.time()
            english_input, _ = self.translate_to_english(transcript, route_lang)
            timings["translate_in"] = round(time.time() - t_translate_in, 3)
            result["translated_to_en"] = english_input
            llm_input = english_input
            back_translate_lang = route_lang

        # ── Stage 4: LLM (unchanged agent pipeline) ──────────────────────────
        t_llm = time.time()
        llm_tokens = []

        if self.agent_controller is not None:
            async for token_dict in self.agent_controller.stream(
                llm_input, session_id, user_id=user_id,
                audio_array=audio_array, ip_address=ip_address,
                voice_style=voice_style
            ):
                raw_token = token_dict.get("raw", "")
                if raw_token:
                    llm_tokens.append(raw_token)
        else:
            async for token_dict in self.llm_engine.stream_tokens(llm_input):
                raw_token = token_dict.get("raw", "")
                if raw_token:
                    llm_tokens.append(raw_token)

        llm_response_english = "".join(llm_tokens).strip()
        timings["llm"] = round(time.time() - t_llm, 3)
        result["llm_english_response"] = llm_response_english
        logger.info("LLM response (EN, %d chars) in %.2fs", len(llm_response_english), timings["llm"])

        # ── Stage 5: Back-translation (if needed) ────────────────────────────
        tts_text = llm_response_english
        if back_translate_lang:
            t_translate_out = time.time()
            translated_response, _ = self.translate_from_english(llm_response_english, back_translate_lang)
            timings["translate_out"] = round(time.time() - t_translate_out, 3)
            result["translated_from_en"] = translated_response
            tts_text = translated_response
        elif use_mms_for_hindi:
            # Hindi Devanagari input: back-translate English response to Hindi
            t_translate_out = time.time()
            translated_response, _ = self.translate_from_english(llm_response_english, "hindi")
            timings["translate_out"] = round(time.time() - t_translate_out, 3)
            result["translated_from_en"] = translated_response
            tts_text = translated_response

        # ── Stage 6: TTS Routing ──────────────────────────────────────────────
        # Indic MMS-TTS: kannada, marathi always; hindi only if Devanagari was in the transcript
        if route_lang in ("kannada", "marathi") or use_mms_for_hindi:
            # Indic TTS via MMS-TTS
            t_tts = time.time()
            wav_bytes, _ = self.synthesize_indic(tts_text, route_lang)
            timings["tts"] = round(time.time() - t_tts, 3)
            result["tts_wav_bytes"] = wav_bytes
            result["tts_engine"] = "mms"
            result["tts_lang"] = route_lang
        else:
            # English → caller uses Kokoro (wav_bytes=None signals Kokoro path)
            result["tts_wav_bytes"] = None
            result["tts_engine"] = "kokoro"
            result["tts_lang"] = "english"

        timings["total"] = round(time.time() - t_total_start, 3)
        logger.info("Multilingual turn complete in %.2fs | %s", timings["total"], timings)
        return result


# Singleton holder
_multilingual_pipeline: Optional[MultilingualPipeline] = None


def get_multilingual_pipeline(
    whisper_engine=None,
    agent_controller=None,
    llm_engine=None
) -> Optional[MultilingualPipeline]:
    """
    Returns the MultilingualPipeline singleton if MULTILINGUAL_ENABLED is True.
    On first call, pass all three engines; subsequent calls return the cached instance.
    """
    global _multilingual_pipeline
    if not Config.MULTILINGUAL_ENABLED:
        return None
    if _multilingual_pipeline is None:
        _multilingual_pipeline = MultilingualPipeline(whisper_engine, agent_controller, llm_engine)
    return _multilingual_pipeline
