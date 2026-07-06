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

        import json
        import os
        self.vocab = {}
        vocab_path = os.path.join(os.path.dirname(__file__), "..", "speech", "data", "engineering_vocab.json")
        try:
            if os.path.exists(vocab_path):
                with open(vocab_path, "r", encoding="utf-8-sig") as f:
                    self.vocab = json.load(f)
                logger.info("[OK] WhisperEngine loaded engineering vocabulary for prompt biasing.")
            else:
                logger.warning("engineering_vocab.json not found at %s. Prompt biasing will fall back to config default.", vocab_path)
        except Exception as e:
            logger.error("Failed to load engineering_vocab.json: %s", e)

        logger.info("[OK] Whisper engine ready.")

    def get_prompt_for_discipline(
        self,
        discipline: str,
        user_corrections: Optional[list[str]] = None
    ) -> str:
        """
        Assemble a dynamic prompt biasing list of engineering vocabulary
        and student-specific corrections.
        """
        prompt_terms = []

        # 1. Prepend user-specific corrections (unique words, max 15)
        if user_corrections:
            for phrase in user_corrections:
                for word in phrase.split():
                    word_clean = word.strip(".,!?").capitalize()
                    if word_clean and len(word_clean) > 2 and word_clean not in prompt_terms:
                        prompt_terms.append(word_clean)
                        if len(prompt_terms) >= 15:
                            break
                if len(prompt_terms) >= 15:
                    break

        # 2. Add discipline-specific terms (unique words, max 25)
        discipline_key = discipline if discipline in self.vocab else "cse"
        if self.vocab and discipline_key in self.vocab:
            disc_terms = list(self.vocab[discipline_key].keys())
            for term in disc_terms:
                term_cap = term.capitalize()
                if term_cap not in prompt_terms:
                    prompt_terms.append(term_cap)
                    if len(prompt_terms) >= 40:
                        break

        final_terms = prompt_terms[:40]
        if not final_terms:
            return Config.WHISPER_PROMPT
        
        return ", ".join(final_terms) + "."

    def transcribe_with_confidence(
        self,
        audio_array: np.ndarray,
        initial_prompt: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> tuple[str, float]:
        """
        Transcribe a mono Float32 numpy array (16 kHz) and return transcript + min avg_logprob.
        """
        if audio_array is None or len(audio_array) == 0:
            return "", 0.0

        segments, info = self.model.transcribe(
            audio_array,
            language="en",
            task="transcribe",
            vad_filter=False, # Disable VAD filter to prevent accidental truncation of low-volume or quiet student responses
            beam_size=Config.WHISPER_BEAM_SIZE,
            best_of=Config.WHISPER_BEAM_SIZE,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt or Config.WHISPER_PROMPT,
            prefix=prefix,
        )

        parts = []
        min_avg_logprob = 0.0
        has_segments = False

        for seg in segments:
            text = seg.text.strip()
            if text and not self._is_hallucination(text):
                parts.append(text)
                if not has_segments:
                    min_avg_logprob = seg.avg_logprob
                    has_segments = True
                else:
                    min_avg_logprob = min(min_avg_logprob, seg.avg_logprob)

        transcript = " ".join(parts).strip()
        logger.info(
            "Transcript (with confidence): %r (lang=%.2f, min_avg_logprob=%.2f)",
            transcript, info.language_probability, min_avg_logprob
        )
        return transcript, min_avg_logprob

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
            vad_filter=False, # Disable VAD filter to prevent accidental truncation of low-volume or quiet student responses
            # Using beam size greater than 1 increases vocabulary accuracy and resolves name-mangling
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
