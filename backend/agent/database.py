"""
EduMentor Agent Layer — Database Manager

Manages the PostgreSQL connection pool, ensures the conversation_logs table
and indexes exist, and provides async query and write execution.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
import asyncpg

from config import Config

logger = logging.getLogger("edumentor.agent.database")

# Expose connection pool globally for the security logger
db_pool = None


class DatabaseManager:
    """
    Manages connection pooling and queries for the PostgreSQL storage backend.
    """

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None
        self.host = Config.POSTGRES_HOST
        self.port = Config.POSTGRES_PORT
        self.user = Config.POSTGRES_USER
        self.password = Config.POSTGRES_PASSWORD
        self.database = Config.POSTGRES_DB
        self.pool_size = Config.POSTGRES_POOL_SIZE
        self.enabled = Config.POSTGRES_ENABLED

    async def initialize(self) -> None:
        """
        Initialize the asyncpg connection pool and create tables/indexes.
        """
        if not self.enabled:
            logger.info("PostgreSQL is disabled in configuration. Skipping initialization.")
            return

        try:
            logger.info(
                "Connecting to PostgreSQL at %s:%d/%s (pool_size=%d)...",
                self.host,
                self.port,
                self.database,
                self.pool_size,
            )
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=self.pool_size,
                max_size=self.pool_size,
            )
            global db_pool
            db_pool = self.pool
            logger.info("[OK] PostgreSQL connection pool initialized.")
            
            # Verify tables and indexes exist
            await self.create_tables()
        except Exception as e:
            logger.error(
                "Failed to initialize PostgreSQL pool: %s. "
                "The server will continue in fail-safe/mock mode.",
                e,
            )

    async def create_tables(self) -> None:
        """
        Ensure the conversation_logs table and indexes exist.
        """
        if not self.pool:
            return

        query_table = """
        CREATE TABLE IF NOT EXISTS conversation_logs (
            id              BIGSERIAL PRIMARY KEY,
            user_id         UUID NOT NULL,
            session_id      UUID NOT NULL,
            query_text      TEXT NOT NULL,
            response_text   TEXT NOT NULL,
            intent_category VARCHAR(32),
            input_flagged   BOOLEAN DEFAULT FALSE,
            output_flagged  BOOLEAN DEFAULT FALSE,
            flag_reason     TEXT,
            latency_ms      INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        query_index_user = """
        CREATE INDEX IF NOT EXISTS idx_conv_user_time ON conversation_logs (user_id, created_at DESC);
        """
        query_index_session = """
        CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_logs (session_id, created_at DESC);
        """
        query_corr_table = """
        CREATE TABLE IF NOT EXISTS speech_corrections (
            id              BIGSERIAL PRIMARY KEY,
            user_id         UUID NOT NULL,
            session_id      UUID NOT NULL,
            raw_text        TEXT NOT NULL,
            corrected_text  TEXT NOT NULL,
            source          VARCHAR(16) NOT NULL DEFAULT 'session',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        query_index_corr = """
        CREATE INDEX IF NOT EXISTS idx_speech_corr_user ON speech_corrections (user_id);
        """
        query_sec_table = """
        CREATE TABLE IF NOT EXISTS security_events (
            event_id     SERIAL PRIMARY KEY,
            student_id   TEXT,
            ip_address   TEXT,
            event_type   TEXT NOT NULL,
            details      TEXT,
            timestamp    TIMESTAMP DEFAULT NOW()
        );
        """
        query_index_sec = """
        CREATE INDEX IF NOT EXISTS idx_sec_student_event ON security_events (student_id, event_type);
        """
        query_low_conf_table = """
        CREATE TABLE IF NOT EXISTS low_confidence_responses (
            id              BIGSERIAL PRIMARY KEY,
            student_id      TEXT,
            session_id      TEXT,
            response_text   TEXT,
            matched_hedging TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        query_pgcrypto = 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";'
        query_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email         TEXT UNIQUE NOT NULL,
            display_name  TEXT,
            avatar_url    TEXT,
            provider      TEXT NOT NULL DEFAULT 'email',
            password_hash TEXT,
            email_verified BOOLEAN DEFAULT FALSE,
            created_at    TIMESTAMPTZ DEFAULT now(),
            last_active   TIMESTAMPTZ DEFAULT now()
        );
        """
        query_session_stats_table = """
        CREATE TABLE IF NOT EXISTS session_stats (
            stat_id          BIGSERIAL PRIMARY KEY,
            user_id          UUID REFERENCES users(user_id) ON DELETE CASCADE,
            session_date     DATE NOT NULL DEFAULT CURRENT_DATE,
            total_turns      INTEGER DEFAULT 0,
            total_tokens_in  INTEGER DEFAULT 0,
            total_tokens_out INTEGER DEFAULT 0,
            disciplines_hit  TEXT[],
            intent_dist      JSONB,
            avg_turns_per_concept FLOAT,
            self_initiated_questions INTEGER DEFAULT 0,
            followup_rate    FLOAT,
            UNIQUE(user_id, session_date)
        );
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query_pgcrypto)
                await conn.execute(query_users_table)
                await conn.execute(query_session_stats_table)
                await conn.execute(query_table)
                await conn.execute(query_index_user)
                await conn.execute(query_index_session)
                await conn.execute(query_corr_table)
                await conn.execute(query_index_corr)
                await conn.execute(query_sec_table)
                await conn.execute(query_index_sec)
                await conn.execute(query_low_conf_table)
                logger.info("[OK] PostgreSQL database schema and indexes verified.")
        except Exception as e:
            logger.error("Failed to verify database schema: %s", e)


    async def close(self) -> None:
        """
        Close the connection pool.
        """
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed.")

    async def write_log(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        query_text: str,
        response_text: str,
        intent_category: Optional[str] = None,
        input_flagged: bool = False,
        output_flagged: bool = False,
        flag_reason: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> None:
        """
        Write a conversation log row. Executed asynchronously (non-blocking).
        """
        if not self.enabled or not self.pool:
            logger.debug("Database logger disabled or pool not initialized. Skipping log write.")
            return

        query = """
        INSERT INTO conversation_logs (
            user_id,
            session_id,
            query_text,
            response_text,
            intent_category,
            input_flagged,
            output_flagged,
            flag_reason,
            latency_ms
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    user_id,
                    session_id,
                    query_text,
                    response_text,
                    intent_category,
                    input_flagged,
                    output_flagged,
                    flag_reason,
                    latency_ms,
                )
                logger.info(
                    "Successfully logged turn to DB. user_id=%s, session_id=%s, input_flagged=%s, output_flagged=%s",
                    user_id,
                    session_id,
                    input_flagged,
                    output_flagged,
                )
        except Exception as e:
            logger.error("Failed to write log to PostgreSQL database: %s", e)

    async def log_low_confidence_response(
        self,
        student_id: str,
        session_id: str,
        response_text: str,
        matched_hedging: str,
    ) -> None:
        """Log a low-confidence response due to hedging."""
        if not self.enabled or not self.pool:
            logger.debug("Database disabled or pool not initialized. Skipping low confidence response log.")
            return

        query = """
        INSERT INTO low_confidence_responses (
            student_id,
            session_id,
            response_text,
            matched_hedging
        ) VALUES ($1, $2, $3, $4);
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, student_id, session_id, response_text, matched_hedging)
                logger.info(
                    "Logged low-confidence response to DB. student_id=%s, session_id=%s, hedging=%s",
                    student_id, session_id, matched_hedging
                )
        except Exception as e:
            logger.error("Failed to write low-confidence response to PostgreSQL: %s", e)

    async def fetch_history(
        self,
        user_id: uuid.UUID,
        session_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the last limit records for a given user_id and optional session_id, ordered by created_at DESC.
        """
        if not self.enabled or not self.pool:
            logger.debug("Database disabled or pool not initialized. Returning empty history.")
            return []

        if session_id:
            query = """
            SELECT query_text, response_text, intent_category, created_at
            FROM conversation_logs
            WHERE user_id = $1 AND session_id = $2
            ORDER BY created_at DESC
            LIMIT $3;
            """
            args = (user_id, session_id, limit)
        else:
            query = """
            SELECT query_text, response_text, intent_category, created_at
            FROM conversation_logs
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2;
            """
            args = (user_id, limit)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Failed to fetch history for user_id=%s from PostgreSQL: %s", user_id, e)
            return []

    async def write_speech_correction(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        raw_text: str,
        corrected_text: str,
        source: str = "session",
    ) -> None:
        """
        Write a speech correction log row.
        """
        if not self.enabled or not self.pool:
            logger.debug("Database disabled or pool not initialized. Skipping speech correction write.")
            return

        query = """
        INSERT INTO speech_corrections (
            user_id,
            session_id,
            raw_text,
            corrected_text,
            source
        ) VALUES ($1, $2, $3, $4, $5);
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, user_id, session_id, raw_text, corrected_text, source)
                logger.info(
                    "Logged speech correction to DB. user_id=%s, raw=%r, corrected=%r, source=%s",
                    user_id, raw_text, corrected_text, source
                )
        except Exception as e:
            logger.error("Failed to write speech correction to PostgreSQL: %s", e)

    async def fetch_user_corrections(self, user_id: uuid.UUID, limit: int = 15) -> List[str]:
        """
        Fetch the most frequently corrected terms/phrases for a given user_id.
        """
        if not self.enabled or not self.pool:
            logger.debug("Database disabled or pool not initialized. Returning empty corrections.")
            return []

        query = """
        SELECT corrected_text, COUNT(*) as count
        FROM speech_corrections
        WHERE user_id = $1
        GROUP BY corrected_text
        ORDER BY count DESC, max(created_at) DESC
        LIMIT $2;
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, user_id, limit)
                return [r["corrected_text"] for r in rows]
        except Exception as e:
            logger.error("Failed to fetch speech corrections for user_id=%s from PostgreSQL: %s", user_id, e)
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # User Authentication Methods
    # ─────────────────────────────────────────────────────────────────────────

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """Fetch user by email address."""
        if not self.pool:
            return None
        query = "SELECT * FROM users WHERE email = $1;"
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, email.lower().strip())
                return dict(row) if row else None
        except Exception as e:
            logger.error("Failed to fetch user by email: %s", e)
            return None

    async def create_user_email(self, email: str, display_name: str, password_hash: str) -> Optional[dict]:
        """Create a new user with email and password."""
        if not self.pool:
            return None
        query = """
        INSERT INTO users (email, display_name, password_hash, provider, email_verified)
        VALUES ($1, $2, $3, 'email', FALSE)
        RETURNING user_id, email, display_name, provider, email_verified, created_at;
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, email.lower().strip(), display_name, password_hash)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Failed to create email user: %s", e)
            return None

    async def verify_user_email(self, email: str) -> bool:
        """Mark a user's email as verified."""
        if not self.pool:
            return False
        query = "UPDATE users SET email_verified = TRUE WHERE email = $1;"
        try:
            async with self.pool.acquire() as conn:
                res = await conn.execute(query, email.lower().strip())
                return "UPDATE 1" in res
        except Exception as e:
            logger.error("Failed to verify user email: %s", e)
            return False

    async def upsert_google_user(self, email: str, display_name: str, avatar_url: str) -> Optional[dict]:
        """Upsert user on Google login to route to the same account by email."""
        if not self.pool:
            return None
        query = """
        INSERT INTO users (email, display_name, avatar_url, provider, email_verified)
        VALUES ($1, $2, $3, 'google', TRUE)
        ON CONFLICT (email) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
            provider = 'google',
            email_verified = TRUE,
            last_active = now()
        RETURNING user_id, email, display_name, avatar_url, provider, created_at;
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, email.lower().strip(), display_name, avatar_url)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Failed to upsert Google user: %s", e)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Session Stats & Profile Computation
    # ─────────────────────────────────────────────────────────────────────────

    async def increment_session_stats(
        self,
        user_id: uuid.UUID,
        prompt_tokens: int,
        completion_tokens: int,
        discipline: str,
        intent: str,
        active_topic: str,
        query_text: str,
        is_self_initiated: bool,
        input_flagged: bool,
        output_flagged: bool
    ) -> None:
        """Increment user stats asynchronously after every conversation turn."""
        if not self.enabled or not self.pool:
            return

        import json
        
        select_query = """
        SELECT total_turns, total_tokens_in, total_tokens_out, disciplines_hit, intent_dist, self_initiated_questions
        FROM session_stats
        WHERE user_id = $1 AND session_date = CURRENT_DATE;
        """
        
        upsert_query = """
        INSERT INTO session_stats (
            user_id,
            session_date,
            total_turns,
            total_tokens_in,
            total_tokens_out,
            disciplines_hit,
            intent_dist,
            avg_turns_per_concept,
            self_initiated_questions,
            followup_rate
        ) VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (user_id, session_date) DO UPDATE
        SET total_turns = EXCLUDED.total_turns,
            total_tokens_in = EXCLUDED.total_tokens_in,
            total_tokens_out = EXCLUDED.total_tokens_out,
            disciplines_hit = EXCLUDED.disciplines_hit,
            intent_dist = EXCLUDED.intent_dist,
            avg_turns_per_concept = EXCLUDED.avg_turns_per_concept,
            self_initiated_questions = EXCLUDED.self_initiated_questions,
            followup_rate = EXCLUDED.followup_rate;
        """
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(select_query, user_id)
                if row:
                    total_turns = row["total_turns"] + 1
                    total_tokens_in = row["total_tokens_in"] + prompt_tokens
                    total_tokens_out = row["total_tokens_out"] + completion_tokens
                    
                    disciplines_hit = row["disciplines_hit"] or []
                    if discipline not in disciplines_hit:
                        disciplines_hit.append(discipline)
                        
                    intent_dist = json.loads(row["intent_dist"]) if row["intent_dist"] else {}
                    self_initiated_questions = (row["self_initiated_questions"] or 0) + (1 if is_self_initiated else 0)
                else:
                    total_turns = 1
                    total_tokens_in = prompt_tokens
                    total_tokens_out = completion_tokens
                    disciplines_hit = [discipline]
                    intent_dist = {}
                    self_initiated_questions = 1 if is_self_initiated else 0
                
                # Update intent distribution
                intent_dist[intent] = intent_dist.get(intent, 0) + 1
                
                # Specificity word count check
                words_count = len(query_text.split())
                if words_count > 8:
                    intent_dist["long_questions"] = intent_dist.get("long_questions", 0) + 1
                
                # Useful turns check
                if not (input_flagged or output_flagged):
                    intent_dist["useful_turns"] = intent_dist.get("useful_turns", 0) + 1
                
                # Concept tracking
                prev_concept = intent_dist.get("current_concept")
                if prev_concept == active_topic:
                    intent_dist["current_concept_turns"] = intent_dist.get("current_concept_turns", 0) + 1
                else:
                    if prev_concept:
                        # previous concept resolved
                        intent_dist["resolved_concepts_count"] = intent_dist.get("resolved_concepts_count", 0) + 1
                        intent_dist["resolved_concepts_total_turns"] = intent_dist.get("resolved_concepts_total_turns", 0) + intent_dist.get("current_concept_turns", 1)
                        
                        # track by discipline
                        from agent.student_profile import TOPIC_TO_DISCIPLINE
                        prev_disp = TOPIC_TO_DISCIPLINE.get(prev_concept, "cse")
                        intent_dist[f"{prev_disp}_resolved_count"] = intent_dist.get(f"{prev_disp}_resolved_count", 0) + 1
                        intent_dist[f"{prev_disp}_resolved_turns"] = intent_dist.get(f"{prev_disp}_resolved_turns", 0) + intent_dist.get("current_concept_turns", 1)
                    
                    intent_dist["current_concept"] = active_topic
                    intent_dist["current_concept_turns"] = 1
                
                resolved_count = intent_dist.get("resolved_concepts_count", 0)
                resolved_turns = intent_dist.get("resolved_concepts_total_turns", 0)
                
                if resolved_count > 0:
                    avg_turns = float(resolved_turns) / resolved_count
                else:
                    avg_turns = float(intent_dist.get("current_concept_turns", 1))
                
                followup_rate = float(total_turns - self_initiated_questions) / total_turns
                
                await conn.execute(
                    upsert_query,
                    user_id,
                    total_turns,
                    total_tokens_in,
                    total_tokens_out,
                    disciplines_hit,
                    json.dumps(intent_dist),
                    avg_turns,
                    self_initiated_questions,
                    followup_rate
                )
                logger.info("Updated session stats for user_id=%s, date=today", user_id)
        except Exception as e:
            logger.error("Failed to update session stats for user_id=%s: %s", user_id, e)

    async def get_profile_stats(self, user_id: uuid.UUID) -> dict:
        """Compute the six required profile metrics for a given user."""
        if not self.pool:
            return {}

        import json
        import datetime

        # Helper function to compute readiness score components
        def calculate_readiness(rows_list):
            if not rows_list:
                return 0.0, {"disciplines": 0.0, "turns": 0.0, "followup": 0.0, "consistency": 0.0}
            
            all_disciplines = set()
            total_turns = 0
            total_self_initiated = 0
            valid_turns_list = []
            
            for r in rows_list:
                if r["disciplines_hit"]:
                    all_disciplines.update(r["disciplines_hit"])
                total_turns += (r["total_turns"] or 0)
                total_self_initiated += (r["self_initiated_questions"] or 0)
                if r["avg_turns_per_concept"] is not None:
                    valid_turns_list.append(r["avg_turns_per_concept"])
            
            disciplines_count = len(all_disciplines)
            avg_turns = sum(valid_turns_list) / len(valid_turns_list) if valid_turns_list else 5.0
            
            followup_rate = float(total_turns - total_self_initiated) / total_turns if total_turns > 0 else 0.0
            active_days = len(rows_list)
            
            consistency_bonus = 20.0 if active_days >= 7 else (10.0 if active_days >= 3 else 0.0)
            disciplines_score = float(disciplines_count * 8)
            turns_score = max(0.0, min(40.0, (1.0 - (avg_turns / 10.0)) * 40.0))
            followup_score = followup_rate * 20.0
            
            total_score = min(100.0, disciplines_score + turns_score + followup_score + consistency_bonus)
            return total_score, {
                "disciplines": disciplines_score,
                "turns": turns_score,
                "followup": followup_score,
                "consistency": consistency_bonus
            }

        # 1. Fetch data for readiness, interaction quality (last 30 days) and weekly comparing (last 14 days)
        query_all = """
        SELECT session_date, total_turns, total_tokens_in, total_tokens_out, disciplines_hit, intent_dist, avg_turns_per_concept, self_initiated_questions
        FROM session_stats
        WHERE user_id = $1 AND session_date >= CURRENT_DATE - 60
        ORDER BY session_date DESC;
        """
        
        try:
            async with self.pool.acquire() as conn:
                db_rows = await conn.fetch(query_all, user_id)
                rows = [dict(r) for r in db_rows]
        except Exception as e:
            logger.error("Failed to query profile stats rows: %s", e)
            rows = []

        today = datetime.date.today()

        # Split rows into intervals
        rows_30 = [r for r in rows if today - r["session_date"] <= datetime.timedelta(days=30)]
        rows_prev_30 = [r for r in rows if datetime.timedelta(days=30) < today - r["session_date"] <= datetime.timedelta(days=60)]
        
        rows_this_week = [r for r in rows if today - r["session_date"] <= datetime.timedelta(days=7)]
        rows_last_week = [r for r in rows if datetime.timedelta(days=7) < today - r["session_date"] <= datetime.timedelta(days=14)]
        
        rows_14 = [r for r in rows if today - r["session_date"] <= datetime.timedelta(days=14)]

        # --- 1. Engineering Readiness Score ---
        score_now, breakdown_now = calculate_readiness(rows_30)
        score_prev, _ = calculate_readiness(rows_prev_30)
        delta_readiness = score_now - score_prev

        # --- 2. Discipline Fingerprint ---
        disciplines = ["cse", "mech", "eee", "civil", "chemical", "aerospace"]
        total_sessions = len(rows)
        fingerprint = {}
        for d in disciplines:
            sessions_with_d = 0
            total_turns_for_d = 0.0
            resolved_count_for_d = 0
            
            for r in rows:
                if r["disciplines_hit"] and d in r["disciplines_hit"]:
                    sessions_with_d += 1
                dist = json.loads(r["intent_dist"]) if r["intent_dist"] else {}
                resolved_count_for_d += dist.get(f"{d}_resolved_count", 0)
                total_turns_for_d += dist.get(f"{d}_resolved_turns", 0)
            
            if total_sessions > 0:
                ratio = float(sessions_with_d) / total_sessions
                avg_turns_d = (total_turns_for_d / resolved_count_for_d) if resolved_count_for_d > 0 else 5.0
                # depth score = ratio weighted by concept turns normalized (e.g. capped at 1.0)
                depth = max(0.0, min(1.0, ratio * (avg_turns_d / 5.0)))
            else:
                depth = 0.0
            fingerprint[d] = round(depth, 2)

        # --- 3. Knowledge Velocity (Last 8 weeks sparkline) ---
        velocity = []
        for i in range(7, -1, -1):
            start_offset = datetime.timedelta(days=(i + 1) * 7)
            end_offset = datetime.timedelta(days=i * 7)
            week_rows = [r for r in rows if end_offset < today - r["session_date"] <= start_offset]
            
            valid_turns = [r["avg_turns_per_concept"] for r in week_rows if r["avg_turns_per_concept"] is not None]
            avg_w = sum(valid_turns) / len(valid_turns) if valid_turns else 0.0
            
            # Label
            w_date = today - end_offset
            iso_label = w_date.strftime("%G-W%V")
            velocity.append({"label": iso_label, "value": round(avg_w, 2)})

        # --- 4. Learning Phase ---
        # foundation-building, placement-prep, interview-mode, post-offer
        intents_14 = {"foundation": 0, "placement": 0, "interview": 0, "post_offer": 0}
        for r in rows_14:
            dist = json.loads(r["intent_dist"]) if r["intent_dist"] else {}
            # map intents
            intents_14["foundation"] += (dist.get("CONCEPT_EXPLANATION", 0) + dist.get("SIMPLIFY", 0) + dist.get("REPEAT_LAST", 0))
            intents_14["placement"] += (dist.get("CODE_HELP", 0) + dist.get("DEBUGGING", 0) + dist.get("CAREER_GUIDANCE", 0))
            intents_14["interview"] += dist.get("QUIZ_REQUEST", 0)
            intents_14["post_offer"] += dist.get("PROJECT_HELP", 0)

        phases = [
            ("foundation-building", intents_14["foundation"], "placement-prep"),
            ("placement-prep", intents_14["placement"], "interview-mode"),
            ("interview-mode", intents_14["interview"], "post-offer"),
            ("post-offer", intents_14["post_offer"], "post-offer")
        ]
        dominant = max(phases, key=lambda x: x[1])
        phase_label = dominant[0] if dominant[1] > 0 else "foundation-building"
        next_phase = [p[2] for p in phases if p[0] == phase_label][0]

        # --- 5. Mentor Interaction Quality (Specificity and Curiosity) ---
        def calc_quality(period_rows):
            total_turns = sum(r["total_turns"] or 0 for r in period_rows)
            total_self_initiated = sum(r["self_initiated_questions"] or 0 for r in period_rows)
            
            long_questions = 0
            for r in period_rows:
                dist = json.loads(r["intent_dist"]) if r["intent_dist"] else {}
                long_questions += dist.get("long_questions", 0)
                
            spec = float(long_questions) / total_turns if total_turns > 0 else 0.0
            curious = float(total_self_initiated) / total_turns if total_turns > 0 else 0.0
            return spec, curious

        spec_now, cur_now = calc_quality(rows_30)
        spec_prev, cur_prev = calc_quality(rows_prev_30)
        
        delta_spec = spec_now - spec_prev
        delta_cur = cur_now - cur_prev

        # --- 6. Token Usage ---
        tokens_in_this = sum(r["total_tokens_in"] or 0 for r in rows_this_week)
        tokens_out_this = sum(r["total_tokens_out"] or 0 for r in rows_this_week)
        total_tokens_this = tokens_in_this + tokens_out_this
        
        useful_turns_this = 0
        for r in rows_this_week:
            dist = json.loads(r["intent_dist"]) if r["intent_dist"] else {}
            useful_turns_this += dist.get("useful_turns", 0)
        
        efficiency_this = float(useful_turns_this) / total_tokens_this if total_tokens_this > 0 else 0.0

        tokens_in_last = sum(r["total_tokens_in"] or 0 for r in rows_last_week)
        tokens_out_last = sum(r["total_tokens_out"] or 0 for r in rows_last_week)
        total_tokens_last = tokens_in_last + tokens_out_last
        
        useful_turns_last = 0
        for r in rows_last_week:
            dist = json.loads(r["intent_dist"]) if r["intent_dist"] else {}
            useful_turns_last += dist.get("useful_turns", 0)
            
        efficiency_last = float(useful_turns_last) / total_tokens_last if total_tokens_last > 0 else 0.0

        # Fetch lifetime count
        query_lifetime = "SELECT COUNT(*), SUM(total_turns) FROM session_stats WHERE user_id = $1;"
        try:
            async with self.pool.acquire() as conn:
                life_row = await conn.fetchrow(query_lifetime, user_id)
                lifetime_sessions = life_row[0] if life_row else 0
        except Exception:
            lifetime_sessions = 0

        return {
            "readiness": {
                "score": round(score_now, 1),
                "breakdown": {k: round(v, 1) for k, v in breakdown_now.items()},
                "delta": round(delta_readiness, 1)
            },
            "fingerprint": fingerprint,
            "velocity": velocity,
            "phase": {
                "current": phase_label,
                "next": next_phase
            },
            "quality": {
                "specificity": round(spec_now, 3),
                "specificity_delta": round(delta_spec, 3),
                "curiosity": round(cur_now, 3),
                "curiosity_delta": round(delta_cur, 3)
            },
            "tokens": {
                "this_week": {
                    "in": tokens_in_this,
                    "out": tokens_out_this,
                    "efficiency": round(efficiency_this, 5)
                },
                "last_week": {
                    "in": tokens_in_last,
                    "out": tokens_out_last,
                    "efficiency": round(efficiency_last, 5)
                }
            },
            "lifetime_sessions": lifetime_sessions
        }
