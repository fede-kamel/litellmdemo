"""Our mini-trained classifier as the complexity router's `classifier_type: custom`.

LiteLLM calls `plugin.classify(context)` with the request's messages and
expects a tier name back (None declines; LiteLLM then routes to the
configured fallback_tier). Each decision is also appended to
out/route-decisions.jsonl, so the web app can show which criterion decided
and with what confidence.

    complexity_router_config:
      classifier_type: custom
      classifier_plugin: trained_classifier.plugin
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from classifier.router_model import shared  # noqa: E402

DECISIONS = ROOT / "out" / "route-decisions.jsonl"


class TrainedClassifier:
    async def classify(self, context) -> str | None:
        messages = list(context.structured_messages or context.raw_messages or [])
        decision = await asyncio.to_thread(shared().classify, messages)
        try:
            DECISIONS.parent.mkdir(parents=True, exist_ok=True)
            with DECISIONS.open("a") as fh:
                fh.write(json.dumps({"at": round(time.time(), 3), **decision.as_dict(),
                                     "metadata": {k: v for k, v in (context.metadata or {}).items()
                                                  if k in ("litellm_call_id", "tags", "user_api_key_alias")}},
                                    default=str) + "\n")
        except OSError:
            pass  # logging must never block routing
        return None if decision.criterion.startswith("fallback") else decision.route


plugin = TrainedClassifier()

# Load the encoder when the gateway starts, not on the first request: loading
# takes seconds, longer than classifier_plugin_timeout_ms.
if shared().trained:
    shared().classify([{"role": "user", "content": "warm up"}])
