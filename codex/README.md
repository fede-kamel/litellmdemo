# Build and run this with Codex

| File | What it is |
|---|---|
| [`PROMPT-ops.md`](PROMPT-ops.md) | get the demo ready for a talk, fix what fails, report: the everyday task |
| [`PROMPT.md`](PROMPT.md) and [`SPEC.md`](SPEC.md) | build it from a clone, step by step with checkpoints |
| [`../AGENTS.md`](../AGENTS.md) | what Codex loads automatically: the hard rules and the layout |
| [`../.agents/skills/`](../.agents/skills/) | the how-to, one skill per part; `litellm-demo-ops` first |

```shell
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  --add-dir ~/.config/litellmdemo --add-dir ~/.kube --add-dir ~/.rd \
  --add-dir ~/.cache/uv --add-dir ~/.local/share/uv --add-dir ~/.npm \
  "$(cat codex/PROMPT-ops.md)"
```

`workspace-write` is enough. Codex may read anywhere; the flags let it write
where the demo keeps its run state, kubectl's cache, Rancher Desktop's Docker
socket and the package caches, and reach the network (the gateways, OCI).
Codex never needs a secret: the one step that does, the OCI login, the
operator runs in their own terminal, and the skill says so.

## What you can ask Codex

| Ask | It uses |
|---|---|
| "Get the demo ready for my talk" | `litellm-demo-ops`: demo-up, preflight, the fix for each failing check |
| "The control room stopped answering" | `litellm-demo-ops`: the console's ROUTE lines, then the matching fix |
| "Add model X to the balanced route" | `litellm-oci-gateway`: smoke test, price from OCI's list, config, probes; then `litellm-route-classifier` to relabel and retrain |
| "Is the router still good?" | `litellm-route-classifier` and `litellm-route-verify`: evaluate, the robustness test, every check |

## Recorded runs

See [`../evidence/codex/`](../evidence/codex/).
[`codex-ops-run1-2026-10-06.log`](../evidence/codex/codex-ops-run1-2026-10-06.log)
is the ops prompt above, run once against the local setup: Codex ran the
preflight (`PREFLIGHT OK (14/14)`), sent one request through the sandbox (fast
route, GPT-6-luna), ran the escape probe (3 of 3 refused) and reported, in
about 34k tokens. The profile name is redacted.
