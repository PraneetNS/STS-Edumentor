import sys
import os
import pytest
import time
import asyncio
from unittest import mock

# Add the parent folder of tests to the path so we can import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from speech.domain_corrector import DomainCorrector, COMMON_WORDS_STOPLIST


@pytest.fixture
def corrector():
    return DomainCorrector()


def test_exact_lookup(corrector):
    corrected, changes = corrector.correct_sentence("my code uses a chace memory", "cse")
    assert "cache" in corrected.lower()
    assert len(changes) > 0
    assert changes[0] == ("chace", "cache")


def test_longest_phrase_first(corrector):
    corrected, changes = corrector.correct_sentence("I encountered a segment haitian fault", "cse")
    assert "segmentation fault" in corrected.lower()
    assert len(changes) == 1
    assert changes[0][1] == "segmentation fault"


def test_fuzzy_matching_threshold(corrector):
    corrected, changes = corrector.correct_sentence("explain recursun to me", "cse")
    assert "recursion" in corrected.lower()

    # An unrelated word that is very different should not match
    corrected_far, changes_far = corrector.correct_sentence("explain reading to me", "cse")
    assert "recursion" not in corrected_far.lower()
    assert len(changes_far) == 0


def test_phonetic_matching(corrector):
    if corrector.jellyfish_available:
        corrected, changes = corrector.correct_sentence("compile the kernell for me", "cse")
        assert "kernel" in corrected.lower()


def test_stoplist_guard(corrector):
    corrected_clean, changes_clean = corrector.correct_sentence("I need to cash my check", "cse")
    assert "cache" not in corrected_clean.lower()
    assert len(changes_clean) == 0

    corrected_context, changes_context = corrector.correct_sentence("explain cash memory to me", "cse")
    assert "cache" in corrected_context.lower()

    corrected_clean_better, changes_clean_better = corrector.correct_sentence("this is a better option", "cse")
    assert "b-tree" not in corrected_clean_better.lower()
    assert len(changes_clean_better) == 0

    corrected_context_better, changes_context_better = corrector.correct_sentence("explain better tree to me", "cse")
    assert "b-tree" in corrected_context_better.lower()


def test_cross_discipline_isolation(corrector):
    corrected, changes = corrector.correct_sentence("this column is load bearing", "civil")
    assert "column" in corrected.lower()
    assert len(changes) == 0


def test_casing_preservation(corrector):
    corrected_title, _ = corrector.correct_sentence("My Chace is empty", "cse")
    assert "Cache" in corrected_title

    corrected_upper, _ = corrector.correct_sentence("MY CHACE IS EMPTY", "cse")
    assert "CACHE" in corrected_upper

    corrected_canonical, _ = corrector.correct_sentence("call the rest api", "cse")
    assert "REST API" in corrected_canonical


def test_graceful_fail_safe_postgres():
    from agent.database import DatabaseManager
    db = DatabaseManager()
    db.enabled = False

    try:
        import uuid
        asyncio.run(db.write_speech_correction(uuid.uuid4(), uuid.uuid4(), "raw", "corr"))
        asyncio.run(db.fetch_user_corrections(uuid.uuid4()))
    except Exception as e:
        pytest.fail(f"Graceful database fail-safe failed with error: {e}")


@pytest.mark.asyncio
async def test_latency_budget_llm_pass():
    from llm.llm_engine import LLMEngine
    llm = LLMEngine()

    with mock.patch.object(llm.client, "post") as mock_post:
        mock_response = mock.Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "cache"}}]}
        mock_post.return_value = mock_response

        start = time.perf_counter()
        res = await llm.get_completion([{"role": "user", "content": "test"}], max_tokens=10, timeout=0.4)
        duration = time.perf_counter() - start

        assert res == "cache"
        assert duration < 0.4

        async def mock_sleep_post(*args, **kwargs):
            await asyncio.sleep(0.6)
            return mock_response

        mock_post.side_effect = mock_sleep_post

        start = time.perf_counter()
        res_timeout = await llm.get_completion([{"role": "user", "content": "test"}], max_tokens=10, timeout=0.1)
        duration = time.perf_counter() - start

        assert res_timeout == ""
        assert duration < 0.3


def test_get_stoplist_words(corrector):
    stoplist = corrector.get_stoplist_words()
    assert isinstance(stoplist, list)
    assert "better" in stoplist
    assert "cash" in stoplist
    assert stoplist == sorted(stoplist)
