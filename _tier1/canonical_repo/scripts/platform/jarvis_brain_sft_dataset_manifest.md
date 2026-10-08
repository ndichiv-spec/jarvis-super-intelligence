# JARVIS BRAIN v1 - SFT Dataset Manifest

- label: `jarvis-brain-qwen3-4b-sft-v1`
- corpus: `01_normalized.jsonl` (292 passages)
- sources: {"wikipedia": 231, "gutenberg": 45, "wikibooks": 16}
- eval-excluded passages: 0 (leakage prevention)
- synthesized passages excluded: 0

| split | examples | tokens |
|---|---|---|
| train | 238 | 8449295 |
| validation | 22 | 456005 |
| test | 32 | 1368391 |

- token total: 10273691 (min 234 / max 651259 / mean 35183.9)
- tokenizer: Qwen3 BPE (qwen3 token_type=pretok) (sha256 aeb13307a71acd8f)

SFT categories: general conversation, technical communication, coding, debugging, mathematics, reasoning, engineering, research, planning, tool use, verification, summarization, structured output

Synthesis (Kaggle kernel): assistant turns are generated THERE with your Brain key. This manifest is the dataset registry + integrity plan only.
