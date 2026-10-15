"""Codex through the gateway: does LiteLLM pick the right OCI model for each Codex request, and does Codex finish the job?

    LITELLM_GATEWAY=http://127.0.0.1:4400 GATEWAY_LOG=out/gateway.log uv run python scripts/codex_e2e.py [--runs 2]

Each case runs `codex exec` in a fresh temporary directory with LiteLLM as Codex's model provider
(Responses API, model `oci-auto-trained`), then checks from the outside:

  - the route and the models: the gateway's ROUTE lines written while the case ran (GATEWAY_LOG,
    the gateway's own log) must all be on the route's models, with no fallback;
  - the outcome: an answer that says what was asked, or code that builds and passes `go vet` and
    the race detector.

The key is LITELLM_API_KEY, or the gateway's master key next to its config (LITELLMDEMO_CONFIG), passed to Codex
through the environment, never on a command line. Ends with "CODEX E2E OK (n/n)". Paid: cents per run, most
of it the code case (Codex sends about 48k tokens of context per turn).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GATEWAY = os.environ.get("LITELLM_GATEWAY", "http://127.0.0.1:4400")
LOG = Path(os.environ.get("GATEWAY_LOG", "out/gateway.log"))
KEY = Path(os.environ.get("LITELLMDEMO_CONFIG", Path.home() / ".config/litellmdemo/config.json")).parent / "master_key"

RACE = """package main

import (
\t"fmt"
\t"sync"
)

func main() {
\tvar n int
\tvar wg sync.WaitGroup
\tfor i := 0; i < 1000; i++ {
\t\twg.Add(1)
\t\tgo func() { defer wg.Done(); n++ }()
\t}
\twg.Wait()
\tfmt.Println(n)
}
"""


def go_ok(work: Path) -> tuple[bool, str]:
    env = dict(os.environ, GOCACHE=str(work / ".gocache"), GOFLAGS="-mod=mod")
    for cmd in (["go", "vet", "main.go"], ["go", "run", "-race", "main.go"]):
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, env=env, timeout=180)
        if r.returncode != 0:
            return False, f"{' '.join(cmd)}: {(r.stderr or r.stdout).strip()[:160]}"
    out = r.stdout.strip()
    return out == "1000", f"prints {out!r}"


CASES = [
    {"id": "chat", "prompt": "In one sentence: what does HTTP status 429 mean? Do not run any command.",
     "models": {"openai.gpt-6-luna", "openai.gpt-5.4-nano"}, "sandbox": "read-only",
     "check": lambda work, answer: (bool(re.search(r"too many requests|rate", answer, re.I)), "names 429")},
    {"id": "code", "prompt": "Fix the data race in main.go so it always prints 1000. Keep the change minimal.",
     "models": {"openai.gpt-5.3-codex"}, "sandbox": "workspace-write", "files": {"main.go": RACE},
     "check": lambda work, answer: go_ok(work)},
    {"id": "spanish", "prompt": "Responde en una frase y sin ejecutar comandos: ¿qué es una condición de carrera?",
     # from a coding agent another language goes to the ladder, not Cohere (classifier/router_model.py)
     "models": {"openai.gpt-6-luna", "openai.gpt-5.4-nano", "openai.gpt-6-sol", "xai.grok-4.20-reasoning", "xai.grok-4.7"},
     "sandbox": "read-only",
     "check": lambda work, answer: (bool(re.search(r"\b(hilos|procesos|recurso|orden)\b", answer, re.I)), "answers in Spanish")},
]


def route_lines(start: int) -> list[str]:
    text = LOG.read_bytes()[start:].decode(errors="replace") if LOG.exists() else ""   # start is a byte offset
    return [ln[ln.index("ROUTE"):] for ln in text.splitlines() if "ROUTE" in ln and "asked=oci-auto-trained" in ln]


def run(case: dict) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix=f"codex-{case['id']}-") as d:
        work = Path(d)
        for name, body in (case.get("files") or {}).items():
            (work / name).write_text(body)
        start = LOG.stat().st_size if LOG.exists() else 0
        last = work / ".last-message"
        cmd = ["codex", "exec", "-C", str(work), "--skip-git-repo-check", "-s", case["sandbox"], "--color", "never",
               "-c", 'model_providers.litellm.name="LiteLLM on OCI"',
               "-c", f'model_providers.litellm.base_url="{GATEWAY}/v1"',
               "-c", 'model_providers.litellm.env_key="LITELLM_KEY"',
               "-c", 'model_providers.litellm.wire_api="responses"',
               "-c", "model_provider=litellm", "-m", "oci-auto-trained", "-o", str(last), case["prompt"]]
        started = time.time()
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900,
                           env=dict(os.environ, LITELLM_KEY=os.environ.get("LITELLM_API_KEY") or KEY.read_text().strip()))
        seconds = time.time() - started
        # the gateway writes a streamed call's line after the stream ends: wait until its log is quiet
        seen, quiet_since = -1, time.time()
        while time.time() - quiet_since < 4 and time.time() - started - seconds < 30:
            n = len(route_lines(start))
            if n != seen:
                seen, quiet_since = n, time.time()
            time.sleep(0.5)
        answer = last.read_text() if last.exists() else ""
        lines = route_lines(start)
        ok_lines = [ln for ln in lines if ln.startswith("ROUTE ")]
        models = {m.group(1) for ln in ok_lines if (m := re.search(r"model=(\S+)", ln))}
        fallbacks = sum(int(m.group(1)) for ln in ok_lines if (m := re.search(r"fallbacks=(\d+)", ln)))
        cost = sum(float(m.group(1)) for ln in ok_lines if (m := re.search(r" \$([0-9.]+)", ln)))
        problems = []
        if r.returncode != 0:
            problems.append(f"codex exit {r.returncode}")
        if not ok_lines:
            problems.append("no ROUTE line in the gateway log")
        if models - case["models"]:
            problems.append(f"answered by {sorted(models - case['models'])}")
        if fallbacks and not case.get("fallback_ok"):
            problems.append(f"{fallbacks} fallback(s)")
        good, what = case["check"](work, answer)
        if not good:
            problems.append(f"outcome: {what}")
        detail = (f"calls={len(ok_lines)} models={','.join(sorted(models)) or '-'} fallbacks={fallbacks} "
                  f"failed_attempts={len(lines) - len(ok_lines)} cost=${cost:.4f} {seconds:.0f}s {what}")
        if problems:
            tail = (answer or r.stderr or r.stdout).strip().replace("\n", " ")[-200:]
            detail += f"  <- {'; '.join(problems)} | {tail}"
        return not problems, detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--only", help="run the cases whose id contains this text")
    args = ap.parse_args()
    if not LOG.exists():
        print(f"ABORT: {LOG} not found: set GATEWAY_LOG to the gateway's log, which has its ROUTE lines", file=sys.stderr)
        return 2
    total = passed = 0
    for n in range(args.runs):
        for case in CASES:
            if args.only and args.only not in case["id"]:
                continue
            ok, detail = run(case)
            total += 1
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'}  run {n + 1}  {case['id']:8s} {detail}", flush=True)
    print(f"\n{'CODEX E2E OK' if passed == total else 'CODEX E2E FAILED'} ({passed}/{total})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
