"""Compare routing policies on the held-out prompts: quality, cost, route accuracy.

    uv run python classifier/evaluate.py     # gateway on 127.0.0.1:4000 -> evidence/classifier-eval.json

Policies:
  always SIMPLE / always COMPLEX / always REASONING   fixed routes
  heuristic     oci-auto, LiteLLM's built-in scorer (route read from the gateway's headers)
  llm           oci-auto-llm, an LLM grades the request (route read from the headers)
  trained       oci-auto-trained, our classifier (route read from the headers)
  oracle        the outcome label: the cheapest route that passed

For the difficulty prompts the label run already holds each SIMPLE, MEDIUM
and COMPLEX answer's cost and verdict; REASONING is answered and judged here.
A policy's quality is the share of prompts whose chosen route passed; its
cost is what those answers cost. For CODE and MULTILINGUAL prompts, only
route accuracy is reported: the built-in tiers cannot express them.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.gateway_client import chat  # noqa: E402
from classifier.label import CRITERIA, PASS, parse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "classifier" / "data"
OUT = ROOT / "evidence" / "classifier-eval.json"
DIFFICULTY = ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING")
ROUTERS = {"heuristic": "oci-auto", "llm": "oci-auto-llm", "trained": "oci-auto-trained"}

SINGLE = """You grade one answer from an AI assistant. Grade it on correctness (facts, numbers and every reasoning
step are right), completeness (every part answered) and instruction_following (format, length, constraints), each
an integer from 1 to 5. Reply with JSON only: {{"correctness": 5, "completeness": 5, "instruction_following": 5}}

REQUEST:
{prompt}

ANSWER:
{answer}"""


async def reasoning_tier(row: dict) -> dict:
    answer = await chat("oci-reasoning", row["prompt"], max_tokens=6000)
    verdict = await chat("oci-judge", SINGLE.format(prompt=row["prompt"], answer=answer["text"][:8000]),
                         max_tokens=800, json_mode=True) if answer["ok"] else {"ok": False, "text": "{}"}
    g = parse(verdict["text"]) if verdict["ok"] else {}
    scores = {c: int(g.get(c, 0) or 0) for c in CRITERIA}
    return {"tier": "REASONING", "group": "oci-reasoning", "deployment": answer["headers"].get("x-litellm-model-name"),
            "cost": float(answer["headers"].get("x-litellm-response-cost") or 0), "ok": answer["ok"],
            "scores": scores, "passed": answer["ok"] and min(scores.values()) >= PASS}


async def routed(router: str, prompt: str) -> dict:
    r = await chat(router, prompt, max_tokens=4000)
    h = r["headers"]
    return {"route": h.get("x-litellm-complexity-router-tier"), "deployment": h.get("x-litellm-model-name"),
            "classifier_cost": float(h.get("x-litellm-classifier-cost") or 0),
            "seconds": float(h.get("x-litellm-response-duration-ms") or 0) / 1000, "ok": r["ok"]}


async def main() -> None:
    labels = {json.loads(line)["id"]: json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines()}
    held = [labels[i] for i in json.loads((DATA / "split.json").read_text())["held_out"] if i in labels]
    # MULTILINGUAL is decided by a rule, not learned: two requests per language test it.
    by_lang: dict[str, list[dict]] = {}
    for r in labels.values():
        if r["route"] == "MULTILINGUAL":
            by_lang.setdefault(r["family"], []).append(r)
    held += [r for rows_ in by_lang.values() for r in rows_[:2]]

    async def one(row: dict) -> dict:
        jobs = {name: routed(group, row["prompt"]) for name, group in ROUTERS.items()}
        if row["route"] in DIFFICULTY:
            results = await asyncio.gather(reasoning_tier(row), *jobs.values())
            row = {**row, "tiers": row["tiers"] + [results[0]]}
            routes = dict(zip(jobs, results[1:], strict=True))
        else:
            routes = dict(zip(jobs, await asyncio.gather(*jobs.values()), strict=True))
        return {**row, "routed": routes}

    rows = await asyncio.gather(*(one(r) for r in held))
    diff = [r for r in rows if r["route"] in DIFFICULTY]
    task = [r for r in rows if r["route"] not in DIFFICULTY]

    def tier_of(row, name):
        if name.startswith("always "):
            return name.split()[1]
        if name == "oracle":
            return row["route"]
        return (row["routed"][name]["route"] or "MEDIUM").upper()

    policies = ["always SIMPLE", "always COMPLEX", "always REASONING", "heuristic", "llm", "trained", "oracle"]
    table = []
    for p in policies:
        quality = cost = 0.0
        exact = 0
        overhead = 0.0
        for r in diff:
            t = tier_of(r, p)
            chosen = next((x for x in r["tiers"] if x["tier"] == t), None)
            if chosen is None:          # a task-type route on a difficulty prompt: price it as MEDIUM
                chosen = next(x for x in r["tiers"] if x["tier"] == "MEDIUM")
            quality += chosen["passed"]
            cost += chosen["cost"]
            exact += t == r["route"]
            if p in ROUTERS:
                overhead += r["routed"][p]["classifier_cost"]
        task_hits = sum(tier_of(r, p) == r["route"] for r in task) if p in ROUTERS or p == "oracle" else None
        table.append({"policy": p, "quality": round(quality / len(diff), 3), "cost_usd": round(cost, 5),
                      "classifier_cost_usd": round(overhead, 5), "route_match": round(exact / len(diff), 3),
                      "task_type_accuracy": None if task_hits is None else round(task_hits / max(1, len(task)), 3)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"held_out_difficulty": len(diff), "held_out_task_type": len(task),
                               "policies": table, "rows": rows}, indent=1, ensure_ascii=False))
    print(f"held-out: {len(diff)} difficulty prompts, {len(task)} code/multilingual prompts\n")
    print(f"{'policy':18s} {'quality':>8s} {'cost $':>10s} {'clf $':>8s} {'route=label':>12s} {'code/lang':>10s}")
    for t in table:
        ta = "-" if t["task_type_accuracy"] is None else f"{t['task_type_accuracy']:.0%}"
        print(f"{t['policy']:18s} {t['quality']:8.0%} {t['cost_usd']:10.4f} {t['classifier_cost_usd']:8.4f} "
              f"{t['route_match']:12.0%} {ta:>10s}")


if __name__ == "__main__":
    asyncio.run(main())
