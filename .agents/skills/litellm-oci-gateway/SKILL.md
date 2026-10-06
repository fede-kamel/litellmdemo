---
name: litellm-oci-gateway
description: Use when starting, operating, or changing the LiteLLM AI Gateway in front of OCI Generative AI in this repository - gateway/config.yaml, OCI signing (session, Kubernetes Secret, instance principal), the master key and virtual keys, adding or swapping a model deployment and its price, the Codex provider for OCI's Responses API, and the OCI model quirks that break routing.
metadata:
  author: federico-kamelhar
  version: "2.0"
compatibility: litellm[proxy]==1.104.0, oci SDK, an OCI CLI profile with an active session (oci session authenticate)
---

# LiteLLM gateway in front of OCI Generative AI

## Start, check, stop

```shell
scripts/gateway.sh </dev/null > out/gateway.log 2>&1 &     # 127.0.0.1:4000
curl -sf localhost:4000/health/liveliness                 # "I'm alive!"
pkill -f "litellm --config config.yaml"                   # stop
```

`scripts/gateway.sh` reads the OCI profile, region and compartment from
`~/.config/litellmdemo/config.json` and the gateway master key from
`~/.config/litellmdemo/master_key` (created on first run, 0600). Never print
either file, never paste the key into a command line you show, and never
commit them. Scripts read the key from the file.

## How OCI calls are signed

LiteLLM's OCI provider signs with API-key fields or an `oci_signer` object.
`gateway/oci_session_signer.py` attaches a `SecurityTokenSigner` to each call
in `async_pre_call_deployment_hook` (after the router picks a deployment,
before the request is sent), so retries, fallbacks and classifier calls are
signed too. It reloads the session token every 60 s. If calls start failing
with 401, the session expired: the operator runs
`oci session authenticate --profile-name <profile> --region us-ashburn-1` in
their own terminal; the gateway picks it up within a minute, no restart.

## Where the gateway runs

| Where | Signs with | Deploy |
|---|---|---|
| the laptop, 127.0.0.1:4000 (fallback) | the operator's OCI session, from `~/.oci` | `scripts/gateway.sh` |
| Rancher Desktop Kubernetes, node port 30400 (the demo) | the same session, mounted from Secret `oci-session`; `OCI_CONFIG_FILE=/oci/config` | `scripts/local/deploy.sh`; `scripts/local/refresh.sh` keeps the Secret fresh |
| OKE (read-only for agents) | the node's instance principal; no stored key | `scripts/oci/deploy.sh` |

The Kubernetes gateway runs LiteLLM's official image
(`ghcr.io/berriai/litellm-database:v1.104.0`) with Postgres for virtual keys;
an init container adds the OCI SDK. The agent's virtual key
(`openshell-agent`: five model groups, $5 per 30 days, 30 requests a minute)
is issued by the deploy script into a 0600 file; OpenShell holds it.

## Codex: OCI's Responses API

OCI serves the Codex models (`openai.gpt-5.3-codex`) only on
`/openai/v1/responses`; the chat API answers 404 "Use the v1/responses endpoint
instead", and LiteLLM's OCI provider speaks only the chat API.
`gateway/oci_responses.py` is a LiteLLM `CustomLLM` provider for it
(`custom_provider_map` in the config; models named `oci-responses/<model>`):
it translates messages, images, tool calls and tool results, signs like every
other call, and raises HTTP errors so fallbacks apply. A new module the
gateway loads must also be added to the `gateway-code` ConfigMap list in
`scripts/oci/deploy.sh`, or the pod fails with an ImportError.

## Adding a deployment

1. Smoke-test the model first with one direct call (see below). Many catalog
   entries are not served on demand in every tenancy and return 404.
2. Add it under `model_list` with the `*oci` anchor for region and compartment.
3. Set its price in `model_info` and say where it came from in a comment:
   OCI's public price list first (`https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD`,
   cite the part numbers), otherwise the vendor's list price (OCI publishes
   none for OpenAI's commercial models). Do not trust LiteLLM's `oci/` map
   blindly: it prices OCI Gemini 2.5 Flash at a quarter of OCI's list price.
   `uv run python scripts/portfolio.py` regenerates the price table the deck uses.
4. To choose between candidates, measure them: `classifier/model_trial.py`
   (same prompts, same judge). A model that changes a ladder route means
   relabelling and retraining (`litellm-route-classifier`).
5. Restart the gateway and run `uv run python scripts/probe_routes.py`.

```python
# one direct call, outside the gateway
import json, os, oci, litellm
cfg = json.load(open(os.path.expanduser("~/.config/litellmdemo/config.json")))
c = oci.config.from_file(profile_name=cfg["oci_profile"])
signer = oci.auth.signers.SecurityTokenSigner(open(os.path.expanduser(c["security_token_file"])).read().strip(),
                                              oci.signer.load_private_key_from_file(c["key_file"]))
litellm.completion(model="oci/<vendor.model>", messages=[{"role": "user", "content": "Say OK."}],
                   oci_signer=signer, oci_region=cfg["oci_region"], oci_compartment_id=cfg["oci_compartment_id"])
```

## Known OCI quirks (litellm 1.104.0)

| Symptom | Cause | Fix |
|---|---|---|
| a complexity-router tier always falls back; `maxOutputTokens value of 65536` in the error | the router sets `max_tokens` from the model map (65536); OCI's Gemini accepts < 65536 | `model_info: {max_output_tokens: 65535}` on every Gemini deployment |
| `apiFormat COHERE is not supported` for `cohere.command-a-vision` | LiteLLM sends all `cohere.*` models in Cohere format | do not route images to it; use Gemini or Llama 4 for vision |
| 404 `Entity with key ... not found` | the model is in the catalog but not served on demand here | pick another model; keep the smoke test |
| response cost is `None` | no `oci/` entry in the model map | set `model_info` prices (step 3) |
| `At most 1 auto-router(s) with operator-defined tier_definitions` at startup | open-source build limit | one custom-tier router (`oci-auto-trained`); the others use the shipped tiers |
| GPT-6 models: `Function tools with reasoning_effort are not supported` | OCI serves them with reasoning on by default | the pre-call hook sends `reasoning_effort: none`, only when the request carries tools |
| Llama 4 Scout answers with a tool call written as text | its tool calling through LiteLLM on OCI is unreliable; LiteLLM's pre-call checks do not skip such deployments yet | keep it a backup, never a primary for tool-using routes |
| 401 after ~20 minutes on OKE | LiteLLM signs with `do_request_sign()`, which skips the instance-principal token refresh | the hook calls `_reset_signers()` before each call |
| a long reasoning answer never arrives | the model is slower than the timeout | `request_timeout: 300`; the timeout falls back to the backup group |

## Rules

- Change only `gateway/`, `scripts/` and docs unless the task says otherwise.
- After any config change: restart, then `scripts/probe_routes.py` must end with `ROUTES OK`.
- Deploy only to this machine or the local `rancher-desktop` cluster unless the operator names another target.
