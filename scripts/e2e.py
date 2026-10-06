"""End-to-end: every use case through the web app, the agent, the gateway and OCI.

    uv run uvicorn ui.server:app --port 8780 &        # web app (gateway on 4000)
    uv run python scripts/e2e.py                      # ends with E2E OK (n/n)
    uv run python scripts/e2e.py --evidence evidence  # also write evidence/e2e.jsonl

For each scenario in app/scenarios.py the langchain-oci agent runs once,
asking the gateway for `oci-auto-trained` (or the scenario's own group).
Checks: the first model call took the route the scenario expects, the
premium request took the premium lane, the failing deployment fell back,
and the agent produced an answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8780"


def run(client: httpx.Client, scenario: str) -> list[dict]:
    rid = client.post(f"{BASE}/api/runs", json={"scenario": scenario}).json()["id"]
    events: list[dict] = []
    with client.stream("GET", f"{BASE}/api/runs/{rid}/stream", timeout=600) as r:
        for line in r.iter_lines():
            if line.startswith("event: end"):
                break
            if line.startswith("data: ") and line != "data: {}":
                events.append(json.loads(line[6:]))
    return events


def check(s: dict, events: list[dict]) -> tuple[bool, str]:
    calls = [e for e in events if e["type"] == "llm"]
    answer = next((e for e in events if e["type"] == "answer"), None)
    error = next((e for e in events if e["type"] == "error"), None)
    if error or not calls or not answer or not answer["text"].strip():
        return False, f"no answer: {error and error['message']}"
    first = calls[0]
    expect = s["expect"]
    if expect == "premium lane":
        ok = "gpt-5.2" in (first.get("deployment") or "")
    elif expect == "fallback":
        ok = first.get("fallbacks", 0) >= 1 and first.get("group") == "oci-balanced"
    else:
        ok = first.get("route") in s.get("accept", [expect])
    spend = sum(c.get("cost") or 0 for c in calls)
    return ok, (f"route={first.get('route') or first.get('group')} deployment={first.get('deployment')} "
                f"calls={len(calls)} fallbacks={sum(c.get('fallbacks', 0) for c in calls)} spend=${spend:.5f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", help="write e2e.jsonl to this directory")
    ap.add_argument("--only", help="run scenarios whose id contains this text")
    args = ap.parse_args()
    lines, ok_count = [], 0
    with httpx.Client(timeout=120) as client:
        scenarios = [s for s in client.get(f"{BASE}/api/scenarios").json() if not args.only or args.only in s["id"]]
        for s in scenarios:
            events = run(client, s["id"])
            ok, detail = check(s, events)
            ok_count += ok
            print(f"{'PASS' if ok else 'FAIL'}  {s['id']:20s} expect {s['expect']:13s} {detail}", flush=True)
            lines.append({"scenario": s["id"], "use_case": s["use_case"], "expect": s["expect"], "passed": ok,
                          "detail": detail, "calls": [{k: e.get(k) for k in ("call", "route", "cause", "group", "deployment",
                                                                              "fallbacks", "retries", "cost", "seconds", "tool_calls")}
                                                     for e in events if e["type"] == "llm"],
                          "classifier": [{k: e.get(k) for k in ("call", "route", "criterion", "probabilities", "milliseconds")}
                                         for e in events if e["type"] == "classify"]})
    if args.evidence:
        out = Path(args.evidence)
        out.mkdir(parents=True, exist_ok=True)
        (out / "e2e.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")
    print(f"\n{'E2E OK' if ok_count == len(scenarios) else 'E2E FAILED'} ({ok_count}/{len(scenarios)})")
    return 0 if ok_count == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
