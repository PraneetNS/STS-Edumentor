import pytest
from i18n.term_corrector import correct_technical_terms

def test_kannada_fuzzy_correction():
    # Exact transliterations
    assert correct_technical_terms("ರಿಕರ್ಷನ್ ಎಂದರೇನು", "kannada") == "recursion ಎಂದರೇನು"
    assert correct_technical_terms("ಲಿಂಕ್ಡ್ ಲಿಸ್ಟ್ ಬಳಸಿ", "kannada") == "linked list ಬಳಸಿ"
    
    # Slightly fuzzy / spelling error transliterations
    assert correct_technical_terms("ರಿಕರ್ಶನ್ ಎಂದರೇನು", "kannada") == "recursion ಎಂದರೇನು"
    assert correct_technical_terms("ಮಷಿನ್ ಲರ್ನಿಂಗ್ ಬಗ್ಗೆ ಹೇಳಿ", "kannada") == "machine learning ಬಗ್ಗೆ ಹೇಳಿ"

def test_hindi_fuzzy_correction():
    # Exact transliterations
    assert correct_technical_terms("रिकर्शन क्या है", "hindi") == "recursion क्या है"
    assert correct_technical_terms("लिंक लिस्ट का उपयोग करें", "hindi") == "linked list का उपयोग करें"
    
    # Slightly fuzzy
    assert correct_technical_terms("रीकर्सन के बारे में बताओ", "hindi") == "recursion के बारे में बताओ"
    assert correct_technical_terms("मशीन लर्नींग सीखो", "hindi") == "machine learning सीखो"

def test_english_no_change():
    # English terms should not be affected or modified when lang is English
    assert correct_technical_terms("What is recursion?", "english") == "What is recursion?"
