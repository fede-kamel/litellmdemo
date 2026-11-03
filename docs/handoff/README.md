# Start here

Personal work. Northwind Cloud and all its data are fictional.

## Read first

[LiteLLM-Codex-routing-writeup.pdf](LiteLLM-Codex-routing-writeup.pdf) is the one document that explains the
whole thing: why route per request, how the router was trained on graded answers, the agent in a sandbox with
no key, the demo in one OCI tenancy, and Codex as both the client of the gateway and the operator that builds
it. Twelve pages, with the figures, the field notes and the references.

## Then run it

In reading order:

| File | What it is for |
|---|---|
| [README.md](../../README.md) | what the demo is: the routes and models, the router, the results, the field notes |
| [docs/RUNBOOK.md](../RUNBOOK.md) | spin up and run: prerequisites, the cloud path, the laptop path, Codex as client, Codex as operator, every check |
| [docs/DEMO.md](../DEMO.md) | the talk: what to click and what to say, about 8 minutes |
| [AGENTS.md](../../AGENTS.md) | the rules a coding agent follows here: secrets, clusters, data, spend, integrity |
| [codex/README.md](../../codex/README.md) | the Codex harness: the prompts, the flags, what you can ask Codex |
| [codex/SPEC.md](../../codex/SPEC.md), [PROMPT.md](../../codex/PROMPT.md), [PROMPT-ops.md](../../codex/PROMPT-ops.md) | build the demo in an OCI tenancy with Codex; get it ready for a talk |
| [codex/SPEC-laptop.md](../../codex/SPEC-laptop.md), [PROMPT-laptop.md](../../codex/PROMPT-laptop.md), [PROMPT-ops-laptop.md](../../codex/PROMPT-ops-laptop.md) | the same on one laptop |
| [.agents/skills/](../../.agents/skills/) | the how-to for each part, one skill per folder |

The skills: `litellm-demo-ops` (bring it up, check it, fix it), `litellm-oci-gateway` (the gateway and OCI
signing), `litellm-oci-routing` (which routing feature fits which need), `litellm-route-classifier` (generate,
label, train, evaluate), `litellm-route-verify` (the probes, the end-to-end tests, the evidence).

From a clone, `codex/README.md` has the one-line commands that hand the whole job to Codex.
