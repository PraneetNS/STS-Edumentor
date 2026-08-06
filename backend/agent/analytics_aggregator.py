"""
backend/agent/analytics_aggregator.py

Asynchronously consumes TurnEvents from Redis Stream, computes real-time stats
(using Redis hashes), and flushes aggregates to PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from agent.models import TurnEvent
from agent.database import DatabaseManager

logger = logging.getLogger("edumentor.agent.analytics_aggregator")

# Prerequisite graph for Concept Dependency Gaps
PREREQUISITE_GRAPH = {
    "stack_frames": "recursion",
    "recursion": "call_stack",
    "dynamic_programming": "recursion",
    "binary_search": "arrays",
    "trees": "linked_lists",
    "graphs": "trees",
}


class AnalyticsAggregator:
    def __init__(self, redis_client, db_manager: DatabaseManager) -> None:
        self.redis = redis_client
        self.db = db_manager
        self.stream_key = "turn_events"
        self.group_name = "analytics_group"
        self.consumer_name = f"consumer_{uuid.uuid4().hex[:6]}"
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background consumer task."""
        if not self.redis:
            logger.warning("Redis client is not available. Aggregator will not run.")
            return

        self.is_running = True
        # Create group if it doesn't exist
        try:
            await self.redis.xgroup_create(self.stream_key, self.group_name, id="0", mkstream=True)
            logger.info("Created Redis Stream consumer group %r on %r", self.group_name, self.stream_key)
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug("Redis Stream consumer group already exists.")
            else:
                logger.error("Failed to create consumer group: %s", e)

        self.task = asyncio.create_task(self._consume_loop())
        logger.info("AnalyticsAggregator worker started (consumer=%s)", self.consumer_name)

    async def stop(self) -> None:
        """Stop the background consumer task."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("AnalyticsAggregator worker stopped.")

    async def _consume_loop(self) -> None:
        """Main consumer loop using XREADGROUP."""
        while self.is_running:
            try:
                # Read new messages (">" means only new messages)
                response = await self.redis.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=5,
                    block=1000
                )
                if not response:
                    continue

                for stream, messages in response:
                    for msg_id, payload in messages:
                        try:
                            event_data = payload.get("event")
                            if event_data:
                                event_dict = json.loads(event_data)
                                event = TurnEvent(**event_dict)
                                await self.process_event(event)
                            
                            # Acknowledge message
                            await self.redis.xack(self.stream_key, self.group_name, msg_id)
                        except Exception as val_exc:
                            logger.error("Failed to process event message %s: %s", msg_id, val_exc)
                            # Acknowledge anyway to prevent infinite loops on corrupted json
                            await self.redis.xack(self.stream_key, self.group_name, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in consumer loop: %s", e)
                await asyncio.sleep(2)

    async def process_event(self, event: TurnEvent) -> None:
        """Process a single TurnEvent."""
        student_id = event.student_id
        session_id = event.session_id
        
        logger.info("[AGGREGATOR] Processing TurnEvent student=%s session=%s topic=%s", student_id, session_id, event.topic)

        # 1. Update Redis live stats hash
        live_key = f"live_stats:{student_id}"
        await self.redis.hincrby(live_key, "turn_count", 1)
        # Assume approx 1.5 active minutes per turn
        await self.redis.hincrby(live_key, "active_minutes", 1)

        # Update topics touched set in Redis
        topics_json = await self.redis.hget(live_key, "topics_touched")
        topics = json.loads(topics_json) if topics_json else []
        if event.topic and event.topic not in topics:
            topics.append(event.topic)
            await self.redis.hset(live_key, "topics_touched", json.dumps(topics))

        # 2. Evaluate topic transitions
        last_turn_key = f"last_turn:{session_id}"
        last_turn_data = await self.redis.get(last_turn_key)
        
        previous_turn: Optional[Dict[str, Any]] = json.loads(last_turn_data) if last_turn_data else None

        if previous_turn:
            prev_topic = previous_turn.get("topic")
            if prev_topic != event.topic:
                # The student changed the topic -> previous topic is now resolved!
                await self.update_topic_mastery(
                    student_id=student_id,
                    branch=previous_turn.get("subject_branch", "cse"),
                    topic=prev_topic,
                    is_confused=previous_turn.get("emotion_signal") in ("confused", "frustrated"),
                    is_resolved=True,
                    is_repeat=previous_turn.get("was_repeat_question", False),
                    increment_attempts=False  # Attempts already counted on emit
                )
                logger.info("[AGGREGATOR] Topic transition resolved previous topic: %r", prev_topic)

        # Update current turn as the last seen turn for the session
        current_turn_state = {
            "topic": event.topic,
            "subject_branch": event.subject_branch,
            "emotion_signal": event.emotion_signal,
            "was_repeat_question": event.was_repeat_question,
            "timestamp": event.timestamp,
        }
        await self.redis.set(last_turn_key, json.dumps(current_turn_state), ex=86400)

        # Log current turn to Postgres topic_mastery as unresolved first (attempts incremented)
        await self.update_topic_mastery(
            student_id=student_id,
            branch=event.subject_branch or "cse",
            topic=event.topic or "general",
            is_confused=event.emotion_signal in ("confused", "frustrated"),
            is_resolved=False,
            is_repeat=event.was_repeat_question,
            increment_attempts=True
        )

    async def update_topic_mastery(
        self,
        student_id: str,
        branch: str,
        topic: str,
        is_confused: bool,
        is_resolved: bool,
        is_repeat: bool,
        increment_attempts: bool = True
    ) -> None:
        """Update Postgres topic_mastery with EMA confidence score."""
        if not self.db or not self.db.pool:
            return

        ALPHA = 0.3
        query_fetch = """
        SELECT attempts, confused_count, resolved_count, repeat_question_count, confidence_score
        FROM topic_mastery
        WHERE student_id = $1 AND subject_branch = $2 AND topic = $3;
        """
        try:
            student_uuid = uuid.UUID(student_id)
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query_fetch, student_uuid, branch, topic)
                
                if row:
                    attempts = row["attempts"] + (1 if increment_attempts else 0)
                    confused_count = row["confused_count"] + (1 if is_confused else 0)
                    resolved_count = row["resolved_count"] + (1 if is_resolved else 0)
                    repeat_count = row["repeat_question_count"] + (1 if is_repeat else 0)
                    prev_score = row["confidence_score"]
                else:
                    attempts = 1 if increment_attempts else 0
                    confused_count = 1 if is_confused else 0
                    resolved_count = 1 if is_resolved else 0
                    repeat_count = 1 if is_repeat else 0
                    prev_score = 0.5

                # EMA scoring formula
                new_signal = 1.0 if is_resolved else (0.0 if is_confused else 0.5)
                confidence_score = ALPHA * new_signal + (1 - ALPHA) * prev_score

                query_upsert = """
                INSERT INTO topic_mastery (
                    student_id, subject_branch, topic, attempts, confused_count,
                    resolved_count, repeat_question_count, confidence_score, last_seen
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (student_id, subject_branch, topic) DO UPDATE SET
                    attempts = EXCLUDED.attempts,
                    confused_count = EXCLUDED.confused_count,
                    resolved_count = EXCLUDED.resolved_count,
                    repeat_question_count = EXCLUDED.repeat_question_count,
                    confidence_score = EXCLUDED.confidence_score,
                    last_seen = EXCLUDED.last_seen;
                """
                await conn.execute(
                    query_upsert,
                    student_uuid,
                    branch,
                    topic,
                    attempts,
                    confused_count,
                    resolved_count,
                    repeat_count,
                    confidence_score
                )
        except Exception as e:
            logger.error("Failed to update topic mastery in Postgres: %s", e)

    async def on_session_end(self, session_id: str, student_id: str) -> None:
        """Triggered on WebSocket session disconnect to clean up and flush stats."""
        if not self.redis or not self.db or not self.db.pool:
            return

        logger.info("[AGGREGATOR] Flushing session analytics for session=%s", session_id)
        
        student_uuid = uuid.UUID(student_id)
        session_uuid = uuid.UUID(session_id)

        # 1. Resolve the last topic discussed
        last_turn_key = f"last_turn:{session_id}"
        last_turn_data = await self.redis.get(last_turn_key)
        if last_turn_data:
            previous_turn = json.loads(last_turn_data)
            await self.update_topic_mastery(
                student_id=student_id,
                branch=previous_turn.get("subject_branch", "cse"),
                topic=previous_turn.get("topic", "general"),
                is_confused=previous_turn.get("emotion_signal") in ("confused", "frustrated"),
                is_resolved=True,
                is_repeat=previous_turn.get("was_repeat_question", False),
                increment_attempts=False
            )
            await self.redis.delete(last_turn_key)

        # 2. Aggregate session data from PostgreSQL conversation_logs
        query_logs = """
        SELECT created_at, intent_category, response_lang, output_flagged
        FROM conversation_logs
        WHERE session_id = $1 AND user_id = $2;
        """
        try:
            async with self.db.pool.acquire() as conn:
                logs = await conn.fetch(query_logs, session_uuid, student_uuid)
                if not logs:
                    return

                started_at = min(r["created_at"] for r in logs)
                ended_at = max(r["created_at"] for r in logs)
                turn_count = len(logs)
                interruption_count = sum(1 for r in logs if r["output_flagged"] is True)

                # Fetch unique topics for this session from Redis live stats, or default
                live_key = f"live_stats:{student_id}"
                topics_json = await self.redis.hget(live_key, "topics_touched")
                topics_covered = json.loads(topics_json) if topics_json else ["general"]
                
                # Languages used
                languages_used = list(set(r["response_lang"] for r in logs if r["response_lang"]))
                if not languages_used:
                    languages_used = ["english"]

                # Average confidence in this session (mean of confidence scores for topics covered)
                avg_confidence = 0.5
                if topics_covered:
                    placeholders = ",".join(f"${i+2}" for i in range(len(topics_covered)))
                    query_conf = f"""
                    SELECT AVG(confidence_score) FROM topic_mastery
                    WHERE student_id = $1 AND topic IN ({placeholders});
                    """
                    avg_conf_val = await conn.fetchval(query_conf, student_uuid, *topics_covered)
                    if avg_conf_val is not None:
                        avg_confidence = float(avg_conf_val)

                # Insert session summary
                query_sess = """
                INSERT INTO session_summary (
                    session_id, student_id, started_at, ended_at, turn_count,
                    topics_covered, interruption_count, avg_confidence, languages_used
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (session_id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    turn_count = EXCLUDED.turn_count,
                    topics_covered = EXCLUDED.topics_covered,
                    interruption_count = EXCLUDED.interruption_count,
                    avg_confidence = EXCLUDED.avg_confidence,
                    languages_used = EXCLUDED.languages_used;
                """
                await conn.execute(
                    query_sess,
                    session_uuid,
                    student_uuid,
                    started_at,
                    ended_at,
                    turn_count,
                    topics_covered,
                    interruption_count,
                    avg_confidence,
                    languages_used
                )

                # 3. Update daily activity
                activity_date = started_at.date()
                
                # Fetch all turns for this user today
                query_day_stats = """
                SELECT SUM(turn_count) as total_turns FROM session_summary
                WHERE student_id = $1 AND DATE(started_at) = $2;
                """
                total_turns_today = await conn.fetchval(query_day_stats, student_uuid, activity_date) or turn_count
                
                # 1.5 active minutes per turn
                minutes_active = int(total_turns_today * 1.5)

                query_day = """
                INSERT INTO daily_activity (student_id, activity_date, minutes_active, turn_count)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (student_id, activity_date) DO UPDATE SET
                    minutes_active = EXCLUDED.minutes_active,
                    turn_count = EXCLUDED.turn_count;
                """
                await conn.execute(query_day, student_uuid, activity_date, minutes_active, total_turns_today)

        except Exception as e:
            logger.error("Failed to finalize session summary for session=%s: %s", session_id, e)


# Singleton reference for main.py access
_aggregator_instance: Optional[AnalyticsAggregator] = None


async def start_analytics_aggregator(redis_client, db_manager: DatabaseManager) -> AnalyticsAggregator:
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = AnalyticsAggregator(redis_client, db_manager)
        await _aggregator_instance.start()
    return _aggregator_instance


async def stop_analytics_aggregator() -> None:
    global _aggregator_instance
    if _aggregator_instance is not None:
        await _aggregator_instance.stop()
        _aggregator_instance = None


def get_analytics_aggregator() -> Optional[AnalyticsAggregator]:
    return _aggregator_instance
