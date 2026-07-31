"""
Unit tests for speech language router.
Tests all Whisper transcript variants from the feasibility report.
"""

import sys
import os

# Append backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from speech.language_router import LanguageRouter


def test_pure_hindi_latin():
    # Whisper base output
    text = "punaravritthi ek asiprakriya hai, jisme ek funkshan khud ko call karta hai."
    lang, meta = LanguageRouter.route(text)
    assert lang == "hindi"
    assert "Hinglish/Hindi" in meta["reason"] or "Defaulted" in meta["reason"]


def test_pure_hindi_devanagari():
    # Whisper small output
    text = "पुनराव्रित्ती एक अईसी प्रक्रिया है, जिस में एक फंक्शन कुद को call करता है."
    lang, meta = LanguageRouter.route(text)
    assert lang == "hindi"
    assert meta["scores"]["hindi"] > meta["scores"]["marathi"]


def test_pure_kannada_latin():
    # Whisper base output
    text = "Pwnarawar tanayu wundhu prakriye jagidhu Adar Ali Function tanna nhu tanne karyu tadeh."
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"
    assert "kannada" in meta["reason"].lower()


def test_pure_kannada_devanagari():
    # Whisper small output (transcribed Kannada words in Devanagari script)
    text = "पूनरावर तने यु उन्दू प्रक्रिये यागिदू अदरली फूंक्ष्यन तननू ताने करी उत्तदे"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"
    assert "Devanagari Kannada phonetic match" in meta["reason"]


def test_pure_kannada_unicode():
    text = "ಪುನರಾವರ್ತನೆಯು ಒಂದು ಪ್ರಕ್ರಿಯೆಯಾಗಿದ್ದು ಅದರಲ್ಲಿ ಫಂಕ್ಷನ್ ತನ್ನನ್ನು ತಾನೇ ಕರೆಯುತ್ತದೆ"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"
    assert "Unicode" in meta["reason"]


def test_pure_marathi_latin():
    # Whisper base output
    text = "Punaravruti hiye ka shi prakriya haye jaamade funkshanswata hla koal karte."
    lang, meta = LanguageRouter.route(text)
    assert lang == "marathi"
    assert "marathi" in meta["reason"].lower()


def test_pure_marathi_devanagari():
    # Whisper small output
    text = "पुनराव्रुत्ती ही एक वषी प्रक्रिया है, जामदे फुंक्षन स्वताला कौल करते।"
    lang, meta = LanguageRouter.route(text)
    assert lang == "marathi"
    assert meta["scores"]["marathi"] > meta["scores"]["hindi"]


def test_hinglish_latin():
    text = "Recursion ek process hai jisme function apne aap ko call karta hai"
    lang, meta = LanguageRouter.route(text)
    assert lang == "hindi"


def test_hinglish_devanagari():
    text = "रेकर्शिन एक प्रोसेस है, जिस्मे फंक्शिन अपने आप को कोल करता है"
    lang, meta = LanguageRouter.route(text)
    assert lang == "hindi"
    assert meta["scores"]["hindi"] > meta["scores"]["marathi"]


def test_kanglish_latin():
    # Whisper base output
    text = "Recursion calculation nalli function thanna thaanu call maaduvudu"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"


def test_kanglish_latin_small():
    # Whisper small output
    text = "Recursion Calculation Nulli Function Thanna Thanu Call Madhu Voodoo."
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"


def test_three_way_mixed_latin():
    text = "Recursion ek logic hai jahan code and function thanna thaanu call karta hai"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"


def test_three_way_mixed_whisper_translation_base():
    # Whisper base translated Hinglish/Kanglish straight to English
    text = "Recursion is a logic where code and function thanna thanu calls"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"
    assert "kannada" in meta["reason"].lower()


def test_three_way_mixed_whisper_translation_small():
    # Whisper small translated Hinglish/Kanglish straight to English
    text = "Recursion is a logic where code in function thanna thanu calls"
    lang, meta = LanguageRouter.route(text)
    assert lang == "kannada"
    assert "kannada" in meta["reason"].lower()


def test_english_technical_terms_routing():
    # Technical English queries containing words like 'ide', 'code', 'tar' should route to English
    text_1 = "what is an ide"
    lang_1, meta_1 = LanguageRouter.route(text_1)
    assert lang_1 == "english"

    text_2 = "how to write recursion code in python"
    lang_2, meta_2 = LanguageRouter.route(text_2)
    assert lang_2 == "english"

    text_3 = "unpack tar archive using tar command"
    lang_3, meta_3 = LanguageRouter.route(text_3)
    assert lang_3 == "english"
