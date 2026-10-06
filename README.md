# The right model for every request: LiteLLM routing across OCI Generative AI

An application sends every request to one OpenAI-compatible endpoint, the
[LiteLLM](https://github.com/BerriAI/litellm) AI Gateway, and asks for a
model group. The gateway decides which of **fifteen OCI Generative AI
models** answers, across OpenAI, Google, Meta, xAI and Cohere: a
**classifier we mini-trained** reads the request and picks one of eight
routes, tags pick a customer lane, a context-window check and fallback chains
keep requests alive, and latency balances deployments. A
[langchain-oci](https://github.com/oracle/langchain-oracle) agent drives it,
a web control room draws every routing decision live, and Codex builds and
verifies it from a spec and four skills.

Built on the integration announced in
[LiteLLM natively supports OCI Generative AI](https://blogs.oracle.com/ai-and-datascience/litellm-natively-supports-generative-ai).

![Architecture](docs/figures/figure1-architecture.png)

## Routes, models and criteria

| Route | Model group | OCI models (backup) |
|---|---|---|
| SIMPLE: short facts, formatting | `oci-fast` | Gemini 2.5 Flash-Lite, Llama 4 Scout (GPT-5 nano) |
| MEDIUM: explanations, summaries | `oci-balanced` | GPT-5 mini, Gemini 2.5 Flash |
| COMPLEX: multi-part analysis | `oci-strong` | Gemini 2.5 Pro (GPT-5.2) |
| REASONING: proofs, constrained planning | `oci-reasoning` | Grok 4.20 reasoning, o3 (o4-mini) |
| CODE | `oci-code` | GPT-5.1 (Grok 4.3) |
| VISION | `oci-vision` | Gemini 2.5 Flash, Llama 4 Maverick |
| LONG_CONTEXT | `oci-long` | Gemini 2.5 Flash (Llama 4 Maverick) |
| MULTILINGUAL | `oci-multilingual` | Cohere Command A (Gemini 2.5 Flash) |

A route is decided by three layers, in order:

1. **Facts in the request**, by rules: an image → VISION; more than ~30k
   tokens → LONG_CONTEXT; not English → MULTILINGUAL.
2. **What the request needs**, by our trained ladder: a programming request →
   CODE; otherwise each route's chance of an answer the judge accepts, and the
   cheapest route that clears the quality bar.
3. **Business rules**, by the gateway: tags (`premium` → GPT-5.2), budgets
   and keys, latency, fallbacks, retries and cooldowns.

Three auto-routers classify the same request three ways, for comparison:
`oci-auto` (LiteLLM's built-in heuristic), `oci-auto-llm` (Gemini Flash-Lite
grades the request) and `oci-auto-trained` (ours, `classifier_type: custom`).

![Where the classifier sits](docs/figures/figure2-classifier-path.png)

## The router: label by outcome, predict the chance of a good answer

![Mini-training](docs/figures/figure3-mini-training.png)

1. **Generate**: the judge model writes 463 prompts across 18 task families,
   trivial to expert (general tasks plus support, billing, IT ops, finance and
   people ops), code tasks, and requests in seven languages.
2. **Label by outcome**: every route answers every prompt through the
   gateway; GPT-5.2 grades the anonymised answers on correctness,
   completeness and instruction-following (1-5); an answer passes at 4 or
   more on all three. Three runs per route (one for the reasoning route) give
   each prompt a pass rate per route: 3,590 judged answers, about $33.
3. **Why not one label**: labelled three times, only 63% of prompts got the
   same cheapest passing route every time, so accuracy against one label tops
   out in the 60s and 70s for any model (bigger encoders, up to 568M weights,
   did not move it). The router predicts pass probabilities instead.
4. **Train the ladder** (`classifier/ladder.py`): per route, a logistic model on
   the multilingual-e5-small embedding and seven difficulty signals, trained on
   fractional outcomes, averaged with the pass rates of the 12 most similar
   labelled requests. A code head sends programming requests to CODE. Seconds
   on a laptop CPU; the shipped model is 210 KB.
5. **Choose the quality bar** inside the training split by 5-fold
   cross-validation: the cheapest bar at least as good as always using the
   reasoning models. Each request may set its own (`metadata.route_quality_bar`).
6. **Plug in**: `gateway/trained_classifier.py` implements LiteLLM's
   `ClassifierPlugin` (`async classify(context) -> route`).

## Results

Through the real gateway, on held-out prompts never seen in training or in
choosing the bar, every answer a real OCI call graded by the same judge
([evidence/classifier-eval.json](evidence/classifier-eval.json)):

| Policy | Answers good enough | Cost of the answers | Code and language routes |
|---|---|---|---|
| always the fast models | 57% | $0.029 | — |
| always the balanced models | 80% | $0.236 | — |
| always Gemini 2.5 Pro | 58% | $1.333 | — |
| always the reasoning models | 86% | $0.724 | — |
| LiteLLM heuristic (`oci-auto`) | 62% | $0.076 | 0% |
| LiteLLM LLM classifier (`oci-auto-llm`) | 68% | $0.719 | 0% |
| **our ladder (`oci-auto-trained`, bar 70%)** | **84%** | **$0.438** | **100%** |

![Quality against cost](docs/figures/figure4-quality-cost.png)

The ladder gives 22 points more good answers than LiteLLM's heuristic and 16
more than its LLM classifier at 40% less, 4 points more than always using the
balanced models, and stays 2 points under always using the reasoning models
for 40% less. Raising the bar trades spend for quality on the same unseen
prompts ([classifier/model/meta.json](classifier/model/meta.json),
`ladder.held_out_curve`): at 85% it matches always-reasoning (86%) for about
20% less. It is the only router that sends code and other languages to their
own models. Held-out is 73 prompts: one prompt moves a score by 1.4 points.

**Did we really train it?** Yes: supervised learning on judged outcomes. The
shipped router fits four logistic models (one per route) and a code head on
frozen multilingual-e5-small embeddings. In an earlier experiment on
single-run labels, fine-tuning the encoder itself (117.7M weights,
`classifier/finetune.py`, 47 s on the Mac's GPU) added about 8 points of label
accuracy ([evidence/finetune-comparison.json](evidence/finetune-comparison.json));
with more labelled traffic that is the next lever, on an OCI GPU.

## See why a request got its model

The control room opens on **Ask and explain**: type any request and the
gateway routes it; the screen shows the decision path (each rule, the code
check, then every route cheapest first with its chance of a good answer
against the bar), where that number comes from (the request's own features
and its twelve most similar labelled requests), the closest training requests
with how often each route passed, and why that deployment answered. Drag the
quality bar to move the same request between models. Nothing on the screen is
written by a model after the fact (`classifier/explain.py`).

## Run it

```shell
uv sync
cp config.example.json ~/.config/litellmdemo/config.json      # your OCI profile, region, compartment
oci session authenticate --profile-name <profile> --region us-ashburn-1   # your terminal
scripts/gateway.sh &                                            # LiteLLM on 127.0.0.1:4000
(cd web && npm ci && npm run build)
uv run uvicorn ui.server:app --host 127.0.0.1 --port 8780       # http://127.0.0.1:8780
```

Or hand it to Codex: `codex "$(cat codex/PROMPT.md)"` with the flags in
[codex/README.md](codex/README.md). Codex follows [codex/SPEC.md](codex/SPEC.md),
the rules in [AGENTS.md](AGENTS.md), and the skills in
[.agents/skills/](.agents/skills/):

| Skill | What it teaches Codex |
|---|---|
| `litellm-oci-gateway` | start and change the gateway; OCI session signing; OCI quirks |
| `litellm-oci-routing` | which routing feature fits which need; reading the route headers |
| `litellm-route-classifier` | generate, label by outcome, train, evaluate, plug in |
| `litellm-route-verify` | probes, end-to-end, browser test, evidence without secrets |

## Run it on Kubernetes (OKE)

The same gateway and classifier run as two services on an OKE Basic cluster
with one Ampere A1 node.

![On Kubernetes](docs/figures/figure5-kubernetes.png)

```shell
cp deploy/deploy.example.json ~/.config/litellmdemo/deploy.json   # your OCI profile and regions
scripts/oci/up.sh                     # compartment, VCN, cluster, node, IAM; about 15 minutes
scripts/oci/deploy.sh                 # ConfigMaps, Secret, both Deployments
scripts/oci/forward.sh &              # the OKE gateway on 127.0.0.1:4100, reconnecting on its own
LITELLM_GATEWAY=http://127.0.0.1:4100 uv run python scripts/probe_routes.py
scripts/oci/down.sh                   # delete everything up.sh created
```

- **No OCI key in the cluster.** The gateway sets `OCI_AUTH=instance_principal`
  and signs as the node: a dynamic group of the demo's instances and one
  policy (`use generative-ai-family in compartment litellmdemo`) allow it.
  OKE Workload Identity scopes this to the pod's service account instead of
  the node; it needs an Enhanced cluster.
- **The classifier is its own service.** `oci-auto-trained` calls
  `route-classifier` over HTTP with a 3 s budget. If the classifier is down
  or slow, the plugin declines and LiteLLM routes to `fallback_tier`: routing
  degrades, requests keep answering.
- **No registry.** Both pods run stock `python:3.12-slim`; an init container
  installs pinned packages (`deploy/requirements/`), and the code, the gateway
  config and the 7 KB head come from ConfigMaps. A pod restarts exactly when
  the hash of what it mounts changes.
- **Measured on the cluster** ([evidence/oke-run.json](evidence/oke-run.json)):
  route probes 11/11, use cases 13/13, browser test 20/20. Signing held for
  70 minutes of token rotation (24/24). With the classifier scaled to zero,
  requests still answered on MEDIUM and routing came back with it; a killed
  classifier or gateway pod is replaced in about 20 s (packages are cached on
  the node). Classification takes 79 ms (median) on the one Ampere core.
- **Failover off the cluster.** The control room sends requests to
  `LITELLM_GATEWAY` (the OKE gateway, through `scripts/oci/forward.sh`, which
  restarts the port-forward whenever its pod goes away) and falls back to
  `LITELLM_GATEWAY_FALLBACK` (the laptop gateway) when it is unreachable or its
  OCI signing fails: `uv run python scripts/failover.py` ends with `FAILOVER OK`.
- **The API endpoint admits one address** (or a NAT pool you name in
  `deploy.json`). `up.sh` detects it on port 6443, because NAT can send 6443
  out of a different address than web traffic.

## Check every claim

| Claim | Command | Ends with |
|---|---|---|
| each routing behaviour, through the real gateway | `uv run python scripts/probe_routes.py` | `ROUTES OK` |
| the classifier and its comparison | `uv run python classifier/evaluate.py` | the policy table |
| every use case through agent, gateway and OCI | `uv run python scripts/e2e.py` | `E2E OK` |
| the screens, clicked in a browser | `cd web && node scripts/ui-e2e.mjs` | `UI E2E OK` |
| the same routes through the OKE gateway | `LITELLM_GATEWAY=http://127.0.0.1:4100 uv run python scripts/probe_routes.py` | `ROUTES OK` |
| requests survive a classifier outage | `scripts/oci/chaos.sh` | `CHAOS OK` |
| signing survives token rotation | `scripts/oci/soak.sh` (70 min) | `SOAK OK` |
| the control room survives a gateway outage | `uv run python scripts/failover.py` | `FAILOVER OK` |

## Field notes

| Where | What we found |
|---|---|
| Complexity router · Gemini | It sets `max_tokens` from LiteLLM's model map (65,536); OCI's Gemini accepts less than 65,536, so every SIMPLE request fell back silently. Declare `max_output_tokens: 65535`. |
| Complexity router · Llama 4 | The map says 8,192 output tokens; OCI allows 4,096. Same failure, same fix. |
| LLM classifier | Its default timeout is 3 s; GPT-5 nano took longer and the router fell back to the heuristic without an error. Use the fastest model and `timeout_ms`. |
| Cohere vision | LiteLLM sends every `cohere.*` model in Cohere format; OCI rejects it for `command-a-vision`. |
| Model catalog | Listed is not served: Grok 4, Grok Code and the Codex models returned 404 on demand. Smoke-test first. |
| Prices | Newer OCI models have no price-map entry; set `model_info` prices or cost is `None`. |
| Open-source limit | One auto-router with operator-defined routes per gateway. |
| Agent requests | The agent's system prompt and tool turns drowned the request: every prompt looked alike to the classifier and Spanish read as English. Classify the user turns only. |
| Short requests | py3langid called "What is 18 percent of 4,217.50?" Afrikaans. The language rule needs a few words and 50% confidence; that keeps 56/56 non-English prompts and flags 0/256 English ones. |
| Unseen domains | The first prompts had no customer-support requests: "reset a password" routed to CODE. 151 business prompts, labelled the same way, fixed it; the ladder now sends it to the balanced models, because the fast ones passed similar requests 47% of the time. |
| OKE behind NAT | Port 6443 left from a different address than web traffic; allowlist the address seen on 6443. |
| Labels | Labelled three times, only 63% of prompts got the same cheapest passing route. Predict each route's pass probability, not one label. |
| Gemini 2.5 Pro | 58% good answers at five times the balanced cost: thinks at length, answers tersely. The router never picks it. |
| OKE signing | Instance-principal signing failed after ~20 minutes: LiteLLM signs with `do_request_sign()`, which skips the SDK's token refresh (only `__call__` refreshes). The pre-call hook refreshes it. |
| Well-known is not hard | Famous proofs pass on the cheapest model, so the classifier learned SIMPLE for them; constrained planning is what needs REASONING. |
| Session signing | The provider signs with API-key fields or an `oci_signer`; a `CustomLogger.async_pre_call_deployment_hook` attaches a session signer per call. |

## Layout

| Path | Purpose |
|---|---|
| `gateway/` | LiteLLM config, OCI session signer, trained-classifier plugin |
| `classifier/` | generate, label, train, evaluate; `router_model.py`; data and the 7 KB trained head |
| `app/` | the langchain-oci agent, its tools, the use cases |
| `ui/`, `web/` | the control room: FastAPI, React; live routing map |
| `scripts/` | `gateway.sh`, `probe_routes.py`, `e2e.py` |
| `.agents/skills/`, `codex/`, `AGENTS.md` | the Codex harness |
| `docs/figures/`, `docs/screenshots/` | figures and screenshots |
| `evidence/` | transcripts behind every claim |

---

Personal open-source work. Northwind Cloud is a fictional company; no real
customer data is used. Not an Oracle publication or a statement of Oracle's
plans.
