#!/usr/bin/env python
"""Migration status investigation."""
import os
import sys
sys.path.insert(0, r'F:/AI/Jarvis-super-intelligence-')

from sqlalchemy import create_engine, text, inspect, select, func
from jarvis_backend.db import database_url

# Don't print the full URL, just check it
db_url = database_url()
print("Database URL type: PostgreSQL" if 'postgresql' in db_url else "Other")

engine = create_engine(db_url)
inspector = inspect(engine)

print("\n=== EXISTING TABLES ===")
for table in inspector.get_table_names():
    cols = [c['name'] for c in inspector.get_columns(table)]
    print(f"{table}: {cols[:10]}{'...' if len(cols) > 10 else ''}")

print("\n=== MODELS TABLE ROW COUNT ===")
with engine.connect() as conn:
    try:
        result = conn.execute(select(func.count()).select_from(text('models')))
        count = result.scalar()
        print(f"models table: {count} rows")
        
        # Sample records
        result = conn.execute(text('SELECT model_id, provider_id, lifecycle_status FROM models LIMIT 3'))
        print("\nSample records:")
        for row in result:
            print(f"  {row}")
    except Exception as e:
        print(f"Error: {e}")

print("\n=== PHASE 2 TABLE STATUS ===")
print("Required Phase 2 tables: models, providers, artifacts, jobs, usage_costs, audit_events")
print("Currently exist:", [t for t in inspector.get_table_names() if t in ['models', 'providers', 'artifacts', 'jobs', 'usage_costs', 'audit_events']])
print("Missing tables:", [t for t in ['models', 'providers', 'artifacts', 'jobs', 'usage_costs', 'audit_events'] if t not in inspector.get_table_names()])