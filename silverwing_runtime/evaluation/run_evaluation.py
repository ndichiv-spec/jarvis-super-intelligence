"""One-shot evaluation of silverwing-120m-base-v1.

Loads the real model via TorchBackend (never EchoBackend), runs the full
evaluation harness, and writes:

1. ``evaluation_report.json`` alongside the model manifest.
2. The result into the EvaluationRegistry.

Usage:
    python silverwing_runtime/evaluation/run_evaluation.py
    python silverwing_runtime/evaluation/run_evaluation.py --val-text path/to/val.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent  # .../evaluation -> .../silverwing_runtime -> F:/AI
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.evaluation import EvaluationHarness, EvaluationRegistry
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry

MODEL_REF = "silverwing-120m-base-v1"
DEFAULT_VAL_TEXT = WORKSPACE / "silverwing-120m" / "data" / "splits" / "val.txt"
REPORT_DIR = WORKSPACE / "silverwing-models" / "silverwing-120m-base" / "v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Silverwing-120M")
    parser.add_argument(
        "--val-text", default=str(DEFAULT_VAL_TEXT),
        help="Path to validation text file for perplexity",
    )
    parser.add_argument(
        "--label", default="r1-real-eval",
        help="Label for this evaluation run",
    )
    parser.add_argument(
        "--report-dir", default=str(REPORT_DIR),
        help="Directory to write evaluation_report.json",
    )
    args = parser.parse_args()

    val_path = Path(args.val_text)
    if not val_path.exists():
        print(f"WARNING: val text not found at {val_path}, falling back to inline text")
        val_text = "the quick brown fox jumps over the lazy dog " * 200
    else:
        val_text = str(val_path)

    print(f"Loading model: {MODEL_REF}")
    t0 = time.monotonic()
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    svc = InferenceService(loader, cfg)
    svc.warmup(MODEL_REF)

    backend = svc._backends[MODEL_REF]
    assert backend.backend == "torch", f"expected torch backend, got {backend.backend}"
    print(f"Model loaded in {time.monotonic() - t0:.1f}s, device={backend.device}")

    print("Running full evaluation...")
    harness = EvaluationHarness(backend, MODEL_REF)
    result = harness.run_full_evaluation(val_text, label=args.label)

    # Write evaluation_report.json alongside the manifest
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"Report written to {report_path}")

    # Persist to registry
    registry = EvaluationRegistry(base_dir=report_dir.parent.parent / "evaluations")
    reg_path = registry.record(result)
    print(f"Registry entry at {reg_path}")

    # Print promotion evidence
    evidence = registry.promotion_evidence(MODEL_REF)
    print("\n=== Promotion Evidence ===")
    print(json.dumps(evidence, indent=2))

    svc.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    main()
