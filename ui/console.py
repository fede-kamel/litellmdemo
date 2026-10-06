"""The control room's console: what OpenShell, LiteLLM and the classifier are doing, live.

Four followers, each restarted when its stream ends (a pod restart, a sandbox
recreated):

  openshell   openshell logs <sandbox> --tail     every connection the sandbox opens or is refused, policy reloads
  litellm     kubectl logs -f litellm-gateway     one ROUTE line per request (gateway/route_headers.py ConsoleLog)
  classifier  kubectl logs -f route-classifier    one CLASSIFY line per decision (classifier/serve.py)
  laptop      tail -F out/gateway.log             the laptop gateway, used when the cluster is unreachable

Lines go into a ring buffer and to every subscriber (GET /api/console, SSE).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = os.environ.get("LITELLMDEMO_SANDBOX", "litellmdemo-agent")
# Which cluster's pods to follow: the local Rancher Desktop cluster by default (the
# conference setup), or OKE with LITELLMDEMO_CLUSTER=oke.
KUBECTL = (["kubectl", "--kubeconfig", str(Path.home() / ".config/litellmdemo/kubeconfig")]
           if os.environ.get("LITELLMDEMO_CLUSTER", "local") == "oke" else ["kubectl", "--context", "rancher-desktop"])
BUFFER: deque = deque(maxlen=600)
SUBSCRIBERS: set[asyncio.Queue] = set()
_started = False

_OCSF = re.compile(r"^\[[\d.]+\] \[\w+\] \[(?P<level>[A-Z ]+)\] \[(?P<who>[^\]]+)\] (?P<msg>.*)$")


def _openshell(line: str) -> dict | None:
    m = _OCSF.match(line.strip())
    if not m:
        return None
    msg, level = m["msg"], m["level"].strip()
    if ":17670" in msg or "NET:LISTEN" in msg or "Fetching sandbox policy" in msg:
        return None                                   # the supervisor's own control channel
    if m["who"] != "ocsf" and level not in ("WARN", "ERROR"):
        return None
    tone = "deny" if "DENIED" in msg or "REFUSE" in msg else "allow" if "ALLOWED" in msg or "NET:OPEN" in msg else "info"
    return {"text": re.sub(r"\s+", " ", msg)[:260], "tone": tone}


def _litellm(line: str) -> dict | None:
    s = line.strip()
    if s.startswith("ROUTE-FAIL"):
        return {"text": s[:300], "tone": "deny"}
    if s.startswith("ROUTE "):
        return {"text": s[6:300], "tone": "route"}
    if re.search(r"\b(ERROR|Exception|Traceback)\b", s) and "prisma:warn" not in s:
        return {"text": s[:260], "tone": "deny"}
    return None


def _classifier(line: str) -> dict | None:
    s = line.strip()
    return {"text": s[9:260], "tone": "route"} if s.startswith("CLASSIFY ") else None


FOLLOWERS = {
    "openshell": (["openshell", "logs", SANDBOX, "--tail", "-n", "0", "--source", "all"], _openshell),
    "litellm": ([*KUBECTL, "logs", "-f", "-n", "litellmdemo", "deploy/litellm-gateway", "-c", "gateway", "--since=5s"], _litellm),
    "classifier": ([*KUBECTL, "logs", "-f", "-n", "litellmdemo", "deploy/route-classifier", "-c", "classifier", "--since=5s"],
                   _classifier),
    "laptop": (["tail", "-n", "0", "-F", str(ROOT / "out" / "gateway.log")], _litellm),
}


def publish(source: str, item: dict) -> None:
    line = {"t": round(time.time(), 3), "source": source, **item}
    BUFFER.append(line)
    for q in list(SUBSCRIBERS):
        if q.qsize() < 500:
            q.put_nowait(line)


async def _follow(source: str, argv: list[str], parse) -> None:
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            assert proc.stdout is not None
            async for raw in proc.stdout:
                item = parse(raw.decode(errors="replace"))
                if item:
                    publish(source, item)
            await proc.wait()
        except (OSError, asyncio.CancelledError):
            pass
        await asyncio.sleep(3)      # the stream ended (pod restarted, sandbox recreated): follow again


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    for source, (argv, parse) in FOLLOWERS.items():
        asyncio.get_running_loop().create_task(_follow(source, argv, parse))
