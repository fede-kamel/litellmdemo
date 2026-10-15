# Build and run this with Codex

Personal work; Northwind Cloud and its data are fictional.

| File | What it is |
|---|---|
| [`PROMPT-ops.md`](PROMPT-ops.md) | get the demo in Oracle Cloud ready for a talk, fix what the scripts can fix, report: the everyday task |
| [`PROMPT.md`](PROMPT.md) and [`SPEC.md`](SPEC.md) | build it in your OCI tenancy from a clone, step by step with checkpoints |
| [`PROMPT-ops-laptop.md`](PROMPT-ops-laptop.md), [`PROMPT-laptop.md`](PROMPT-laptop.md) and [`SPEC-laptop.md`](SPEC-laptop.md) | the same on one laptop (Rancher Desktop, an OCI session) |
| [`../AGENTS.md`](../AGENTS.md) | what Codex loads automatically: the hard rules and the layout |
| [`../.agents/skills/`](../.agents/skills/) | the how-to, one skill per part; `litellm-demo-ops` first |

In Oracle Cloud:

```shell
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  --add-dir ~/.config/litellmdemo --add-dir ~/.kube \
  --add-dir ~/.cache/uv --add-dir ~/.local/share/uv --add-dir ~/.npm \
  "$(cat codex/PROMPT-ops.md)"
```

To build it, write `~/.config/litellmdemo/deploy.json` from
`deploy/deploy.example.json`, then run `codex` with the same flags and
`"$(cat codex/PROMPT.md)"`, interactively: Codex shows the preflight and the
plan (what it will create, the sizes, what it costs) and waits for your yes
before the first cloud change. Then it runs the five scripts that build the
demo, records the runs for replay, and runs the four checks.

`workspace-write` is enough. Codex may read anywhere; the flags let it write
where the demo keeps its state and kubectl its cache, fill the package caches,
and reach the network (OCI, the cluster, the VM, the public URL). Codex never
needs a secret: the scripts read the OCI API key through the OCI CLI and the
gateway's keys from `~/.config/litellmdemo/`, and print neither. On the laptop
path add `--add-dir ~/.rd --add-dir ~/.config/openshell --add-dir ~/.local/state/openshell`;
the one step that needs a person there, the OCI login, the operator runs in
their own terminal, and the skill says so.

## What you can ask Codex

| Ask | It uses |
|---|---|
| "Build the demo in my tenancy" | `PROMPT.md`, `SPEC.md`: the preflight, the plan, five build scripts, the recorded runs, four checks |
| "Get the demo ready for my talk" | `PROMPT-ops.md` and `litellm-demo-ops`: the cloud preflight, the fixes the scripts can make, a request on three routes, the escape probe |
| "The control room stopped answering" | `litellm-demo-ops`: the console's ROUTE lines, then the matching fix |
| "Add model X to the balanced route" | `litellm-oci-gateway`: smoke test, price from OCI's list, config, probes; then `litellm-route-classifier` to relabel and retrain. The model trial and the relabel are paid: Codex asks before it spends |
| "Is the router still good?" | `litellm-route-classifier` and `litellm-route-verify`: the evaluation and every check; the robustness test is paid (about $15), so Codex asks first |

## Recorded runs

See [`../evidence/codex/`](../evidence/codex/).

- [`codex-ops-run1-2026-10-06.log`](../evidence/codex/codex-ops-run1-2026-10-06.log):
  the laptop ops prompt, run once against the local setup. Codex ran the
  preflight (`PREFLIGHT OK (14/14)`), sent one request through the sandbox
  (fast route, GPT-6-luna), ran the escape probe (3 of 3 refused) and
  reported, in about 34k tokens. The profile name is redacted.
