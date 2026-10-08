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
    ("6", "OCI model", RED, ["signed with the", "operator's session", "e.g. Grok 4.20 reasoning"]),
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
cols = [
    ("1", "Generate", NAVY, "classifier/generate.py", ["463 prompts", "18 task families", "+ support · billing · ops", "+ code · 7 languages"]),
    ("2", "Answer", TEAL, "classifier/label.py", ["every route answers", "every prompt, 3 runs", "reasoning route: 1 run", "3,590 real OCI answers"]),
    ("3", "Judge", OCHRE, "GPT-5.2 · anonymised", ["correctness 1–5", "completeness 1–5", "instruction-following 1–5", "pass = all ≥ 4"]),
    ("4", "Pass rates", RED, "per prompt, per route", ["fast 70% · balanced 76%", "strong 86% · reasoning 87%", "72% label-stable", "about $18 a labelling"]),
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
f.text(1000, 985, "Labelled three times, 72% of prompts got the same cheapest passing route every time.", 25, INK, weight="700")
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
                          "llm": (-20, 58, "middle"), "always MEDIUM": (30, 44, "start"), "trained": (-34, -46, "end")}.get(name, (30, -10, "start"))
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


# ===================================================== Figure 5 · the same gateway on Kubernetes
f = Fig(2000, 1240)
f.header("FIGURE 5 · ON KUBERNETES", "The gateway and the classifier as two services on OKE",
         "one small Ampere node; the gateway signs as the node, so no OCI key lives in the cluster", accent=INDIGO)
# laptop
f.panel(60, 280, 400, 760, NAVY)
f.text(260, 335, "OPERATOR LAPTOP", 22, NAVY, weight="700", spacing="4")
for i, (t, s) in enumerate([("Control room", "ui/server.py · web/"), ("Route probes", "scripts/probe_routes.py"),
                            ("End-to-end", "scripts/e2e.py"), ("Codex", "the four skills")]):
    y = 380 + i * 130
    f.rect(100, y, 320, 104, stroke=NAVY, sw=2)
    f.text(260, y + 44, t, 22, NAVY, weight="700")
    f.text(260, y + 76, s, 16, SUB, mono=True)
f.text(260, 935, "LITELLM_GATEWAY=", 17, NAVY, mono=True)
f.text(260, 962, "http://127.0.0.1:4100", 17, NAVY, mono=True)
f.arrow(460, 560, 600, 560, color=NAVY, sw=4)
f.text(530, 530, "port-forward", 16, SUB, weight="600")
f.text(530, 600, "API on 6443,", 15, SUB)
f.text(530, 622, "allowlisted", 15, SUB)
# cluster
f.panel(600, 280, 840, 760, INDIGO, fill="#F3F2FB")
f.text(1020, 335, "OKE BASIC CLUSTER · ca-toronto-1", 22, INDIGO, weight="700", spacing="3")
f.text(1020, 372, "1 × VM.Standard.A1.Flex · 1 OCPU · 6 GB · arm64 · namespace litellmdemo", 17, SUB, mono=True)
f.rect(650, 410, 740, 250, stroke=INDIGO, sw=2.5)
f.text(1020, 455, "litellm-gateway", 26, INDIGO, weight="700", mono=True)
f.text(1020, 495, "LiteLLM 1.104.0 proxy · Service :4000", 19, SUB)
f.text(1020, 530, "8 routes · tags · fallbacks · context-window check · latency", 18, SUB)
f.text(1020, 565, "oci-auto-trained asks the classifier service", 18, SUB)
f.chip(700, 595, 300, "OCI_AUTH=instance_principal", RED, size=16)
f.chip(1040, 595, 300, "config + plugins: ConfigMap", INDIGO, size=16)
f.arrow(1020, 660, 1020, 760, color=INDIGO, sw=4)
f.text(1250, 705, "POST /classify · 3 s budget", 17, INDIGO, weight="600")
f.text(1250, 732, "down or slow → fallback_tier MEDIUM", 17, OCHRE, weight="600")
f.rect(650, 760, 740, 220, stroke=INDIGO, sw=2.5)
f.text(1020, 805, "route-classifier", 26, INDIGO, weight="700", mono=True)
f.text(1020, 845, "FastAPI · Service :8080 · ready only when the encoder is loaded", 18, SUB)
f.text(1020, 880, "rules → multilingual-e5-small → 7 KB logistic head", 18, SUB)
f.chip(700, 910, 300, "readiness: /healthz", INDIGO, size=16)
f.chip(1040, 910, 300, "head + code: ConfigMap", INDIGO, size=16)
f.text(1020, 1015, "stock python:3.12-slim · packages installed by an init container · non-root", 16, MUT)
f.arrow(1440, 535, 1520, 535, color=RED, sw=4)
f.text(1480, 505, "signed", 16, SUB, weight="600")
# OCI
f.panel(1520, 280, 420, 760, RED, fill="#FDF4F2")
f.logo("oracle.png", 1620, 300, 220)
f.text(1730, 400, "OCI Generative AI", 22, RED, weight="700")
f.text(1730, 430, "us-chicago-1 · 20 models", 18, SUB)
f.rect(1560, 470, 340, 180, stroke=RED, sw=2)
f.text(1730, 515, "OpenAI · Google · Meta", 19, INK, weight="600")
f.text(1730, 550, "xAI · Cohere", 19, INK, weight="600")
f.text(1730, 600, "the same deployments", 17, SUB)
f.text(1730, 625, "as the laptop gateway", 17, SUB)
f.text(1730, 710, "IAM", 22, RED, weight="700", spacing="4")
f.rect(1560, 735, 340, 245, stroke=RED, sw=2)
f.text(1730, 780, "dynamic group", 19, INK, weight="700")
f.text(1730, 810, "instances in compartment", 16, SUB, mono=True)
f.text(1730, 870, "policy", 19, INK, weight="700")
f.text(1730, 900, "use generative-ai-family", 16, SUB, mono=True)
f.text(1730, 925, "in compartment litellmdemo", 16, SUB, mono=True)
f.text(1730, 962, "no key · no token stored", 16, OKG, weight="700")
f.text(1000, 1130, "scripts/oci/up.sh · scripts/oci/deploy.sh · deploy/k8s/litellmdemo.yaml · scripts/oci/down.sh", 18, MUT, mono=True)
f.save("figure5-kubernetes.svg")


# ===================================================== Figure 6 · isolation: who holds what
f = Fig(2000, 1300)
f.header("FIGURE 6 · ISOLATION", "The agent holds nothing; LiteLLM decides, signs and accounts",
         "an OpenShell sandbox can reach one endpoint; every key lives one layer away from the code that uses it", accent=INDIGO)
# sandbox
f.panel(60, 270, 520, 760, GREEN)
f.text(320, 322, "OPENSHELL SANDBOX", 22, "#4C7A00", weight="700", spacing="4")
f.text(320, 354, "litellmdemo-agent · on the operator's laptop", 16, SUB, mono=True)
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
          ("4", "Sign", "OCI request signing: on OKE as the node (instance principal); on the laptop with the OCI session"),
          ("5", "Account", "cost per call, spend per key · x-litellm-route-decision explains the route")]
for i, (n, t, d) in enumerate(steps6):
    y = 390 + i * 118
    f.rect(720, y, 740, 100, stroke=INDIGO, sw=2)
    f.badge(762, y + 50, n, INDIGO, r=19)
    f.text(800, y + 42, t, 21, INDIGO, anchor="start", weight="700")
    f.text(800, y + 74, d, 15.5, SUB, anchor="start")
f.text(1090, 1000, "pods: litellm-gateway · route-classifier · postgres  (OKE, or Rancher Desktop on the laptop)", 15, MUT)
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
f.text(1760, 840, "IAM: a dynamic group", 16, SUB)
f.text(1760, 866, "of the demo's nodes,", 16, SUB)
f.text(1760, 892, "one policy:", 16, SUB)
f.text(1760, 920, "use generative-ai-family", 15, SUB, mono=True)
# who holds what
f.panel(60, 1060, 1880, 200, NAVY)
f.text(1000, 1105, "WHO HOLDS WHICH SECRET", 20, NAVY, weight="700", spacing="4")
cols6 = [("the agent, in the sandbox", "nothing: a placeholder", OKG), ("the OpenShell gateway", "the agent's LiteLLM virtual key", "#4C7A00"),
         ("LiteLLM", "its master key · Postgres: keys, budgets, spend", INDIGO), ("OCI", "OKE: the node's identity · laptop: a 1-hour session", RED)]
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
