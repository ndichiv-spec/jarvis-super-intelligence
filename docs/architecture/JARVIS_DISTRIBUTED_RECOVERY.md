# JARVIS Distributed Recovery Architecture

**Version:** Phase 1  
**Date:** 2026-10-01  
**Purpose:** Enable disaster recovery without requiring 40GB local copies

---

## 1. RECOVERY PRINCIPLES

### 1.1 Authority Separation
Large artifacts remain in their appropriate systems:
- Model weights → Object storage
- Datasets → HuggingFace/Kaggle/Cloud storage
- Training outputs → Designated artifact storage
- Local checkpoints → Referenceable, not copied

JARVIS maintains:
- Source code (git repository)
- Database schema (migrations)
- Configuration schema (schema definitions)
- Identity (user accounts, roles)
- Connector definitions (interface contracts)
- Model registry (metadata, references, hashes)
- Artifact references (not artifacts themselves)
- Model hashes (integrity verification)
- Dataset manifests (metadata only)
- Learning lineage (provenance tracking)
- Deployment definitions (what to deploy)
- Bootstrap procedures (recovery steps)
- Health validation (verification checks)
- Rollback procedures (versioned reversibility)

---

## 2. PRESERVABLE ARTIFACTS

### 2.1 Source Code
```
Location: Git repository (F:/AI is the working copy)
Recovery: git clone + pip install
```

### 2.2 Database Schema
```
Location: jarvis_backend/db.py (SQLAlchemy)
Migrations: Alembic-based future migration system
Recovery: Recreate schema from SQLAlchemy models
```

### 2.3 Configuration Schema
```
Location: Various .py configuration modules
Recovery: Default configuration + environment overrides
```

### 2.4 Platform Identity
```
Location: jarvis_data/jarvis.db (SQLite)
Collections: users, sessions, api_keys, oauth_identities, settings
Recovery: Seed script + database restore
```

### 2.5 Connector Definitions
```
Location: providers/ + jarvis_backend/connectors/
Recovery: Import from source code
```

### 2.6 Model Registry
```
Location: providers/models.py + runtime state
Tables: model_id, provider, version, family, artifact_location, artifact_hash
Recovery: Registry from provider models + Silverwing catalog
```

### 2.7 Artifact References
```
Location: ModelRegistry.artifact_location + training logs
Format: URI to artifact storage (S3, GCS, HF Hub, local path)
Recovery: Re-fetch from URIs
```

### 2.8 Model Hashes
```
Location: Training logs, model catalog
Format: SHA256 or MD5 checksums
Recovery: Verify artifact integrity
```

### 2.9 Dataset Manifests
```
Location: Dataset configuration files
Format: JSON manifest with source URIs
Recovery: Re-download from source URIs
```

### 2.10 Learning Lineage
```
Location: Training artifacts, experiment logs
Format: DAG of Lesson → Training Run → Model
Recovery: Reconstruct from logs
```

### 2.11 Deployment Definitions
```
Location: Configuration YAML + model registry states
Recovery: Re-apply deployment targets
```

### 2.12 Bootstrap Procedures
```
Location: docs/architecture/*.md + scripts
Recovery: Execute bootstrap sequence
```

### 2.13 Health Validation
```
Location: providers/health.py + platform health endpoints
Recovery: Probe all components
```

### 2.14 Rollback Procedures
```
Location: Model registry active/candidate/deprecated states
Recovery: Promote candidate → active
```

---

## 3. BACKUP STRATEGY

### 3.1 Critical Data (Frequent Backups)
```
Daily:
- jarvis_data/jarvis.db (SQLite database)
- jarvis_config.json (configuration)
- platform_identity.json (identity state)

Weekly:
- Full database dump
- Audit log archive
- Model deployment states
```

### 3.2 Artifact References (Versioned)
```
Version Control:
- Training configurations
- Model registry entries
- Dataset manifests
- Experiment definitions
```

### 3.3 Logs (Append Only)
```
Location: Logs directory
Retention: 30 days rolling
Archive: Compressed monthly
```

---

## 4. BOOTSTRAP PROCEDURE

### 4.1 Fresh Machine Bootstrap
```
1. git clone <repository>
2. pip install -e .
3. Set environment variables:
   - JARVIS_SECRET_KEY
   - Database URLs (optional)
   - Provider API keys (via secrets manager)
4. Initialize database:
   python -c "from jarvis_backend.db import create_db_and_tables; create_db_and_tables()"
5. Start platform:
   python start_jarvis.py
6. Verify health:
   curl http://localhost:8000/health
```

### 4.2 Disaster Recovery Steps
```
Step 1: Restore Source Code
- Clone latest repository
- Install dependencies

Step 2: Restore Identity
- Import users from backup
- Restore API keys
- Reconfigure roles

Step 3: Restore Configuration
- Import settings
- Reconnect providers

Step 4: Restore Model References
- Re-register models from catalog
- Verify artifact URIs
- Update deployment states

Step 5: Verify Health
- Run health probes
- Validate connectivity
- Check provider availability
```

---

## 5. MODEL LINEAGE TRACKING

### 5.1 Lineage Chain
```
Lesson
  ↓
Approved Dataset (manifest, hash, source)
  ↓
Training Run (config, hyperparameters, output)
  ↓
Candidate Model (artifact_uri, checksum, evaluation)
  ↓
Evaluation (metrics, test results, ranking)
  ↓
Model Registry (active/candidate/deprecated)
  ↓
Deployment (target, version, status)
  ↓
Active Model (currently serving)
```

### 5.2 Registry States
```
UNCONFIGURED → AVAILABLE → READY → ACTIVE
                      ↘         ↗
                       → DEGRADED → OFFLINE
                      ↘         ↗
                       → UNAVAILABLE
```

---

## 6. DATA PROVENANCE

### 6.1 Dataset Provenance Record
```json
{
  "dataset_id": "wiki-explore-2024",
  "source_uri": "s3://kaggle-datasets/wiki-explore",
  "manifest_hash": "sha256:abc123...",
  "size_bytes": 1234567890,
  "lineage": [
    "source:kaggle",
    "download:2024-01-15",
    "checksum:sha256:def456..."
  ],
  "provenance_hash": "sha256:xyz789..."
}
```

### 6.2 Training Provenance Record
```json
{
  "training_id": "silverwing-120m-r1",
  "dataset_ids": ["wiki-explore-2024", "arxiv-2024"],
  "hyperparameters": {...},
  "output_uri": "s3://models/silverwing-120m-r1",
  "artifact_hash": "sha256:pqr456...",
  "evaluation_id": "eval-r1-passed",
  "lineage": [
    "experiment:silverwing-120m",
    "training:2024-02-01",
    "checkpoint:r1"
  ]
}
```

---

## 7. ROLLBACK PROCEDURES

### 7.1 Model Rollback
```
1. Identify candidate version with passing evaluations
2. Mark as "ready" (pending promotion)
3. Verify artifact availability
4. Promote candidate → active
5. Monitor health
6. Rollback if issues detected
```

### 7.2 Configuration Rollback
```
1. Retrieve previous configuration version
2. Validate against schema
3. Apply to runtime
4. Verify health
5. Notify monitoring
```

### 7.3 Deployment Rollback
```
1. Identify previous deployment version
2. Verify rollback path exists
3. Execute deployment rollback
4. Validate service health
5. Update model registry state
```

---

## 8. HEALTH VERIFICATION

### 8.1 Component Verification Checklist
```
[ ] Source code accessible (git status)
[ ] Database schema valid (migration status)
[ ] Identity restored (admin login works)
[ ] Configurations loaded (no defaults)
[ ] Models registered (registry populated)
[ ] Connectors active (health probes pass)
[ ] Providers available (real endpoints)
[ ] AI service enabled (ai_enabled=True)
[ ] Platform healthy (all checks pass)
```

### 8.2 Verification Commands
```bash
# Verify source
git status

# Verify database
python -c "from jarvis_backend.db import check_db; print(check_db())"

# Verify identity
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d '{"email":"admin","password":"..."}'

# Verify models
curl http://localhost:8000/api/v1/models

# Verify health
curl http://localhost:8000/api/v1/system/health

# Verify providers
curl http://localhost:8000/api/v1/provider-status
```

---

## 9. RECOVERY DOCUMENTATION

### 9.1 Required Documentation
```
docs/architecture/JARVIS_CURRENT_PLATFORM_MAP.md  ✓ Phase 1
docs/architecture/PHASE1_IMPLEMENTATION_PLAN.md   ✓ Phase 1
docs/architecture/JARVIS_DISTRIBUTED_RECOVERY.md ✗ To create
docs/architecture/MODEL_LINEAGE.md                ✗ Future
docs/architecture/DATA_PROVENANCE.md                ✗ Future
docs/architecture/BOOTSTRAP_GUIDE.md               ✗ Future
```

### 9.2 Bootstrap Guide Template
```
# JARVIS Bootstrap Guide

## Prerequisites
- Python 3.13+
- Node.js 20+
- Git
- Environment variables

## Installation
1. Clone repository
2. Install Python dependencies
3. Install frontend dependencies
4. Set environment variables
5. Initialize database
6. Configure providers
7. Start services
8. Verify health

## Recovery Scenarios
### Fresh Install
Steps: 1-8

### Database Only Recovery
Steps: 1-5 + import database dump

### Model Recovery
Steps: Restore registry + verify artifacts

### Full Disaster Recovery
All steps with additional artifact restoration
```

---

## 10. IMPLEMENTATION TASKS

### 10.1 Create Recovery Registry
- [ ] Create `jarvis_backend/recovery.py`
- [ ] Implement manifest storage
- [ ] Add provenance tracking
- [ ] Implement verification checks

### 10.2 Create Bootstrap Service
- [ ] Create `jarvis_backend/bootstrap.py`
- [ ] Implement identity seeding
- [ ] Implement configuration loading
- [ ] Add health verification

### 10.3 Create Recovery API
- [ ] Create `jarvis_backend/routers/recovery.py`
- [ ] Add recovery status endpoint
- [ ] Add bootstrap endpoint
- [ ] Add rollback endpoint

### 10.4 Create Documentation
- [ ] Complete BOOTSTRAP_GUIDE.md
- [ ] Complete MODEL_LINEAGE.md
- [ ] Complete DATA_PROVENANCE.md

---

## 11. VALIDATION

### 11.1 Recovery Test Scenarios
```
Scenario 1: Fresh Machine Setup
- Clone repo on new machine
- Run bootstrap
- Verify all services
- Test AI functionality

Scenario 2: Database Recovery
- Delete database
- Restore from backup
- Verify data integrity
- Test identity access

Scenario 3: Model Recovery
- Delete model artifacts
- Re-register from registry
- Verify artifact fetch
- Test inference
```

---

*Part of Phase 1 Implementation Plan*