# PostgreSQL Migration Script
# Run this script to set up PostgreSQL for JARVIS

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "jarvis")
DB_PASSWORD = os.getenv("DB_PASSWORD", "jarvis_password")
DB_NAME = os.getenv("DB_NAME", "jarvis")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))


async def create_database():
    """Create PostgreSQL database and user"""
    
    # Connect to default postgres database
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user="postgres",
        password=os.getenv("POSTGRES_PASSWORD", "postgres")
    )
    
    try:
        # Create user if not exists
        await conn.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{DB_USER}') THEN
                    CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}';
                    ALTER ROLE {DB_USER} WITH SUPERUSER;
                END IF;
            END
            $$;
        """)
        print(f"✓ User '{DB_USER}' created or already exists")
        
        # Create database if not exists
        await conn.execute(f"""
            SELECT 'CREATE DATABASE {DB_NAME}'
            WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{DB_NAME}')
        """)
        print(f"✓ Database '{DB_NAME}' created or already exists")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()


async def run_migrations():
    """Run database migrations"""
    from core.database import init_db
    
    await init_db()
    print("✓ Database tables created")


if __name__ == "__main__":
    print("Starting PostgreSQL migration...")
    asyncio.run(create_database())
    print("\nRunning database migrations...")
    asyncio.run(run_migrations())
    print("\n✓ Migration complete!")
