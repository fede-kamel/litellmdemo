"""Write the prompts the classifier learns from, through the gateway.

    uv run python classifier/generate.py            # -> classifier/data/prompts.jsonl
    uv run python classifier/generate.py --domains  # append the business-domain prompts

The judge model (group oci-judge) writes prompts for thirteen task families,
easy to expert, plus code tasks and requests in seven other languages. Each
line: {"id", "family", "route_hint", "difficulty", "prompt"}. route_hint is
what the family suggests; classifier/label.py replaces it with the route that
outcomes justify, for every prompt that is not CODE or MULTILINGUAL.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.gateway_client import chat  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "prompts.jsonl"

# family, route hint, what to ask for
FAMILIES = [
    ("factual", "SIMPLE", "short factual questions with one clear answer (capitals, dates, units, definitions)"),
    ("formatting", "SIMPLE", "formatting or conversion requests on a short given text (to bullets, to JSON, title case, a table)"),
    ("rewrite", "SIMPLE", "requests to rewrite one or two given sentences (shorter, more formal, friendlier)"),
    ("explanation", "MEDIUM", "requests to explain a concept clearly for a given audience"),
    ("summary", "MEDIUM", "requests to summarise a given paragraph of 80-150 words (include the paragraph)"),
    ("email", "MEDIUM", "requests to write a short business email or message for a stated situation"),
    ("analysis", "COMPLEX", "multi-part business or technical analysis questions with trade-offs"),
    ("comparison", "COMPLEX", "requests to compare several options against stated criteria and recommend one"),
    ("longform", "COMPLEX", "requests for structured long-form writing: a policy, a plan, a report outline with content"),
    ("math", "REASONING", "math problems from arithmetic word problems up to proofs and olympiad-style questions"),
    ("logic", "REASONING", "logic puzzles and deduction problems, from simple to hard"),
    ("planning", "REASONING", "scheduling or planning problems under several hard constraints"),
    ("quantitative", "REASONING", "quantitative estimation or finance problems that need several calculation steps"),
]
# Business domains the first set missed: an assistant at a cloud company gets
# these every day, and the classifier misrouted them (README "Unseen domains").
# Their route is decided by outcome, like every family above.
DOMAINS = [
    ("support", "customer-support requests to a cloud provider's assistant: account access, how-to questions, "
                "troubleshooting steps, escalations that cite SLA terms"),
    ("billing", "billing requests: unexpected charges, refunds, disputes, drafting replies to customers, "
                "usage-based pricing questions, some with figures to work out"),
    ("itops", "IT operations requests: incident triage, runbook steps, alert tuning, capacity questions, "
              "change plans, postmortem write-ups"),
    ("finance", "finance and FP&A requests with the numbers given: budgets, variances, forecasts, unit economics"),
    ("people", "internal operations requests: HR policy questions, onboarding plans, announcements, meeting scheduling"),
]
CODE = ("code", "CODE", "programming requests: write, explain, review or debug code or SQL, from one-liners to concurrency bugs")
LANGUAGES = ["Spanish", "French", "German", "Japanese", "Portuguese", "Italian", "Chinese"]

ASK = """Write {n} different prompts a real user might send to an AI assistant: {what}.
Spread them evenly across four difficulty levels, 1 (trivial) to 4 (expert). Vary topics, wording and length;
never number or label the prompts inside their text. {extra}
Reply with JSON only: {{"prompts": [{{"difficulty": 1, "prompt": "..."}}, ...]}}"""


async def family_prompts(family: str, hint: str, what: str, n: int, extra: str = "") -> list[dict]:
    reply = await chat("oci-judge", ASK.format(n=n, what=what, extra=extra), max_tokens=8000, json_mode=True)
    try:
        items = json.loads(reply["text"])["prompts"]
    except (KeyError, ValueError):
        match = re.search(r"\{.*\}", reply["text"], re.S)
        items = json.loads(match.group(0))["prompts"] if match else []
    return [{"family": family, "route_hint": hint, "difficulty": int(i.get("difficulty", 2)), "prompt": i["prompt"].strip()}
            for i in items if isinstance(i, dict) and i.get("prompt")]


async def add_domains() -> None:
    existing = [json.loads(line) for line in OUT.read_text().splitlines()]
    seen = {r["prompt"].lower() for r in existing}
    start = 1 + max(int(r["id"][1:]) for r in existing)
    jobs = [family_prompts(f, "MEDIUM", w, 15, extra) for f, w in DOMAINS
            for extra in ("Write as the employee or customer would.", "Make about half of them need several steps.")]
    rows = [r for batch in await asyncio.gather(*jobs) for r in batch
            if not (r["prompt"].lower() in seen or seen.add(r["prompt"].lower()))]
    with OUT.open("a") as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps({"id": f"p{start + i:04d}", **r}, ensure_ascii=False) + "\n")
    print(json.dumps({"added": len(rows), "by_family": {f: sum(r["family"] == f for r in rows) for f, _ in DOMAINS}}))


async def main() -> None:
    if "--domains" in sys.argv:
        return await add_domains()
    jobs = [family_prompts(f, h, w, 16) for f, h, w in FAMILIES]
    jobs += [family_prompts(*CODE, 24), family_prompts(*CODE, 24, "Use different languages: Python, SQL, JavaScript, Go, Java.")]
    jobs += [family_prompts(f"multilingual-{lang.lower()}", "MULTILINGUAL",
                            "everyday, business and technical requests of mixed difficulty", 8,
                            f"Write every prompt entirely in {lang}.") for lang in LANGUAGES]
    rows: list[dict] = []
    for batch in await asyncio.gather(*jobs):
        rows.extend(batch)
    seen: set[str] = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        for i, r in enumerate(r for r in rows if not (r["prompt"].lower() in seen or seen.add(r["prompt"].lower()))):
            fh.write(json.dumps({"id": f"p{i:04d}", **r}, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for line in OUT.read_text().splitlines():
        hint = json.loads(line)["route_hint"]
        counts[hint] = counts.get(hint, 0) + 1
    print(json.dumps({"prompts": sum(counts.values()), "by_route_hint": counts}))


if __name__ == "__main__":
    asyncio.run(main())
