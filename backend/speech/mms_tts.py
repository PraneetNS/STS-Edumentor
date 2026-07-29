"""
EduMentor Voice — AI4Bharat indic-parler-tts Engine

Replaces Meta MMS-TTS with the AI4Bharat indic-parler-tts model for
high-quality, natural Indic TTS (Hindi, Kannada, Marathi, and 21+ other languages).

Gated model: requires HF_TOKEN with accepted terms at:
  https://huggingface.co/ai4bharat/indic-parler-tts

Requires:
  pip install git+https://github.com/huggingface/parler-tts.git
"""

import io
import logging
import time
from typing import Optional

import numpy as np
import soundfile as sf
import torch

logger = logging.getLogger("edumentor.speech.mms_tts")

# Voice description for indic-parler-tts
# Controls gender, pace, and quality of Indic output
_VOICE_DESCRIPTION = (
    "A female speaker with a clear, natural, and calm voice. "
    "The recording is of high quality with a slight room acoustic."
)

# Language name → Parler-TTS description modifier
_LANG_DESC_MAP = {
    "hin": "The speaker speaks in Hindi.",
    "kan": "The speaker speaks in Kannada.",
    "mar": "The speaker speaks in Marathi.",
}


class MMSTTSEngine:
    """
    AI4Bharat indic-parler-tts engine (replaces Meta MMS-TTS).

    Exposes the same synthesize(text, lang) interface so no changes
    are needed in multilingual_pipeline.py.
    """

    MODEL_ID = "ai4bharat/indic-parler-tts"

    def __init__(self) -> None:
        import threading
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self.warmed_up = False
        logger.info(
            "[OK] IndicParlerTTS engine initialized (lazy-load, device=%s).", self.device
        )
        # Start background warmup to load weights and synthesize a dummy character per language
        threading.Thread(target=self._background_warmup, daemon=True).start()

    def _load_model(self) -> None:
        """Lazy-load the indic-parler-tts model on first synthesis call."""
        with self._lock:
            if self._model is None:
                from parler_tts import ParlerTTSForConditionalGeneration
                from transformers import AutoTokenizer

                logger.info("Loading AI4Bharat indic-parler-tts model (%s) ...", self.MODEL_ID)
                t0 = time.time()

                import os
                hf_token = os.getenv("HF_TOKEN")
                self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID, token=hf_token)
                self._model = ParlerTTSForConditionalGeneration.from_pretrained(
                    self.MODEL_ID,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    token=hf_token,
                ).to(self.device)
                self._model.eval()

                logger.info(
                    "[OK] indic-parler-tts loaded in %.2fs on %s.", time.time() - t0, self.device
                )

    def _background_warmup(self) -> None:
        """Load model and run a dummy synthesis for each supported language to warm cache."""
        logger.info("Starting background warmup for IndicParlerTTS...")
        try:
            self._load_model()
            # Synthesize one character per supported language to cache voice weights
            for lang_code in ["hin", "kan", "mar"]:
                logger.info("Warming up IndicParlerTTS voice weights for lang '%s'...", lang_code)
                self.synthesize("म", lang_code)
            self.warmed_up = True
            logger.info("IndicParlerTTS background warmup complete.")
        except Exception as e:
            logger.warning("IndicParlerTTS background warmup failed: %s", e)

    def synthesize(self, text: str, lang: str) -> bytes:
        """
        Synthesize text into WAV bytes using AI4Bharat indic-parler-tts.

        Args:
            text: Text in the target Indic script (or romanized).
            lang: Language code — 'hin', 'kan', 'mar'.

        Returns:
            WAV bytes (16-bit PCM at model sample rate), or b"" on error.
        """
        text = text.strip()
        if not text:
            return b""

        t_start = time.time()
        try:
            self._load_model()

            lang_mod = _LANG_DESC_MAP.get(lang, "")
            description = f"{_VOICE_DESCRIPTION} {lang_mod}".strip()

            # Tokenize description (controls voice style)
            desc_input = self._tokenizer(
                description,
                return_tensors="pt",
            ).to(self.device)

            # Tokenize text (the content to speak)
            text_input = self._tokenizer(
                text,
                return_tensors="pt",
            ).to(self.device)

            # Generate waveform
            with torch.inference_mode():
                generation = self._model.generate(
                    input_ids=desc_input.input_ids,
                    attention_mask=desc_input.attention_mask,
                    prompt_input_ids=text_input.input_ids,
                    prompt_attention_mask=text_input.attention_mask,
                )

            audio_arr = generation.cpu().float().numpy().squeeze()
            sampling_rate = self._model.config.sampling_rate

            # Encode to WAV bytes
            buf = io.BytesIO()
            sf.write(buf, audio_arr, sampling_rate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            wav_bytes = buf.read()

            latency = time.time() - t_start
            logger.debug(
                "indic-parler-tts synthesized %d chars (%s) → %d bytes WAV in %.2fs",
                len(text), lang, len(wav_bytes), latency,
            )
            return wav_bytes

        except Exception as e:
            logger.exception(
                "indic-parler-tts synthesis failed for %r (%s): %s", text[:60], lang, e
            )
            return b""


# Singleton
_mms_tts_engine: Optional[MMSTTSEngine] = None


def get_mms_tts_engine() -> MMSTTSEngine:
    """Get or initialize the global MMSTTSEngine singleton."""
    global _mms_tts_engine
    if _mms_tts_engine is None:
        _mms_tts_engine = MMSTTSEngine()
    return _mms_tts_engine
