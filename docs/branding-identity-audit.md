# JARVIS branding identity audit

The tracked source and product-facing UI contain no occurrences of the full
names `Videlis Ndichi` or `Videlis Ndich`. The assistant, application, and
product labels use JARVIS/JARVIS Super-Intelligence; no personal name is used
as the assistant persona or product name.

The remaining case-insensitive matches for the name variants and associated
account identifiers are not product branding. They are intentionally retained
as legal attribution, repository/account ownership, configured administrator
identity, or model/dataset provenance:

| Files | Why retained |
|---|---|
| `LICENSE` | `ndichiv-spec` is the copyright/account attribution; legal authorship is retained. |
| `docs/branding-identity-audit.md` | Literal personal-name variants appear only as search terms in this audit record, not as a product or assistant identity. |
| `docs/backend/BACKEND_UPGRADE_PLAN.md`, `docs/JARVIS_BRAIN_V1_RUNBOOK.md`, `docs/FRONTEND_UPGRADE_PLAN.md`, `docs/RECOVERY_FAILURE_MATRIX.md`, `docs/RECOVERY_RESULT.md`, `tests/test_brain_security.py`, `tests/test_security_regression.py`, `tools/_patch_live_env.py` | These contain the configured administrator email as account/security identity or an explicit test/operations fixture. It was not changed, and no credentials were copied or exposed. The historical recovery documents contain redacted password placeholders. |
| `docs/RECOVERY_FAILURE_MATRIX.md` | The Kaggle username is an account identifier, not an assistant identity. |
| `docs/JARVIS_BRAIN_V1_RUNBOOK.md`, `docs/MODEL_GATEWAY_REMOTE.md`, `docs/PHASE12_IMPLEMENTATION_MAP.md`, `silverwing-backend/model_catalog.py` | Kaggle/Hugging Face publisher handles and URLs identify existing model or dataset provenance. |
| `monitoring/kaggle/monitor_kaggle_kernel.ps1`, `monitoring/kaggle/status_history.jsonl` | The script's kernel slug is a monitoring target; the JSONL file is generated historical status/error provenance. |
| `silverwing/kaggle/fetch_audit.py`, `silverwing/kaggle/kernel-metadata-audit.json`, `silverwing/kaggle/kernel-metadata-train.json`, `silverwing/kaggle/kernel-metadata.json`, `silverwing/kaggle/train_kernel/kernel-metadata.json`, `silverwing/kaggle/train_kernel_cpu/kernel-metadata.json`, `staging/jarvis-sft-skills/dataset-metadata.json` | Kaggle kernel, dataset, and publisher identifiers are required for provenance and reproducibility. |
| `.github/workflows/production.yml`, `deployment/production/.env.example`, `deployment/production/.env.production.example`, `deployment/production/docker-compose.prod.yml`, `deployment/production/deploy.sh`, `docs/audits/JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md`, `docs/deployment/github-integration.md`, `docs/guides/development-workflow.md` | `ndichiv-spec` is the verified GitHub organization/account for this repository and its GHCR images, not a product persona. The docs now name the canonical repository without the obsolete trailing hyphen. |
| `frontend/digital_clock.py` | The clock utility's GitHub API/clone URL still names its previously configured `jarvis-cloud` repository; it is source-repository metadata, not a product title or assistant identity. It was not retargeted without evidence that this separate repository link should change. |

No usernames, email addresses, credentials, provider identifiers, or
administrator ownership settings were changed as part of the branding review.
