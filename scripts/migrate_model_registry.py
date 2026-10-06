#!/usr/bin/env python3
"""Migration script for the durable Model Registry (Phase 1).

Imports model lifecycle data from:
    jarvis_data/model_lifecycle/model_lifecycle.jsonl

Into the PostgreSQL-backed models table.

Usage:
    python scripts/migrate_model_registry.py [--dry-run] [--source PATH]
    
    --dry-run    : Validate and report, don't write
    --source     : Override default source path
    --reset      : Truncate models table first (dev/test only)

This is IDEMPOTENT: re-running will UPDATE existing records by model_id
and preserve history, never duplicate or lose data.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make the project importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import the registry
from infrastructure.model_registry import (
    ModelRegistry,
    ModelInfo,
    ModelLifecycleState,
)


def load_jsonl_source(source_path: Path) -> List[Dict[str, Any]]:
    """Load model records from JSONL file."""
    if not source_path.exists():
        print(f"[migrate] ERROR: Source file not found: {source_path}")
        return []
    
    records = []
    rejected = []
    
    with open(source_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                rejected.append({
                    "line": line_num,
                    "reason": str(e),
                    "content": line[:100],
                })
    
    return records, rejected


def convert_record_to_model_info(record: Dict[str, Any]) -> ModelInfo:
    """Convert a JSONL record to ModelInfo."""
    return ModelInfo(
        id=record.get("record_id") or str(uuid.uuid4()),
        model_id=record.get("model_id", ""),
        provider_id=record.get("provider", "unknown"),
        display_name=record.get("name", ""),
        description=record.get("description", ""),
        lifecycle_type=record.get("lifecycle_type", "discovered"),
        lifecycle_status=record.get("lifecycle_stage", "discovered"),
        parent_model_id=record.get("parent_model"),
        revision=record.get("revision", ""),
        capabilities=record.get("capabilities", []),
        context_length=record.get("context_length", 0),
        max_output_tokens=record.get("max_output_tokens", 0),
        architecture=record.get("architecture", ""),
        parameters=record.get("parameters"),
        open_weights=record.get("open_weights", False),
        deployment=record.get("deployment", "local"),
        metadata=record.get("metadata", {}),
        provenance={
            "source": record.get("source"),
            "discovered_at": record.get("discovered_at"),
        },
        evaluation_results=record.get("evaluation_results", {}),
        history=record.get("history", []),
        created_at=record.get("discovered_at", time.time()),
        updated_at=time.time(),
    )


def migrate_models(
    source_path: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Migrate model records from JSONL to PostgreSQL."""
    
    # Load source data
    records, rejected = load_jsonl_source(source_path)
    
    if not records:
        return {
            "status": "error",
            "reason": "No records to migrate",
        }
    
    print(f"[migrate] Loading {len(records)} records from {source_path}")
    
    if rejected:
        print(f"[migrate] WARNING: {len(rejected)} rejected lines")
        for r in rejected[:5]:
            print(f"  Line {r['line']}: {r['reason']}")
    
    # Initialize registry
    registry = ModelRegistry.get_instance()
    
    # Track results
    imported = 0
    skipped = 0
    errors = []
    
    if not dry_run:
        # Ensure tables exist
        registry._ensure_tables()
    
    # Get existing model IDs for idempotency check
    existing_ids: set = set()
    if not dry_run:
        all_existing = registry.list_models()
        existing_ids = {m.model_id for m in all_existing}
    
    # Process each record
    for record in records:
        try:
            model_id = record.get("model_id", "")
            if not model_id:
                errors.append(f"Record missing model_id: {record.get('record_id', 'unknown')}")
                continue
            
            model_info = convert_record_to_model_info(record)
            
            if dry_run:
                print(f"[dry-run] Would migrate: {model_id} ({model_info.lifecycle_type})")
                imported += 1
            else:
                # register() does upsert
                registry.register(model_info)
                print(f"[migrate] Imported: {model_id} ({model_info.lifecycle_type})")
                imported += 1
                
        except Exception as e:
            errors.append(f"Error processing {record.get('model_id', 'unknown')}: {e}")
    
    return {
        "status": "success" if not errors else "partial",
        "total_records": len(records),
        "imported": imported,
        "rejected_lines": len(rejected),
        "errors": errors,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate model lifecycle JSONL to PostgreSQL Model Registry"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report, don't write to database",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "jarvis_data" / "model_lifecycle" / "model_lifecycle.jsonl",
        help="Source JSONL file path",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE models table before import (dev/test only)",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("MODEL REGISTRY MIGRATION")
    print("=" * 60)
    print(f"Source: {args.source}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    if args.reset and not args.dry_run:
        print("[migrate] WARNING: Resetting models table")
        from sqlalchemy import delete
        from infrastructure.model_registry import ModelRecord
        from jarvis_backend.db import get_engine
        with get_engine().begin() as conn:
            conn.execute(delete(ModelRecord))
        print("[migrate] Tables reset")
    
    result = migrate_models(args.source, dry_run=args.dry_run)
    
    print()
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Status: {result['status']}")
    print(f"Total records: {result.get('total_records', 0)}")
    print(f"Imported: {result.get('imported', 0)}")
    print(f"Rejected lines: {result.get('rejected_lines', 0)}")
    
    if result.get('errors'):
        print(f"Errors: {len(result['errors'])}")
        for err in result['errors'][:10]:
            print(f"  - {err}")
    
    return 0 if result['status'] != 'error' else 1


if __name__ == "__main__":
    sys.exit(main())