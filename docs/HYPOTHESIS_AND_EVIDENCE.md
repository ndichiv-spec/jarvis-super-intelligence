# Phase 10 — Hypothesis & Evidence

## Overview

Phase 10 introduces structured hypothesis management and evidence provenance tracking. Every important conclusion in a mission is traceable to evidence, and hypotheses are maintained as explicit, testable objects — not forced into a single "truth."

## Hypothesis Engine

### Hypothesis Model

```python
@dataclass
class Hypothesis:
    id: str                    # hyp_<uuid>
    statement: str             # What is being tested
    context: str               # Context/mission background
    status: HypothesisStatus   # Current state
    rationale: str             # Why this hypothesis was proposed
    proposed_by: str           # Actor that proposed it
    proposed_at: str           # ISO timestamp
    tested_at: Optional[str]   # When last tested
    confidence: Optional[float]  # 0.0–1.0
    evidence_ids: list[str]   # Evidence supporting this hypothesis
    refuted_by: list[str]      # Evidence contradicting it
    conclusion: Optional[str]  # Final conclusion
```

### Hypothesis Statuses

| Status | Meaning |
|--------|---------|
| PROPOSED | Hypothesis is proposed but not yet tested |
| TESTING | Hypothesis is currently being tested |
| SUPPORTED | Hypothesis is supported by some evidence |
| WEAKENED | Hypothesis is weakened by some evidence |
| REJECTED | Hypothesis is contradicted by evidence |
| CONFIRMED | Hypothesis is confirmed by verified evidence |
| INCONCLUSIVE | Insufficient evidence to decide |

### Key Guarantees

1. **Multiple competing hypotheses** are maintained simultaneously.
2. **The first hypothesis is not forced into truth.** A new hypothesis can supersede or contradict an existing one.
3. **CONFIRMED requires VerificationStatus.VERIFIED** — not just evidence presence.
4. **REJECTED requires CONTRADICTED evidence or test failure.**

### HypothesisEngine API

```python
class HypothesisEngine:
    def propose(statement, context, rationale, proposed_by) -> Hypothesis
    def select_next() -> Optional[Hypothesis]   # Next hypothesis to test
    def get(hypothesis_id) -> Optional[Hypothesis]
    def list_all() -> list[Hypothesis]
    def evaluate(hypothesis_id, evidence, experiments) -> HypothesisStatus
    def mark_testing(hypothesis_id)
    def close_as_inconclusive(hypothesis_id, reason)
    def to_dict() / from_dict()  # For checkpointing
```

## Evidence Engine

### EvidenceEntry Model

```python
@dataclass
class EvidenceEntry:
    evidence_id: str            # ev_<uuid>
    source_url: str             # Where the evidence came from
    source_type: str            # web, document, database, tool, model, system, etc.
    title: Optional[str]        # Human-readable title
    retrieved_at: str           # ISO timestamp
    relevant_content: str       # The actual evidence content
    claims: list[str]           # Claims supported by this evidence
    supporting_excerpt: str     # Excerpt from the source
    provider: Optional[str]     # Provider (if applicable)
    verification_status: str    # VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, etc.
    provenance: list[ProvenanceEvent]  # Full audit trail
```

### ProvenanceChain

Every `EvidenceEntry` has a `ProvenanceChain` — an append-only audit trail:

```python
@dataclass
class ProvenanceEvent:
    actor: str      # Who/what registered this event
    action: str     # collected, verified, linked, etc.
    at: str         # ISO timestamp
    detail: str     # Human-readable detail
```

### Evidence Sources

Evidence can come from:

| Source Type | Examples |
|------------|----------|
| `web` | Web search results, documentation |
| `document` | Document extraction, PDF analysis |
| `database` | Database query results |
| `tool` | Capability tool output (READ operations) |
| `model` | NVIDIA inference results |
| `system` | System diagnostics, local hardware info |
| `experiment` | Training/evaluation results (Kaggle) |
| `artifact` | Hugging Face artifact metadata |
| `project` | Source code inspection |
| `internal` | Internally generated structured data |

### Evidence Engine API

```python
class EvidenceEngine:
    def register_evidence(source_url, source_type, ...) -> EvidenceEntry
    def register_from_tool_result(tool_name, result, source_type) -> EvidenceEntry
    def verify_evidence(evidence_id, verifier, claim) -> EvidenceEntry
    def list_all() -> list[EvidenceEntry]
    def get_chain_of_custody(evidence_id) -> list[ProvenanceEvent]
    def assert_no_fabrication() -> list[str]  # Returns any fabricated evidence IDs
```

## Critic

The Critic inspects the cognitive state for potential issues:

### Checks Performed

1. **Fabrication**: Evidence marked VERIFIED without provenance links
2. **Evidence Quality**: Unverified evidence count, empty content
3. **Hypothesis Quality**: Untested hypotheses
4. **Budget**: Warning at 80%, exhaustion at 100%
5. **Confidence Calibration**: High confidence without supporting evidence
6. **Evidence Conflicts**: Contradictory evidence entries
7. **Verification Gaps**: Claims without verification

### CriticFinding Model

```python
@dataclass
class CriticFinding:
    finding_id: str
    at: str
    severity: FindingSeverity    # info, warning, error
    category: FindingCategory   # fabrication, evidence, hypothesis, budget, etc.
    description: str
    recommendation: str
```

### Critic Guarantees

- **Analysis only** — no execution authority
- **No `execute`, `run_tool`, `submit_job`, `create_task`, `transition`, or `authorize` methods**
- **Produces findings** — does not block execution
- **Error-severity findings** can trigger budget exhaustion stop

## Verifier

The Verifier wraps the existing Phase 7 `VerificationEngine`:

### Verification States

| State | Meaning |
|-------|---------|
| GENERATED | Claim was generated |
| EXECUTED | Code/tool was executed |
| OBSERVED | Output was observed |
| VERIFIED | Output was independently verified |
| FAILED_VERIFICATION | Verification failed |

### Key Non-Confusability Rules

| Claim | Is NOT Equivalent To |
|-------|---------------------|
| "Model was trained" | "Training job completed" |
| "Training job completed" | "Model passed evaluation" |
| "Model passed evaluation" | "Model is approved for production" |
| "Task succeeded" | "Mission objectives met" |

### Verifier API

```python
class Verifier:
    def verify_claim(claim, evidence_ids) -> VerificationOutcome
    def verify_success_criteria(criteria, evidence_entries) -> dict
    def verify_evidence(evidence_id) -> bool
    def verify_hypothesis(hypothesis_id) -> bool
```

## Integration Example

```
Mission: "Improve math reasoning"

Cycle 1:
1. PERCEIVE  → local_hardware(), discover_brain()
2. UNDERSTAND → intent=investigation
3. HYPOTHESIZE → "Model fails on word problems" (PROPOSED)
4. PLAN → [project.search("math benchmark results")]
5. AUTHORIZE → READ capability auto-authorized
6. EXECUTE → project.search returns evidence
7. OBSERVE → evidence registered with provenance
8. CRITIQUE → no fabrication, evidence unverified
9. VERIFY → evidence UNVERIFIED (needs independent check)
10. LEARN → evidence added to mission memory
11. REPLAN → not complete, continue

Cycle 2:
3. HYPOTHESIZE → selects existing hypothesis "Model fails on word problems" (TESTING)
4. PLAN → [compute.inference (NVIDIA, if available)]
...
9. VERIFY → inference result VERIFIED via deterministic check
3. HYPOTHESIZE → evaluate existing hypothesis
```
