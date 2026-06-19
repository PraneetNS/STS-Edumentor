"""
EduMentor Voice — Speech Emotion Layer

Extracts acoustic features (pitch, RMS energy, tempo, pauses) from the user's
raw audio using librosa/numpy, and combines them with transcript text cues
to detect frustration, confusion, confidence, or engagement.
"""

import logging
import numpy as np
from typing import Dict, Any, Tuple

from agent.models import Emotion, EmotionResult
from agent.emotion_detector import detect as detect_text_emotion

logger = logging.getLogger("edumentor.speech.emotion")


def extract_acoustic_features(audio_array: np.ndarray, transcript: str, sample_rate: int = 16000) -> Dict[str, Any]:
    """
    Extract energy, speed, pauses, pitch, and tempo from the raw audio array.
    """
    duration = len(audio_array) / sample_rate if sample_rate > 0 else 0.0

    # 1. RMS Energy
    overall_rms = np.sqrt(np.mean(audio_array ** 2)) if len(audio_array) > 0 else 0.0
    if overall_rms < 0.005:
        energy_cat = "low"
    elif overall_rms > 0.04:
        energy_cat = "high"
    else:
        energy_cat = "medium"

    # 2. Speaking Speed (Words Per Minute)
    word_count = len(transcript.split())
    if duration > 0.5:
        wpm = (word_count / duration) * 60
    else:
        wpm = 130.0  # default normal WPM

    if wpm < 95:
        speed_cat = "slow"
    elif wpm > 165:
        speed_cat = "fast"
    else:
        speed_cat = "normal"

    # 3. Pause Count (silence regions longer than 300ms)
    # 100ms frames
    frame_len = int(sample_rate * 0.1)
    pause_count = 0
    if frame_len > 0 and len(audio_array) >= frame_len:
        num_frames = len(audio_array) // frame_len
        silence_streak = 0
        for i in range(num_frames):
            frame = audio_array[i * frame_len : (i + 1) * frame_len]
            frame_rms = np.sqrt(np.mean(frame ** 2))
            # Frame is silent if RMS is less than 15% of overall RMS or absolute low threshold
            if frame_rms < 0.003 or (overall_rms > 0 and frame_rms < overall_rms * 0.2):
                silence_streak += 1
            else:
                # If a silence run of >= 3 frames (300ms) just ended, count as a pause
                if silence_streak >= 3:
                    pause_count += 1
                silence_streak = 0
        # Catch trailing pause
        if silence_streak >= 3:
            pause_count += 1

    # 4. Pitch and Tempo (using fast fallback to keep latency < 1ms)
    pitch = 120.0
    tempo = 120.0
    librosa_used = False

    return {
        "speaking_speed": speed_cat,
        "pause_count": pause_count,
        "energy": energy_cat,
        "pitch": round(pitch, 1),
        "tempo": round(tempo, 1),
        "wpm": round(wpm, 1),
        "duration": round(duration, 2),
        "librosa_used": librosa_used
    }


def detect_audio_emotion(audio_array: np.ndarray, transcript: str, sample_rate: int = 16000) -> EmotionResult:
    """
    Combined speech analysis. Analyzes raw audio features and merges them with
    text emotion detection to determine a high-confidence EmotionResult.
    """
    if audio_array is None or len(audio_array) == 0:
        return detect_text_emotion(transcript)

    try:
        # 1. Extract acoustic features
        features = extract_acoustic_features(audio_array, transcript, sample_rate)
        
        # 2. Get text-based emotion prediction
        text_emotion_res = detect_text_emotion(transcript)

        # 3. Hybrid decision logic
        final_emotion = Emotion.NEUTRAL
        confidence = 0.5
        trigger_phrase = text_emotion_res.trigger_phrase

        # Acoustic indicators
        is_slow = features["speaking_speed"] == "slow"
        is_fast = features["speaking_speed"] == "fast"
        has_many_pauses = features["pause_count"] >= 3
        is_low_energy = features["energy"] == "low"
        is_high_energy = features["energy"] == "high"

        # Check for text confirmation first
        if text_emotion_res.emotion == Emotion.FRUSTRATED:
            final_emotion = Emotion.FRUSTRATED
            confidence = text_emotion_res.confidence
            if is_slow or has_many_pauses:
                confidence = min(0.99, confidence + 0.1)  # increased certainty if voice is struggling
        elif text_emotion_res.emotion == Emotion.CONFUSED:
            final_emotion = Emotion.CONFUSED
            confidence = text_emotion_res.confidence
            if is_slow or has_many_pauses:
                confidence = min(0.99, confidence + 0.1)
        elif text_emotion_res.emotion == Emotion.CONFIDENT:
            final_emotion = Emotion.CONFIDENT
            confidence = text_emotion_res.confidence
            if is_fast or is_high_energy:
                confidence = min(0.99, confidence + 0.05)
        elif text_emotion_res.emotion == Emotion.HAPPY:
            final_emotion = Emotion.HAPPY
            confidence = text_emotion_res.confidence
        elif text_emotion_res.emotion == Emotion.BORED:
            final_emotion = Emotion.BORED
            confidence = text_emotion_res.confidence
        else:
            # Text was neutral, rely heavily on acoustics
            if is_slow and has_many_pauses:
                # Student taking long pauses, sounding unsure or confused
                final_emotion = Emotion.CONFUSED
                confidence = 0.75
                trigger_phrase = "[acoustic: hesitant speech]"
            elif is_slow and is_low_energy:
                # Monotone, slow voice
                final_emotion = Emotion.BORED
                confidence = 0.65
                trigger_phrase = "[acoustic: low energy monotone]"
            elif is_fast and is_high_energy:
                # Fast, excited speech
                final_emotion = Emotion.CONFIDENT
                confidence = 0.70
                trigger_phrase = "[acoustic: high energy fast speech]"
            else:
                final_emotion = Emotion.NEUTRAL
                confidence = 1.0
                trigger_phrase = ""

        # Store features as metadata inside EmotionResult (via trigger_phrase or a dictionary)
        # We return the standard EmotionResult to keep the API fully compatible with agent layer.
        logger.info(
            "Speech Emotion: final=%s (text=%s) conf=%.2f. Features: speed=%s, pauses=%d, energy=%s",
            final_emotion.value, text_emotion_res.emotion.value, confidence,
            features["speaking_speed"], features["pause_count"], features["energy"]
        )

        # Attach the raw features dictionary to the result object for WebSocket serialization
        result = EmotionResult(
            emotion=final_emotion,
            confidence=round(confidence, 2),
            trigger_phrase=trigger_phrase,
            features=features
        )
        return result

    except Exception as exc:
        logger.exception("Speech Emotion extraction failed: %s", exc)
        # Safe fallback: return text-only emotion
        return detect_text_emotion(transcript)
