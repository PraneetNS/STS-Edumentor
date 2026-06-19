"""
EduMentor Voice — Whisper Speech-to-Text Engine

Wraps faster-whisper for low-latency transcription.
The model is loaded ONCE at startup and kept in memory for the lifetime
of the server — never reloaded between requests.
"""

import logging
from typing import Optional
import numpy as np
from faster_whisper import WhisperModel

from config import Config

logger = logging.getLogger(__name__)


class WhisperEngine:
    """
    Singleton-style Whisper transcription engine.

    Usage:
        engine = WhisperEngine()           # call once at startup
        text   = engine.transcribe(array) # call per user utterance
    """

    def __init__(self) -> None:
        logger.info(
            "Loading Whisper model '%s' on %s (%s) ...",
            Config.WHISPER_MODEL,
            Config.WHISPER_DEVICE,
            Config.WHISPER_COMPUTE_TYPE,
        )
        self.model = WhisperModel(
            Config.WHISPER_MODEL,
            device=Config.WHISPER_DEVICE,
            compute_type=Config.WHISPER_COMPUTE_TYPE,
        )
        self.sample_rate = Config.AUDIO_SAMPLE_RATE
        logger.info("[OK] Whisper engine ready.")

    def transcribe(
        self,
        audio_array: np.ndarray,
        initial_prompt: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> str:
        """
        Transcribe a mono Float32 numpy array (16 kHz) to text.

        Args:
            audio_array: Float32 numpy array, values in [-1.0, 1.0], 16 kHz.
            initial_prompt: Optional initial prompt to guide spelling and context.
            prefix: Optional prefix text for incremental decoding.

        Returns:
            Transcribed text string, or empty string if nothing detected.
        """
        if audio_array is None or len(audio_array) == 0:
            return ""

        from typing import Optional

        segments, info = self.model.transcribe(
            audio_array,
            language="en",
            task="transcribe",
            vad_filter=Config.WHISPER_VAD_FILTER,
            beam_size=1,                           # fastest beam size
            best_of=1,
            temperature=0.0,                       # greedy decoding = faster
            condition_on_previous_text=False,      # stateless per utterance
            initial_prompt=initial_prompt or Config.WHISPER_PROMPT,
            prefix=prefix,
        )

        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info("Transcript: %r (lang=%.2f)", transcript, info.language_probability)
        return transcript
