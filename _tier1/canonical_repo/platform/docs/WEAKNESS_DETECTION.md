# Weakness Detection & Failure Analysis

## Overview

Weakness detection is the first step in the JARVIS self-improvement loop. It
identifies regressions, capability gaps, and failure patterns by comparing
baseline model performance against candidate model performance.

## Failure Taxonomy

Failures are classified into 12 categories:

| Category | Description |
|----------|-------------|
| `METRIC_REGRESSION` | A metric value dropped compared to baseline |
| `CAPABILITY_GAP` | A capability that was not demonstrated |
| `SAFETY_VIOLATION` | An unsafe or harmful output was generated |
| `BIAS_DETECTED` | Bias detected in outputs |
| `HALLUCINATION` | Factual hallucination in outputs |
| `CONFIDENTIALITY_BREACH` | Confidential information leaked in output |
| `INSTRUCTION_HIJACKING` | Model followed injected instructions over system prompt |
| `ROBUSTNESS_FAILURE` | Model failed on perturbed/edge case inputs |
| `LATENCY_REGRESSION` | Inference latency increased beyond threshold |
| `THROUGHPUT_DEGRADATION` | Throughput decreased beyond threshold |
| `COST_OVERRUN` | Compute costs exceeded budget |
| `DEPENDENCY_FAILURE` | External dependency (tool/API) failed |

## Failure Severity

| Level | Threshold | Description |
|-------|-----------|-------------|
| `LOW` | < 5% regression | Minor degradation, below minimum improvement threshold |
| `MEDIUM` | 5%–15% regression | Noticeable degradation |
| `HIGH` | 15%–30% regression | Significant degradation |
| `CRITICAL` | > 30% regression | Severe degradation |

## Weakness Classification

The `FailureTaxonomy.classify()` method determines failure category and severity
based on:

- Capability name
- Metric name
- Baseline value vs current value
- `higher_is_better` flag
- `regression_threshold` (default 5%)

```python
category, severity = FailureTaxonomy.classify(
    capability="math_reasoning",
    metric_name="accuracy",
    baseline_value=0.88,
    current_value=0.72,
    higher_is_better=True,
    regression_threshold=0.05,
)
# Returns: (FailureCategory.METRIC_REGRESSION, FailureSeverity.CRITICAL)
```

## Weakness Detection Algorithm

1. Compare baseline and candidate evaluation results metric-by-metric.
2. For each metric with `evaluation_version` matching:
   - Compute relative delta: `(candidate - baseline) / baseline` (or inverted for lower-is-better)
   - If `|relative_delta| >= min_regression` and it's a regression:
     - Classify using `FailureTaxonomy.classify()`
     - Create a `FailureInstance` with actual values (never fabricated)
     - Create a `Weakness` aggregating all failures for the same capability+category+severity
3. Cluster weaknesses by category+severity into `cluster_id`.

## Failure Clustering

Weaknesses are automatically clustered by `(category, severity)` hash:

```python
cluster_id = f"cluster_{md5(f'{category}_{severity}').hexdigest()[:12]}"
```

This enables the system to group similar weaknesses across multiple evaluation
runs, forming a directed acyclic graph of improvement efforts.

## WeaknessDetector

```python
detector = WeaknessDetector()
weaknesses = detector.detect_from_results(
    baseline_results={...},
    candidate_results={...},
    min_regression=0.05,  # 5% minimum relative regression
)
```

Key properties:
- **No fabrication**: Only reports actual metric regressions, never invents them
- **Version matching**: Only compares metrics with matching `evaluation_version`
- **Population awareness**: Confidence is derived from actual sample counts
- **Provenance tracking**: Each failure includes evidence provenance

## No-Fabrication Guarantees

1. WeaknessDetector never reports a weakness for improved metrics
2. WeaknessDetector returns empty list for empty baseline or candidate results
3. FailureInstance stores exact `baseline_value` and `current_value` — no estimates
4. Evidence strings contain actual measured values, no "fabricated" or "estimated"
   language
5. Confidence is derived from regression magnitude, not sample size assumptions
