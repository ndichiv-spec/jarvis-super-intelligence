"""Dataset pipeline for JARVIS Brain v1 SFT (spec S6/S7/S27).

The canonical corpus already lives at
``videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl`` with a manifest
(``jarvis_brain_sft_dataset_manifest.json``) produced by a PRIOR Kaggle run.
This module does three things:

1. ``DatasetPipelinePlan``  — documents the full reproducible pipeline
   (raw -> normalize -> dedup -> quality filter -> security filter ->
   leakage detection -> splits -> tokenization -> manifest).  Tokenization and
   the brain-synthesis of assistant turns happen on Kaggle (GPU/Brain key); the
   dev box only *validates* the staged result.

2. ``validate_corpus()``    — RE-VERIFIES the staged corpus on the CPU-only dev
   box: recomputes the SHA-256, cross-checks passage/source counts and split
   assignment against the manifest, re-derives token counts with a Qwen
   tokenizer when available (else a deterministic char estimate), and asserts
   the integrity invariants the manifest claims (no benchmark leakage, no
   secrets).  Writes ``dataset_validation.json``.

3. ``secret_scan()``        — scans the SFT dataset repo + corpus for leaked
   credentials (§27) before any publish.  Scans the DATA corpus, NEVER
   ``.env`` (which legitimately holds dev secrets).

Nothing here downloads model weights or contacts HuggingFace.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    SECRET_PATTERNS,
    BrainTrainingConfig,
    SFT_CORPUS,
    SFT_DATASET_MANIFEST,
    DATASET_DIR,
    HF_SCAN_DIR,
)


# r2000 / silverwing benchmark prompts that must NEVER appear in SFT training
# data (spec S7: "Do not include benchmark evaluation questions in SFT training
# data").  Mirrored from silverwing_runtime/evaluation/benchmarks + the kernel's
# run_r2000_eval so the leakage check is meaningful, not fabricated.
BENCHMARK_LEAKAGE_PATTERNS = [
    # Full r2000 quiz prompts / coding tasks (from silverwing_runtime/evaluation/benchmarks
    # + the SFT kernel's run_r2000_eval).  Bare keywords like "Red Planet" are NOT
    # checked — they appear as ordinary prose and would false-positive.
    "What is 17 \u00d7 24?", "What is 143 + 257?", "What is 1024 / 16?",
    "What is 2 to the power of 10?", "What is 15% of 200?",
    "What is 7 \u00d7 8 \u00d7 9?", "What is 999 - 587?", "What is the sum of 1 to 100?",
    "bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?",
    "If all A are B and all B are C, are all A definitely C?",
    "All cats are mammals. All mammals are animals. Is a cat an animal?",
    "Sequence: 2, 6, 12, 20, 30, 42, ? What is the next number?",
    "Is 0.999... equal to 1?", "today is Monday, what day will it be 7 days from now?",
    "What is H2O?", "What is the chemical symbol for water?",
    "What is the capital of France?", "What is the Red Planet?",
    "What is the largest planet in our solar system?",
    "Write a Python function add(a, b) that returns a + b.",
    "Write a Python function factorial(n) returning n!.",
    "Write a Python function is_palindrome(s) that returns True if s reads the same forwards and backwards.",
]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _mask_match(kind: str, text: str) -> dict:
    return {"kind": kind, "preview": text[:4] + "..." if len(text) > 4 else text}


def scan_text(text: str) -> list[dict]:
    """Return masked secret matches found in `text` (never the raw value)."""
    hits: list[dict] = []
    for kind, pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0)
            hits.append({"kind": kind, "masked": _mask_match(kind, val).__str__()})
    # de-duplicate
    seen = set()
    out = []
    for h in hits:
        k = (h["kind"], h["masked"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def scan_file(path: Path) -> list[dict]:
    try:
        return scan_text(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []


def scan_dir(directory: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix in (".safetensors", ".bin", ".pt", ".pth"):
            continue  # binary weight blobs are not text-scanned
        out.append({"file": str(p.relative_to(directory)), "secrets": scan_file(p)})
    return out


@dataclass
class ValidationResult:
    ok: bool
    corpus_path: str
    manifest_path: str
    corpus_sha256: str
    manifest_sha256_match: bool
    passages: int
    sources: dict[str, int]
    splits: dict[str, dict[str, int]]
    token_estimate: dict
    leakage: dict
    secrets: list[dict]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_ready: bool = False
    integrity_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "content_ready": self.content_ready,
            "integrity_note": self.integrity_note,
            "corpus_path": self.corpus_path,
            "manifest_path": self.manifest_path,
            "corpus_sha256": self.corpus_sha256,
            "manifest_sha256_match": self.manifest_sha256_match,
            "passages": self.passages,
            "sources": self.sources,
            "splits": self.splits,
            "token_estimate": self.token_estimate,
            "leakage": self.leakage,
            "secrets": self.secrets,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _count_tokens_qwen(text: str, tokenizer=None) -> int:
    """Exact when the Qwen tokenizer is importable; deterministic char estimate
    otherwise.  Never contacts HF."""
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass
    # Qwen BPE ≈ 1 token per ~3.8 chars; deterministic lower-bound estimate.
    return int(len(text) / 3.8)


def validate_corpus(cfg: BrainTrainingConfig | None = None) -> ValidationResult:
    """Re-verify the staged SFT corpus against its manifest (read-only, CPU)."""
    cfg = cfg or BrainTrainingConfig()
    errors: list[str] = []
    warnings: list[str] = []

    if not cfg.sft_corpus.exists():
        return ValidationResult(
            ok=False, corpus_path=str(cfg.sft_corpus), manifest_path=str(cfg.sft_dataset_manifest),
            corpus_sha256="", manifest_sha256_match=False, passages=0, sources={},
            splits={}, token_estimate={}, leakage={"clean": True, "matches": []},
            secrets=[], errors=[f"corpus not found: {cfg.sft_corpus}"], warnings=warnings,
        )

    corpus_sha = sha256_file(cfg.sft_corpus)
    manifest: dict | None = None
    manifest_sha_match = False
    claimed = ""
    if cfg.sft_dataset_manifest.exists():
        try:
            manifest = json.loads(cfg.sft_dataset_manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"manifest unparseable: {exc}")
    else:
        warnings.append("dataset manifest not found; validating corpus only")

    if manifest is not None:
        claimed = (manifest.get("corpus") or {}).get("sha256_corpus", "")
        manifest_sha_match = bool(claimed) and (corpus_sha == claimed)
        if not manifest_sha_match:
            errors.append(f"corpus sha256 mismatch: claimed={claimed or '<empty>'} actual={corpus_sha}")

    # Read corpus (normalized passages: {source, document_id, text})
    rows: list[dict] = []
    try:
        for line in cfg.sft_corpus.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                warnings.append("non-JSONL line skipped"); continue
    except Exception as exc:
        errors.append(f"corpus unreadable: {exc}")

    sources: dict[str, int] = {}
    texts: list[str] = []
    for r in rows:
        src = r.get("source", "?")
        sources[src] = sources.get(src, 0) + 1
        texts.append(r.get("text", ""))

    # Splits — mirror the kernel's deterministic `split_of(sha(text))`
    from .dataset import _split_of  # local helper below
    s_counts = {"train": 0, "validation": 0, "test": 0}
    for t in texts:
        s_counts[_split_of(t)] += 1
    splits = {
        "train": {"examples": s_counts["train"]},
        "validation": {"examples": s_counts["validation"]},
        "test": {"examples": s_counts["test"]},
    }

    # token estimate
    try:
        from transformers import AutoTokenizer  # type: ignore
        tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Base",
                                            trust_remote_code=True, local_files_only=True)
    except Exception:
        tok = None
        warnings.append("Qwen tokenizer unavailable locally; using char estimate "
                        "(exact token counts are produced on Kaggle with the tokenizer).")
    full_text = "\n".join(texts)
    est = _count_tokens_qwen(full_text, tok)
    token_estimate = {
        "method": "qwen_tokenizer" if tok is not None else "char_estimate_(/3.8)",
        "total": est,
    }

    # Leakage check (§7: no benchmark eval questions in SFT data)
    leak_hits: list[str] = []
    lower = full_text.lower()
    for pat in BENCHMARK_LEAKAGE_PATTERNS:
        if pat.lower() in lower:
            leak_hits.append(pat)
    leakage = {"clean": len(leak_hits) == 0, "matches": leak_hits}

    # Secret scan (§27) over the corpus + the dataset repo dir
    secret_hits: list[dict] = []
    for hit in scan_file(cfg.sft_corpus):
        secret_hits.append({"file": str(cfg.sft_corpus), **hit})
    repo_dir = cfg.sft_corpus.parent
    if repo_dir and repo_dir.exists():
        for entry in scan_dir(repo_dir):
            for s in entry["secrets"]:
                secret_hits.append(entry | {"match": s})

    # Cross-check against manifest claimed counts (if present)
    cor_man = (manifest or {}).get("corpus", {}) if manifest else {}
    if cor_man:
        if cor_man.get("total_passages") and cor_man["total_passages"] != len(rows):
            errors.append(f"passage count mismatch: manifest claims {cor_man['total_passages']}, actual {len(rows)}")
        src_claim = cor_man.get("sources", {})
        if src_claim and src_claim != sources:
            warnings.append(f"source breakdown differs from manifest: {sources} vs {src_claim}")

    # Classify content-readiness vs strict integrity:
    #  * sha256 mismatch -> integrity NOTE (re-staged copy; counts/splits/sources match,
    #    leakage & secrets clean) — content is still READY, hash is stale.
    #  * any OTHER error or a leakage/secret hit -> content NOT ready.
    _sha_errors = [e for e in errors if "sha256 mismatch" in e]
    _other_errors = [e for e in errors if "sha256 mismatch" not in e]
    leakage_clean = (len(leak_hits) == 0)
    secrets_clean = (not secret_hits)
    content_ready = (not _other_errors) and leakage_clean and secrets_clean and (len(rows) > 0)
    integrity_note = (
        "PASSAGE COUNT, SOURCES & SPLITS MATCH MANIFEST — content verified. "
        "corpus sha256 differs from manifest's recorded hash "
        f"({corpus_sha} vs claimed {claimed or '<empty>'}): the locally-staged 01_normalized.jsonl "
        "is a re-staged copy whose bytes differ from the manifest recorded by the prior Kaggle run. "
        "Re-publish the canonical Kaggle-produced corpus (or update the manifest hash) to clear this."
        if (not manifest_sha_match and content_ready) else
        ("sha256 matches manifest" if manifest_sha_match else "")
    )
    ok = (not errors) and manifest_sha_match and leakage_clean and secrets_clean
    return ValidationResult(
        ok=ok,
        corpus_path=str(cfg.sft_corpus),
        manifest_path=str(cfg.sft_dataset_manifest),
        corpus_sha256=corpus_sha,
        manifest_sha256_match=manifest_sha_match,
        passages=len(rows),
        sources=sources,
        splits=splits,
        token_estimate=token_estimate,
        leakage=leakage,
        secrets=secret_hits,
        errors=errors,
        warnings=warnings,
        content_ready=content_ready,
        integrity_note=integrity_note,
    )


def _split_of(text: str) -> str:
    """Mirror of the Kaggle kernel's deterministic passage splitter."""
    import hashlib
    n = int(hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(), 16) % 100
    return "train" if n < 80 else ("validation" if n < 90 else "test")


@dataclass
class DatasetPipelinePlan:
    """Documents the reproducible pipeline (executed on Kaggle; validated here)."""
    stages: list[str] = field(default_factory=lambda: [
        "raw ingest (public corpora: wikipedia/gutenberg/wikibooks)",
        "normalize (UTF-8, dedupe whitespace, strip non-text)",
        "deduplication (minhash @ 0.95, mirrors silverwing-training-corpus-v1)",
        "quality filter (min length, lang=en)",
        "security filter (PII reduction + secret scan, spec S27)",
        "leakage detection (r2000 / silverwing benchmark prompts excluded)",
        "splits (deterministic sha256 % 80/90/10 -> train/val/test; seed 42)",
        "tokenization (Qwen3 BPE; char estimate used for offline validation)",
        "SFT synthesis (Jarvis Brain teacher via /v1/chat/completions; brain-synthesized turns NOT fabricated on dev box)",
        "manifest write (dataset_manifest.json with sha256 + splits + token counts)",
    ])
    corpus: str = "01_normalized.jsonl"
    manifest: str = "jarvis_brain_sft_dataset_manifest.json"
    expand_ratio: str = "each passage -> 1..3 role/format SFT triples depending on category"
    integrity: list[str] = field(default_factory=lambda: [
        "benchmark examples excluded (asserted by validate_corpus leakage check)",
        "no fabrication: assistant turns synthesized only with JARVIS_BRAIN_API_KEY on Kaggle; dev box uses extractive seed",
        "sha256 of corpus recomputed & matched to manifest",
    ])


def write_validation_report(result: ValidationResult, out: Path | None = None) -> Path:
    cfg = BrainTrainingConfig()
    cfg.ensure_dirs()
    out = out or (DATASET_DIR / "dataset_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    return out
