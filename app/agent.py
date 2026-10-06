"""The control room's agent: langchain-oci, with every model call routed by the gateway.

`create_oci_agent` builds a tool-using agent; its model is an OpenAI-compatible
client pointed at the LiteLLM gateway with a model-group name (by default
`oci-auto-trained`), so the agent never names a vendor model and holds no OCI
credential. Each model call's route comes back in the response headers; the
runner turns every call and tool step into an event for the web app.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_oci import create_oci_agent
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.tools import TOOLS  # noqa: E402
from classifier.gateway_client import GATEWAY, key  # noqa: E402
from classifier.router_model import shared  # noqa: E402

SYSTEM = """You are Northwind Cloud's assistant for support, engineering and finance teams. Northwind Cloud is a
fictional company. Use the tools for policies, accounts and arithmetic instead of guessing, and answer in the
language of the request. Be concise and complete."""

ROUTE_HEADERS = {
    "x-litellm-complexity-router-tier": "route", "x-litellm-complexity-router-cause": "cause",
    "x-litellm-model-group": "group", "x-litellm-model-name": "deployment",
    "x-litellm-attempted-fallbacks": "fallbacks", "x-litellm-attempted-retries": "retries",
    "x-litellm-response-cost": "cost", "x-litellm-response-duration-ms": "ms", "x-litellm-call-id": "call_id",
}


def route_of(headers: dict) -> dict:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out: dict[str, Any] = {name: h[k] for k, name in ROUTE_HEADERS.items() if k in h}
    for n in ("cost", "ms"):
        if n in out:
            out[n] = round(float(out[n]), 6 if n == "cost" else 0)
    for n in ("fallbacks", "retries"):
        out[n] = int(out.get(n) or 0)
    return out


class RouteRecorder(BaseCallbackHandler):
    """Turns each model call and tool step into an event."""

    def __init__(self, emit: Callable[[dict], None], router: str, gateway: str = GATEWAY):
        self.emit, self.router, self.gateway, self.calls, self.started = emit, router, gateway, 0, {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self.started[run_id] = time.time()
        flat = [{"role": getattr(m, "type", "user"), "content": m.content} for m in messages[0]]
        if self.router == "oci-auto-trained":
            d = shared().classify([m for m in flat if m["role"] in ("human", "user")] or flat)
            self.emit({"type": "classify", "call": self.calls + 1, **d.as_dict()})

    def on_llm_end(self, response, *, run_id, **kw):
        self.calls += 1
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        meta = getattr(msg, "response_metadata", {}) or {}
        tool_calls = [c["name"] for c in (getattr(msg, "tool_calls", None) or [])]
        usage = meta.get("token_usage") or {}
        self.emit({"type": "llm", "call": self.calls, "asked": self.router, "gateway": self.gateway,
                   **route_of(meta.get("headers")),
                   "seconds": round(time.time() - self.started.pop(run_id, time.time()), 2),
                   "tokens": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")},
                   "tool_calls": tool_calls, "text": (msg.content if isinstance(getattr(msg, "content", None), str) else "")[:2000]})

    def on_tool_start(self, serialized, input_str, **kw):
        self.emit({"type": "tool", "name": serialized.get("name"), "input": str(input_str)[:300]})

    def on_tool_end(self, output, **kw):
        self.emit({"type": "tool_result", "output": str(getattr(output, "content", output))[:600]})


def chat_model(router: str, tags: list[str] | None = None, gateway: str = GATEWAY) -> ChatOpenAI:
    extra = {"tags": tags} if tags else {}
    return ChatOpenAI(model=router, base_url=f"{gateway}/v1", api_key=key(), include_response_headers=True,
                      max_retries=0, timeout=300, extra_body=extra or None)


def run(messages: list[dict], emit: Callable[[dict], None], router: str = "oci-auto-trained",
        tags: list[str] | None = None, use_tools: bool = True, gateway: str = GATEWAY) -> dict:
    agent = create_oci_agent(model=chat_model(router, tags, gateway), tools=TOOLS if use_tools else [], system_prompt=SYSTEM,
                             name="northwind-assistant")
    recorder = RouteRecorder(emit, router, gateway)
    started = time.time()
    result = agent.invoke({"messages": messages}, config={"callbacks": [recorder], "recursion_limit": 20})
    final = result["messages"][-1]
    answer = final.content if isinstance(final.content, str) else str(final.content)
    emit({"type": "answer", "text": answer, "seconds": round(time.time() - started, 1), "calls": recorder.calls})
    return {"answer": answer, "calls": recorder.calls}


if __name__ == "__main__":
    import json

    prompt = " ".join(sys.argv[1:]) or "How do I reset my Northwind Cloud console password?"
    run([{"role": "user", "content": prompt}], lambda e: print(json.dumps(e, ensure_ascii=False)[:400], flush=True),
        router=os.environ.get("ROUTER", "oci-auto"))
