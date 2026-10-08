#!/usr/bin/env python
"""
JSONL to PostgreSQL Model Registry Migration Script.

Safely imports model records from jarvis_data/model_lifecycle/model_lifecycle.jsonl
into the PostgreSQL Model Registry.

Phase 2 compliance:
- Handles new fields: model_family, modalities, context_window, deployment_type,
  endpoint_reference, artifact_reference, checksum, training_run_id, dataset_id
- Supports blocked lifecycle state
- Full provenance chain preservation

Usage:
    python -m infrastructure.migration.import_jsonl_models
    python -m infrastructure.migration.import_jsonl_models --dry-run  # Preview without writing
    python -m infrastructure.migration.import_jsonl_models --reset   # Clear existing models first
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Ensure repo root is on sys.path for imports
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_jsonl_records(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load and parse JSONL file, returning list of record dicts."""
    records = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid JSON on line {line_num}: {e}")
    return records


def validate_record(record: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate a single JSONL record.
    
    Returns (is_valid, error_message).
    """
    required_fields = ['provider', 'model_id']
    
    for field in required_fields:
        if field not in record or not record[field]:
            return False, f"Missing required field: {field}"
    
    return True, None


def jsonl_to_model_info(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSONL record fields to ModelInfo-compatible dict.
    
    Mapping:
        record_id -> id
        model_id -> model_id
        provider -> provider_id
        name -> display_name
        revision -> revision
        capabilities -> capabilities
        metadata -> metadata
        evaluation_results -> evaluation_results
        history -> history
        discovered_at -> created_at (when set)
        
    Phase 2 additions:
        family -> model_family
        artifact_uri -> artifact_reference
        checksum -> checksum
        training_run_id -> training_run_id
        dataset_ids -> dataset_id (first if list)
    """
    # Parse timestamp if present
    discovered_at = record.get('discovered_at')
    created_at = discovered_at if discovered_at else time.time()
    
    # Import the lifecycle mapper
    from infrastructure.model_registry import jsonl_to_lifecycle_status
    lifecycle_status = jsonl_to_lifecycle_status(record)
    
    # Map lifecycle_type from JSONL format
    lifecycle_type_map = {
        'jarvis_base': 'discovered',
        'jarvis_candidate': 'candidate',
        'jarvis_sft': 'candidate',
        'local_model': 'discovered',
        'external': 'registered',
    }
    jsonl_lifecycle_type = record.get('lifecycle_type', 'discovered')
    lifecycle_type = lifecycle_type_map.get(jsonl_lifecycle_type, 'discovered')
    
    # Extract provenance
    parent_model = record.get('parent_model')
    
    # Handle dataset_ids (list) -> dataset_id (take first)
    dataset_ids = record.get('source_dataset_ids', [])
    dataset_id = dataset_ids[0] if isinstance(dataset_ids, list) and dataset_ids else None
    
    return {
        'id': record.get('record_id', str(uuid.uuid4())),
        'model_id': record['model_id'],
        'provider_id': record['provider'],
        'display_name': record.get('name', ''),
        'description': record.get('description', ''),
        'model_family': record.get('family', ''),
        'lifecycle_type': lifecycle_type,
        'lifecycle_status': lifecycle_status,
        'parent_model_id': parent_model,
        'revision': record.get('revision', ''),
        'capabilities': record.get('capabilities', []),
        'modalities': record.get('modalities', ['text']),
        'context_window': record.get('context_length', 0),
        'max_output_tokens': record.get('max_output_tokens', 0),
        'architecture': record.get('architecture', ''),
        'parameters': record.get('parameters'),
        'open_weights': record.get('open_weights', False),
        'deployment_type': record.get('deployment', 'local'),
        'endpoint_reference': '',  # Will be filled if available in extension
        'artifact_reference': record.get('artifact_uri', ''),
        'checksum': record.get('checksum', ''),
        'source': record.get('source', ''),
        'training_run_id': record.get('training_run_id', ''),
        'dataset_id': dataset_id or '',
        'evaluation_results': record.get('evaluation_results', {}),
        'metadata': record.get('metadata', {}),
        'provenance': _build_provenance(record),
        'history': record.get('history', []),
        'created_at': created_at,
        'updated_at': created_at,
    }


def _build_provenance(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build the provenance chain from JSONL record."""
    provenance = {}
    
    # Source information
    if record.get('source'):
        provenance['source_provider'] = record['source']
    
    # Parent/base model relationship
    if record.get('parent_model'):
        provenance['parent_model'] = record['parent_model']
    
    # Training run
    if record.get('training_run_id'):
        provenance['training_run_id'] = record['training_run_id']
    
    # Dataset relationship
    if record.get('source_dataset_ids'):
        provenance['dataset_ids'] = record['source_dataset_ids']
    
    # Evaluation results
    if record.get('evaluation_results'):
        provenance['evaluation_results'] = record['evaluation_results']
    
    # Brain full ID
    if record.get('metadata', {}).get('brain_full_id'):
        provenance['brain_id'] = record['metadata']['brain_full_id']
    
    return provenance


def migrate_jsonl(
    jsonl_path: Path,
    dry_run: bool = False,
    reset_existing: bool = False,
) -> Dict[str, Any]:
    """Migrate JSONL records to PostgreSQL Model Registry.
    
    Returns migration statistics:
        - total_records: number of records in JSONL
        - valid_records: number of records that passed validation
        - imported: number of records imported (or would be imported in dry-run)
        - skipped: number of records skipped (duplicate with same data)
        - rejected: list of rejected records with errors
    """
    from infrastructure.model_registry import ModelInfo, ModelRegistry
    from sqlalchemy import text
    
    registry = ModelRegistry.get_instance()
    
    stats = {
        'total_records': 0,
        'valid_records': 0,
        'imported': 0,
        'skipped': 0,
        'rejected': [],
        'duplicates_found': 0,
    }
    
    # Load JSONL records
    records = load_jsonl_records(jsonl_path)
    stats['total_records'] = len(records)
    
    if dry_run:
        logger.info(f"DRY RUN: Would process {len(records)} records from {jsonl_path}")
    
    if reset_existing:
        # Delete all existing models (safe - we're migrating fresh data)
        if not dry_run:
            engine = registry._get_engine()
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM models"))
                count = result.scalar()
                logger.info(f"Found {count} existing models in database")
                with engine.begin() as begin_conn:
                    begin_conn.execute(text("DELETE FROM models"))
                logger.info(f"Reset existing models")
    
    # Process each record
    for idx, record in enumerate(records, 1):
        stats['valid_records'] += 1
        
        # Validate
        is_valid, error = validate_record(record)
        if not is_valid:
            stats['rejected'].append({
                'index': idx,
                'record': record,
                'error': error,
            })
            continue
        
        # Convert to ModelInfo format
        model_data = jsonl_to_model_info(record)
        
        # Check for existing model (by model_id)
        existing = registry.get(model_data['model_id'])
        if existing:
            # Check if data is the same (idempotency)
            if (existing.id == model_data.get('id') and
                existing.provider_id == model_data['provider_id'] and
                existing.lifecycle_status == model_data['lifecycle_status']):
                stats['skipped'] += 1
                continue
            else:
                stats['duplicates_found'] += 1
        
        if dry_run:
            logger.info(f"DRY RUN: Would import {model_data['model_id']} ({record.get('record_id', 'no-id')})")
            stats['imported'] += 1
            continue
        
        # Import
        model_info = ModelInfo(
            id=model_data['id'],
            model_id=model_data['model_id'],
            provider_id=model_data['provider_id'],
            display_name=model_data['display_name'],
            description=model_data['description'],
            model_family=model_data['model_family'],
            lifecycle_type=model_data['lifecycle_type'],
            lifecycle_status=model_data['lifecycle_status'],
            parent_model_id=model_data['parent_model_id'],
            revision=model_data['revision'],
            capabilities=model_data['capabilities'],
            modalities=model_data['modalities'],
            context_window=model_data['context_window'],
            max_output_tokens=model_data['max_output_tokens'],
            architecture=model_data['architecture'],
            parameters=model_data['parameters'],
            open_weights=model_data['open_weights'],
            deployment_type=model_data['deployment_type'],
            endpoint_reference=model_data['endpoint_reference'],
            artifact_reference=model_data['artifact_reference'],
            checksum=model_data['checksum'],
            source=model_data['source'],
            training_run_id=model_data['training_run_id'],
            dataset_id=model_data['dataset_id'],
            metadata=model_data['metadata'],
            provenance=model_data['provenance'],
            evaluation_results=model_data['evaluation_results'],
            history=model_data['history'],
            created_at=model_data['created_at'],
            updated_at=model_data['updated_at'],
        )
        
        registry.register(model_info)
        stats['imported'] += 1
        
        if stats['imported'] % 10 == 0:
            logger.info(f"Imported {stats['imported']} models...")
    
    # Final count
    all_models = registry.list_models()
    logger.info(f"Migration complete. Total models in registry: {len(all_models)}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Migrate model records from JSONL to PostgreSQL Model Registry'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migration without writing to database'
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Reset existing models before import (DESTRUCTIVE)'
    )
    parser.add_argument(
        '--jsonl-path',
        type=str,
        default=None,
        help='Path to JSONL file (default: jarvis_data/model_lifecycle/model_lifecycle.jsonl)'
    )
    
    args = parser.parse_args()
    
    # Determine JSONL path
    if args.jsonl_path:
        jsonl_path = Path(args.jsonl_path)
    else:
        # Find the model_lifecycle.jsonl in the project
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        jsonl_path = project_root / 'jarvis_data' / 'model_lifecycle' / 'model_lifecycle.jsonl'
    
    if not jsonl_path.exists():
        # Try alternate location
        jsonl_path = Path(__file__).resolve().parent.parent.parent / 'model_lifecycle.jsonl'
    
    if not jsonl_path.exists():
        logger.error(f"JSONL file not found: {jsonl_path}")
        sys.exit(1)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    
    stats = migrate_jsonl(
        jsonl_path,
        dry_run=args.dry_run,
        reset_existing=args.reset,
    )
    
    print("\nMigration Summary:")
    print(f"  Total records in JSONL: {stats['total_records']}")
    print(f"  Valid records: {stats['valid_records']}")
    print(f"  Imported: {stats['imported']}")
    print(f"  Skipped (unchanged): {stats['skipped']}")
    print(f"  Duplicates (different data): {stats['duplicates_found']}")
    print(f"  Rejected: {len(stats['rejected'])}")
    
    if stats['rejected']:
        print("\nRejected records:")
        for r in stats['rejected']:
            print(f"  - Index {r['index']}: {r['error']}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())