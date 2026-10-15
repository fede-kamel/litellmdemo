#!/usr/bin/env python3
"""Figures for the LiteLLM routing deck and README.

Same visual system as the NeMo Relay and OpenShell figures: white canvas,
letter-spaced kicker, bold headline with an accent rule, flat panels with a
coloured edge, embedded brand logos, labelled connectors. Writes SVG next to
this file; `web/scripts/svg2png.mjs 2 docs/figures-src/*.svg` renders PNG.

    python3 docs/figures-src/gen.py
"""

from __future__ import annotations

import base64
import html
import os

OUT = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(OUT, "logos")
INK, SUB, MUT, LINE, PANEL, CARD = "#1F2430", "#6B7280", "#9AA1AC", "#D5D8DE", "#F7F8FA", "#FFFFFF"
GREEN = "#76B900"     # NVIDIA / OpenShell
RED = "#C74634"       # Oracle
NAVY = "#161F34"      # LangChain
SKY = "#3B8FD9"       # LangChain accent, readable on white
TEAL = "#2C7A7B"      # SQL and the relational chart
VIOLET = "#6B4FA0"    # research evidence
MOSS = "#5F7D4F"      # clinical reference
OCHRE = "#B07D1F"     # chart notes, secrets
OKG, BADR = "#2E8B57", "#C0392B"
INDIGO = "#3D3A8F"    # the LiteLLM gateway
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "SFMono-Regular, Menlo, Consolas, monospace"
ASPECT = {"openshell-lockup.png": 3.378, "nvidia.png": 3.888, "oracle.png": 4.762, "openai-mark.png": 1.0,
          "langchain.png": 4.72, "adb.png": 1.137, "genai.png": 1.084, "google.png": 2.957}


def esc(s):
    return html.escape(str(s), quote=True)


def b64(name):
    with open(os.path.join(LOGO, name), "rb") as f:
        return base64.b64encode(f.read()).decode()


class Fig:
    def __init__(self, w, h):
        self.w, self.h, self.e = w, h, []

    def logo(self, name, x, y, w):
        h = w / ASPECT[name]
        self.e.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" '
                      f'xlink:href="data:image/png;base64,{b64(name)}"/>')
        return h

    def rect(self, x, y, w, h, fill=CARD, stroke=LINE, sw=2, rx=16, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def panel(self, x, y, w, h, accent, fill=PANEL):
        self.rect(x, y, w, h, fill=fill, stroke=LINE, sw=3, rx=24)
        self.e.append(f'<rect x="{x}" y="{y}" width="14" height="{h}" rx="7" fill="{accent}"/>')

    def text(self, x, y, s, size, fill=INK, anchor="middle", weight="400", spacing=None, mono=False, italic=False):
        sp = f' letter-spacing="{spacing}"' if spacing else ""
        it = ' font-style="italic"' if italic else ""
        self.e.append(f'<text x="{x}" y="{y}" font-family="{MONO if mono else FONT}" font-size="{size}" fill="{fill}" '
                      f'text-anchor="{anchor}" font-weight="{weight}"{sp}{it}>{esc(s)}</text>')

    def card(self, x, y, w, h, title, lines=(), ts=25, tcol=INK, fill=CARD, stroke=LINE, mono_lines=False, lsize=20):
        self.rect(x, y, w, h, fill=fill, stroke=stroke)
        cy = y + (42 if lines else h / 2 + 9)
        self.text(x + w / 2, cy, title, ts, tcol, weight="700")
        for i, ln in enumerate(lines):
            self.text(x + w / 2, cy + 30 + i * 27, ln, lsize, SUB, mono=mono_lines)

    def chip(self, x, y, w, label, color, h=40, size=18, mono=True):
        self.rect(x, y, w, h, fill=CARD, stroke=color, sw=2, rx=10)
        self.text(x + w / 2, y + h / 2 + 6, label, size, color, weight="600", mono=mono)

    def badge(self, x, y, n, color=INK, r=17):
        self.e.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')
        self.text(x, y + 6, n, int(r * 1.1), "#FFFFFF", weight="700")

    def arrow(self, x1, y1, x2, y2, color=SUB, sw=3.5, dash=None, label=None, lx=None, ly=None, lcol=None, lsize=20):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" marker-end="url(#ar)"{d}/>')
        if label:
            self.text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 12,
                      label, lsize, lcol or SUB, weight="600")

    def header(self, label, title, subtitle, accent=RED, left_logo=None):
        self.logo("oracle.png", self.w - 70 - 170, 38, 170)
        if left_logo:
            self.logo(left_logo[0], 70, 40, left_logo[1])
        self.text(self.w / 2, 70, label, 24, MUT, weight="600", spacing="6")
        self.text(self.w / 2, 132, title, 46, INK, weight="700")
        self.e.append(f'<rect x="{self.w / 2 - 160}" y="156" width="320" height="7" rx="3.5" fill="{accent}"/>')
        self.text(self.w / 2, 208, subtitle, 25, SUB)

    def legend(self, y, items):
        # Lay out by label length so long and short labels sit evenly.
        widths = [40 + len(label) * 11 for _, label in items]
        gap = (self.w - 160 - sum(widths)) / max(1, len(items) - 1)
        x = 80
        for (color, label), w in zip(items, widths, strict=True):
            self.e.append(f'<circle cx="{x + 11}" cy="{y}" r="11" fill="{color}"/>')
            self.text(x + 34, y + 7, label, 21, INK, anchor="start")
            x += w + gap

    def save(self, name):
        defs = (f'<defs><marker id="ar" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" '
                f'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{SUB}"/></marker></defs>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{self.w}" '
               f'height="{self.h}" viewBox="0 0 {self.w} {self.h}" font-family="{FONT}"><rect width="{self.w}" '
               f'height="{self.h}" fill="#FFFFFF"/>{defs}' + "".join(self.e) + "</svg>")
        with open(os.path.join(OUT, name), "w") as fh:
            fh.write(svg)
        print("wrote", name)




# ===================================================== Figure 1 · the full architecture
f = Fig(2000, 1240)
f.header("FIGURE 1 · ARCHITECTURE", "One gateway between every application and every model",
         "applications ask for a model group; LiteLLM decides where the request goes and whether it may go there", accent=INDIGO)
# applications
f.panel(60, 280, 440, 760, NAVY)
f.text(290, 335, "APPLICATIONS", 22, NAVY, weight="700", spacing="4")
apps = [("langchain-oci agent", "this demo · create_oci_agent"), ("OpenAI Agents SDK", "the blog's agent example"),
        ("Codex and coding agents", "OpenAI-compatible base_url"), ("Any OpenAI client", "repoint, don't rewrite")]
for i, (t, s) in enumerate(apps):
    y = 380 + i * 150
    f.rect(100, y, 360, 120, stroke=NAVY, sw=2)
    f.text(280, y + 50, t, 22, NAVY, weight="700")
    f.text(280, y + 84, s, 17, SUB)
f.text(280, 1000, 'model="oci-auto-trained"', 18, NAVY, mono=True)
f.arrow(500, 660, 600, 660, color=NAVY, sw=4)
f.text(550, 630, "OpenAI API", 16, SUB, weight="600")
f.text(550, 700, "virtual key", 16, SUB, weight="600")
# gateway
f.panel(600, 280, 820, 760, INDIGO, fill="#F3F2FB")
f.text(1010, 335, "LITELLM AI GATEWAY", 22, INDIGO, weight="700", spacing="4")
f.text(1010, 372, "litellm --config config.yaml · one process, one endpoint", 18, SUB, mono=True)
f.text(800, 425, "ROUTING · where it goes", 19, INDIGO, weight="700")
f.text(1220, 425, "GOVERNANCE · whether and how", 19, INDIGO, weight="700")
routing = [("Classifier · auto-routers", "heuristic · LLM · our trained model"), ("Tags and teams", "premium lane · per-team groups"),
           ("Context-window check", "too long → long-context model"), ("Fallbacks · retries · cooldowns", "a failing model is skipped"),
           ("Load balancing", "latency · cost · usage · weights")]
gov = [("Virtual keys · budgets", "per team · per key · expiry"), ("Rate limits", "RPM / TPM per key and model"),
       ("Cache · guardrails", "exact or semantic · PII · prompt attacks"), ("Observability · spend", "cost per request, key, team, tag"),
       ("OCI request signing", "keys stay in the gateway")]
for col, items in ((640, routing), (1040, gov)):
    for i, (t, s) in enumerate(items):
        y = 450 + i * 112
        f.rect(col, y, 340, 96, stroke=INDIGO, sw=2)
        f.text(col + 170, y + 40, t, 19, INDIGO, weight="700")
        f.text(col + 170, y + 72, s, 15.5, SUB)
f.text(1010, 1015, "every decision returns in x-litellm-* response headers", 18, INK, weight="600")
f.arrow(1420, 660, 1500, 660, color=RED, sw=4)
f.text(1460, 630, "signed", 16, SUB, weight="600")
# OCI
f.panel(1500, 280, 440, 760, RED, fill="#FDF4F2")
f.logo("oracle.png", 1610, 300, 220)
f.text(1720, 395, "OCI Generative AI · us-chicago-1", 19, RED, weight="700")
vendors = [("OpenAI", "GPT-6-luna · 6-sol · 5.4 mini · nano · 5.1 · o3"), ("Google", "Gemini 2.5 Flash-Lite · Flash"),
           ("Meta", "Llama 4 Scout · Maverick · 3.3 70B"), ("xAI", "Grok 4.20 · Grok 4.7 · Grok 4.3"), ("Cohere", "Command A")]
for i, (v, ms) in enumerate(vendors):
    y = 430 + i * 104
    f.rect(1530, y, 380, 88, stroke=LINE, sw=2)
    f.text(1720, y + 36, v, 20, INK, weight="700")
    f.text(1720, y + 66, ms, 15, SUB)
f.text(1720, 985, "same gateway also fronts", 16, SUB)
f.text(1720, 1012, "100+ other providers", 16, SUB, weight="600")
f.panel(60, 1080, 1880, 110, INDIGO)
f.text(1000, 1130, "Applications never name a vendor model and never hold an OCI credential.", 23, INK, weight="700")
f.text(1000, 1166, "Changing a model, a route or a budget is a gateway config change, not an application release.", 19, SUB)
f.save("figure1-architecture.svg")


# ===================================================== Figure 2 · the classifier in the request path
f = Fig(2000, 1180)
f.header("FIGURE 2 · WHERE THE CLASSIFIER SITS", "Inside the gateway, before any model is called",
         "the complexity router asks a classifier for a route; the route names a model group; the group picks a deployment", accent=INDIGO)
steps = [
    ("1", "Request", NAVY, ["model: oci-auto-trained", "messages, maybe an image"]),
    ("2", "Rules", OCHRE, ["image → VISION", "very long → LONG_CONTEXT", "not English → MULTILINGUAL"]),
    ("3", "Trained ladder", RED, ["code? → CODE", "else P(good answer)", "for every route", "cheapest over the bar"]),
    ("4", "Route → group", INDIGO, ["REASONING → oci-reasoning", "MEDIUM → oci-balanced", "CODE → oci-code ..."]),
    ("5", "Deployment", TEAL, ["latency-based choice", "context-window check", "fallback if it fails"]),
    ("6", "OCI model", RED, ["signed as the OKE node", "no key in the cloud", "e.g. Grok 4.20 reasoning"]),
]
x = 70
for n, title, c, lines in steps:
    f.panel(x, 290, 290, 470, c)
    f.badge(x + 52, 340, n, c, r=20)
    f.text(x + 160, 350, title, 23, c, weight="700")
    for i, ln in enumerate(lines):
        f.rect(x + 28, 400 + i * 84, 238, 66, rx=12)
        f.text(x + 147, 440 + i * 84, ln, 15 if n == "4" else 16, INK, mono=i == 0 and n == "1")
    if x < 1600:
        f.arrow(x + 294, 525, x + 316, 525, color=MUT, sw=4)
    x += 314
f.text(1000, 820, "LiteLLM's complexity router asks our classifier, and gets back the name of a route", 23, INDIGO, weight="600")
f.panel(70, 870, 1860, 260, INDIGO)
f.text(1000, 925, "WHAT COMES BACK WITH EVERY RESPONSE", 21, INDIGO, weight="700", spacing="4")
heads = [("x-litellm-complexity-router-tier", "REASONING"), ("x-litellm-complexity-router-cause", "classifier_plugin"),
         ("x-litellm-model-name", "oci/xai.grok-4.20-reasoning"), ("x-litellm-attempted-fallbacks", "0"),
         ("x-litellm-response-cost", "0.000412"), ("x-litellm-response-duration-ms", "2140")]
for i, (k, v) in enumerate(heads):
    cx, cy = 150 + (i % 2) * 900, 970 + (i // 2) * 42
    f.text(cx, cy, k, 18, SUB, anchor="start", mono=True)
    f.text(cx + 820, cy, v, 18, INK, anchor="end", mono=True, weight="700")
f.text(1000, 1112, "the control room reads these headers to show every routing decision live", 18, SUB)
f.save("figure2-classifier-path.svg")


# ===================================================== Figure 3 · the mini-training pipeline
f = Fig(2000, 1120)
f.header("FIGURE 3 · MINI-TRAINING", "Label by outcome, train in seconds, plug into LiteLLM",
         "the router learns each route's chance of a good answer from answers a judge actually graded", accent=RED)
# the labels and the portfolio evidence, so the figure says what the files say
import json as _json  # noqa: E402
_root = os.path.join(OUT, "..", "..")
_labels = [_json.loads(x) for x in open(os.path.join(_root, "classifier", "data", "labels.jsonl"))]
_out = [r for r in _labels if r.get("label_source") == "outcome"]
_answers = sum(len(r["tiers"]) + sum(len(v["tiers"]) for v in r.get("vote_runs", [])) + bool(r.get("reasoning")) for r in _out)
_spend = sum(t["cost"] for r in _out for t in r["tiers"]) + sum(t["cost"] for r in _out for v in r.get("vote_runs", []) for t in v["tiers"]) \
    + sum(r.get("judge_cost", 0) for r in _out) + sum(r["reasoning"]["cost"] for r in _out if r.get("reasoning"))
_voted = [r for r in _out if r.get("votes")]
_stable = round(100 * sum(len(set(r["votes"])) == 1 for r in _voted) / max(1, len(_voted)))
_rp = _json.load(open(os.path.join(_root, "evidence", "model-portfolio.json")))["route_pass_rate"]
_prompts = sum(1 for _ in open(os.path.join(_root, "classifier", "data", "prompts.jsonl")))
cols = [
    ("1", "Generate", NAVY, "classifier/generate.py", [f"{_prompts} prompts", "18 task families", "+ support · billing · ops", "+ code · 7 languages"]),
    ("2", "Answer", TEAL, "classifier/label.py", ["every route answers", "every prompt, 3 runs", "reasoning route: 1 run", f"{_answers:,} real OCI answers"]),
    ("3", "Judge", OCHRE, "GPT-5.2 · anonymised", ["correctness 1–5", "completeness 1–5", "instruction-following 1–5", "pass = all ≥ 4"]),
    ("4", "Pass rates", RED, "per prompt, per route", [f"fast {_rp['SIMPLE']:.0%} · balanced {_rp['MEDIUM']:.0%}", f"strong {_rp['COMPLEX']:.0%} · reasoning {_rp['REASONING']:.0%}",
                                                        f"{_stable}% label-stable", f"about ${round(_spend)} a labelling"]),
    ("5", "Train", INDIGO, "classifier/train.py", ["e5-small embeddings", "+ difficulty signals", "4 logistic models", "+ precedent · seconds"]),
]
x = 70
for n, title, c, sub, lines in cols:
    f.panel(x, 280, 350, 560, c)
    f.badge(x + 52, 330, n, c, r=20)
    f.text(x + 190, 340, title, 26, c, weight="700")
    f.text(x + 175, 385, sub, 16, SUB, mono=True)
    for i, ln in enumerate(lines):
        f.rect(x + 30, 420 + i * 98, 290, 78, rx=12)
        f.text(x + 175, 466 + i * 98, ln, 17, INK)
    if x < 1500:
        f.arrow(x + 354, 560, x + 376, 560, color=MUT, sw=4)
    x += 375
f.panel(70, 880, 1860, 190, RED)
f.text(1000, 935, "WHAT THE LABELS SAID", 21, RED, weight="700", spacing="4")
f.text(1000, 985, f"Labelled three times, {_stable}% of prompts got the same cheapest passing route every time.", 25, INK, weight="700")
f.text(1000, 1030, "So the router predicts each route's chance of a good answer: the cheapest model is good enough for most requests, it escalates the rest.", 20, SUB)
f.save("figure3-mini-training.svg")


# ===================================================== Figure 4 · quality versus cost (from the evaluation)
import json as _json  # noqa: E402

_ev_path = os.path.join(OUT, "..", "..", "evidence", "classifier-eval.json")
if os.path.exists(_ev_path):
    ev = _json.load(open(_ev_path))
    pol = {p["policy"]: p for p in ev["policies"]}
    f = Fig(2000, 1180)
    f.header("FIGURE 4 · DOES ROUTING PAY", "Quality against cost, on the same held-out requests",
             f"{ev['held_out_difficulty']} held-out prompts; every answer a real OCI call graded by the judge", accent=RED)
    X0, X1, Y0, Y1 = 220, 1640, 980, 300
    max_cost = max(p["cost_usd"] for p in ev["policies"]) * 1.2
    f.e.append(f'<rect x="{X0}" y="{Y1}" width="{X1 - X0}" height="{Y0 - Y1}" fill="#FAFAFB" stroke="{LINE}" stroke-width="2"/>')
    for q in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        y = Y0 - (q - 0.45) / 0.6 * (Y0 - Y1)
        f.e.append(f'<line x1="{X0}" y1="{y}" x2="{X1}" y2="{y}" stroke="{LINE}" stroke-dasharray="4 6"/>')
        f.text(X0 - 20, y + 7, f"{int(q * 100)}%", 18, SUB, anchor="end")
    for c in [i * 0.2 for i in range(0, 8)]:
        if c <= max_cost:
            x = X0 + c / max_cost * (X1 - X0)
            f.text(x, Y0 + 36, f"${c:.1f}", 18, SUB)
    f.text((X0 + X1) / 2, Y0 + 80, "cost of the answers (USD)", 20, INK, weight="600")
    f.e.append(f'<text x="120" y="{(Y0 + Y1) / 2}" font-family="{FONT}" font-size="20" fill="{INK}" font-weight="600" '
               f'text-anchor="middle" transform="rotate(-90 120 {(Y0 + Y1) / 2})">answers good enough</text>')
    style = {"trained": (RED, "our ladder router"), "oracle": (OKG, "the labelled route"),
             "heuristic": (MUT, "LiteLLM heuristic"), "llm": (INDIGO, "LiteLLM LLM classifier"),
             "always SIMPLE": (SUB, "always the fast models"), "always MEDIUM": (SUB, "always the balanced models"),
             "always COMPLEX": (SUB, "always the strong models"), "always REASONING": (SUB, "always the reasoning models")}
    for name, (color, label) in style.items():
        p = pol.get(name)
        if not p:
            continue
        x = X0 + p["cost_usd"] / max_cost * (X1 - X0)
        y = Y0 - (p["quality"] - 0.45) / 0.6 * (Y0 - Y1)
        r = 22 if name == "trained" else 15
        dx, dy, anchor = {"always SIMPLE": (30, 48, "start"), "heuristic": (30, -34, "start"),
                          "always COMPLEX": (0, 100, "middle"), "oracle": (-30, -44, "end"), "always REASONING": (-30, -40, "end"),
                          "llm": (0, -40, "middle"), "always MEDIUM": (30, 44, "start"), "trained": (-34, -46, "end")}.get(name, (30, -10, "start"))
        f.e.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" opacity="0.9"/>')
        f.text(x + dx, y + dy, label, 19 if name != "trained" else 22, color, anchor=anchor, weight="700")
        f.text(x + dx, y + dy + 28, f"{int(round(p['quality'] * 100))}% · ${p['cost_usd']:.3f}", 17, SUB, anchor=anchor, mono=True)
    t, r_ = pol["trained"], pol["always REASONING"]
    f.panel(1680, 300, 260, 680, RED)
    f.text(1810, 360, "LADDER vs", 18, RED, weight="700", spacing="2")
    f.text(1810, 388, "ALWAYS REASONING", 18, RED, weight="700", spacing="2")
    f.text(1810, 480, f"{int(round((1 - t['cost_usd'] / r_['cost_usd']) * 100))}%", 64, INK, weight="700")
    f.text(1810, 520, "less spend", 19, SUB)
    f.text(1810, 640, f"{int(round((r_['quality'] - t['quality']) * 100))} pts", 54, INK, weight="700")
    f.text(1810, 676, "quality given up", 19, SUB)
    f.text(1810, 800, f"{int(round((t['quality'] - pol['heuristic']['quality']) * 100))} pts", 54, INK, weight="700")
    f.text(1810, 836, "better than the", 19, SUB)
    f.text(1810, 862, "built-in heuristic", 19, SUB)
    f.text(1000, 1130, "evidence/classifier-eval.json · classifier/evaluate.py", 18, MUT, mono=True)
    f.save("figure4-quality-cost.svg")


# ===================================================== Figure 5 · the whole demo in Oracle Cloud
f = Fig(2000, 1240)
f.header("FIGURE 5 · IN ORACLE CLOUD", "The whole demo in Oracle Cloud: OKE, one VM, an API gateway in front",
         "nothing runs on a laptop; the gateway signs as its node, so no OCI key lives anywhere in the cloud", accent=INDIGO)
# the public face
f.panel(60, 280, 320, 760, TEAL, fill="#F0F7F8")
f.text(220, 335, "PUBLIC", 22, TEAL, weight="700", spacing="4")
f.rect(95, 375, 250, 150, stroke=TEAL, sw=2)
f.text(220, 420, "A browser", 22, TEAL, weight="700")
f.text(220, 452, "anyone, anywhere", 16, SUB)
f.text(220, 478, "no login to the demo", 16, SUB)
f.text(220, 502, "the key's budget caps the spend", 15, SUB)
f.arrow(220, 525, 220, 600, color=TEAL, sw=4)
f.text(265, 568, "HTTPS 443", 15, SUB, weight="600", anchor="start")
f.rect(95, 600, 250, 390, stroke=TEAL, sw=2.5)
f.text(220, 645, "OCI API Gateway", 22, TEAL, weight="700")
f.text(220, 678, "Oracle's hostname", 16, SUB)
f.text(220, 702, "and certificate", 16, SUB)
f.text(220, 740, "<id>.apigateway.<region>", 14, INK, mono=True)
f.text(220, 762, ".oci.customer-oci.com", 14, INK, mono=True)
f.text(220, 805, "every path → the VM, :8780", 16, SUB)
f.text(220, 831, "50 requests / s per client", 16, SUB)
f.text(220, 857, "read timeout 300 s", 16, SUB)
f.text(220, 883, "closes a stream silent 15 s:", 15, OCHRE)
f.text(220, 905, "a keep-alive every 5 s", 15, OCHRE)
f.text(220, 955, "scripts/oci/edge.sh", 15, MUT, mono=True)
f.arrow(380, 700, 440, 700, color=TEAL, sw=4)
f.text(410, 672, ":8780", 15, SUB, weight="600")
f.text(410, 728, "VCN only", 13, SUB)
# the VM: the control room, OpenShell and the agent's sandbox
f.panel(440, 280, 520, 760, MOSS, fill="#F4F7F2")
f.text(700, 335, "VM · litellmdemo-control", 22, MOSS, weight="700", spacing="3")
f.text(700, 372, "A1.Flex · 2 OCPU · 12 GB · Oracle Linux 9", 15, SUB, mono=True)
f.rect(480, 410, 440, 170, stroke=MOSS, sw=2.5)
f.text(700, 452, "control room", 26, MOSS, weight="700", mono=True)
f.text(700, 490, "FastAPI + React · :8780, from the VCN only", 17, SUB)
f.text(700, 518, "a systemd user unit · reads the cluster's logs", 17, SUB)
f.text(700, 546, "with a read-only service account", 17, SUB)
f.rect(480, 605, 440, 150, stroke=MOSS, sw=2.5)
f.text(700, 648, "OpenShell gateway", 24, MOSS, weight="700")
f.text(700, 684, "rootless Podman · Landlock on · cpu cgroup delegated", 16, SUB)
f.text(700, 712, "holds the agent's LiteLLM virtual key", 17, SUB)
f.text(700, 738, "and swaps it in on the way out", 17, SUB)
f.rect(480, 780, 440, 200, stroke=GREEN, sw=2.5, dash="10 6")
f.text(700, 822, "sandbox litellmdemo-agent", 22, "#4E7A00", weight="700", mono=True)
f.text(700, 858, "the langchain-oci agent", 17, SUB)
f.text(700, 886, "no key · no OCI credential", 17, OKG, weight="700")
f.text(700, 918, "egress: POST /v1/chat/completions", 16, SUB, mono=True)
f.text(700, 942, "on the gateway, nothing else", 16, SUB)
f.text(700, 1012, "scripts/oci/control.sh · control-deploy.sh", 15, MUT, mono=True)
f.arrow(960, 560, 1020, 560, color=INDIGO, sw=4)
f.text(990, 532, ":30400", 15, SUB, weight="600")
f.text(990, 588, "VCN only", 13, SUB)
# the cluster
f.panel(1020, 280, 460, 760, INDIGO, fill="#F3F2FB")
f.text(1250, 335, "OKE BASIC CLUSTER", 22, INDIGO, weight="700", spacing="3")
f.text(1250, 372, "1 × A1.Flex · 1 OCPU · 6 GB · ns litellmdemo", 15, SUB, mono=True)
f.rect(1060, 410, 380, 290, stroke=INDIGO, sw=2.5)
f.text(1250, 452, "litellm-gateway", 26, INDIGO, weight="700", mono=True)
f.text(1250, 490, "LiteLLM 1.104.0 · node port 30400", 17, SUB)
f.text(1250, 518, "8 routes · tags · fallbacks", 17, SUB)
f.text(1250, 546, "context-window check · latency", 17, SUB)
f.text(1250, 574, "oci-auto-trained asks the classifier", 17, SUB)
f.chip(1090, 605, 320, "OCI_AUTH=instance_principal", RED, size=15)
f.chip(1090, 652, 320, "config + plugins: ConfigMap", INDIGO, size=15)
f.arrow(1250, 700, 1250, 790, color=INDIGO, sw=4)
f.text(1270, 735, "POST /classify · 3 s", 15, INDIGO, weight="600", anchor="start")
f.text(1270, 760, "down → fallback_tier", 15, OCHRE, weight="600", anchor="start")
f.rect(1060, 790, 380, 190, stroke=INDIGO, sw=2.5)
f.text(1250, 832, "route-classifier", 26, INDIGO, weight="700", mono=True)
f.text(1250, 868, "FastAPI · Service :8080", 17, SUB)
f.text(1250, 896, "rules → e5-small → 7 KB head", 17, SUB)
f.chip(1090, 918, 320, "head + code: ConfigMap", INDIGO, size=15)
f.text(1250, 1012, "stock images · init container · ConfigMaps", 15, MUT, mono=True)
f.arrow(1480, 535, 1540, 535, color=RED, sw=4)
f.text(1510, 505, "signed", 15, SUB, weight="600")
# OCI
f.panel(1540, 280, 400, 760, RED, fill="#FDF4F2")
f.logo("oracle.png", 1630, 300, 220)
f.text(1740, 400, "OCI Generative AI", 22, RED, weight="700")
f.text(1740, 430, "us-chicago-1 · 20 models", 18, SUB)
f.rect(1580, 470, 320, 180, stroke=RED, sw=2)
f.text(1740, 515, "OpenAI · Google · Meta", 19, INK, weight="600")
f.text(1740, 550, "xAI · Cohere", 19, INK, weight="600")
f.text(1740, 600, "Codex on the", 17, SUB)
f.text(1740, 625, "Responses API", 17, SUB)
f.text(1740, 710, "IAM", 22, RED, weight="700", spacing="4")
f.rect(1580, 735, 320, 245, stroke=RED, sw=2)
f.text(1740, 780, "dynamic group", 19, INK, weight="700")
f.text(1740, 810, "instances in compartment", 15, SUB, mono=True)
f.text(1740, 858, "policy", 19, INK, weight="700")
f.text(1740, 886, "use generative-ai-family", 15, SUB, mono=True)
f.text(1740, 910, "manage generative-ai-response", 15, SUB, mono=True)
f.text(1740, 934, "in compartment litellmdemo", 15, SUB, mono=True)
f.text(1740, 966, "no key · no token stored", 16, OKG, weight="700")
f.text(1000, 1130, "scripts/oci/up.sh · deploy.sh · control.sh · control-deploy.sh · edge.sh · preflight.sh · down.sh", 18, MUT, mono=True)
f.save("figure5-kubernetes.svg")

# ===================================================== Figure 6 · isolation: who holds what
f = Fig(2000, 1300)
f.header("FIGURE 6 · ISOLATION", "The agent holds nothing; LiteLLM decides, signs and accounts",
         "an OpenShell sandbox can reach one endpoint; every key lives one layer away from the code that uses it", accent=INDIGO)
# sandbox
f.panel(60, 270, 520, 760, GREEN)
f.text(320, 322, "OPENSHELL SANDBOX", 22, "#4C7A00", weight="700", spacing="4")
f.text(320, 354, "litellmdemo-agent · on the VM in OCI", 16, SUB, mono=True)
f.rect(100, 385, 440, 150, stroke="#4C7A00", sw=2)
f.text(320, 430, "the langchain-oci agent", 22, INK, weight="700")
f.text(320, 465, "create_oci_agent · tools · the control room's", 16, SUB)
f.text(320, 490, "requests, one exec each", 16, SUB)
f.text(320, 520, "LITELLM_API_KEY = placeholder", 15, "#4C7A00", mono=True, weight="600")
f.text(320, 585, "POLICY", 18, "#4C7A00", weight="700", spacing="3")
for i, (ok, line) in enumerate([(True, "POST /v1/chat/completions"), (True, "GET /v1/models"),
                                (False, "OCI Generative AI, directly"), (False, "api.openai.com"),
                                (False, "the gateway's /key/* admin API"), (False, "anything else")]):
    y = 615 + i * 52
    f.rect(100, y, 440, 42, stroke=OKG if ok else BADR, sw=1.5, rx=10)
    f.text(130, y + 28, "✓" if ok else "✕", 20, OKG if ok else BADR, weight="700")
    f.text(165, y + 28, line, 16, INK, anchor="start", mono=ok)
f.text(320, 960, "the OpenShell gateway holds the real key", 16, SUB, weight="600")
f.text(320, 985, "and swaps it in on the way out", 16, SUB, weight="600")
f.arrow(580, 520, 680, 520, color=INDIGO, sw=4)
f.text(630, 490, "the agent's", 15, SUB, weight="600")
f.text(630, 560, "virtual key", 15, SUB, weight="600")
# LiteLLM on OKE
f.panel(680, 270, 820, 760, INDIGO, fill="#F3F2FB")
f.text(1090, 322, "LITELLM AI GATEWAY · KUBERNETES", 22, INDIGO, weight="700", spacing="3")
f.text(1090, 354, "official image ghcr.io/berriai/litellm-database:v1.104.0", 16, SUB, mono=True)
steps6 = [("1", "Key check", "virtual key openshell-agent: 5 model groups, $5 / 30 days, 120 rpm (Postgres)"),
          ("2", "Classify", "complexity router → classifier_type: custom → route-classifier (the ladder)"),
          ("3", "Route", "route → model group → fastest healthy deployment · fallbacks · retries"),
          ("4", "Sign", "OCI request signing as the OKE node (instance principal): no key, no token stored"),
          ("5", "Account", "cost per call, spend per key · x-litellm-route-decision explains the route")]
for i, (n, t, d) in enumerate(steps6):
    y = 390 + i * 118
    f.rect(720, y, 740, 100, stroke=INDIGO, sw=2)
    f.badge(762, y + 50, n, INDIGO, r=19)
    f.text(800, y + 42, t, 21, INDIGO, anchor="start", weight="700")
    f.text(800, y + 74, d, 15.5, SUB, anchor="start")
f.text(1090, 1000, "pods: litellm-gateway · route-classifier · postgres  (OKE Basic cluster, namespace litellmdemo)", 15, MUT)
f.arrow(1500, 520, 1580, 520, color=RED, sw=4)
f.text(1540, 490, "signed", 15, SUB, weight="600")
# OCI
f.panel(1580, 270, 360, 760, RED, fill="#FDF4F2")
f.logo("oracle.png", 1660, 295, 200)
f.text(1760, 390, "OCI Generative AI", 22, RED, weight="700")
f.text(1760, 420, "us-chicago-1", 17, SUB)
for i, v in enumerate(["OpenAI", "Google", "Meta", "xAI", "Cohere"]):
    f.rect(1620, 450 + i * 70, 280, 56, stroke=RED, sw=1.5, rx=10)
    f.text(1760, 485 + i * 70, v, 19, INK, weight="600")
f.text(1760, 830, "IAM: a dynamic group", 16, SUB)
f.text(1760, 856, "of the demo's instances,", 16, SUB)
f.text(1760, 882, "one policy:", 16, SUB)
f.text(1760, 910, "use generative-ai-family", 14.5, SUB, mono=True)
f.text(1760, 934, "manage generative-ai-response", 14.5, SUB, mono=True)
# who holds what
f.panel(60, 1060, 1880, 200, NAVY)
f.text(1000, 1105, "WHO HOLDS WHICH SECRET", 20, NAVY, weight="700", spacing="4")
cols6 = [("the agent, in the sandbox", "nothing: a placeholder", OKG), ("the OpenShell gateway", "the agent's LiteLLM virtual key", "#4C7A00"),
         ("LiteLLM", "its master key · Postgres: keys, budgets, spend", INDIGO), ("OCI", "the node's identity: nothing stored", RED)]
for i, (who, what, c) in enumerate(cols6):
    x = 120 + i * 455
    f.text(x + 200, 1160, who, 19, c, weight="700")
    f.text(x + 200, 1195, what, 16, SUB)
f.save("figure6-isolation.svg")


# ===================================================== Figure 7 · one request, in order
f = Fig(2000, 1500)
f.header("FIGURE 7 · SEQUENCE", "One request, from the sandbox to the model and back",
         "what LiteLLM does in between: check the key, classify, route, sign, call, fall back, account", accent=INDIGO)
lanes = [("Agent", "OpenShell sandbox", "#4C7A00"), ("OpenShell proxy", "the sandbox's egress", "#4C7A00"),
         ("LiteLLM gateway", "key check · router · hooks", INDIGO), ("Classifier service", "the ladder", VIOLET),
         ("OCI Generative AI", "us-chicago-1", RED)]
X = [180, 560, 990, 1420, 1800]
for (title, sub, c), x in zip(lanes, X):
    f.rect(x - 150, 250, 300, 86, stroke=c, sw=2.5)
    f.text(x, 287, title, 22, c, weight="700")
    f.text(x, 318, sub, 15, SUB)
    f.e.append(f'<line x1="{x}" y1="336" x2="{x}" y2="1440" stroke="{LINE}" stroke-width="2.5" stroke-dasharray="8 8"/>')

def msg(y, a, b, label, sub=None, color=SUB, dash=None):
    x1, x2 = X[a], X[b]
    f.arrow(x1 + (8 if x2 > x1 else -8), y, x2 - (10 if x2 > x1 else -10), y, color=color, sw=3, dash=dash)
    mid = (x1 + x2) / 2
    f.text(mid, y - 12, label, 17, INK if color == SUB else color, weight="600")
    if sub:
        f.text(mid, y + 26, sub, 14.5, SUB, mono=True)

def note(y, lane, label, color, w=330):
    x = X[lane]
    f.rect(x - w / 2, y - 26, w, 52, fill="#F7F8FA", stroke=color, sw=2, rx=10)
    f.text(x, y + 6, label, 15.5, color, weight="600")

msg(390, 0, 1, "POST /v1/chat/completions", "Authorization: placeholder")
note(455, 1, "policy: the one allowed endpoint", "#4C7A00")
msg(520, 1, 2, "same request, real virtual key", "Authorization: sk-… (openshell-agent)", color="#4C7A00")
note(585, 2, "1 · key check: models, budget, rpm", INDIGO)
msg(650, 2, 3, "POST /classify (complexity router plugin)", "messages, quality bar")
msg(715, 3, 2, "route + P(good answer) per route", "SIMPLE · fast 92% ≥ bar 75%", color=VIOLET, dash="8 6")
note(780, 2, "2 · route → group → deployment", INDIGO)
note(845, 2, "3 · pre-call hook: sign the request", INDIGO)
msg(910, 2, 4, "signed OCI request", "openai.gpt-6-luna · tools · max_tokens", color=RED)
msg(975, 4, 2, "error (429 / 5xx / timeout)", None, color=OCHRE, dash="8 6")
note(1040, 2, "4 · fallback: next deployment or group", OCHRE)
msg(1105, 2, 4, "signed OCI request (fallback)", "the backup group's model", color=RED)
msg(1170, 4, 2, "answer + token usage", None, color=RED, dash="8 6")
note(1235, 2, "5 · cost, spend on the key, ROUTE log line", INDIGO, w=420)
msg(1300, 2, 1, "answer + x-litellm-* headers", "tier · model · cost · route-decision", color=INDIGO, dash="8 6")
msg(1365, 1, 0, "answer (headers intact)", None, color="#4C7A00", dash="8 6")
f.text(1000, 1470, "gateway/route_headers.py · gateway/trained_classifier.py · gateway/oci_session_signer.py · sandbox/profile/litellm-gateway.yaml", 16, MUT, mono=True)
f.save("figure7-sequence.svg")


# ===================================================== Figure 8 · the Codex harness
CODEX = "#5B4BC4"     # Codex, as in the OpenShell guide's figures
f = Fig(2000, 1300)
f.header("FIGURE 8 · BUILT AND RUN BY CODEX", "You ask; Codex runs the scripts and the checks, and reports",
         "the repository carries the rules, the skills and the spec; the scripts change the cloud; the checks say when it is done", accent=CODEX)
# the operator
f.panel(60, 270, 330, 640, NAVY)
f.text(225, 322, "OPERATOR", 22, NAVY, weight="700", spacing="4")
f.text(225, 352, "plain-language requests", 16, SUB)
for i, ask in enumerate(["“Build the demo", "“Get it ready", "“Add a model", "“Is the router"]):
    tail = ["in my tenancy”", "for my talk”", "to a route”", "still good?”"][i]
    y = 380 + i * 104
    f.rect(92, y, 266, 86, stroke=NAVY, sw=2, rx=12)
    f.text(225, y + 36, ask, 18, NAVY, weight="700")
    f.text(225, y + 64, tail, 18, NAVY, weight="700")
f.rect(92, 806, 266, 84, fill="#FCF6E8", stroke=OCHRE, sw=2, rx=12)
f.text(225, 840, "keeps the OCI API key", 16, OCHRE, weight="700")
f.text(225, 868, "read by the OCI CLI, never by Codex", 13.5, SUB)
f.arrow(390, 470, 450, 470, color=NAVY, sw=4)
f.badge(420, 505, "1", NAVY, r=15)
f.text(420, 440, "asks", 16, SUB, weight="600")
# Codex and the harness
f.panel(450, 270, 520, 640, CODEX, fill="#F5F3FC")
f.logo("openai-mark.png", 492, 296, 50)
f.text(740, 330, "Codex", 30, CODEX, weight="700")
f.text(710, 362, "codex exec -s workspace-write", 15, SUB, mono=True)
harness = [("AGENTS.md", "loaded on start: the hard rules",
            ["no secret ever passes through Codex", "the cloud changes only through scripts/oci", "never change code to make a check pass"]),
           ("five skills", ".agents/skills/: one per part",
            ["demo-ops · oci-gateway · oci-routing", "route-classifier · route-verify"]),
           ("codex/SPEC.md + PROMPT*.md", "the build, as steps with checkpoints",
            ["inputs · preflight · a plan you approve", "known behaviour · the report"])]
y = 395
for title, sub, lines in harness:
    h = 74 + 25 * len(lines)
    f.rect(482, y, 456, h, stroke=CODEX, sw=2, rx=12)
    f.text(710, y + 32, title, 19, CODEX, weight="700", mono=title.startswith(("AGENTS", "codex")))
    f.text(710, y + 56, sub, 15, SUB)
    for j, ln in enumerate(lines):
        f.text(710, y + 84 + j * 25, ln, 15, INK)
    y += h + 14
f.arrow(970, 470, 1040, 470, color=CODEX, sw=4)
f.badge(1005, 505, "2", CODEX, r=15)
f.text(1005, 440, "runs", 16, SUB, weight="600")
# the scripts
f.panel(1040, 270, 440, 640, INDIGO, fill="#F3F2FB")
f.text(1260, 322, "THE SCRIPTS", 22, INDIGO, weight="700", spacing="4")
f.text(1260, 352, "idempotent · rerun after any failure", 16, SUB)
for i, (script, end) in enumerate([("scripts/oci/up.sh", "UP OK"), ("scripts/oci/deploy.sh", "DEPLOY OK"),
                                   ("scripts/oci/control.sh", "CONTROL OK"), ("scripts/oci/control-deploy.sh", "CONTROL DEPLOY OK"),
                                   ("scripts/oci/edge.sh", "EDGE OK  https://…")]):
    y = 380 + i * 102
    f.rect(1072, y, 376, 86, stroke=INDIGO, sw=2, rx=12)
    f.text(1260, y + 34, script, 16, INDIGO, weight="700", mono=True)
    f.text(1260, y + 64, end, 15, OKG, weight="700", mono=True)
f.arrow(1480, 470, 1540, 470, color=RED, sw=4)
f.badge(1510, 505, "3", RED, r=15)
f.text(1510, 440, "create", 16, SUB, weight="600")
# Oracle Cloud
f.panel(1540, 270, 400, 640, RED, fill="#FDF4F2")
f.logo("oracle.png", 1630, 292, 220)
f.text(1740, 384, "one tenancy, nothing on a laptop", 16, SUB)
for i, (t, s_) in enumerate([("OKE Basic cluster", "LiteLLM · classifier · Postgres"), ("one A1 VM", "control room · OpenShell · sandbox"),
                             ("OCI API Gateway", "the public HTTPS URL"), ("OCI Generative AI", "20 models · signed as the node")]):
    y = 410 + i * 120
    f.rect(1572, y, 336, 102, stroke=RED, sw=2, rx=12)
    f.text(1740, y + 42, t, 19, INK, weight="700")
    f.text(1740, y + 72, s_, 15, SUB)
# the checks
f.panel(60, 950, 1880, 220, TEAL, fill="#F0F7F8")
f.text(1000, 998, "THE CHECKS SAY WHEN IT IS DONE", 21, TEAL, weight="700", spacing="4")
checks = [("scripts/oci/preflight.sh", "CLOUD PREFLIGHT OK (10/10)"), ("scripts/probe_routes.py", "ROUTES OK"),
          ("scripts/e2e.py", "E2E OK"), ("web/scripts/ui-e2e.mjs", "UI E2E OK")]
for i, (c, end) in enumerate(checks):
    x = 100 + i * 370
    f.rect(x, 1030, 340, 100, stroke=TEAL, sw=2, rx=12)
    f.text(x + 170, 1072, c, 16, TEAL, weight="700", mono=True)
    f.text(x + 170, 1104, end, 15, OKG, weight="700", mono=True)
f.rect(1580, 1030, 320, 100, fill="#FFFFFF", stroke=NAVY, sw=2.5, rx=12)
f.text(1740, 1072, "the report", 19, NAVY, weight="700")
f.text(1740, 1104, "every last line · every known miss", 14.5, SUB)
f.arrow(1540, 1080, 1576, 1080, color=TEAL, sw=4)
f.arrow(640, 910, 640, 1026, color=CODEX, sw=4)
f.badge(610, 966, "4", CODEX, r=15)
f.text(660, 972, "verifies", 16, SUB, weight="600", anchor="start")
f.text(1000, 1235, "You ask. Codex runs the scripts and the checks. The keys stay where the scripts read them.", 24, INK, weight="700")
f.save("figure8-codex.svg")
