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
from ui import console, sandbox  # noqa: E402
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
    bar: float | None = Field(default=None, ge=0.3, le=0.99)    # the ladder's quality bar; None: the trained one
    runtime: str = Field(default="openshell", pattern=r"^(openshell|host)$")
    image: str | None = Field(default=None, max_length=12_000_000, pattern=r"^data:image/(png|jpeg|webp|gif);base64,")
    mode: str | None = Field(default=None, pattern=r"^(single|plan)$")   # plan: decompose, route each step; None: the scenario's
    replay: bool = True    # if every live path fails, replay a recorded run of the same request (labelled as such)


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return [summary(s) for s in SCENARIOS]


def _request(req: RunRequest) -> tuple[list[dict], str, list[str] | None, dict | None]:
    if req.scenario:
        s = next((x for x in SCENARIOS if x["id"] == req.scenario), None)
        if s is None:
            raise HTTPException(404, "unknown scenario")
        return messages_for(s), s.get("model", req.router), s.get("tags", req.tags), s
    if not req.prompt and not req.image:
        raise HTTPException(400, "a scenario or a prompt is required")
    if req.image:   # multimodal: the text and the image in one user turn
        parts = [{"type": "text", "text": req.prompt or "What is in this image?"},
                 {"type": "image_url", "image_url": {"url": req.image}}]
        return [{"role": "user", "content": parts}], req.router, req.tags, None
    return [{"role": "user", "content": req.prompt}], req.router, req.tags, None


@app.post("/api/runs")
async def start_run(req: RunRequest) -> dict:
    messages, router, tags, scenario = _request(req)
    mode = req.mode or (scenario or {}).get("mode") or "single"
    rid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:6]
    run = {"id": rid, "router": router, "tags": tags, "scenario": scenario and summary(scenario), "mode": mode,
           "events": [], "done": False, "cond": asyncio.Condition()}
    RUNS[rid] = run
    loop = asyncio.get_running_loop()

    def emit(event: dict) -> None:
        event = {"t": round(time.time(), 3), **event}
        if event["type"] == "llm":
            CALLS.append({**event, "run": rid, "scenario": scenario and scenario["id"]})
        asyncio.run_coroutine_threadsafe(_append(run, event), loop)

    gateway = await active_gateway()
    in_sandbox = req.runtime == "openshell" and await asyncio.to_thread(sandbox.available)

    def work() -> None:
        tools = router not in ("oci-flaky", "oci-chat")
        started = time.time()
        try:
            if in_sandbox:
                emit({"type": "runtime", "runtime": "openshell", "sandbox": sandbox.NAME, "gateway": sandbox.SANDBOX_GATEWAY})
                if sandbox.run(_sandbox_request(messages, router, tags, req.bar) | {"mode": mode}, emit):
                    _after_run(emit, messages, run, started)
                    return
                # The sandbox could not answer (its gateway down, the sandbox gone): say
                # so, and answer from the host through the failover gateways instead.
                emit({"type": "failover", "from": f"OpenShell sandbox {sandbox.NAME}", "to": "the host agent",
                      "reason": "the sandbox path did not answer"})
            emit({"type": "runtime", "runtime": "host", "gateway": gateway})
            try:
                agent.execute(messages, emit, mode=mode, router=router, tags=tags, use_tools=tools, gateway=gateway, bar=req.bar)
            except Exception as exc:  # noqa: BLE001
                # A gateway that fails before any model call (unreachable, or its OCI
                # signing broken) gets the run once more on the next gateway.
                calls = [e for e in run["events"] if e["type"] == "llm"]
                spare = [g for g in GATEWAYS if g != gateway]
                if calls or not spare or not _looks_like_gateway_fault(exc):
                    raise
                mark_down(gateway, f"host run: {type(exc).__name__}")
                emit({"type": "failover", "from": gateway, "to": spare[0], "reason": str(exc)[:200]})
                agent.execute(messages, emit, mode=mode, router=router, tags=tags, use_tools=tools, gateway=spare[0], bar=req.bar)
            _after_run(emit, messages, run, started, network=False)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            # Both live paths failed (the sandbox, then the host): a recorded run of the
            # same request, clearly labelled, beats an error on stage.
            if not (req.replay and _replay(req, emit)):
                emit({"type": "error", "message": str(exc)[:500]})
        finally:
            _record(req, run["events"])
            asyncio.run_coroutine_threadsafe(_finish(run), loop)

    threading.Thread(target=work, daemon=True).start()
    return {"id": rid}


RECORDINGS = ROOT / "out" / "recordings"


def _recording_key(req: "RunRequest") -> str:
    import hashlib

    s = next((x for x in SCENARIOS if x["id"] == req.scenario), None) if req.scenario else None
    default = (s or {}).get("mode") or "single"
    mode = req.mode if req.mode and req.mode != default else None    # the default mode keys like an unset one
    raw = json.dumps({"s": req.scenario, "m": mode, "p": req.prompt, "r": req.router, "t": req.tags, "b": req.bar,
                      "i": hashlib.sha256((req.image or "").encode()).hexdigest()}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _record(req: "RunRequest", events: list[dict]) -> None:
    """Keep every run that answered, so a conference network failure can replay it."""
    if not any(e["type"] == "answer" for e in events) or any(e.get("replayed") for e in events):
        return
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    (RECORDINGS / f"{_recording_key(req)}.json").write_text(json.dumps(
        {"recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "prompt": (req.prompt or req.scenario or "")[:200],
         "events": events}, ensure_ascii=False))


def _replay(req: "RunRequest", emit) -> bool:
    """Replay a recorded run of the same request, with its original pacing (capped), labelled as a replay."""
    path = RECORDINGS / f"{_recording_key(req)}.json"
    if not path.exists():
        return False
    rec = json.loads(path.read_text())
    emit({"type": "replay", "recorded_at": rec["recorded_at"],
          "reason": "the live path did not answer; this is a recorded run of the same request"})
    last = None
    for e in rec["events"]:
        if e["type"] in ("replay", "runtime", "failover", "sandbox_error", "error"):
            continue
        if last is not None and e.get("t") and last:
            time.sleep(min(1.5, max(0.0, e["t"] - last)))
        last = e.get("t") or last
        emit({k: v for k, v in e.items() if k != "t"} | {"replayed": True})
    return True


def _sandbox_request(messages: list[dict], router: str, tags: list[str] | None, bar: float | None) -> dict:
    content = messages[-1]["content"]
    prompt, image = (content, None) if isinstance(content, str) else (
        next((p["text"] for p in content if p.get("type") == "text"), ""),
        next((p["image_url"]["url"] for p in content if p.get("type") == "image_url"), None))
    return {"prompt": prompt, "image": image, "router": router, "tags": tags, "bar": bar}


def _after_run(emit, messages: list[dict], run: dict, started: float, network: bool = True) -> None:
    """What the screen needs once the agent is done: the sandbox's network decisions,
    LiteLLM's record of the agent key, and the first route explained."""
    if network:
        emit({"type": "sandbox_net", "events": sandbox.network(started)})
        key = sandbox.agent_key()
        if key:
            emit({"type": "key", **key})
    decision = next((e for e in run["events"] if e["type"] == "classify"), None)
    if decision:
        try:
            why = explain(messages, 3, None, decision)
            emit({"type": "explain", "call": decision.get("call", 1), **why})
        except Exception as exc:  # noqa: BLE001 - an explanation must never fail the run
            emit({"type": "explain", "error": str(exc)[:200]})


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
    max_tokens: int = Field(default=4000, ge=16, le=8000)   # reasoning models spend much of it thinking
    bar: float | None = Field(default=None, ge=0.3, le=0.99)   # the ladder's quality bar; None: the trained default


EXAMPLES = [
    "What is 18 percent of 4,217.50?",
    "Draft a short, polite reply to a customer who was charged twice in September, explaining the refund steps.",
    "Our GPU spend grew 12%, 9%, 15% and 11% over four quarters from $1.2M. With a $7.5M annual budget and a hard "
    "$2.1M cap per quarter, model three growth scenarios, say when the cap binds, and what to defer.",
    "Explain this SQL: SELECT region, SUM(amount) FROM orders GROUP BY region HAVING SUM(amount) > 1e6;",
    "Bonjour, comment puis-je télécharger ma facture du mois dernier ?",
]


@app.get("/api/sample-image")
def sample_image():
    """The demo's invoice photo (fictional Northwind Cloud), for the multimodal example."""
    import base64

    from fastapi import Response

    from app.scenarios import invoice_image

    return Response(base64.b64decode(invoice_image().split(",", 1)[1]), media_type="image/png")


@app.get("/api/ask/config")
def ask_config() -> dict:
    """Examples, the trained quality bar, and what each bar delivered on held-out prompts."""
    meta = json.loads((ROOT / "classifier" / "model" / "meta.json").read_text()).get("ladder", {})
    return {"examples": EXAMPLES, "default_bar": meta.get("bar"), "held_out_curve": meta.get("held_out_curve", []),
            "held_out": meta.get("held_out", {}), "held_out_prompts": meta.get("held_out_prompts")}


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    """One request through the trained router, with the evidence for its route and its model."""
    messages = [{"role": "user", "content": req.prompt}]
    started = time.time()
    metadata = {"route_quality_bar": req.bar} if req.bar is not None else None
    why, reply = await asyncio.gather(asyncio.to_thread(explain, messages, 3, req.bar),
                                      chat("oci-auto-trained", messages, max_tokens=req.max_tokens, metadata=metadata))
    route = agent.route_of(reply["headers"])
    if reply["ok"]:
        CALLS.append(route)
    if reply["ok"] and not reply["text"]:
        reply = {**reply, "text": "(The model returned no text: it spent its whole token budget reasoning. "
                                  "Raise max_tokens for this request.)"}
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
        voted = [r for r in rows if r.get("votes")]
        same = sum(1 for r in voted if len(set(r["votes"])) == 1)   # the three runs chose the same cheapest passing route
        out["labels"] = {"outcome_prompts": len(voted), "runs": 3, "unanimous": same,
                         "with_reasoning": sum(1 for r in rows if r.get("reasoning")),
                         "families": len({r["family"] for r in rows})}
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


@app.get("/api/console")
async def console_stream():
    """Live lines from OpenShell, LiteLLM and the classifier (Server-Sent Events); the last 120 first."""
    console.start()
    q: asyncio.Queue = asyncio.Queue()
    console.SUBSCRIBERS.add(q)

    async def events():
        try:
            for line in list(console.BUFFER)[-120:]:
                yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            console.SUBSCRIBERS.discard(q)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.on_event("startup")
async def start_console() -> None:
    console.start()


@app.on_event("startup")
async def warm() -> None:
    if shared().trained:
        await asyncio.to_thread(shared().classify, [{"role": "user", "content": "warm up"}])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "classifier_trained": shared().trained}


@app.get("/api/session")
def oci_session() -> dict:
    """Minutes left on the operator's OCI session (the one thing that expires during a talk)."""
    import base64
    import configparser

    cfg = json.loads((Path.home() / ".config/litellmdemo/config.json").read_text())
    c = configparser.ConfigParser()
    c.read(Path.home() / ".oci/config")
    try:
        t = Path(c[cfg["oci_profile"]]["security_token_file"]).expanduser().read_text().split(".")[1]
        t += "=" * (-len(t) % 4)
        left = int((json.loads(base64.urlsafe_b64decode(t))["exp"] - time.time()) / 60)
    except (KeyError, OSError, ValueError, IndexError):
        left = -1
    status = Path.home() / ".config/litellmdemo/run/session.json"
    refresher = json.loads(status.read_text()) if status.exists() else {}
    return {"minutes_left": left, "refresher": refresher.get("state", "not running")}


@app.get("/api/sandbox")
async def sandbox_status() -> dict:
    """Is the OpenShell sandbox up, and what can its agent key do (from LiteLLM)."""
    ready = await asyncio.to_thread(sandbox.available)
    import os

    return {"ready": ready, "name": sandbox.NAME, "gateway": sandbox.SANDBOX_GATEWAY,
            "cluster": os.environ.get("LITELLMDEMO_CLUSTER", "local"),
            "key": await asyncio.to_thread(sandbox.agent_key) if ready else None}


@app.post("/api/sandbox/probe")
async def sandbox_probe() -> dict:
    """The agent tries to leave: OCI directly, a model vendor, the gateway's admin API."""
    started = time.time()
    tries = await asyncio.to_thread(sandbox.probe)
    return {"tries": tries, "network": await asyncio.to_thread(sandbox.network, started)}


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
