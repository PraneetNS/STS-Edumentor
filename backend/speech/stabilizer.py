"""
EduMentor Voice — Live Transcript Stabilizer

Heuristic-based transcript stabilization to identify "confirmed" vs "temporary"
words as they stream in from Whisper STT.
"""

from typing import List, Dict, Any


class TranscriptStabilizer:
    """
    Stabilizes real-time Whisper transcript streams.
    
    Categorises words into 'confirmed' (white, stable) and 'temporary' (grey, unstable).
    Uses a prefix-matching heuristic compared against previous live updates, combined
    with a safe lag threshold to commit older words.
    """

    def __init__(self) -> None:
        self.prev_words: List[str] = []

    def reset(self) -> None:
        """Reset the stabilizer state for a new speaking turn."""
        self.prev_words = []

    def stabilize(self, text: str) -> List[Dict[str, Any]]:
        """
        Processes a new raw live transcript text and returns a list of word dictionaries
        with statuses: {"word": str, "status": "confirmed" | "temporary"}.
        """
        new_words = text.split()
        if not new_words:
            return []

        # 1. Match prefix with previous words
        matching_len = 0
        for w1, w2 in zip(self.prev_words, new_words):
            if w1 == w2:
                matching_len += 1
            else:
                break

        # 2. To avoid high latency on confirming, we also safely confirm
        # everything except the last 2 words of the current utterance.
        safe_confirm_len = max(matching_len, len(new_words) - 2)
        safe_confirm_len = min(safe_confirm_len, len(new_words))

        words_payload = []
        for i, w in enumerate(new_words):
            status = "confirmed" if i < safe_confirm_len else "temporary"
            words_payload.append({
                "word": w,
                "status": status
            })

        self.prev_words = new_words
        return words_payload
