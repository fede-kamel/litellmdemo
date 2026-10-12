"""Record a real run of every Ask example and every use case, for replay if the network fails on stage.

    uv run python scripts/record_runs.py      # the control room on 127.0.0.1:8780
    LITELLMDEMO_APP=https://<host> uv run python scripts/record_runs.py   # the public control room (records on its VM)

Each request goes through the live path (the OpenShell sandbox and LiteLLM);
the control room saves every run that answers in out/recordings/. If later
both live paths fail for the same request, it replays the recording, labelled
"REPLAY" on screen.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

APP = os.environ.get("LITELLMDEMO_APP", "http://127.0.0.1:8780")


def run(body: dict) -> bool:
    req = urllib.request.Request(f"{APP}/api/runs", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    rid = json.load(urllib.request.urlopen(req, timeout=30))["id"]
    answered = False
    for line in urllib.request.urlopen(f"{APP}/api/runs/{rid}/stream", timeout=600):
        text = line.decode().strip()
        if text.startswith("data:") and '"type": "answer"' in text:
            answered = True
    return answered


def main() -> int:
    cfg = json.load(urllib.request.urlopen(f"{APP}/api/ask/config", timeout=10))
    scenarios = json.load(urllib.request.urlopen(f"{APP}/api/scenarios", timeout=10))
    image = "data:image/png;base64," + __import__("base64").b64encode(
        urllib.request.urlopen(f"{APP}/api/sample-image", timeout=10).read()).decode()
    jobs = [("example", {"prompt": p, "bar": cfg["default_bar"]}) for p in cfg["examples"]]
    jobs.append(("example", {"prompt": "Read this invoice: what is the total due and when is it due?", "image": image,
                             "bar": cfg["default_bar"]}))
    jobs += [("use case", {"scenario": s["id"]}) for s in scenarios]
    ok = 0
    for kind, body in jobs:
        good = run(body)
        ok += good
        print(f"{'RECORDED' if good else 'FAILED  '}  {kind:8}  {(body.get('prompt') or body.get('scenario'))[:70]}", flush=True)
    print(f"\n{ok}/{len(jobs)} recorded")
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
