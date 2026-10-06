---
name: litellm-oci-gateway
description: Use when starting, operating, or changing the LiteLLM AI Gateway in front of OCI Generative AI in this repository - gateway/config.yaml, OCI session signing, the master key, adding or removing a model deployment, and the OCI model quirks that break routing.
metadata:
  author: federico-kamelhar
  version: "1.0"
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

## Adding a deployment

1. Smoke-test the model first with one direct call (see below). Many catalog
   entries are not served on demand in every tenancy and return 404.
2. Add it under `model_list` with the `*oci` anchor for region and compartment.
3. If `litellm.model_cost` has no `oci/<model>` entry, set
   `model_info.input_cost_per_token` / `output_cost_per_token` (and
   `max_input_tokens`) from the same model at its own provider, and say so in
   a comment. Without prices, cost-based routing and spend are wrong.
4. Restart the gateway and run `uv run python scripts/probe_routes.py`.

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

## Rules

- Change only `gateway/`, `scripts/` and docs unless the task says otherwise.
- After any config change: restart, then `scripts/probe_routes.py` must end with `ROUTES OK`.
- Never deploy the gateway anywhere but this machine without the operator's explicit go-ahead.
