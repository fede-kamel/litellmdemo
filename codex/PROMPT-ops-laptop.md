Get this demo ready for a talk, on this laptop, and report.

Read AGENTS.md, then the litellm-demo-ops skill, and follow it:

1. Run scripts/demo-up.sh (it is idempotent) and then scripts/preflight.sh.
2. For every failing check, apply the fix the skill gives for that check, then run the preflight again.
   Stop and report instead if the fix needs the operator (the OCI login), a secret, a change to
   gateway/, classifier/, app/ or scripts/ to make a check pass, or any cluster other than rancher-desktop.
3. Run one request through the OpenShell sandbox with scripts/openshell.sh ask and the escape probe
   with scripts/openshell.sh probe.
4. Report, in a short table: each preflight check with its result, what you fixed and how, the sandbox
   request's route and model, the probe's three results, and the OCI session's minutes left.
   End with the preflight's last line. Never print a key or a token.
