# The demo in the cloud, checked from the outside (2026-10-12)

Everything ran in one OCI tenancy: the gateway, the classifier and Postgres on
the OKE cluster; the control room, the OpenShell gateway and the agent's
sandbox on the `litellmdemo-control` VM; the API gateway in front. The laptop
only ran the clients below, against the public URL (`scripts/oci/edge.sh`
prints it; it stays out of the repository).

| Check | Command | Result |
|---|---|---|
| every piece, read-only | `scripts/oci/preflight.sh` | `CLOUD PREFLIGHT OK (10/10)` |
| every use case through the public URL | `LITELLMDEMO_APP=https://<host> uv run python scripts/e2e.py` | 15/17 on the 6 October head; 14/17 on today's head after the evening's fixes (see below) |
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

Redeployed the same evening with the sandbox console (dark, open by default,
every `ALLOWED`/`DENIED` connection with its policy) and the Safety drawer:
`CLOUD PREFLIGHT OK (10/10)`, then `UI E2E OK (28/28)` through the public URL.
The first rerun was 27/28: the test's "find text" helper took the first match in
the DOM, which since the tab fix can be the hidden copy on the other screen
("unseen prompts" is also in the demo screen's hint), and waited for it to
become visible. The helper now waits for a visible match; the screen itself
was right (the classifier view had loaded, `/api/classifier` answered in
138 ms).

## Two primaries that failed quietly (2026-10-12, late evening)

The console history of the evening's runs showed two `ROUTE-FAIL` lines on
every run of their kind, each answered by a fallback, so every check above had
passed:

- Every CODE call: `openai.gpt-5.3-codex` 404 "Authorization failed or
  requested resource not found" in about 0.1 s, then GPT-5.1 (`fallbacks=1`).
  From inside the gateway pod, signed as the node, `/openai/v1/responses`
  returned that 404 for every model, a made-up name included; from the laptop
  with the operator's key and the same compartment, Codex and GPT-5.1 returned
  200. The node's policy granted `generative-ai-family` in the compartment,
  which Oracle's policy page lists without a Responses resource type. Fix: a
  `generative-ai-response` statement for the node's dynamic group
  (`scripts/oci/up.sh`, which now reconciles the statements).
- The Japanese request's second call: `cohere.command-a-03-2025` 400
  "cannot specify message if the last entry in chat history contains tool
  results", then Gemini 2.5 Flash. Reproduced from the laptop through LiteLLM
  1.104.0 with the operator's identity: LiteLLM keeps `message` and appends the
  tool result to `chatHistory`. Of three shapes tried, OCI accepted a top-level
  `toolResults` with an empty `message`; the answer then failed LiteLLM's
  validation (citations carry `documentIds`, the type wants `document_ids`).
  Fix: `gateway/oci_cohere_fix.py`, both sides; reported upstream as
  BerriAI/litellm#46157.

Checks changed with the fixes: `scripts/probe_routes.py` requires Codex and no
fallback on the code probe, keeps the Spanish probe on Cohere with no fallback,
and adds a probe whose last turn is a tool result; `scripts/e2e.py` fails a
code or multilingual run whose calls fell back or left the route's own models.

After the policy update (`scripts/oci/up.sh`) and the redeploy
(`scripts/oci/deploy.sh`), checked again from the outside:

| Check | Result |
|---|---|
| `/openai/v1/responses` from the gateway pod, signed as the node | 200 |
| `scripts/oci/preflight.sh` | `CLOUD PREFLIGHT OK (10/10)` |
| `scripts/probe_routes.py` against the cluster gateway (port-forward) | 11/12: code → Codex, no fallback; Spanish and the tool-result turn → Cohere, no fallback. The miss is "constrained planning", COMPLEX instead of REASONING: the router's known miss (`strong-vs-reasoning.json`), not changed here |
| `scripts/e2e.py` through the public URL | 14/17, twice in a row: both coding cases on Codex, both language cases on Cohere (the Japanese one in two calls), every other call `fallbacks=0` except the fallback scenario itself. Misses: `support-escalation` and `analyst-forecast` go to the strong route (the same known miss; the afternoon's 15/17 ran on the 6 October head) and `agent-incident` missed its number (51.2) in all three runs of the day, its arithmetic step landing on the strong route |
| `web/scripts/ui-e2e.mjs` through the public URL | `UI E2E OK (28/28)` |

## Streams through the API gateway

API Gateway closes a response that is silent for 15 s. `/api/console` read for
15 s through the gateway: 120 buffered lines, then `: keep-alive` at 5.2 s,
10.2 s and 15.2 s; the run stream sends the same comment while a model thinks.
