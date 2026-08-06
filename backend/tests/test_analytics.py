"""
backend/tests/test_analytics.py

Unit tests for the real-time student analytics pipeline, including:
- TurnEvent emission
- AnalyticsAggregator processing logic and EMA score calculations
- Session end rollup and daily activity logs
"""

import pytest
import asyncio
import uuid
import json
from datetime import datetime, date

from agent.models import TurnEvent
from agent.analytics_aggregator import AnalyticsAggregator


class MockRedis:
    def __init__(self):
        self.hashes = {}
        self.keys = {}
        self.streams = {}

    async def hincrby(self, key, field, amount):
        if key not in self.hashes:
            self.hashes[key] = {}
        curr = int(self.hashes[key].get(field, 0))
        self.hashes[key][field] = str(curr + amount)
        return curr + amount

    async def hget(self, key, field):
        if key in self.hashes:
            return self.hashes[key].get(field)
        return None

    async def hset(self, key, field, value):
        if key not in self.hashes:
            self.hashes[key] = {}
        self.hashes[key][field] = str(value)

    async def hgetall(self, key):
        return self.hashes.get(key, {})

    async def get(self, key):
        return self.keys.get(key)

    async def set(self, key, value, ex=None):
        self.keys[key] = str(value)

    async def delete(self, key):
        self.keys.pop(key, None)


class MockConnection:
    def __init__(self, db_state):
        self.db_state = db_state

    async def fetchrow(self, query, *args):
        if "FROM topic_mastery" in query:
            student_uuid = args[0]
            topic = None
            if "AND topic = " in query:
                parts = query.split("AND topic = ")
                if len(parts) > 1:
                    topic = parts[1].split(";")[0].strip().replace("'", "").replace('"', "")
            if len(args) >= 3:
                topic = args[2]

            for k, v in self.db_state["topic_mastery"].items():
                if k[0] == student_uuid and (topic is None or k[1] == topic):
                    # Return dict-like behavior for column names
                    return v
            return None
        return None

    async def fetch(self, query, *args):
        if "FROM conversation_logs" in query:
            return self.db_state["conversation_logs"]
        elif "FROM session_summary" in query:
            return self.db_state["session_summary"]
        elif "FROM daily_activity" in query:
            return self.db_state["daily_activity"]
        return []

    async def execute(self, query, *args):
        if "INSERT INTO topic_mastery" in query:
            student_uuid, branch, topic, attempts, confused, resolved, repeat, confidence = args
            self.db_state["topic_mastery"][(student_uuid, topic)] = {
                "attempts": attempts,
                "confused_count": confused,
                "resolved_count": resolved,
                "repeat_question_count": repeat,
                "confidence_score": confidence,
                "subject_branch": branch,
            }
        elif "INSERT INTO session_summary" in query:
            session_uuid, student_uuid, started_at, ended_at, turn_count, topics_covered, interruption_count, avg_confidence, languages_used = args
            self.db_state["session_summary"].append({
                "session_id": session_uuid,
                "student_id": student_uuid,
                "started_at": started_at,
                "ended_at": ended_at,
                "turn_count": turn_count,
                "topics_covered": topics_covered,
                "interruption_count": interruption_count,
                "avg_confidence": avg_confidence,
                "languages_used": languages_used,
            })
        elif "INSERT INTO daily_activity" in query:
            student_uuid, activity_date, minutes_active, total_turns = args
            self.db_state["daily_activity"].append({
                "student_uuid": student_uuid,
                "activity_date": activity_date,
                "minutes_active": minutes_active,
                "turn_count": total_turns
            })
        return None

    async def fetchval(self, query, *args):
        if "SELECT AVG(confidence_score)" in query:
            scores = [v["confidence_score"] for v in self.db_state["topic_mastery"].values()]
            return sum(scores) / len(scores) if scores else 0.5
        elif "SELECT SUM(turn_count)" in query:
            return sum(s["turn_count"] for s in self.db_state["session_summary"])
        return None


class MockPool:
    def __init__(self, db_state):
        self.db_state = db_state

    def acquire(self):
        class AsyncContext:
            def __init__(self, conn):
                self.conn = conn
            async def __aenter__(self):
                return self.conn
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return AsyncContext(MockConnection(self.db_state))


class MockDBManager:
    def __init__(self):
        self.db_state = {
            "topic_mastery": {},
            "conversation_logs": [],
            "session_summary": [],
            "daily_activity": [],
        }
        self.pool = MockPool(self.db_state)


@pytest.fixture
def mock_analytics_db():
    return MockDBManager()


@pytest.mark.asyncio
async def test_analytics_aggregator_processing(mock_analytics_db):
    redis = MockRedis()
    aggregator = AnalyticsAggregator(redis, mock_analytics_db)

    student_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    # Turn 1: recursion (confused)
    event1 = TurnEvent(
        student_id=student_id,
        session_id=session_id,
        turn_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat(),
        intent="CONCEPT_EXPLANATION",
        topic="recursion",
        subject_branch="cse",
        language="english",
        emotion_signal="confused",
        grounding_used=False,
        was_repeat_question=False,
        was_interrupted=False,
        turn_duration_ms=250,
    )

    await aggregator.process_event(event1)

    # Check live stats updated in Redis
    live_stats = await redis.hgetall(f"live_stats:{student_id}")
    assert live_stats["turn_count"] == "1"
    assert live_stats["active_minutes"] == "1"
    
    topics = json.loads(live_stats["topics_touched"])
    assert "recursion" in topics

    # Check topic_mastery row created in postgres mock_analytics_db
    async with mock_analytics_db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT attempts, confused_count, confidence_score FROM topic_mastery WHERE student_id = $1 AND topic = 'recursion';", uuid.UUID(student_id))
        assert row is not None
        assert row["attempts"] == 1
        assert row["confused_count"] == 1
        # EMA: 0.3 * 0.0 + 0.7 * 0.5 = 0.35
        assert abs(row["confidence_score"] - 0.35) < 0.01

    # Turn 2: sorting (topic transition, recursion gets resolved)
    event2 = TurnEvent(
        student_id=student_id,
        session_id=session_id,
        turn_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat(),
        intent="CONCEPT_EXPLANATION",
        topic="sorting",
        subject_branch="cse",
        language="english",
        emotion_signal="neutral",
        grounding_used=False,
        was_repeat_question=False,
        was_interrupted=False,
        turn_duration_ms=300,
    )

    await aggregator.process_event(event2)

    # Check topic transition: recursion should now have resolved_count = 1 and updated confidence score
    async with mock_analytics_db.pool.acquire() as conn:
        row_recursion = await conn.fetchrow("SELECT attempts, resolved_count, confidence_score FROM topic_mastery WHERE student_id = $1 AND topic = 'recursion';", uuid.UUID(student_id))
        assert row_recursion["resolved_count"] == 1
        # Recursion attempts shouldn't double increment on transition resolution
        assert row_recursion["attempts"] == 1
        # EMA recursion: 0.3 * 1.0 + 0.7 * 0.35 = 0.545
        assert abs(row_recursion["confidence_score"] - 0.545) < 0.01

        # Check new sorting topic mastery
        row_sorting = await conn.fetchrow("SELECT attempts, resolved_count, confidence_score FROM topic_mastery WHERE student_id = $1 AND topic = 'sorting';", uuid.UUID(student_id))
        assert row_sorting["attempts"] == 1
        assert row_sorting["resolved_count"] == 0
        # EMA sorting: 0.3 * 0.5 + 0.7 * 0.5 = 0.5
        assert abs(row_sorting["confidence_score"] - 0.5) < 0.01


@pytest.mark.asyncio
async def test_session_end_rollup(mock_analytics_db):
    redis = MockRedis()
    aggregator = AnalyticsAggregator(redis, mock_analytics_db)

    student_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    student_uuid = uuid.UUID(student_id)
    session_uuid = uuid.UUID(session_id)

    # Pre-populate logs so rollup can query them
    mock_analytics_db.db_state["conversation_logs"].extend([
        {
            "created_at": datetime.utcnow(),
            "intent_category": "CONCEPT_EXPLANATION",
            "response_lang": "english",
            "output_flagged": False
        },
        {
            "created_at": datetime.utcnow(),
            "intent_category": "CONCEPT_EXPLANATION",
            "response_lang": "english",
            "output_flagged": True
        }
    ])

    # Set last turn topic in Redis
    last_turn_key = f"last_turn:{session_id}"
    await redis.set(last_turn_key, json.dumps({
        "topic": "recursion",
        "subject_branch": "cse",
        "emotion_signal": "neutral",
        "was_repeat_question": False,
        "timestamp": datetime.utcnow().isoformat(),
    }))

    # Trigger session end rollup
    await aggregator.on_session_end(session_id, student_id)

    # 1. Verify last topic was resolved
    async with mock_analytics_db.pool.acquire() as conn:
        row_rec = await conn.fetchrow("SELECT resolved_count, confidence_score FROM topic_mastery WHERE student_id = $1 AND topic = 'recursion';", student_uuid)
        assert row_rec is not None
        assert row_rec["resolved_count"] == 1

        # 2. Verify session_summary row created
        summaries = mock_analytics_db.db_state["session_summary"]
        assert len(summaries) == 1
        assert summaries[0]["turn_count"] == 2
        assert summaries[0]["interruption_count"] == 1
        
        # 3. Verify daily_activity updated
        daily = mock_analytics_db.db_state["daily_activity"]
        assert len(daily) == 1
        assert daily[0]["turn_count"] == 2
        assert daily[0]["minutes_active"] == 3 # 2 turns * 1.5 min = 3 min
