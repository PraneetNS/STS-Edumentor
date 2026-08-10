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
from i18n.term_glossary import protect_terms, restore_terms, protect_visual_blocks, restore_visual_blocks

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

    def __init__(self, whisper_engine, agent_controller, llm_engine, kokoro_engine=None) -> None:
        """
        Args:
            whisper_engine:   The existing WhisperEngine singleton.
            agent_controller: The existing AgentController singleton.
            llm_engine:       The existing LLMEngine singleton (fallback when agent disabled).
            kokoro_engine:    The existing KokoroEngine singleton.
        """
        self.whisper_engine = whisper_engine
        self.agent_controller = agent_controller
        self.llm_engine = llm_engine

        # Lazy-load translation, MMS-TTS, and Mixed Synthesizer modules
        from speech.nllb_translator import get_translator
        from speech.mms_tts import get_mms_tts_engine
        from speech.language_router import LanguageRouter
        from tts.mixed_language_synth import MixedLanguageSynthesizer

        self.translator = get_translator()
        self.mms_tts = get_mms_tts_engine()
        self.router = LanguageRouter()
        self.mixed_synthesizer = MixedLanguageSynthesizer(kokoro_engine)

        logger.info("[OK] MultilingualPipeline initialized.")


    # ──────────────────────────────────────────────────────────────────────
    # Allowed language gate — only these languages will ever be passed to
    # Whisper's transcribe() call. Arabic ('ar') and all other unsupported
    # languages are blocked here before any audio is decoded.
    # 'ml' (Malayalam) is included because Whisper small frequently confuses
    # Kannada speech as Malayalam (both are Dravidian languages). We immediately
    # remap 'ml' → 'kn' downstream to ensure the Kannada path is taken.
    # ──────────────────────────────────────────────────────────────────────
    ALLOWED_LANGS: set = {"en", "kn", "hi", "mr"}

    def _pick_allowed_lang(self, all_language_probs) -> Tuple[str, float]:
        """
        Given Whisper's full language probability list, pick the highest-probability
        language that is in ALLOWED_LANGS. Falls back to 'en' if nothing scores > 0.
        If there is a tie and the current best candidate is English, prefer an
        Indic language over English to preserve the spoken language when the model
        is uncertain.
        """
        # Remap Malayalam to Kannada: Whisper small frequently confuses the two Dravidian languages.
        mapped_probs = []
        for lang, prob in (all_language_probs or []):
            if lang == "ml":
                mapped_probs.append(("kn", prob))
            else:
                mapped_probs.append((lang, prob))

        best_lang, best_prob = "en", -1.0
        for lang, prob in mapped_probs:
            if lang not in self.ALLOWED_LANGS:
                continue
            if prob > best_prob or (prob == best_prob and best_lang == "en" and lang != "en"):
                best_prob = prob
                best_lang = lang
        return best_lang, max(best_prob, 0.0)

    def transcribe_multilingual(
        self,
        audio_array: np.ndarray,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        """
        Transcribes audio using a two-step approach:
          1. auto-detect transcription with a multilingual prompt and preserve the
             detected supported language when possible (or use the explicitly passed language).
          2. if auto-detect returns an unsupported language or no transcript,
             force transcription into the best allowed language.

        Returns (transcript, detected_language, latency_seconds).
        """
        t_start = time.time()
        time_to_first_output = None
        transcript = ""
        detected_lang = language if language else "en"
        info = None

        # Temporary debug audio dump to verify VAD capture quality
        import soundfile as sf
        try:
            sf.write("debug_audio.wav", audio_array, 16000)
            logger.info("[MULTILINGUAL STT] Temporary debug audio written to debug_audio.wav")
        except Exception as e:
            logger.warning("[MULTILINGUAL STT] Failed to write temporary debug audio: %s", e)

        # ── Step 1: Attempt auto-detected multilingual transcription first ────
        # Use the full multilingual prompt only when language is auto-detected.
        # For forced-language passes (e.g. language='kn'), use a language-specific
        # prompt so we don't confuse Whisper with mixed-script content.
        _step1_prompt = initial_prompt
        if language == "kn":
            _step1_prompt = "ನಮಸ್ಕಾರ Edi, ನನಗೆ programming ಮತ್ತು variable ಬಗ್ಗೆ ವಿವರಿಸಿ."
        elif language == "hi":
            _step1_prompt = "नमस्ते Edi, मुझे coding और recursion के बारे में बताओ।"
        elif language == "mr":
            _step1_prompt = "नमस्कार Edi, मला computer science आणि loop समजावून सांगा."
        try:
            segments, info = self.whisper_engine.model.transcribe(
                audio_array,
                language=language,
                task="transcribe",
                vad_filter=Config.WHISPER_VAD_FILTER,
                beam_size=Config.WHISPER_BEAM_SIZE,
                best_of=Config.WHISPER_BEAM_SIZE,
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=_step1_prompt,
            )
            parts = []
            for seg in segments:
                if time_to_first_output is None:
                    time_to_first_output = time.time() - t_start
                text = seg.text.strip()
                if text and not self.whisper_engine._is_hallucination(text):
                    parts.append(text)
            transcript = " ".join(parts).strip()

            # Determine detected language from Whisper
            if info and info.language in self.ALLOWED_LANGS:
                step1_lang = info.language
            elif info:
                step1_lang = info.language  # unsupported, will be caught below
            else:
                step1_lang = "en"

            if transcript and step1_lang in self.ALLOWED_LANGS:
                detected_lang = step1_lang
                logger.info(
                    "[MULTILINGUAL STT] auto-detected supported language=%r | transcript=%r",
                    detected_lang, transcript,
                )
            else:
                if not transcript:
                    logger.info("[MULTILINGUAL STT] Step-1 transcript empty (lang=%r).", step1_lang)
                else:
                    logger.info("[MULTILINGUAL STT] Step-1 unsupported lang=%r — discarding.", step1_lang)
                info = None
                transcript = ""
                # Keep step1_lang so the verification pass can still run

            # ── Kannada / Malayalam verification pass ────────────────────────────
            # Whisper small confuses Kannada speech as 'hi' or 'ml'. When either is
            # detected (including when transcript was empty), check kn+ml combined
            # probability and force a Kannada transcription pass if significant.
            if step1_lang in ("hi", "ml"):
                try:
                    _, _, all_lang_probs = self.whisper_engine.model.detect_language(audio_array)
                    probs = {lang: prob for lang, prob in (all_lang_probs or [])}
                    kn_prob = probs.get("kn", 0.0)
                    ml_prob = probs.get("ml", 0.0)
                    hi_prob = probs.get("hi", 0.0)
                    dravidian_prob = kn_prob + ml_prob
                    logger.info(
                        "[MULTILINGUAL STT] Kannada verification: kn=%.4f ml=%.4f dravidian=%.4f hi=%.4f",
                        kn_prob, ml_prob, dravidian_prob, hi_prob,
                    )
                    # Fire if: combined Dravidian >15%, OR >40% relative to Hindi, OR ml alone >30%
                    kn_significant = (
                        dravidian_prob > 0.15
                        or (hi_prob > 0 and dravidian_prob / hi_prob > 0.40)
                        or ml_prob > 0.30
                    )
                    if kn_significant:
                        logger.info(
                            "[MULTILINGUAL STT] Dravidian significant (%.4f) — forcing kn pass.",
                            dravidian_prob,
                        )
                        # We use temperature fallbacks and fully disable the no-speech and logprob gates
                        # to trust the forced language selection rather than pre-filtering on English norms.
                        kn_segs, kn_info = self.whisper_engine.model.transcribe(
                            audio_array,
                            language="kn",
                            task="transcribe",
                            vad_filter=Config.WHISPER_VAD_FILTER,
                            beam_size=Config.WHISPER_BEAM_SIZE,
                            best_of=Config.WHISPER_BEAM_SIZE,
                            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                            no_speech_threshold=None,
                            log_prob_threshold=None,
                            condition_on_previous_text=False,
                            initial_prompt="ನಮಸ್ಕಾರ Edi, ನನಗೆ programming ಮತ್ತು variable ಬಗ್ಗೆ ವಿವರಿಸಿ.",
                        )
                        kn_parts = []
                        for seg in kn_segs:
                            t_seg = seg.text.strip()
                            if t_seg and not self.whisper_engine._is_hallucination(t_seg):
                                kn_parts.append(t_seg)
                        kn_transcript = " ".join(kn_parts).strip()
                        if kn_transcript:
                            logger.info(
                                "[MULTILINGUAL STT] Forced-kn pass=%r — overriding %r.",
                                kn_transcript, step1_lang,
                            )
                            transcript = kn_transcript
                            detected_lang = "kn"
                        else:
                            logger.info(
                                "[MULTILINGUAL STT] Forced-kn pass empty — keeping %r.", step1_lang
                            )
                except Exception as kn_exc:
                    logger.warning("[MULTILINGUAL STT] Kannada verification pass failed: %s", kn_exc)
            # ── End Kannada / Malayalam verification pass ─────────────────────────
        except Exception as exc:
            logger.warning("[MULTILINGUAL STT] auto-detect pass failed (%s).", exc)
            info = None
            transcript = ""

        # ── Step 2: Force transcription into the best allowed language if needed ─────
        if not transcript:
            try:
                _, _, all_lang_probs = self.whisper_engine.model.detect_language(audio_array)
            except Exception as exc:
                logger.warning("[MULTILINGUAL STT] detect_language() failed (%s). Defaulting to 'en'.", exc)
                all_lang_probs = []

            forced_lang, lang_prob = self._pick_allowed_lang(all_lang_probs)
            logger.info(
                "[MULTILINGUAL STT] detect_language → forced_lang=%r (prob=%.4f) from allowed set %s",
                forced_lang, lang_prob, self.ALLOWED_LANGS,
            )

            transcribe_prompt = None
            if forced_lang == "en":
                transcribe_prompt = Config.WHISPER_PROMPT
            elif forced_lang == "kn":
                transcribe_prompt = "ನಮಸ್ಕಾರ Edi, ನನಗೆ programming ಮತ್ತು variable ಬಗ್ಗೆ ವಿವರಿಸಿ."
            elif forced_lang == "hi":
                transcribe_prompt = "नमस्ते Edi, मुझे coding और recursion के बारे में बताओ।"
            elif forced_lang == "mr":
                transcribe_prompt = "नमस्कार Edi, मला computer science आणि loop समजावून सांगा."

            # We use temperature fallbacks and fully disable the no-speech and logprob gates
            # to trust the forced language selection rather than pre-filtering on English norms.
            segments, info = self.whisper_engine.model.transcribe(
                audio_array,
                language=forced_lang,
                task="transcribe",
                vad_filter=Config.WHISPER_VAD_FILTER,
                beam_size=Config.WHISPER_BEAM_SIZE,
                best_of=Config.WHISPER_BEAM_SIZE,
                temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                no_speech_threshold=None,
                log_prob_threshold=None,
                condition_on_previous_text=False,
                initial_prompt=transcribe_prompt,
            )
            parts = []
            for seg in segments:
                if time_to_first_output is None:
                    time_to_first_output = time.time() - t_start
                text = seg.text.strip()
                if text and not self.whisper_engine._is_hallucination(text):
                    parts.append(text)
            transcript = " ".join(parts).strip()
            detected_lang = info.language

        if time_to_first_output is None:
            time_to_first_output = time.time() - t_start

        latency = time.time() - t_start

        try:
            from observability.metrics import multilingual_stt_ttf_seconds, multilingual_stt_total_seconds
            multilingual_stt_ttf_seconds.labels(language=detected_lang).observe(time_to_first_output)
            multilingual_stt_total_seconds.labels(language=detected_lang).observe(latency)
        except Exception as exc:
            logger.warning("Failed to record STT metrics: %s", exc)

        logger.info(
            "Multilingual STT: %r | whisper_lang=%s (prob=%.2f) | latency=%.2fs",
            transcript,
            detected_lang,
            info.language_probability if info is not None else 0.0,
            latency,
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
        route_lang, route_meta = self.router.route(transcript, whisper_lang)
        router_latency = time.time() - t_route
        timings["router"] = round(router_latency, 3)
        result["route_lang"] = route_lang
        result["route_metadata"] = route_meta
        logger.info("Router decision: %s | reason: %s", route_lang, route_meta.get("reason"))

        try:
            from observability.metrics import multilingual_router_classify_seconds
            multilingual_router_classify_seconds.labels(language=route_lang).observe(router_latency)
        except Exception as exc:
            logger.warning("Failed to record router metrics: %s", exc)

        # Increment Prometheus metric
        routing_path = route_meta.get("routing_path", "hindi-default")
        try:
            from observability.metrics import language_routing_total
            language_routing_total.labels(routing_path=routing_path, route_lang=route_lang).inc()
        except Exception as exc:
            logger.warning("Failed to record language routing metric: %s", exc)

        # Retrieve profile preferences
        lang_pref = "auto"
        glossary_mode = "english"
        if self.agent_controller is not None:
            profile = await self.agent_controller._profile_manager.get_profile(session_id)
            if profile:
                lang_pref = getattr(profile, "output_language_preference", "auto")
                glossary_mode = getattr(profile, "glossary_mode", "english")

        lang_pref = self.router.normalize_language(lang_pref) or "auto"

        # Determine target output language
        response_lang = lang_pref if lang_pref != "auto" else route_lang

        # ── Stage 3: Input translation (only for kannada / marathi) ──────────
        llm_input = transcript
        needs_translation = route_lang in ("kannada", "marathi")

        if needs_translation:
            t_translate_in = time.time()
            
            # Protect terms
            t_prot = time.time()
            protected_transcript, mapping = protect_terms(transcript)
            prot_latency = time.time() - t_prot

            t_call = time.time()
            english_input_protected, _ = self.translate_to_english(protected_transcript, route_lang)
            call_latency = time.time() - t_call

            # Restore protected terms in English mode for the LLM
            t_rest = time.time()
            english_input = restore_terms(english_input_protected, mapping, mode="english")
            rest_latency = time.time() - t_rest
            
            translate_in_latency = time.time() - t_translate_in
            timings["translate_in"] = round(translate_in_latency, 3)
            result["translated_to_en"] = english_input
            llm_input = english_input

            try:
                from observability.metrics import (
                    multilingual_glossary_protect_seconds,
                    multilingual_translate_in_seconds,
                    multilingual_glossary_restore_seconds
                )
                multilingual_glossary_protect_seconds.labels(language=route_lang).observe(prot_latency)
                multilingual_translate_in_seconds.labels(language=route_lang).observe(call_latency)
                multilingual_glossary_restore_seconds.labels(language=route_lang).observe(rest_latency)
            except Exception as exc:
                logger.warning("Failed to record translate_in stages metrics: %s", exc)

        # ── Stage 4: LLM (unchanged agent pipeline) ──────────────────────────
        t_llm = time.time()
        llm_tokens = []
        ttft = None

        if self.agent_controller is not None:
            async for token_dict in self.agent_controller.stream(
                llm_input, session_id, user_id=user_id,
                audio_array=audio_array, ip_address=ip_address,
                voice_style=voice_style, response_lang=response_lang,
                original_query=transcript
            ):
                if ttft is None:
                    ttft = time.time() - t_llm
                raw_token = token_dict.get("raw", "")
                if raw_token:
                    llm_tokens.append(raw_token)
        else:
            async for token_dict in self.llm_engine.stream_tokens(llm_input):
                if ttft is None:
                    ttft = time.time() - t_llm
                raw_token = token_dict.get("raw", "")
                if raw_token:
                    llm_tokens.append(raw_token)

        llm_response_english = "".join(llm_tokens).strip()
        llm_latency = time.time() - t_llm
        timings["llm"] = round(llm_latency, 3)
        result["llm_english_response"] = llm_response_english
        logger.info("LLM response (EN, %d chars) in %.2fs", len(llm_response_english), timings["llm"])

        if ttft is None:
            ttft = llm_latency

        try:
            from observability.metrics import multilingual_llm_ttft_seconds, multilingual_llm_completion_seconds
            multilingual_llm_ttft_seconds.labels(language=response_lang).observe(ttft)
            multilingual_llm_completion_seconds.labels(language=response_lang).observe(llm_latency)
        except Exception as exc:
            logger.warning("Failed to record LLM metrics: %s", exc)

        # ── Stage 5: Back-translation (if needed) ────────────────────────────
        tts_text = llm_response_english
        back_translate_lang = None
        use_mms_for_hindi = False

        if response_lang in ("kannada", "marathi"):
            back_translate_lang = response_lang
        elif response_lang == "hindi":
            use_mms_for_hindi = True

        if back_translate_lang:
            t_translate_out = time.time()
            
            # Protect visual blocks
            resp_no_vis, vis_mapping = protect_visual_blocks(llm_response_english)
            
            t_prot = time.time()
            protected_response, mapping = protect_terms(resp_no_vis)
            prot_latency = time.time() - t_prot

            t_call = time.time()
            translated_protected, _ = self.translate_from_english(protected_response, back_translate_lang)
            call_latency = time.time() - t_call

            t_rest = time.time()
            translated_no_vis = restore_terms(translated_protected, mapping, mode=glossary_mode, target_language=back_translate_lang)
            rest_latency = time.time() - t_rest
            
            # Restore visual blocks
            translated_response = restore_visual_blocks(translated_no_vis, vis_mapping)

            translate_out_latency = time.time() - t_translate_out
            timings["translate_out"] = round(translate_out_latency, 3)
            result["translated_from_en"] = translated_response
            
            # Strip show/visual blocks for TTS
            import re
            tts_clean = re.sub(r"<show(?:\s+[^>]*)?>.*?</show>", "", translated_response, flags=re.DOTALL | re.IGNORECASE)
            tts_clean = re.sub(r"<followup>.*?</followup>", "", tts_clean, flags=re.DOTALL | re.IGNORECASE)
            tts_clean = re.sub(r"```.*?```", "", tts_clean, flags=re.DOTALL)
            tts_clean = re.sub(r"</?(?:speak|show|followup|code)(?:\s+[^>]*)?>", "", tts_clean, flags=re.IGNORECASE)
            tts_text = tts_clean.strip()

            try:
                from observability.metrics import (
                    multilingual_glossary_protect_seconds,
                    multilingual_translate_out_seconds,
                    multilingual_glossary_restore_seconds
                )
                multilingual_glossary_protect_seconds.labels(language=back_translate_lang).observe(prot_latency)
                multilingual_translate_out_seconds.labels(language=back_translate_lang).observe(call_latency)
                multilingual_glossary_restore_seconds.labels(language=back_translate_lang).observe(rest_latency)
            except Exception as exc:
                logger.warning("Failed to record back-translation metrics: %s", exc)

        elif use_mms_for_hindi:
            t_translate_out = time.time()
            
            # Protect visual blocks
            resp_no_vis, vis_mapping = protect_visual_blocks(llm_response_english)
            
            t_prot = time.time()
            protected_response, mapping = protect_terms(resp_no_vis)
            prot_latency = time.time() - t_prot

            t_call = time.time()
            translated_protected, _ = self.translate_from_english(protected_response, "hindi")
            call_latency = time.time() - t_call

            t_rest = time.time()
            translated_no_vis = restore_terms(translated_protected, mapping, mode=glossary_mode, target_language="hindi")
            rest_latency = time.time() - t_rest
            
            # Restore visual blocks
            translated_response = restore_visual_blocks(translated_no_vis, vis_mapping)

            translate_out_latency = time.time() - t_translate_out
            timings["translate_out"] = round(translate_out_latency, 3)
            result["translated_from_en"] = translated_response
            
            # Strip show/visual blocks for TTS
            import re
            tts_clean = re.sub(r"<show(?:\s+[^>]*)?>.*?</show>", "", translated_response, flags=re.DOTALL | re.IGNORECASE)
            tts_clean = re.sub(r"<followup>.*?</followup>", "", tts_clean, flags=re.DOTALL | re.IGNORECASE)
            tts_clean = re.sub(r"```.*?```", "", tts_clean, flags=re.DOTALL)
            tts_clean = re.sub(r"</?(?:speak|show|followup|code)(?:\s+[^>]*)?>", "", tts_clean, flags=re.IGNORECASE)
            tts_text = tts_clean.strip()

            try:
                from observability.metrics import (
                    multilingual_glossary_protect_seconds,
                    multilingual_translate_out_seconds,
                    multilingual_glossary_restore_seconds
                )
                multilingual_glossary_protect_seconds.labels(language="hindi").observe(prot_latency)
                multilingual_translate_out_seconds.labels(language="hindi").observe(call_latency)
                multilingual_glossary_restore_seconds.labels(language="hindi").observe(rest_latency)
            except Exception as exc:
                logger.warning("Failed to record back-translation metrics for Hindi: %s", exc)

        # ── Stage 6: TTS Routing ──────────────────────────────────────────────
        if response_lang in ("kannada", "marathi") or use_mms_for_hindi:
            t_tts = time.time()
            wav_bytes, _ = self.synthesize_indic(tts_text, response_lang)
            tts_latency = time.time() - t_tts
            timings["tts"] = round(tts_latency, 3)
            result["tts_wav_bytes"] = wav_bytes
            result["tts_engine"] = "mms"
            result["tts_lang"] = response_lang

            try:
                from observability.metrics import multilingual_tts_ttf_seconds, multilingual_tts_completion_seconds
                # Since this is non-streaming end-to-end, time to first byte of synthesis is the same as the total synthesis latency
                multilingual_tts_ttf_seconds.labels(language=response_lang).observe(tts_latency)
                multilingual_tts_completion_seconds.labels(language=response_lang).observe(tts_latency)
            except Exception as exc:
                logger.warning("Failed to record TTS metrics: %s", exc)
        else:
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
    llm_engine=None,
    kokoro_engine=None
) -> Optional[MultilingualPipeline]:
    """
    Returns the MultilingualPipeline singleton if MULTILINGUAL_ENABLED is True.
    On first call, pass all four engines; subsequent calls return the cached instance.
    """
    global _multilingual_pipeline
    if not Config.MULTILINGUAL_ENABLED:
        return None
    if _multilingual_pipeline is None:
        _multilingual_pipeline = MultilingualPipeline(
            whisper_engine, agent_controller, llm_engine, kokoro_engine
        )
    return _multilingual_pipeline
