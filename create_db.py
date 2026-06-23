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

    print(f"Connecting to default 'postgres' database on {host}:{port} to create '{database}' database if missing...")

    try:
        # Connect to the default 'postgres' database
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres"
        )
        
        # Check if the database already exists
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1);",
            database
        )
        
        if not exists:
            # CREATE DATABASE cannot be executed in a transaction.
            # asyncpg connection.execute runs in a transaction if we are not careful,
            # but conn.execute() actually executes the query directly if it's a single query.
            # Let's execute it directly.
            print(f"Database '{database}' does not exist. Creating database '{database}'...")
            await conn.execute(f'CREATE DATABASE "{database}";')
            print(f"Database '{database}' successfully created!")
        else:
            print(f"Database '{database}' already exists.")
            
        await conn.close()
    except Exception as e:
        print(f"\n[ERROR] Failed to setup database: {e}")
        print("Please verify that PostgreSQL is running and credentials in backend/.env are correct.")

if __name__ == '__main__':
    asyncio.run(main())
