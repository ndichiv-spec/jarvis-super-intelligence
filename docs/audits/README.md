# docs/audits/README.md — tracking, verifying, and closing findings

This directory holds the **JARVIS audit** materials and the process for keeping
them current. Coding agents must read `../../AUDIT.md` and this file before
touching audited components.

## Files in this directory

| File | Purpose |
|------|---------|
| `initial-audit-report.md` | The **master** original audit report, preserved **byte-for-byte** (verbatim copy of `JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md`). Read this first for the full blocker matrix and verification ledger. |
| `JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md` | Verbatim original: blocker matrix + verification ledger (same content as `initial-audit-report.md`). |
| `JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` | Verbatim original: code-overlap & entry-point audit. |
| `JARVIS_DEPLOYMENT_AND_PORTLESS_ACCESS.md` | Verbatim original: deployment/compose/Caddy assessment. |
| `JARVIS_EXTERNAL_SERVICE_CAPABILITY_MATRIX.md` | Verbatim original: per-service matrix + dependency alerts. |
| `JARVIS_GIT_HISTORY_RECONCILIATION.md` | Verbatim original: history reconciliation plan. |
| `JARVIS_INTEGRATION_TEST_AND_RELEASE_EVIDENCE.md` | Verbatim original: test evidence & release gate. |
| `JARVIS_OWNER_ONLY_SECURITY_MODEL.md` | Verbatim original: auth/security model. |
| `JARVIS_SUPABASE_AND_SERVICE_FABRIC_BASELINE.md` | Verbatim original: DB/secret/storage boundaries. |
| `JARVIS_WORLD_WORKSPACE_AND_AI_COOPERATION.md` | World-Workspace audit (revised in this tree; see `audited-baseline.md`). |
| `audited-baseline.md` | Precise baseline & limitations (authoritative for this tree). |

> The eight `JARVIS_*.md` reports above (plus `initial-audit-report.md`) are
> **byte-for-byte copies** of the originals authored for the JARVIS recovery.
> They are intentionally not rewritten here so that future agents can cite the
> original evidence verbatim. `AUDIT.md` (repo root) is the *synthesized,
> prioritized* findings list that ties them to actionable work in this tree.

## How findings are tracked

1. **Source of truth:** `AUDIT.md` (repo root) contains the tracking table with
   a stable ID (`P1-1`, `P2-3`, …), priority, short description, status, and
   evidence for each finding.
2. **Priority bands** (mirrors the mission):
   - **P1 — Critical/operational** (auth, secrets, clean-clone, entry points,
     code duplication).
   - **P2 — Medium** (syntax/compile, import safety, dependency reproducibility,
     vulnerability alerts).
   - **P3 — Hygiene/visibility** (secret scanning, env hygiene).
3. **Status values:**
   - ✅ **FIXED** — only when a test or check proves it in *this* tree.
   - 📄 **DOCUMENTED** — addressed upstream/in the platform checkout, not here;
     preserved as a known constraint.
   - ⚠️ **OPEN** — not yet remediated; work blocked or out of scope.
   - ❓ **NOT VERIFIED HERE** — claimed elsewhere but not reproducible in this
     environment.

## How findings are verified

Every status change requires **evidence captured in this tree**, e.g.:

- Compilation: `python -m py_compile <file>` (exit 0).
- Collection: `python -m pytest --collect-only -q` (exit 0, item count).
- Regression: `python -m pytest tests/test_audit_guard.py -q` (green).
- Targeted: `python -m pytest tests/<scoped>.py -q -m "not integration"`.
- Secret scan: regex over tracked source + `git log --all -p` history
  (no real credentials; AWS-pattern fixtures = documented example keys).
- Dependency scan: `python -m pip_audit` where network allows (see P2-5).

> **Rule:** a finding is never closed solely because documentation was added.
> `DIAGRAM.md`-style claims ("auth is fixed") without a green test are not
> accepted. If a check cannot run in this environment, say so and keep the
> finding **OPEN**.

## How findings are closed

1. Make the minimal, in-place source change that resolves the finding (fix in
   the relevant package; do **not** create a disconnected replacement file).
2. Add or extend a regression test under `tests/` (the audit guard
   `tests/test_audit_guard.py` pins the most security-critical invariants).
3. Run the check in §"How findings are verified" and confirm it is green.
4. In `AUDIT.md`, flip the status to ✅ FIXED and cite the exact check + test.
5. If the fix cannot be verified here, keep the finding ⚠️ OPEN and explain
   why, including what environment/credentials are required.

## Closing a finding requires agent action
- Do **not** mark a finding resolved because docs were written.
- Do **not** refactor broadly outside the finding's scope.
- Do **not** deploy to production, rotate real credentials, or mutate
  external infrastructure without explicit authorization.

See `audited-baseline.md` for what counts as authoritative evidence in this
workspace, and `../../docs/JARVIS_PHASE1_AUDIT.md` and `../../docs/PHASE9_AUDIT.md`
for the architectural mapping of the brain/provider/backends side of JARVIS.
