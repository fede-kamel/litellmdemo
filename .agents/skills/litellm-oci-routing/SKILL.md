---
name: litellm-oci-routing
description: Use when deciding how LiteLLM should route a kind of request across OCI Generative AI models - complexity routing and its classifier types (heuristic, llm, custom, oss_classifier), tag routing, fallbacks, context-window fallbacks, load balancing, retries and cooldowns - and when reading which route a request took from the x-litellm-* headers.
metadata:
  author: federico-kamelhar
  version: "1.0"
compatibility: litellm[proxy]==1.104.0
---

# Routing across OCI models with LiteLLM

Applications ask for a **model group**; the gateway chooses the deployment.
Pick the mechanism by what decides the route:

| What decides | Mechanism | Config |
|---|---|---|
| what the request needs (difficulty, code, language, image, length) | complexity router (`model: auto_router/complexity_router`) | `complexity_router_config` with `tiers` and a `classifier_type` |
| who is calling (customer tier, team) | tag routing | `router_settings.enable_tag_filtering: true`; deployments carry `tags: [default]` / `[premium]`; requests send `"tags": [...]` or header `x-litellm-tags` |
| the prompt does not fit | context-window fallback | `enable_pre_call_checks: true`, `context_window_fallbacks: [{small: [long]}]`, `model_info.max_input_tokens` |
| a deployment fails | fallbacks, retries, cooldowns | `fallbacks: [{group: [backup]}]`, `num_retries`, `allowed_fails`, `cooldown_time` |
| several deployments can serve | load balancing | same `model_name` on several deployments; `routing_strategy: latency-based-routing` (or `simple-shuffle` with `weight`, `usage-based-routing-v2`, `cost-based-routing`, `least-busy`) |

## Complexity router classifiers

| `classifier_type` | Who decides | Cost / latency | Notes |
|---|---|---|---|
| `heuristic` (default) | local keyword and structure scoring | none, < 1 ms | four shipped tiers; misroutes hard prompts written plainly |
| `heuristic_v2` | a bundled trained heuristic | none | four tiers |
| `llm` | a model group grades the request (`classifier_llm_config.model`) | one extra call per request | shipped rubric unless `tier_definitions` |
| `custom` | your `classifier_plugin` (`async classify(context) -> tier | None`) | what your code costs | this repo: `gateway/trained_classifier.py` |
| `oss_classifier` | an open classifier: provider `jev` (TypeSafe), `laya` or `bespoke`, self-hostable via `api_base` | one network call | upstream renamed `jev` to this |
| `capability` | forecasts whether the efficient tier succeeds, then a threshold | one extra call | two-tier policy |

Custom routes: `tier_definitions` (names, descriptions) + `fallback_tier` +
`tiers` keyed by the same names. **The open-source build registers only one
router with operator-defined tiers.**

## Reading the route

Every gateway response carries the decision:

| Header | Meaning |
|---|---|
| `x-litellm-complexity-router-tier` | the route the classifier chose |
| `x-litellm-complexity-router-cause` | `heuristic_scorer`, `classifier_plugin`, `classifier_fallback`, ... |
| `x-litellm-model-group` | the group that answered (after fallbacks) |
| `x-litellm-model-name` | the OCI deployment, e.g. `oci/google.gemini-2.5-pro` |
| `x-litellm-attempted-fallbacks`, `x-litellm-attempted-retries` | how hard it had to try |
| `x-litellm-response-cost`, `x-litellm-response-duration-ms` | what it cost, how long it took |

From langchain: `ChatOpenAI(base_url=".../v1", include_response_headers=True)`
puts them in `AIMessage.response_metadata["headers"]`.

## Rules

- Prove a routing change with `scripts/probe_routes.py` (add a probe for a new behaviour).
- Never hard-code a vendor model in application code; add a group instead.
