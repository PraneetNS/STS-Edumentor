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

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query_table)
                await conn.execute(query_index_user)
                await conn.execute(query_index_session)
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

    async def fetch_history(self, user_id: uuid.UUID, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch the last limit records for a given user_id, ordered by created_at DESC.
        """
        if not self.enabled or not self.pool:
            logger.debug("Database disabled or pool not initialized. Returning empty history.")
            return []

        query = """
        SELECT query_text, response_text, intent_category, created_at
        FROM conversation_logs
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2;
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, user_id, limit)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Failed to fetch history for user_id=%s from PostgreSQL: %s", user_id, e)
            return []
