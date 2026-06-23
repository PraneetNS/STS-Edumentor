import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load env configurations from backend/.env
load_dotenv(dotenv_path='backend/.env')

async def main():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    database = os.getenv("POSTGRES_DB", "edumentor")

    print(f"Connecting to PostgreSQL at {host}:{port}/{database}...")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        # Fetch the 10 most recent logs
        rows = await conn.fetch(
            "SELECT id, query_text, response_text, created_at FROM conversation_logs ORDER BY created_at DESC LIMIT 10;"
        )
        
        if not rows:
            print("\nNo conversation logs found in the 'conversation_logs' table.")
        else:
            print(f"\n--- Last 10 Conversation Logs in PostgreSQL ({database}) ---")
            for r in rows:
                print(f"\n[ID: {r['id']} | Date: {r['created_at']}]")
                print(f"Student: {r['query_text']}")
                print(f"Edi:     {r['response_text']}")
                print("-" * 75)
                
        await conn.close()
    except Exception as e:
        print(f"\n[ERROR] Could not connect to PostgreSQL database: {e}")
        print("Please check that:")
        print("1. Your PostgreSQL server is running.")
        print(f"2. A database named '{database}' has been created.")
        print("3. Your credentials in backend/.env match your Postgres setup.")

if __name__ == '__main__':
    asyncio.run(main())
