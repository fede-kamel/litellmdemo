Build and verify this LiteLLM routing demo by following `codex/SPEC.md` exactly.
Read the spec in full before you run anything, obey `AGENTS.md`, and use the
skills in `.agents/skills/` for how each part works.

If I put an "Operator context" block above this prompt, use it as my answers.
Otherwise ask only for what SPEC section 1 requires and you cannot detect.

Show me the preflight table from SPEC section 2. If the OCI session check
fails, tell me to re-authenticate in my own terminal and stop.

Run SPEC section 4 from the repository root, foreground, with stdin from
`/dev/null`. If a check fails, match it against SPEC section 6 and the
`litellm-route-verify` skill before doing anything else, tell me what
happened, and retry at most twice.

Do not run `classifier/label.py` or `classifier/generate.py` unless I say so.

Give me the report in SPEC section 7.
