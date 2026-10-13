# The demo, step by step

Personal work; Northwind Cloud and all its data are fictional.

## The day before

The demo runs in Oracle Cloud; the laptop only needs a browser. `scripts/oci/edge.sh`
prints the public URL.

```shell
scripts/oci/preflight.sh                                          # ends with CLOUD PREFLIGHT OK (n/n)
LITELLMDEMO_APP=https://<host> uv run python scripts/record_runs.py   # a recorded run of every use case, for replay if a model is slow
```

## One hour before

1. `scripts/oci/preflight.sh` → `CLOUD PREFLIGHT OK`. Nothing to log in to: the gateway
   signs as its OKE node (the header says so).
2. Open the public URL in Chrome, full screen. Run "FAQ: reset a password" once to warm everything up.
3. Have the deck open on slide 20 (the demo divider).

Without the cloud, the laptop path still works: `scripts/demo-up.sh` → `PREFLIGHT OK`, log in to OCI
first in your own terminal (`oci session authenticate --profile-name <profile> --region us-ashburn-1`,
then `scripts/local/push-session.sh`), and open http://127.0.0.1:8780.

## The screen

Three numbered parts, top to bottom: **The request** (pick a use case, Route it), **The decision**
(the route, the model, and why, in one sentence; each route's chance of a good answer beside it) and
**The answer**. Everything else is under **Details**, one tab at a time: *Every call* (the agent trace,
with LiteLLM's decision on each call), *Route map*, *Why, in detail* (every check and the closest
training requests), *Sandbox* (what OpenShell allowed and refused; the escape button) and the *Sandbox console*,
open by default: every connection the sandbox opens or is refused, with the policy that decided it, and LiteLLM's
`ROUTE` line for every request. The header's **Safety** button explains the three layers (OpenShell, LiteLLM, OCI)
and has the escape button too.

## The click path (about 8 minutes)

Each use case is in the left rail, in this order. Click it, then **Route it**.
Half the steps show a LiteLLM feature with no classifier in it; the "Shows" column keeps the balance visible.

| # | Use case | Shows | Say | Point at |
|---|---|---|---|---|
| 1 | Customer support · FAQ: reset a password | router | "An easy question. LiteLLM sends it to the fastest, cheapest model." | What happened: SIMPLE, 89% ≥ 75% bar → a fast model (GPT-6-luna or GPT-5.4-nano), a fraction of a cent |
| 2 | Customer support · Billing dispute | router + tools | "A routine reply that needs two lookups. Watch the agent work: it asks for a tool, the agent runs it, the model reads the result. LiteLLM classifies every one of those calls." | the agent trace: each call's decision, each tool with its arguments and what it returned |
| 3 | (same run) | LiteLLM: keys | "The sandbox holds no key. LiteLLM gave the agent a virtual key: five model groups, $5 every 30 days, a rate limit. Anything else is a 403, and the spend is LiteLLM's own accounting." | the line under the request: the key, its spend against the budget; Details → Sandbox for the five steps |
| 4 | (same run) | LiteLLM: every call | "LiteLLM classified every call, and they all got the same route, because they all carry the same request. To give each part its own model, split the job: that is step 6." | Details → Every call: the hint, then the trace |
| 5 | Premium customer · Same request, premium contract | LiteLLM: tags | "No classifier here: a business rule. A premium tag on the request takes the premium lane. One line of config." | GPT-5.2, where untagged traffic gets Gemini 2.5 Flash |
| 6 | Multi-step agent · Invoice photo to reply | router | "Now one job, split into tasks. Each task reaches LiteLLM as its own request." | the photo task goes to VISION, the compare to fast, the check to Codex: four routes in one job |
| 7 | Coding assistant · Debug a race condition | LiteLLM: custom provider | "Code goes to Codex, which OCI serves only on its Responses API. LiteLLM plugs that in as a custom provider, behind the same route." | CODE → gpt-5.3-codex |
| 8 | Multilingual service · Japanese request | router: rule | "A rule, not a guess: another language goes to the multilingual model." | the "written in Japanese" line in Why |
| 9 | Resilience · A deployment fails | LiteLLM: fallbacks | "A deployment fails. LiteLLM falls back and the answer still arrives." | fallback ×1 → oci-balanced |
| 10 | Details → Sandbox → Try to escape | OpenShell + LiteLLM | "The agent tries to reach OCI, OpenAI and the gateway's admin API directly. OpenShell refuses all three; the gateway is its only way out." | three REFUSED lines |

If there is time:

- **Customer support · Escalation with SLA credits**: the router sends it to the strong route. Said plainly, this is
  the router's known miss: on this prompt the reasoning route passed 4 times in 4 and the strong route once
  (`evidence/strong-vs-reasoning.json`). A good moment for "routing is a prediction; measure it".

- **Multi-step agent · Escalation, end to end**: lookup, the credit, a reply in Spanish, a Python function; Codex on the last task, click a call to show its ladder.
- **Drag the quality bar**, rerun step 2: one dial between spend and quality, per request.
- **How the router decides** → **The gateway**: every route, its models and its fallbacks, read from LiteLLM's config; "Beyond classification" lists the context-window fallback (a prompt too big for `oci-compact` moves to `oci-long` before the call, checked by `scripts/probe_routes.py`).
- **How the router decides** → **Compare routers**: the same request through LiteLLM's heuristic, its LLM classifier and our ladder.

The Sandbox console (Details → Sandbox console) shows OpenShell's and LiteLLM's own lines for every step, `ALLOWED` and `DENIED` with the policy; point at a `ROUTE` line once.

If someone asks what the classifier runs on: a CPU, no GPU. A frozen e5-small encoder and small logistic models answer in tens of milliseconds;
if the classifier is down or slow, LiteLLM routes to `fallback_tier` and the request still gets an answer.

## If something goes wrong

| You see | It means | Do |
|---|---|---|
| a **REPLAY** banner | the live path did not answer; this is a recorded run of the same request | keep going, and say it is a recording |
| "the run started again on the host agent" | the sandbox did not answer; the host agent answered through the gateway | keep going; mention it is the failover |
| a wrong number in a multi-step answer | an arithmetic task landed on a cheaper route (about 1 run in 6 in testing) | the teaching moment: drag the quality bar up and rerun |
| "OCI session expired" in the header (laptop only) | the session ran out | replays still work; log in again after the talk |
| the page does not load | the API gateway, the VM or the control room | `scripts/oci/preflight.sh` names the piece and its fix |
| a run taking over a minute | a reasoning model (Grok 4.7 has taken up to 2.5 minutes once) | talk over it, or switch to the next use case |

`scripts/oci/preflight.sh` (the cloud) and `scripts/preflight.sh` (the laptop) print the fix for every failing check.

## Videos of the beats

For a room where the live path is slow (every run pays about six seconds of
sandbox start-up before the first model call, and a reasoning model can think
for a minute), record the beats the day before and keep them in the deck:

```shell
LITELLMDEMO_APP=https://<host> node web/scripts/record-demo.mjs ~/Downloads/litellmdemo-videos
```

One video per beat, run through the real control room the way a click does:
the billing dispute with every call and the sandbox console, the premium lane,
the invoice-photo plan, "Try to escape", the failing deployment, the Japanese
request, the race-condition fix on Codex, and the three routers compared. Each
is a `.webm` and, with ffmpeg installed, an `.mp4` that PowerPoint and Keynote
play. `ONLY=invoice` records one beat again.
