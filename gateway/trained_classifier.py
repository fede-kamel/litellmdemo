"""Our mini-trained classifier as the complexity router's `classifier_type: custom`.

LiteLLM calls `plugin.classify(context)` with the request's messages and
expects a tier name back (None declines; LiteLLM then routes to the
configured fallback_tier). Each decision is also appended to
out/route-decisions.jsonl, so the web app can show which criterion decided
and with what confidence.

With ROUTE_CLASSIFIER_URL set (Kubernetes), the plugin asks the
route-classifier service instead of loading the model into the gateway. If
the service is down or slow, it declines and LiteLLM routes to fallback_tier:
a classifier outage degrades routing, never availability.

    complexity_router_config:
      classifier_type: custom
      classifier_plugin: trained_classifier.plugin
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DECISIONS = Path(os.environ.get("ROUTE_DECISIONS_LOG", ROOT / "out" / "route-decisions.jsonl"))
SERVICE = os.environ.get("ROUTE_CLASSIFIER_URL")   # e.g. http://route-classifier:8080


class TrainedClassifier:
    def __init__(self) -> None:
        self._client = None

    @staticmethod
    def bar_of(context) -> float | None:
        metadata = dict(context.metadata or {})
        for source in (metadata, metadata.get("requester_metadata") or {}):
            value = source.get("route_quality_bar") if isinstance(source, dict) else None
            if value is not None:
                try:
                    return min(0.99, max(0.3, float(value)))
                except (TypeError, ValueError):
                    return None
        return None

    async def decide(self, messages: list, bar: float | None = None) -> dict:
        if SERVICE:
            import httpx

            if self._client is None:
                self._client = httpx.AsyncClient(base_url=SERVICE, timeout=3.0)
            try:
                r = await self._client.post("/classify", json={"messages": messages, "bar": bar})
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                return {"route": None, "criterion": f"fallback: classifier service ({type(exc).__name__})"}
        from classifier.router_model import shared

        return (await asyncio.to_thread(shared().classify, messages, bar)).as_dict()

    async def classify(self, context) -> str | None:
        messages = list(context.structured_messages or context.raw_messages or [])
        decision = await self.decide(messages, self.bar_of(context))
        try:
            DECISIONS.parent.mkdir(parents=True, exist_ok=True)
            with DECISIONS.open("a") as fh:
                fh.write(json.dumps({"at": round(time.time(), 3), **decision,
                                     "metadata": {k: v for k, v in (context.metadata or {}).items()
                                                  if k in ("litellm_call_id", "tags", "user_api_key_alias")}},
                                    default=str) + "\n")
        except OSError:
            pass  # logging must never block routing
        return None if decision["criterion"].startswith("fallback") else decision["route"]


plugin = TrainedClassifier()

# Load the encoder when the gateway starts, not on the first request: loading
# takes seconds, longer than classifier_plugin_timeout_ms.
if not SERVICE:
    from classifier.router_model import shared

    if shared().trained:
        shared().classify([{"role": "user", "content": "warm up"}])
