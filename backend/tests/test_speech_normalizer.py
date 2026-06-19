"""
Tests — Speech Normalizer

Covers dictionary corrections, fuzzy matching, and context-sensitive homophone fixes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from speech.normalizer import SpeechNormalizer


@pytest.fixture
def normalizer():
    return SpeechNormalizer()


def test_dictionary_correction(normalizer):
    # Test Stage 1: Exact mapping replacements
    assert normalizer.normalize("explain wreckursion using pie torch") == "explain recursion using PyTorch"
    assert normalizer.normalize("let us use fast api") == "let us use FastAPI"
    assert normalizer.normalize("react huks are great") == "React hooks are great"
    assert normalizer.normalize("programming with java skript") == "programming with JavaScript"
    assert normalizer.normalize("enable cute a acceleration") == "enable CUDA acceleration"
    assert normalizer.normalize("parse that jason") == "parse that JSON"
    assert normalizer.normalize("deploy to versel") == "deploy to Vercel"


def test_fuzzy_matching(normalizer):
    # Test Stage 2: Fuzzy matching for programming terms
    assert normalizer.normalize("how to use recursun") == "how to use recursion"
    
    # Capitalization / title case preservation
    assert normalizer.normalize("Recursun is a concept") == "Recursion is a concept"
    
    # Common words and short words should not be fuzzy matched
    assert normalizer.normalize("the code with some logic") == "the code with some logic"


def test_context_correction(normalizer):
    # Test Stage 3: Context-aware homophone resolution
    assert normalizer.normalize("explain cash memory") == "explain cache memory"
    assert normalizer.normalize("we got a cash hit") == "we got a cache hit"
    assert normalizer.normalize("it is a cash miss") == "it is a cache miss"
    assert normalizer.normalize("what is cash coherence") == "what is cache coherence"
    
    assert normalizer.normalize("teach me see language") == "teach me C language"
    assert normalizer.normalize("tell me about sea language") == "tell me about C language"
    assert normalizer.normalize("i am programming in see") == "i am programming in C"
    assert normalizer.normalize("i am programming in sea") == "i am programming in C"
    
    assert normalizer.normalize("explain see sharp") == "explain C#"
    assert normalizer.normalize("explain sea sharp") == "explain C#"
    
    # dock or compose -> Docker Compose
    assert normalizer.normalize("let us run dock or compose") == "let us run Docker Compose"
