"""Does the router hold up on prompts nobody trained on, graded by a judge from another vendor?

    uv run python classifier/robustness.py      # -> evidence/robustness.json   (about $12-15 of OCI calls)

1. Fresh prompts: GPT-5.5, a model the router never routes to, writes 150 new
   requests across the task families and business domains, trivial to expert.
2. Every route answers every prompt once (fast, balanced, strong, reasoning).
3. Two judges grade every answer on the labelling contract (correctness,
   completeness, instruction-following; pass = all at least 4): GPT-5.2, the
   training judge, and Gemini 2.5 Pro, from another vendor and not in the
   portfolio. Their agreement is reported.
4. Policies are scored under each judge: always each route, perfect routing,
   our ladder (decided locally by the shipped model), and LiteLLM's heuristic
   and LLM classifier (their route read from the gateway's headers).
5. Code: 20 coding tasks answered by GPT-5.3-codex (the CODE route), GPT-5.1
   and GPT-6-luna, judged the same way. Vision: images with an exact answer,
   read by the vision route's models.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import random
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gateway"))

from classifier.evaluate import SINGLE  # noqa: E402
from classifier.gateway_client import chat  # noqa: E402
from classifier.label import CRITERIA, PASS, parse  # noqa: E402

OUT = ROOT / "evidence" / "robustness.json"
ROUTES = {"SIMPLE": "oci-fast", "MEDIUM": "oci-balanced", "COMPLEX": "oci-strong", "REASONING": "oci-reasoning"}
WRITER, JUDGES = "openai.gpt-5.5", {"gpt-5.2": "oci-judge", "gemini-2.5-pro": "oci/google.gemini-2.5-pro"}
FAMILIES = ["short factual questions", "rewriting or formatting a given text", "explaining a concept for an audience",
            "summarising a given paragraph (include it)", "business emails for a stated situation", "multi-part analysis with trade-offs",
            "comparing options against criteria", "math word problems up to olympiad level", "logic puzzles", "planning under hard constraints",
            "multi-step finance or estimation problems", "customer support questions for a cloud provider", "billing disputes and refunds",
            "IT incident triage and runbooks", "finance requests with the numbers given"]
_cfg = json.loads((Path.home() / ".config/litellmdemo/config.json").read_text())
_gate = asyncio.Semaphore(int(os.environ.get("LITELLMDEMO_CONCURRENCY", "16")))


async def direct(model: str, messages, max_tokens=4000) -> dict:
    """Call an OCI model directly through LiteLLM's OCI provider (the writer and the second judge)."""
    import litellm
    from oci_session_signer import handler

    async with _gate:
        try:
            r = await litellm.acompletion(model=model if model.startswith("oci/") else f"oci/{model}", messages=messages,
                                          max_tokens=max_tokens, oci_signer=handler.signer(), oci_region=_cfg["oci_region"],
                                          oci_compartment_id=_cfg["oci_compartment_id"], timeout=300, drop_params=True)
            return {"ok": True, "text": r.choices[0].message.content or ""}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "text": f"(error: {type(exc).__name__})"}


async def judge(name: str, prompt: str, answer: str) -> bool:
    text = SINGLE.format(prompt=prompt, answer=answer[:8000])
    group = JUDGES[name]
    r = await (chat(group, text, max_tokens=800, json_mode=True) if not group.startswith("oci/")
               else direct(group, [{"role": "user", "content": text}], max_tokens=2000))
    g = parse(r["text"]) if r["ok"] else {}
    return min(int(g.get(c, 0) or 0) for c in CRITERIA) >= PASS


async def fresh_prompts(n: int) -> list[str]:
    async def one(family: str) -> list[str]:
        ask = (f"Write 10 different requests a real user might send to an AI assistant: {family}. Spread them from trivial to expert. "
               "Make them unlike textbook examples: concrete, specific, with their own details. Never number them inside the text. "
               'Reply with JSON only: {"prompts": ["...", ...]}')
        r = await direct(WRITER, [{"role": "user", "content": ask}], max_tokens=6000)
        try:
            return [p for p in json.loads(re.search(r"\{.*\}", r["text"], re.S).group(0))["prompts"] if isinstance(p, str)]
        except (AttributeError, ValueError, KeyError):
            return []
    out = [p for batch in await asyncio.gather(*(one(f) for f in FAMILIES)) for p in batch]
    random.Random(5).shuffle(out)
    return out[:n]


async def route_of(group: str, prompt: str) -> str | None:
    r = await chat(group, prompt, max_tokens=16)
    return (r["headers"].get("x-litellm-complexity-router-tier") or "").upper() or None


def invoice(total: str, due: str, lines: list[tuple[str, str]]) -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (560, 70 + 34 * (len(lines) + 2)), "white")
    d = ImageDraw.Draw(img)
    d.text((24, 20), "NORTHWIND CLOUD - INVOICE", fill="black")
    for i, (k, v) in enumerate(lines + [("TOTAL DUE", total), ("Due date", due)]):
        d.text((24, 56 + 34 * i), f"{k:<28}{v}", fill="black")
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def main() -> None:
    from classifier.router_model import shared

    report: dict = {}
    # --- 1-4: fresh prompts, every route, two judges --------------------------------
    prompts = await fresh_prompts(150)
    print(f"{len(prompts)} fresh prompts", flush=True)
    answers = {r: await asyncio.gather(*(chat(g, p, max_tokens=4000) for p in prompts)) for r, g in ROUTES.items()}
    print("answered", flush=True)
    passed = {j: {r: await asyncio.gather(*(judge(j, p, a["text"]) if a["ok"] else asyncio.sleep(0, False)
                                            for p, a in zip(prompts, answers[r], strict=True)))
                  for r in ROUTES} for j in JUDGES}
    print("judged", flush=True)
    cost = {r: [float(a["headers"].get("x-litellm-response-cost") or 0) for a in answers[r]] for r in ROUTES}
    ours = [shared().classify([{"role": "user", "content": p}]).route for p in prompts]
    heur = await asyncio.gather(*(route_of("oci-auto", p) for p in prompts))
    llm = await asyncio.gather(*(route_of("oci-auto-llm", p) for p in prompts))

    def score(choice: list[str], j: str) -> tuple[float, float]:
        pick = [c if c in ROUTES else "MEDIUM" for c in choice]     # a code/language route on a difficulty prompt: price it as MEDIUM
        return (float(np.mean([passed[j][c][i] for i, c in enumerate(pick)])), float(sum(cost[c][i] for i, c in enumerate(pick))))

    policies = {f"always {r}": [r] * len(prompts) for r in ROUTES}
    policies |= {"ladder (ours)": ours, "LiteLLM heuristic": [h or "MEDIUM" for h in heur], "LiteLLM LLM classifier": [x or "MEDIUM" for x in llm]}
    table = {}
    for j in JUDGES:
        best = [min((r for r in ROUTES if passed[j][r][i]), key=lambda r: cost[r][i], default="REASONING") for i in range(len(prompts))]
        table[j] = {name: dict(zip(("quality", "cost_usd"), (round(v, 4) for v in score(ch, j)))) for name, ch in {**policies, "oracle": best}.items()}
    agree = float(np.mean([passed["gpt-5.2"][r][i] == passed["gemini-2.5-pro"][r][i] for r in ROUTES for i in range(len(prompts))]))
    report["fresh"] = {"prompts": len(prompts), "writer": WRITER, "judges": list(JUDGES), "judge_agreement": round(agree, 3),
                       "policies_by_judge": table, "ladder_mix": {r: round(ours.count(r) / len(ours), 3) for r in set(ours)}}
    for j in JUDGES:
        print(f"\njudge {j}"); [print(f"  {k:26} {v['quality']:6.1%}  ${v['cost_usd']:.3f}") for k, v in table[j].items()]
    print(f"\njudges agree on {agree:.0%} of answers", flush=True)

    # --- 5a: code quality -----------------------------------------------------------
    labels = [json.loads(line) for line in (ROOT / "classifier/data/labels.jsonl").read_text().splitlines()]
    code = random.Random(9).sample([r["prompt"] for r in labels if r["route"] == "CODE"], 20)
    coders = {"GPT-5.3-codex (CODE route)": "oci-code", "GPT-5.1": "oci/openai.gpt-5.1", "GPT-6-luna": "oci/openai.gpt-6-luna"}
    code_out = {}
    for name, target in coders.items():
        ans = await asyncio.gather(*((chat(target, p, max_tokens=4000) if not target.startswith("oci/")
                                      else direct(target, [{"role": "user", "content": p}])) for p in code))
        ok = await asyncio.gather(*(judge("gpt-5.2", p, a["text"]) if a["ok"] else asyncio.sleep(0, False) for p, a in zip(code, ans, strict=True)))
        ok2 = await asyncio.gather(*(judge("gemini-2.5-pro", p, a["text"]) if a["ok"] else asyncio.sleep(0, False) for p, a in zip(code, ans, strict=True)))
        code_out[name] = {"gpt-5.2": round(float(np.mean(ok)), 3), "gemini-2.5-pro": round(float(np.mean(ok2)), 3)}
    report["code"] = {"tasks": len(code), "pass_rate": code_out}
    print("\ncode:", json.dumps(code_out), flush=True)

    # --- 5b: vision with exact answers -------------------------------------------------
    rng = random.Random(3)
    cases = []
    for _ in range(8):
        items = [(f"Service {k}", f"${rng.randint(100, 9999):,}.{rng.randint(0, 99):02d}") for k in "ABC"[: rng.randint(2, 3)]]
        total = f"${sum(float(v[1:].replace(',', '')) for _, v in items):,.2f}"
        due = f"2026-{rng.randint(1, 12):02d}-{rng.randint(10, 28)}"
        cases.append((invoice(total, due, items), total, due))
    viewers = {"GPT-6-luna": "oci/openai.gpt-6-luna", "Gemini 2.5 Flash": "oci/google.gemini-2.5-flash",
               "Llama 4 Maverick": "oci/meta.llama-4-maverick-17b-128e-instruct-fp8"}
    vision = {}
    for name, m in viewers.items():
        ans = await asyncio.gather(*(direct(m, [{"role": "user", "content": [
            {"type": "text", "text": "Read this invoice. Reply exactly as: TOTAL=<amount>; DUE=<date>"},
            {"type": "image_url", "image_url": {"url": img}}]}], max_tokens=1500) for img, _, _ in cases))
        vision[name] = round(float(np.mean([(t.replace(",", "") in a["text"].replace(",", "")) and (d in a["text"])
                                            for a, (_, t, d) in zip(ans, cases, strict=True)])), 3)
    report["vision"] = {"images": len(cases), "exact_answer_rate": vision}
    print("vision:", json.dumps(vision), flush=True)
    OUT.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
