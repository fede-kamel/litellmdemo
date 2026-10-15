---
name: litellm-demo-ops
description: Use when bringing the demo up, checking it is ready for a talk, or fixing it when something breaks - in Oracle Cloud (scripts/oci/*.sh, the public URL, the VM, the OKE cluster) or on a laptop (scripts/demo-up.sh, scripts/preflight.sh, Rancher Desktop, the OCI session). Start here for "get the demo ready", "it stopped working", or "before my talk".
metadata:
  author: federico-kamelhar
  version: "2.0"
compatibility: the OCI CLI with an API-key profile for the demo tenancy, uv, Node, Google Chrome (for the browser test); for the laptop path also macOS with Rancher Desktop (6 CPUs / 16 GB) and the Homebrew OpenShell gateway
---

# Running the demo

## What runs where

The demo runs in Oracle Cloud; nothing of it runs on a laptop. The laptop path
below is the fallback for a talk without the cloud.

| Piece | Where | Started by |
|---|---|---|
| LiteLLM gateway, route classifier, Postgres | OKE Basic cluster (one Ampere A1 node), namespace `litellmdemo`; node port 30400 inside the VCN | `scripts/oci/up.sh`, then `scripts/oci/deploy.sh` |
| OCI signing | the node's instance principal; nothing to renew | the IAM policy `up.sh` creates |
| the control room | the VM `litellmdemo-control`, systemd user unit `litellmdemo-control`, port 8780 inside the VCN | `scripts/oci/control.sh`, then `scripts/oci/control-deploy.sh` |
| the OpenShell gateway and the agent's sandbox `litellmdemo-agent` | the same VM: rootless Podman, unit `openshell-gateway` | `scripts/oci/control-deploy.sh` |
| the public URL (HTTPS, Oracle's hostname and certificate) | OCI API Gateway, forwarding every path to the VM | `scripts/oci/edge.sh` (prints it) |

Every script is idempotent: rerun it after a failure or a change.
`control-deploy.sh` is the one to rerun after a code change (it builds the web
app, copies the repository, restarts the service and re-uploads the agent).
`scripts/oci/down.sh` deletes everything they created.

Laptop path: `scripts/demo-up.sh` starts Rancher Desktop's cluster
(`scripts/local/deploy.sh`), the OCI session refresher, the OpenShell sandbox,
a fallback gateway on 127.0.0.1:4000 and the control room on 127.0.0.1:8780,
then runs `scripts/preflight.sh`.

## Ready for a talk

```shell
scripts/oci/preflight.sh                                            # ends with CLOUD PREFLIGHT OK (n/n) and the URL
LITELLMDEMO_APP=https://<host> uv run python scripts/e2e.py         # every use case, through the public URL (paid calls)
LITELLMDEMO_APP=https://<host> node web/scripts/ui-e2e.mjs          # the screens, in a browser (paid calls)
```

Before going on stage: `CLOUD PREFLIGHT OK`, and recorded runs on the VM (the
preflight counts them; `LITELLMDEMO_APP=https://<host> uv run python
scripts/record_runs.py` records them there). The agent's key has a budget
($5 every 30 days) and a rate limit; the preflight fails at 90% of the budget.

On the laptop: `scripts/demo-up.sh` → `PREFLIGHT OK`. The OCI session must
have more than 30 minutes; only the operator can log in, in their own terminal
(`oci session authenticate --profile-name <profile> --region us-ashburn-1`,
then `scripts/local/push-session.sh`). Never try to log in for them.

## When a check fails

| Check | Cause seen before | Fix |
|---|---|---|
| OKE pods | a pod in CrashLoopBackOff; an ImportError is a module missing from a ConfigMap list in `scripts/oci/deploy.sh` | `KUBECONFIG=~/.config/litellmdemo/kubeconfig kubectl logs -n litellmdemo deploy/<name> -c <container> --tail=40`; `scripts/oci/deploy.sh` |
| kubectl times out | the cluster's API admits one address and the operator's changed (NAT pools: `api_allow_cidr` in `deploy.json`) | `scripts/oci/up.sh` (refreshes the rule), `scripts/oci/control.sh` (the VM's SSH rule) |
| the VM's services | the unit stopped, or the VM rebooted before linger was on | `scripts/oci/control.sh ssh 'systemctl --user restart openshell-gateway litellmdemo-control'` |
| the sandbox | `Landlock probe` error: Landlock is off in the kernel; `controller cpu is not available`: cgroup delegation missing | `scripts/oci/control.sh` sets both at first boot and waits for the reboot; a VM created before that needs a repair the operator authorises (`lsm=landlock,...` with grubby, `Delegate=cpu cpuset io memory pids` for `user@.service`, a reboot): stop and report |
| a request fails with `Argument list too long` | the request went to the sandbox on the command line (Linux caps one argument at 128 KiB) | the control room hands it over as a file (`ui/sandbox.py`, `scripts/openshell.sh ask @file`); update the VM with `scripts/oci/control-deploy.sh` |
| the public URL | the API gateway deployment not ACTIVE, or the VM's firewall | `scripts/oci/edge.sh`; the VM allows 8780 from 10.20.0.0/16 only |
| a run's stream stops mid-way | API Gateway closes a response silent for 15 s | the streams send a keep-alive every 5 s (`ui/server.py`); check the deployment's read timeout (300 s) with `scripts/oci/edge.sh` |
| the agent's virtual key | missing or invalid (a fresh database) | `scripts/oci/deploy.sh` issues a new one, then `scripts/oci/control-deploy.sh`. A valid key near its budget is kept as it is: its spend resets every 30 days; rotating it early is the operator's decision; after a re-issued key, `scripts/oci/control-deploy.sh` recreates the provider and the sandbox |
| the CODE route answers with GPT-5.1, not Codex | the cluster runs an older `gateway/` than the repository | `scripts/oci/deploy.sh` (the pods restart when their ConfigMaps' hash changes) |
| the sandbox cannot escape | a probe reached something | stop: that is a policy regression, report it, do not loosen anything |
| laptop: OCI session | expired, or at its maximum lifetime | the operator logs in (above); then `scripts/local/push-session.sh` |
| laptop: Rancher Desktop | not started, or the VM starved | `rdctl start`; the VM needs 6 CPUs / 16 GB: ask the operator before changing it |
| laptop: image pulls | `ImagePullBackOff` on a `docker.io` image | Docker Hub is blocked behind the corporate proxy: use the same image from ghcr.io or quay.io |

Every `openshell` command in a script reads stdin from `/dev/null`
(OpenShell 0.1.2 waits for piped stdin to close). `openshell sandbox get`
output must be read whole before matching it: `grep -q` closes the pipe and,
with `pipefail`, fails the check. The OCI CLI's `--wait-for-state` fails
silently for `api-gateway` resources: `edge.sh` polls `get` instead.

## The screen

Three numbered parts: the request, the decision (route, model, one sentence
why, the ladder beside it), the answer. The rest is under Details, one tab at a
time: Every call, Route map, Why in detail, Sandbox, Sandbox console (open by
default). The header's Safety button opens a drawer that explains the three
layers (OpenShell, LiteLLM, OCI) and carries the escape button. The browser
test (`web/scripts/ui-e2e.mjs`) opens those tabs by their labels.

## Multi-step runs

The "Escalation, end to end" use case runs in plan mode (`mode: plan` in
`app/scenarios.py`; `RunRequest.mode` for any prompt): a planner call, then
each step as its own request, so LiteLLM routes every task separately. Events:
`plan`, `step`, `step_done`, and `step` on every `llm` event (0 = the
planner). A task routed somewhere unexpected is usually its wording: the router
reads only the step's instruction. That is the planner prompt (`PLANNER` in
`app/agent.py`), not the router: report it; change the prompt only when the
operator asks for it, never to make a check pass. The planner
sometimes writes one step or a cheaper route misses a number (about 1 run in
6): report it, do not loosen the check.

## The console

The Sandbox console (dark, like the Deep Agents app's) follows `openshell logs`
(every `ALLOWED`/`DENIED` connection with its policy), the gateway's pod log (one `ROUTE` line per
request: key, route, why, model, seconds, cost, fallbacks) and the classifier's
`CLASSIFY` lines. When a request misbehaves, read the `ROUTE`/`ROUTE-FAIL`
lines first: they name the deployment and the error.

## Rules

- Never print or copy a key, a token or a password; scripts read them from
  `~/.config/litellmdemo/` and `~/.oci/`. The public hostname stays out of the
  repository too: `scripts/oci/edge.sh` prints it.
- The OKE cluster and the VM change only through `scripts/oci/*.sh`, and only
  when the operator asks. The local `rancher-desktop` context is yours.
- Report what you ran and its last line (`CLOUD PREFLIGHT OK (n/n)`, `E2E OK (n/n)`).
