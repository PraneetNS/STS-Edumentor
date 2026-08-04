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
