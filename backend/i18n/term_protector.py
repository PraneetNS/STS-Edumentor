import os
import re
import yaml

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

def mask_protected_terms(text: str, language: str = "english") -> tuple[str, dict]:
    """
    Finds all canonical English terms and their regional language variants in the text
    and replaces them with placeholders '__TERM_X__'.
    Returns (masked_text, placeholder_to_canonical_map).
    """
    if not text:
        return "", {}

    glossary = get_glossary()
    normalized_lang = language.lower()

    # We build a list of (target_phrase, canonical_english_term)
    targets = []
    lang_key = f"{normalized_lang}_variants"
    
    for entry in glossary:
        canonical = entry.get("canonical", "")
        if not canonical:
            continue
            
        # English canonical is always a target
        targets.append((canonical, canonical))
        
        # Regional variants are targets if the language is regional
        if normalized_lang in ("hindi", "kannada", "marathi"):
            variants = entry.get(lang_key) or []
            for v in variants:
                targets.append((v, canonical))

    # Dedup and sort targets by length descending so longer phrases match first
    seen = set()
    deduped_targets = []
    for match_text, eng_term in targets:
        match_lower = match_text.lower()
        if match_lower not in seen:
            seen.add(match_lower)
            deduped_targets.append((match_text, eng_term))
            
    deduped_targets.sort(key=lambda x: len(x[0]), reverse=True)

    mapping = {}
    modified_text = text
    placeholder_idx = 0

    for match_text, eng_term in deduped_targets:
        # Match whole word/phrase case-insensitively.
        # Support optional trailing 's' or 'es' for English canonical terms to handle plurals
        if re.search(r'[a-zA-Z]', match_text):
            pattern = re.compile(rf"\b{re.escape(match_text)}(?:es|s)?\b", re.IGNORECASE)
        else:
            # Indic script: no boundary (\b) support in standard regex for non-latin.
            # We match with lookarounds to prevent partial word matches of Indic characters.
            # Special case for conversational exclamations followed by punctuation
            if match_text in ("अरे", "ಅರೇ"):
                pattern = re.compile(
                    rf"(?<![a-zA-Z0-9_\u0900-\u097f\u0c80-\u0cff]){re.escape(match_text)}(?![a-zA-Z0-9_\u0900-\u097f\u0c80-\u0cff])(?![!,])",
                    re.IGNORECASE
                )
            else:
                pattern = re.compile(
                    rf"(?<![a-zA-Z0-9_\u0900-\u097f\u0c80-\u0cff]){re.escape(match_text)}(?![a-zA-Z0-9_\u0900-\u097f\u0c80-\u0cff])",
                    re.IGNORECASE
                )
        
        def replace_fn(match):
            nonlocal placeholder_idx
            placeholder = f"__TERM_{placeholder_idx}__"
            mapping[placeholder] = eng_term
            placeholder_idx += 1
            return placeholder
            
        modified_text = pattern.sub(replace_fn, modified_text)

    return modified_text, mapping

def restore_protected_terms(text: str, mapping: dict) -> str:
    """
    Restores the masked placeholders '__TERM_X__' back to their original English canonical terms.
    """
    if not text or not mapping:
        return text

    restored_text = text
    for placeholder, original_term in mapping.items():
        # Extract digits from placeholder to build regex (resilient to NLLB translation spaces/case shifts)
        match_idx = re.search(r"\d+", placeholder)
        if match_idx:
            idx = match_idx.group(0)
            pattern = re.compile(rf"_*TERM_*{idx}_*(?![0-9])", re.IGNORECASE)
            restored_text = pattern.sub(original_term, restored_text)
            
    return restored_text
