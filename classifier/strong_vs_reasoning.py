"""Two demo prompts the router sends to the strong route: answer each N times on the strong and the
reasoning routes, and grade every answer the way evaluate.py does (same judge, same pass rule).

    uv run python classifier/strong_vs_reasoning.py evidence/strong-vs-reasoning.json
"""
import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classifier.gateway_client import chat  # noqa: E402
from classifier.label import CRITERIA, PASS, parse  # noqa: E402
from classifier.evaluate import SINGLE  # noqa: E402
from app.scenarios import SCENARIOS  # noqa: E402
from app.tools import POLICIES  # noqa: E402

N = 4
by_id = {s["id"]: s for s in SCENARIOS}
prompts = {
    "analyst-forecast": by_id["analyst-forecast"]["prompt"],
    # the agent reads the SLA policy with a tool; give it to both routes in the prompt
    "support-escalation": by_id["support-escalation"]["prompt"] + "\n\nOur SLA policy: " + POLICIES["sla"],
}
sem = asyncio.Semaphore(6)

async def one(pid, group, i):
    async with sem:
        a = await chat(group, prompts[pid], max_tokens=6000)
        v = await chat("oci-judge", SINGLE.format(prompt=prompts[pid], answer=a["text"][:8000]), max_tokens=800, json_mode=True) if a["ok"] else {"ok": False}
    g = parse(v["text"]) if v.get("ok") else {}
    s = {c: int(g.get(c, 0) or 0) for c in CRITERIA}
    return {"prompt": pid, "group": group, "run": i, "deployment": a["headers"].get("x-litellm-model-name"),
            "cost": float(a["headers"].get("x-litellm-response-cost") or 0), "scores": s,
            "passed": a["ok"] and min(s.values()) >= PASS}

async def main():
    rows = await asyncio.gather(*(one(p, g, i) for p in prompts for g in ("oci-strong", "oci-reasoning") for i in range(N)))
    out = {"n": N, "judge": "oci-judge", "pass": f"every criterion >= {PASS}", "rows": rows, "summary": {}}
    for p in prompts:
        for g in ("oci-strong", "oci-reasoning"):
            r = [x for x in rows if x["prompt"] == p and x["group"] == g]
            out["summary"][f"{p} {g}"] = {"passed": sum(x["passed"] for x in r), "of": len(r), "cost": round(sum(x["cost"] for x in r) / len(r), 5)}
    print(json.dumps(out["summary"], indent=1))
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))

asyncio.run(main())
