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

def test_multiple_tags_in_single_chunk():
    parser = StreamingDualParser()
    events = parser.feed("<speak>Speak 1</speak><show type=\"table\">Show 1</show><followup>Followup 1</followup>")
    assert len(events) == 3
    assert events[0]["type"] == "text"
    assert events[0]["content"] == "Speak 1"
    assert events[1]["type"] == "show"
    assert events[1]["content"] == "Show 1"
    assert events[1]["show_type"] == "table"
    assert events[2]["type"] == "followup"
    assert events[2]["content"] == "Followup 1"

def test_tag_nesting_mitigation():
    parser = StreamingDualParser()
    events = parser.feed("<speak>First <speak>Second</speak> Third</speak>")
    assert len(events) == 1
    assert events[0]["type"] == "text"
    # The first complete pair is <speak>First <speak>Second</speak>
    assert events[0]["content"] == "First Second"

def test_show_tag_single_attribute():
    parser = StreamingDualParser()
    events = parser.feed('<show type="roadmap">Roadmap content</show>')
    assert len(events) == 1
    assert events[0]["type"] == "show"
    assert events[0]["show_type"] == "roadmap"
    assert events[0]["lang"] == ""
    assert events[0]["content"] == "Roadmap content"

def test_show_tag_no_attributes():
    parser = StreamingDualParser()
    events = parser.feed("<show>Generic show content</show>")
    assert len(events) == 1
    assert events[0]["type"] == "show"
    assert events[0]["show_type"] == ""
    assert events[0]["lang"] == ""
    assert events[0]["content"] == "Generic show content"

def test_followup_tag_cleaning():
    parser = StreamingDualParser()
    events = parser.feed("<followup>Should we try <another> tag?</followup>")
    assert len(events) == 1
    assert events[0]["type"] == "followup"
    assert events[0]["content"] == "Should we try  tag?"

def test_to_sse():
    from edmentor.confidence_router import to_sse
    
    e_text = {"type": "text", "content": "Hello"}
    assert to_sse(e_text) == "event: text\ndata: Hello\n\n"
    
    e_show = {"type": "show", "show_type": "code", "lang": "python", "content": "print()"}
    assert "event: show\ndata: " in to_sse(e_show)
    assert 'type": "code"' in to_sse(e_show)
    
    e_followup = {"type": "followup", "content": "More?"}
    assert to_sse(e_followup) == "event: followup\ndata: More?\n\n"


def test_show_tag_full_attributes():
    parser = StreamingDualParser()
    events = parser.feed('<show type="checklist" lang="markdown" title="RAG Advantages">Item 1</show>')
    assert len(events) == 1
    assert events[0]["type"] == "show"
    assert events[0]["show_type"] == "checklist"
    assert events[0]["lang"] == "markdown"
    assert events[0]["title"] == "RAG Advantages"
    assert events[0]["content"] == "Item 1"

