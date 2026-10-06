"""Run one request through the agent inside the OpenShell sandbox; print one JSON event per line.

    python -m app.sandbox_run <base64 of {"prompt", "router", "tags", "bar", "image"}>
    python -m app.sandbox_run @/sandbox/req/<file>      # the same, from an uploaded file (large requests)

The sandbox holds no model key and no OCI credential. LITELLM_API_KEY is an
OpenShell placeholder: the sandbox proxy swaps in the agent's LiteLLM virtual
key on the way to the gateway, the only host the policy lets it reach.
LITELLM_GATEWAY names that host. stdout carries only events.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time


def main() -> int:
    arg = sys.argv[1]
    if arg.startswith("@"):                       # a large request, uploaded as a file
        path = arg[1:]
        with open(path) as fh:
            arg = fh.read()
        os.remove(path)
    req = json.loads(base64.b64decode(arg))
    from app import agent

    def emit(event: dict) -> None:
        print(json.dumps({"t": round(time.time(), 3), **event}, ensure_ascii=False), flush=True)

    content = req["prompt"]
    if req.get("image"):
        content = [{"type": "text", "text": req["prompt"]}, {"type": "image_url", "image_url": {"url": req["image"]}}]
    router = req.get("router") or "oci-auto-trained"
    try:
        agent.run([{"role": "user", "content": content}], emit, router=router, tags=req.get("tags"),
                  use_tools=router not in ("oci-flaky", "oci-chat"), gateway=agent.GATEWAY, bar=req.get("bar"))
    except Exception as exc:  # noqa: BLE001 - reported to the control room
        emit({"type": "error", "message": f"{type(exc).__name__}: {str(exc)[:400]}"})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
