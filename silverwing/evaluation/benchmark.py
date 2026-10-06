"""Simple evaluation benchmarks for Silverwing.

Tests basic language model capabilities:
- grammar / coherence
- factual pattern recall
- simple arithmetic
- simple coding patterns
"""
from __future__ import annotations

import torch


def evaluate_grammar(model, tokenizer, device: str = "cpu") -> dict:
    """Evaluate basic grammar and coherence."""
    prompts = [
        "The cat sat on the",
        "In the morning, the bird",
        "She walked to the store and",
        "The algorithm sorted the",
    ]
    results = {"passed": 0, "total": len(prompts), "samples": []}
    for prompt in prompts:
        # Encode and generate
        ids = tokenizer.encode(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=15, temperature=0.8, do_sample=True)
        text = tokenizer.decode(gen[0])
        results["samples"].append({"prompt": prompt, "completion": text})
    return results


def evaluate_arithmetic(model, tokenizer, device: str = "cpu") -> dict:
    """Evaluate basic arithmetic reasoning."""
    questions = [
        ("What is 2 + 2?", "4"),
        ("What is 5 * 3?", "15"),
        ("What is 10 - 7?", "3"),
        ("What is 4 / 2?", "2"),
    ]
    results = {"passed": 0, "total": len(questions), "details": []}
    for q, expected in questions:
        ids = tokenizer.encode(q, return_tensors="pt").to(device)
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=10, temperature=0.3, do_sample=True)
        answer = tokenizer.decode(gen[0][ids.shape[1]:])
        correct = expected.strip() in answer
        if correct:
            results["passed"] += 1
        results["details"].append({"question": q, "expected": expected, "answer": answer, "correct": correct})
    return results


def evaluate_facts(model, tokenizer, device: str = "cpu") -> dict:
    """Evaluate basic factual recall."""
    questions = [
        ("Capital of France?", "Paris"),
        ("Largest planet in our solar system?", "Jupiter"),
        ("Chemical symbol for water?", "H2O"),
    ]
    results = {"passed": 0, "total": len(questions), "details": []}
    for q, expected in questions:
        ids = tokenizer.encode(q, return_tensors="pt").to(device)
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=15, temperature=0.7, do_sample=True)
        answer = tokenizer.decode(gen[0][ids.shape[1]:])
        correct = expected.lower().strip() in answer.lower()
        if correct:
            results["passed"] += 1
        results["details"].append({"question": q, "expected": expected, "answer": answer, "correct": correct})
    return results


def run_all_benchmarks(model, tokenizer, device: str = "cpu") -> dict:
    """Run all evaluation benchmarks and return results."""
    results = {
        "grammar": evaluate_grammar(model, tokenizer, device),
        "arithmetic": evaluate_arithmetic(model, tokenizer, device),
        "facts": evaluate_facts(model, tokenizer, device),
    }
    return results
