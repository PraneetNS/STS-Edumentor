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

        segments, info = self.model.transcribe(
            audio_array,
            language="en",
            task="transcribe",
            vad_filter=True,                       # Skip silent/noisy segments before decoding
            vad_parameters=dict(
                min_silence_duration_ms=300,       # Minimum silence gap to split on
                speech_pad_ms=200,                 # Padding around detected speech
            ),
            beam_size=Config.WHISPER_BEAM_SIZE,
            best_of=Config.WHISPER_BEAM_SIZE,
            temperature=0.0,                       # greedy decoding = faster
            condition_on_previous_text=False,      # stateless per utterance
            initial_prompt=initial_prompt or Config.WHISPER_PROMPT,
            prefix=prefix,
        )

        parts = []
        for seg in segments:
            text = seg.text.strip()
            if text and not self._is_hallucination(text):
                parts.append(text)

        transcript = " ".join(parts).strip()
        logger.info("Transcript: %r (lang=%.2f)", transcript, info.language_probability)
        return transcript

    @staticmethod
    def _is_hallucination(text: str) -> bool:
        """
        Return True if the segment looks like a Whisper hallucination.

        Whisper commonly hallucinates on silent / low-energy audio:
          - Repeated punctuation:  "...", "- - -", "———"
          - Tag-style artifacts:   "[Music]", "(Silence)", "[BLANK_AUDIO]"
          - Single-char noise:     ".", "-", "*"
          - Nonsense repetition:   "vvvvvv", "aaaa"
          - Common filler phrases that appear with no real speech
        """
        import re

        # Strip outer whitespace
        t = text.strip()

        if not t:
            return True

        # Pure punctuation / whitespace only (dots, dashes, underscores, spaces)
        if re.fullmatch(r"[\s.·•\-_—–~*#]+", t):
            return True

        # Whisper tag artifacts: [Music], (Silence), [BLANK_AUDIO], etc.
        if re.fullmatch(r"[\[\(].*[\]\)]\.?", t, re.IGNORECASE):
            return True

        # Repeated single character noise (e.g. "vvvvvvv", "aaaaaaa")
        if len(t) > 3 and len(set(t.lower().replace(" ", ""))) <= 2:
            return True

        # Known filler hallucination phrases Whisper emits on silence
        HALLUCINATION_PHRASES = {
            "thank you",
            "thank you.",
            "thanks for watching",
            "thanks for watching.",
            "you",
            ".",
            "..",
            "...",
            "....",
            "- - -",
            "—",
            "[ music ]",
            "[music]",
            "( music )",
            "(music)",
            "[ silence ]",
            "[silence]",
            "( silence )",
            "(silence)",
            "[blank_audio]",
            "[ blank_audio ]",
            "subtitles by",
            "transcribed by",
        }
        if t.lower() in HALLUCINATION_PHRASES:
            return True

        return False
