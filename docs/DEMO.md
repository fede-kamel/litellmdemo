# The demo, step by step

Personal work; Northwind Cloud and all its data are fictional.

## The day before

```shell
scripts/demo-up.sh                        # ends with PREFLIGHT OK (n/n)
uv run python scripts/record_runs.py      # a recorded run of every use case, for replay if the network fails
```

## One hour before

1. Log in to OCI in your own terminal, so the session outlasts the talk
   (the header shows "OCI session NN min"; you want more than 60):
   `oci session authenticate --profile-name <profile> --region us-ashburn-1`, then `scripts/local/push-session.sh`.
2. On the venue's network: `scripts/demo-up.sh` → `PREFLIGHT OK`.
3. Open http://127.0.0.1:8780 in Chrome, full screen. Run "FAQ: reset a password" once to warm everything up.
4. Have the deck open on slide 20 (the demo divider).

## The click path (about 8 minutes)

Each use case is in the left rail, in this order. Click it, then **Route it**.
Half the steps show a LiteLLM feature with no classifier in it; the "Shows" column keeps the balance visible.

| # | Use case | Shows | Say | Point at |
|---|---|---|---|---|
| 1 | Customer support · FAQ: reset a password | router | "An easy question. LiteLLM sends it to the fastest, cheapest model." | What happened: SIMPLE, 89% ≥ 75% bar → a fast model (GPT-6-luna or GPT-5.4-nano), a fraction of a cent |
| 2 | Customer support · Billing dispute | router + tools | "A routine reply that needs two lookups. Watch the agent work: it asks for a tool, the agent runs it, the model reads the result. LiteLLM classifies every one of those calls." | the agent trace: each call's decision, each tool with its arguments and what it returned |
| 3 | (same run) | LiteLLM: keys | "The sandbox holds no key. LiteLLM gave the agent a virtual key: five model groups, $5 every 30 days, 120 requests a minute. Anything else is a 403, and the spend is LiteLLM's own accounting." | the LiteLLM card in the strip: allowed groups, spend against the budget |
| 4 | (same run) | LiteLLM: every call | "LiteLLM classified every call, and they all got the same route, because they all carry the same request. To give each part its own model, split the job: that is step 6." | the grey hint under What happened |
| 5 | Premium customer · Same request, premium contract | LiteLLM: tags | "No classifier here: a business rule. A premium tag on the request takes the premium lane. One line of config." | GPT-5.2, where untagged traffic gets Gemini 2.5 Flash |
| 6 | Multi-step agent · Invoice photo to reply | router | "Now one job, split into tasks. Each task reaches LiteLLM as its own request." | the photo task goes to VISION, the compare to fast, the check to Codex: four routes in one job |
| 7 | Coding assistant · Debug a race condition | LiteLLM: custom provider | "Code goes to Codex, which OCI serves only on its Responses API. LiteLLM plugs that in as a custom provider, behind the same route." | CODE → gpt-5.3-codex |
| 8 | Multilingual service · Japanese request | router: rule | "A rule, not a guess: another language goes to the multilingual model." | the "written in Japanese" line in Why |
| 9 | Resilience · A deployment fails | LiteLLM: fallbacks | "A deployment fails. LiteLLM falls back and the answer still arrives." | fallback ×1 → oci-balanced |
| 10 | Try to escape the sandbox (in the strip) | OpenShell + LiteLLM | "The agent tries to reach OCI, OpenAI and the gateway's admin API directly. OpenShell refuses all three; the gateway is its only way out." | three REFUSED lines |

If there is time:

- **Customer support · Escalation with SLA credits**: the router sends it to the strong route. Said plainly, this is
  the router's known miss: on this prompt the reasoning route passed 4 times in 4 and the strong route once
  (`evidence/strong-vs-reasoning.json`). A good moment for "routing is a prediction; measure it".

- **Multi-step agent · Escalation, end to end**: lookup, the credit, a reply in Spanish, a Python function; Codex on the last task, click a call to show its ladder.
- **Drag the quality bar**, rerun step 2: one dial between spend and quality, per request.
- **How the router decides** → **The gateway**: every route, its models and its fallbacks, read from LiteLLM's config; "Beyond classification" lists the context-window fallback (a prompt too big for `oci-compact` moves to `oci-long` before the call, checked by `scripts/probe_routes.py`).
- **How the router decides** → **Compare routers**: the same request through LiteLLM's heuristic, its LLM classifier and our ladder.

The console at the bottom shows LiteLLM's and OpenShell's own log lines for every step; point at a `ROUTE` line once.

If someone asks what the classifier runs on: a CPU, no GPU. A frozen e5-small encoder and small logistic models answer in tens of milliseconds;
if the classifier is down or slow, LiteLLM routes to `fallback_tier` and the request still gets an answer.

## If something goes wrong

| You see | It means | Do |
|---|---|---|
| a **REPLAY** banner | the live path did not answer; this is a recorded run of the same request | keep going, and say it is a recording |
| "the run started again on the host agent" | the sandbox did not answer; the host agent answered through the gateway | keep going; mention it is the failover |
| a wrong number in a multi-step answer | an arithmetic task landed on a cheaper route (about 1 run in 6 in testing) | the teaching moment: drag the quality bar up and rerun |
| "OCI session expired" in the header | the session ran out | replays still work; log in again after the talk |
| a run taking over a minute | a reasoning model (Grok 4.7 has taken up to 2.5 minutes once) | talk over it, or switch to the next use case |

`scripts/preflight.sh` prints the fix for every failing check.
