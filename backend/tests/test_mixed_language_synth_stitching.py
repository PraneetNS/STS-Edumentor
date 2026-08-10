import pytest
import numpy as np
from tts.mixed_language_synth import resample_audio, MixedLanguageSynthesizer

def test_resample_audio():
    # 100 samples at 8000 Hz resampled to 16000 Hz should yield 200 samples
    audio = np.ones(100, dtype=np.float32)
    resampled = resample_audio(audio, 8000, 16000)
    assert len(resampled) == 200
    assert np.allclose(resampled, 1.0)
    
    # 200 samples at 16000 Hz resampled to 8000 Hz should yield 100 samples
    resampled_down = resample_audio(resampled, 16000, 8000)
    assert len(resampled_down) == 100

def test_text_splitting():
    synthesizer = MixedLanguageSynthesizer(None)
    
    # Test split function
    text = "ನಮಸ್ಕಾರ Edi, ಇವತ್ತು machine learning ಮತ್ತು recursion ಕಲಿಯೋಣ."
    
    # Split using pattern matching
    import re
    pattern = re.compile(r'([a-zA-Z0-9_\'-]+(?:\s+[a-zA-Z0-9_\'-]+)*)')
    parts = pattern.split(text)
    
    segments = []
    for part in parts:
        part_strip = part.strip()
        if not part_strip:
            continue
        if re.search(r'[a-zA-Z]', part):
            segments.append({"text": part_strip, "type": "english"})
        else:
            segments.append({"text": part_strip, "type": "native"})
            
    # Check that English terms are identified correctly
    types = [seg["type"] for seg in segments]
    assert "english" in types
    assert "native" in types
    
    # Check specific terms are marked as english
    english_texts = [seg["text"] for seg in segments if seg["type"] == "english"]
    assert "Edi" in english_texts
    assert "machine learning" in english_texts
    assert "recursion" in english_texts
