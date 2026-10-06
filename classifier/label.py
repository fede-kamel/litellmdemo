"""Label each prompt with the cheapest route whose answer is good enough.

    uv run python classifier/label.py            # prompts.jsonl -> labels.jsonl
    uv run python classifier/label.py --votes 3  # label each prompt three times; keep the median

For every prompt that is not CODE or MULTILINGUAL (those are task-type
routes and keep their family's label), the SIMPLE, MEDIUM and COMPLEX routes
each answer it through the gateway. The judge (oci-judge) grades the three
answers, anonymised and shuffled, on three criteria from 1 to 5:

    correctness            facts, numbers and logic are right
    completeness           every part of the request is answered
    instruction_following  format, length and constraints are respected

An answer passes when all three scores are at least 4. The label is the
cheapest passing route; when none passes, REASONING. Each line keeps the
answers' deployments, costs and scores, so the evaluation can price every
routing policy on the same requests.

One run is a noisy label: relabelling 64 prompts the same way agreed 78% of
the time (65% for MEDIUM). With --votes N every outcome-labelled prompt is
labelled N times; the label is the median vote in cost order (SIMPLE <
MEDIUM < COMPLEX < REASONING), so one outlier run in either direction does not
move it, and each route keeps its pass rate across the votes.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.gateway_client import chat  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
ROOT_OUT = Path(__file__).resolve().parents[1] / "out"
LADDER = [("SIMPLE", "oci-fast"), ("MEDIUM", "oci-balanced"), ("COMPLEX", "oci-strong")]
PASS = 4
CRITERIA = ("correctness", "completeness", "instruction_following")

JUDGE = """You grade answers from AI assistants. The user's request is below, then {n} answers labelled {labels}.
Grade each answer on three criteria, each an integer from 1 (poor) to 5 (excellent):
- correctness: facts, numbers and reasoning are right (for proofs and calculations, check every step)
- completeness: every part of the request is answered
- instruction_following: requested format, length, language and constraints are respected
Judge each answer on its own merits; length is not quality.
Reply with JSON only: {{"grades": {{"A": {{"correctness": 5, "completeness": 5, "instruction_following": 5}}, ...}}}}

REQUEST:
{prompt}

{answers}"""


def parse(text: str) -> dict:
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


async def label(row: dict, rng: random.Random) -> dict:
    if row["route_hint"] in ("CODE", "MULTILINGUAL"):
        return {**row, "route": row["route_hint"], "label_source": "task type"}
    answers = await asyncio.gather(*(chat(group, row["prompt"], max_tokens=4000) for _, group in LADDER))
    order = list(range(len(LADDER)))
    rng.shuffle(order)
    letters = "ABC"
    blocks = "\n\n".join(f"ANSWER {letters[i]}:\n{answers[j]['text'][:6000] if answers[j]['ok'] else '(no answer)'}"
                         for i, j in enumerate(order))
    verdict = await chat("oci-judge", JUDGE.format(n=len(LADDER), labels=", ".join(letters[:len(LADDER)]),
                                                   prompt=row["prompt"], answers=blocks), max_tokens=1500, json_mode=True)
    grades = parse(verdict["text"]).get("grades", {}) if verdict["ok"] else {}
    tiers = []
    for i, j in enumerate(order):
        tier, group = LADDER[j]
        g = grades.get(letters[i], {})
        scores = {c: int(g.get(c, 0) or 0) for c in CRITERIA}
        h = answers[j]["headers"]
        tiers.append({"tier": tier, "group": group, "deployment": h.get("x-litellm-model-name"),
                      "cost": float(h.get("x-litellm-response-cost") or 0), "ok": answers[j]["ok"],
                      "scores": scores, "passed": answers[j]["ok"] and min(scores.values()) >= PASS})
    tiers.sort(key=lambda t: [x for x, _ in LADDER].index(t["tier"]))
    route = next((t["tier"] for t in tiers if t["passed"]), "REASONING")
    return {**row, "route": route, "label_source": "outcome", "tiers": tiers,
            "judge_cost": float(verdict["headers"].get("x-litellm-response-cost") or 0)}


ORDER = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"]


def settle(row: dict, votes: list[dict]) -> dict:
    """Fold extra label runs into a row: the median route and each route's pass rate."""
    runs = [{"route": row["route"], "tiers": row["tiers"]}] + votes
    routes = sorted((r["route"] for r in runs), key=ORDER.index)
    rates = {t: sum(next(x for x in r["tiers"] if x["tier"] == t)["passed"] for r in runs) / len(runs)
             for t, _ in LADDER}
    tiers = [{**t, "pass_rate": round(rates[t["tier"]], 3)} for t in row["tiers"]]
    return {**row, "route": routes[(len(routes) - 1) // 2], "first_route": row.get("first_route", row["route"]),
            "votes": [r["route"] for r in runs], "tiers": tiers, "vote_runs": [{"route": v["route"], "tiers": v["tiers"]} for v in votes],
            "judge_cost": row.get("judge_cost", 0) + sum(v["judge_cost"] for v in votes)}


async def vote(n: int) -> None:
    out = DATA / "labels.jsonl"
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    seeded = {}   # second runs already paid for by the noise check
    sample = ROOT_OUT / "relabel-sample.json"
    if sample.exists():
        for s_ in json.loads(sample.read_text()):
            seeded[s_["id"]] = [{"route": s_["second"], "tiers": s_["second_tiers"], "judge_cost": 0.0}]
    rng = random.Random(13)

    async def one(row: dict) -> dict:
        if row.get("label_source") != "outcome" or len(row.get("votes", [])) >= n:
            return row
        have = [{"route": r, "tiers": t["tiers"], "judge_cost": 0.0} for r, t in zip(row.get("votes", [])[1:], row.get("vote_runs", []))]
        have = have or seeded.get(row["id"], [])
        base = {k: v for k, v in row.items() if k in ("id", "family", "route_hint", "difficulty", "prompt")}
        extra = await asyncio.gather(*(label(base, random.Random(rng.random())) for _ in range(n - 1 - len(have))))
        first = {**row, "route": row.get("first_route", row["route"]),
                 "tiers": [{k: v for k, v in t.items() if k != "pass_rate"} for t in row["tiers"]]}
        return settle(first, have + list(extra))

    partial = ROOT_OUT / "votes-partial.jsonl"   # resumable: finished rows survive a crash
    done = {json.loads(line)["id"]: json.loads(line) for line in partial.read_text().splitlines()} if partial.exists() else {}
    results = list(done.values())
    partial.parent.mkdir(exist_ok=True)
    with partial.open("a") as ck:
        for i, task in enumerate(asyncio.as_completed([one(r) for r in rows if r["id"] not in done]), 1):
            result = await task
            results.append(result)
            ck.write(json.dumps(result, ensure_ascii=False) + "\n")
            ck.flush()
            if i % 40 == 0:
                print(f"voted {i}/{len(rows) - len(done)}", flush=True)
    by_id = {r["id"]: r for r in results}
    out.write_text("".join(json.dumps(by_id[r["id"]], ensure_ascii=False) + "\n" for r in rows))
    partial.unlink()
    changed = sum(1 for r in results if r.get("first_route") and r["first_route"] != r["route"])
    print(json.dumps({"labelled": len(results), "votes": n, "label_changed_by_votes": changed}))


async def main() -> None:
    if "--votes" in sys.argv:
        return await vote(int(sys.argv[sys.argv.index("--votes") + 1]))
    rows = [json.loads(line) for line in (DATA / "prompts.jsonl").read_text().splitlines()]
    out = DATA / "labels.jsonl"
    done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
    rng = random.Random(7)
    todo = [r for r in rows if r["id"] not in done]
    with out.open("a") as fh:
        for i, task in enumerate(asyncio.as_completed([label(r, rng) for r in todo]), 1):
            result = await task
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 20 == 0 or i == len(todo):
                print(f"labelled {i}/{len(todo)}", flush=True)
    labels = [json.loads(line) for line in out.read_text().splitlines()]
    counts: dict[str, int] = {}
    for r in labels:
        counts[r["route"]] = counts.get(r["route"], 0) + 1
    spend = sum(t["cost"] for r in labels for t in r.get("tiers", [])) + sum(r.get("judge_cost", 0) for r in labels) \
        + sum(t["cost"] for r in labels for v in r.get("vote_runs", []) for t in v["tiers"])
    print(json.dumps({"labelled": len(labels), "by_route": counts, "labelling_spend_usd": round(spend, 4)}))


if __name__ == "__main__":
    asyncio.run(main())
