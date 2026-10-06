"""The model portfolio as deployed: every model, its route and role, its price and the price's source,
and the route's measured pass rate. Read by the deck and the README.

    uv run python scripts/portfolio.py      # -> evidence/model-portfolio.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROUTE_OF_GROUP = {}


def main() -> None:
    text = (ROOT / "gateway" / "config.yaml").read_text()
    cfg = yaml.safe_load(text)
    tiers = next(d for d in cfg["model_list"] if d["model_name"] == "oci-auto-trained")["litellm_params"]["complexity_router_config"]["tiers"]
    fallbacks = {k: v for f in cfg["router_settings"]["fallbacks"] for k, v in f.items()}
    for route, group in tiers.items():
        ROUTE_OF_GROUP[group] = (route, "primary")
        for b in fallbacks.get(group, []):
            ROUTE_OF_GROUP.setdefault(b, (route, "backup"))
    ROUTE_OF_GROUP.update({"oci-chat": ("tag lane", "default / premium"), "oci-compact": ("context-window demo", "primary"),
                           "oci-classifier-llm": ("LLM classifier", "LiteLLM's oci-auto-llm"), "oci-judge": ("judge", "labels and grades")})
    trial = json.loads((ROOT / "evidence" / "model-trial.json").read_text())
    trial_rate = {e["model"]: e["pass_rate"] for entries in trial["routes"].values() for e in entries}
    labels = [json.loads(line) for line in (ROOT / "classifier/data/labels.jsonl").read_text().splitlines()]
    outcome = [r for r in labels if r.get("label_source") == "outcome"]
    route_rate = {t: float(np.mean([next(x for x in r["tiers"] if x["tier"] == t)["pass_rate"] for r in outcome]))
                  for t in ("SIMPLE", "MEDIUM", "COMPLEX")}
    route_rate["REASONING"] = float(np.mean([r["reasoning"]["passed"] for r in outcome]))
    lines = text.splitlines()
    rows: dict[str, dict] = {}
    for d in cfg["model_list"]:
        m = d["litellm_params"]["model"]
        if m.startswith("auto_router") or "retired" in m or d["model_name"] not in ROUTE_OF_GROUP:
            continue
        route, role = ROUTE_OF_GROUP[d["model_name"]]
        mi = d.get("model_info") or {}
        name = m.replace("oci/", "")
        src = next((ln for ln in lines if re.search(rf"model: oci/{re.escape(name)}[,}}\s]", ln)), "")
        nxt = lines[lines.index(src) + 1] if src in lines else ""
        oci = re.search(r"OCI (B\d+/B\d+)", src + nxt)
        anchor = re.search(r"model_info: \*(\w+)", nxt)
        if not oci and anchor and anchor.group(1) in ("gemini_flash", "gemini_lite"):
            oci = re.search(r"OCI (B\d+/B\d+)", next(ln for ln in lines if f"&{anchor.group(1)}" in ln))
        price = (mi.get("input_cost_per_token"), mi.get("output_cost_per_token"))
        if price[0] is None:
            import litellm

            e = litellm.model_cost.get(m, {})
            price = (e.get("input_cost_per_token"), e.get("output_cost_per_token"))
            source = ("LiteLLM model map; OCI bills per character, the per-token conversion is unverified"
                      if "meta." in name or "cohere." in name else "LiteLLM model map")
        else:
            source = f"OCI price list {oci.group(1)}" if oci else "vendor list price (OCI publishes none)"
        r = rows.setdefault(name, {"model": name, "uses": [], "price_per_1m": [round((price[0] or 0) * 1e6, 3), round((price[1] or 0) * 1e6, 3)],
                                   "price_source": source, "trial_pass_rate": trial_rate.get(name)})
        r["uses"].append({"route": route, "role": role, "group": d["model_name"], "route_pass_rate": route_rate.get(route)})
    out = {"models": len(rows), "route_pass_rate": {k: round(v, 3) for k, v in route_rate.items()}, "rows": list(rows.values())}
    (ROOT / "evidence" / "model-portfolio.json").write_text(json.dumps(out, indent=1))
    for r in rows.values():
        print(f"{r['model']:44} ${r['price_per_1m'][0]:6.3f}/${r['price_per_1m'][1]:6.2f}  {r['price_source'][:34]:34}  "
              + "; ".join(f"{u['route']} {u['role']}" for u in r["uses"]))
    print(out["models"], "models;", out["route_pass_rate"])


if __name__ == "__main__":
    main()
