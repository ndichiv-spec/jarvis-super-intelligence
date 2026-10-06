# Dataset Improvement Pipeline

## Overview

The Dataset Improvement Pipeline is responsible for extracting, validating, and
curating failure examples from evaluation results to create training datasets
for model improvement cycles.

## Pipeline Flow

```
Evaluation Results
    → FailureExtractor (DatasetImprovementLoop.extract_failures)
    → DatasetQualityGate.run_pipeline()
        ├── Schema Validation
        ├── Safety / Contamination Check
        ├── Deduplication
        ├── Answer Validation + Provenance
        └── Size / Budget Check
    → Versioned Dataset
```

## DatasetImprovementLoop

The `DatasetImprovementLoop` class orchestrates the full pipeline:

### extract_failures(evaluation_results, target_capability)

Extracts failure examples from evaluation results — **never fabricates**.

Two extraction paths:
1. **From metrics**: If a metric has `provenance`, it's recorded as evidence:
   ```python
   {
       "prompt": "accuracy",
       "response": "value=0.75, sample_count=200",
       "category": target_capability,
       "source": "evaluation_metrics",
       "provenance": ["eval:math_v1"],
   }
   ```

2. **From detailed results**: If a result item has `score.pass == False`:
   ```python
   {
       "prompt": item["prompt"],
       "response": item["answer"],
       "category": item.get("category", target_capability),
       "source": "eval:<suite_name>",
       "provenance": ["extracted_from_failure"],
   }
   ```

### run(evaluation_results, target_capability)

Full pipeline: extract → quality gate → version.

Returns:
```python
{
    "passed": True/False,
    "dataset": {...},
    "issues": [...],
    "stage": "validated" / "failed",
}
```

## DatasetQualityGate

### Schema Fields

Required fields for each example:
- `prompt`: The input prompt
- `response`: The model's response
- `category`: Capability category
- `source`: Source of the example

### Quality Gate Stages

| Stage | Check | Rejection Criteria |
|-------|-------|-------------------|
| 1. Schema Validation | All 4 required fields present and non-empty | Missing field |
| 2. Safety/Contamination | No harmful content, no training data references | Harmful patterns, contamination |
| 3. Deduplication | SHA256 hash of prompt+response | Exact duplicates removed |
| 4. Answer Validation | Response is non-empty, provenance assigned | Empty response |
| 5. Size/Budget | 5 ≤ examples ≤ 50000 | Too few or too many |

### Safety Patterns Blocked

- `how to make a bomb`
- `how to hack`
- `illegal`
- `self-harm`
- `kill myself`

### Contamination Patterns Blocked

- `training data`
- `training_data`

## Versioning

After passing the quality gate, the dataset is versioned:

```python
cycle.dataset["version"] = f"v1_{short_uuid()}"
```

## Integration

The curated dataset is stored in the `SelfImprovementCycle.dataset` field and
used by:

1. `establish_baseline()` — for baseline lock dataset_id
2. `train_candidate()` — as training data
3. `evaluate_improvement()` — for evaluation

## No-Fabrication Guarantees

1. Only extracts what was actually observed in evaluation results
2. No synthetic data generation
3. Every example has provenance tracing
4. Safety check prevents harmful data from entering training
5. Contamination check prevents training data leakage
6. Answer validation ensures non-empty responses
7. Deduplication prevents duplicate examples inflating metrics
