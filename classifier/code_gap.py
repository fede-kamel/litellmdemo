"""Coding requests written in business language: does the code check catch them?

    uv run python classifier/code_gap.py generate    # training rows + a separate test set (a few cents of OCI calls)
    uv run python classifier/code_gap.py score before
    uv run python classifier/code_gap.py negatives   # counter-examples: business requests that are not code
    uv run python classifier/train.py
    uv run python classifier/code_gap.py score after  # -> evidence/code-gap.json

Found in the multi-step demo: a planner wrote "Write a Python function named
calculate_sla_credit that takes outages ... and monthly_fee ..." and the code
check gave it 31%, so the step went to the balanced route instead of Codex.
Every CODE training example was worded like engineering ("a JavaScript
debounce"); none was a coding request in a business team's words.

- Training rows: GPT-5.5 writes coding requests from billing, support, finance
  and operations teams; they are labelled CODE by task type, like the other 48
  (`family: code-business`). The ladder trains on outcome-labelled rows only, so
  these change the code check and nothing else.
- Counter-examples (`negatives`): coding rows alone taught the check that
  business words plus a format mean code (31% of non-coding test requests went
  to CODE). GPT-5.5 also writes business requests that are not code; they are
  labelled MEDIUM by task type (`family: not-code-business`). With the ladder in
  place a non-CODE class only means "not code": the ladder, which ignores these
  rows, still picks the difficulty route.
- Test set, never trained on: Gemini 2.5 Pro, a different writer, writes
  business coding requests and business requests that are not code (emails,
  calculations, policies). Scored: how many coding requests go to CODE, and how
  many non-coding ones are wrongly sent there.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# the laptop's OCI profile, as scripts/gateway.sh sets it, for the direct calls below
os.environ.setdefault("OCI_CONFIG_PROFILE", json.loads((Path.home() / ".config/litellmdemo/config.json").read_text())["oci_profile"])

from classifier.robustness import direct  # noqa: E402

DATA = ROOT / "classifier" / "data"
TEST = DATA / "code-gap-test.json"
OUT = ROOT / "evidence" / "code-gap.json"
TEAMS = ["billing and invoicing", "customer support", "finance and FP&A", "IT operations and incident response",
         "sales operations", "HR and payroll", "procurement", "compliance and audit"]
LANGS = "Python, SQL, JavaScript, TypeScript, Go, Java, Bash, Excel formulas or Apps Script"


async def ask(model: str, text: str) -> list[str]:
    r = await direct(model, [{"role": "user", "content": text + ' Reply with JSON only: {"prompts": ["...", ...]}'}], max_tokens=6000)
    try:
        return [p.strip() for p in json.loads(re.search(r"\{.*\}", r["text"], re.S).group(0))["prompts"] if isinstance(p, str) and p.strip()]
    except (AttributeError, ValueError, KeyError):
        return []


def coding(team: str, n: int) -> str:
    return (f"Write {n} different requests that someone on a {team} team might send an AI assistant asking for code ({LANGS}): "
            "a function, a query, a script, a fix to their code. Word them the way that team talks, about their own business "
            "(invoices, credits, tickets, refunds, payroll, SLAs, quotas), with concrete names, fields and numbers. Vary the "
            "length and the phrasing; some name a function and its parameters, some do not.")


def not_coding(team: str, n: int) -> str:
    return (f"Write {n} different requests that someone on a {team} team might send an AI assistant that do NOT ask for code: "
            "emails, calculations with the numbers given, policy questions, summaries, plans. Use the same business vocabulary "
            "(invoices, credits, SLAs, refunds, formulas, steps) with concrete names and numbers.")


async def generate() -> None:
    train = [p for batch in await asyncio.gather(*(ask("openai.gpt-5.5", coding(t, 8)) for t in TEAMS)) for p in batch]
    pos = [p for batch in await asyncio.gather(*(ask("google.gemini-2.5-pro", coding(t, 4)) for t in TEAMS)) for p in batch]
    neg = [p for batch in await asyncio.gather(*(ask("google.gemini-2.5-pro", not_coding(t, 4)) for t in TEAMS)) for p in batch]
    TEST.write_text(json.dumps({"writer": "google.gemini-2.5-pro", "coding": pos, "not_coding": neg}, indent=1, ensure_ascii=False))
    _append(train, family="code-business", route="CODE")
    print(f"test set: {len(pos)} coding, {len(neg)} not coding -> {TEST.relative_to(ROOT)}")


async def negatives() -> None:
    neg = [p for batch in await asyncio.gather(*(ask("openai.gpt-5.5", not_coding(t, 8)) for t in TEAMS)) for p in batch]
    _append(neg, family="not-code-business", route="MEDIUM")


def _append(prompts: list[str], family: str, route: str) -> None:
    labels = DATA / "labels.jsonl"
    rows = [json.loads(line) for line in labels.read_text().splitlines()]
    seen = {r["prompt"] for r in rows}
    start = max(int(r["id"][1:]) for r in rows) + 1
    new = [{"id": f"p{start + i:04d}", "family": family, "route_hint": route, "difficulty": 2, "prompt": p,
            "route": route, "label_source": "task type", "writer": "openai.gpt-5.5"}
           for i, p in enumerate(p for p in dict.fromkeys(prompts) if p not in seen)]
    with labels.open("a") as fh:
        fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in new)
    print(f"{len(new)} {family} rows appended")


def score(tag: str) -> None:
    from classifier.router_model import RouterModel

    model, test = RouterModel(), json.loads(TEST.read_text())
    def routes(ps):
        return [model.classify([{"role": "user", "content": p}]).route for p in ps]
    pos, neg = routes(test["coding"]), routes(test["not_coding"])
    res = {"coding_to_CODE": round(pos.count("CODE") / len(pos), 3), "not_coding_to_CODE": round(neg.count("CODE") / len(neg), 3),
           "coding": len(pos), "not_coding": len(neg),
           "missed": [p for p, r in zip(test["coding"], pos, strict=True) if r != "CODE"][:10],
           "false_alarms": [p for p, r in zip(test["not_coding"], neg, strict=True) if r == "CODE"][:10]}
    rows = [json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines()]
    split = json.loads((DATA / "split.json").read_text())
    held = [r for r in rows if r["id"] in set(split["held_out"]) and r.get("family") not in ("code-business", "not-code-business") and r["route"] not in ("MULTILINGUAL", "LONG_CONTEXT", "VISION")]
    hr = routes([r["prompt"] for r in held])
    res["held_out_labels"] = {"CODE_recall": round(sum(1 for r, x in zip(held, hr, strict=True) if r["route"] == "CODE" and x == "CODE") /
                                                max(1, sum(r["route"] == "CODE" for r in held)), 3),
                              "non_CODE_to_CODE": round(sum(1 for r, x in zip(held, hr, strict=True) if r["route"] != "CODE" and x == "CODE") /
                                                     max(1, sum(r["route"] != "CODE" for r in held)), 3)}
    report = json.loads(OUT.read_text()) if OUT.exists() else {}
    report[tag] = res
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(tag, {k: v for k, v in res.items() if k not in ("missed", "false_alarms")})


if __name__ == "__main__":
    if sys.argv[1:2] == ["generate"]:
        asyncio.run(generate())
    elif sys.argv[1:2] == ["negatives"]:
        asyncio.run(negatives())
    else:
        score(sys.argv[2] if len(sys.argv) > 2 else "now")
