"""
Tests — Transcript Stabilizer
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from speech.stabilizer import TranscriptStabilizer


def test_stabilizer_empty():
    stabilizer = TranscriptStabilizer()
    assert stabilizer.stabilize("") == []


def test_stabilizer_flow():
    stabilizer = TranscriptStabilizer()
    
    # 1. First word
    res1 = stabilizer.stabilize("explain")
    assert len(res1) == 1
    assert res1[0]["word"] == "explain"
    assert res1[0]["status"] == "temporary"
    
    # 2. Second word
    res2 = stabilizer.stabilize("explain recursion")
    assert len(res2) == 2
    assert res2[0]["word"] == "explain"
    assert res2[0]["status"] == "confirmed"  # Confirmed because of len - 2 rule or prefix matching
    assert res2[1]["word"] == "recursion"
    assert res2[1]["status"] == "temporary"
    
    # 3. Third word
    res3 = stabilizer.stabilize("explain recursion in")
    assert len(res3) == 3
    assert res3[0]["word"] == "explain"
    assert res3[0]["status"] == "confirmed"
    assert res3[1]["word"] == "recursion"
    assert res3[1]["status"] == "confirmed"
    assert res3[2]["word"] == "in"
    assert res3[2]["status"] == "temporary"

    # 4. Word correction/jump (user corrects their speech or Whisper re-transcribes)
    res4 = stabilizer.stabilize("explain recursive function")
    assert len(res4) == 3
    assert res4[0]["word"] == "explain"
    assert res4[0]["status"] == "confirmed"  # prefix matches "explain"
    assert res4[1]["word"] == "recursive"
    assert res4[1]["status"] == "temporary"  # unstable because it changed from recursion
    assert res4[2]["word"] == "function"
    assert res4[2]["status"] == "temporary"
