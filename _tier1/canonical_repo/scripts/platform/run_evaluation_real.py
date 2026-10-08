"""Run evaluation against the real silverwing-120m-base-v1 model.

Loads the model via TorchBackend (never EchoBackend), runs the full
evaluation harness, and writes evaluation_report.json + registry entry.
"""
from __future__ import annotations

import sys
import time
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry
from silverwing_runtime.evaluation import EvaluationHarness, EvaluationRegistry

MODEL_REF = "silverwing-120m-base-v1"
VAL_PATH = WORKSPACE / "silverwing-120m" / "data" / "splits" / "val.txt"
REPORT_DIR = WORKSPACE / "silverwing-models" / "silverwing-120m-base" / "v1"

def main():
    print("=== Silverwing-120M Evaluation ===")
    t0 = time.monotonic()

    # 1. Load model
    print(f"Loading model: {MODEL_REF}")
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    svc = InferenceService(loader, cfg)
    svc.warmup(MODEL_REF)
    load_time = time.monotonic() - t0
    print(f"Model loaded + warmup in {load_time:.1f}s")

    # 2. Get backend
    backend = svc._backends[MODEL_REF]
    assert backend.backend == "torch", f"expected torch, got {backend.backend}"
    print(f"  device: {backend.device}, dtype: {backend.dtype_str}")

    # 3. Run evaluation
    harness = EvaluationHarness(backend, MODEL_REF)
    val_text = str(VAL_PATH) if VAL_PATH.exists() else "the quick brown fox " * 200
    if VAL_PATH.exists():
        print(f"  val_text: {VAL_PATH}")
    else:
        print(f"  WARNING: val.txt not found, using inline fallback")

    print("Running full evaluation (perplexity + 5 benchmark categories + 10 samples)...")
    result = harness.run_full_evaluation(val_text, label="r1-real-eval")
    eval_time = time.monotonic() - t0
    print(f"Evaluation complete in {eval_time:.1f}s (total incl. load: {eval_time:.1f}s)")

    # 4. Print summary
    print("\n=== Evaluation Summary ===")
    print(f"Model:       {result.model_id}@{result.revision}")
    print(f"Params:      {result.param_count:,}")
    print(f"SHA-256:     {result.weights_sha256[:16]}...")
    print(f"Val Loss:    {result.perplexity.val_loss:.4f}")
    print(f"Val PPL:     {result.perplexity.val_perplexity:.2f}")
    print(f"PPL skipped: {result.perplexity.skipped}")
    print(f"Samples:     {result.perplexity.val_samples if hasattr(result.perplexity, 'val_samples') else 'N/A'}")

    for name, br in result.benchmarks.items():
        print(f"  {name:15s}: {br.correct}/{br.total} ({br.accuracy:.1%})")

    cmp = result.comparison
    print(f"\n=== Comparison vs r2000 ===")
    print(f"  Beats r2000 PPL:     {cmp.beats_baseline_ppl}")
    print(f"  Beats r2000 loss:    {cmp.beats_baseline_val_loss}")
    print(f"  Math improvement:    +{cmp.math_improvement:.3f}")
    print(f"  Logic improvement:   +{cmp.logic_improvement:.3f}")
    print(f"  Knowledge improvement:+{cmp.knowledge_improvement:.3f}")
    print(f"  Coding improvement:  +{cmp.coding_improvement:.3f}")

    # 5. Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"\nReport saved to: {report_path}")

    # 6. Save to registry
    registry = EvaluationRegistry()
    reg_path = registry.record(result)
    print(f"Registry entry:      {reg_path}")

    # 7. Promotion evidence
    evidence = registry.promotion_evidence(MODEL_REF)
    print(f"\n=== Promotion Evidence ===")
    print(json.dumps(evidence, indent=2))
    print(f"\nPromotion status: {evidence['promotion_status']}")

    svc.shutdown()
    print("\nDone.")

if __name__ == "__main__":
    main()
