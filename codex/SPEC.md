# Specification: LiteLLM routing across OCI Generative AI

## 0. What is being built, and what "done" means

An application (a langchain-oci agent) sends every request to one
OpenAI-compatible endpoint, a LiteLLM AI Gateway, asking for a model group.
The gateway decides which of fifteen OCI Generative AI models answers: a
classifier reads the request and picks one of eight routes, tags pick a
customer lane, a context-window check and fallback chains keep requests
alive, and latency balances deployments. The classifier is ours: a mini
training run on outcome-labelled prompts, plugged in as the complexity
router's `classifier_type: custom`.

Done means:

1. `scripts/gateway.sh` serves on 127.0.0.1:4000 and `/v1/models` lists the groups in `gateway/config.yaml`.
2. `uv run python scripts/probe_routes.py` ends with `ROUTES OK`.
3. `classifier/model/meta.json` exists, and `evidence/classifier-eval.json` holds the policy comparison.
4. With the web app on 8780, `uv run python scripts/e2e.py` ends with `E2E OK`.
5. The operator has the report in section 7.

Out of scope: production hardening, real customer data, any deployment beyond this machine.

## 1. Inputs the operator supplies

| Input | How the agent gets it |
|---|---|
| An OCI CLI profile with an active session and Generative AI access in us-chicago-1 | `~/.config/litellmdemo/config.json` (see `config.example.json`); the operator renews the session in their own terminal |
| Nothing else | the gateway master key is generated on first start, 0600 |

Never read the session token or the key file yourself; the gateway does.

## 2. Preflight

| Check | Command | Pass |
|---|---|---|
| uv | `uv --version` | prints a version |
| dependencies | `uv sync` | exits 0 |
| config | `test -f ~/.config/litellmdemo/config.json` | exists |
| OCI session | `oci iam region list --profile "$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/litellmdemo/config.json')))['oci_profile'])")" --auth security_token >/dev/null` | exits 0; if not, ask the operator to re-authenticate and stop |
| web build | `(cd web && npm ci && npm run build)` | exits 0 |

## 3. Architecture

| Piece | Where | Skill |
|---|---|---|
| Gateway config: 8 routes, backups, tags, fallbacks, 3 auto-routers | `gateway/config.yaml` | `litellm-oci-gateway`, `litellm-oci-routing` |
| OCI signing with the operator's session | `gateway/oci_session_signer.py` | `litellm-oci-gateway` |
| Trained classifier: rules + e5-small + logistic regression | `classifier/router_model.py`, `gateway/trained_classifier.py` | `litellm-route-classifier` |
| Agent: `create_oci_agent` on the gateway | `app/agent.py`, `app/tools.py`, `app/scenarios.py` | `litellm-oci-routing` |
| Control room | `ui/server.py`, `web/` | `litellm-route-verify` |

## 4. Steps

### 4.1 Start the gateway

```shell
mkdir -p out && scripts/gateway.sh </dev/null > out/gateway.log 2>&1 &
for i in $(seq 1 90); do curl -sf localhost:4000/health/liveliness >/dev/null && break; sleep 1; done
```

Checkpoint: `curl -sf localhost:4000/health/liveliness` prints `"I'm alive!"`.

### 4.2 Probe the routes

```shell
uv run python scripts/probe_routes.py </dev/null
```

Checkpoint: `ROUTES OK`. On a failure, read the `litellm-route-verify` skill's table first.

### 4.3 The classifier

If `classifier/model/meta.json` exists, skip to 4.4. Otherwise, and only if
the operator agreed to the labelling spend (about $5):

```shell
uv run python classifier/label.py </dev/null     # resumable; prompts.jsonl must already exist
uv run python classifier/train.py </dev/null
```

Then restart the gateway (4.1) so the plugin loads the model, and run:

```shell
uv run python classifier/evaluate.py </dev/null
```

Checkpoint: the policy table prints; report it as it is.

### 4.4 The control room

```shell
uv run uvicorn ui.server:app --host 127.0.0.1 --port 8780 </dev/null > out/ui.log 2>&1 &
uv run python scripts/e2e.py </dev/null
```

Checkpoint: `E2E OK`. Tell the operator the URL, http://127.0.0.1:8780.

## 5. Rules for the agent

- Never handle a secret (section 1). Anything that looks like a key in an output is a stop condition.
- Local only: no clusters, no GPU instances, no cloud resources without the operator's go-ahead naming them.
- Do not edit code to make a check pass; explain and stop.
- One run of `label.py` at a time; never rerun `generate.py` unless asked.

## 6. Known behaviour

| Symptom | Cause | Action |
|---|---|---|
| a tier always falls back; `maxOutputTokens`/`maxTokens` errors | the complexity router sets `max_tokens` from LiteLLM's model map; OCI's Gemini accepts < 65536 and Llama 4 ≤ 4096 | declared in `model_info`; keep it |
| gateway refuses to start: `At most 1 auto-router(s) with operator-defined tier_definitions` | open-source build limit | one custom-tier router only |
| 401 from OCI | the session expired | operator re-authenticates; the gateway reloads within a minute |
| 404 `Entity with key` | model not served on demand here | choose another model |
| `cause=classifier_fallback` | the plugin declined or timed out | train the model; restart the gateway |
| the first request after a restart is slow | the encoder loads at startup | wait for the gateway to report alive |

## 7. Report

End with: the preflight table; the probe results; the classifier's held-out
accuracy and the policy table; the end-to-end results per use case; and any
section-6 symptom met and what was done.
