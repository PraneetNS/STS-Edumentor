import asyncio
import asyncpg
import uuid
import sys
import os

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from config import Config
from agent.database import DatabaseManager

async def main():
    db = DatabaseManager()
    await db.initialize()
    if not db.pool:
        print("Failed to initialize database pool.")
        return

    try:
        async with db.pool.acquire() as conn:
            # 1. Get all unique user IDs from conversation_logs
            rows = await conn.fetch("SELECT DISTINCT user_id FROM conversation_logs;")
            user_ids = [r["user_id"] for r in rows]
            print(f"Found {len(user_ids)} users with conversation logs.")

            for uid in user_ids:
                print(f"Backfilling user {uid}...")
                await db.backfill_session_stats_from_logs(uid)

            # 2. Check session_stats counts
            print("\n--- Updated Session Stats Summary ---")
            stats = await conn.fetch("SELECT user_id, COUNT(*), SUM(total_turns) FROM session_stats GROUP BY user_id;")
            for s in stats:
                print(dict(s))
                
    except Exception as e:
        print(f"Error during backfill run: {e}")
    finally:
        if db.pool:
            await db.pool.close()

if __name__ == "__main__":
    asyncio.run(main())
