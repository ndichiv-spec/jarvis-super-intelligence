"""
PHASE 3 — Data Quality Pipeline

Pipeline stages (modular, each can be run independently):
  1. Normalize   — Unicode normalization, encoding fix, whitespace cleanup
  2. Language filter — Keep English content, remove non-English
  3. Quality filter   — Remove boilerplate, spam, very short/long docs
  4. Dedup           — Exact + near-duplicate removal
  5. PII reduce      — Redact emails, phones, IPs
  6. Tokenize       — BPE tokenization with Silverwing tokenizer
  7. Pack & split   — Sequence packing + train/val split

Produces: dataset_manifest.json with full provenance
"""
import json
import os
import re
import sys
import hashlib
import unicodedata
import html as html_lib
from pathlib import Path
from collections import defaultdict

# Load the Silverwing tokenizer
import importlib.util

SCRIPT_DIR = Path(__file__).resolve().parent
SILVERWING_DIR = SCRIPT_DIR.parent
SILVERWING_SCRIPT = SILVERWING_DIR / "kaggle" / "silverwing_train.py"

RAW_DIR = SCRIPT_DIR / "raw"
PROC_DIR = SCRIPT_DIR / "processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)

TOKENIZER_PATH = SILVERWING_DIR / "local_run" / "tokenizer" / "tokenizer.json"

# Load the Silverwing tokenizer/training module
spec = importlib.util.spec_from_file_location("silverwing_train", str(SILVERWING_SCRIPT))
sw = importlib.util.module_from_spec(spec)
sys.modules["silverwing_train"] = sw
spec.loader.exec_module(sw)


# ============================================================
# STAGE 1: Normalize
# ============================================================

def normalize_text(text, source=None):
    """Normalize Unicode, fix encoding, strip HTML tags, clean whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lstrip("\ufeff")
    text = text.replace("\x00", "")
    # Strip HTML tags — convert block-level elements to paragraph breaks
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL)
    # Replace block-level HTML elements with double newlines
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr|td|th|table|ul|ol|blockquote|section|article|header|footer|aside|nav|figure|figcaption|pre)[^>]*>',
                  '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining inline tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Unescape HTML entities
    text = html_lib.unescape(text)
    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Clean up lines: strip each, remove empty lines
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Collapse consecutive single newlines into double newlines for paragraph separation
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def strip_gutenberg_boundary(text):
    """Remove Project Gutenberg header/footer markers."""
    start_idx = -1
    for marker in ["*** START", "START OF THE PROJECT", "START OF"]:
        idx = text.find(marker)
        if idx > 0:
            start_idx = idx
            break
    if start_idx > 0:
        text = text[start_idx:]
    end_idx = -1
    for marker in ["*** END", "END OF THE PROJECT", "END OF"]:
        idx = text.rfind(marker)
        if idx > 0:
            end_idx = idx
            break
    if end_idx > 0:
        text = text[:end_idx]
    return text.strip()


def stage_normalize():
    """Stage 1: Normalize all raw text into JSONL format."""
    print("=== Stage 1: Normalize ===")
    output_file = PROC_DIR / "01_normalized.jsonl"

    stats = {
        "sources": defaultdict(lambda: {"documents": 0, "chars_in": 0, "chars_out": 0}),
        "total_documents": 0,
    }

    with open(output_file, "w", encoding="utf-8") as out_f:
        for source_name in ["wikipedia", "gutenberg", "wikibooks"]:
            source_dir = RAW_DIR / source_name
            if not source_dir.exists():
                print(f"  Skipping {source_name}: not found")
                continue

            for jf in sorted(source_dir.glob("*.jsonl")):
                print(f"  Processing JSONL: {jf.name}")
                with open(jf, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        record = json.loads(line)
                        original = record.get("text", "")
                        normalized = normalize_text(original)
                        stats["sources"][source_name]["documents"] += 1
                        stats["sources"][source_name]["chars_in"] += len(original)
                        stats["sources"][source_name]["chars_out"] += len(normalized)
                        stats["total_documents"] += 1

                        out_f.write(json.dumps({
                            "source": record.get("source", source_name),
                            "document_id": record.get("title", f"{jf.stem}_{stats['total_documents']}"),
                            "chars": len(normalized),
                            "text": normalized,
                            "original_source": source_name,
                        }, ensure_ascii=False) + "\n")

            for tf in sorted(source_dir.glob("*.txt")):
                if tf.name in ["acquisition_summary.json", "gutenberg_books.json"]:
                    continue
                print(f"  Processing TXT: {tf.name}")
                with open(tf, "r", encoding="utf-8", errors="replace") as f:
                    original = f.read()
                if source_name == "gutenberg":
                    original = strip_gutenberg_boundary(original)
                normalized = normalize_text(original)
                stats["sources"][source_name]["documents"] += 1
                stats["sources"][source_name]["chars_in"] += len(original)
                stats["sources"][source_name]["chars_out"] += len(normalized)
                stats["total_documents"] += 1

                out_f.write(json.dumps({
                    "source": source_name,
                    "document_id": tf.stem,
                    "chars": len(normalized),
                    "text": normalized,
                    "original_source": source_name,
                }, ensure_ascii=False) + "\n")

    stats["sources"] = dict(stats["sources"])
    print(f"  Total documents: {stats['total_documents']}")
    for src, s in stats["sources"].items():
        print(f"    {src}: {s['documents']} docs, {s['chars_in']:,} -> {s['chars_out']:,} chars")
    print(f"  Output: {output_file} ({os.path.getsize(output_file):,} bytes)")
    return stats


# ============================================================
# STAGE 2: Language Filter
# ============================================================

ENGLISH_WORDS = set("""
the of and to in a is that was he for it as his on with was that by to and he
his her in this that there was began could the had from which one were words
into than said had not have an what when them see can no only other its over
think also first after would who so if no more will people my has what where
now may then some what only very know also may way many call get come could
their them about much before look two more write go see number no way take
them make day also come find use long mean new talk old yes make time year
man new still good way make sure most me give great thing set got go
""".split())


def detect_language(text):
    """Simple English language detection."""
    if len(text) < 200:
        return "unknown"
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
    if ascii_ratio < 0.80:
        return "non-english"
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if len(words) < 10:
        return "unknown"
    en_count = sum(1 for w in words if w in ENGLISH_WORDS)
    en_ratio = en_count / len(words)
    if en_ratio < 0.005:
        return "non-english"
    if en_ratio < 0.02:
        return "mixed"
    return "english"


def stage_language_filter(input_file, output_file):
    """Stage 2: Filter for English content."""
    print("=== Stage 2: Language Filter ===")
    stats = {"total": 0, "english": 0, "removed": 0, "removed_chars": 0}

    with open(input_file, "r", encoding="utf-8") as in_f, \
         open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            stats["total"] += 1
            lang = detect_language(record["text"])
            if lang in ("english", "mixed"):
                stats["english"] += 1
                record["detected_language"] = lang
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                stats["removed"] += 1
                stats["removed_chars"] += len(record["text"])
                print(f"  Removed ({lang}): {record['source']}/{record.get('document_id', '?')[:50]}")

    print(f"  Total: {stats['total']}, English kept: {stats['english']}, Removed: {stats['removed']}")
    print(f"  Removed chars: {stats['removed_chars']:,}")
    return stats


# ============================================================
# STAGE 3: Quality Filter
# ============================================================

BOILERPLATE_PATTERNS = [
    "this website uses cookies",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "terms and conditions",
    "all rights reserved",
    "copyright (c)",
    "cookie consent",
    "subscribe to our newsletter",
]


def quality_check(text):
    """Quality filter: check document quality."""
    if len(text) < 300:
        return False, "too_short"
    if len(text) > 5_000_000:
        return False, "too_long"
    text_lower = text.lower()[:5000]
    boilerplate_matches = sum(1 for p in BOILERPLATE_PATTERNS if p in text_lower)
    if boilerplate_matches > 2:
        return False, "boilerplate"
    alpha_count = sum(1 for c in text if c.isalpha())
    alpha_ratio = alpha_count / len(text)
    if alpha_ratio < 0.40:
        return False, "low_alpha_ratio"
    word_chars = sum(1 for c in text if c.isalnum() or c in " .,!?;:'\"()[]")
    word_ratio = word_chars / len(text)
    if word_ratio < 0.50:
        return False, "low_word_ratio"
    paragraphs = [p for p in text.split("\n\n") if len(p.strip()) > 50]
    if len(paragraphs) < 2:
        # Fall back: split on single newlines for HTML-stripped/plain text
        # that uses single newlines between sentences/paragraphs.
        # Group consecutive non-empty lines into blocks separated by
        # content that looks like paragraph boundaries.
        single_lines = text.split("\n")
        blocks = []
        current = []
        for line in single_lines:
            stripped = line.strip()
            if stripped:
                current.append(stripped)
            else:
                if current:
                    block = " ".join(current)
                    if len(block) > 50:
                        blocks.append(block)
                    current = []
        if current:
            block = " ".join(current)
            if len(block) > 50:
                blocks.append(block)
        # If still only one giant block, try splitting on sentence-like
        # boundaries to detect paragraph structure
        if len(blocks) < 2 and len(text) > 5000:
            # Split by lines and group into chunks of ~5 lines as pseudo-paragraphs
            all_lines = [l.strip() for l in single_lines if l.strip() and len(l.strip()) > 20]
            if len(all_lines) >= 5:
                chunk_size = max(1, len(all_lines) // (len(all_lines) // 5 + 1))
                paragraphs = []
                for i in range(0, len(all_lines), max(3, len(all_lines) // 10)):
                    chunk = " ".join(all_lines[i:i + max(3, len(all_lines) // 10)])
                    if len(chunk) > 50:
                        paragraphs.append(chunk)
        else:
            paragraphs = blocks
        if len(paragraphs) < 2:
            return False, "no_paragraphs"
    return True, "ok"


def stage_quality_filter(input_file, output_file):
    """Stage 3: Quality filter documents."""
    print("=== Stage 3: Quality Filter ===")
    stats = {"total": 0, "kept": 0, "removed": 0, "reasons": defaultdict(int)}

    with open(input_file, "r", encoding="utf-8") as in_f, \
         open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            stats["total"] += 1
            ok, reason = quality_check(record["text"])
            if ok:
                stats["kept"] += 1
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                stats["removed"] += 1
                stats["reasons"][reason] += 1
                if reason != "too_short":
                    print(f"  Removed ({reason}): {record['source']}/{record.get('document_id', '?')[:50]}")

    print(f"  Total: {stats['total']}, Kept: {stats['kept']}, Removed: {stats['removed']}")
    print(f"  Reasons: {dict(stats['reasons'])}")
    return stats


# ============================================================
# STAGE 4: Deduplication
# ============================================================

def stage_dedup(input_file, output_file):
    """Stage 4: Remove exact and near-duplicate documents."""
    print("=== Stage 4: Deduplication ===")
    stats = {"total": 0, "kept": 0, "exact_dups": 0, "near_dups": 0}
    seen_hashes = set()
    seen_fingerprints = set()

    with open(input_file, "r", encoding="utf-8") as in_f, \
         open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            stats["total"] += 1
            text = record["text"]
            full_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if full_hash in seen_hashes:
                stats["exact_dups"] += 1
                continue
            fingerprint = hashlib.sha256(text[:300].encode("utf-8")).hexdigest()
            if fingerprint in seen_fingerprints:
                stats["near_dups"] += 1
                print(f"  Near dup: {record['source']}/{record.get('document_id', '?')[:50]}")
                continue
            seen_hashes.add(full_hash)
            seen_fingerprints.add(fingerprint)
            stats["kept"] += 1
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"  Total: {stats['total']}, Kept: {stats['kept']}")
    print(f"  Exact dups removed: {stats['exact_dups']}")
    print(f"  Near dups removed: {stats['near_dups']}")
    return stats


# ============================================================
# STAGE 5: PII Reduction
# ============================================================

def redact_pii(text):
    """Redact PII: emails, phone numbers, IP addresses."""
    redactions = 0
    text, n = re.subn(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)
    redactions += n
    text, n = re.subn(r"\b(\d{3}[-.]?){2}\d{4}\b", "[PHONE]", text)
    redactions += n
    text, n = re.subn(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", text)
    redactions += n
    return text, redactions


def stage_pii_reduce(input_file, output_file):
    """Stage 5: Redact PII."""
    print("=== Stage 5: PII Reduction ===")
    stats = {"total": 0, "redactions": 0}
    with open(input_file, "r", encoding="utf-8") as in_f, \
         open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            stats["total"] += 1
            text, n = redact_pii(record["text"])
            record["text"] = text
            record["pii_redactions"] = n
            if n > 0:
                stats["redactions"] += n
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"  Total: {stats['total']}, Redactions: {stats['redactions']}")
    return stats


# ============================================================
# STAGE 6: Tokenization & Statistics
# ============================================================

def stage_tokenize(input_file, output_file):
    """Stage 6: Tokenize documents and compute statistics."""
    print("=== Stage 6: Tokenization ===")
    print(f"  Loading tokenizer: {TOKENIZER_PATH}")
    tokenizer = sw.BPETokenizer.from_file(str(TOKENIZER_PATH))
    print(f"  Tokenizer loaded: vocab_size={tokenizer.vocab_size}")

    stats = {
        "total": 0,
        "total_tokens": 0,
        "total_chars": 0,
        "by_source": defaultdict(lambda: {"docs": 0, "tokens": 0, "chars": 0}),
    }

    with open(input_file, "r", encoding="utf-8") as in_f, \
         open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            stats["total"] += 1
            stats["total_chars"] += len(record["text"])
            stats["by_source"][record["source"]]["docs"] += 1
            stats["by_source"][record["source"]]["chars"] += len(record["text"])
            token_ids = tokenizer.encode(record["text"])
            n_tokens = len(token_ids)
            stats["total_tokens"] += n_tokens
            stats["by_source"][record["source"]]["tokens"] += n_tokens
            out_f.write(json.dumps({
                "source": record["source"],
                "document_id": record["document_id"],
                "chars": len(record["text"]),
                "tokens": n_tokens,
                "text_preview": record["text"][:200],
            }, ensure_ascii=False) + "\n")

    stats["by_source"] = {k: dict(v) for k, v in stats["by_source"].items()}
    print(f"  Total documents: {stats['total']}")
    print(f"  Total tokens: {stats['total_tokens']:,}")
    print(f"  Total chars: {stats['total_chars']:,}")
    print(f"  Chars/token: {stats['total_chars'] / max(stats['total_tokens'], 1):.2f}")
    for src, s in stats["by_source"].items():
        print(f"    {src}: {s['docs']} docs, {s['tokens']:,} tokens")
    return stats


# ============================================================
# STAGE 7: Concatenation, Packing & Split
# ============================================================

def stage_pack_and_split(input_file, tokenizer):
    """Stage 7: Concatenate, tokenize, pack, and split."""
    print("=== Stage 7: Pack & Split ===")

    all_tokens = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            ids = tokenizer.encode(record["text"])
            all_tokens.extend(ids)

    print(f"  Total tokens: {len(all_tokens):,}")
    split_idx = int(len(all_tokens) * 0.98)
    train_tokens = all_tokens[:split_idx]
    val_tokens = all_tokens[split_idx:]

    print(f"  Train tokens: {len(train_tokens):,}")
    print(f"  Val tokens: {len(val_tokens):,}")

    max_seq_len = 256
    n_train_seqs = len(train_tokens) // max_seq_len
    n_val_seqs = len(val_tokens) // max_seq_len

    train_tokens = train_tokens[:n_train_seqs * max_seq_len]
    val_tokens = val_tokens[:n_val_seqs * max_seq_len]

    print(f"  Train sequences: {n_train_seqs:,} ({len(train_tokens):,} tokens)")
    print(f"  Val sequences: {n_val_seqs:,} ({len(val_tokens):,} tokens)")

    train_path = PROC_DIR / "train.txt"
    val_path = PROC_DIR / "val.txt"

    with open(train_path, "w", encoding="utf-8") as f:
        for i in range(n_train_seqs):
            seq = train_tokens[i * max_seq_len:(i + 1) * max_seq_len]
            text = tokenizer.decode(seq)
            f.write(text)

    with open(val_path, "w", encoding="utf-8") as f:
        for i in range(n_val_seqs):
            seq = val_tokens[i * max_seq_len:(i + 1) * max_seq_len]
            text = tokenizer.decode(seq)
            f.write(text)

    return {
        "train_sequences": n_train_seqs,
        "val_sequences": n_val_seqs,
        "train_tokens": len(train_tokens),
        "val_tokens": len(val_tokens),
        "total_tokens": len(all_tokens),
        "max_seq_len": max_seq_len,
    }


# ============================================================
# Dataset Manifest Generation
# ============================================================

def sha256_file(filepath):
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    """Compute SHA256 hash of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_manifest(stage_stats):
    """Generate dataset_manifest.json with full provenance."""
    print("=== Generating Dataset Manifest ===")

    # Hash the raw source files
    source_info = {}
    raw_dir = RAW_DIR
    for source_name in ["wikipedia", "gutenberg", "wikibooks"]:
        source_dir = raw_dir / source_name
        if not source_dir.exists():
            continue
        docs = 0
        chars = 0
        files = []
        for f in sorted(source_dir.iterdir()):
            if f.suffix in (".jsonl", ".txt"):
                docs += 1
                files.append(f.name)
                try:
                    with open(f, "r", encoding="utf-8", errors="replace") as fh:
                        chars += len(fh.read())
                except Exception:
                    pass
        source_info[source_name] = {
            "files": files,
            "documents": docs,
            "chars": chars,
        }

    total_tokens = stage_stats.get("total_tokens", 0)
    train_tokens = stage_stats.get("train_tokens", 0)
    val_tokens = stage_stats.get("val_tokens", 0)

    # Hash the processed outputs
    train_path = PROC_DIR / "train.txt"
    val_path = PROC_DIR / "val.txt"

    manifest = {
        "dataset_name": "silverwing-training-corpus-v1",
        "dataset_version": "1.0.0",
        "created": __import__("datetime").datetime.now().isoformat(),
        "tokenizer": {
            "name": "silverwing-bpe-tokenizer-v1",
            "path": str(TOKENIZER_PATH),
            "sha256": sha256_file(TOKENIZER_PATH) if TOKENIZER_PATH.exists() else None,
            "vocab_size": sw.BPETokenizer.from_file(str(TOKENIZER_PATH)).vocab_size if TOKENIZER_PATH.exists() else None,
        },
        "sources": source_info,
        "total_documents": sum(s["documents"] for s in source_info.values()),
        "total_chars": sum(s["chars"] for s in source_info.values()),
        "total_tokens": total_tokens,
        "splits": {
            "train": {
                "tokens": train_tokens,
                "sequences": stage_stats.get("train_sequences", 0),
                "max_seq_len": stage_stats.get("max_seq_len", 256),
                "file": str(train_path),
                "sha256": sha256_file(train_path) if train_path.exists() else None,
            },
            "validation": {
                "tokens": val_tokens,
                "sequences": stage_stats.get("val_sequences", 0),
                "max_seq_len": stage_stats.get("max_seq_len", 256),
                "file": str(val_path),
                "sha256": sha256_file(val_path) if val_path.exists() else None,
            },
        },
        "split_ratio": "98% train / 2% validation",
        "processing_pipeline": [
            "normalize (Unicode NFKC, encoding fix, whitespace cleanup)",
            "language_filter (keep English/Mixed, remove non-English)",
            "quality_filter (min 300 chars, alpha ratio >= 0.40, paragraph check, boilerplate removal)",
            "dedup (exact SHA256 + near-duplicate first-300-char fingerprint)",
            "pii_reduction (email/phone/IP redaction)",
            "tokenization (Silverwing BPE, vocab=8192)",
            "pack_and_split (256-token sequences, 98/2 split)",
        ],
        "filtering_statistics": {
            "normalize": stage_stats.get("normalize_stats", {}),
            "language_filter": stage_stats.get("lang_stats", {}),
            "quality_filter": stage_stats.get("quality_stats", {}),
            "dedup": stage_stats.get("dedup_stats", {}),
            "pii_reduction": stage_stats.get("pii_stats", {}),
            "tokenization": stage_stats.get("tokenize_stats", {}),
        },
        "license": "CC-BY-SA 3.0 (Wikipedia), Public Domain (Gutenberg, Project Gutenberg)",
        "notes": "Validation data is held out from training. No validation contamination. "
                 "Split is deterministic: last 2% of concatenated token stream.",
    }

    # Add per-source token counts from tokenization stats
    tok_stats = stage_stats.get("tokenize_stats", {})
    if "by_source" in tok_stats:
        for src, s in tok_stats["by_source"].items():
            if src in source_info:
                source_info[src]["tokens"] = s.get("tokens", 0)

    manifest_path = PROC_DIR / "dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"  Manifest written to: {manifest_path}")
    print(f"  Total tokens: {total_tokens:,}")
    print(f"  Train tokens: {train_tokens:,}")
    print(f"  Val tokens: {val_tokens:,}")
    return manifest


# ============================================================
# Main Pipeline Runner
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SILVERWING PHASE 3 — DATA QUALITY PIPELINE")
    print("=" * 60)

    all_stats = {}

    # Stage 1: Normalize
    norm_stats = stage_normalize()
    all_stats["normalize_stats"] = norm_stats

    # Stage 2: Language Filter
    stage_language_filter(
        PROC_DIR / "01_normalized.jsonl",
        PROC_DIR / "02_language_filtered.jsonl"
    )

    # Stage 3: Quality Filter
    stage_quality_filter(
        PROC_DIR / "02_language_filtered.jsonl",
        PROC_DIR / "03_quality_filtered.jsonl"
    )

    # Stage 4: Deduplication
    stage_dedup(
        PROC_DIR / "03_quality_filtered.jsonl",
        PROC_DIR / "04_deduped.jsonl"
    )

    # Stage 5: PII Reduction
    stage_pii_reduce(
        PROC_DIR / "04_deduped.jsonl",
        PROC_DIR / "05_pii_reduced.jsonl"
    )

    # Stage 6: Tokenization & Statistics
    tok_stats = stage_tokenize(
        PROC_DIR / "05_pii_reduced.jsonl",
        PROC_DIR / "06_tokenized_stats.jsonl"
    )
    all_stats["tokenize_stats"] = tok_stats

    # Stage 7: Pack & Split (needs tokenizer)
    print("=== Stage 7: Pack & Split ===")
    tokenizer = sw.BPETokenizer.from_file(str(TOKENIZER_PATH))
    pack_stats = stage_pack_and_split(
        PROC_DIR / "05_pii_reduced.jsonl",
        tokenizer
    )
    all_stats.update(pack_stats)

    # Generate manifest
    all_stats["normalize_stats"] = norm_stats
    manifest = generate_manifest(all_stats)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Total tokens: {pack_stats['total_tokens']:,}")
    print(f"  Train tokens: {pack_stats['train_tokens']:,}")
    print(f"  Val tokens:   {pack_stats['val_tokens']:,}")
    print(f"  Train file:   {PROC_DIR / 'train.txt'}")
    print(f"  Val file:     {PROC_DIR / 'val.txt'}")
    print(f"  Manifest:     {PROC_DIR / 'dataset_manifest.json'}")
    print("=" * 60)
