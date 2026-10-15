# Codex review 2 of the cloud harness, 2026-10-15 (read-only sandbox, gpt-6.1-sol)

After the 35 findings of review 1 were fixed, a fresh Codex session reviewed the harness and the changed
scripts again. Disposition, same day:

- Fixed: 1 (openshell status read the heredoc), 5 (repairs run through `uv run`), 8 (node wait could fall
  through to UP OK), 9 (address probe failure skipped its diagnostic), 10 (subnet helper could return an
  empty ID), 11 (port-forward readiness).
- Fixed the same day, after the write-up's first draft: 2 and 6 (control-deploy.sh keeps a stamp of the agent
  key, the gateway's address and sandbox/; when it changes, the provider and the sandbox are recreated),
  3 (up.sh, control.sh and edge.sh adopt a demo resource an interrupted run already created, by name),
  4 (cloud-init writes the ready marker only when its steps took; a rerun of control.sh reinstalls the
  packages), 7 (control-deploy.sh fails unless the control room reports the OKE gateway, a ready sandbox and
  the agent key), 12 (record_runs.py asks for no replay and counts only live sandbox runs), 13 (the SSH key
  path is quoted for rsync).
- Not yet run: a first build in an empty tenancy with these scripts.

The review as Codex wrote it:

1. **[P1] `scripts/oci/control-deploy.sh:77` — OpenShell can consume the remaining setup script.**  
   `openshell status` inherits the heredoc supplying the remote `bash -s`. It can consume the subsequent image-build and cluster-check commands.  
   **Evidence:** `scripts/oci/control-deploy.sh:63`, `:77–79`; `.agents/skills/litellm-demo-ops/SKILL.md:71` documents OpenShell’s stdin behavior.  
   **Exact fix:** Redirect `openshell status` from `/dev/null`, capture its complete output, and match the captured string instead of piping it into `grep -q`.

2. **[P1] `scripts/oci/control-deploy.sh:85` — Replacing the agent key leaves OpenShell using the old credential.**  
   After a fresh database, `deploy.sh` issues a replacement key. Deployment copies that file to the VM but skips provider refresh whenever the provider exists. The documented recovery therefore leaves sandbox calls unauthorized. A changed node address likewise leaves the existing provider profile pointing at the previous gateway.  
   **Evidence:** `scripts/oci/deploy.sh:115–120`; `scripts/oci/control-deploy.sh:59`, `:83–86`; `scripts/openshell.sh:39–53`.  
   **Exact fix:** Reconcile the provider’s credential and rendered endpoint when either changes, then ensure the sandbox has adopted the updated provider configuration.

3. **[P1] `scripts/oci/up.sh:56` — Interrupted creation is still not safely resumable.**  
   Several resources are recorded only after creation and its waiter finish. If creation succeeds but the waiter fails or execution stops, rerunning can hit an existing-name conflict or create another resource. Cluster and API-gateway adoption do not cover these other resources.  
   **Evidence:** `scripts/oci/up.sh:53–59`, `:64–108`; `scripts/oci/control.sh:56–88`; `scripts/oci/edge.sh:32–47`. This contradicts `codex/SPEC.md:96–97`.  
   **Exact fix:** Before each create, adopt a uniquely matching demo-owned resource. Record its identifier immediately after creation, then perform readiness polling separately. Apply this to the compartment, networking, IAM resources and VM.

4. **[P2] `scripts/oci/control.sh:65` — Failed first-boot provisioning can leave a permanent “ready” marker.**  
   The cloud-init command list has no fail-fast guard. A package installation, firewall command or delegation setup can fail while subsequent commands still create the marker and reboot. Rerunning `control.sh` skips that provisioning because the VM already exists; its new readiness check verifies only the marker and Landlock.  
   **Evidence:** `scripts/oci/control.sh:65–80`, `:96–101`; `scripts/oci/control-deploy.sh:40` requires remote `rsync`.  
   **Exact fix:** Run provisioning with explicit failure propagation, create the marker only after successful validation, and reconcile failed prerequisites on an existing VM during a rerun.

5. **[P2] [codex/PROMPT-ops.md:13] — Repair commands omit the required project environment.**  
   The prompt tells the agent to execute the printed fixes directly. `uv sync` installs dependencies but does not activate them for later bare `python3` commands. A permitted `control-deploy.sh` repair can therefore fail importing PyYAML.  
   **Evidence:** `codex/PROMPT-ops.md:6`, `:12–16`; `scripts/oci/control-deploy.sh:48–49`; `codex/SPEC.md:94–96` explicitly requires `uv run` for this reason.  
   **Exact fix:** Require every allowed repair to run as `uv run scripts/oci/<script>.sh </dev/null`.

6. **[P2] `scripts/oci/control-deploy.sh:78` — Rebuilding the sandbox image does not update an existing sandbox.**  
   Deployment rebuilds the image, then calls `up`, which immediately returns when a sandbox exists. `sync` uploads selected Python files only. Changes to sandbox dependencies, its Dockerfile or policy consequently remain unapplied after the advertised deployment rerun.  
   **Evidence:** `scripts/oci/control-deploy.sh:78`, `:86`; `scripts/openshell.sh:56–61`, `:77–84`; `.agents/skills/litellm-demo-ops/SKILL.md:27–29`.  
   **Exact fix:** Compare the deployed image digest and policy hash with the desired versions; recreate and validate the sandbox when either changes.

7. **[P2] `scripts/oci/control-deploy.sh:114` — Deployment still reports success after failed final API checks.**  
   The remote command separates both `curl` calls with semicolons and ends with `echo`, so its exit status is successful even when either request fails. HTTP success with `"ready": false` also passes. The added health check establishes only that FastAPI answers.  
   **Evidence:** `scripts/oci/control-deploy.sh:112–115`; `ui/server.py:441–443`, `:468–477`, `:489–496`.  
   **Exact fix:** Propagate both request failures and validate the returned JSON: primary OKE gateway, sandbox ready, and agent-key information present. Print `CONTROL DEPLOY OK` only afterward.

8. **[P2] `scripts/oci/up.sh:169` — Node polling exhaustion can fall through to `UP OK`.**  
   Unlike the cluster polling loop, the node loop has no assertion after its final iteration. A node still provisioning after thirty minutes therefore falls through. Listing nodes does not establish that the required node exists and is Ready.  
   **Evidence:** `scripts/oci/up.sh:134–141` versus `:169–176`, followed by `:224–225`.  
   **Exact fix:** Abort unless `NODE_NOW` is `ACTIVE` after polling, then require the expected Kubernetes node to exist and reach Ready before printing `UP OK`.

9. **[P2] `scripts/oci/up.sh:47` — Address-probe failures bypass the documented diagnostic.**  
   With `set -euo pipefail`, a failed or timed-out `curl` makes the assignment fail and exits before the guard that prints `ABORT: cannot determine…`. The harness’s recovery table names an error that this common failure path never emits.  
   **Evidence:** `scripts/oci/up.sh:13`, `:46–49`; `codex/SPEC.md:222`.  
   **Exact fix:** Explicitly catch failure of the detection pipeline, clear the detected address, and route both transport failure and empty output through the existing diagnostic.

10. **[P2] `scripts/oci/up.sh:105` — The subnet helper can swallow a failed create.**  
    `subnet` runs inside command substitution. Bash normally clears `errexit` there, so a failed OCI assignment can be followed by a successful `put` and `echo`. The caller then receives success with an empty subnet identifier and continues.  
    **Evidence:** `scripts/oci/up.sh:101–113`; only `set -euo pipefail` is enabled at `:13`.  
    **Exact fix:** Add explicit `|| return 1` guards to creation and state persistence, and reject an empty or null identifier before storing or returning it.

11. **[P2] [codex/SPEC.md:191] — The route check can probe an unrelated listener.**  
    If port 4100 is occupied, the new port-forward exits. The readiness loop can nevertheless succeed against the existing listener, after which the probe’s result is presented as evidence about this cluster. Exhausting the readiness loop also does not abort.  
    **Evidence:** `codex/SPEC.md:191–194`; `scripts/probe_routes.py:22` uses whichever endpoint it receives.  
    **Exact fix:** Require the spawned port-forward to remain alive and establish its listener; abort on its exit or readiness timeout before running any paid probe.

12. **[P2] [codex/SPEC.md:169] — `23/23 recorded` does not prove 23 live sandbox recordings.**  
    The recorder counts any answer event. Requests permit replay by default and can fall back to the host. A rerun during an outage can therefore print the stated checkpoint from existing replays, without producing new live sandbox recordings.  
    **Evidence:** `scripts/record_runs.py:22–30`, `:44–47`; `ui/server.py:59`, `:110–131`, `:155–158`, `:175–180`.  
    **Exact fix:** Disable replay in recording requests and count success only after checking sandbox-only runtime, network evidence and a non-replayed answer. Until then, remove the claim that this checkpoint proves live sandbox recordings.

13. **[P2] `scripts/oci/control-deploy.sh:40` — The supported SSH-key override breaks when its path contains spaces.**  
    Quoting the outer `-e` argument does not preserve the key path when rsync parses that argument into the SSH command. Other SSH invocations correctly pass the path as one argument, so provisioning can succeed and deployment then fail.  
    **Evidence:** `codex/SPEC.md:54`; `scripts/oci/control-deploy.sh:24`, `:27`, `:40`.  
    **Exact fix:** Pass rsync an SSH wrapper that reads the key path from an exported variable and executes `ssh -i "$key_path" … "$@"`, preserving argument boundaries.

The first review’s 35-item list was not supplied or found in the reviewed files, so I cannot reliably identify its still-open finding numbers.

DEFECTS: 13
