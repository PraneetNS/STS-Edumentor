"""Regression coverage for native-script and Romanized Indic routing."""

from speech.language_router import LanguageRouter


def test_routes_native_kannada_to_kannada():
    language, _ = LanguageRouter.route("ಪುನರಾವರ್ತನೆ ಎಂದರೇನು?")
    assert language == "kannada"


def test_routes_native_hindi_to_hindi():
    language, _ = LanguageRouter.route("रिकर्शन क्या है और यह कैसे काम करता है?")
    assert language == "hindi"


def test_routes_native_marathi_to_marathi():
    language, _ = LanguageRouter.route("रिकर्शन काय आहे आणि ते कसे काम करते?")
    assert language == "marathi"


def test_routes_common_romanized_marathi_to_marathi():
    language, _ = LanguageRouter.route("mala recursion kase kaam karte te sanga")
    assert language == "marathi"


def test_normalizes_whisper_language_codes():
    assert LanguageRouter.normalize_language("MR") == "marathi"
    assert LanguageRouter.normalize_language("kn") == "kannada"
    assert LanguageRouter.normalize_language("unsupported") is None


def test_uses_the_highest_romanized_language_score():
    language, _ = LanguageRouter.route("hege mujhe recursion kaise kaam karta hai batao")
    assert language == "hindi"


def test_accepts_uppercase_profile_language_codes():
    language, _ = LanguageRouter.route("unrecognized technical phrase", lang_pref="MR")
    assert language == "marathi"


def test_detects_explicit_to_language_output_requests():
    assert LanguageRouter.detect_requested_output_language("translate this to Hindi") == "hindi"
    assert LanguageRouter.detect_requested_output_language("switch language to Marathi") == "marathi"


def test_detects_requested_kannada_output_with_a_stt_spelling_variant():
    assert LanguageRouter.detect_requested_output_language("explain recursion in Kanada") == "kannada"


def test_routes_common_romanized_kannada_to_kannada():
    language, _ = LanguageRouter.route("nanage recursion yavudu anta tilisi")
    assert language == "kannada"


def test_keeps_technical_english_on_the_english_route():
    language, metadata = LanguageRouter.route("How do I use an IDE to debug this code?")
    assert language == "english"
    assert metadata["routing_path"] == "english-default"
