"""
EduMentor Voice — Speech Normalization Layer

Performs real-time correction of raw user transcripts from Whisper.
Applies:
  1. Exact dictionary substitutions for common tech terms.
  2. Fuzzy matching (via rapidfuzz) to catch close variations of programming terms.
  3. Context-sensitive homophone resolution tailored to computer science.
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger("edumentor.speech.normalizer")

# Stage 1: Technical vocabulary dictionary for exact matching
TECH_TERMS: Dict[str, str] = {
    "wreckursion": "recursion",
    "recurrsion": "recursion",
    "pie torch": "PyTorch",
    "fast api": "FastAPI",
    "react huks": "React hooks",
    "java skript": "JavaScript",
    "cute a": "CUDA",
    "jason": "JSON",
    "versel": "Vercel",
    "pythan": "Python",
    "pie thon": "Python",
}

# Stage 2: Tech vocabulary list for fuzzy matching
TECH_VOCAB: List[str] = [
    "recursion",
    "PyTorch",
    "FastAPI",
    "React hooks",
    "JavaScript",
    "CUDA",
    "JSON",
    "Vercel",
    "Python",
    "cache",
    "Docker",
    "Kubernetes",
    "TypeScript",
    "HTML",
    "CSS",
    "Node.js",
    "Git",
    "Github",
    "Vite",
    "Next.js",
    "API",
    "REST",
    "GraphQL",
    "programming",
]

COMMON_WORDS = {"and", "the", "for", "with", "this", "that", "from", "your", "have", "some", "like", "more", "make", "about", "write", "code"}


class SpeechNormalizer:
    """
    Normalizes speech transcripts by correcting misheard vocabulary
    specifically for technical and programming tutoring.
    """

    def __init__(self, similarity_threshold: float = 80.0) -> None:
        self.threshold = similarity_threshold
        try:
            from rapidfuzz import fuzz  # noqa: PLC0415
            self.fuzz_available = True
        except ImportError:
            self.fuzz_available = False
            logger.warning("rapidfuzz is not installed. Fuzzy matching will be skipped.")

    def normalize(self, text: str, session_id: str = "default") -> str:
        """
        Correct common mishearings and format anomalies in the transcript.

        Args:
            text: Raw Whisper transcript.
            session_id: Active WebSocket connection session identifier.

        Returns:
            Normalized transcript text.
        """
        if not text:
            return ""

        original = text

        # Stage 1: Exact dictionary replacement
        text = self._stage1_dict_correction(text)

        # Stage 2: Context correction
        text = self._stage3_context_correction(text)

        # Stage 3: Fuzzy matching
        if self.fuzz_available:
            text = self._stage2_fuzzy_matching(text)

        if text != original:
            logger.info("Speech Normalizer: %r -> %r", original, text)

        return text

    def _stage1_dict_correction(self, text: str) -> str:
        """Perform exact dictionary substitution for known common misheard terms."""
        # Sort terms by length descending to match multi-word phrases first
        sorted_terms = sorted(TECH_TERMS.items(), key=lambda item: len(item[0]), reverse=True)
        for mishearing, correction in sorted_terms:
            pattern = re.compile(r'\b' + re.escape(mishearing) + r'\b', re.IGNORECASE)
            text = pattern.sub(correction, text)
        return text

    def _stage2_fuzzy_matching(self, text: str) -> str:
        """Perform fuzzy matching of individual words against a tech vocabulary list."""
        from rapidfuzz import fuzz  # noqa: PLC0415

        words = text.split()
        corrected_words = []

        for word in words:
            # Separate prefix/suffix punctuation (e.g. "recursion.") so we only match the core word
            match = re.match(r'^(\W*)(.*?)(\W*)$', word)
            if not match:
                corrected_words.append(word)
                continue

            prefix, core_word, suffix = match.groups()

            # Skip fuzzy checks for very short or common english words
            if len(core_word) < 4 or core_word.lower() in COMMON_WORDS:
                corrected_words.append(word)
                continue

            best_match = None
            best_score = 0.0

            for vocab_item in TECH_VOCAB:
                score = fuzz.ratio(core_word.lower(), vocab_item.lower())
                if score > best_score:
                    best_score = score
                    best_match = vocab_item

            if best_score >= self.threshold and best_match:
                # Respect standard title-casing if user capitalized the word
                if core_word.istitle():
                    corrected_core = best_match.title()
                else:
                    corrected_core = best_match

                corrected_words.append(f"{prefix}{corrected_core}{suffix}")
            else:
                corrected_words.append(word)

        return " ".join(corrected_words)

    def _stage3_context_correction(self, text: str) -> str:
        """Perform context-aware phonetic homophone correction (e.g. cash -> cache)."""
        # "cash memory" / "cash hit" / "cash miss" -> "cache ..."
        text = re.sub(r'\bcash\s+memory\b', 'cache memory', text, flags=re.IGNORECASE)
        text = re.sub(r'\bcash\s+hit\b', 'cache hit', text, flags=re.IGNORECASE)
        text = re.sub(r'\bcash\s+miss\b', 'cache miss', text, flags=re.IGNORECASE)
        text = re.sub(r'\bcash\s+coherence\b', 'cache coherence', text, flags=re.IGNORECASE)
        text = re.sub(r'\bcash\s+line\b', 'cache line', text, flags=re.IGNORECASE)

        # "sea language" / "see language" / "programming in see" -> "C language"
        text = re.sub(r'\bsee\s+language\b', 'C language', text, flags=re.IGNORECASE)
        text = re.sub(r'\bsea\s+language\b', 'C language', text, flags=re.IGNORECASE)
        text = re.sub(r'\bprogramming\s+in\s+see\b', 'programming in C', text, flags=re.IGNORECASE)
        text = re.sub(r'\bprogramming\s+in\s+sea\b', 'programming in C', text, flags=re.IGNORECASE)

        # "see sharp" / "sea sharp" -> "C#"
        text = re.sub(r'\bsee\s+sharp\b', 'C#', text, flags=re.IGNORECASE)
        text = re.sub(r'\bsea\s+sharp\b', 'C#', text, flags=re.IGNORECASE)

        # "dock or compose" / "dock or container" -> "Docker ..."
        text = re.sub(r'\bdock\s+or\b', 'Docker', text, flags=re.IGNORECASE)
        text = re.sub(r'\bdocker\s+compose\b', 'Docker Compose', text, flags=re.IGNORECASE)

        return text


# Module-level singleton instance
speech_normalizer = SpeechNormalizer()
