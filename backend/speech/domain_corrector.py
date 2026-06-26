"""
EduMentor Voice — Domain Corrector Layer

Performs real-time, discipline-scoped speech-to-text corrections of engineering terms,
combining dictionary substitutions, longest-match phrase mapping, fuzzy matching, and phonetic indexing.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("edumentor.speech.domain_corrector")

# Common English words that sound like engineering terms but should not be aggressively corrected
COMMON_WORDS_STOPLIST: Set[str] = {
    "cash", "catch", "trust", "talk", "bite", "get", "see", "sea", "sharp",
    "dock", "port", "host", "key", "force", "mass", "flow", "wing", "column", "some"
}


class DomainCorrector:
    """
    Corrects transcription errors scoped to the student's active engineering discipline.
    """

    def __init__(self, vocab_path: str = "data/engineering_vocab.json") -> None:
        self.raw_vocab: Dict[str, Dict[str, List[str]]] = {}

        # Resolve path relative to this file's directory (backend/speech/) so
        # the vocab travels with the package regardless of the working directory.
        if not os.path.isabs(vocab_path):
            vocab_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), vocab_path)
            )

        try:
            with open(vocab_path, "r", encoding="utf-8-sig") as f:
                self.raw_vocab = json.load(f)
            logger.info("Loaded vocabulary from %s for domain correction.", vocab_path)
        except Exception as e:
            logger.error("Failed to load engineering_vocab.json: %s", e)

        # Setup jellyfish phonetic matching
        try:
            import jellyfish
            self.jellyfish_available = True
            logger.info("Jellyfish phonetic library loaded successfully.")
        except ImportError:
            self.jellyfish_available = False
            self.phonetic_indices = {}
            logger.warning("jellyfish is not installed. Phonetic matching will be skipped.")

        # Build per-discipline lookup structures
        self.exact_maps: Dict[str, Dict[str, str]] = {}
        self.phrase_keys_sorted: Dict[str, List[str]] = {}
        self.phrase_to_correct_map: Dict[str, Dict[str, str]] = {}
        self.single_word_terms: Dict[str, List[str]] = {}
        self.phonetic_indices: Dict[str, Dict[str, str]] = {}
        self.canonical_casing: Dict[str, str] = {}
        self.discipline_keywords: Dict[str, Set[str]] = {}

        disciplines = ["cse", "eee", "ece", "mech", "civil", "chemical", "aerospace"]
        for d in disciplines:
            self.exact_maps[d] = {}
            self.phrase_to_correct_map[d] = {}
            self.single_word_terms[d] = []
            self.phonetic_indices[d] = {}
            self.discipline_keywords[d] = set()

            disc_vocab = self.raw_vocab.get(d, {})
            phrase_candidates: Set[str] = set()

            for correct_term, variants in disc_vocab.items():
                correct_term_lower = correct_term.lower()
                self.canonical_casing[correct_term_lower] = correct_term

                # Gather keywords for stoplist verification (canonical terms only)
                for w in correct_term_lower.split():
                    self.discipline_keywords[d].add(w)

                # Add direct correct term as a single word or phrase
                if " " in correct_term:
                    phrase_candidates.add(correct_term)
                    self.phrase_to_correct_map[d][correct_term_lower] = correct_term
                else:
                    self.single_word_terms[d].append(correct_term_lower)

                for v in variants:
                    v_lower = v.lower()
                    self.exact_maps[d][v_lower] = correct_term

                    if " " in v:
                        phrase_candidates.add(v)
                        self.phrase_to_correct_map[d][v_lower] = correct_term

            # Sort phrases by descending token count (longest phrase first), then length
            sorted_phrases = sorted(
                list(phrase_candidates),
                key=lambda x: (len(x.split()), len(x)),
                reverse=True
            )
            self.phrase_keys_sorted[d] = sorted_phrases

            # Build phonetic index for single words
            if self.jellyfish_available:
                import jellyfish
                for term in self.single_word_terms[d]:
                    try:
                        phon = jellyfish.metaphone(term)
                        if phon:
                            self.phonetic_indices[d][phon] = self.canonical_casing.get(term, term)
                    except Exception:
                        pass

    def _apply_casing(self, original: str, corrected: str) -> str:
        """Preserve original capitalization patterns or enforce canonical casing."""
        corrected_lower = corrected.lower()
        canonical = self.canonical_casing.get(corrected_lower, corrected)

        # Enforce canonical casing if it has uppercase (acronym / proper noun)
        if any(c.isupper() for c in canonical):
            return canonical

        # Otherwise, match original word casing pattern
        match = re.match(r'^(\W*)(.*?)(\W*)$', original)
        core = match.group(2) if match else original

        if core.isupper() and len(core) > 1:
            return corrected.upper()
        if core.istitle():
            return corrected.title()
        return corrected

    def correct_sentence(self, text: str, discipline: str = "cse") -> Tuple[str, List[Tuple[str, str]]]:
        """
        Correct all misheard technical terms in a sentence using discipline-scoped mapping.
        Returns (corrected_sentence, list_of_changes).
        """
        if not text:
            return "", []

        disc_key = discipline if discipline in self.exact_maps else "cse"
        tokens = text.split()
        if not tokens:
            return "", []

        consumed = [False] * len(tokens)
        changes_list: List[Tuple[str, str]] = []

        # Extract keywords in user sentence for stoplist co-occurrence check
        sentence_keywords = set()
        for tok in tokens:
            m = re.match(r'^(\W*)(.*?)(\W*)$', tok)
            if m:
                sentence_keywords.add(m.group(2).lower())

        # Step 1: Longest-match-first phrase substitution
        phrase_keys = self.phrase_keys_sorted.get(disc_key, [])
        for phrase in phrase_keys:
            phrase_tokens = phrase.split()
            plen = len(phrase_tokens)
            i = 0
            while i <= len(tokens) - plen:
                if not any(consumed[i + j] for j in range(plen)):
                    window_match = True
                    for j in range(plen):
                        tok = tokens[i + j]
                        m = re.match(r'^(\W*)(.*?)(\W*)$', tok)
                        core = m.group(2).lower() if m else tok.lower()
                        if core != phrase_tokens[j].lower():
                            window_match = False
                            break

                    if window_match:
                        correct_term = self.phrase_to_correct_map[disc_key].get(phrase.lower(), phrase)
                        
                        # Preserve punctuation
                        first_match = re.match(r'^(\W*)(.*?)(\W*)$', tokens[i])
                        last_match = re.match(r'^(\W*)(.*?)(\W*)$', tokens[i + plen - 1])
                        prefix = first_match.group(1) if first_match else ""
                        suffix = last_match.group(3) if last_match else ""

                        cased_term = self._apply_casing(tokens[i], correct_term)

                        # Capture raw phrase chunk
                        raw_phrase = " ".join(
                            re.match(r'^(\W*)(.*?)(\W*)$', tokens[i + j]).group(2)
                            for j in range(plen)
                        )
                        
                        if raw_phrase.lower() != correct_term.lower():
                            changes_list.append((raw_phrase, correct_term))

                        tokens[i] = f"{prefix}{cased_term}{suffix}"
                        for j in range(1, plen):
                            tokens[i + j] = ""
                            consumed[i + j] = True
                        consumed[i] = True
                        i += plen - 1
                i += 1

        # Step 2: Single-word corrections on remaining unconsumed words
        from config import Config
        fuzzy_threshold = getattr(Config, "FUZZY_MATCH_THRESHOLD", 80.0)

        for i in range(len(tokens)):
            if not tokens[i] or consumed[i]:
                continue

            m = re.match(r'^(\W*)(.*?)(\W*)$', tokens[i])
            if not m:
                continue

            prefix, core, suffix = m.groups()
            if not core:
                continue

            corrected_core = self.correct_word_internal(
                core, disc_key, sentence_keywords, fuzzy_threshold
            )
            if corrected_core != core:
                cased_corrected = self._apply_casing(core, corrected_core)
                changes_list.append((core, corrected_core))
                tokens[i] = f"{prefix}{cased_corrected}{suffix}"

        # Clean empty spaces resulting from phrase replacements
        cleaned_sentence = " ".join(t for t in tokens if t)
        return cleaned_sentence, changes_list

    def correct_word_internal(
        self, word: str, discipline: str, sentence_keywords: Set[str], fuzzy_threshold: float
    ) -> str:
        """Internal correction logic with stoplist and co-occurrence checks."""
        word_lower = word.lower()

        # Stoplist Check first
        if word_lower in COMMON_WORDS_STOPLIST:
            # Require at least one other discipline term in the sentence to allow correction
            disc_keywords = self.discipline_keywords.get(discipline, set())
            other_keywords = sentence_keywords - {word_lower}
            if not (other_keywords & disc_keywords):
                return word

        exact_map = self.exact_maps.get(discipline, {})
        # 1. Exact direct mishearing lookup
        if word_lower in exact_map:
            return exact_map[word_lower]

        # Skip fuzzy/phonetic corrections for very short words (avoids false-positive grammar collisions)
        if len(word_lower) < 4:
            return word

        # 2. Fuzzy string matching (Rapidfuzz ratio)
        from rapidfuzz import fuzz, process
        single_words = self.single_word_terms.get(discipline, [])
        if single_words:
            match_res = process.extractOne(word_lower, single_words, scorer=fuzz.ratio)
            if match_res:
                match_word, score = match_res[0], match_res[1]
                if score >= fuzzy_threshold:
                    return match_word

        # 3. Phonetic matching (Jellyfish Metaphone)
        if self.jellyfish_available:
            import jellyfish
            try:
                phon = jellyfish.metaphone(word_lower)
                if phon:
                    phon_map = self.phonetic_indices.get(discipline, {})
                    if phon in phon_map:
                        return phon_map[phon].lower()
            except Exception:
                pass

        return word

    def correct_word(self, word: str, discipline: str = "cse") -> str:
        """Thin wrapper for unit testing single words in isolation."""
        from config import Config
        fuzzy_threshold = getattr(Config, "FUZZY_MATCH_THRESHOLD", 80.0)
        return self.correct_word_internal(word, discipline, {word.lower()}, fuzzy_threshold)


# Module-level singleton
domain_corrector = DomainCorrector()
