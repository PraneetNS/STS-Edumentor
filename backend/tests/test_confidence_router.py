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
