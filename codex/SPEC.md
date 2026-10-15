# Specification: LiteLLM routing across OCI Generative AI, in Oracle Cloud

This is the build an agent follows to stand the demo up in an OCI tenancy and
prove it works. `SPEC-laptop.md` is the same demo on one laptop. This is
personal work; Northwind Cloud and its data are fictional, and the report keeps
that sentence.

## 0. What is being built, and what "done" means

An application (a langchain-oci agent) sends every request to one
OpenAI-compatible endpoint, a LiteLLM AI Gateway, asking for a model group.
The gateway decides which of twenty OCI Generative AI models answers: a
classifier trained on judged outcomes picks one of eight routes, tags pick a
customer lane, a context-window check and fallback chains keep requests alive,
and latency balances deployments. The agent runs in an NVIDIA OpenShell
sandbox that holds no key. A web control room shows every decision.

Everything runs in one OCI tenancy; the operator's machine only runs the
scripts and the checks:

| Piece | Where | Created by |
|---|---|---|
| compartment, VCN, OKE Basic cluster with one Ampere A1 node, IAM dynamic group and policy | the home region in `deploy.json` | `scripts/oci/up.sh` |
| LiteLLM gateway, route classifier, Postgres; the gateway's master key and the agent's virtual key | namespace `litellmdemo` on the cluster | `scripts/oci/deploy.sh` |
| the control room's VM (Ampere A1, Oracle Linux 9, Landlock on, OpenShell with rootless Podman) | the same VCN | `scripts/oci/control.sh` |
| the control room, the OpenShell provider and the agent's sandbox, as services | that VM | `scripts/oci/control-deploy.sh` |
| the public URL: an OCI API Gateway with Oracle's hostname and certificate | its own public subnet | `scripts/oci/edge.sh` |
| the models | OCI Generative AI in us-chicago-1 (the manifests and the control room use that region) | nothing to create |

The gateway signs OCI calls as its node (instance principal): no OCI key or
token is stored in the cloud.

Done means:

1. `scripts/oci/preflight.sh` ends with `CLOUD PREFLIGHT OK (10/10)  https://<host>`.
2. `scripts/probe_routes.py` against the cluster's gateway ends with `ROUTES OK`,
   or fails only the known miss in section 6.
3. `scripts/e2e.py` through the public URL ends with `E2E OK`, or fails only
   the known misses in section 6, and every run ran in the sandbox (4.7).
4. `web/scripts/ui-e2e.mjs` through the public URL ends with `UI E2E OK`
   (macOS with Google Chrome; elsewhere the check is skipped and the build is
   reported as not fully verified).
5. The operator has the report in section 7.

Out of scope: production hardening, real customer data, any resource the
scripts do not create, and `scripts/oci/down.sh` unless the operator asks for it.

## 1. Inputs the operator supplies

| Input | How the agent gets it |
|---|---|
| An OCI CLI profile with an API key, for a user who may create a compartment, a dynamic group and a policy in the tenancy, and networks, an OKE cluster, compute instances and an API gateway in that compartment (a tenancy administrator, or equivalent policies) | the operator writes `~/.config/litellmdemo/deploy.json` from `deploy/deploy.example.json`: `profile`, `region` (the home region for the cluster and the VM), `genai_region` (`us-chicago-1`), `compartment_name`, `node_ocpus`, `node_memory_gbs`, optional `control_ocpus` and `control_memory_gbs` (default 2 and 12), and `api_allow_cidr` (empty: the operator's current address is detected) |
| Capacity | Ampere A1 room for the node and the VM (3 OCPU and 18 GB with the defaults), boot volumes of 50 GB and 100 GB, and OCI Generative AI in us-chicago-1 |
| An SSH key for the VM | `~/.ssh/id_ed25519` and `~/.ssh/id_ed25519.pub`, or `LITELLMDEMO_SSH_KEY`; a key with a passphrase must already be loaded in the operator's SSH agent |
| Approval of the plan | the operator's yes to the plan in section 4.0 |

Nothing else. `deploy.sh` generates the gateway's master key and the
database password (0600 files under `~/.config/litellmdemo/`) and issues the
agent's virtual key; every OCID goes to `~/.config/litellmdemo/oci-state.json`,
never into the repository. Never read the key files, the state file's OCIDs,
or `~/.oci/` yourself: the scripts and the OCI CLI do.

## 2. Preflight

| Check | Command | Pass |
|---|---|---|
| uv | `uv --version` | prints a version |
| Python dependencies | `uv sync` | exits 0 |
| Node | `node --version` | v20.19 or later in 20.x, or v22.12 or later |
| web dependencies and build | `(cd web && npm ci && npm run build)` | exits 0 |
| tools | `command -v python3 oci kubectl ssh scp rsync curl shasum` | prints eight paths |
| deploy config | `test -f ~/.config/litellmdemo/deploy.json` | exists; if not, tell the operator to create it and stop |
| OCI API key | `OCI_CLI_AUTH=api_key oci iam region list --profile "$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/litellmdemo/deploy.json')))['profile'])")" >/dev/null` | exits 0. This proves the key signs, not that the user may create everything in section 1: say so |
| SSH key | `test -f "${LITELLMDEMO_SSH_KEY:-$HOME/.ssh/id_ed25519}" && test -f "${LITELLMDEMO_SSH_KEY:-$HOME/.ssh/id_ed25519}.pub"` | both exist |
| Chrome, for the browser test | `test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` | exists; if not, check 4 is skipped (section 0) |

Show the table before going on. Do not print the profile's name in it.

## 3. Architecture

| Piece | Where | Skill |
|---|---|---|
| Gateway config: 8 routes, backups, tags, fallbacks, 3 auto-routers | `gateway/config.yaml` | `litellm-oci-gateway`, `litellm-oci-routing` |
| OCI signing: the node's instance principal on OKE | `gateway/oci_session_signer.py` | `litellm-oci-gateway` |
| GPT-5.3-codex on OCI's Responses API; Cohere after a tool call | `gateway/oci_responses.py`, `gateway/oci_cohere_fix.py` | `litellm-oci-gateway` |
| Trained classifier, as a service the gateway's plugin calls | `classifier/`, `gateway/trained_classifier.py` | `litellm-route-classifier` |
| Agent: `create_oci_agent` on the gateway | `app/` | `litellm-oci-routing` |
| Sandbox: image, provider profile, policy | `sandbox/`, `scripts/openshell.sh` | `litellm-demo-ops` |
| Control room | `ui/`, `web/` | `litellm-route-verify` |
| Manifests; the cloud scripts | `deploy/k8s/`, `scripts/oci/` | `litellm-demo-ops` |

## 4. Steps

Run every step from the repository root, in the foreground, with stdin from
`/dev/null`, through the project's environment (`uv run`: the scripts call
`python3` with PyYAML). Every script is idempotent: after a failure, fix the
cause (section 6) and run the same script again. In Codex's sandbox, ssh may
warn that it cannot add a new VM to `~/.ssh/known_hosts`; it connects anyway.

### 4.0 The plan

Before any cloud change, show the operator what sections 4.1 to 4.5 will
create, from `deploy.json` and section 0's table: the region, the compartment
name, the node (`node_ocpus`, `node_memory_gbs`, a 50 GB boot volume), the VM
(`control_ocpus`, `control_memory_gbs`, a 100 GB boot volume), their totals,
and what it costs. The node and the VM fit the Always Free Ampere allowance (4
OCPU, 24 GB) only when those totals fit what the tenancy has left of it;
otherwise they are billed by the hour. The API gateway is billed per million
calls, model calls per token. Wait for the operator's yes. An "Operator
context" block that says the plan is approved counts as the yes.

### 4.1 The cluster

```shell
uv run scripts/oci/up.sh </dev/null
```

Checkpoint: the last line is `UP OK`. About 15 minutes the first time; the
kubeconfig is `~/.config/litellmdemo/kubeconfig`.

### 4.2 The gateway, the classifier and Postgres

```shell
uv run scripts/oci/deploy.sh </dev/null
```

Checkpoint: `DEPLOY OK`. The pods run stock images; an init container
installs pinned packages, so the first start takes a few minutes.

### 4.3 The control room's VM

```shell
uv run scripts/oci/control.sh </dev/null
```

Checkpoint: `CONTROL OK`. The VM reboots once at first boot (Landlock and
cgroup delegation, which OpenShell needs); the script waits until the rebooted
kernel runs Landlock, then installs OpenShell 0.1.2 and rootless Podman and
starts the OpenShell gateway as a user service.

### 4.4 The control room and the sandbox

```shell
uv run scripts/oci/control-deploy.sh </dev/null
```

Checkpoint: `CONTROL DEPLOY OK`. It builds the web front end, copies the
repository, builds the sandbox image on the VM with Podman, creates the
OpenShell provider from the agent's key, and starts the control room; it fails
if the control room does not answer.

### 4.5 The public URL

```shell
uv run scripts/oci/edge.sh </dev/null
```

Checkpoint: `EDGE OK  https://<host>`. Up to about 30 minutes the first time
(the gateway, its deployment and its first health check each have a 10-minute
wait). Set `URL=https://<host>` in every later shell. Give the URL to the
operator; do not write it into the repository.

### 4.6 Recorded runs, for replay

```shell
LITELLMDEMO_APP="$URL" uv run python scripts/record_runs.py </dev/null
```

Paid, a few cents: 23 live jobs (six of the control room's examples and the
seventeen use cases), saved on the VM. Checkpoint: `23/23 recorded`.

### 4.7 The checks

```shell
uv run scripts/oci/preflight.sh </dev/null                                         # check 1
LITELLMDEMO_APP="$URL" uv run python scripts/e2e.py --evidence out/e2e </dev/null    # check 3, paid, cents
LITELLMDEMO_APP="$URL" node web/scripts/ui-e2e.mjs out/ui-e2e </dev/null             # check 4, paid, cents
```

Check 3 also needs every run to have used the sandbox: in `out/e2e/e2e.jsonl`,
each line's `runtime` is `["openshell"]` and its `sandbox_network` lists the
sandbox's connections. A run without them came from the host agent or a
replay: report it.

Check 2 needs the cluster's gateway on a local port. Run this block in one
shell; it ends the port-forward and returns the probe's status:

```shell
(
  export KUBECONFIG=~/.config/litellmdemo/kubeconfig
  kubectl port-forward -n litellmdemo svc/litellm-gateway 4100:4000 >out/port-forward.log 2>&1 &
  pf=$!; trap 'kill $pf 2>/dev/null' EXIT
  for _ in $(seq 30); do curl -sf -o /dev/null http://127.0.0.1:4100/health/liveliness && break; sleep 1; done
  kill -0 $pf 2>/dev/null || { echo "ABORT: the port-forward did not start (port 4100 in use?)" >&2; exit 1; }
  LITELLM_GATEWAY=http://127.0.0.1:4100 uv run python scripts/probe_routes.py </dev/null
)
```

Checkpoints: `CLOUD PREFLIGHT OK (10/10)  https://<host>`, `ROUTES OK`,
`E2E OK`, `UI E2E OK`, or only the known misses in section 6. A known miss is
not a failure to fix or retry: report it and go on.

## 5. Rules for the agent

- Never handle a secret (section 1). Anything that looks like a key or a token
  in an output is a stop condition.
- The cloud changes only through `scripts/oci/*.sh`, and only within the build
  the operator approved in 4.0. Never create, change or delete anything else,
  and never run `scripts/oci/down.sh` unless the operator asks for it by name.
- Do not edit `gateway/`, `classifier/`, `app/` or `scripts/` to make a check
  pass, during a build or after it; explain and stop. A known miss is
  reported, not fixed.
- Do not run `classifier/label.py`, `classifier/generate.py`,
  `classifier/model_trial.py` or `classifier/robustness.py`: the trained model
  ships in `classifier/model/`, and those runs are paid.
- Keep OCIDs, the profile's name and the public hostname out of every file
  you write.

## 6. Known behaviour

| Symptom | Cause | Action |
|---|---|---|
| `ABORT: cannot determine the address to admit to the Kubernetes API` | the address probe on port 6443 failed | ask the operator for their public address or NAT range; they set `api_allow_cidr` in `deploy.json`; rerun `up.sh` |
| `kubectl` times out or is refused later, and ssh to the VM times out | the operator's address changed (another network, a NAT pool), or the network blocks port 6443 | the fix, `scripts/oci/up.sh` (the API rule) and `scripts/oci/control.sh` (the VM's SSH rule), locks out the previous network: ask the operator first |
| the CODE route answers with GPT-5.1, and the gateway log has `ROUTE-FAIL ... gpt-5.3-codex ... 404` | the node's policy lacks the Responses API statement | `scripts/oci/up.sh` reconciles the policy (`manage generative-ai-response`); wait a minute for IAM |
| the Japanese request's second call answers from Gemini, after a Cohere 400 "cannot specify message" | LiteLLM's Cohere request after a tool call | fixed by `gateway/oci_cohere_fix.py`; if the cluster runs an older `gateway/`: `scripts/oci/deploy.sh` |
| `ABORT: cloud-init or its reboot not finished` | the first boot is slow, or the image lacks Landlock | rerun `control.sh`; if it fails again, stop and report |
| the sandbox fails with a `Landlock` probe error, or `controller cpu is not available`, on a VM created before these scripts set them | Landlock off in the kernel, or cgroup delegation missing | stop and report: the VM needs a repair the operator authorises |
| `edge.sh` is quiet for minutes | the CLI's `--wait-for-state` fails silently for API Gateway resources, so it polls | wait (4.5) |
| a run's stream stops after 15 s of silence | API Gateway closes a silent response | the control room sends a keep-alive every 5 s; check the deployment's read timeout with `edge.sh` |
| preflight: recorded runs fewer than 5 | 4.6 not run yet | run 4.6 |
| preflight: the agent key near its budget | $5 every 30 days; the spend resets on its own | report the spend; rotating the key early is the operator's decision (`deploy.sh` keeps a valid key, and the VM's provider is recreated only when missing) |
| probe `trained: constrained planning` gets COMPLEX, expects REASONING | the router's known miss: on these prompts it picks the strong route (`evidence/strong-vs-reasoning.json`) | report it; do not change the router or the check |
| e2e `support-escalation` and `analyst-forecast` get COMPLEX, expect REASONING | the same known miss | report them |
| e2e `agent-incident` misses `51.2` | its arithmetic step lands on a cheaper route; it missed in every run on 2026-10-12 | report it; do not loosen the check |
| the pods take minutes to become ready | the init container installs packages and the classifier loads its encoder before it reports ready | wait for `DEPLOY OK`; a slow request after that is not the encoder |

## 7. Report

End with: the preflight table (section 2); each step's last line and how long
it took; the check results (section 4.7) with every known miss named and the
sandbox evidence for check 3; what the paid steps spent; any section-6 symptom
met and what was done; the personal-work sentence at the top of this file;
and the public URL, to the operator only.
