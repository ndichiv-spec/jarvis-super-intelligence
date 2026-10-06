"""
JARVIS Data Migration Script
===========================
Migrate data from SQLite to PostgreSQL with enhanced features.
"""

import asyncio
import logging
import sqlite3
import asyncpg
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import uuid

logger = logging.getLogger(__name__)


class DataMigrator:
    """Data migration from SQLite to PostgreSQL"""
    
    def __init__(self, sqlite_path: str, postgres_url: str):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        self.sqlite_conn = None
        self.pg_pool = None
    
    async def initialize(self):
        """Initialize database connections"""
        # SQLite connection
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row
        
        # PostgreSQL connection pool
        self.pg_pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        
        logger.info("Database connections initialized")
    
    async def close(self):
        """Close database connections"""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        
        if self.pg_pool:
            await self.pg_pool.close()
        
        logger.info("Database connections closed")
    
    async def migrate_all(self):
        """Run complete migration"""
        try:
            await self.initialize()
            
            # Migration order matters due to foreign keys
            await self.migrate_users()
            await self.migrate_organizations()
            await self.migrate_conversations()
            await self.migrate_messages()
            await self.migrate_knowledge_documents()
            await self.migrate_tasks()
            await self.migrate_usage_analytics()
            
            logger.info("Migration completed successfully")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            await self.close()
    
    async def migrate_users(self):
        """Migrate users table"""
        logger.info("Migrating users...")
        
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for user in users:
                try:
                    await conn.execute("""
                        INSERT INTO users (
                            id, username, email, password_hash, role, 
                            first_name, last_name, avatar_url, is_active, 
                            email_verified, last_login_at, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        ON CONFLICT (username) DO NOTHING
                    """, 
                        user.get('id') or str(uuid.uuid4()),
                        user['username'],
                        user['email'],
                        user['password_hash'],
                        user.get('role', 'user'),
                        user.get('first_name'),
                        user.get('last_name'),
                        user.get('avatar_url'),
                        user.get('is_active', True),
                        user.get('email_verified', False),
                        user.get('last_login_at'),
                        user.get('created_at', datetime.now()),
                        user.get('updated_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate user {user['username']}: {e}")
        
        logger.info(f"Migrated {len(users)} users")
    
    async def migrate_organizations(self):
        """Migrate organizations table"""
        logger.info("Migrating organizations...")
        
        cursor = self.sqlite_conn.cursor()
        
        # Check if organizations table exists in SQLite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizations'")
        if not cursor.fetchone():
            logger.info("Organizations table not found in SQLite, skipping")
            return
        
        cursor.execute("SELECT * FROM organizations")
        orgs = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for org in orgs:
                try:
                    await conn.execute("""
                        INSERT INTO organizations (
                            id, name, slug, description, plan_type, 
                            max_users, max_api_calls_per_day, is_active, 
                            created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (slug) DO NOTHING
                    """,
                        org.get('id') or str(uuid.uuid4()),
                        org['name'],
                        org['slug'],
                        org.get('description'),
                        org.get('plan_type', 'free'),
                        org.get('max_users', 10),
                        org.get('max_api_calls_per_day', 1000),
                        org.get('is_active', True),
                        org.get('created_at', datetime.now()),
                        org.get('updated_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate organization {org['name']}: {e}")
        
        logger.info(f"Migrated {len(orgs)} organizations")
    
    async def migrate_conversations(self):
        """Migrate conversations table"""
        logger.info("Migrating conversations...")
        
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM conversations")
        conversations = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for conv in conversations:
                try:
                    await conn.execute("""
                        INSERT INTO conversations (
                            id, user_id, organization_id, title, status, 
                            metadata, message_count, token_count, 
                            created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (id) DO NOTHING
                    """,
                        conv.get('id') or str(uuid.uuid4()),
                        conv['user_id'],
                        conv.get('organization_id'),
                        conv.get('title'),
                        conv.get('status', 'active'),
                        json.loads(conv.get('metadata', '{}')),
                        conv.get('message_count', 0),
                        conv.get('token_count', 0),
                        conv.get('created_at', datetime.now()),
                        conv.get('updated_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate conversation {conv.get('id')}: {e}")
        
        logger.info(f"Migrated {len(conversations)} conversations")
    
    async def migrate_messages(self):
        """Migrate messages table"""
        logger.info("Migrating messages...")
        
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM messages")
        messages = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for msg in messages:
                try:
                    await conn.execute("""
                        INSERT INTO messages (
                            id, conversation_id, user_id, message_type, 
                            content, metadata, token_count, model_used, 
                            processing_time_ms, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (id) DO NOTHING
                    """,
                        msg.get('id') or str(uuid.uuid4()),
                        msg['conversation_id'],
                        msg.get('user_id'),
                        msg.get('message_type', 'user'),
                        msg['content'],
                        json.loads(msg.get('metadata', '{}')),
                        msg.get('token_count', 0),
                        msg.get('model_used'),
                        msg.get('processing_time_ms'),
                        msg.get('created_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate message {msg.get('id')}: {e}")
        
        logger.info(f"Migrated {len(messages)} messages")
    
    async def migrate_knowledge_documents(self):
        """Migrate knowledge documents table"""
        logger.info("Migrating knowledge documents...")
        
        cursor = self.sqlite_conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_documents'")
        if not cursor.fetchone():
            logger.info("Knowledge documents table not found in SQLite, skipping")
            return
        
        cursor.execute("SELECT * FROM knowledge_documents")
        docs = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for doc in docs:
                try:
                    # Generate embedding if not present (placeholder)
                    embedding = None  # Would need to generate actual embedding
                    
                    await conn.execute("""
                        INSERT INTO knowledge_documents (
                            id, user_id, organization_id, title, content, 
                            content_type, source_url, metadata, embedding, 
                            is_public, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (id) DO NOTHING
                    """,
                        doc.get('id') or str(uuid.uuid4()),
                        doc['user_id'],
                        doc.get('organization_id'),
                        doc['title'],
                        doc['content'],
                        doc.get('content_type', 'text'),
                        doc.get('source_url'),
                        json.loads(doc.get('metadata', '{}')),
                        embedding,
                        doc.get('is_public', False),
                        doc.get('created_at', datetime.now()),
                        doc.get('updated_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate document {doc.get('id')}: {e}")
        
        logger.info(f"Migrated {len(docs)} knowledge documents")
    
    async def migrate_tasks(self):
        """Migrate tasks table"""
        logger.info("Migrating tasks...")
        
        cursor = self.sqlite_conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            logger.info("Tasks table not found in SQLite, skipping")
            return
        
        cursor.execute("SELECT * FROM tasks")
        tasks = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for task in tasks:
                try:
                    await conn.execute("""
                        INSERT INTO tasks (
                            id, user_id, organization_id, task_type, status, 
                            priority, title, description, input_data, 
                            output_data, error_message, progress, 
                            started_at, completed_at, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        ON CONFLICT (id) DO NOTHING
                    """,
                        task.get('id') or str(uuid.uuid4()),
                        task['user_id'],
                        task.get('organization_id'),
                        task['task_type'],
                        task.get('status', 'pending'),
                        task.get('priority', 'medium'),
                        task.get('title'),
                        task.get('description'),
                        json.loads(task.get('input_data', '{}')),
                        json.loads(task.get('output_data', '{}')),
                        task.get('error_message'),
                        task.get('progress', 0),
                        task.get('started_at'),
                        task.get('completed_at'),
                        task.get('created_at', datetime.now()),
                        task.get('updated_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate task {task.get('id')}: {e}")
        
        logger.info(f"Migrated {len(tasks)} tasks")
    
    async def migrate_usage_analytics(self):
        """Migrate usage analytics table"""
        logger.info("Migrating usage analytics...")
        
        cursor = self.sqlite_conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usage_analytics'")
        if not cursor.fetchone():
            logger.info("Usage analytics table not found in SQLite, skipping")
            return
        
        cursor.execute("SELECT * FROM usage_analytics")
        analytics = cursor.fetchall()
        
        async with self.pg_pool.acquire() as conn:
            for record in analytics:
                try:
                    await conn.execute("""
                        INSERT INTO usage_analytics (
                            id, user_id, organization_id, api_key_id, 
                            endpoint, method, status_code, response_time_ms, 
                            tokens_used, cost, metadata, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (id) DO NOTHING
                    """,
                        record.get('id') or str(uuid.uuid4()),
                        record.get('user_id'),
                        record.get('organization_id'),
                        record.get('api_key_id'),
                        record['endpoint'],
                        record['method'],
                        record['status_code'],
                        record.get('response_time_ms'),
                        record.get('tokens_used'),
                        record.get('cost'),
                        json.loads(record.get('metadata', '{}')),
                        record.get('created_at', datetime.now())
                    )
                except Exception as e:
                    logger.warning(f"Failed to migrate analytics record {record.get('id')}: {e}")
        
        logger.info(f"Migrated {len(analytics)} analytics records")
    
    async def verify_migration(self):
        """Verify migration by comparing record counts"""
        logger.info("Verifying migration...")
        
        # Get SQLite counts
        sqlite_cursor = self.sqlite_conn.cursor()
        sqlite_counts = {}
        
        tables = ['users', 'conversations', 'messages', 'knowledge_documents', 'tasks', 'usage_analytics']
        for table in tables:
            try:
                sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                sqlite_counts[table] = sqlite_cursor.fetchone()[0]
            except sqlite3.OperationalError:
                sqlite_counts[table] = 0
        
        # Get PostgreSQL counts
        pg_counts = {}
        async with self.pg_pool.acquire() as conn:
            for table in tables:
                try:
                    result = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    pg_counts[table] = result
                except Exception:
                    pg_counts[table] = 0
        
        # Compare counts
        logger.info("Migration verification results:")
        for table in tables:
            sqlite_count = sqlite_counts[table]
            pg_count = pg_counts[table]
            status = "✓" if sqlite_count == pg_count else "✗"
            logger.info(f"{status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        
        return sqlite_counts, pg_counts


async def run_migration():
    """Run the complete migration"""
    import os
    from core.config import settings
    
    # Configuration
    sqlite_path = "./jarvis.db"  # Path to SQLite database
    postgres_url = settings.DATABASE_URL.replace("sqlite+aiosqlite://", "postgresql://")
    
    if not postgres_url:
        raise ValueError("PostgreSQL URL not configured")
    
    # Run migration
    migrator = DataMigrator(sqlite_path, postgres_url)
    
    try:
        await migrator.migrate_all()
        await migrator.verify_migration()
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_migration())
