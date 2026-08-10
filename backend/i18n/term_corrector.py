import os
import re
import yaml
from rapidfuzz import fuzz
from i18n.term_glossary import normalize_lang

# Default glossary path
GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), "protected_terms.yaml")

_glossary_cache = None

def get_glossary():
    global _glossary_cache
    if _glossary_cache is None:
        if os.path.exists(GLOSSARY_PATH):
            with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
                _glossary_cache = yaml.safe_load(f) or []
        else:
            _glossary_cache = []
    return _glossary_cache

def correct_technical_terms(transcript: str, language: str) -> str:
    """
    Fuzzy-matches transliterated regional variants of technical terms in transcript
    and replaces them with the canonical English term.
    Uses a sliding window for matching multi-word and single-word terms to preserve spacing and punctuation.
    """
    if not transcript:
        return transcript

    normalized_lang = normalize_lang(language)
    if normalized_lang not in ("hindi", "kannada", "marathi"):
        return transcript

    glossary = get_glossary()
    lang_key = f"{normalized_lang}_variants"

    # Gather all (variant, canonical) pairs for this language
    variant_map = []
    for entry in glossary:
        canonical = entry.get("canonical", "")
        variants = entry.get(lang_key) or []
        # Include canonical itself in case it's spoken or written in English
        variant_map.append((canonical.lower(), canonical))
        for v in variants:
            variant_map.append((v.lower(), canonical))

    if not variant_map:
        return transcript

    # Find all words and their start/end indices in the transcript.
    # Matches words containing English/Latin and Indic characters.
    word_pattern = re.compile(r"[a-zA-Z0-9_\u0900-\u097f\u0c80-\u0cff]+")
    matches = list(word_pattern.finditer(transcript))
    if not matches:
        return transcript

    # Build list of tokens with spans
    tokens = []
    for m in matches:
        tokens.append({
            "text": m.group(0),
            "start": m.start(),
            "end": m.end()
        })

    n_tokens = len(tokens)
    proposed_matches = []

    # Sliding window of size 3 down to 1
    for sz in (3, 2, 1):
        for i in range(n_tokens - sz + 1):
            window_tokens = tokens[i : i + sz]
            start_pos = window_tokens[0]["start"]
            end_pos = window_tokens[-1]["end"]
            span_text = transcript[start_pos:end_pos].strip()

            best_canonical = None
            best_score = 0.0
            best_variant_len = 0
            for variant, canonical in variant_map:
                score = fuzz.ratio(span_text.lower(), variant)
                if score > best_score:
                    best_score = score
                    best_canonical = canonical
                    best_variant_len = len(variant)

            # Match threshold: 85% for short spans/variants (< 6 chars) to prevent false matches
            # on short common words (e.g. "करें" matching "current" via "करंट"), 72% for longer words.
            req_threshold = 85 if (best_variant_len < 6 or len(span_text) < 6) else 72
            if best_score >= req_threshold:
                proposed_matches.append({
                    "start": start_pos,
                    "end": end_pos,
                    "canonical": best_canonical,
                    "score": best_score,
                    "length": sz
                })

    # Resolve overlaps: prefer higher score, then longer phrase length
    proposed_matches.sort(key=lambda x: (x["score"], x["length"]), reverse=True)
    selected_matches = []
    
    def overlaps(m1, m2):
        return not (m1["end"] <= m2["start"] or m2["end"] <= m1["start"])

    for m in proposed_matches:
        conflict = False
        for s in selected_matches:
            if overlaps(m, s):
                conflict = True
                break
        if not conflict:
            selected_matches.append(m)

    # Reconstruct transcript with canonical terms
    selected_matches.sort(key=lambda x: x["start"])
    new_transcript = ""
    last_idx = 0
    for m in selected_matches:
        new_transcript += transcript[last_idx:m["start"]] + m["canonical"]
        last_idx = m["end"]
    new_transcript += transcript[last_idx:]

    return new_transcript
