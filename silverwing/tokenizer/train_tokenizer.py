"""Silverwing tokenizer training script.

Trains a BPE tokenizer with 16,384 vocabulary on available training text.
Uses HuggingFace's fast tokenizers library (Rust backend).
"""
import os
import sys
import json
import math
from pathlib import Path

from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.post_processors import ByteLevel as ByteLevelPost
from tokenizers.decoders import ByteLevel as ByteLevelDecoder
from tokenizers.processors import TemplateProcessing


def build_tokenizer(vocab_size: int = 16384) -> Tokenizer:
    """Create a BPE tokenizer with the specified vocab size."""
    tokenizer = Tokenizer(BPE(unk_token="<unk>"))

    # ByteLevel pre-tokenization (compatible with byte-level encoding)
    tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=True, use_regex=True)

    # ByteLevel post-processing (adds </s> and converts to byte-level format)
    tokenizer.post_processor = ByteLevelPost(trim_offsets=True)

    # ByteLevel decoder
    tokenizer.decoder = ByteLevelDecoder()

    # Trainer with special tokens
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=2,
        special_tokens=["<pad>", "<bos>", "<eos>", "<unk>"],
        show_progress=True,
        initial_alphabet=ByteLevel.alphabet(),
    )

    # Templates for chat-style formatting
    tokenizer.post_processor = TemplateProcessing(
        single="<bos> $A <eos>",
        pair="<bos> $A <eos>",
        special_tokens=[
            ("<pad>", 0),
            ("<bos>", 1),
            ("<eos>", 2),
            ("<unk>", 3),
        ],
    )

    return tokenizer, trainer


def train_tokenizer(input_files, vocab_size=16384, output_dir="./tokenizer"):
    """Train a BPE tokenizer from text files."""
    os.makedirs(output_dir, exist_ok=True)

    tokenizer, trainer = build_tokenizer(vocab_size)
    tokenizer.train(files=input_files, trainer=trainer)

    # Save the tokenizer
    tokenizer_path = os.path.join(output_dir, "tokenizer.json")
    tokenizer.save(tokenizer_path)

    # Save config
    config = {
        "type": "bpe",
        "vocab_size": vocab_size,
        "special_tokens": {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3},
        "byte_level": True,
        "version": "1.0.0",
    }
    with open(os.path.join(output_dir, "tokenizer_config.json"), "w") as f:
        json.dump(config, f, indent=2)

    # Save manifest
    manifest = {
        "tokenizer_hash": compute_file_hash(tokenizer_path),
        "vocab_size": vocab_size,
        "special_tokens": {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3},
        "version": "1.0.0",
        "training_data": input_files,
    }
    with open(os.path.join(output_dir, "tokenizer_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Tokenizer trained: {tokenizer_path}")
    print(f"Vocabulary size: {tokenizer.get_vocab_size()}")
    return tokenizer_path


def compute_file_hash(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    # Find training data
    data_files = []
    for pattern in ["data/processed/*.txt", "data/splits/*.txt",
                     "/kaggle/working/data/processed/*.txt"]:
        for f in Path(".").glob(pattern):
            data_files.append(str(f))

    if not data_files:
        print("No training data found. Using embedded sample.")
        # Write a small sample
        sample = Path("/tmp/sample_data.txt")
        sample.write_text("Hello world. This is a sample text for tokenizer training.\n")
        data_files = [str(sample)]

    train_tokenizer(data_files, vocab_size=16384, output_dir="tokenizer")
