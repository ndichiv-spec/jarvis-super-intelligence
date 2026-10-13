# Autonomous Runtime Slice

## Existing components reused

Capability requests continue through the authenticated conversation, World
Resolver, canonical capability contracts, `ToolRegistry`, Plan Validator, and
durable command/event path. The current discovery catalogue describes registered
capabilities; it does not install discovered code or grant new authority.

The code-candidate workflow extends the existing self-improvement API and uses
the project test runner. `POST /api/v1/improvements/code-candidates` is
admin-authenticated. It takes a reproducible problem, evidence, a proposed
change, complete replacement contents for existing Python source files, and
existing test-file paths. It creates a filtered filesystem copy, runs the same
fixed pytest targets before and after the change, records the diff and results,
and writes the candidate source files plus a versioned JSON report under
`JARVIS_CANDIDATE_ROOT` (default: the runtime data directory). Reports are
owner-scoped. `GET /api/v1/improvements/code-candidates/{candidate_id}` reads
only the caller's report.

Candidate writes are limited to existing Python files in supported source
roots. Test files, credentials, provider code, authorization/runtime boundaries,
and promotion controls are protected. Test selectors must name existing Python
files under a `tests` directory. The subprocess command is fixed to
`python -m pytest`, has a bounded timeout, removes credential-shaped
environment variables, disables the cache provider, and points test databases
to temporary paths. A passing candidate is only recommended for owner review
when the same tests fail on the baseline. No endpoint promotes or deploys it.

## Isolation and release gates

The candidate gets an ephemeral isolated filesystem workspace and separate
temporary baseline/candidate test databases; only the changed candidate files
and report remain under the configured artifact volume. The active source
checkout and its tracked test database are not written.
This is **not** an OS sandbox: candidate tests execute as the JARVIS process
user and network access is not technically disabled. Only trusted project
changes should be evaluated this way. Do not run downloaded adapters or other
untrusted code with this runner.

The report records the baseline result, candidate result, evidence, diff,
candidate version, owner reference, and recovery recommendation. Promotion is
always disabled and owner approval is always required. Production promotion,
health monitoring after deployment, and automatic rollback are not implemented
by this slice.

## External capability status

The conversation research path can use configured search and model connectors
through the existing registry and reports real evidence or a blocked/partial
result. External capability acquisition, credential onboarding, arbitrary
adapter installation, and live service execution are not added here. The local
checkout has no verified staging target or approved live-provider credentials;
therefore no external integration or paid provider call is claimed or attempted.
