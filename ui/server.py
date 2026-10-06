"""The routing control room's backend.

    uv run uvicorn ui.server:app --port 8780      # gateway on 127.0.0.1:4000

- GET  /api/scenarios          the use cases, each with the route it should take
- POST /api/runs               run the langchain-oci agent on a scenario or a prompt;
                               GET /api/runs/{id}/stream streams every model call's route (SSE)
- POST /api/compare            send one request to the three auto-routers and to fixed routes
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
from classifier.gateway_client import chat  # noqa: E402
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

    def work() -> None:
        try:
            agent.run(messages, emit, router=router, tags=tags, use_tools=router not in ("oci-flaky", "oci-chat"))
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


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        return FileResponse(DIST / "index.html")
