# Agent instructions

This repository is a runnable demo: a LiteLLM AI Gateway routes every request
an application sends across twenty OCI Generative AI models, deciding the
route with a router we trained; a langchain-oci agent runs inside an NVIDIA
OpenShell sandbox that holds no key, and a web control room shows every
decision with LiteLLM's and OpenShell's own logs. The skills in
`.agents/skills/` hold the how-to for each part; start with
`litellm-demo-ops`. `codex/SPEC.md` is the build specification and
`codex/PROMPT*.md` drive an agent through the common tasks.

## Hard rules

- Secrets. Never ask for, echo, log, or store a password, key, or token.
  `~/.config/litellmdemo/` (config, master key, agent keys, database password)
  and `~/.oci/` stay where they are; scripts read them. The OCI session is
  renewed by the operator in their own terminal (`oci session authenticate`).
- Clusters. The local `rancher-desktop` cluster is yours to deploy to
  (`scripts/local/deploy.sh`). The OKE cluster is read-only for you, and no
  other cluster, GPU instance or cloud resource may be created or changed,
  unless the operator asks for it by name.
- Data. Every scenario is about a fictional company (Northwind Cloud). Never
  add real customer data.
- Spend. Labelling (`classifier/label.py`, about $18 a run), the model trial
  (`classifier/model_trial.py`) and the robustness test (`classifier/robustness.py`,
  about $15) make many paid OCI calls: run them only when the task asks for it.
  `classifier/generate.py` replaces the prompts the labels depend on.
- Integrity. Do not modify `gateway/`, `classifier/`, `app/` or `scripts/` to
  make a check pass. A test expectation changes only with the outcome data that
  justifies it, written next to it. Explain and stop instead.

## Where things are

| Path | Purpose |
|---|---|
| `gateway/` | LiteLLM config (routes, prices, tags, fallbacks, auto-routers); hooks: OCI signing, the decision header, the console line; the trained-classifier plugin; the OCI Responses provider (Codex) |
| `classifier/` | generate, label by outcome, the ladder, train, evaluate, the model trial, the robustness test, the classifier service |
| `app/` | the langchain-oci agent (single run, or plan mode: a planner, then each task routed on its own), its tools, the use cases; `sandbox_run.py` runs it inside OpenShell |
| `sandbox/` | the OpenShell image, provider profile and policy |
| `ui/`, `web/` | the control room: FastAPI backend (runs, sandbox bridge, console, replay), React front end |
| `deploy/k8s/` | the manifests, the same for OKE and the local cluster |
| `scripts/` | `demo-up.sh`, `preflight.sh`, `openshell.sh`, `local/` (Rancher Desktop), `oci/` (OKE), the checks |
| `.agents/skills/` | `litellm-demo-ops`, `litellm-oci-gateway`, `litellm-oci-routing`, `litellm-route-classifier`, `litellm-route-verify` |
| `evidence/` | transcripts behind every claim |
| `codex/` | the specification and the prompts |

## Verifying

- `scripts/preflight.sh` ends with `PREFLIGHT OK`.
- `LITELLM_GATEWAY=http://127.0.0.1:30400 uv run python scripts/probe_routes.py` ends with `ROUTES OK`.
- With the control room on 8780, `uv run python scripts/e2e.py` ends with `E2E OK`.
- `cd web && node scripts/ui-e2e.mjs` ends with `UI E2E OK`.

## Writing

Active voice, short sentences, commands in `shell` fences. Keep the
disclaimer that this is personal work with a fictional company's data.
Never mention accounts, OCIDs, profile names, or key values.
