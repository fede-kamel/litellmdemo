"""The routing control room's backend.

    uv run uvicorn ui.server:app --port 8780      # gateway on 127.0.0.1:4000

- GET  /api/scenarios          the use cases, each with the route it should take
- POST /api/runs               run the langchain-oci agent on a scenario or a prompt;
                               GET /api/runs/{id}/stream streams every model call's route (SSE)
- POST /api/compare            send one request to the three auto-routers and to fixed routes
- POST /api/ask                any prompt through oci-auto-trained, with why: the checks, the model's
                               probabilities, precedent from the labels, and why that deployment
- POST /api/classify           our classifier's view of a request: route, criterion, probabilities
- GET  /api/gateway            the routes, model groups and deployments from gateway/config.yaml
- GET  /api/classifier         training data, held-out accuracy, the policy comparison
- GET  /api/stats              this session's calls, spend and route mix
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import agent  # noqa: E402
from app.scenarios import SCENARIOS, messages_for, summary  # noqa: E402
from classifier.gateway_client import GATEWAYS, active_gateway, chat, mark_down  # noqa: E402
from classifier.explain import explain  # noqa: E402
from classifier.router_model import shared  # noqa: E402

app = FastAPI(title="LiteLLM routing control room")
RUNS: dict[str, dict] = {}
CALLS: list[dict] = []
ROUTERS = ["oci-auto-trained", "oci-auto-llm", "oci-auto"]


class RunRequest(BaseModel):
    scenario: str | None = None
    prompt: str | None = Field(default=None, max_length=200_000)
    router: str = Field(default="oci-auto-trained", pattern=r"^oci-[a-z-]+$")
    tags: list[str] | None = None


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return [summary(s) for s in SCENARIOS]


def _request(req: RunRequest) -> tuple[list[dict], str, list[str] | None, dict | None]:
    if req.scenario:
        s = next((x for x in SCENARIOS if x["id"] == req.scenario), None)
        if s is None:
            raise HTTPException(404, "unknown scenario")
        return messages_for(s), s.get("model", req.router), s.get("tags", req.tags), s
    if not req.prompt:
        raise HTTPException(400, "a scenario or a prompt is required")
    return [{"role": "user", "content": req.prompt}], req.router, req.tags, None


@app.post("/api/runs")
async def start_run(req: RunRequest) -> dict:
    messages, router, tags, scenario = _request(req)
    rid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:6]
    run = {"id": rid, "router": router, "tags": tags, "scenario": scenario and summary(scenario),
           "events": [], "done": False, "cond": asyncio.Condition()}
    RUNS[rid] = run
    loop = asyncio.get_running_loop()

    def emit(event: dict) -> None:
        event = {"t": round(time.time(), 3), **event}
        if event["type"] == "llm":
            CALLS.append({**event, "run": rid, "scenario": scenario and scenario["id"]})
        asyncio.run_coroutine_threadsafe(_append(run, event), loop)

    gateway = await active_gateway()

    def work() -> None:
        tools = router not in ("oci-flaky", "oci-chat")
        try:
            try:
                agent.run(messages, emit, router=router, tags=tags, use_tools=tools, gateway=gateway)
            except Exception as exc:  # noqa: BLE001
                # A gateway that fails before any model call (unreachable, or its OCI
                # signing broken) gets the run once more on the next gateway.
                calls = [e for e in run["events"] if e["type"] == "llm"]
                spare = [g for g in GATEWAYS if g != gateway]
                if calls or not spare or not _looks_like_gateway_fault(exc):
                    raise
                mark_down(gateway)
                emit({"type": "failover", "from": gateway, "to": spare[0], "reason": str(exc)[:200]})
                agent.run(messages, emit, router=router, tags=tags, use_tools=tools, gateway=spare[0])
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            emit({"type": "error", "message": str(exc)[:500]})
        finally:
            asyncio.run_coroutine_threadsafe(_finish(run), loop)

    threading.Thread(target=work, daemon=True).start()
    return {"id": rid}


async def _append(run: dict, event: dict) -> None:
    async with run["cond"]:
        run["events"].append(event)
        run["cond"].notify_all()


def _looks_like_gateway_fault(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return any(k in text for k in ("APIConnectionError", "ConnectError", "Connection refused", "OciException", "502", "503"))


async def _finish(run: dict) -> None:
    async with run["cond"]:
        run["done"] = True
        run["cond"].notify_all()


@app.get("/api/runs/{rid}/stream")
async def stream(rid: str):
    run = RUNS.get(rid)
    if run is None:
        raise HTTPException(404, "unknown run")

    async def events():
        sent = 0
        while True:
            async with run["cond"]:
                while sent >= len(run["events"]) and not run["done"]:
                    await run["cond"].wait()
                batch, done = run["events"][sent:], run["done"]
            for e in batch:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            sent += len(batch)
            if done and sent >= len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                return

    return StreamingResponse(events(), media_type="text/event-stream")


class CompareRequest(BaseModel):
    scenario: str | None = None
    prompt: str | None = Field(default=None, max_length=200_000)


@app.post("/api/compare")
async def compare(req: CompareRequest) -> dict:
    messages, _, _, scenario = _request(RunRequest(scenario=req.scenario, prompt=req.prompt))

    async def one(router: str) -> dict:
        started = time.time()
        r = await chat(router, messages, max_tokens=4000)
        return {"router": router, "ok": r["ok"], **agent.route_of(r["headers"]),
                "seconds": round(time.time() - started, 2), "text": r["text"][:3000]}

    results = await asyncio.gather(*(one(r) for r in ROUTERS))
    decision = await asyncio.to_thread(shared().classify, messages)
    return {"scenario": scenario and summary(scenario), "classifier": decision.as_dict(), "results": results}


class AskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=200_000)
    max_tokens: int = Field(default=1200, ge=16, le=8000)


EXAMPLES = [
    "What is 18 percent of 4,217.50?",
    "Draft a short, polite reply to a customer who was charged twice in September, explaining the refund steps.",
    "Our GPU spend grew 12%, 9%, 15% and 11% over four quarters from $1.2M. With a $7.5M annual budget and a hard "
    "$2.1M cap per quarter, model three growth scenarios, say when the cap binds, and what to defer.",
    "Explain this SQL: SELECT region, SUM(amount) FROM orders GROUP BY region HAVING SUM(amount) > 1e6;",
    "Bonjour, comment puis-je télécharger ma facture du mois dernier ?",
]


@app.get("/api/ask/examples")
def ask_examples() -> list[str]:
    return EXAMPLES


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    """One request through the trained router, with the evidence for its route and its model."""
    messages = [{"role": "user", "content": req.prompt}]
    started = time.time()
    why, reply = await asyncio.gather(asyncio.to_thread(explain, messages),
                                      chat("oci-auto-trained", messages, max_tokens=req.max_tokens))
    route = agent.route_of(reply["headers"])
    cfg = yaml.safe_load((ROOT / "gateway" / "config.yaml").read_text())
    trained = next(d for d in cfg["model_list"] if d["model_name"] == "oci-auto-trained")
    group = trained["litellm_params"]["complexity_router_config"]["tiers"].get(route.get("route") or "", "")
    candidates = [d["litellm_params"]["model"] for d in cfg["model_list"] if d["model_name"] == group]
    strategy = cfg.get("router_settings", {}).get("routing_strategy", "simple-shuffle")
    if not reply["ok"]:
        model_why = "The gateway did not answer: " + reply["text"][:300]
    elif route.get("fallbacks"):
        model_why = (f"{route.get('deployment')} answered after {route['fallbacks']} fallback(s): "
                     f"the first choice in {group} failed, so the gateway moved down the fallback chain.")
    elif len(candidates) > 1:
        model_why = (f"{group} has {len(candidates)} deployments; with {strategy} the gateway sent it to the one "
                     f"answering fastest lately: {route.get('deployment')}.")
    else:
        model_why = f"{group} has one deployment: {route.get('deployment')}."
    gateway_route = route.get("route")
    return {"prompt": req.prompt, "why": why, "group": group, "candidates": candidates, "strategy": strategy,
            "model_why": model_why, "route": route, "ok": reply["ok"], "text": reply["text"][:6000],
            "agrees": gateway_route == why["decision"]["route"], "seconds": round(time.time() - started, 2),
            "gateway": reply.get("gateway"), "gateway_role": _role(reply.get("gateway"))}


def _role(url: str | None) -> str:
    """"primary" for LITELLM_GATEWAY (the OKE gateway in the cluster demo), "fallback" for the others."""
    if not url:
        return "none"
    return "primary" if url == GATEWAYS[0] else "fallback"


@app.post("/api/classify")
async def classify(req: CompareRequest) -> dict:
    messages, _, _, _ = _request(RunRequest(scenario=req.scenario, prompt=req.prompt))
    return (await asyncio.to_thread(shared().classify, messages)).as_dict()


@app.get("/api/gateway")
def gateway() -> dict:
    cfg = yaml.safe_load((ROOT / "gateway" / "config.yaml").read_text())
    groups: dict[str, list[dict]] = {}
    for d in cfg["model_list"]:
        p = d["litellm_params"]
        groups.setdefault(d["model_name"], []).append(
            {"model": p["model"], "tags": p.get("tags"), "router": p["model"].startswith("auto_router/")})
    routers = {}
    for d in cfg["model_list"]:
        c = d["litellm_params"].get("complexity_router_config")
        if c:
            routers[d["model_name"]] = {"classifier": c.get("classifier_type", "heuristic"), "routes": c["tiers"]}
    rs = cfg.get("router_settings", {})
    return {"groups": groups, "routers": routers, "strategy": rs.get("routing_strategy"),
            "fallbacks": rs.get("fallbacks", []), "context_window_fallbacks": rs.get("context_window_fallbacks", [])}


@app.get("/api/classifier")
def classifier() -> dict:
    meta = ROOT / "classifier" / "model" / "meta.json"
    ev = ROOT / "evidence" / "classifier-eval.json"
    out = {"trained": meta.exists(), "meta": json.loads(meta.read_text()) if meta.exists() else None, "eval": None}
    if ev.exists():
        e = json.loads(ev.read_text())
        out["eval"] = {k: e[k] for k in ("held_out_difficulty", "held_out_task_type", "policies")}
    labels = ROOT / "classifier" / "data" / "labels.jsonl"
    if labels.exists():
        rows = [json.loads(line) for line in labels.read_text().splitlines()]
        out["data"] = {"prompts": len(rows), "by_route": dict(Counter(r["route"] for r in rows)),
                       "examples": [{"prompt": r["prompt"][:160], "route": r["route"], "family": r["family"]}
                                    for r in rows[::max(1, len(rows) // 12)]][:12]}
    return out


@app.get("/api/stats")
def stats() -> dict:
    return {"calls": len(CALLS), "spend_usd": round(sum(c.get("cost") or 0 for c in CALLS), 6),
            "by_route": dict(Counter(c.get("route") or c.get("group") for c in CALLS)),
            "by_deployment": dict(Counter(c.get("deployment") for c in CALLS)),
            "fallbacks": sum(c.get("fallbacks", 0) for c in CALLS)}


@app.on_event("startup")
async def warm() -> None:
    if shared().trained:
        await asyncio.to_thread(shared().classify, [{"role": "user", "content": "warm up"}])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "classifier_trained": shared().trained}


@app.get("/api/gateways")
async def gateways() -> dict:
    """Which gateway new requests go to, and the others in failover order."""
    active = await active_gateway()
    return {"active": active, "role": _role(active), "gateways": GATEWAYS}


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        return FileResponse(DIST / "index.html")
