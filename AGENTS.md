# Agent instructions

This repository is a runnable demo: a LiteLLM AI Gateway routes every request
an application sends across fifteen OCI Generative AI models, deciding the
route with a classifier we mini-trained; a langchain-oci agent and a web
control room show each decision. The specification for building and running
it is `codex/SPEC.md`; `codex/PROMPT.md` drives an agent through it. The
skills in `.agents/skills/` hold the how-to for each part. Read the
specification before running anything.

## Hard rules

- Secrets. Never ask for, echo, log, or store a password, key, or token.
  `~/.config/litellmdemo/config.json` and `master_key` stay where they are;
  scripts read them. The OCI session is renewed by the operator in their own
  terminal (`oci session authenticate`).
- Local only. The gateway, the classifier and the web app run on this machine.
  Never create, use or deploy to a cluster, a GPU instance, or any cloud
  resource without the operator's explicit go-ahead naming it.
- Data. Every scenario is about a fictional company (Northwind Cloud). Never
  add real customer data.
- Spend. `classifier/label.py` costs about $5 in OCI calls and
  `classifier/generate.py` replaces the prompts the labels depend on: run
  them only when the task asks for it.
- Integrity. Do not modify `gateway/`, `classifier/`, `app/` or `scripts/` to
  make a check pass. Explain and stop instead.

## Where things are

| Path | Purpose |
|---|---|
| `gateway/` | LiteLLM config (routes, tags, fallbacks, auto-routers), OCI session signer, the trained-classifier plugin |
| `classifier/` | generate, label by outcome, mini-train, evaluate; the shared `router_model.py` |
| `app/` | the langchain-oci agent, its tools, the use-case scenarios |
| `ui/`, `web/` | the control room: FastAPI backend, React front end |
| `scripts/` | `gateway.sh`, `probe_routes.py`, `e2e.py` |
| `.agents/skills/` | `litellm-oci-gateway`, `litellm-oci-routing`, `litellm-route-classifier`, `litellm-route-verify` |
| `evidence/` | transcripts behind every claim |
| `codex/` | the specification and the prompt |

## Verifying

- `uv run python scripts/probe_routes.py` ends with `ROUTES OK`.
- With the web app on 8780, `uv run python scripts/e2e.py` ends with `E2E OK`.
- `cd web && node scripts/ui-e2e.mjs` ends with `UI E2E OK`.

## Writing

Active voice, short sentences, commands in `shell` fences. Keep the
disclaimer that this is personal work with a fictional company's data.
Never mention accounts, OCIDs, profile names, or key values.
