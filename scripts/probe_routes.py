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

PROBES = [
    # name, model group, prompt, extra body, expectation(headers) -> bool, what it shows
    ("complexity: simple", "oci-auto", "What is the capital of France?", {},
     lambda h: h.get("x-litellm-complexity-router-tier") == "SIMPLE" and "flash-lite" in h.get("x-litellm-model-name", ""),
     "a one-line fact goes to the cheapest tier"),
    ("complexity: proof (heuristic)", "oci-auto",
     "Prove step by step that the square root of 2 is irrational, then explain why the proof generalises to every non-square integer.", {},
     lambda h: bool(h.get("x-litellm-complexity-router-tier")),
     "the built-in heuristic's tier for a proof: the baseline the trained classifier must beat"),
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
    ("load balancing", "oci-balanced", "Name one benefit of load balancing.", {},
     lambda h: h.get("x-litellm-model-group") == "oci-balanced",
     "two vendors behind one group; latency decides"),
]

SHOWN = ("x-litellm-model-group", "x-litellm-model-name", "x-litellm-complexity-router-tier",
         "x-litellm-complexity-router-cause", "x-litellm-attempted-fallbacks", "x-litellm-attempted-retries",
         "x-litellm-response-cost", "x-litellm-response-duration-ms")


def call(client: httpx.Client, key: str, model: str, prompt: str, extra: dict) -> tuple[int, dict, str]:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 600, **extra}
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
