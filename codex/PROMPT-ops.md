Get this demo ready for a talk, in Oracle Cloud, and report. It is already built (codex/SPEC.md);
this checks it and fixes what the scripts can fix.

Read AGENTS.md, then the litellm-demo-ops skill, and follow them. Run everything from the repository
root, in the foreground, with stdin from /dev/null. First make sure the checkout is ready:
uv sync, and (cd web && npm ci) if web/node_modules is missing.

1. Run: uv run scripts/oci/preflight.sh
   When it passes, its last line ends with the public URL. When it fails, read the URL with:
   python3 -c "import json,os; print('https://' + json.load(open(os.path.expanduser('~/.config/litellmdemo/oci-state.json')))['api_hostname'])"
   In every later shell, set URL to that value first (URL=https://...).
2. For every failing check, the preflight prints its fix. Run that fix only if it is
   scripts/oci/deploy.sh, scripts/oci/control-deploy.sh or scripts/oci/edge.sh (they reconcile the
   demo's own resources and are idempotent), as uv run scripts/oci/<script>.sh </dev/null, then run
   the preflight again. If the fix is anything
   else, needs a secret, needs the operator, or needs a change to gateway/, classifier/, app/ or
   scripts/, do not run it: report the check, its cause (the skill's table) and the fix, and go on.
3. Send three requests through the agent in its OpenShell sandbox, one at a time:
   LITELLMDEMO_APP="$URL" uv run python scripts/e2e.py --only support-faq --evidence out/ops-faq
   LITELLMDEMO_APP="$URL" uv run python scripts/e2e.py --only code-race --evidence out/ops-code
   LITELLMDEMO_APP="$URL" uv run python scripts/e2e.py --only lang-ja --evidence out/ops-ja
   In each out/ops-*/e2e.jsonl, runtime must be ["openshell"] and sandbox_network must list the
   sandbox's connections; otherwise the run came from the host agent or a replay: say so.
4. Run the escape probe: curl -fsS -m 120 -X POST "$URL/api/sandbox/probe"
   It must return three tries, each REFUSED, and its network list should show the refusals. If a try
   reaches its target, stop: that is a policy regression; report it and do not loosen anything. If the
   call itself fails, the probe is inconclusive: say so.
5. Read the agent key's spend: curl -fsS -m 60 "$URL/api/sandbox"
6. Report, in a short table: each preflight check with its result, what you fixed and how (or why you
   did not), each request's route, model, calls, fallbacks, spend and runtime, the probe's three
   results, and the agent key's spend against its budget. Keep the sentence that this is personal
   work with a fictional company's data. End with the preflight's last line.

Never print a key, a token or an OCID. Do not run anything paid beyond step 3.
