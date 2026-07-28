"""
EduMentor Voice — Language Router Layer

Classifies post-STT transcripts into 'hindi' (native Hinglish/Hindi path),
'marathi' (translation path), or 'kannada' (translation path) using Unicode
block analysis, Devanagari lexical pattern matching, and Latin keyword fallbacks.
"""

import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("edumentor.speech.language_router")

# --- Curated Lexical Dictionaries ---

# Kannada words phonetically transcribed in Devanagari by Whisper
DEVANAGARI_KANNADA_KEYWORDS = {
    "उन्दू", "ओंदु", "वंदु", "प्रक्रिये", "यागिदू", "अदरली", "अदरल्ली",
    "तननू", "ताने", "उत्तदे", "उदाहरणे", "एंदरे", "कोडी", "कोडि",
    "माडु", "माडो", "हेळु", "हेळू", "हेलु", "नल्ली", "नली", "तने"
}

# Unique Marathi keywords/suffixes in Devanagari
DEVANAGARI_MARATHI_KEYWORDS = {
    "आहे", "नाही", "आणि", "काय", "करतात", "केले", "आहेत", "म्हणजे", "मध्ये",
    "पण", "तर", "होते", "झाले", "कडून", "साठी", "पेक्षा", "येतो", "झाली",
    "केली", "केला", "पुनरावृत्ती", "अशी", "ज्यामध्ये", "स्वतःला", "म्हणून",
    "केल्यास", "तेव्हा", "म्हणते", "द्या", "पुनराव्रुत्ती", "स्वताला", "जामदे"
}

# Unique Hindi keywords in Devanagari
DEVANAGARI_HINDI_KEYWORDS = {
    "है", "हैं", "होता", "होती", "का", "की", "के", "को", "में", "से", "और",
    "क्या", "नहीं", "करता", "करते", "था", "थे", "थी", "लिए", "पर",
    "काफी", "होते", "सकता", "सकते", "सकती", "किया", "दिए", "दिया", "खुद",
    "ऐसी", "जिसमें", "सकते", "सकती", "हैं", "कीजिए"
}

# Romanized Kannada keywords (Latin script)
LATIN_KANNADA_KEYWORDS = {
    "nalli", "aagide", "helthini", "heluthini", "helutene", "maaduvudu", "maadodu",
    "maduvudu", "endarenu", "andarenu", "kodi", "ide", "idare", "iddare", "illa",
    "mathu", "mattu", "mathe", "ondu", "wundu", "prakriye", "tanna", "thanu",
    "thanna", "taane", "thane", "karyu", "kare", "karyutade", "karyutadeh",
    "adaralli", "adrali", "avathu", "yavathu", "hoge", "hege", "yaake", "odu",
    "karnaka", "kannada", "kodthini", "bidi", "nodona", "madthini", "nulli"
}

# Romanized Marathi keywords (Latin script)
LATIN_MARATHI_KEYWORDS = {
    "ahe", "aahe", "ahet", "aahet", "mhanje", "mhanajae", "karto", "karate", "karatat",
    "nahi", "naahi", "ani", "aani", "kay", "kaay", "madhye", "madhe", "pan", "tar",
    "hote", "jhale", "zale", "sope", "peksha", "changle", "changli", "swatahlah",
    "swatahla", "swata", "goshta", "karava", "karaycha", "marathi", "sangto",
    "baghu", "karu", "kartoy", "kartyat", "bolto", "punaravruti"
}


class LanguageRouter:
    """
    Routes a post-STT text transcript to 'hindi', 'marathi', or 'kannada'
    using Unicode script checks and lexical dictionaries.
    """

    @staticmethod
    def contains_kannada_script(text: str) -> bool:
        """True if text contains any character in the Kannada Unicode block."""
        return any('\u0c80' <= char <= '\u0cff' for char in text)

    @staticmethod
    def contains_devanagari_script(text: str) -> bool:
        """True if text contains any character in the Devanagari Unicode block."""
        return any('\u0900' <= char <= '\u097f' for char in text)

    @classmethod
    def route(cls, text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Classifies transcript and returns (route_lang, metadata_details).
        Possible return languages: 'hindi', 'marathi', 'kannada'.
        """
        if not text or not text.strip():
            return "hindi", {"reason": "Empty text, defaulted to Hindi", "scores": {}}

        # Clean words for lookup
        tokens = [w.strip(".,!?\"'()[]।;-") for w in text.lower().split()]
        raw_words = [w.strip(".,!?\"'()[]।;-") for w in text.split()]

        # 1. Kannada Unicode Script Check (Unconditional route)
        if cls.contains_kannada_script(text):
            return "kannada", {
                "reason": "Kannada Unicode characters detected in transcript",
                "scores": {"kannada_script": True}
            }

        # 2. Devanagari Unicode Script Check
        if cls.contains_devanagari_script(text):
            # Check for phonetic Kannada written in Devanagari
            kannada_deva_matches = [w for w in raw_words if w.strip(".,!?") in DEVANAGARI_KANNADA_KEYWORDS]
            if kannada_deva_matches:
                return "kannada", {
                    "reason": f"Devanagari Kannada phonetic match found: {kannada_deva_matches}",
                    "scores": {"kannada_deva_matches": len(kannada_deva_matches)}
                }

            # Check for Marathi-specific letter 'ळ' (Devanagari Letter LLA)
            if 'ळ' in text:
                return "marathi", {
                    "reason": "Marathi-specific Devanagari character 'ळ' detected",
                    "scores": {"has_lla_char": True}
                }

            # Disambiguate Marathi vs Hindi Devanagari vocabulary
            marathi_score = sum(1 for w in tokens if w in DEVANAGARI_MARATHI_KEYWORDS)
            hindi_score = sum(1 for w in tokens if w in DEVANAGARI_HINDI_KEYWORDS)

            if marathi_score > hindi_score:
                return "marathi", {
                    "reason": f"Devanagari Marathi lexicon score ({marathi_score}) > Hindi score ({hindi_score})",
                    "scores": {"marathi": marathi_score, "hindi": hindi_score}
                }
            else:
                return "hindi", {
                    "reason": f"Devanagari Hindi lexicon score ({hindi_score}) >= Marathi score ({marathi_score})",
                    "scores": {"marathi": marathi_score, "hindi": hindi_score}
                }

        # 3. Latin / Romanized Script Check (Keyword Matching)
        kannada_latin_matches = [w for w in tokens if w in LATIN_KANNADA_KEYWORDS]
        marathi_latin_matches = [w for w in tokens if w in LATIN_MARATHI_KEYWORDS]

        kannada_score = len(kannada_latin_matches)
        marathi_score = len(marathi_latin_matches)

        if kannada_score > 0 and kannada_score > marathi_score:
            return "kannada", {
                "reason": f"Latin Kannada keywords found: {kannada_latin_matches}",
                "scores": {"kannada": kannada_score, "marathi": marathi_score}
            }
        elif marathi_score > 0 and marathi_score > kannada_score:
            return "marathi", {
                "reason": f"Latin Marathi keywords found: {marathi_latin_matches}",
                "scores": {"kannada": kannada_score, "marathi": marathi_score}
            }

        # Fallback to Hindi/Hinglish
        return "hindi", {
            "reason": "Only Latin script detected with no strong Kannada/Marathi keywords. Defaulted to Hinglish/Hindi.",
            "scores": {"kannada": kannada_score, "marathi": marathi_score}
        }
