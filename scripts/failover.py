"""Prove the control room survives its gateway failing: a dead primary, the laptop gateway as fallback.

    uv run python scripts/failover.py        # local gateway on 127.0.0.1:4000

Starts a second copy of the web app on 127.0.0.1:8781 whose primary gateway is
a port nothing listens on, sends an Ask request and a full agent run, and
checks that both were answered, by the fallback gateway, with a route. Ends
with "FAILOVER OK".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "http://127.0.0.1:8781"
DEAD, FALLBACK = "http://127.0.0.1:4999", os.environ.get("LITELLM_GATEWAY_FALLBACK", "http://127.0.0.1:4000")


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(APP + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=240))


def main() -> int:
    env = {**os.environ, "LITELLM_GATEWAY": DEAD, "LITELLM_GATEWAY_FALLBACK": FALLBACK}
    server = subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "ui.server:app", "--host", "127.0.0.1", "--port", "8781"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(APP + "/api/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        ask = post("/api/ask", {"prompt": "What is 18 percent of 4,217.50?", "max_tokens": 100})
        results.append(("ask answered by the fallback gateway", ask["ok"] and ask["gateway"] == FALLBACK and bool(ask["route"].get("route")),
                        f"via {ask['gateway']}, route {ask['route'].get('route')}"))
        rid = post("/api/runs", {"scenario": "code-explain"})["id"]
        events = []
        for line in urllib.request.urlopen(f"{APP}/api/runs/{rid}/stream", timeout=240):
            text = line.decode().strip()
            if text.startswith("data:") and len(text) > 8:
                events.append(json.loads(text[5:]))
        llm = [e for e in events if e["type"] == "llm"]
        answered = any(e["type"] == "answer" for e in events)
        results.append(("agent run answered by the fallback gateway", answered and bool(llm) and all(e.get("gateway") == FALLBACK for e in llm),
                        f"{len(llm)} model call(s) via {llm[0].get('gateway') if llm else '-'}"))
    finally:
        server.terminate()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{'FAILOVER OK' if passed == len(results) else 'FAILOVER FAILED'} ({passed}/{len(results)})")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
