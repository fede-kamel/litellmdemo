# The demo in the cloud, checked from the outside (2026-10-12)

Everything ran in one OCI tenancy: the gateway, the classifier and Postgres on
the OKE cluster; the control room, the OpenShell gateway and the agent's
sandbox on the `litellmdemo-control` VM; the API gateway in front. The laptop
only ran the clients below, against the public URL (`scripts/oci/edge.sh`
prints it; it stays out of the repository).

| Check | Command | Result |
|---|---|---|
| every piece, read-only | `scripts/oci/preflight.sh` | `CLOUD PREFLIGHT OK (10/10)` |
| every use case through the public URL | `LITELLMDEMO_APP=https://<host> uv run python scripts/e2e.py` | 15/17 (see below) |
| the screens, clicked in a browser | `LITELLMDEMO_APP=https://<host> node web/scripts/ui-e2e.mjs` | `UI E2E OK (28/28)` |

## The use cases

First pass, with the cluster still on the 6 October code: `E2E FAILED (14/17)`.

- `doc-long` failed with `[Errno 7] Argument list too long`: the control room
  handed the 200 KB request to `scripts/openshell.sh` as one argument, which
  Linux caps at 128 KiB (macOS allowed it). Fixed: the request goes through a
  private file (`ui/sandbox.py`, `scripts/openshell.sh ask @file`). Rerun:
  `PASS doc-long expect LONG_CONTEXT route=LONG_CONTEXT deployment=oci/google.gemini-2.5-flash` → 15/17.
- `agent-plan`: the planner wrote one step (`steps=1`); `agent-incident`: a
  number missing from the answer (`facts=MISSING 51.2`, every task routed). Both
  are the planner's known variance (about 1 run in 6, docs/DEMO.md); the checks
  were not changed.
- Before `scripts/oci/deploy.sh` brought the cluster up to date, CODE answered
  from `openai.gpt-5.1`: the cluster's `gateway-code` ConfigMap had no
  `oci_responses.py` (the Codex provider) and an older classifier head.

## The screens

`UI E2E OK (28/28)` with the redesigned control room (light theme; the request,
the decision, the answer; details in tabs), through the API gateway. The
screenshots in `docs/screenshots/` are from this run.

## Streams through the API gateway

API Gateway closes a response that is silent for 15 s. `/api/console` read for
15 s through the gateway: 120 buffered lines, then `: keep-alive` at 5.2 s,
10.2 s and 15.2 s; the run stream sends the same comment while a model thinks.
