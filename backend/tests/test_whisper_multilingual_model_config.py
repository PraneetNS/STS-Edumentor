import pytest
from config import Config

def test_whisper_multilingual_model_config():
    """
    Asserts that if MULTILINGUAL_ENABLED is True, the Whisper model is NOT an English-only model.
    English-only models in faster-whisper end with '.en' (e.g. 'small.en', 'base.en', 'tiny.en').
    """
    if Config.MULTILINGUAL_ENABLED:
        model_name = Config.WHISPER_MODEL
        assert not model_name.endswith(".en"), (
            f"Regression Guard: Config.MULTILINGUAL_ENABLED is True, but "
            f"Config.WHISPER_MODEL is set to '{model_name}', which is an English-only model! "
            f"Please set WHISPER_MODEL to a multilingual model (e.g., 'small', 'base', 'medium') "
            f"in the environment or .env file."
        )
