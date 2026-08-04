"""Short, localised messages used by the multilingual voice flow."""


def language_switch_confirmation(language: str) -> str:
    """Acknowledge a language choice in that language when possible."""
    confirmations = {
        "hindi": "ठीक है, अब से मैं हिंदी में जवाब दूँगा।",
        "marathi": "ठीक आहे, आता मी मराठीत उत्तर देईन।",
        "kannada": "ಸರಿ, ಇನ್ನು ಮುಂದೆ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸುತ್ತೇನೆ.",
        "auto": "Okay, I will automatically match your language from now on.",
    }
    return confirmations.get(language, "Okay, I will reply in English from now on.")
