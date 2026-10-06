---
base_model:
- Qwen/Qwen3-4B-Base
library_name: peft
tags:
- qwen3
- qwen
- lora
- jarvis
- jarvis-brain
- sft
---

# JARVIS Brain — Qwen3-4B SFT Adapter

This repository contains the JARVIS Brain LoRA/PEFT adapter trained on top of:

`Qwen/Qwen3-4B-Base`

Adapter:

- PEFT type: LoRA
- Rank: 64
- Alpha: 128
- Dropout: 0.1
- Target modules: q_proj, k_proj, o_proj, v_proj
- Task: CAUSAL_LM

This repository is an adapter artifact, not a standalone base model.

JARVIS must verify:

1. Base model availability.
2. Adapter loadability.
3. Inference.
4. Evaluation benchmark.
5. Promotion status.

It must not mark this artifact READY merely because it exists in the Hub.

Training and evaluation provenance is maintained by the JARVIS control plane.
