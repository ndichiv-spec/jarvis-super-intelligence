# JARVIS BRAIN v1 — Evaluation Suite

Fixed, deterministic evaluation set for the CANDIDATE verification gate.

- `eval_suite.jsonl` — 108 items, 9 task families x 12:
  conversation, math, logic, coding, knowledge, instruction_following,
  structured_output, tool_selection, verification.
- `eval_suite.json` — same content with suite metadata.
- `evaluator.py` — the single shared evaluation implementation (baseline and
  SFT kernels import exactly this file, so both models are scored with
  identical code).
- sha256(eval_suite.jsonl): `62ae8523b30a2b78891e2fc4391574c22199546b33e2ad5537e107a1da90e248`
- Generation: greedy (`do_sample=False`, temperature 1.0) for reproducibility.
- The suite is NEVER used for training and is not modified after model
  evaluation begins (fixed contract).

Scoring contract (per family):
- math: `exact_answer` numeric (deterministic reference)
- logic / verification: `bool_eq` (deterministic yes/no reference)
- coding: `code_judge` — extracted Python function run against hidden cases
- instruction_following: `exact_answer` structural checks
- structured_output: `json_fields` (parse + field/value comparison)
- tool_selection: `tool_name` (JSON `{"tool": "<name>"}`)
- knowledge: `keyword_overlap` — **explicitly a weak proxy metric**, recorded as
  such, not an authoritative score
- conversation: `record_only` — **not auto-scored**; raw outputs recorded for
  human review (no fabricated correctness)