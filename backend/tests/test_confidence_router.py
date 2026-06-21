import sys
import os
# Add the parent folder of tests to the path so we can import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from edmentor.confidence_router import StreamingDualParser

def test_basic_parse():
    parser = StreamingDualParser()
    events = parser.feed("<speak>Hello</speak>")
    assert len(events) == 1
    assert events[0]["type"] == "text"
    assert events[0]["content"] == "Hello"

def test_malformed_tag_does_not_leak():
    parser = StreamingDualParser()
    chunks = [
        "<speak>Here is the answer.</speak>",
        "<followup>Want to know more",  # deliberately unclosed
    ]
    speak_out = []
    for c in chunks:
        for e in parser.feed(c):
            if e["type"] == "text":
                speak_out.append(e["content"])
    final = parser.finalize()
    combined_speak = " ".join(speak_out)
    assert "<followup>" not in combined_speak
    assert "Want to know more" not in combined_speak
    print("PASS — malformed tag did not leak into speak stream")

def test_show_tag_attributes():
    parser = StreamingDualParser()
    events = parser.feed('<show type="code" lang="python">print("Hello")</show>')
    assert len(events) == 1
    assert events[0]["type"] == "show"
    assert events[0]["show_type"] == "code"
    assert events[0]["lang"] == "python"
    assert events[0]["content"] == 'print("Hello")'

def test_speak_tag_cleaning():
    parser = StreamingDualParser()
    # If the text has nested tags or stray angle brackets inside speak, they should be cleaned
    events = parser.feed("<speak>This is <b>bold</b> text & <stray> bracket.</speak>")
    assert len(events) == 1
    assert events[0]["type"] == "text"
    assert events[0]["content"] == "This is bold text &  bracket."

def test_unclosed_speak_tag():
    parser = StreamingDualParser()
    events = parser.feed("<speak>Incomplete text")
    assert len(events) == 0
    final_events = parser.finalize()
    assert len(final_events) == 0
    assert parser.buffer == ""

def test_empty_input():
    parser = StreamingDualParser()
    events = parser.feed("")
    assert len(events) == 0
    events = parser.feed(None)
    assert len(events) == 0
