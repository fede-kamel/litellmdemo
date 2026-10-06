"""Pick a model per route from the OCI catalog: every candidate answers the same prompts, one judge grades them.

    uv run python classifier/model_trial.py           # -> evidence/model-trial.json

Before swapping a route's model, measure it against the model it would
replace, on the same requests and the same contract as the labels (the judge
scores correctness, completeness and instruction-following 1-5; pass = all at
least 4). 40 outcome-labelled prompts, stratified by their current label, so
easy and hard requests are both in the sample. Candidates are called directly
through LiteLLM's OCI provider with the operator's session; the judge is the
gateway's oci-judge (GPT-5.2), the same as label.py.

Prices: OCI's public price list where it has one (B-part numbers below);
otherwise the vendor's list price from LiteLLM's model map. OCI publishes no
on-demand price for OpenAI's commercial models.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gateway"))

from classifier.evaluate import SINGLE  # noqa: E402
from classifier.gateway_client import chat  # noqa: E402
from classifier.label import CRITERIA, PASS, parse  # noqa: E402

CANDIDATES = {
    "fast": ["google.gemini-2.5-flash-lite", "openai.gpt-6-luna", "openai.gpt-5.6-luna", "openai.gpt-5.4-nano", "openai.gpt-oss-120b"],
    "balanced": ["openai.gpt-5-mini", "google.gemini-2.5-flash", "openai.gpt-5.4-mini", "xai.grok-4.20-non-reasoning"],
    "strong": ["google.gemini-2.5-pro", "openai.gpt-6-sol", "openai.gpt-6.1-sol", "openai.gpt-5.4", "openai.gpt-5.6-terra"],
    "reasoning": ["xai.grok-4.20-reasoning", "openai.o3", "xai.grok-4.7", "xai.grok-4.6", "openai.gpt-5.5"],
}
# OCI public price list, USD per 1M tokens (input, output), short context, on demand
OCI_PRICE = {
    "google.gemini-2.5-flash-lite": (0.10, 0.40, "B111854/B111856"),
    "google.gemini-2.5-flash": (0.30, 2.50, "B111851/B111853"),
    "google.gemini-2.5-pro": (1.25, 10.0, "B111847/B111849"),
    "xai.grok-4.20-reasoning": (1.25, 2.50, "B111910/B112076"),
    "xai.grok-4.20-non-reasoning": (1.25, 2.50, "B111910/B112076"),
    "xai.grok-4.3": (1.25, 2.50, "B112080/B112082"),
    "xai.grok-4.6": (2.0, 6.0, "B112086/B112589"),
    "xai.grok-4.7": (2.0, 6.0, "B113303/B113305"),
    "openai.gpt-oss-120b": (0.15, 0.60, "B112004/B112005"),
}
SAMPLE = 40
OUT = ROOT / "evidence" / "model-trial.json"


def price(model: str) -> tuple[float, float, str]:
    if model in OCI_PRICE:
        i, o, part = OCI_PRICE[model]
        return i / 1e6, o / 1e6, f"OCI price list {part}"
    import litellm

    name = model.split(".", 1)[1]
    e = litellm.model_cost.get(f"oci/{model}") or litellm.model_cost.get(name) or {}
    return e.get("input_cost_per_token", 0.0), e.get("output_cost_per_token", 0.0), \
        "LiteLLM map (oci)" if litellm.model_cost.get(f"oci/{model}") else f"vendor list price ({name}, LiteLLM map)"


async def main() -> None:
    import litellm
    from oci_session_signer import handler

    cfg = json.loads((Path.home() / ".config/litellmdemo/config.json").read_text())
    rows = [json.loads(line) for line in (ROOT / "classifier/data/labels.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r.get("label_source") == "outcome"]
    by = defaultdict(list)
    for r in rows:
        by[{"COMPLEX": "REASONING"}.get(r["route"], r["route"])].append(r)
    rng = random.Random(21)
    share = {"SIMPLE": 16, "MEDIUM": 12, "REASONING": 12}
    sample = [r for k, n in share.items() for r in rng.sample(by[k], min(n, len(by[k])))]
    gate = asyncio.Semaphore(int(os.environ.get("LITELLMDEMO_CONCURRENCY", "16")))

    async def answer(model: str, row: dict) -> dict:
        async with gate:
            t = time.time()
            try:
                r = await litellm.acompletion(model=f"oci/{model}", messages=[{"role": "user", "content": row["prompt"]}],
                                              max_tokens=4000, oci_signer=handler.signer(), oci_region=cfg["oci_region"],
                                              oci_compartment_id=cfg["oci_compartment_id"], timeout=180, drop_params=True)
                text = r.choices[0].message.content or ""
                u = r.usage
                i, o, _ = price(model)
                cost = (u.prompt_tokens or 0) * i + (u.completion_tokens or 0) * o
                ok, seconds = True, time.time() - t
            except Exception as exc:  # noqa: BLE001 - a failed answer is a failed answer
                text, cost, ok, seconds = f"(error: {type(exc).__name__})", 0.0, False, time.time() - t
        verdict = await chat("oci-judge", SINGLE.format(prompt=row["prompt"], answer=text[:8000]), max_tokens=800,
                             json_mode=True) if ok and text.strip() else {"ok": False, "text": "{}"}
        g = parse(verdict["text"]) if verdict["ok"] else {}
        scores = {c: int(g.get(c, 0) or 0) for c in CRITERIA}
        return {"id": row["id"], "model": model, "ok": ok, "passed": ok and min(scores.values()) >= PASS,
                "scores": scores, "cost": cost, "seconds": round(seconds, 2)}

    jobs = [answer(m, r) for route in CANDIDATES.values() for m in route for r in sample]
    results = []
    for i, task in enumerate(asyncio.as_completed(jobs), 1):
        results.append(await task)
        if i % 100 == 0:
            print(f"answered {i}/{len(jobs)}", flush=True)

    table = {}
    for route, models in CANDIDATES.items():
        table[route] = []
        for m in models:
            rs = [x for x in results if x["model"] == m]
            i, o, src = price(m)
            table[route].append({"model": m, "pass_rate": round(sum(x["passed"] for x in rs) / len(rs), 3),
                                 "errors": sum(not x["ok"] for x in rs), "cost_per_request": round(sum(x["cost"] for x in rs) / len(rs), 6),
                                 "median_seconds": sorted(x["seconds"] for x in rs)[len(rs) // 2],
                                 "price_per_1m": [round(i * 1e6, 3), round(o * 1e6, 3)], "price_source": src})
    OUT.write_text(json.dumps({"prompts": len(sample), "by_label": {k: min(n, len(by[k])) for k, n in share.items()},
                               "routes": table, "answers": results}, indent=1))
    for route, entries in table.items():
        print(f"\n{route}")
        for e in sorted(entries, key=lambda e: -e["pass_rate"]):
            print(f"  {e['model']:32} pass {e['pass_rate']:5.0%}  ${e['cost_per_request']:.5f}/req  {e['median_seconds']:5.1f}s  "
                  f"err {e['errors']}  [{e['price_source']}]")


if __name__ == "__main__":
    asyncio.run(main())
