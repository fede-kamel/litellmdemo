# Spin up and run the demo

How to bring the LiteLLM routing demo up, check it, run it, and point Codex at
it. The README explains what the demo is; this file is the order of commands.

Personal work. Northwind Cloud and all its data are fictional.

Repository: https://github.com/fede-kamel/litellmdemo

## What you need

| Tool | Why | Path |
|---|---|---|
| OCI CLI, with a profile in `~/.oci/config` | every cloud script; the laptop gateway signs with it too | both |
| `uv` (Python 3.12) | the scripts, the checks, the control room | both |
| Node 22 or newer (Vite 8; tested on 24) | the web front end and the browser test | both |
| Google Chrome | `web/scripts/ui-e2e.mjs` | both |
| an SSH key at `~/.ssh/id_ed25519` (or `LITELLMDEMO_SSH_KEY`) | the control VM | cloud |
| Rancher Desktop (6 CPUs / 16 GB) | the local Kubernetes | laptop |
| OpenShell 0.1.2 (`brew install nvidia/openshell/openshell`, then `brew services start openshell`) | the agent's sandbox | laptop |
| Codex CLI | the Codex sections | optional |
| Go | the code case of `scripts/codex_e2e.py` runs `go vet` and the race detector | optional |

Nothing in this file prints a key. The scripts read every secret from
`~/.config/litellmdemo/` and `~/.oci/`, and write the keys they issue there.

Prepare the checkout once:

```shell
git clone https://github.com/fede-kamel/litellmdemo.git
cd litellmdemo
uv sync
(cd web && npm ci && npm run build)
mkdir -p ~/.config/litellmdemo
```

## Path A: Oracle Cloud

Everything runs in one OCI tenancy. The gateway, the classifier and Postgres
run on an OKE Basic cluster with one Ampere A1 node. The control room, the
OpenShell gateway and the agent's sandbox run on one Ampere A1 VM beside it.
An OCI API Gateway in front gives the demo a public HTTPS hostname that Oracle
issues. The gateway signs OCI calls as its node, so nothing in the cloud holds
a key and nothing expires.

### A.1 Configure

```shell
cp deploy/deploy.example.json ~/.config/litellmdemo/deploy.json
```

Edit it:

| Field | Value |
|---|---|
| `profile` | an OCI CLI profile with an API key (not a session) |
| `region` | where the cluster, the VM and the API gateway live |
| `genai_region` | where OCI Generative AI is served (for example `us-chicago-1`) |
| `compartment_name` | the compartment the scripts create, `litellmdemo` by default |
| `node_ocpus`, `node_memory_gbs` | the OKE node; 1 OCPU / 6 GB fits the Always Free allowance |
| `api_allow_cidr` | empty to detect your address, or one or more CIDRs, comma-separated, that may reach the Kubernetes API and the VM's SSH |

### A.2 Build (first time, about 30 minutes)

Run from the repository root, in order. Every script is idempotent: rerun it
after a failure or a change and it reconciles what it owns.

```shell
scripts/oci/up.sh              # compartment, VCN, OKE cluster, node, IAM policy; ends with UP OK
scripts/oci/deploy.sh          # gateway, classifier, Postgres; issues the agent's key and the Codex key; DEPLOY OK
scripts/oci/control.sh         # the VM: rootless Podman, OpenShell, Landlock on (one reboot)
scripts/oci/control-deploy.sh  # control room and sandbox on the VM, as services
scripts/oci/edge.sh            # the API gateway; ends with: EDGE OK https://<host>
scripts/oci/preflight.sh       # every piece from the outside; ends with CLOUD PREFLIGHT OK (n/n)
```

The last line of `edge.sh` is the public URL. Keep it out of the repository;
the preflight prints it again, and it lives in the state file
`~/.config/litellmdemo/oci-state.json` as `api_hostname`.

The API gateway routes two paths:

| Path | Goes to | For |
|---|---|---|
| `/v1/*` | LiteLLM on the OKE node | OpenAI-compatible clients, Codex among them; LiteLLM checks a key on every call |
| everything else | the control room on the VM | the browser |

LiteLLM's admin API is not routed. The control room, the gateway and the VM
are not reachable from the internet.

### A.3 Check and record

```shell
URL=https://<host>
LITELLMDEMO_APP=$URL uv run python scripts/e2e.py           # every use case through the public URL; E2E OK (paid)
LITELLMDEMO_APP=$URL node web/scripts/ui-e2e.mjs            # the screens, clicked in Chrome; UI E2E OK (paid)
LITELLMDEMO_APP=$URL uv run python scripts/record_runs.py   # recorded runs for replay when a model is slow
```

### A.4 Run it

Open the public URL in Chrome. `docs/DEMO.md` has the click path for a talk
and what to say at each step.

### A.5 Day to day

| You want to | Run |
|---|---|
| know it is ready | `scripts/oci/preflight.sh` |
| push a code change (control room, agent, sandbox) | `scripts/oci/control-deploy.sh` |
| push a gateway or classifier change | `scripts/oci/deploy.sh` (pods restart when their ConfigMap hash changes) |
| change the API gateway's routes | `scripts/oci/edge.sh` |
| work from a new network | set `api_allow_cidr` in `deploy.json`, then `scripts/oci/up.sh && scripts/oci/control.sh` |
| get a shell on the VM | `scripts/oci/control.sh ssh` |
| read the gateway's ROUTE lines | `KUBECONFIG=~/.config/litellmdemo/kubeconfig kubectl logs -n litellmdemo deploy/litellm-gateway -c gateway --tail=40` |
| reach the OKE gateway from the laptop | `scripts/oci/forward.sh &` then `LITELLM_GATEWAY=http://127.0.0.1:4100` |
| delete everything the scripts created | `scripts/oci/down.sh` |

The cluster's API and the VM's SSH admit only the address in
`api_allow_cidr`. Behind a corporate NAT the address shifts; rerun `up.sh`
and `control.sh` on the network you work from.

## Path B: one laptop

For a talk without the cloud. Everything runs locally; the only outside
services are OCI Generative AI and the OCI session's identity provider.

### B.1 Configure

```shell
cp config.example.json ~/.config/litellmdemo/config.json
```

| Field | Value |
|---|---|
| `oci_profile` | an OCI CLI profile |
| `oci_auth` | `security_token` for a session profile, `api_key` for an API-key profile |
| `oci_region` | the Generative AI region |
| `oci_compartment_id` | a compartment or tenancy with Generative AI access |

With a session profile, log in first in your own terminal. Sessions last
about an hour; `scripts/local/refresh.sh` renews them and pushes the copy
the cluster uses.

```shell
oci session authenticate --profile-name <profile> --region us-ashburn-1
```

### B.2 Up

```shell
scripts/demo-up.sh       # Rancher Desktop, the session refresher, the cluster, the sandbox, the gateways, the control room, the preflight
scripts/preflight.sh     # on its own: PREFLIGHT OK (14/14) or the fixes to run, in order
```

`demo-up.sh` starts only what is not running. It leaves:

| Piece | Where |
|---|---|
| LiteLLM gateway, classifier, Postgres | Rancher Desktop, namespace `litellmdemo`, node port 30400 |
| fallback gateway (plain LiteLLM process) | http://127.0.0.1:4000, log in `out/laptop-gateway.log` |
| OpenShell sandbox `litellmdemo-agent` | the Homebrew OpenShell gateway |
| control room | http://127.0.0.1:8780 |

### B.3 Check and run

```shell
LITELLM_GATEWAY=http://127.0.0.1:30400 uv run python scripts/probe_routes.py   # ROUTES OK
uv run python scripts/e2e.py                                                  # E2E OK
(cd web && node scripts/ui-e2e.mjs)                                           # UI E2E OK
uv run python scripts/failover.py                                             # FAILOVER OK
```

Open http://127.0.0.1:8780. Keep the OCI session countdown in the header
above 15 minutes before going on stage.

### B.4 Down

```shell
scripts/demo-down.sh     # stops the background processes; the cluster and the sandbox keep running
scripts/openshell.sh down
```

## Codex, as a client of the gateway

Codex can use LiteLLM as its model provider. LiteLLM then picks the OCI model
for every Codex turn: a chat question goes to a fast model, a coding task to
GPT-5.3-codex on OCI's Responses API, and Codex never holds an OCI
credential. The gateway speaks the Responses API to Codex and the chat or
Responses API to OCI, whichever the model needs.

### Against the cloud

`scripts/oci/deploy.sh` issues a key for Codex into
`~/.config/litellmdemo/codex_key`: the trained router only, a $10 budget
every 30 days, 60 requests a minute. `scripts/oci/edge.sh` opens `/v1` on
the public URL to LiteLLM.

Both must have run once since the Codex changes, from a network on the
allow list (`deploy.sh` needs the cluster's API). If `/v1/models` on the
public URL returns the control room's HTML, they have not.

```shell
export LITELLM_KEY="$(cat ~/.config/litellmdemo/codex_key)"
codex exec \
  -c 'model_providers.litellm.name="LiteLLM on OCI"' \
  -c 'model_providers.litellm.base_url="https://<host>/v1"' \
  -c 'model_providers.litellm.env_key="LITELLM_KEY"' \
  -c 'model_providers.litellm.wire_api="responses"' \
  -c model_provider=litellm -m oci-auto-trained \
  "In one sentence: what does HTTP status 429 mean?"
```

To make it the default, put the same in `~/.codex/config.toml`:

```toml
model_provider = "litellm"
model = "oci-auto-trained"

[model_providers.litellm]
name = "LiteLLM on OCI"
base_url = "https://<host>/v1"
env_key = "LITELLM_KEY"
wire_api = "responses"
```

Ask for `oci-code` instead of `oci-auto-trained` to force every turn onto
Codex's own model.

### Against a laptop gateway

A plain LiteLLM process on the repo's config is the quickest way to test:

```shell
mkdir -p out
LITELLM_PORT=4400 nohup scripts/gateway.sh > out/gateway.log 2>&1 &
export LITELLM_KEY="$(cat ~/.config/litellmdemo/master_key)"
codex exec -c 'model_providers.litellm.base_url="http://127.0.0.1:4400/v1"' \
  -c 'model_providers.litellm.env_key="LITELLM_KEY"' -c 'model_providers.litellm.wire_api="responses"' \
  -c model_provider=litellm -m oci-auto-trained "Fix the data race in main.go so it always prints 1000."
```

### Prove it

`scripts/codex_e2e.py` runs three Codex jobs in fresh directories (a chat
question, a Go race fix, a question in Spanish), then checks from outside: the
gateway's ROUTE lines must name only the expected models with no fallback,
and the code must pass `go vet` and the race detector.

```shell
# a laptop gateway on 4400, started as above
LITELLM_GATEWAY=http://127.0.0.1:4400 GATEWAY_LOG=out/gateway.log uv run python scripts/codex_e2e.py --runs 2
# the cloud: stream the pod's log to a file first, then point the check at the public URL and the Codex key
KUBECONFIG=~/.config/litellmdemo/kubeconfig kubectl logs -n litellmdemo deploy/litellm-gateway -c gateway -f > out/oke-gateway.log &
LITELLM_GATEWAY=https://<host> GATEWAY_LOG=out/oke-gateway.log \
  LITELLM_API_KEY="$(cat ~/.config/litellmdemo/codex_key)" uv run python scripts/codex_e2e.py
```

Ends with `CODEX E2E OK (n/n)`. Paid: cents to about $0.50 a run, most of it
the code case. `evidence/codex/codex-e2e-2026-10-15.md` and
`evidence/codex/codex-e2e-2026-11-03.md` are passing runs on a laptop gateway.

## Codex, as the operator

Codex can also build and check the demo from a clone. It follows
`codex/SPEC.md`, the rules in `AGENTS.md`, and the skills in
`.agents/skills/`; `codex/README.md` has the details.

Get the cloud demo ready for a talk:

```shell
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  --add-dir ~/.config/litellmdemo --add-dir ~/.kube \
  --add-dir ~/.cache/uv --add-dir ~/.local/share/uv --add-dir ~/.npm \
  "$(cat codex/PROMPT-ops.md)"
```

Build it in your tenancy from scratch, interactively. Codex shows the
preflight and the plan, and waits for your yes before the first cloud change:

```shell
codex -s workspace-write -c sandbox_workspace_write.network_access=true \
  --add-dir ~/.config/litellmdemo --add-dir ~/.kube \
  --add-dir ~/.cache/uv --add-dir ~/.local/share/uv --add-dir ~/.npm \
  "$(cat codex/PROMPT.md)"
```

The laptop versions are `codex/PROMPT-ops-laptop.md` and
`codex/PROMPT-laptop.md`; add
`--add-dir ~/.rd --add-dir ~/.config/openshell --add-dir ~/.local/state/openshell`.
The OCI login is the one step Codex cannot do: run it in your own terminal
when the skill asks.

## Every check, and what it ends with

| Claim | Command | Ends with |
|---|---|---|
| the cloud, from the outside | `scripts/oci/preflight.sh` | `CLOUD PREFLIGHT OK` |
| the laptop, end to end | `scripts/preflight.sh` | `PREFLIGHT OK` |
| each routing behaviour | `LITELLM_GATEWAY=<gateway> uv run python scripts/probe_routes.py` | `ROUTES OK` |
| every use case through the agent | `LITELLMDEMO_APP=<app> uv run python scripts/e2e.py` | `E2E OK` |
| the screens, in a browser | `LITELLMDEMO_APP=<app> node web/scripts/ui-e2e.mjs` | `UI E2E OK` |
| Codex through the gateway | `LITELLM_GATEWAY=<gateway> GATEWAY_LOG=<log> uv run python scripts/codex_e2e.py` | `CODEX E2E OK` |
| requests survive a classifier outage | `scripts/oci/chaos.sh` | `CHAOS OK` |
| signing survives token rotation (70 min) | `scripts/oci/soak.sh` | `SOAK OK` |
| the control room survives a gateway outage | `uv run python scripts/failover.py` | `FAILOVER OK` |

One probe fails by design: "trained: constrained planning" expects REASONING
and gets COMPLEX. That is the router's documented known miss, not a bug to fix
in the check.

## When something fails

Both preflights print the fix for every failing check. The table in
`.agents/skills/litellm-demo-ops/SKILL.md` lists every cause seen so far. The
ones that come up most:

| You see | Do |
|---|---|
| `kubectl` times out or is refused on 6443; SSH to the VM is refused | your address is not on the allow list: set `api_allow_cidr`, then `scripts/oci/up.sh && scripts/oci/control.sh` |
| the CODE route answers with GPT-5.1, not Codex | the cluster runs an older `gateway/`: `scripts/oci/deploy.sh` |
| `/v1/models` on the public URL returns HTML | the API gateway has only the catch-all route: `scripts/oci/edge.sh` |
| a Codex request gets 404 from OCI's Responses API | the node's policy lacks the `generative-ai-response` statement: `scripts/oci/up.sh` reconciles it |
| the VM's services are down | `scripts/oci/control.sh ssh 'systemctl --user restart openshell-gateway litellmdemo-control'` |
| laptop: "OCI session expired" | log in in your own terminal, then `scripts/local/push-session.sh` |
| laptop: `ImagePullBackOff` on a `docker.io` image | Docker Hub is blocked behind the corporate proxy; the manifests use ghcr.io and quay.io |
| the sandbox reaches something in "Try to escape" | a policy regression: stop and report, do not loosen anything |

Never edit `gateway/`, `classifier/`, `app/` or `scripts/` to make a check
pass.
