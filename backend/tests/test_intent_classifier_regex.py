import pytest
from agent.intent_classifier import IntentClassifier
from agent.models import Intent

def test_intent_classifier_quick_rules():
    # Instantiate with None LLM since we only test the fast-path regex (quick rules)
    classifier = IntentClassifier(None, enabled=False)

    # Test cases that should match Intent.GREETING
    greeting_queries = [
        "hi",
        "hello",
        "hey there",
        "good morning",
        "what is your name",
        "what's your name?",
        "who are you",
        "tell me about yourself",
        "how are you",
        "how are u",
        "how are your",
        "how are you doing",
        "how's it going",
        "how you doing"
    ]

    for query in greeting_queries:
        result = classifier._quick_classify(query)
        assert result is not None, f"Query '{query}' did not match any quick rule."
        assert result.intent == Intent.GREETING, f"Query '{query}' was classified as {result.intent} instead of GREETING."

    # Test cases that should NOT match GREETING but match others or fall through
    non_greeting_queries = {
        "thank you": Intent.THANKS,
        "say that again": Intent.REPEAT_LAST,
        "make it simpler": Intent.SIMPLIFY,
        "test me": Intent.QUIZ_REQUEST,
        "my code isn't working": Intent.PROJECT_HELP, # matches project
        "hiring process": Intent.CAREER_GUIDANCE,
        "what is page 5 of pdf": Intent.PDF_QUESTION,
        "fix my error": Intent.DEBUGGING,
        "write a class": Intent.CODE_HELP,
        "continue explaining": Intent.FOLLOW_UP,
    }

    for query, expected_intent in non_greeting_queries.items():
        result = classifier._quick_classify(query)
        if expected_intent is None:
            assert result is None, f"Query '{query}' matched a quick rule unexpectedly: {result.intent}"
        else:
            assert result is not None, f"Query '{query}' did not match expected quick rule for {expected_intent}"
            assert result.intent == expected_intent, f"Query '{query}' matched {result.intent} instead of {expected_intent}"
