"""The control room's bridge to the OpenShell sandbox where the agent runs.

- run(request, emit): one request through scripts/openshell.sh ask; every JSON
  line the agent prints becomes an event.
- network(since): the sandbox's own network decisions (OpenShell OCSF log)
  after a moment: which connections it allowed and which it refused.
- probe(): the agent tries OCI, a model vendor and the gateway's admin API
  directly; the policy must refuse all three.
- agent_key(): what LiteLLM says about the agent's virtual key: alias, allowed
  models, budget, spend, rate limit. Read with the master key, server side.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "openshell.sh"
NAME = os.environ.get("LITELLMDEMO_SANDBOX", "litellmdemo-agent")
CONF = Path.home() / ".config" / "litellmdemo"
# The gateway the sandbox's agent uses, as the sandbox and as this machine see it,
# and the virtual key it holds: the local cluster by default, OKE when overridden.
SANDBOX_GATEWAY = os.environ.get("LITELLMDEMO_SANDBOX_GATEWAY", "http://192.168.5.15:30400")
HOST_VIEW = os.environ.get("LITELLMDEMO_SANDBOX_GATEWAY_FROM_HOST", "http://127.0.0.1:30400")
AGENT_KEY_FILE = Path(os.environ.get("LITELLMDEMO_AGENT_KEY_FILE", Path.home() / ".config/litellmdemo/agent_key-local"))
_status: dict = {"at": 0.0, "ready": False}


def available() -> bool:
    """Is the sandbox Ready? Cached for ten seconds."""
    if time.monotonic() - _status["at"] < 10:
        return _status["ready"]
    try:
        out = subprocess.run(["openshell", "sandbox", "get", NAME], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=10).stdout
        ready = "Ready" in out
    except (OSError, subprocess.TimeoutExpired):
        ready = False
    _status.update(at=time.monotonic(), ready=ready)
    return ready


def run(request: dict, emit: Callable[[dict], None], timeout: int = 600) -> bool:
    """Run one request in the sandbox. True when the agent answered."""
    # The request goes through a private file, not the command line: Linux caps one
    # argument at 128 KiB, and a long document (or an image) is more. The script removes it.
    fd, path = tempfile.mkstemp(prefix="litellmdemo-req-", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(request, fh)
    proc = subprocess.Popen([str(SCRIPT), "ask", f"@{path}"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    answered = False
    started = time.time()
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        event.pop("t", None)
        answered |= event.get("type") == "answer"
        if event.get("type") == "error":      # the server decides: fail over, or report it
            event = {**event, "type": "sandbox_error"}
        emit({**event, "runtime": "openshell"})
        if time.time() - started > timeout:
            proc.kill()
            break
    proc.wait(timeout=30)
    if os.path.exists(path):      # the script removes it; make sure
        os.remove(path)
    if not answered and proc.stderr is not None:
        tail = proc.stderr.read()[-300:]
        if tail.strip():
            emit({"type": "sandbox_error", "message": f"sandbox: {tail.strip()}", "runtime": "openshell"})
    return answered


_NET = re.compile(r"^\[(?P<t>[\d.]+)\].*\[ocsf\] (?P<kind>NET:\w+|HTTP:\w+) \[(?P<level>\w+)\] (?P<rest>.*)$")


def network(since: float) -> list[dict]:
    """The sandbox's network decisions after `since` (epoch seconds), newest last."""
    try:
        out = subprocess.run(["openshell", "logs", NAME, "-n", "400", "--source", "sandbox"],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    events = []
    for line in out.splitlines():
        m = _NET.match(line.strip())
        if not m or float(m["t"]) < since - 1:
            continue
        rest = m["rest"]
        if m["kind"] == "NET:LISTEN" or ":17670" in rest:   # the supervisor's own control channel
            continue
        verdict = "DENIED" if "DENIED" in rest else "ALLOWED" if ("ALLOWED" in rest or m["kind"] == "NET:OPEN") else ""
        reason = re.search(r"\[reason:([^\]]+)\]", rest)
        http = re.search(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD) (\S+)", rest)
        dest = re.search(r"-> ([^\s\[]+)", rest) or re.search(r"\] ([\w.\-]+:\d+)", rest) or re.search(r"([\w.\-]+:\d+)", rest)
        target = f"{http.group(1)} {http.group(2)}" if http else (dest.group(1) if dest else rest[:80])
        events.append({"t": float(m["t"]), "kind": m["kind"], "verdict": verdict, "destination": target,
                       "reason": reason.group(1) if reason else None, "line": rest[:200]})
    return events[-40:]


def probe() -> list[dict]:
    out = subprocess.run([str(SCRIPT), "probe"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip().startswith("{")]


def agent_key() -> dict | None:
    """LiteLLM's record of the agent's virtual key (never the key itself)."""
    keyfile, master = AGENT_KEY_FILE, CONF / "master_key"
    if not keyfile.exists() or not master.exists():
        return None
    try:
        r = httpx.get(f"{HOST_VIEW}/key/info", params={"key": keyfile.read_text().strip()},
                      headers={"Authorization": f"Bearer {master.read_text().strip()}"}, timeout=10)
        info = r.json().get("info", {})
    except (httpx.HTTPError, ValueError):
        return None
    return {k: info.get(k) for k in ("key_alias", "models", "max_budget", "spend", "rpm_limit", "budget_duration",
                                     "budget_reset_at")} | {"key_name": info.get("key_name")}
