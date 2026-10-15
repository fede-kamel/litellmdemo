I reviewed the files locally without running scripts, accessing the network, reading credential directories, or editing files. These findings are ordered by how severely they obstruct a first-time operator.

1. **`codex/SPEC.md:64` — The web install requires an undeclared internal registry.**  
   **Evidence:** `web/package-lock.json:36` and `web/package-lock.json:3401` resolve packages through Oracle’s corporate registry. A stranger outside that network cannot follow the advertised clone-to-build path.  
   **Exact fix:** Regenerate the lockfile against the public npm registry while preserving the selected versions, or explicitly document corporate registry access as a prerequisite.

2. **`codex/SPEC.md:63` — `uv sync` does not prepare the Python interpreter used by the shell scripts.**  
   **Evidence:** `scripts/oci/up.sh:212–220` and `scripts/oci/control-deploy.sh:48–56` invoke bare `python3` and import `yaml`. Synchronizing `.venv` does not activate it.  
   **Exact fix:** After `uv sync`, add `export PATH="$PWD/.venv/bin:$PATH"` and require subsequent commands to use that environment.

3. **`codex/SPEC.md:105` — A fresh `up.sh` run contaminates subnet identifiers with progress output.**  
   **Evidence:** `scripts/oci/up.sh:28` sends `say` output to stdout. The `subnet` function calls it at line 104, while lines 112–113 capture the function’s entire stdout. Line 126 then passes the contaminated value as a subnet identifier.  
   **Exact fix:** Change `say` to write to stderr. Until that source defect is fixed, the harness must identify fresh provisioning as blocked; the operator must not patch it during a run.

4. **`codex/SPEC.md:52` — The cloud sequence never generates the promised master key.**  
   **Evidence:** `scripts/oci/deploy.sh:44` requires an existing file. Generation exists only in `scripts/gateway.sh:19–20`, which the cloud sequence never runs.  
   **Exact fix:** Add the same guarded, private-file generation to the cloud deploy script before its first read. Do not add a laptop gateway startup as a workaround.

5. **`codex/SPEC.md:23` and `codex/SPEC.md:135` — The VM bootstrap omits essential components.**  
   **Evidence:** `scripts/oci/control.sh:66–80` installs Docker, but does not install Podman or OpenShell or create `openshell-gateway.service`. `scripts/oci/control-deploy.sh:77–85` immediately requires OpenShell and Podman; line 110 starts only the control-room service.  
   **Exact fix:** Complete the cloud bootstrap with the supported OpenShell version, rootless Podman configuration, and enabled OpenShell gateway unit. Mark first-time deployment blocked until that exists.

6. **`codex/SPEC.md:48` — The stated cloud permissions are incomplete.**  
   **Evidence:** Beyond compartment and IAM creation, `scripts/oci/up.sh:66`, `up.sh:125`, `control.sh:83`, and `edge.sh:60` create networking, OKE, compute, and API Gateway resources. The region-list command at SPEC line 67 does not verify those permissions.  
   **Exact fix:** List permission to create and manage every resource in section 0, required read access, and sufficient limits/capacity for both A1 instances. Describe region-list success as an authentication check only.

7. **`codex/SPEC.md:62–65` — Tool prerequisites omit required programs and versions.**  
   **Evidence:** `scripts/oci/deploy.sh:57` requires `shasum`; the cloud scripts require `python3`; `web/package-lock.json:3416` requires Node `^20.19.0 || >=22.12.0`. The table checks neither Node compatibility nor these additional tools.  
   **Exact fix:** Add Python, compatible Node, npm, and `shasum` checks before dependency installation and web building.

8. **`codex/SPEC.md:68` — The SSH check can pass without usable SSH authentication.**  
   **Evidence:** It checks only the public key. `scripts/oci/control.sh:35` and `scripts/oci/control-deploy.sh:27` use the corresponding private key, and the prescribed execution cannot depend on interactive authentication.  
   **Exact fix:** Check both files and document that any encrypted private key must already be available through the operator’s SSH agent.

9. **`codex/PROMPT-ops.md:3–7` — The ops path omits checkout prerequisites needed by its authorized repairs.**  
   **Evidence:** `scripts/oci/control-deploy.sh:37` runs `npm run build`, but never installs web dependencies. Cloud scripts also need the Python environment described above.  
   **Exact fix:** Add an ops prerequisite section requiring the existing cloud deployment/state, configured tools and SSH, synchronized Python environment, and installed web dependencies before running preflight.

10. **`codex/SPEC.md:26` — `genai_region` is presented as configurable but ignored.**  
    **Evidence:** `deploy/k8s/litellmdemo.yaml:165` hard-codes the inference region. `scripts/oci/control-deploy.sh:60` also hard-codes it. No cloud script applies `genai_region`.  
    **Exact fix:** Render both settings from `deploy.json`, or explicitly require the supported fixed region and reject other configured values.

11. **`codex/SPEC.md:126–127` — `control.sh` does not reliably wait through the promised reboot.**  
    **Evidence:** `scripts/oci/control.sh:79–80` creates its readiness marker before rebooting. Lines 94–98 can observe that marker before the reboot begins.  
    **Exact fix:** Wait for a changed boot identifier and successful post-reboot readiness before printing `CONTROL OK`.

12. **`codex/SPEC.md:135` — `CONTROL DEPLOY OK` does not establish the promised readiness.**  
    **Evidence:** `scripts/oci/control-deploy.sh:111` exhausts its health loop without an explicit failure. At line 112, trailing `echo` commands mask failed `curl` commands; line 113 then prints success.  
    **Exact fix:** Fail after the health deadline, preserve request failures, and require the expected gateway identity and sandbox readiness before printing success.

13. **`codex/PROMPT-ops.md:12–15` — The URL examples use literal `URL`.**  
    **Evidence:** `scripts/e2e.py:28` uses the environment value directly; it does not expand placeholder names. SPEC line 145 also never provides an explicit shell assignment for its later `$URL` references.  
    **Exact fix:** Add `URL='https://<host>'`, then use `LITELLMDEMO_APP="$URL"` and `"$URL/api/sandbox/probe"` consistently.

14. **`codex/SPEC.md:161` — The browser command writes outside the repository.**  
    **Evidence:** The spec requires repository-root execution. `web/scripts/ui-e2e.mjs:8–10` defaults to `../out/ui-e2e`, resolved against the working directory. That is outside the workspace permitted by the README invocation.  
    **Exact fix:** Pass an explicit repository-local output directory: `node web/scripts/ui-e2e.mjs out/ui-e2e`.

15. **`codex/README.md:14–26` — The writable-directory flags omit SSH’s first-connection state.**  
    **Evidence:** `scripts/oci/control.sh:95` and `scripts/oci/control-deploy.sh:27` use `StrictHostKeyChecking=accept-new`, which may write `~/.ssh/known_hosts`. The supplied flags do not permit that directory.  
    **Exact fix:** Add `--add-dir ~/.ssh`, or require the operator to establish the relevant known-host entries before starting Codex.

16. **`codex/SPEC.md:168–170` — Port forwarding has unreliable readiness, cleanup, and result handling.**  
    **Evidence:** The commands sleep for a fixed five seconds, discard forward errors, target job `%1`, and finish with `kill` rather than the probe’s status. They also contradict SPEC line 88 and PROMPT line 16’s foreground-only instruction.  
    **Exact fix:** Explicitly exempt this helper from the foreground rule. Use one scoped shell block that captures `$!`, installs cleanup traps, verifies forwarding readiness, saves the probe status, and returns that status after cleanup.

17. **`codex/SPEC.md:203` — Redeploying does not replenish a valid key’s budget.**  
    **Evidence:** `scripts/oci/deploy.sh:94–100` tests only whether key-info returns HTTP 200. Lines 102–112 preserve that key and update models/rate limits, without resetting spend or budget.  
    **Exact fix:** Remove the automatic-reissue claim. Report spend and the reset date, and stop for an explicit operator decision about budget renewal or rotation.

18. **`codex/SPEC.md:203` — A genuinely replaced key is not propagated to an existing OpenShell provider.**  
    **Evidence:** `scripts/oci/control-deploy.sh:85` refreshes the provider only when it is missing. The ops skill acknowledges this at line 64. Running its suggested bare provider command also risks the laptop defaults in `scripts/openshell.sh:27–33`.  
    **Exact fix:** Refresh the provider during cloud deployment under the existing cloud gateway and key-file environment, rather than guarding refresh with “provider exists.”

19. **`codex/PROMPT-ops.md:5` — A failing preflight does not end with the public URL.**  
    **Evidence:** `scripts/oci/preflight.sh:69` prints the URL only on success. Lines 70–71 finish failures with repair instructions.  
    **Exact fix:** Say: “After preflight succeeds, take the URL from its success line. Do not derive URL from a failed preflight’s last line.”

20. **`codex/SPEC.md:36–38` and `codex/PROMPT-ops.md:11` — Passing checks do not prove a live sandbox execution.**  
    **Evidence:** `ui/server.py:99–131` can use the host agent or replay a recording. Replay defaults to enabled at line 59. `scripts/e2e.py:51–83` checks neither runtime nor replay, although the verification skill requires sandbox-only runs at lines 23–25.  
    **Exact fix:** Add explicit live-path verification using `runtime: "openshell"` and `replay: false`, and inspect raw events for sandbox-only runtime, no replay/failover, and current sandbox network activity. Do not claim that `E2E OK` alone proves this.

21. **`codex/PROMPT-ops.md:15–17` — The escape command does not reliably establish three policy refusals.**  
    **Evidence:** `curl -s` accepts HTTP errors. `ui/sandbox.py:118–120` can return an empty attempt list after subprocess failure. `scripts/openshell.sh:118–121` also labels ordinary connection failures as refusals.  
    **Exact fix:** Use `curl -fsS` with a deadline, require exactly three attempts, reject unexpected HTTP results, and require corresponding policy-denial evidence. Treat unrelated connectivity failures as inconclusive.

22. **`codex/PROMPT-ops.md:18–20` — The requested final budget and readiness report has no final measurement step.**  
    **Evidence:** Preflight measures key spend before step 3 at `scripts/oci/preflight.sh:44–49`. E2E output reports request costs, not the final key balance (`scripts/e2e.py:81–83`).  
    **Exact fix:** After the three requests and escape probe, read `/api/sandbox` and rerun cloud preflight. Report that final balance and end with the final preflight result.

23. **`codex/PROMPT.md:17–19` — The retry instruction conflicts with the documented treatment of known misses.**  
    **Evidence:** SPEC lines 183–184 require reporting known misses without fixing them; lines 204–206 describe expected nonzero checks. PROMPT nevertheless requires fixing and rerunning every failed step.  
    **Exact fix:** Exempt explicitly documented known misses from repair/retry. Record their actual failure status and continue only as the completion criteria permit.

24. **`codex/SPEC.md:69` — Skipping Chrome conflicts with mandatory completion and the unconditional browser command.**  
    **Evidence:** SPEC line 38 requires UI success, and line 161 runs the browser test unconditionally. `web/scripts/ui-e2e.mjs:14` hard-codes the macOS Chrome executable.  
    **Exact fix:** Gate the browser command on that prerequisite and classify a skipped browser test as incomplete verification. Document that the supplied browser runner requires macOS.

25. **`codex/SPEC.md:199` — The legacy-VM repair referral conflicts with the cloud-change rule.**  
    **Evidence:** The ops skill’s line 60 recommends direct kernel/systemd changes and rebooting. `AGENTS.md:20–23` and SPEC lines 180–182 require cloud changes through `scripts/oci/*.sh`. No referenced repair script implements that legacy repair.  
    **Exact fix:** Replace the referral with “Stop and report: this VM needs an operator-authorized repair through the cloud scripts.”

26. **`codex/PROMPT.md:3–4` — Blanket skill instructions expose contradictory operating rules.**  
    **Evidence:** The gateway skill labels OKE read-only for agents at line 43, despite this prompt authorizing deployment there. The ops skill instructs editing `app/agent.py` at lines 92–94, conflicting with `AGENTS.md:30–32` during check repair.  
    **Exact fix:** State that approved cloud provisioning uses the cloud scripts, and that build/ops checks must stop before any application, classifier, gateway, or script edit. Update the conflicting skill passages accordingly.

27. **`codex/SPEC.md:80` — The referenced classifier skill describes a different shipped route set.**  
    **Evidence:** `.agents/skills/litellm-route-classifier/SKILL.md:24` says training selected fast/balanced/reasoning. `classifier/model/meta.json:69–72` records SIMPLE/COMPLEX/REASONING.  
    **Exact fix:** Change the skill’s statement to fast/strong/reasoning for the shipped artifact, retaining the recorded 75% bar.

28. **`codex/SPEC.md:200` — The ten-minute `edge.sh` duration is understated.**  
    **Evidence:** `scripts/oci/edge.sh:65–71` allows ten minutes for the gateway, lines 105–111 another ten for deployment, and line 114 up to roughly ten more for health attempts. Request time adds overhead.  
    **Exact fix:** Document the separate phase deadlines and roughly thirty minutes of configured waits, plus API-call time.

29. **`codex/SPEC.md:154` — Recording runs more jobs than disclosed.**  
    **Evidence:** `scripts/record_runs.py:38–41` records five text examples, one image example, and all seventeen scenarios in `app/scenarios.py:39–117`: twenty-three jobs.  
    **Exact fix:** Replace the description with “Records six Ask examples and seventeen scenarios: twenty-three live jobs. Success ends with `23/23 recorded`; spend varies with calls and retries.”

30. **`codex/SPEC.md:94–98` — The cost approval assumes resource sizes that are configurable.**  
    **Evidence:** `scripts/oci/up.sh:159` uses configured node sizes; `scripts/oci/control.sh:82–85` uses separately configurable VM sizes. They also request 50 GB and 100 GB boot volumes (`up.sh:160`, `control.sh:85`).  
    **Exact fix:** Show both configured compute sizes, their combined totals, and both boot volumes in the approval plan. Make the allowance claim conditional on those totals and available allowance.

31. **`codex/SPEC.md:33` and `codex/SPEC.md:173` — The literal cloud-preflight end line is wrong.**  
    **Evidence:** `scripts/oci/preflight.sh:69` appends two spaces and the public URL.  
    **Exact fix:** Use `CLOUD PREFLIGHT OK (10/10)  https://<host>` as the full success-line template, or explicitly describe the existing text as a prefix.

32. **`codex/SPEC.md:207` — The cold-classifier diagnosis is outdated.**  
    **Evidence:** `classifier/serve.py:25–29` warms the classifier before startup completes; lines 51–55 expose readiness afterward. `ui/server.py:435–438` also warms its local classifier during startup.  
    **Exact fix:** Say that startup/readiness may be slow while weights load. Do not attribute a slow request after readiness to encoder loading without further evidence.

33. **`codex/README.md:40–41` — Paid maintenance work is presented without the skill’s spending gate.**  
    **Evidence:** The classifier skill requires asking before trial, relabelling, and robustness spending at lines 53–56. `AGENTS.md:26–28` restricts those jobs to tasks that request them.  
    **Exact fix:** State that evaluation starts locally, while model trials, relabelling, and robustness runs require explicit spending authorization before execution.

34. **`codex/README.md:37` — “Seven scripts” does not match the build sequence.**  
    **Evidence:** SPEC sections 4.1–4.5 invoke five provisioning shell scripts. Section 4.6 records runs; section 4.7 performs checks.  
    **Exact fix:** Replace it with “the preflight, the plan, five provisioning scripts, recorded runs, and four checks.”

35. **`codex/README.md:1` and `codex/SPEC.md:1` — The required personal-work disclaimer is absent.**  
    **Evidence:** `AGENTS.md:61–62` requires preserving the disclaimer that this is personal work using a fictional company’s data. Neither document supplies it.  
    **Exact fix:** Add: “This is personal work. Northwind Cloud and its data are fictional.” Require the operator report to preserve that statement.

DEFECTS: 35
