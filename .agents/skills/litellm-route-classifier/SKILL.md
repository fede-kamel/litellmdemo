---
name: litellm-route-classifier
description: Use when generating routing data, labelling it by outcome, mini-training, evaluating, or plugging in the routing classifier that LiteLLM's complexity router calls as classifier_type custom - classifier/generate.py, label.py, train.py, evaluate.py, router_model.py and gateway/trained_classifier.py.
metadata:
  author: federico-kamelhar
  version: "1.0"
compatibility: sentence-transformers, scikit-learn, py3langid; the gateway on 127.0.0.1:4000 for generate, label and evaluate
---

# The routing classifier: data, labels, training, plug-in

## Criteria it routes on

1. **Rules** for facts the request states (`classifier/router_model.py`):
   an image part → `VISION`; more than 120,000 characters → `LONG_CONTEXT`;
   not English (py3langid) → `MULTILINGUAL`.
2. **A mini-trained model** for what the request needs: multilingual-e5-small
   embeddings (local, CPU, ~10 ms) and a logistic-regression head predicting
   `SIMPLE`, `MEDIUM`, `REASONING` or `CODE`.
3. **Labels come from outcomes, not opinions**: the cheapest route whose
   answer the judge passes (correctness, completeness, instruction-following,
   each ≥ 4 of 5).

## Pipeline

```shell
uv run python classifier/generate.py     # ~312 prompts via oci-judge      -> data/prompts.jsonl
uv run python classifier/label.py        # 3 routes answer, judge grades   -> data/labels.jsonl  (resumable)
uv run python classifier/train.py        # seconds                         -> model/head.joblib, model/meta.json
uv run python classifier/evaluate.py     # policies on held-out prompts    -> evidence/classifier-eval.json
```

`label.py` costs about $5 in OCI calls and takes ~20 minutes at
`LITELLMDEMO_CONCURRENCY=24`; it resumes where it stopped. `generate.py`
overwrites `prompts.jsonl`: never rerun it unless asked, the labels depend on it.

## Plugging it in

`gateway/config.yaml`, group `oci-auto-trained`:

```yaml
complexity_router_config:
  classifier_type: custom
  classifier_plugin: trained_classifier.plugin     # gateway/trained_classifier.py
  classifier_plugin_timeout_ms: 2000
  fallback_tier: MEDIUM
  tier_definitions: [...]                          # the 8 routes
  tiers: {SIMPLE: oci-fast, ..., MULTILINGUAL: oci-multilingual}
```

The plugin warms the encoder when the gateway starts (loading takes longer
than the timeout) and appends each decision to `out/route-decisions.jsonl`.
After retraining, restart the gateway and the web app: both hold the model
in memory.

## Acceptance

- `train.py` held-out accuracy is reported, not tuned to: report the number
  and the confusion matrix as they are.
- `evaluate.py`: the trained policy's quality must be within 5 points of
  "always COMPLEX" at lower cost; say so plainly if it is not.
- `scripts/probe_routes.py`: the `trained:` probes pass.

## Moving training to an OCI GPU

The scripts run unchanged on a GPU node with a larger encoder
(`ENCODER` in `router_model.py`). Do not create or use any cluster or GPU
instance without the operator's explicit go-ahead naming it.
