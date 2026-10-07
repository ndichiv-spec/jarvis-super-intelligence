# Silverwing Evaluation Registry

A standardized evaluation harness for Silverwing models, integrated directly
into `silverwing_runtime`.  It measures perplexity, math, logic, knowledge,
coding, and instruction-following capabilities using the real model backend,
persists results as structured evidence, and provides promotion decisions
(spec section 48).

## Directory Structure

```
silverwing_runtime/evaluation/
├── __init__.py        # Public exports
├── benchmarks.py      # Benchmark case definitions + r2000 baseline data
├── perplexity.py      # Validation loss / perplexity computation
├── harness.py         # EvaluationHarness: orchestrates all benchmark runs
├── registry.py        # EvaluationRegistry: persist + query evaluation results
├── results.py         # Pydantic result schemas
└── README.md          # This file
```

## Quick Start

### Running a Full Evaluation Against the Real Model

```python
from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry
from silverwing_runtime.evaluation import EvaluationHarness, EvaluationRegistry

# 1. Load the model (uses real TorchBackend — never EchoBackend for evaluation)
cfg = RuntimeConfig()
reg = SilverwingRegistry(cfg)
reg.refresh()
loader = ModelLoader(reg, config=cfg)
svc = InferenceService(loader, cfg)
svc.warmup("silverwing-120m-base-v1")

# 2. Get the real backend
backend = svc._backends["silverwing-120m-base-v1"]

# 3. Run evaluation
harness = EvaluationHarness(backend, "silverwing-120m-base-v1")
result = harness.run_full_evaluation(
    val_text="F:/AI/silverwing-120m/data/splits/val.txt",
    label="r1-gpu-eval",
)

# 4. Persist + review
registry = EvaluationRegistry()
registry.record(result)
print(registry.promotion_evidence("silverwing-120m-base-v1"))

svc.shutdown()
```

### CLI Script

For convenience, a one-shot evaluation script:

```python
#!/usr/bin/env python
"""Run a full evaluation of silverwing-120m-base-v1 and write evaluation_report.json"""
from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry
from silverwing_runtime.evaluation import EvaluationHarness, EvaluationRegistry
import json

cfg = RuntimeConfig()
reg = SilverwingRegistry(cfg)
reg.refresh()
loader = ModelLoader(reg, config=cfg)
svc = InferenceService(loader, cfg)
svc.warmup("silverwing-120m-base-v1")

backend = svc._backends["silverwing-120m-base-v1"]
harness = EvaluationHarness(backend, "silverwing-120m-base-v1")
result = harness.run_full_evaluation(
    val_text=r"F:\AI\silverwing-120m\data\splits\val.txt",
    label="r1-gpu-eval",
)

# Write report alongside the model manifest
report_path = Path(r"F:\AI\silverwing-models\silverwing-120m-base\v1\evaluation_report.json")
with open(report_path, "w") as f:
    f.write(result.model_dump_json(indent=2))

# Save to registry
EvaluationRegistry().record(result)
print(f"Evaluation saved to {report_path}")
svc.shutdown()
```

## Benchmark Categories

| Category        | Count | Scoring Method                          |
|----------------|-------|------------------------------------------|
| Math           | 8     | Extract first integer, compare to answer |
| Logic          | 6     | Keyword fragment match (case-insensitive) |
| Knowledge      | 8     | Keyword fragment match                   |
| Coding         | 3     | Extract Python → sandboxed execution → test assertion |
| Instruction    | 5     | Keyword match + negation check           |
| Perplexity     | 1     | Validation loss + perplexity via `full_forward` |

## r2000 Baseline (12M Model)

These values are frozen from the r2000 training run (`silverwing-12m-base-r2000`)
and serve as the promotion gate (spec section 48, B16 gate):

| Metric             | r2000 Baseline |
|--------------------|----------------|
| Parameters         | 12,440,448     |
| Val Loss           | 6.3445         |
| Val Perplexity     | 569.38         |
| Math Accuracy      | 0/8            |
| Logic Accuracy     | 4/6            |
| Coding Accuracy    | 0/3            |
| Knowledge Accuracy | 0/8            |

The B16 gate: *"Do NOT build 300M until 120M base beats r2000 on math/logic/coding/knowledge (B25 gate)."*

## Code Execution Sandbox (Spec Section 17)

Model-generated Python code is **never** executed directly on the host.
Each coding benchmark test runs in a separate Python subprocess with a hard
timeout:

```python
def _run_code_check_sandboxed(code: str, test_expr: str, timeout: float = 5.0) -> tuple[bool, dict]:
    """Execute code + test assertion in an isolated subprocess."""
```

If the subprocess times out or errors, the test is scored as failed.

## Results Storage

Evaluations are persisted as JSON in:
- Default: `SILVERWING_EVAL_DIR` env var, or `./evaluations/`
- Model repo: `<model_repo>/evaluations/`

Each result is stored at:
```
<eval_dir>/<model_id>/<revision>/<label>.json
```

Query the registry:

```python
reg = EvaluationRegistry(base_dir="/path/to/evals")
reg.record(result)                    # Save
entry = reg.get("silverwing-120m-base-v1", "r1", "r1-gpu-eval")  # Retrieve
history = reg.list_evaluations("silverwing-120m-base-v1")         # All runs
latest = reg.latest("silverwing-120m-base-v1")                   # Most recent
comparison = reg.compare("silverwing-120m-base-v1")              # Cross-run comparison
evidence = reg.promotion_evidence("silverwing-120m-base-v1")      # Promotion decision
```

## Result Schema

The `EvaluationResult` pydantic model contains:

- **model_id, version, revision** — model identity from the manifest
- **weights_sha256** — verified weight hash (not fabricated)
- **param_count** — architecture-verified parameter count
- **perplexity** — val_loss, val_perplexity, token/window counts
- **benchmarks** — per-category BenchmarkResult with per-question detail
- **generation_samples** — 10 fixed-prompt generations with timing
- **comparison** — r2000 baseline comparison + improvement deltas
- **hardware** — device, dtype, torch version (honest reporting)

## Running Tests

```bash
# Unit tests (no model loading — fast)
python -m pytest tests/test_silverwing_evaluation.py -v -m "not integration"

# Full evaluation suite (unit + real-model integration — slow on CPU)
python -m pytest tests/test_silverwing_evaluation.py -v
```

## Important Notes

- **Never uses EchoBackend silently**: When the backend is not `TorchBackend`,
  perplexity is *skipped* (honestly reported as `skipped=True`) rather than
  faked. EchoBackend is never used as a silent fallback.
- **Unit tests with EchoBackend**: The harness is tested against a mock
  EchoBackend for fast unit tests. All benchmarks score 0% (or keyword-match
  from echoed prompts), and perplexity is skipped — this is the honest,
  expected behavior.
- **Real evaluation requires TorchBackend**: Full evaluation against the real
  120M model runs via the integration test `TestFullEvaluationRealModel`
  (marked `@pytest.mark.integration`, skipped by default).
