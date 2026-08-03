"""
Unit tests for the multilingual STT pipeline.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from speech.multilingual_pipeline import MultilingualPipeline


def test_pick_allowed_lang_prefers_indic_over_english_on_tie():
    """Ensure equal-probability Indic languages beat English when the model is uncertain."""
    pipeline = MultilingualPipeline.__new__(MultilingualPipeline)
    pipeline.ALLOWED_LANGS = {"en", "hi", "kn", "mr"}

    best_lang, best_prob = pipeline._pick_allowed_lang([
        ("en", 0.5),
        ("hi", 0.5),
        ("kn", 0.4),
    ])

    assert best_lang == "hi"
    assert best_prob == 0.5


def test_transcribe_multilingual_auto_detects_supported_indic_language():
    """The multilingual STT path should preserve a supported auto-detected Indic language."""
    mock_model = MagicMock()
    mock_segments = [SimpleNamespace(text="ನಮಸ್ಕಾರ"), SimpleNamespace(text="")]
    mock_info = SimpleNamespace(language="kn", language_probability=0.72)

    mock_model.transcribe.return_value = (mock_segments, mock_info)
    whisper_engine = MagicMock()
    whisper_engine.model = mock_model

    pipeline = MultilingualPipeline.__new__(MultilingualPipeline)
    pipeline.whisper_engine = whisper_engine

    transcript, detected_lang, latency = pipeline.transcribe_multilingual(
        audio_array=None,
        initial_prompt=None,
    )

    assert transcript == "ನಮಸ್ಕಾರ"
    assert detected_lang == "kn"
    assert latency >= 0.0
    mock_model.detect_language.assert_not_called()
    mock_model.transcribe.assert_called_once()
