# JARVIS technology watch and safe platform evolution

Research snapshot: 2026-10-01. This is an internal engineering note; it does not
authorize external model training, repository writes, or production deployment.

## Findings from current vendor guidance

| Area | Verified guidance | JARVIS implication |
|---|---|---|
| MCP | The [2025-11-25 authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) describes OAuth-based authorization and protected-resource discovery for HTTP transports. The [tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) says applications should show exposed tools and invocations, and should preserve a human ability to deny calls. | Treat MCP as a protocol and authorization boundary, not a public arbitrary-command endpoint. Keep tools allowlisted, scoped, visible, audited, and confirmation-gated for consequential actions. |
| GitHub integration | [GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app) are selected by the app and should be the minimum required. The [pull request API](https://docs.github.com/en/rest/pulls/pulls) supports creating and reviewing PRs. [Actions security guidance](https://docs.github.com/en/actions/reference/security/secure-use) recommends least-privilege tokens and careful secret handling. | A future repository assistant should propose a branch/PR, run checks, and wait for human review. It must not write to the default branch, expose credentials to untrusted code, or deploy by implication. |
| Hugging Face compute | [Jobs documentation](https://huggingface.co/docs/huggingface_hub/guides/jobs) requires a positive credit balance and supports explicit job lifecycle management. [Pricing](https://huggingface.co/docs/hub/jobs-pricing) is usage-based; the published page gives GPU hardware rates. | Do not describe remote GPU jobs as free or unlimited. Require administrator-configured credentials, a spend ceiling, hardware allowlist, timeout, cancellation, artifact checks, and explicit job approval. |
| Kaggle | The [official Kaggle CLI](https://github.com/Kaggle/kaggle-cli) supports datasets, models, and notebook/kernel operations; its [user guide](https://github.com/Kaggle/kaggle-cli/blob/main/docs/README.md) requires a Kaggle account and configured API credentials. | Kaggle is a possible controlled job/data integration, not a guaranteed always-available GPU provider. This research did not establish a stable quota or free-GPU entitlement; verify current account-specific rules before promising capacity. |
| NVIDIA | [NVIDIA NIM for LLM/VLM](https://docs.nvidia.com/nim/large-language-models/latest/about-nim-llm/overview.html) is an inference microservice offering. [NeMo](https://docs.nvidia.com/nemo-framework/user-guide/latest/overview.html) is a framework for model development, customization, and training. | Keep inference and training adapters separate. NIM is not itself a free training-GPU service; NeMo still needs compute and a compatible training workflow. |

## What exists in this checkout

- `jarvis_backend/gateway.py` and `jarvis_backend/providers/` provide an existing
  provider-routing foundation. Extend that fabric rather than creating a
  parallel provider catalogue.
- `jarvis_backend/research/autonomous_research.py` contains RSS/arXiv ingestion,
  a provenance-bearing item model, semantic digestion, and database storage.
  Its broader crawler/trending capabilities are not equivalent to a bounded,
  scheduled, security-reviewed production technology monitor.
- `silverwing/training/`, `silverwing/phase1_freeze.py`,
  `silverwing/phase2_continue_pretrain.py`, and `KAGGLE_TRAINING.md` provide
  training-related code and a runbook. That does not by itself demonstrate an
  authorized remote-job lifecycle, cost controls, automatic artifact promotion,
  or a guaranteed free GPU allocation.
- `jarvis_backend/self_improvement.py` establishes a no-production-source
  mutation principle. Candidate data/model changes should preserve it.
- The execution API security tranche now requires JARVIS authentication for
  code generation/review and image generation; review reads only regular source
  files under the project root, and deployment honestly returns `501` until a
  deployment adapter exists. Image requests are bounded/rate-limited and
  Replicate polling is pinned to its API host.
- Sandbox runs are rate-limited on both API aliases and history lookups are
  owner-scoped. Mounted Silverwing tool calls require JARVIS authentication;
  code-execution tools additionally require an admin principal and an explicit
  `code_execution` grant. Standalone Silverwing operation remains separate.
- Sandbox execution remains a software sandbox rather than an OS/container
  boundary. Its recent-run index and the image/technology-watch cooldown are
  process-local; multi-worker deployments need shared rate/lock state for
  cluster-wide enforcement.
- The legacy `POST /api/v1/global/rss/refresh` endpoint previously returned
  success without ingesting anything. It now returns `501` rather than
  fabricating a refresh result.

## Implemented first vertical slice

The authenticated technology watch is intentionally advisory:

- `GET /api/v1/global/technology/updates` returns cached, provenance-tagged
  release notes for a fixed list of upstream FastAPI, MCP Python SDK, Hugging
  Face Hub, Kaggle CLI, NVIDIA NeMo, and vLLM repositories.
- Admin-only `POST /api/v1/global/technology/refresh` checks GitHub's public
  releases API for that fixed list. It accepts no URL/repository input, applies
  a six-hour cooldown with a process-local concurrency lock, limits each source
  to five stable releases, caps persisted results, and records partial source
  failures. It audits the requesting administrator and result counts without
  copying release-note bodies to the audit log. Multi-worker deployments still
  need a shared/distributed refresh lock before enabling automated polling.
- Release-note text is explicitly labeled untrusted. This component does not
  execute text, call tools, fine-tune Silverwing, modify source, open a PR, or
  deploy.
- Refresh is user-triggered, not a background scheduler. No automatic polling
  is claimed; deployment can later add an explicitly configured scheduler with
  shared locking and operational monitoring.

## Recommended evolution sequence

1. Replace process-local rate limiting and cooldowns with shared state before
   running multiple backend workers; add operational alerting for failures and
   source health.
2. Operate the advisory technology watch with audit logs and source health
   metrics. Add sources only through reviewed code changes; keep fetched text
   isolated as untrusted evidence.
3. Add a human-reviewed technology evaluation queue. Each proposal should name
   the evidence, affected JARVIS component, security/compatibility impact,
   evaluation plan, rollback, and estimated cost.
4. Add Hugging Face/Kaggle job adapters only after deployment administrators
   configure secrets in a secret manager. Enforce budgets, approved hardware,
   timeouts, cancellation, dataset/license provenance, immutable candidate
   artifacts, reproducible evaluations, and manual model promotion. Never
   require secrets to be pasted into chat or committed to the repository.
5. Add GitHub App support with minimum permissions and short-lived tokens.
   Generate reviewable branches/PRs only; require CI, code-owner approval,
   protected branches, and an explicit deployment gate.
6. Expose MCP only after transport authentication, per-user/per-tool
   authorization, egress policy, audit trails, rate/cost controls, and
   confirmation UI have been exercised in deployment tests.

## Local/upstream repository state

At the time this note was prepared, the checkout was at `7f94a58`, and its
recorded `origin/main` reference was `b0a8835`; local `HEAD` was two commits
ahead. No fetch, merge, push, or commit was performed for this work. Preserve
the existing dirty worktree and review this report and code changes before any
repository publication.
