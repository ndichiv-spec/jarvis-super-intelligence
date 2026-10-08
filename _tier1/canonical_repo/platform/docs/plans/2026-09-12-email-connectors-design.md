# Email Connectors — Design (2026-09-12)

Status: agreed with stakeholder (developer). Approach **D**: unified Connectors
hub, email shipped first via generic IMAP/SMTP app-password, OAuth (Gmail /
Outlook) later behind the same interface. AI autonomy default: **everything
allowed** via per-capability toggles + global kill switch, with mandatory audit.

## Goals / constraints (from spec)

* Never rebuild JARVIS, never swap the Silverwing model. Additive only.
* Every claim measured: tests run against a REAL protocol stack on loopback
  (minimal IMAP/SMTP servers), not unit-mocked sockets.
* Credentials never returned to clients; encrypted at rest keyed off the
  existing stable `JARVIS_SECRET_KEY`.
* Honest AI: if no connector configured, the AI says so instead of inventing.

## Architecture

Backend (`jarvis_backend/connectors/`):

* `crypto.py`     — Fernet encrypt/decrypt of secret fields.
* `base.py`       — `Connector` ABC, `ActionSpec`, capability constants.
* `mail/imap_connector.py` — read path via `imaplib` (TLS), actions:
  `email.list`, `email.search`, `email.read`, `email.summarize`,
  `email.folders`. Body previews truncated; nothing written to disk.
* `mail/smtp_connector.py` — send path via `smtplib` (STARTTLS), actions:
  `email.draft`, `email.send`, `email.reply`. Send rate-limited and carries a
  provenance footer.
* `registry.py`   — persistent `jarvis_data/connectors/mail.json`; secrets
  encrypted; masked representation `••••`; kill switch + capability set.
* `dispatch.py`   — `execute_connector_action(kind, action, params, actor)`:
  loads config, enforces capability, runs action, appends audit line.

Router (`jarvis_backend/routers/connectors.py`, wired in `main.py`):

* `GET    /api/v1/connectors`            — list (masked) + status
* `GET    /api/v1/connectors/{kind}`     — one connector
* `POST   /api/v1/connectors/{kind}/test`— test a config without saving
* `POST   /api/v1/connectors/{kind}`     — create/save connector
* `PATCH  /api/v1/connectors/{kind}`     — update (empty password = keep)
* `DELETE /api/v1/connectors/{kind}`     — remove
* `POST   /api/v1/connectors/{kind}/actions` — dispatch an action
* `GET    /api/v1/connectors/activity`   — audit feed

All mutate/action endpoints authenticated (`get_current_user`). Masked values
sent back in PATCH are ignored as real secrets (kept).

AI wiring: agents router gains `action="email"` support in
`POST /api/v1/agents/{id}/act` (capability-gated: email capability required),
reusing the dispatch + audit path; Coder agent gets `email` capability.

Frontend: new `/dashboard/connections` route + sidebar entry (category
"Infrastructure", before Settings). Email connector card with provider
picker, IMAP/SMTP host+port, username, app-password, send-from, capability
toggles (Read/Search, Summarize, Draft, Send/Reply), Test, Save, Disable,
Delete, global kill switch, last-tested/status badge, and activity feed from
the audit trail.

## Security model

* Only the admin (any authenticated user with `connectors` access; UI is
  developer-facing) can manage connectors. Actions require auth too.
* Send defaults shared: rate limit (20/hr in-flight), provenance footer
  (`Sent by JARVIS AI via <from>`), full audit: actor, action, mailbox,
  subject, recipients, size, timestamp.
* Kill switch disables every connector action at dispatch time.
* Password change requires a fresh secret; masked PATCH never overwrites.
* No mail writes to disk; bodies exist only in the transient response.

## Testing

* `tests/fakes/mail_servers.py` — minimal REAL SMTP (`socketserver`,
  HELO/EHLO/MAIL/RCPT/DATA/QUIT, captures messages in memory) and REAL IMAP
  (LOGIN/SELECT/SEARCH/FETCH/STORE/EXPUNGE subset) servers on loopback.
* `tests/test_connectors.py` — RegistryTest (encryption round-trip, masking,
  PATCH keep semantics), RouterTest (auth 401, capability gating, kill
  switch, audit lines, unconfigured honest error), MailFlowTest (end-to-end
  read/search/send against the loopback servers). Provider default is
  "FakeIMAP"/"FakeSMTP"; real-app-password mode optional via env.