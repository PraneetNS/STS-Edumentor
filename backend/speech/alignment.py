"""
EduMentor Voice — Speech Text Forced Alignment

Estimates relative word timestamps for synthesized assistant speech.
Uses character-proportional duration estimation to map each word in a
sentence to a specific start and end time inside the generated WAV audio.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger("edumentor.speech.alignment")


def estimate_word_timestamps(text: str, wav_bytes: bytes, sample_rate: int = 24000) -> List[Dict[str, Any]]:
    """
    Estimate word timings for a sentence based on the length of its WAV bytes.

    Args:
        text: The sentence string synthesized by TTS.
        wav_bytes: Synthesized audio WAV file bytes (from Kokoro).
        sample_rate: The native sample rate of the audio (default 24000 Hz for Kokoro).

    Returns:
        A list of dictionaries containing {"word": str, "start": float, "end": float}
        where start/end times are in seconds.
    """
    text = text.strip()
    if not text or not wav_bytes:
        return []

    # A WAV file has a 44-byte header. The remaining bytes are 16-bit (2-byte) PCM samples.
    header_offset = 44
    data_bytes = len(wav_bytes) - header_offset
    if data_bytes <= 0:
        return []

    # 16-bit PCM = 2 bytes per sample, 1 channel (mono)
    num_samples = data_bytes // 2
    duration = num_samples / sample_rate

    # Split text into word tokens
    words = text.split()
    if not words:
        return []

    # Count character lengths of words
    word_lengths = [len(w) for w in words]
    total_word_chars = sum(word_lengths)

    if total_word_chars == 0:
        return []

    # Allocate duration proportionally based on character length.
    # To make it sound more natural, we also factor in space characters between words.
    # We assign 85% of duration to the spoken word characters and 15% to inter-word spacing.
    char_duration = (duration * 0.85) / total_word_chars
    space_duration = (duration * 0.15) / max(1, len(words) - 1)

    timestamps = []
    current_time = 0.0

    for i, (word, length) in enumerate(zip(words, word_lengths)):
        word_dur = length * char_duration
        start = current_time
        end = current_time + word_dur
        
        timestamps.append({
            "word": word,
            "start": round(start, 3),
            "end": round(end, 3),
            "index": i
        })

        # Slide cursor: word duration + spacing between words
        current_time = end + space_duration

    logger.debug(
        "Estimated timestamps for %d words in %.2fs audio clip",
        len(words), duration
    )

    return timestamps
