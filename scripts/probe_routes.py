"""Send one request per routing feature through the gateway and show what it decided.

    uv run python scripts/probe_routes.py            # gateway on 127.0.0.1:4000
    uv run python scripts/probe_routes.py --json     # one JSON line per probe

Each probe asks the gateway for a model group, never a vendor model, and
reads the route back from the x-litellm-* response headers. Ends with
"ROUTES OK (n/n)" when every probe took the route it should.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

GATEWAY = os.environ.get("LITELLM_GATEWAY", "http://127.0.0.1:4000")
KEYFILE = Path(os.environ.get("LITELLMDEMO_CONFIG", Path.home() / ".config/litellmdemo/config.json")).parent / "master_key"

LONG = " ".join(["The quarterly operations review covers capacity, incidents, spend and hiring."] * 260)

# The fast route's models, from the gateway config, so the probe follows the portfolio.
FAST_MODELS = {d["litellm_params"]["model"].replace("oci/", "")
               for d in __import__("yaml").safe_load((Path(__file__).resolve().parents[1] / "gateway" / "config.yaml").read_text())["model_list"]
               if d["model_name"] == "oci-fast"}

PROBES = [
    # name, model group, prompt, extra body, expectation(headers) -> bool, what it shows
    ("complexity: simple", "oci-auto", "What is the capital of France?", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "SIMPLE" and int(h.get("x-litellm-attempted-fallbacks") or 0) == 0
              and h.get("x-litellm-model-name", "").replace("oci/", "") in FAST_MODELS,
     "a one-line fact goes to the cheapest tier"),
    ("complexity: proof (heuristic)", "oci-auto",
     "Prove step by step that the square root of 2 is irrational, then explain why the proof generalises to every non-square integer.", {},
     lambda h: bool(h.get("x-litellm-complexity-router-tier")),
     "the built-in heuristic's tier for a proof: the baseline the trained classifier must beat"),
    ("trained: constrained planning", "oci-auto-trained",
     "Our GPU spend grew 12%, 9%, 15% and 11% over the last four quarters from $1.2M. Next year the budget is $7.5M with a "
     "hard cap of $2.1M in any quarter. Model three growth scenarios, show for each whether and when the cap binds, and "
     "recommend which workloads to defer, with the arithmetic.", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "REASONING" and h.get("x-litellm-complexity-router-cause") == "classifier_plugin",
     "a multi-constraint plan goes to REASONING (planning prompts were mostly REASONING by outcome)"),
    ("trained: code", "oci-auto-trained",
     "My Go program increments a shared counter from goroutines and the total is wrong. Explain and fix it with sync/atomic.", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "CODE",
     "a code task goes to the code route"),
    ("trained: language rule", "oci-auto-trained",
     "Hola, ¿cómo puedo fijar un límite de gasto mensual en mi cuenta?", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "MULTILINGUAL" and "cohere" in h.get("x-litellm-model-name", ""),
     "a Spanish request goes to the multilingual route by rule"),
    ("trained: image rule", "oci-auto-trained", "IMAGE", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "VISION",
     "an image in the request goes to a vision model by rule"),
    ("tag: default", "oci-chat", "Summarise the benefits of a model gateway in one sentence.", {},
     lambda h: "gemini-2.5-flash" in h.get("x-litellm-model-name", ""),
     "untagged traffic takes the default lane"),
    ("tag: premium", "oci-chat", "Summarise the benefits of a model gateway in one sentence.", {"tags": ["premium"]},
     lambda h: "gpt-5.2" in h.get("x-litellm-model-name", ""),
     "a premium-tagged request takes the premium lane"),
    ("context window fallback", "oci-compact", LONG + "\n\nIn one sentence, what does this review cover?", {},
     lambda h: h.get("x-litellm-model-group") == "oci-long",
     "a prompt too long for the window moves to a long-context model before the call"),
    ("fallback chain", "oci-flaky", "Say hello in French.", {},
     lambda h: h.get("x-litellm-model-group") == "oci-balanced" and int(h.get("x-litellm-attempted-fallbacks") or 0) >= 1,
     "a failing deployment falls back to the next group"),
    ("load balancing", "oci-vision", "Name one benefit of load balancing.", {},
     lambda h: h.get("x-litellm-model-group") == "oci-vision",
     "two vendors behind one group (OpenAI and Google); latency decides"),
]

SHOWN = ("x-litellm-model-group", "x-litellm-model-name", "x-litellm-complexity-router-tier",
         "x-litellm-complexity-router-cause", "x-litellm-attempted-fallbacks", "x-litellm-attempted-retries",
         "x-litellm-response-cost", "x-litellm-response-duration-ms")


def call(client: httpx.Client, key: str, model: str, prompt: str, extra: dict) -> tuple[int, dict, str]:
    content: str | list = prompt
    if prompt == "IMAGE":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.scenarios import invoice_image

        content = [{"type": "text", "text": "What is the total due on this invoice?"},
                   {"type": "image_url", "image_url": {"url": invoice_image()}}]
    body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 600, **extra}
    r = client.post(f"{GATEWAY}/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=180)
    text = ""
    if r.status_code == 200:
        text = (r.json()["choices"][0]["message"].get("content") or "").strip()
    else:
        text = r.text[:300]
    return r.status_code, {k.lower(): v for k, v in r.headers.items()}, text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", help="run probes whose name contains this text")
    args = ap.parse_args()
    key = KEYFILE.read_text().strip()
    ok = 0
    probes = [p for p in PROBES if not args.only or args.only in p[0]]
    with httpx.Client() as client:
        for name, model, prompt, extra, expect, shows in probes:
            t = time.time()
            status, h, text = call(client, key, model, prompt, extra)
            passed = status == 200 and expect(h)
            ok += passed
            route = {k.replace("x-litellm-", ""): h[k] for k in SHOWN if k in h}
            if args.json:
                print(json.dumps({"probe": name, "asked": model, "passed": passed, "status": status,
                                  "seconds": round(time.time() - t, 1), "route": route, "shows": shows}), flush=True)
            else:
                print(f"{'PASS' if passed else 'FAIL'}  {name:26s} asked {model:12s} -> "
                      f"{route.get('model-group', '?'):14s} {route.get('model-name', '')[:40]:40s} "
                      f"tier={route.get('complexity-router-tier', '-'):9s} fallbacks={route.get('attempted-fallbacks', '0')} "
                      f"cost=${float(route.get('response-cost') or 0):.6f}  ({time.time() - t:.1f}s)", flush=True)
                if status != 200:
                    print(f"      {text}", flush=True)
    print(f"\n{'ROUTES OK' if ok == len(probes) else 'ROUTES FAILED'} ({ok}/{len(probes)})")
    return 0 if ok == len(probes) else 1


if __name__ == "__main__":
    sys.exit(main())
