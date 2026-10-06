---
name: litellm-route-classifier
description: Use when changing how requests are routed by need - the outcome labels, the ladder router, the quality bar, retraining after a model swap, the model trial, the robustness test - classifier/label.py, ladder.py, train.py, evaluate.py, model_trial.py, robustness.py, router_model.py and gateway/trained_classifier.py.
metadata:
  author: federico-kamelhar
  version: "2.0"
compatibility: sentence-transformers, scikit-learn, py3langid; the laptop gateway on 127.0.0.1:4000 (OCI session) for labelling and evaluation
---

# The router: outcome labels, the ladder, the quality bar

## How a route is decided

1. **Rules** (`classifier/router_model.py`): an image → `VISION`; more than
   120,000 characters → `LONG_CONTEXT`; not English with at least 50%
   confidence (py3langid) → `MULTILINGUAL`.
2. **Code check**: a logistic head on multilingual-e5-small embeddings sends
   programming requests to `CODE` (GPT-5.3-codex).
3. **The ladder** (`classifier/ladder.py`): for each route, the chance its
   answer is good enough: a logistic model on the embedding and seven
   difficulty signals, averaged with the pass rates of the 12 most similar
   labelled prompts. The cheapest route at least as likely as the quality bar
   wins; if none is, the most likely one. Training chose the route set
   (fast, balanced, reasoning) and the bar (75%).

LiteLLM calls it as the complexity router's `classifier_type: custom`
(`gateway/trained_classifier.py`, through the `route-classifier` service on
Kubernetes). A request may set its own bar: `metadata.route_quality_bar`.
The decision returns in `x-litellm-route-decision`.

## Labels come from outcomes

Every route answers every prompt through the gateway; GPT-5.2 grades each
answer on correctness, completeness and instruction-following (1-5); pass =
all at least 4. Three runs per route (one for the reasoning route) give each
prompt a pass rate per route. A single run is a coin flip for a third of the
prompts; never train on one label.

## When the portfolio changes (a model swapped into a ladder route)

The pass rates belong to the models that answered. Swap a model, relabel:

```shell
uv run python classifier/model_trial.py                 # pick the model: same 40 prompts, one judge (~$5)
# edit gateway/config.yaml, restart the gateway, run the probes
# move the outcome labels aside, keep the CODE and MULTILINGUAL ones, then (~$18):
uv run python classifier/label.py && uv run python classifier/label.py --votes 3 && uv run python classifier/label.py --reasoning
uv run python classifier/train.py                       # the ladder, its route set and bar, scored once on held-out
uv run python classifier/evaluate.py                    # through the gateway, against LiteLLM's built-in routers
uv run python classifier/ladder_lab.py                  # cross-validated comparison of predictors and bars
```

Before relabelling, move `out/relabel-sample.json` and
`evidence/classifier-eval.json` aside: both hold old-model results that the
scripts would otherwise reuse. Ask before spending: labelling, the trial and
the robustness test are paid OCI calls.

## Does it hold up

`classifier/robustness.py` (~$15): 150 fresh prompts written by a model
outside the portfolio, every route answers, two judges from different vendors
grade, plus code and vision quality checks. Report under both judges.

## Coding requests in business words

`classifier/code_gap.py` (a few cents): coding requests and counter-examples
in business teams' words for training, and a test set from a different writer.
Score before and after (`score before`, `score after`); ship only if false
alarms (non-coding requests sent to CODE) stay low, not just if recall rises.
Coding rows without counter-examples sent 31% of emails and policy questions
to Codex.

## Honest reporting

- Held-out is 73 prompts: one prompt moves a score by 1.4 points; quote the
  cross-validated numbers next to it.
- Report quality and cost together, against every fixed route and against
  LiteLLM's heuristic and LLM classifier.
- A test expectation changes only with the outcome data that justifies it,
  written next to it (`app/scenarios.py`, `accept` and `why`).
