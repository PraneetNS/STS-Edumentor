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

    # Generate a temporary registered user UUID
    test_user_id = uuid.uuid4()
    test_email = f"test_migration_{test_user_id.hex[:8]}@example.com"
    print(f"Created temporary user account: {test_email} (ID: {test_user_id})")

    try:
        async with db.pool.acquire() as conn:
            # Insert the user into users table
            await conn.execute(
                "INSERT INTO users (user_id, email, display_name, provider) VALUES ($1, $2, 'Test Migrated User', 'email');",
                test_user_id,
                test_email
            )
            
            # Count current logs for this test user (should be 0)
            initial_logs = await conn.fetchval("SELECT COUNT(*) FROM conversation_logs WHERE user_id = $1;", test_user_id)
            print(f"Initial log count for new user: {initial_logs}")
            
            # Fetch profile stats - this should trigger the migration and backfill!
            print("Calling get_profile_stats for the new user...")
            stats = await db.get_profile_stats(test_user_id)
            
            # Count logs for this test user after get_profile_stats call
            final_logs = await conn.fetchval("SELECT COUNT(*) FROM conversation_logs WHERE user_id = $1;", test_user_id)
            final_stats = await conn.fetchval("SELECT COUNT(*) FROM session_stats WHERE user_id = $1;", test_user_id)
            print(f"Final log count for new user: {final_logs}")
            print(f"Final session_stats count: {final_stats}")
            
            if final_logs > 0 and final_stats > 0:
                print("\n[SUCCESS] Guest migration and backfill completed successfully!")
                print(f"Readiness Score: {stats.get('readiness', {}).get('score')}%")
                print(f"Total Sessions: {stats.get('lifetime_sessions')}")
                print(f"Tokens Used (this week): {stats.get('tokens', {}).get('this_week', {})}")
            else:
                print("\n[FAILURE] Migration was not triggered or failed to populate stats.")
                
            # Clean up the test user and restore logs/stats to a guest UUID for safety
            # (or we can keep it as is, but restoring keeps the database clean)
            guest_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO users (user_id, email, display_name, provider) VALUES ($1, $2, 'Restored Guest', 'guest');",
                guest_id,
                f"guest_{guest_id}@edumentor.local"
            )
            await conn.execute("UPDATE conversation_logs SET user_id = $1 WHERE user_id = $2;", guest_id, test_user_id)
            await conn.execute("UPDATE speech_corrections SET user_id = $1 WHERE user_id = $2;", guest_id, test_user_id)
            await conn.execute("UPDATE session_stats SET user_id = $1 WHERE user_id = $2;", guest_id, test_user_id)
            await conn.execute("DELETE FROM users WHERE user_id = $1;", test_user_id)
            print("Cleaned up and restored logs to temporary guest ID.")

    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        if db.pool:
            await db.pool.close()

if __name__ == "__main__":
    asyncio.run(main())
