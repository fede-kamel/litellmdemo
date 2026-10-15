Build this LiteLLM routing demo in my OCI tenancy by following `codex/SPEC.md`
exactly, and prove it works. Read the spec in full before you run anything,
obey `AGENTS.md`, and use the skills in `.agents/skills/` for how each part
works; start with `litellm-demo-ops`. Where a skill and the spec differ, the
spec and `AGENTS.md` win.

If I put an "Operator context" block above this prompt, use it as my answers.
Otherwise ask only for what SPEC section 1 requires and you cannot detect.

Show me the preflight table from SPEC section 2. If a check fails that only I
can fix (the deploy config, the OCI profile, the SSH key, Node), tell me what
to do and stop.

Then show me the plan from SPEC section 4.0 and wait for my yes. Do not create
or change anything in the cloud before it.

Run SPEC sections 4.1 to 4.7 in order, from the repository root, foreground,
with stdin from `/dev/null`. If a step fails, match it against SPEC section 6
and the `litellm-demo-ops` skill before doing anything else, tell me what
happened, and when the fix is a rerun of the same script after its cause is
gone, rerun it at most twice. A known miss in section 6 is not a failure:
report it and go on. Never edit `gateway/`, `classifier/`, `app/` or
`scripts/` during the build.

Do not run `classifier/label.py`, `classifier/generate.py`,
`classifier/model_trial.py`, `classifier/robustness.py` or
`scripts/oci/down.sh`. Never print a key, a token or an OCID.

Give me the report in SPEC section 7.
