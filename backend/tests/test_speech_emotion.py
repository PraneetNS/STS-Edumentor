"""
Tests — Speech Emotion Layer

Covers acoustic feature extraction and hybrid emotion classification (acoustics + text).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np
from speech.emotion import extract_acoustic_features, detect_audio_emotion
from agent.models import Emotion


def test_extract_acoustic_features_silence():
    # 1 second of silence at 16000 Hz
    audio = np.zeros(16000)
    features = extract_acoustic_features(audio, "hello", sample_rate=16000)
    
    assert features["energy"] == "low"
    assert features["duration"] == 1.0
    assert features["pause_count"] == 1  # 1 continuous trailing pause at the end


def test_extract_acoustic_features_normal():
    # 2 seconds of high energy sound
    np.random.seed(42)
    audio = np.random.normal(0, 0.1, 32000)
    features = extract_acoustic_features(audio, "hello world this is a test segment", sample_rate=16000)
    
    assert features["energy"] == "high"
    assert features["duration"] == 2.0
    # No silent frames of >= 300ms, so pause_count should be 0
    assert features["pause_count"] == 0


def test_extract_acoustic_features_pauses():
    # Construct audio with a silence period in the middle
    # 500ms sound (8000 samples)
    # 500ms silence (8000 samples)
    # 500ms sound (8000 samples)
    # Total: 1.5 seconds
    np.random.seed(42)
    sound1 = np.random.normal(0, 0.05, 8000)
    silence = np.zeros(8000)
    sound2 = np.random.normal(0, 0.05, 8000)
    audio = np.concatenate([sound1, silence, sound2])
    
    features = extract_acoustic_features(audio, "hello world python code", sample_rate=16000)
    
    # Check that a pause is detected in the middle
    assert features["pause_count"] >= 1
    assert features["duration"] == 1.5


def test_detect_audio_emotion_hybrid_text_override():
    # If text is strongly frustrated, final emotion should be frustrated
    audio = np.zeros(16000)
    result = detect_audio_emotion(audio, "I still don't understand this, it is so confusing")
    assert result.emotion == Emotion.FRUSTRATED


def test_detect_audio_emotion_acoustic_only_confused():
    # Text is neutral, but speech is slow and hesitant (many pauses)
    # 3 seconds of audio: sound -> silence -> sound -> silence -> sound -> silence
    # Let's mock a case with many pauses
    np.random.seed(42)
    audio = np.concatenate([
        np.random.normal(0, 0.05, 5000), # 312ms
        np.zeros(8000),                  # 500ms (pause 1)
        np.random.normal(0, 0.05, 5000), # 312ms
        np.zeros(8000),                  # 500ms (pause 2)
        np.random.normal(0, 0.05, 5000), # 312ms
        np.zeros(8000),                  # 500ms (pause 3)
    ])
    
    # 3 words over 3.9 seconds (~46 WPM -> slow)
    result = detect_audio_emotion(audio, "I... don't... know", sample_rate=16000)
    
    # Slow speech + many pauses + neutral text -> classified as CONFUSED
    assert result.emotion == Emotion.CONFUSED
    assert "acoustic:" in result.trigger_phrase


def test_detect_audio_emotion_acoustic_only_bored():
    # Text is neutral, but voice is slow and low energy (monotone)
    audio = np.random.normal(0, 0.001, 48000)  # low volume noise, 3 seconds
    # 4 words in 3 seconds = 80 WPM (slow)
    result = detect_audio_emotion(audio, "what do we do", sample_rate=16000)
    
    assert result.emotion == Emotion.BORED
    assert "low energy" in result.trigger_phrase
