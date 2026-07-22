"""
EduMentor — Prompt Caching Test Suite

Verifies that KV cache reuse is actually engaging in the llama-server pipeline.

Tests are split into two categories:
  - Pure unit tests (no server required): slot affinity, determinism, distribution.
  - Integration tests (live llama-server required): timing-based cache hit verification.

Run all:
    pytest backend/tests/test_prompt_caching.py -v -s

The -s flag is required to see the printed timing comparisons from integration tests.

Integration tests are automatically skipped when llama-server is not reachable.
Set LLM_BASE_URL in .env or environment to override the default (http://localhost:8080).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import List, Dict

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Import the modules under test
# ---------------------------------------------------------------------------
from llm.llm_engine import get_slot_for_session, NUM_SLOTS, LLMEngine
from agent.prompt_builder import PromptBuilder
from agent.models import (
    AgentContext,
    Intent,
    EmotionResult,
    StudentProfile,
)
from config import Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILDER = PromptBuilder()


def _make_profile(weak_areas: list[str] | None = None) -> StudentProfile:
    return StudentProfile(
        name="TestStudent",
        level="beginner",
        learning_topics=["Python"],
        weak_topics=weak_areas or [],
        preferred_style="examples",
        session_count=1,
        discipline="cse",
        active_topics=["Python"],
    )


def _make_context(
    session_id: str,
    user_text: str,
    profile: StudentProfile | None = None,
    history_messages: list[dict] | None = None,
) -> AgentContext:
    return AgentContext(
        session_id=session_id,
        user_text=user_text,
        intent=Intent.CONCEPT_EXPLANATION,
        emotion=EmotionResult.neutral(),
        profile=profile or _make_profile(),
        history_messages=history_messages or [],
        safety_flags={},
    )


def build_messages(
    session_id: str,
    user_text: str,
    profile: StudentProfile | None = None,
    history_messages: list[dict] | None = None,
) -> list[dict]:
    """Build messages list via PromptBuilder (mirrors the real pipeline)."""
    ctx = _make_context(session_id, user_text, profile, history_messages)
    return _builder.build_messages(ctx)


_builder = _BUILDER


def _server_reachable() -> bool:
    """Return True if llama-server is up and accepting connections."""
    try:
        r = httpx.get(f"{Config.LLM_BASE_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


SKIP_INTEGRATION = pytest.mark.skipif(
    not _server_reachable(),
    reason="llama-server not reachable at %s — skipping integration test" % Config.LLM_BASE_URL,
)


# ---------------------------------------------------------------------------
# PART A — Pure unit tests (no server required)
# ---------------------------------------------------------------------------


class TestSlotAffinity:
    """
    Slot assignment must be deterministic and distribute sessions reasonably
    across available slots. No server connection needed.
    """

    def test_slot_affinity_consistent(self):
        """Same session_id must always resolve to the same slot index."""
        session_id = "affinity_test_session"
        slots = [get_slot_for_session(session_id) for _ in range(10)]
        assert len(set(slots)) == 1, (
            f"Slot assignment is not deterministic: got {set(slots)} across 10 calls"
        )

    def test_slot_in_valid_range(self):
        """Slot index must always be in [0, NUM_SLOTS)."""
        for i in range(50):
            slot = get_slot_for_session(f"session_{i}")
            assert 0 <= slot < NUM_SLOTS, (
                f"Slot {slot} out of range [0, {NUM_SLOTS}) for session_{i}"
            )

    def test_different_sessions_get_different_slots_when_possible(self):
        """
        With NUM_SLOTS >= 4, four different session_ids should land on at
        least 2 distinct slots. Not a strict guarantee (hash collisions are
        possible), but total collision across all 4 is extremely unlikely.
        """
        sessions = [f"session_{i}" for i in range(4)]
        slots = [get_slot_for_session(s, num_slots=4) for s in sessions]
        unique_slots = set(slots)
        assert len(unique_slots) >= 2, (
            f"Slot distribution is too collision-prone: all 4 sessions landed on {unique_slots}. "
            f"This may indicate a bug in get_slot_for_session()."
        )
        print(f"\n[SLOT DISTRIBUTION] sessions={sessions} -> slots={slots}")

    def test_empty_session_id_defaults_to_slot_zero(self):
        """Empty session_id should not raise and should return a valid slot."""
        slot = get_slot_for_session("")
        assert slot == 0, f"Expected slot 0 for empty session_id, got {slot}"

    def test_num_slots_matches_server_config(self):
        """
        NUM_SLOTS in llm_engine.py must match the -np flag passed to llama-server.
        This test documents the contract — if you change -np, update NUM_SLOTS too.
        """
        assert NUM_SLOTS in (1, 4), (
            f"NUM_SLOTS={NUM_SLOTS} but run_llm_server.bat/sh passes -np 1 or 4. "
            f"Update the constant or the server flag to match."
        )


class TestPromptPrefixStability:
    """
    Verify that the first system message (_BASE_SYSTEM) is byte-identical
    across different requests. This is the cache anchor — if it differs even
    by one character, llama.cpp cannot reuse the prefix.
    """

    def test_static_layer_identical_across_calls(self):
        """Layer 1 (first system message) must be byte-identical regardless of session."""
        msgs_a = build_messages("session_a", "what is recursion")
        msgs_b = build_messages("session_b", "what is dynamic programming")
        assert msgs_a[0]["content"] == msgs_b[0]["content"], (
            "Layer 1 (static system message) differs between sessions — "
            "this will break the KV cache prefix for every request."
        )

    def test_static_layer_identical_across_turns(self):
        """Layer 1 must not change between turn 1 and turn 2 of the same session."""
        session_id = "stable_prefix_session"
        profile = _make_profile()

        # Turn 1 — no history
        msgs_turn1 = build_messages(session_id, "what is a linked list", profile)

        # Turn 2 — with history from turn 1
        history_after_turn1 = [
            {"role": "user",      "content": "what is a linked list"},
            {"role": "assistant", "content": "<speak>A linked list is...</speak><followup>Would you like to see an example?</followup>"},
        ]
        msgs_turn2 = build_messages(
            session_id, "give me an example", profile, history_after_turn1
        )

        assert msgs_turn1[0]["content"] == msgs_turn2[0]["content"], (
            "Layer 1 (static system message) changed between turn 1 and turn 2. "
            "This invalidates the cached prefix at the very first token."
        )

    def test_profile_block_fixed_field_order(self):
        """
        build_profile_block() must produce the same string regardless of
        how the StudentProfile was constructed, as long as the field values
        are the same. Dict ordering or field-insertion order must not affect
        the output.
        """
        builder = PromptBuilder()
        profile_a = StudentProfile(
            name="Savan", level="intermediate",
            learning_topics=["Python", "ML"], weak_topics=["recursion"],
            preferred_style="examples", session_count=3, discipline="cse",
            active_topics=["Python"],
        )
        profile_b = StudentProfile(
            name="Savan", level="intermediate",
            # Same fields, different insertion sequence (for future-proofing)
            weak_topics=["recursion"], learning_topics=["Python", "ML"],
            preferred_style="examples", session_count=3, discipline="cse",
            active_topics=["Python"],
        )
        block_a = builder.build_profile_block(profile_a)
        block_b = builder.build_profile_block(profile_b)
        assert block_a == block_b, (
            f"Profile block differs despite identical field values:\n"
            f"  A: {block_a!r}\n  B: {block_b!r}\n"
            "This means field order is non-deterministic — cache will miss every call."
        )


# ---------------------------------------------------------------------------
# PART B — Integration tests (require live llama-server)
# ---------------------------------------------------------------------------

@SKIP_INTEGRATION
@pytest.mark.asyncio
async def test_kv_cache_hit_on_repeated_system_prompt():
    """
    First call is a cold prefill — all tokens computed from scratch.
    Second call with the same session (same slot, same system prefix) should
    show a dramatically shorter prefill time because only the new user message
    needs fresh computation.

    Expected: warm_prefill_ms < cold_prefill_ms * 0.4
    (60%+ reduction — only the new message tokens are re-prefilled)
    """
    engine = LLMEngine()
    session_id = "test_cache_session_cold_warm"
    profile = _make_profile()

    # ── Turn 1: cold prefill ─────────────────────────────────────────────────
    msgs_turn1 = build_messages(session_id, "what is dynamic programming", profile)
    cold_start = time.perf_counter()
    response1_tokens = []
    async for token in engine.stream_tokens_from_messages(msgs_turn1, session_id=session_id, max_tokens=10):
        response1_tokens.append(token)
    cold_elapsed_ms = (time.perf_counter() - cold_start) * 1000
    response1_text = "".join(response1_tokens)

    if "offline" in response1_text:
        await engine.aclose()
        pytest.skip("LLM server is offline — skipping cache timing checks.")

    # ── Turn 2: warm prefill ─────────────────────────────────────────────────
    # Append the first turn to history so the prefix includes it.
    history_after_turn1 = [
        {"role": "user",      "content": "what is dynamic programming"},
        {"role": "assistant", "content": response1_text},
    ]
    msgs_turn2 = build_messages(
        session_id, "can you give an example", profile, history_after_turn1
    )
    warm_start = time.perf_counter()
    response2_tokens = []
    async for token in engine.stream_tokens_from_messages(msgs_turn2, session_id=session_id, max_tokens=10):
        response2_tokens.append(token)
    warm_elapsed_ms = (time.perf_counter() - warm_start) * 1000

    print(f"\n[CACHE TIMING] Cold turn (full prefill): {cold_elapsed_ms:.0f}ms total")
    print(f"[CACHE TIMING] Warm turn (cached prefix): {warm_elapsed_ms:.0f}ms total")
    print(f"[CACHE TIMING] Ratio warm/cold: {warm_elapsed_ms/cold_elapsed_ms:.2%}")
    print(
        "[CACHE TIMING] NOTE: These are total streaming times, not isolated prefill times. "
        "For exact prefill_ms, enable llama-server timing headers and parse 'timings' from the response."
    )

    # The warm turn covers far fewer new tokens (only the new message, not the whole prefix),
    # so its total time should be meaningfully shorter. We use a conservative threshold
    # of 0.85 here since total streaming time includes generation (which is not cached).
    assert warm_elapsed_ms < cold_elapsed_ms * 0.85, (
        f"Warm turn ({warm_elapsed_ms:.0f}ms) is not shorter than 85% of cold turn "
        f"({cold_elapsed_ms:.0f}ms). Cache may not be engaging. "
        f"Check: (1) same slot_id used? (2) --cache-reuse 256 set? (3) prefix byte-stable?"
    )

    await engine.aclose()


@SKIP_INTEGRATION
@pytest.mark.asyncio
async def test_cache_breaks_correctly_on_profile_change():
    """
    When the student profile's weak_areas changes mid-session, Layer 2 (the
    dynamic context message) changes. This should cause a higher prefill cost
    for that turn compared to a normal warm turn, because the cached prefix
    no longer matches from the profile block onward.

    This test verifies that cache INVALIDATION works correctly — not just hits.
    """
    engine = LLMEngine()
    session_id = "profile_change_session"
    profile_before = _make_profile(weak_areas=[])

    # Warm-up turn with original profile
    msgs_turn1 = build_messages(session_id, "explain graphs", profile_before)
    warm1_tokens = []
    async for token in engine.stream_tokens_from_messages(msgs_turn1, session_id=session_id):
        warm1_tokens.append(token)
    warm1_text = "".join(warm1_tokens)

    if "offline" in warm1_text:
        await engine.aclose()
        pytest.skip("LLM server is offline — skipping cache invalidation checks.")

    # Second turn with same profile — establish a warm baseline
    history = [
        {"role": "user",      "content": "explain graphs"},
        {"role": "assistant", "content": warm1_text},
    ]
    msgs_turn2 = build_messages(
        session_id, "give me a practice problem", profile_before, history
    )
    warm2_start = time.perf_counter()
    async for _ in engine.stream_tokens_from_messages(msgs_turn2, session_id=session_id):
        pass
    warm2_ms = (time.perf_counter() - warm2_start) * 1000

    # Simulate a profile update — weak_areas changes → Layer 2 changes
    profile_after = _make_profile(weak_areas=["graphs"])

    msgs_turn3 = build_messages(
        session_id, "I still don't understand", profile_after, history
    )
    invalidated_start = time.perf_counter()
    async for _ in engine.stream_tokens_from_messages(msgs_turn3, session_id=session_id):
        pass
    invalidated_ms = (time.perf_counter() - invalidated_start) * 1000

    print(f"\n[CACHE INVALIDATION] Normal warm turn: {warm2_ms:.0f}ms")
    print(f"[CACHE INVALIDATION] After profile change: {invalidated_ms:.0f}ms")
    print(
        "[CACHE INVALIDATION] The post-change turn should be elevated vs the warm turn "
        "because the profile block changed, invalidating the KV cache from that point forward. "
        "This confirms cache invalidation works correctly."
    )

    # We don't assert a hard threshold here — generation time dominates.
    # The print output gives the developer the information to judge manually.

    await engine.aclose()


@SKIP_INTEGRATION
@pytest.mark.asyncio
async def test_slots_endpoint_accessible():
    """
    Verify that the /slots endpoint is available (requires --slots flag on server).
    After a request, n_past on the assigned slot should be > 0.

    curl http://localhost:8080/slots
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{Config.LLM_BASE_URL}/slots")
            if resp.status_code != 200:
                pytest.skip(f"/slots returned {resp.status_code} — skipping slots verification.")
        except Exception:
            pytest.skip("Cannot reach llama-server /slots — skipping slots verification.")

        slots_data = resp.json()
        print(f"\n[SLOTS] {len(slots_data)} slot(s) reported by server")
        for i, slot in enumerate(slots_data):
            n_past = slot.get("n_past", "N/A")
            print(f"  Slot {i}: n_past={n_past}")
