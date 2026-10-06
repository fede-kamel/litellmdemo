"""The trained classifier as its own service, the way it runs on Kubernetes.

    uvicorn classifier.serve:app --host 0.0.0.0 --port 8080

POST /classify {"messages": [...]} returns the same decision the in-process
plugin makes: route, criterion, probabilities, milliseconds. GET /healthz is
ready only once the encoder is loaded, so Kubernetes sends no traffic to a pod
that would still be loading weights. The gateway's plugin calls this service
when ROUTE_CLASSIFIER_URL is set (gateway/trained_classifier.py).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from classifier.router_model import shared

state = {"ready": False}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(shared().classify, [{"role": "user", "content": "warm up"}])
    state["ready"] = shared().trained
    yield


app = FastAPI(title="route-classifier", lifespan=lifespan)


class ClassifyRequest(BaseModel):
    messages: list[dict]
    bar: float | None = Field(default=None, ge=0.3, le=0.99)   # quality bar; None: the one chosen in training


@app.post("/classify")
async def classify(req: ClassifyRequest) -> dict:
    decision = await asyncio.to_thread(shared().classify, req.messages, req.bar)
    return decision.as_dict()


@app.get("/healthz")
async def healthz() -> dict:
    if not state["ready"]:
        raise HTTPException(503, "loading")
    return {"ok": True, "encoder": "loaded"}
