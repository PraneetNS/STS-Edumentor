"""
EduMentor Voice — Language Router Layer

Classifies post-STT transcripts into 'hindi' (native Hinglish/Hindi path),
'marathi' (translation path), or 'kannada' (translation path) using Unicode
block analysis, Devanagari lexical pattern matching, and Latin keyword fallbacks.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional

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
    "केल्यास", "तेव्हा", "म्हणते", "द्या", "पुनराव्रुत्ती", "स्वताला", "जामदे",
    "कसे", "कायानी", "मला", "करून", "तुम्हाला", "येथे"
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
    "maduvudu", "endarenu", "andarenu", "reno", "enu", "kodi", "ide", "idare", "iddare", "illa",
    "mathu", "mattu", "mathe", "ondu", "wundu", "prakriye", "tanna", "thanu",
    "thanna", "taane", "thane", "karyu", "kare", "karyutade", "karyutadeh",
    "adaralli", "adrali", "avathu", "yavathu", "hoge", "hege", "yaake", "odu",
    "karnaka", "kannada", "kodthini", "bidi", "nodona", "madthini", "nulli"
}

# Romanized Marathi keywords (Latin script)
LATIN_MARATHI_KEYWORDS = {
    "ahe", "aahe", "ahet", "aahet", "mhanje", "mahanj", "mhanajae", "mahansh", "rekharshan", "karto", "karate", "karatat",
    "nahi", "naahi", "ani", "aani", "kay", "kaay", "madhye", "madhe", "pan", "tar",
    "hote", "jhale", "zale", "sope", "peksha", "changle", "changli", "swatahlah",
    "swatahla", "swata", "goshta", "karava", "karaycha", "marathi", "sangto",
    "baghu", "karu", "kartoy", "kartyat", "bolto", "punaravruti", "mala",
    "kase", "kaam", "sanga", "sangaa", "shikva", "samjha", "tumhi"
}

# Romanized Hindi/Hinglish keywords (Latin script)
LATIN_HINDI_KEYWORDS = {
    "kya", "hai", "hain", "aur", "mein", "se", "ko", "ka", "ki", "ke", "tha", "thi", "the",
    "ho", "rha", "raha", "rahi", "rahe", "kar", "karna", "karke", "karta", "karte", "krta",
    "krte", "bhi", "toh", "ek", "haan", "nhi", "nahi", "kuch", "apne", "aap", "karne",
    "karty", "krke", "kaise", "kese", "hoga", "hogi", "hogya", "gaya", "gayi", "gaye",
    "karo", "karoo", "batao", "samjhao", "sikhaya", "samajh", "aaya", "aayi",
    "mereko", "tereko", "mujhe", "mere", "mujko", "bata"
}

# Common English function words to confirm standard English queries
ENGLISH_FUNCTION_WORDS = {
    "the", "of", "and", "a", "to", "in", "is", "you", "that", "it", "he", "was", "for", "on",
    "are", "as", "with", "his", "they", "i", "at", "be", "this", "have", "from", "or", "one",
    "had", "by", "word", "but", "not", "what", "all", "were", "we", "when", "your", "can",
    "said", "there", "use", "an", "each", "which", "she", "do", "how", "their", "if", "will",
    "up", "other", "about", "out", "many", "then", "them", "these", "so", "some", "her",
    "would", "make", "like", "him", "into", "time", "has", "look", "two", "more", "write",
    "go", "see", "number", "no", "way", "could", "people", "my", "than", "first", "water",
    "been", "call", "who", "oil", "its", "now", "find", "long", "down", "day", "did", "get",
    "come", "made", "may", "part", "explain", "what", "how", "why", "describe", "recursion",
    "programming", "computer", "science", "engineering", "ide", "code", "coding", "codes",
    "program", "programs", "tar", "file", "files", "data", "variable", "variables", "function",
    "functions", "class", "classes", "object", "objects", "loop", "loops", "run", "compile",
    "error", "bugs", "null", "void", "string", "integer", "boolean", "array", "list"
}

LANGUAGE_ALIASES = {
    "kn": "kannada", "kannada": "kannada",
    "mr": "marathi", "marathi": "marathi",
    "hi": "hindi", "hindi": "hindi",
    "en": "english", "english": "english",
}


class LanguageRouter:
    """
    Routes a post-STT text transcript to 'hindi', 'marathi', 'kannada', or 'english'
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

    @staticmethod
    def normalize_language(language: Optional[str]) -> Optional[str]:
        """Return a supported canonical language name, or ``None``."""
        if not language:
            return None
        return LANGUAGE_ALIASES.get(language.strip().lower())

    @classmethod
    def route(
        cls,
        text: str,
        whisper_detected_lang: Optional[str] = None,
        lang_pref: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Classifies transcript and returns (route_lang, metadata_details).
        Possible return languages: 'hindi', 'marathi', 'kannada', 'english'.
        """
        if not text or not text.strip():
            return "english", {
                "reason": "Empty text, defaulted to English",
                "scores": {},
                "routing_path": "english-default"
            }

        # Clean words for lookup
        tokens = [w.strip(".,!?\"'()[]।॥;-").lower() for w in text.split()]
        raw_words = [w.strip(".,!?\"'()[]।॥;-") for w in text.split()]

        # 1. Kannada Unicode Script Check (Unconditional route)
        if cls.contains_kannada_script(text):
            return "kannada", {
                "reason": "Kannada Unicode characters detected in transcript",
                "scores": {"kannada_script": True},
                "routing_path": "keyword-match"
            }

        # 2. Devanagari Unicode Script Check
        if cls.contains_devanagari_script(text):
            # Check for phonetic Kannada written in Devanagari
            kannada_deva_matches = [w for w in raw_words if w.strip(".,!?") in DEVANAGARI_KANNADA_KEYWORDS]
            if kannada_deva_matches:
                return "kannada", {
                    "reason": f"Devanagari Kannada phonetic match found: {kannada_deva_matches}",
                    "scores": {"kannada_deva_matches": len(kannada_deva_matches)},
                    "routing_path": "keyword-match"
                }

            # Check for Marathi-specific letter 'ळ' (Devanagari Letter LLA)
            if 'ळ' in text:
                return "marathi", {
                    "reason": "Marathi-specific Devanagari character 'ळ' detected",
                    "scores": {"has_lla_char": True},
                    "routing_path": "keyword-match"
                }

            # Disambiguate Marathi vs Hindi Devanagari vocabulary
            marathi_score = sum(1 for w in tokens if w in DEVANAGARI_MARATHI_KEYWORDS)
            hindi_score = sum(1 for w in tokens if w in DEVANAGARI_HINDI_KEYWORDS)

            if marathi_score > hindi_score:
                return "marathi", {
                    "reason": f"Devanagari Marathi lexicon score ({marathi_score}) > Hindi score ({hindi_score})",
                    "scores": {"marathi": marathi_score, "hindi": hindi_score},
                    "routing_path": "keyword-match"
                }
            elif hindi_score > marathi_score:
                return "hindi", {
                    "reason": f"Devanagari Hindi lexicon score ({hindi_score}) > Marathi score ({marathi_score})",
                    "scores": {"marathi": marathi_score, "hindi": hindi_score},
                    "routing_path": "keyword-match"
                }
            else:
                # Lexicon scores are tied or both 0. Fall back to user preference or Whisper's language detection if valid.
                resolved_lp = cls.normalize_language(lang_pref)
                if resolved_lp in ("kannada", "marathi", "hindi"):
                    return resolved_lp, {
                        "reason": f"Devanagari script detected but lexicon scores tied. User preference {lang_pref!r} used as fallback.",
                        "scores": {"marathi": marathi_score, "hindi": hindi_score},
                        "routing_path": "preference-bias-fallback"
                    }
                resolved_whisper_lang = cls.normalize_language(whisper_detected_lang)
                if resolved_whisper_lang:
                    if resolved_whisper_lang == "kannada":
                        return "kannada", {
                            "reason": f"Devanagari script detected but lexicon scores tied. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                            "scores": {"marathi": marathi_score, "hindi": hindi_score},
                            "routing_path": "whisper-probability-fallback"
                        }
                    elif resolved_whisper_lang == "marathi":
                        return "marathi", {
                            "reason": f"Devanagari script detected but lexicon scores tied. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                            "scores": {"marathi": marathi_score, "hindi": hindi_score},
                            "routing_path": "whisper-probability-fallback"
                        }
                    elif resolved_whisper_lang == "hindi":
                        return "hindi", {
                            "reason": f"Devanagari script detected but lexicon scores tied. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                            "scores": {"marathi": marathi_score, "hindi": hindi_score},
                            "routing_path": "whisper-probability-fallback"
                        }

                # Fallback to Hindi default for Devanagari script
                return "hindi", {
                    "reason": f"Devanagari Hindi lexicon fallback (tied score {hindi_score})",
                    "scores": {"marathi": marathi_score, "hindi": hindi_score},
                    "routing_path": "keyword-match"
                }

        # 3. Latin / Romanized Script Check (Keyword Matching)
        # Filter out common English function words to prevent false Hinglish matches (such as 'the' matching Hinglish 'थे')
        indic_tokens = [w for w in tokens if w not in ENGLISH_FUNCTION_WORDS]
        kannada_latin_matches = [w for w in indic_tokens if w in LATIN_KANNADA_KEYWORDS]
        marathi_latin_matches = [w for w in indic_tokens if w in LATIN_MARATHI_KEYWORDS]
        hindi_latin_matches = [w for w in indic_tokens if w in LATIN_HINDI_KEYWORDS]

        kannada_score = len(kannada_latin_matches)
        marathi_score = len(marathi_latin_matches)
        hindi_score = len(hindi_latin_matches)

        if kannada_score > 0 and kannada_score > marathi_score and kannada_score > hindi_score:
            return "kannada", {
                "reason": f"Latin Kannada keywords found: {kannada_latin_matches}",
                "scores": {"kannada": kannada_score, "marathi": marathi_score, "hindi": hindi_score},
                "routing_path": "keyword-match"
            }
        elif marathi_score > 0 and marathi_score > kannada_score and marathi_score > hindi_score:
            return "marathi", {
                "reason": f"Latin Marathi keywords found: {marathi_latin_matches}",
                "scores": {"kannada": kannada_score, "marathi": marathi_score, "hindi": hindi_score},
                "routing_path": "keyword-match"
            }

        # If they are 0 or tied, check for Hindi/Hinglish keywords (or mixed Indic signals)
        if hindi_score > 0 or kannada_score > 0 or marathi_score > 0:
            return "hindi", {
                "reason": f"Latin Hinglish/Hindi keywords or mixed signals found: hindi_matches={hindi_latin_matches}",
                "scores": {"kannada": kannada_score, "marathi": marathi_score, "hindi": hindi_score},
                "routing_path": "keyword-match"
            }

        # 4. Fallback to user preference or Whisper's detected language when scores are all 0
        resolved_lp = cls.normalize_language(lang_pref)
        if resolved_lp:
            return resolved_lp, {
                "reason": f"No keywords matched. User preference {lang_pref!r} used fallback.",
                "scores": {"kannada": 0, "marathi": 0, "hindi": 0},
                "routing_path": "preference-bias-fallback"
            }
        resolved_whisper_lang = cls.normalize_language(whisper_detected_lang)
        if resolved_whisper_lang:
            if resolved_whisper_lang == "kannada":
                return "kannada", {
                    "reason": f"No keywords matched. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                    "scores": {"kannada": 0, "marathi": 0, "hindi": 0},
                    "routing_path": "whisper-probability-fallback"
                }
            elif resolved_whisper_lang == "marathi":
                return "marathi", {
                    "reason": f"No keywords matched. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                    "scores": {"kannada": 0, "marathi": 0, "hindi": 0},
                    "routing_path": "whisper-probability-fallback"
                }
            elif resolved_whisper_lang == "hindi":
                return "hindi", {
                    "reason": f"No keywords matched. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                    "scores": {"kannada": 0, "marathi": 0, "hindi": 0},
                    "routing_path": "whisper-probability-fallback"
                }
            elif resolved_whisper_lang == "english":
                return "english", {
                    "reason": f"No keywords matched. Whisper detected language {whisper_detected_lang!r} used as fallback.",
                    "scores": {"kannada": 0, "marathi": 0, "hindi": 0},
                    "routing_path": "whisper-probability-fallback"
                }

        # 5. Default to English when no Indic keywords are matched and Whisper has no signal
        return "english", {
            "reason": "Only Latin script detected with no Indic keywords. Classified as English.",
            "scores": {"kannada": kannada_score, "marathi": marathi_score, "hindi": hindi_score},
            "routing_path": "english-default"
        }

    @staticmethod
    def detect_requested_output_language(text: str) -> Optional[str]:
        """
        Scans the transcript for explicit output-language requests expressed in English.
        Handles common misspellings (e.g. 'Kanada', 'Marati', 'hindhi').

        Returns one of: 'hindi' | 'marathi' | 'kannada' | None.
        Returns None if no explicit language request is found.
        """
        import re
        if not text:
            return None

        t = text.lower().strip()

        # ── Step 1: Normalise common misspellings to canonical names ─────────
        # Kannada aliases: Canada, Kanada, Kannad, Cannada, Karnada, Kanaada, Kannadiga
        t = re.sub(r"\bcanada\b",    "kannada", t)
        t = re.sub(r"\bkarna?da\b",  "kannada", t)
        t = re.sub(r"\bkanna?d(?:a|e)?\b", "kannada", t)
        t = re.sub(r"\bcannada\b",   "kannada", t)
        t = re.sub(r"\bkana+da\b",   "kannada", t)
        t = re.sub(r"\bkannadiga\b", "kannada", t)


        # Marathi aliases: Marati, Marathii, Maratthi, Marathi
        t = re.sub(r"\bmara?t+h?i\b", "marathi", t)
        t = re.sub(r"\bmaraathi\b",   "marathi", t)

        # Hindi aliases: Hindhi, Hinde, Hinde, Hindie, Hindy
        t = re.sub(r"\bhin(?:d(?:h?i|y|ie)|de)\b", "hindi", t)

        # ── Step 2: Broad pattern — any verb/prep + language name ─────────────
        # Matches: "in hindi", "explain in kannada", "tell me in marathi",
        # "answer in hindi", "respond in kannada", "translate to marathi",
        # "hindi mein", "kannada lo", "kannada medium", etc.
        LANG_NAMES = r"(?:hindi|marathi|kannada)"

        BROAD_PATTERN = re.compile(
            r"""
            (?:
                # "in/into/to <lang>" with optional verb prefix
                \b(?:explain|answer|respond|reply|speak|say|write|tell\s+(?:me\s+)?|give(?:\s+me)?|describe|translate(?:\s+(?:it\s+)?(?:to|into))?|use|switch\s+to|change\s+(?:language\s+)?to)?\s*
                \bin\s+""" + LANG_NAMES + r"""\b
            |
                # Translation and switching requests commonly use "to <lang>".
                \b(?:translate(?:\s+(?:it|this|that))?|switch(?:\s+language)?|change\s+(?:language\s+)?)\s+(?:to|into)\s+""" + LANG_NAMES + r"""\b
            |
                # "<lang> mein/medium/lo" (Indic-English hybrid)
                \b""" + LANG_NAMES + r"""\s+(?:mein|medium|lo|me)\b
            |
                # Pure bare language word at the end: "explain ... kannada"
                \b(?:explain|answer|respond|tell|describe)\b.{0,80}?\b""" + LANG_NAMES + r"""\s*$
            )
            """,
            re.VERBOSE | re.IGNORECASE,
        )

        match = BROAD_PATTERN.search(t)
        if match:
            matched_text = match.group(0).lower()
            if "kannada" in matched_text:
                return "kannada"
            if "marathi" in matched_text:
                return "marathi"
            if "hindi" in matched_text:
                return "hindi"

        # ── Step 3: Fallback — bare language name anywhere in short utterances ─
        # For very short queries like "in Hindi" or "Kannada lo boliye"
        words = t.split()
        if len(words) <= 8:
            for w in words:
                if w == "kannada":
                    return "kannada"
                if w == "marathi":
                    return "marathi"
                if w == "hindi":
                    return "hindi"

        return None

