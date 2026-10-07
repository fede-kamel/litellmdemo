"""The use cases the control room runs: one per kind of request a company sends.

Every scenario is a single request to the same agent; the gateway decides the
route. `expect` is the route a well-built router should choose, shown next to
the route it actually took. `accept` widens it where the outcome labels say
two routes are both reasonable (see each scenario's `why`). Northwind Cloud is fictional; nothing here is real
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
    {"id": "support-faq", "shows": "an easy question goes to a fast, cheap model", "use_case": "Customer support", "title": "FAQ: reset a password", "expect": "SIMPLE",
     "accept": ["SIMPLE", "MEDIUM"],
     "why": "the fast models passed similar password and account requests 47% of the time; the balanced 96%",
     "prompt": "How do I reset my Northwind Cloud console password?"},
    {"id": "support-billing", "shows": "a routine reply with a policy lookup stays cheap", "use_case": "Customer support", "title": "Billing dispute", "expect": "MEDIUM",
     "accept": ["SIMPLE", "MEDIUM"],
     "why": "with the newer models the fast route passed 82% of billing requests (27 of 31 labelled SIMPLE)",
     "prompt": "I was charged twice for September on account NW-4471. Look up our refund policy and draft a short, "
               "polite reply to the customer explaining what happens next."},
    {"id": "support-escalation", "shows": "a hard, multi-part request goes to a reasoning model", "use_case": "Customer support", "title": "Escalation with SLA credits", "expect": "REASONING",
     "accept": ["MEDIUM", "REASONING"],
     "why": "the balanced models are 73% likely to pass it, the reasoning models 76%: both clear a 70% bar",
     "prompt": "Enterprise customer NW-0093 had three outages last month (2h10m, 45m, 3h30m) against a 99.9% SLA. "
               "Using our SLA policy, work out the credit, explain the calculation, and propose a remediation plan "
               "with owners and dates for the account team."},
    {"id": "agent-plan", "shows": "one job split into tasks; LiteLLM routes every task on its own", "use_case": "Multi-step agent", "title": "Escalation, end to end", "expect": "a route per step",
     "mode": "plan",
     "why": "a planner splits the job into tasks; LiteLLM routes each task on its own, so a lookup, a calculation, "
            "a reply in Spanish and a Python function can each land on a different model",
     "prompt": "Handle the escalation for enterprise customer NW-0093 end to end. They had three outages last month "
               "(2h10m, 45m, 3h30m). Look up the account and our SLA policy, work out the credit with the arithmetic, "
               "write the reply to their CTO in Spanish (she is based in Madrid), and give our billing team a Python "
               "function that computes the SLA credit from a list of outage durations and a monthly fee.",
     # 385 minutes down in a 43,776-minute month is 99.12%: below 99.9%, so 10% of $48,000
     "check": [["4,800", "4800"]]},
    {"id": "agent-incident", "shows": "an incident turned into a breach number, a SQL query, a Japanese update and a summary",
     "use_case": "Multi-step agent", "title": "Incident to customer update", "expect": "a route per step", "mode": "plan",
     "why": "four different jobs in one request: arithmetic against the policy, SQL, a customer update in Japanese, a short summary",
     "prompt": "Incident NW-INC-2291: on 2026-10-02 the Tokyo API region returned errors from 09:12 to 10:47 UTC. Using our SLA "
               "policy, work out how many minutes this went past the monthly downtime allowance. Write a SQL query against "
               "accounts(account_id, name, plan, region) that lists the Enterprise accounts in region ap-tokyo-1. Write the "
               "status update for those customers in Japanese. Finish with a three-line internal summary for the on-call channel.",
     # 09:12-10:47 is 95 minutes; the policy allows 43.8 minutes a month: 51.2 minutes over
     "check": [["51.2"]]},
    {"id": "agent-invoice", "shows": "an invoice photo read, checked against the account, answered, and turned into a billing check",
     "use_case": "Multi-step agent", "title": "Invoice photo to reply", "expect": "a route per step", "mode": "plan", "image": True,
     "why": "the step that reads the photo carries the image, so the image rule sends it to a vision model; the rest are text",
     "prompt": "This invoice photo came from Tailspin Toys, account NW-4471. Read the total due from the photo, compare it with "
               "the monthly fee on their account, and work out the difference. Then write them a short, polite reply about "
               "it, and give our billing team a Python function that flags an invoice whose total is above the account's monthly fee.",
     # the photo says $4,217.50; NW-4471's fee is $1,200.00: $3,017.50 above it
     "check": [["4,217.50", "4217.5"], ["3,017.50", "3017.5"]]},
    {"id": "agent-gpu", "shows": "a forecast, an executive summary, a plotting script and a Spanish version",
     "use_case": "Multi-step agent", "title": "GPU budget pack", "expect": "a route per step", "mode": "plan",
     "why": "planning arithmetic, short business writing, code and another language, in one job",
     "prompt": "Our GPU spend was $1.2M last quarter. Model three growth scenarios for the next four quarters, 5%, 10% and 15% "
               "a quarter, with each quarter's spend and the four-quarter total, and say whether a $2.1M quarterly cap ever "
               "binds. Then write a five-line executive summary, give the finance team a Python script that plots the three "
               "scenarios with matplotlib, and write the summary again in Spanish for the Madrid office.",
     # at 15%: 1.38 + 1.587 + 1.825 + 2.0988 = 6.89 million; the cap never binds (2.0988 < 2.1)
     "check": [["6.89", "6,890"]]},
    {"id": "code-explain", "shows": "code goes to Codex, on OCI's Responses API", "use_case": "Coding assistant", "title": "Explain a one-liner", "expect": "CODE",
     "prompt": "What does this Python do: `sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:3]`?"},
    {"id": "code-race", "shows": "a debugging task goes to Codex", "use_case": "Coding assistant", "title": "Debug a race condition", "expect": "CODE",
     "prompt": "Two workers increment a shared counter in Go with `counter++` inside goroutines and the total is "
               "sometimes wrong. Explain the race, then fix it twice: with sync.Mutex and with sync/atomic."},
    {"id": "analyst-number", "shows": "one number: the cheapest model is enough", "use_case": "Analyst", "title": "Pull one number", "expect": "SIMPLE",
     "prompt": "What is 18 percent of 4,217.50?"},
    {"id": "analyst-forecast", "shows": "planning under constraints goes to reasoning", "use_case": "Analyst", "title": "Forecast with constraints", "expect": "REASONING",
     "prompt": "Our GPU spend grew 12%, 9%, 15% and 11% over the last four quarters from $1.2M. Budget for next year "
               "is $7.5M with a hard cap of $2.1M in any quarter. Model three growth scenarios, show for each whether "
               "and when the cap binds, and recommend which workloads to defer, with the arithmetic."},
    {"id": "doc-long", "shows": "a 300-page document goes to a long-context model", "use_case": "Document analysis", "title": "300-page contract", "expect": "LONG_CONTEXT",
     "prompt": "Here is our master services agreement. What is the cap on service credits, and what is the "
               "customer's only remedy for unavailability?\n\n" + CONTRACT},
    {"id": "lang-es", "shows": "another language goes to a multilingual model", "use_case": "Multilingual service", "title": "Spanish request", "expect": "MULTILINGUAL",
     "prompt": "Hola, ¿pueden explicarme cómo funciona la facturación por uso de Northwind Cloud y cómo puedo "
               "fijar un límite de gasto mensual?"},
    {"id": "lang-ja", "shows": "Japanese, decided by a rule, not a guess", "use_case": "Multilingual service", "title": "Japanese request", "expect": "MULTILINGUAL",
     "prompt": "Northwind Cloud のサポートチケットの優先度はどのように決まりますか？簡単に教えてください。"},
    {"id": "vision-invoice", "shows": "an image goes to a vision model", "use_case": "Vision", "title": "Read an invoice photo", "expect": "VISION",
     "prompt": "Read this invoice: what is the total due and when is it due?", "image": True},
    {"id": "premium-lane", "shows": "a tag on the request picks a premium lane", "use_case": "Premium customer", "title": "Same request, premium contract", "expect": "premium lane",
     "prompt": "Summarise the benefits of an AI gateway for a CIO in three sentences.", "model": "oci-chat",
     "tags": ["premium"]},
    {"id": "chaos-fallback", "shows": "a deployment fails; LiteLLM falls back and still answers", "use_case": "Resilience", "title": "A deployment fails", "expect": "fallback",
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
