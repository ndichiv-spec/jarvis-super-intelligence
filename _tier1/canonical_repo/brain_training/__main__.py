"""CLI entry: ``python -m brain_training <command>``.

Commands:
  status          §24 operations status view (actual state only)
  validate        §6 dataset validation (recompute sha256, leakage, secrets)
  probe-hf        §3/4 HuggingFace connection probe
  probe-kaggle    §8/13 Kaggle configuration probe
  hardware        §8 GPU/CUDA/RAM/disk probe
  gate            §18 promotion gate
  deploy          §19-22 deployment config + live Brain health probe
  pipeline        §25 run the orchestrated workflow (read-only stages)
  baseline        §16 Qwen3-4B baseline (GPU-gated; NOT_RUN on CPU)
"""
from __future__ import annotations

import argparse
import json
import sys

from .status import status, status_json
from .dataset import validate_corpus, write_validation_report
from .hf import secret_scan_artifact
from .hf import probe as hf_probe
from .kaggle import probe as kaggle_probe
from .hardware import gpu_probe
from .promote import gate as promotion_gate
from .deploy import load_config, resolve_model, probe_brain_endpoint
from .pipeline import run_pipeline


def _print(d: dict) -> None:
    print(json.dumps(d, indent=2, default=str))


def cmd_status() -> int:
    _print({"JARVIS BRAIN v1 - OPERATIONS STATUS": json.loads(status_json())})
    return 0


def cmd_validate() -> int:
    from .config import BrainTrainingConfig
    cfg = BrainTrainingConfig()
    res = validate_corpus(cfg)
    path = write_validation_report(res)
    scan = secret_scan_artifact(cfg.sft_corpus.parent)
    _print({"dataset": res.to_dict(), "secret_scan": scan, "report": str(path)})
    return 0 if res.ok and scan["clean"] else 1


def cmd_hf() -> int:
    _print({"huggingface": hf_probe().summary()})
    return 0


def cmd_kaggle() -> int:
    _print({"kaggle": kaggle_probe().summary(),
            "expected_gpu_requirements": __import__("brain_training.kaggle",
                                                     fromlist=["kaggle_gpu_requirements"]).kaggle_gpu_requirements()})
    return 0


def cmd_hardware() -> int:
    _print({"hardware": gpu_probe().summary()})
    return 0


def cmd_gate(target: str | None = None) -> None:
    t = target or "validated"
    _print({"promotion_gate": promotion_gate(t).to_dict()})


def cmd_deploy() -> None:
    cfg = load_config()
    _print({"deploy_config": cfg.summary(),
            "model_resolution": resolve_model(cfg.model),
            "brain_health": probe_brain_endpoint(cfg.endpoint)})


def cmd_pipeline() -> int:
    res = run_pipeline()
    _print(res.to_dict())
    return 0 if res.overall == "PASS" else 1


def cmd_baseline() -> int:
    from .baseline import run_baseline, write_baseline
    res = run_baseline()
    jp, mp = write_baseline(res)
    _print({"baseline": {**res.__dict__}, "json": str(jp), "md": str(mp)})
    return 0 if res.ran else 2  # 2 = NOT_RUN (no GPU)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain_training",
                                     description="JARVIS BRAIN v1 training operations")
    parser.add_argument("command", choices=[
        "status", "validate", "probe-hf", "probe-kaggle", "hardware",
        "gate", "deploy", "pipeline", "baseline",
    ])
    parser.add_argument("target", nargs="?", default=None,
                        help="promotion target stage (for 'gate': "
                             "candidate|validated|promoted; default validated)")
    args = parser.parse_args(argv)
    if args.command == "gate":
        cmd_gate(args.target)
        return 0
    dispatch = {
        "status": cmd_status, "validate": cmd_validate, "probe-hf": cmd_hf,
        "probe-kaggle": cmd_kaggle, "hardware": cmd_hardware, "deploy": cmd_deploy,
        "pipeline": cmd_pipeline, "baseline": cmd_baseline,
    }
    return dispatch[args.command]()


if __name__ == "__main__":
    sys.exit(main())
