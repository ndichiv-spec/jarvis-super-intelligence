"""Perplexity evaluation for Silverwing.

Computes validation perplexity on a held-out text dataset.
"""
from __future__ import annotations

import math
import torch
from torch.utils.data import DataLoader


@torch.no_grad()
def compute_perplexity(model, tokenizer, text_dataset, batch_size: int = 2,
                       max_length: int = 2048, device: str = "cpu") -> float:
    """Compute perplexity on a text dataset.

    Args:
        model: SilverwingModel instance
        tokenizer: tokenizer with encode() method
        text_dataset: list of text strings
        batch_size: evaluation batch size
        max_length: maximum sequence length
        device: 'cpu' or 'cuda'

    Returns:
        Perplexity (float)
    """
    model.eval()

    total_loss = 0.0
    total_tokens = 0

    for i in range(0, len(text_dataset), batch_size):
        batch_texts = text_dataset[i:i + batch_size]
        input_ids = []
        for text in batch_texts:
            ids = tokenizer.encode(text, max_length=max_length, truncation=True)
            # Add BOS and EOS
            ids = [tokenizer.bos_token_id] + ids + [tokenizer.eos_token_id]
            input_ids.append(ids)

        max_len = max(len(ids) for ids in input_ids)
        padded = torch.full((len(input_ids), max_len), tokenizer.pad_token_id,
                            dtype=torch.long, device=device)
        for j, ids in enumerate(input_ids):
            padded[j, :len(ids)] = torch.tensor(ids)

        with torch.autocast(device_type=device, enabled=False):
            outputs = model(padded, labels=padded)
            loss = outputs["loss"]
            # Count non-pad tokens
            num_tokens = (padded != tokenizer.pad_token_id).sum().item()

        total_loss += loss.item() * num_tokens
        total_tokens += num_tokens

    avg_loss = total_loss / max(total_tokens, 1)
    perplexity = math.exp(min(avg_loss, 20.0))  # Cap to avoid overflow
    return perplexity


@torch.no_grad()
def generate_sample(model, tokenizer, prompt: str, max_new_tokens: int = 50,
                    temperature: float = 0.8, top_p: float = 0.9,
                    device: str = "cpu") -> str:
    """Generate text from a prompt for qualitative evaluation."""
    model.eval()

    input_ids = tokenizer.encode(prompt, return_tensors="pt")
    input_ids = input_ids.to(device)

    with torch.autocast(device_type=device, enabled=False):
        generated = model.generate(
            input_ids=input_ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=True,
        )

    # Decode the generated text (skip the prompt)
    generated_text = tokenizer.decode(generated[0][input_ids.shape[1]:])
    return generated_text
