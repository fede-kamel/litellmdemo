"""The use cases the control room runs: one per kind of request a company sends.

Every scenario is a single request to the same agent; the gateway decides the
route. `expect` is the route a well-built router should choose, shown next to
the route it actually took. Northwind Cloud is fictional; nothing here is real
customer data.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache

CONTRACT = " ".join(
    f"Section {i}. The provider shall maintain service availability of 99.9 percent per calendar month, "
    f"measured at the load balancer; credits of {5 + i % 20} percent apply for each full hour below target, "
    "capped at 30 percent of the monthly fee, and are the customer's sole remedy for unavailability."
    for i in range(1, 700)
)


@lru_cache(maxsize=1)
def invoice_image() -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (520, 220), "white")
    d = ImageDraw.Draw(img)
    for y, line in enumerate(["NORTHWIND CLOUD - INVOICE NW-2026-0917", "Compute (A1 Flex)      $3,912.00",
                              "Object Storage         $  305.50", "TOTAL DUE              $4,217.50",
                              "Due date: 2026-10-31"]):
        d.text((24, 24 + y * 36), line, fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SCENARIOS = [
    {"id": "support-faq", "use_case": "Customer support", "title": "FAQ: reset a password", "expect": "SIMPLE",
     "prompt": "How do I reset my Northwind Cloud console password?"},
    {"id": "support-billing", "use_case": "Customer support", "title": "Billing dispute", "expect": "MEDIUM",
     "prompt": "I was charged twice for September on account NW-4471. Look up our refund policy and draft a short, "
               "polite reply to the customer explaining what happens next."},
    {"id": "support-escalation", "use_case": "Customer support", "title": "Escalation with SLA credits", "expect": "REASONING",
     "prompt": "Enterprise customer NW-0093 had three outages last month (2h10m, 45m, 3h30m) against a 99.9% SLA. "
               "Using our SLA policy, work out the credit, explain the calculation, and propose a remediation plan "
               "with owners and dates for the account team."},
    {"id": "code-explain", "use_case": "Coding assistant", "title": "Explain a one-liner", "expect": "CODE",
     "prompt": "What does this Python do: `sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:3]`?"},
    {"id": "code-race", "use_case": "Coding assistant", "title": "Debug a race condition", "expect": "CODE",
     "prompt": "Two workers increment a shared counter in Go with `counter++` inside goroutines and the total is "
               "sometimes wrong. Explain the race, then fix it twice: with sync.Mutex and with sync/atomic."},
    {"id": "analyst-number", "use_case": "Analyst", "title": "Pull one number", "expect": "SIMPLE",
     "prompt": "What is 18 percent of 4,217.50?"},
    {"id": "analyst-forecast", "use_case": "Analyst", "title": "Forecast with constraints", "expect": "REASONING",
     "prompt": "Our GPU spend grew 12%, 9%, 15% and 11% over the last four quarters from $1.2M. Budget for next year "
               "is $7.5M with a hard cap of $2.1M in any quarter. Model three growth scenarios, show for each whether "
               "and when the cap binds, and recommend which workloads to defer, with the arithmetic."},
    {"id": "doc-long", "use_case": "Document analysis", "title": "300-page contract", "expect": "LONG_CONTEXT",
     "prompt": "Here is our master services agreement. What is the cap on service credits, and what is the "
               "customer's only remedy for unavailability?\n\n" + CONTRACT},
    {"id": "lang-es", "use_case": "Multilingual service", "title": "Spanish request", "expect": "MULTILINGUAL",
     "prompt": "Hola, ¿pueden explicarme cómo funciona la facturación por uso de Northwind Cloud y cómo puedo "
               "fijar un límite de gasto mensual?"},
    {"id": "lang-ja", "use_case": "Multilingual service", "title": "Japanese request", "expect": "MULTILINGUAL",
     "prompt": "Northwind Cloud のサポートチケットの優先度はどのように決まりますか？簡単に教えてください。"},
    {"id": "vision-invoice", "use_case": "Vision", "title": "Read an invoice photo", "expect": "VISION",
     "prompt": "Read this invoice: what is the total due and when is it due?", "image": True},
    {"id": "premium-lane", "use_case": "Premium customer", "title": "Same request, premium contract", "expect": "premium lane",
     "prompt": "Summarise the benefits of an AI gateway for a CIO in three sentences.", "model": "oci-chat",
     "tags": ["premium"]},
    {"id": "chaos-fallback", "use_case": "Resilience", "title": "A deployment fails", "expect": "fallback",
     "prompt": "Say hello to the operations team in one sentence.", "model": "oci-flaky"},
]


def messages_for(s: dict) -> list[dict]:
    if s.get("image"):
        return [{"role": "user", "content": [{"type": "text", "text": s["prompt"]},
                                             {"type": "image_url", "image_url": {"url": invoice_image()}}]}]
    return [{"role": "user", "content": s["prompt"]}]


def summary(s: dict) -> dict:
    prompt = s["prompt"]
    return {k: v for k, v in s.items() if k != "prompt"} | {
        "prompt": prompt if len(prompt) < 600 else prompt[:400] + f" … [{len(prompt):,} characters]"}
