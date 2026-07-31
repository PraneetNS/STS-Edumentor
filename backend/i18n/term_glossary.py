import json
import os
import re

# Load vocabulary dynamically from the central engineering_vocab.json
VOCAB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "speech", "data", "engineering_vocab.json"
)

def load_glossary_terms():
    try:
        with open(VOCAB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        terms = set()
        for discipline in data.values():
            for term in discipline.keys():
                # Clean up whitespace
                t = term.strip()
                if t:
                    terms.add(t)
        # Sort by length descending to match longer phrases first (e.g. "linked list" before "list")
        return sorted(list(terms), key=len, reverse=True)
    except Exception:
        # Fallback to high-frequency standard terms if load fails
        return ["recursion", "encapsulation", "inheritance", "polymorphism", "abstraction", "linked list", "binary search", "pointer", "array", "function"]

GLOSSARY_TERMS = load_glossary_terms()

# Transliteration mapping for high-frequency categories to sound natural in TTS/reading
TRANSLITERATIONS = {
    "recursion": {
        "kannada": "ರಿಕರ್ಷನ್",
        "marathi": "रिकर्शन",
        "hindi": "रिकर्शन"
    },
    "encapsulation": {
        "kannada": "ಎನ್ಕ್ಯಾಪ್ಸುಲೇಷನ್",
        "marathi": "एनकॅप्सुलेशन",
        "hindi": "एन्कैप्सुलेशन"
    },
    "inheritance": {
        "kannada": "ಇನ್ಹೆರಿಟೆನ್ಸ್",
        "marathi": "इन्हेरीटन्स",
        "hindi": "इन्हेरिटेंस"
    },
    "polymorphism": {
        "kannada": "ಪಾಲಿಮಾರ್ಫಿಸಮ್",
        "marathi": "पॉलीमॉर्फिझम",
        "hindi": "पॉलीमॉर्फिज्म"
    },
    "abstraction": {
        "kannada": "ಅಬ್ಸ್ಟ್ರ್ಯಾಕ್ಷನ್",
        "marathi": "अब्स्ट्रॅक्शन",
        "hindi": "एब्स्ट्रक्शन"
    },
    "linked list": {
        "kannada": "ಲಿಂಕ್ಡ್ ಲಿಸ್ಟ್",
        "marathi": "लिंक्ड लिस्ट",
        "hindi": "लिंक्ड लिस्ट"
    },
    "binary search": {
        "kannada": "ಬೈನರಿ ಸರ್ಚ್",
        "marathi": "बायनरी सर्च",
        "hindi": "बायनरी सर्च"
    },
    "pointer": {
        "kannada": "ಪಾಯಿಂಟರ್",
        "marathi": "पॉइंटर",
        "hindi": "पॉइंटर"
    },
    "array": {
        "kannada": "ಅರೇ",
        "marathi": "अरे",
        "hindi": "ऐरे"
    },
    "function": {
        "kannada": "ಫಂಕ್ಷನ್",
        "marathi": "फंक्शन",
        "hindi": "फंक्शन"
    },
    "ai": {
        "kannada": "ಎಐ",
        "marathi": "एआय",
        "hindi": "एआई"
    },
    "computer": {
        "kannada": "ಕಂಪ್ಯೂಟರ್",
        "marathi": "कॉम्प्युटर",
        "hindi": "कंप्यूटर"
    },
    "engineering": {
        "kannada": "ಎಂಜಿನಿಯರಿಂಗ್",
        "marathi": "इंजिनीअरिंग",
        "hindi": "इंजीनियरिंग"
    },
    "technology": {
        "kannada": "ಟೆಕ್ನಾಲಜಿ",
        "marathi": "ಟೆಕ್ನಾಲಜಿ",
        "hindi": "टेक्नोलॉजी"
    },
    "science": {
        "kannada": "ಸೈನ್ಸ್",
        "marathi": "सायन्स",
        "hindi": "साइंस"
    },
    "algorithm": {
        "kannada": "ಅಲ್ಗಾರಿದಮ್",
        "marathi": "अल्गोरिदम",
        "hindi": "एल्गोरिदम"
    },
    "algorithms": {
        "kannada": "ಅಲ್ಗಾರಿದಮ್ಗಳು",
        "marathi": "अल्गोरिदम",
        "hindi": "एल्गोरिदम"
    },
    "compiler": {
        "kannada": "ಕಂಪೈಲರ್",
        "marathi": "कंपायलिर",
        "hindi": "कंपाइलर"
    },
    "compilers": {
        "kannada": "ಕಂಪೈಲರ್ಗಳು",
        "marathi": "कंपायलर्स",
        "hindi": "कंपाइलर्स"
    },
    "thread": {
        "kannada": "ಥ್ರೆಡ್",
        "marathi": "थ्रेड",
        "hindi": "थ्रेड"
    },
    "threads": {
        "kannada": "ಥ್ರೆಡ್ಗಳು",
        "marathi": "थ्रेड्स",
        "hindi": "थ्रेड्स"
    },
    "process": {
        "kannada": "ಪ್ರೊಸೆಸ್",
        "marathi": "प्रोसेस",
        "hindi": "प्रोसेस"
    },
    "processes": {
        "kannada": "ಪ್ರೊಸೆಸ್ಗಳು",
        "marathi": "प्रोसेसेस",
        "hindi": "प्रोसेसेस"
    },
    "database": {
        "kannada": "ಡೇಟಾಬೇಸ್",
        "marathi": "डेटाबेस",
        "hindi": "डेटाबेस"
    },
    "databases": {
        "kannada": "ಡೇಟಾಬೇಸ್ಗಳು",
        "marathi": "डेटाबेस",
        "hindi": "डेटाबेस"
    },
    "cache": {
        "kannada": "ಕ್ಯಾಶ್",
        "marathi": "कॅश",
        "hindi": "कैश"
    },
    "caches": {
        "kannada": "ಕ್ಯಾಶ್ಗಳು",
        "marathi": "कॅश",
        "hindi": "कैश"
    },
    "variable": {
        "kannada": "ವೇರಿಯಬಲ್",
        "marathi": "व्हेरिएबल",
        "hindi": "वेरिएबल"
    },
    "variables": {
        "kannada": "ವೇರಿಯಬಲ್ಗಳು",
        "marathi": "व्हेरिएबल्स",
        "hindi": "वेरिएबल्स"
    },
    "loop": {
        "kannada": "ಲೂಪ್",
        "marathi": "लूप",
        "hindi": "लूप"
    },
    "loops": {
        "kannada": "ಲೂಪ್ಗಳು",
        "marathi": "लूप्स",
        "hindi": "लूप्स"
    },
    "code": {
        "kannada": "ಕೋಡ್",
        "marathi": "कोड",
        "hindi": "कोड"
    },
    "codes": {
        "kannada": "ಕೋಡ್ಗಳು",
        "marathi": "कोड्स",
        "hindi": "कोड्स"
    },
    "coding": {
        "kannada": "ಕೋಡಿಂಗ್",
        "marathi": "कोडिंग",
        "hindi": "कोडिंग"
    },
    "program": {
        "kannada": "ಪ್ರೋಗ್ರಾಂ",
        "marathi": "प्रोग्राम",
        "hindi": "प्रोग्राम"
    },
    "programs": {
        "kannada": "ಪ್ರೋಗ್ರಾಂಗಳು",
        "marathi": "प्रोग्राम्स",
        "hindi": "प्रोग्राम्स"
    },
    "programming": {
        "kannada": "ಪ್ರೋಗ್ರಾಮಿಂಗ್",
        "marathi": "प्रोग्रामिंग",
        "hindi": "प्रोग्रामिंग"
    }
}

def normalize_lang(lang: str) -> str:
    if not lang:
        return "english"
    lang_lower = lang.lower()
    if "kan" in lang_lower:
        return "kannada"
    if "mar" in lang_lower:
        return "marathi"
    if "hin" in lang_lower or "ind" in lang_lower:
        return "hindi"
    return lang_lower

def protect_terms(text: str) -> tuple[str, dict]:
    """
    Scans the text for glossary matches (case-insensitive, word-boundary aware)
    and replaces each with a unique placeholder token (e.g. __TERM_0__, __TERM_1__),
    returning the modified text and a mapping of placeholder -> original term.
    """
    if not text:
        return "", {}
    
    mapping = {}
    modified_text = text
    placeholder_idx = 0
    
    for term in GLOSSARY_TERMS:
        if not term.strip():
            continue
        # Use regex to find case-insensitive whole word matches
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        
        def replace_fn(match_obj):
            nonlocal placeholder_idx
            placeholder = f"__TERM_{placeholder_idx}__"
            val = match_obj.group(0)
            mapping[placeholder] = val
            placeholder_idx += 1
            return placeholder
            
        modified_text = pattern.sub(replace_fn, modified_text)
        
    return modified_text, mapping

def restore_terms(text: str, mapping: dict, mode: str = "english", target_language: str = "english") -> str:
    """
    Replaces each placeholder back.
    In 'english' mode, reinsert the original English term unchanged.
    In 'native' mode, look up a transliteration for that term+language pair.
    """
    if not text or not mapping:
        return text
        
    normalized_lang = normalize_lang(target_language)
    restored_text = text
    
    for placeholder, orig_term in mapping.items():
        if mode == "native" and normalized_lang in ("hindi", "kannada", "marathi"):
            key = orig_term.lower().strip()
            trans_val = TRANSLITERATIONS.get(key, {}).get(normalized_lang)
            if trans_val:
                restored_text = restored_text.replace(placeholder, trans_val)
                continue
        # Default to English (original term)
        restored_text = restored_text.replace(placeholder, orig_term)
        
    return restored_text
