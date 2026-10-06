---
name: litellm-demo-ops
description: Use when bringing the demo up on a laptop, checking it is ready for a talk, or fixing it when something breaks - scripts/demo-up.sh, scripts/preflight.sh, the OpenShell sandbox, the local Kubernetes cluster, the OCI session, recorded runs for replay. Start here for "get the demo ready", "it stopped working", or "before my talk".
metadata:
  author: federico-kamelhar
  version: "1.0"
compatibility: macOS with Rancher Desktop (Kubernetes enabled, 6 CPUs / 16 GB), the Homebrew OpenShell gateway, the OCI CLI with a session profile, uv, Node, Google Chrome
---

# Running the demo

## What runs where

| Piece | Where | Started by |
|---|---|---|
| LiteLLM gateway, route classifier, Postgres | Rancher Desktop Kubernetes, namespace `litellmdemo`, node port 30400 | `scripts/local/deploy.sh` |
| the OCI session, copied into the cluster | Secret `oci-session`, renewed every 20 min | `scripts/local/refresh.sh` |
| the agent | OpenShell sandbox `litellmdemo-agent` | `scripts/openshell.sh up` |
| fallback gateway | the laptop, 127.0.0.1:4000 | `scripts/gateway.sh` |
| control room | http://127.0.0.1:8780 | `uvicorn ui.server:app` |

`scripts/demo-up.sh` starts whatever is not running, in that order, and ends
with the preflight. It is idempotent: run it again after any failure.

## Ready for a talk

```shell
scripts/demo-up.sh          # ends with PREFLIGHT OK (n/n)
scripts/preflight.sh        # anytime; every check prints its fix when it fails
```

Before going on stage, on the venue's network:

1. The OCI session must have more than 30 minutes. A refresh cannot extend a
   session past its maximum lifetime; when the header says "log in again" or
   the preflight says "at its maximum lifetime", only the operator can fix it,
   in their own terminal: `oci session authenticate --profile-name <profile> --region us-ashburn-1`.
   Then `scripts/local/push-session.sh`. Never try to log in for them.
2. `PREFLIGHT OK`.
3. Recorded runs exist (`out/recordings/`, at least 5). If not: `uv run python scripts/record_runs.py`.

## When a check fails

| Preflight check | Cause seen before | Fix |
|---|---|---|
| OCI session | expired, or at its maximum lifetime | the operator logs in (above); then `scripts/local/push-session.sh` |
| Rancher Desktop | not started, or the VM starved (load in the hundreds, Docker not answering) | `rdctl start`; if starved, the VM needs 6 CPUs / 16 GB: ask the operator before changing it |
| local cluster pods | a pod in CrashLoopBackOff | `kubectl --context rancher-desktop logs -n litellmdemo deploy/<name> -c <container> --tail=40`; an ImportError in the gateway is a module missing from the `gateway-code` ConfigMap list in `scripts/oci/deploy.sh` |
| image pulls | `ImagePullBackOff` on a `docker.io` image | Docker Hub is blocked behind the corporate proxy: use the same image from ghcr.io or quay.io |
| LiteLLM signs to OCI | 401 from OCI | a stale session in the cluster: `scripts/local/push-session.sh` |
| the CODE route answers with Codex | the gateway falls back to GPT-5.1 | look for ROUTE-FAIL lines for `gpt-5.3-codex` in the gateway log |
| the agent's virtual key | spent, or missing after a fresh database | `scripts/local/deploy.sh` re-issues it; then `scripts/openshell.sh provider && scripts/openshell.sh down && scripts/openshell.sh up` |
| OpenShell sandbox / request through it | the sandbox died with a Rancher Desktop restart; or `policy_dns_trusted_gateway_unavailable` | `scripts/openshell.sh down && scripts/openshell.sh up`; the profile endpoint must be the node's IP, which `scripts/openshell.sh` renders |
| the sandbox cannot escape | a probe reached something | stop: that is a policy regression, report it, do not loosen anything |

Every `openshell` command in a script reads stdin from `/dev/null`
(OpenShell 0.1.2 waits for piped stdin to close). `openshell sandbox get`
output must be read whole before matching it: `grep -q` closes the pipe and,
with `pipefail`, fails the check.

## Multi-step runs

The "Escalation, end to end" use case runs in plan mode (`mode: plan` in
`app/scenarios.py`; `RunRequest.mode` for any prompt): a planner call, then
each step as its own request, so LiteLLM routes every task separately. Events:
`plan`, `step`, `step_done`, and `step` on every `llm` event (0 = the
planner). A task routed somewhere unexpected is usually its wording: the router
reads only the step's instruction. Fix the planner prompt (`PLANNER` in
`app/agent.py`), never the router, and say so in the report.

## The console

The control room's console follows `openshell logs`, the gateway's pod log
(one `ROUTE` line per request: key, route, why, model, seconds, cost,
fallbacks) and the classifier's `CLASSIFY` lines. When a request misbehaves,
read the `ROUTE`/`ROUTE-FAIL` lines first: they name the deployment and the
error.

## Rules

- Never print or copy a key, a token or a password; scripts read them from
  `~/.config/litellmdemo/` and `~/.oci/`.
- Only the local `rancher-desktop` context is yours to change. The OKE cluster
  (`~/.config/litellmdemo/kubeconfig`) is read-only for you unless the operator
  asks for a change there.
- Report what you ran and its last line (`PREFLIGHT OK (n/n)`, `E2E OK (n/n)`).
