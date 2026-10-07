"""The control room's agent: langchain-oci, with every model call routed by the gateway.

`create_oci_agent` builds a tool-using agent; its model is an OpenAI-compatible
client pointed at the LiteLLM gateway with a model-group name (by default
`oci-auto-trained`), so the agent never names a vendor model and holds no OCI
credential. Each model call's route comes back in the response headers; the
runner turns every call and tool step into an event for the web app.
"""

from __future__ import annotations

import json
import os
import re
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
from langgraph.errors import GraphRecursionError  # noqa: E402

from classifier.gateway_client import GATEWAY, key  # noqa: E402

SYSTEM = """You are Northwind Cloud's assistant for support, engineering and finance teams. Northwind Cloud is a
fictional company. Use the tools for policies, accounts and arithmetic instead of guessing, and answer in the
language of the request. Batch arithmetic: put every calculation you need into one calculate call, separated by
';'. Use at most six tool calls. Be concise and complete."""

ROUTE_HEADERS = {
    "x-litellm-complexity-router-tier": "route", "x-litellm-complexity-router-cause": "cause",
    "x-litellm-model-group": "group", "x-litellm-model-name": "deployment",
    "x-litellm-attempted-fallbacks": "fallbacks", "x-litellm-attempted-retries": "retries",
    "x-litellm-response-cost": "cost", "x-litellm-response-duration-ms": "ms", "x-litellm-call-id": "call_id",
    "x-litellm-key-spend": "key_spend",
}
DECISION_HEADER = "x-litellm-route-decision"


def decision_of(headers: dict) -> dict | None:
    """The classifier's decision as the gateway reported it, in the shape of a classify event."""
    raw = {k.lower(): v for k, v in (headers or {}).items()}.get(DECISION_HEADER)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    details = {k: d[k] for k in ("bar", "order", "cost", "features", "precedent", "code") if k in d}
    return {"route": d.get("route"), "criterion": d.get("criterion"), "probabilities": d.get("p") or {},
            "milliseconds": d.get("ms"), "details": details, "source": "litellm"}


def route_of(headers: dict) -> dict:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out: dict[str, Any] = {name: h[k] for k, name in ROUTE_HEADERS.items() if k in h}
    for n in ("cost", "ms", "key_spend"):
        if n in out:
            out[n] = round(float(out[n]), 0 if n == "ms" else 6)
    for n in ("fallbacks", "retries"):
        out[n] = int(out.get(n) or 0)
    return out


class RouteRecorder(BaseCallbackHandler):
    """Turns each model call and tool step into an event."""

    def __init__(self, emit: Callable[[dict], None], router: str, gateway: str = GATEWAY):
        self.emit, self.router, self.gateway, self.calls, self.started = emit, router, gateway, 0, {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self.started[run_id] = time.time()

    def on_llm_end(self, response, *, run_id, **kw):
        self.calls += 1
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        meta = getattr(msg, "response_metadata", {}) or {}
        tool_calls = [c["name"] for c in (getattr(msg, "tool_calls", None) or [])]
        usage = meta.get("token_usage") or {}
        decision = decision_of(meta.get("headers"))
        if decision:
            self.emit({"type": "classify", "call": self.calls, **decision})
        self.emit({"type": "llm", "call": self.calls, "asked": self.router, "gateway": self.gateway,
                   **route_of(meta.get("headers")),
                   "seconds": round(time.time() - self.started.pop(run_id, time.time()), 2),
                   "tokens": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")},
                   "tool_calls": tool_calls, "text": (msg.content if isinstance(getattr(msg, "content", None), str) else "")[:2000]})

    def on_tool_start(self, serialized, input_str, **kw):
        self.emit({"type": "tool", "name": serialized.get("name"), "input": str(input_str)[:300]})

    def on_tool_end(self, output, **kw):
        self.emit({"type": "tool_result", "output": str(getattr(output, "content", output))[:600]})


def chat_model(router: str, tags: list[str] | None = None, gateway: str = GATEWAY,
               bar: float | None = None) -> ChatOpenAI:
    extra: dict = {"tags": tags} if tags else {}
    if bar is not None:
        extra["metadata"] = {"route_quality_bar": bar}
    return ChatOpenAI(model=router, base_url=f"{gateway}/v1", api_key=key(), include_response_headers=True,
                      max_retries=0, timeout=300, extra_body=extra or None)


FINAL_NUDGE = "Please give your final answer to my request in full."


def _final_from_transcript(history: list, model) -> str:
    """One tool-free call: the request, the tool results so far, and a request for the final answer."""
    request = next((_text(m) for m in history if getattr(m, "type", None) == "human" or (isinstance(m, dict) and m.get("role") == "user")), "")
    results = [f"- {getattr(m, 'name', 'tool')}: {_text(m)[:600]}" for m in history if getattr(m, "type", None) == "tool"]
    prompt = (f"{request}\n\nResults already computed with tools:\n" + "\n".join(results[-20:]) +
              "\n\nUsing these results, give your final answer in full now.")
    return _text(model.invoke([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))


_TOOL_TEXT = re.compile(r"\[?\s*(calculate|lookup_policy|get_account)\s*\(", re.S)


def _tool_call_as_text(answer: str) -> bool:
    """A short answer that names one of our tools as a call: the model wrote it instead of making it."""
    return len(answer) < 400 and bool(_TOOL_TEXT.search(answer))


def _text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, list):   # content blocks
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content if isinstance(content, str) else str(content)


def run(messages: list[dict], emit: Callable[[dict], None], router: str = "oci-auto-trained",
        tags: list[str] | None = None, use_tools: bool = True, gateway: str = GATEWAY,
        bar: float | None = None, context: str = "") -> dict:
    # `context` (a plan step's earlier results) goes into the system prompt: the router
    # reads the user turns only, so each step is routed on its own instruction.
    system = SYSTEM + (f"\n\n{context}" if context else "")
    agent = create_oci_agent(model=chat_model(router, tags, gateway, bar), tools=TOOLS if use_tools else [], system_prompt=system,
                             name="northwind-assistant")
    recorder = RouteRecorder(emit, router, gateway)
    started = time.time()
    config = {"callbacks": [recorder], "recursion_limit": 20}
    state: dict = {"messages": messages}
    capped = False
    try:
        for state in agent.stream({"messages": messages}, config=config, stream_mode="values"):
            pass
        result = state
        answer = _text(result["messages"][-1])
    except GraphRecursionError:
        # The agent kept calling tools. Answer from what it gathered, without tools,
        # rather than end the run with an error.
        capped = True
        result = state
        answer = _final_from_transcript(state["messages"], chat_model(router, tags, gateway, bar))
    retried = False
    if (not answer.strip() or _tool_call_as_text(answer)) and not capped:
        # Some models return an empty final message (Gemini Flash-Lite after a tool
        # result) or write a tool call as text instead of making it (Llama 4 Scout,
        # sometimes); ask once more rather than end the run with no answer.
        retried = True
        result = agent.invoke({"messages": [*result["messages"], {"role": "user", "content": FINAL_NUDGE}]}, config=config)
        answer = _text(result["messages"][-1])
    emit({"type": "answer", "text": answer, "seconds": round(time.time() - started, 1), "calls": recorder.calls,
          "retried_empty": retried, "tool_limit_reached": capped})
    return {"answer": answer, "calls": recorder.calls}


PLANNER = """You plan work for Northwind Cloud's assistant. Split the request into the separate tasks it contains,
in the order they must be done: two to five steps, each one job (look something up, calculate, write, code).
Write each step as a complete instruction that can be done on its own, with the facts it needs (ids, numbers),
in the language its result must be written in. A coding step is a spec: the programming language, the function
signature, its inputs and output. Results of earlier steps are passed to later ones.
Use only facts stated in the request. Never assume or invent a number, a fee, a threshold or a policy: a step that
needs one says to look it up (the assistant has tools for accounts and policies) or to use an earlier step's result.
Reply with JSON only: {"steps": [{"title": "<three to six words>", "instruction": "<the task>"}]}"""


def plan(request: str, router: str = "oci-auto-trained", tags: list[str] | None = None, gateway: str = GATEWAY,
         bar: float | None = None, emit: Callable[[dict], None] | None = None) -> list[dict]:
    """The planner is a model call like any other: LiteLLM routes it too."""
    recorder = RouteRecorder(emit or (lambda e: None), router, gateway)
    model = chat_model(router, tags, gateway, bar)
    reply = model.invoke([{"role": "system", "content": PLANNER}, {"role": "user", "content": request}],
                         config={"callbacks": [recorder]})
    match = re.search(r"\{.*\}", _text(reply), re.S)
    try:
        steps = json.loads(match.group(0))["steps"] if match else []
    except (ValueError, KeyError, TypeError):
        steps = []
    steps = [s for s in steps if isinstance(s, dict) and str(s.get("instruction", "")).strip()][:5]
    return steps or [{"title": "Answer the request", "instruction": request}]


def run_plan(messages: list[dict], emit: Callable[[dict], None], router: str = "oci-auto-trained",
             tags: list[str] | None = None, gateway: str = GATEWAY, bar: float | None = None) -> dict:
    """A multi-step agent: plan, then run each step as its own request through the gateway.

    Each step reaches LiteLLM with its own instruction as the user turn, so the router
    picks a route per task: a lookup can go to the fast route, the credit calculation
    to reasoning, a reply in Spanish to the multilingual route, a function to Codex.
    """
    content = messages[-1]["content"]
    request = content if isinstance(content, str) else " ".join(p.get("text", "") for p in content if p.get("type") == "text")
    started, offset = time.time(), 0

    def tagged(step: int):
        def out(event: dict) -> None:
            event = dict(event)
            if "call" in event:
                event["call"] += offset
            if event["type"] == "answer":       # a step's answer; the run's answer comes at the end
                event["type"] = "step_done"
            emit({**event, "step": step})
        return out

    planner_events: list[dict] = []
    steps = plan(request, router, tags, gateway, bar, emit=lambda e: (planner_events.append(e), tagged(0)(e)))
    offset = sum(1 for e in planner_events if e["type"] == "llm")
    emit({"type": "plan", "steps": [{"step": i, "title": str(s.get("title") or f"Step {i}"), "instruction": s["instruction"]}
                                    for i, s in enumerate(steps, 1)]})
    results: list[tuple[str, str]] = []
    for i, s in enumerate(steps, 1):
        title = str(s.get("title") or f"Step {i}")
        emit({"type": "step", "step": i, "title": title, "instruction": s["instruction"]})
        context = f"This step is part of a larger job. The whole request:\n{request}"
        if results:
            context += "\n\nResults of the earlier steps of this job:\n" + "\n\n".join(f"## {t}\n{a}" for t, a in results)
        out = run([{"role": "user", "content": s["instruction"]}], tagged(i), router=router, tags=tags,
                  gateway=gateway, bar=bar, context=context)
        offset += out["calls"]
        results.append((title, out["answer"]))
    answer = "\n\n".join(f"**{i}. {t}**\n\n{a}" for i, (t, a) in enumerate(results, 1))
    emit({"type": "answer", "text": answer, "seconds": round(time.time() - started, 1), "calls": offset,
          "steps": len(steps), "retried_empty": False, "tool_limit_reached": False})
    return {"answer": answer, "calls": offset}


def execute(messages: list[dict], emit: Callable[[dict], None], mode: str = "single", **kw) -> dict:
    """One request, as a single agent run or as a plan of steps."""
    if mode == "plan":
        kw.pop("use_tools", None)
        return run_plan(messages, emit, **kw)
    return run(messages, emit, **kw)


if __name__ == "__main__":
    import json

    prompt = " ".join(sys.argv[1:]) or "How do I reset my Northwind Cloud console password?"
    run([{"role": "user", "content": prompt}], lambda e: print(json.dumps(e, ensure_ascii=False)[:400], flush=True),
        router=os.environ.get("ROUTER", "oci-auto"))
