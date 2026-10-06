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
2. **What the request needs**, by our trained classifier: SIMPLE, MEDIUM,
   REASONING or CODE.
3. **Business rules**, by the gateway: tags (`premium` → GPT-5.2), budgets
   and keys, latency, fallbacks, retries and cooldowns.

Three auto-routers classify the same request three ways, for comparison:
`oci-auto` (LiteLLM's built-in heuristic), `oci-auto-llm` (Gemini Flash-Lite
grades the request) and `oci-auto-trained` (ours, `classifier_type: custom`).

![Where the classifier sits](docs/figures/figure2-classifier-path.png)

## The classifier: label by outcome, train in seconds

![Mini-training](docs/figures/figure3-mini-training.png)

1. **Generate**: the judge model writes 312 prompts across 13 task families,
   trivial to expert, plus code tasks and requests in seven languages.
2. **Label by outcome**: SIMPLE, MEDIUM and COMPLEX each answer every prompt
   through the gateway; GPT-5.2 grades the anonymised answers on
   correctness, completeness and instruction-following (1-5). The label is
   the cheapest route scoring at least 4 on all three. $5.39 of OCI calls.
3. **Mini-train**: multilingual-e5-small embeddings (local) and a logistic
   regression head, 5-fold cross-validation, 20% held out: **73% held-out
   accuracy** on the learned routes, trained in 0.14 s on a laptop CPU (the
   encoder stays frozen; see "Did we really train it?" below). The rules catch
   56 of 56 non-English requests.
4. **Plug in**: `gateway/trained_classifier.py` implements LiteLLM's
   `ClassifierPlugin` (`async classify(context) -> route`).

What the labels said: the cheapest route was good enough for **62%** of the
prompts, and Gemini 2.5 Pro was the cheapest passing route for only 4 of 208.

## Results

On held-out prompts, priced by the real OCI answers and graded by the same
judge ([evidence/classifier-eval.json](evidence/classifier-eval.json)):

| Policy | Answers good enough | Cost of the answers | Code and language routes |
|---|---|---|---|
| always the cheapest route | 62% | $0.015 | — |
| always Gemini 2.5 Pro | 52% | $0.794 | — |
| always the reasoning route | 86% | $0.364 | — |
| LiteLLM heuristic (`oci-auto`) | 64% | $0.041 | 0% |
| LLM classifier (`oci-auto-llm`) | 81% | $0.365 | 0% |
| **our trained classifier (`oci-auto-trained`)** | 81% | $0.211 | 100% |
| perfect routing (oracle) | 88% | $0.235 | 100% |

![Quality against cost](docs/figures/figure4-quality-cost.png)

Our classifier matches the LLM classifier's quality at 42% less spend and
no extra model call per request, gives up 5 points against always using the reasoning
route for 42% less, and is 17 points better than LiteLLM's
heuristic. It is the only router that sends code and other languages to
their own models.

**Did we really train it?** The shipped router trains a logistic-regression
head (1,540 weights) on frozen multilingual-e5-small embeddings. Fine-tuning
the encoder itself as well (117.7M weights, `classifier/finetune.py`, 47 s on
the Mac's GPU) raised held-out accuracy from 73.1% to 80.8%
([evidence/finetune-comparison.json](evidence/finetune-comparison.json)); two schedules were tried and the
better one kept, so read that gain as optimistic. The frozen head ships: it
rebuilds from 7 KB in a second.

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
scripts/oci/deploy.sh --forward       # ConfigMaps, Secret, both Deployments; gateway on 127.0.0.1:4100
LITELLM_GATEWAY=http://127.0.0.1:4100 uv run python scripts/probe_routes.py
scripts/oci/down.sh                   # delete everything up.sh created
```

- **No OCI key in the cluster.** The gateway sets `OCI_AUTH=instance_principal`
  and signs as the node: a dynamic group of the demo's instances and one
  policy (`use generative-ai-family in compartment litellmdemo`) allow it.
  OKE Workload Identity scopes this to the pod's service account instead of
  the node; it needs an Enhanced cluster.
- **The classifier is its own service.** `oci-auto-trained` calls
  `route-classifier` over HTTP with a 1.5 s budget. If the classifier is down
  or slow, the plugin declines and LiteLLM routes to `fallback_tier`: routing
  degrades, requests keep answering.
- **No registry.** Both pods run stock `python:3.12-slim`; an init container
  installs pinned packages (`deploy/requirements/`), and the code, the gateway
  config and the 7 KB head come from ConfigMaps. A pod restarts exactly when
  the hash of what it mounts changes.
- **Measured on the cluster** ([evidence/oke-run.json](evidence/oke-run.json)):
  route probes 11/11, browser test 14/14, use cases 11/13 (the two misses are
  the classifier's; see "Unseen domains" in the field notes). Deleting the classifier pod mid-run: the request
  answered on MEDIUM through the outage, and routing returned to CODE when
  the new pod was ready.
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
| Unseen domains | The training prompts have no customer-support requests: "reset a password" routes to CODE and a billing reply to SIMPLE. The fix is data, not rules: support prompts labelled by the same outcome contract. |
| OKE behind NAT | Port 6443 left from a different address than web traffic; allowlist the address seen on 6443. |
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
