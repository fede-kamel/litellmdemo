---
name: litellm-route-verify
description: Use when proving that the gateway routes requests the way it should - running scripts/probe_routes.py, the control-room end-to-end test, and the browser test - and when publishing their transcripts into evidence/ without secrets.
metadata:
  author: federico-kamelhar
  version: "1.0"
compatibility: the local cluster gateway on 127.0.0.1:30400 and the laptop gateway on 127.0.0.1:4000; the control room on 127.0.0.1:8780; the OpenShell sandbox; Google Chrome for the browser test
---

# Verifying routes

## The checks, in order

```shell
scripts/preflight.sh                                                     # every piece, end to end   -> PREFLIGHT OK (n/n)
LITELLM_GATEWAY=http://127.0.0.1:30400 uv run python scripts/probe_routes.py   # each routing behaviour -> ROUTES OK (n/n)
uv run python scripts/e2e.py --evidence evidence/openshell              # every use case, in the sandbox -> E2E OK (n/n)
(cd web && node scripts/ui-e2e.mjs)                                     # the screens, clicked     -> UI E2E OK (n/n)
uv run python scripts/failover.py                                       # a dead primary gateway   -> FAILOVER OK (n/n)
scripts/oci/chaos.sh                                                    # a classifier outage      -> CHAOS OK
```

`e2e.py` runs the agent inside the OpenShell sandbox and records, per use
case, the runtime and the sandbox's network decisions; every run should be
`openshell` only, with no denied connection.

Each probe asks for a model group and checks the route from the response
headers (`x-litellm-complexity-router-tier`, `x-litellm-model-name`,
`x-litellm-attempted-fallbacks`, ...). A probe that fails prints the gateway's
error. Match it against the quirks table in the `litellm-oci-gateway` skill
before changing anything.

## Reading a failure

| Probe output | Usual cause |
|---|---|
| SIMPLE answers come from `oci-fast-backup` | a tier deployment rejects the router's `max_tokens`: declare the model's real `max_output_tokens` |
| `cause=classifier_fallback` on `oci-auto-trained` | the plugin declined or timed out: model not trained, or the gateway started before training |
| 401 from OCI | the OCI session expired: the operator re-authenticates; the gateway reloads within a minute |
| 404 `Entity with key` | the model is not served on demand in this tenancy |

## Publishing evidence

```shell
uv run python scripts/probe_routes.py --json > evidence/probe-routes.jsonl
uv run python scripts/e2e.py --evidence evidence
```

Before committing evidence, scan it: no OCIDs, no profile names, no keys.

```shell
grep -rlE "ocid1\.|BEGIN .*PRIVATE|sk-[A-Za-z0-9_-]{20,}" evidence/ && echo "STOP: redact first"
```

Never edit routing code to make a check pass without saying why: a failing
probe is information.
