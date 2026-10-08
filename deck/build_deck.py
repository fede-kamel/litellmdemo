"""Build the LiteLLM routing deck on the Oracle FY26 corporate template.

The template (masters, layouts, theme) comes from an Oracle FY26 deck passed as
--template; every existing slide is dropped and the slides below are built on
its "Title/Cover_5" and "Light - Blank" layouts with the same type system: an
Oracle Sans kicker in Oracle red, a 30 pt title, a short red rule, and the
copyright footer. The classifier's numbers are read from classifier/model/meta.json
and evidence/classifier-eval.json, so the slides carry the numbers in the repo.

    uv run --with python-pptx python deck/build_deck.py \
        --template ~/Desktop/litellm/LiteLLM-OCI-PPO-FY26.pptx \
        --out ~/Documents/LiteLLM-OCI-Routing-FY26.pptx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
LOGOS = ROOT / "docs" / "figures-src" / "logos"
EVIDENCE = ROOT / "evidence"
SHOTS = ROOT / "docs" / "screenshots"
INDIGO = RGBColor(0x3D, 0x3A, 0x8F)

RED = RGBColor(0xC7, 0x46, 0x34)
INK = RGBColor(0x2A, 0x2F, 0x2F)
BODY = RGBColor(0x57, 0x5C, 0x5C)
MUTED = RGBColor(0x8A, 0x8F, 0x8F)
TEAL = RGBColor(0x04, 0x53, 0x6F)
SAND = RGBColor(0xF4, 0xF2, 0xF0)
SAND_LINE = RGBColor(0xE2, 0xDF, 0xDB)
CARD_LINE = RGBColor(0xE6, 0xE2, 0xDE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x5F, 0x7D, 0x4F)
OCHRE = RGBColor(0xB0, 0x7D, 0x1F)
VIOLET = RGBColor(0x6B, 0x4F, 0xA0)
YELLOW = RGBColor(0xF0, 0xCC, 0x71)
FONT = "Oracle Sans"
MONO = "Consolas"
FOOTER = "Copyright © 2026, Oracle and/or its affiliates   —   Personal open-source work; Northwind Cloud is fictional"


# ------------------------------------------------------------------ helpers --

def drop_all_slides(prs: Presentation) -> None:
    ids = prs.slides._sldIdLst
    for sid in list(ids):
        prs.part.drop_rel(sid.rId)
        ids.remove(sid)


def layout(prs, name):
    return next(lay for lay in prs.slide_layouts if lay.name == name)


def text(slide, x, y, w, h, runs, size=14, color=BODY, bold=False, align=PP_ALIGN.LEFT, font=FONT,
         anchor=MSO_ANCHOR.TOP, spacing=None, line=1.12):
    """runs: str, or list of paragraphs; a paragraph is a str or a list of (text, overrides) tuples."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paragraphs = [runs] if isinstance(runs, str) else runs
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        parts = [(para, {})] if isinstance(para, str) else para
        for chunk, o in parts:
            r = p.add_run()
            r.text = chunk
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = o.get("color", color)
            if spacing or o.get("spacing"):
                r._r.get_or_add_rPr().set("spc", str(o.get("spacing", spacing)))
        if isinstance(para, list) and para and para[0][1].get("space_after") is not None:
            p.space_after = Pt(para[0][1]["space_after"])
    return box


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(0.75)
    s.shadow.inherit = False
    return s


def header(slide, kicker, title):
    text(slide, 0.72, 0.46, 11.9, 0.3, kicker.upper(), size=11.5, color=RED, bold=True, spacing=180)
    text(slide, 0.72, 0.78, 11.9, 1.0, title, size=30, color=INK, bold=True)
    rect(slide, 0.72, 1.40, 1.15, 0.06, RED)
    text(slide, 0.72, 7.06, 11.9, 0.3, FOOTER, size=8, color=MUTED)


def bullets(slide, x, y, w, h, items, size=14.5):
    paras = []
    for lead, rest in items:
        paras.append([("▪  ", {"color": RED, "bold": True, "size": size}), (lead + " ", {"bold": True, "color": INK, "size": size}),
                      (rest, {"color": BODY, "size": size})])
    box = text(slide, x, y, w, h, paras, size=size)
    for p in box.text_frame.paragraphs:
        p.space_after = Pt(11)
    return box


def card(slide, x, y, w, h, title, body, accent=RED, fill=SAND, title_size=15, body_size=12.5):
    rect(slide, x, y, w, h, fill, line=CARD_LINE)
    rect(slide, x, y, w, 0.07, accent)
    text(slide, x + 0.2, y + 0.2, w - 0.4, h - 0.3,
         [[(title, {"bold": True, "color": INK, "size": title_size})], [(body, {"color": BODY, "size": body_size})]], line=1.15)


def figure(slide, name, x, y, w, caption=None, frame=True, max_h=None):
    path = FIG / name
    if frame:
        rect(slide, x - 0.08, y - 0.08, w + 0.16, 0.1, WHITE)  # placeholder, resized below
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
    if max_h and pic.height > Inches(max_h):    # a long screenshot: keep its top, crop the rest
        pic.crop_bottom = 1 - Inches(max_h) / pic.height
        pic.height = Inches(max_h)
    if frame:
        border = slide.shapes[-2]
        border.top, border.left = pic.top - Inches(0.08), pic.left - Inches(0.08)
        border.width, border.height = pic.width + Inches(0.16), pic.height + Inches(0.16)
        border.line.color.rgb = CARD_LINE
        border.line.width = Pt(0.75)
    if caption:
        cy = Emu(pic.top + pic.height).inches + 0.14
        text(slide, x, cy, w, 0.5, caption, size=10.5, color=BODY, line=1.1)
        slide.shapes[-1].text_frame.paragraphs[0].runs[0].font.italic = True
    return pic


def code(slide, x, y, w, h, source, size=11.5):
    rect(slide, x, y, w, h, SAND, line=SAND_LINE)
    rect(slide, x, y, 0.07, h, TEAL)
    lines = source.strip("\n").splitlines()
    paras = []
    for ln in lines:
        stripped = ln.lstrip()
        color = MUTED if stripped.startswith("#") else (TEAL if stripped.split(" ")[0] in ("from", "import", "def", "return", "CREATE", "BEGIN", "END;", "SELECT", "FROM", "WHERE") else INK)
        paras.append([(ln or " ", {"font": MONO, "size": size, "color": color})])
    text(slide, x + 0.25, y + 0.2, w - 0.4, h - 0.3, paras, line=1.05)


def table(slide, x, y, w, rows, col_w, size=12, header_fill=TEAL):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(0.4 * len(rows)))
    tbl = shape.table
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if i == 0 else (WHITE if i % 2 else SAND)
            tf = cell.text_frame
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = str(val)
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.bold = i == 0 or j == 0
            r.font.color.rgb = WHITE if i == 0 else (INK if j == 0 else BODY)
            cell.margin_left = cell.margin_right = Inches(0.12)
    return tbl


def notes(slide, body):
    slide.notes_slide.notes_text_frame.text = body


def repo(slide, paths):
    """The files behind a slide go into the speaker notes, not onto the slide: the audience sees ideas, not file names."""
    tf = slide.notes_slide.notes_text_frame
    tf.text = (tf.text + "\n\n" if tf.text else "") + "In the repository: " + paths


def steps(slide, x, y, w, h, items, gap=0.32, title_size=14, body_size=11.5):
    """A left-to-right flow of numbered boxes: items are (title, body, accent)."""
    n = len(items)
    bw = (w - gap * (n - 1)) / n
    for i, (title, body, accent) in enumerate(items):
        bx = x + i * (bw + gap)
        rect(slide, bx, y, bw, h, SAND, line=CARD_LINE)
        rect(slide, bx, y, bw, 0.07, accent)
        text(slide, bx + 0.16, y + 0.2, bw - 0.32, 0.3, str(i + 1), size=20, color=accent, bold=True)
        text(slide, bx + 0.16, y + 0.62, bw - 0.32, h - 0.75,
             [[(title, {"bold": True, "color": INK, "size": title_size})], [(body, {"color": BODY, "size": body_size})]], line=1.13)
        if i < n - 1:
            arrow = rect(slide, bx + bw + 0.05, y + h / 2 - 0.13, gap - 0.1, 0.26, MUTED, shape=MSO_SHAPE.RIGHT_ARROW)
            arrow.line.fill.background()


def versus(slide, y, h, left, right, left_items, right_items, size=12.5, chosen_left=False):
    """Two columns: without (red, ✕) and with (green, ✓); chosen_left: the left is the choice, the right a neutral alternative."""
    styles = ((GREEN, "✓  "), (OCHRE, "•  ")) if chosen_left else ((RED, "✕  "), (GREEN, "✓  "))
    for i, (title, items, (accent, mark)) in enumerate(((left, left_items, styles[0]), (right, right_items, styles[1]))):
        x = 0.72 + i * 6.05
        rect(slide, x, y, 5.85, h, SAND, line=CARD_LINE)
        rect(slide, x, y, 5.85, 0.07, accent)
        text(slide, x + 0.22, y + 0.2, 5.4, 0.4, title, size=15, color=accent, bold=True)
        paras = [[(mark, {"bold": True, "color": accent, "size": size}), (a + " ", {"bold": True, "color": INK, "size": size}),
                  (b, {"color": BODY, "size": size})] for a, b in items]
        box = text(slide, x + 0.22, y + 0.7, 5.4, h - 0.85, paras, line=1.12)
        for p in box.text_frame.paragraphs:
            p.space_after = Pt(8)


def sandbox_run() -> tuple[int, int, int]:
    """(use cases passed, use cases, chat-completion POSTs) from the last e2e run in the sandbox."""
    path = EVIDENCE / "openshell" / "e2e.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    posts = sum(1 for r in rows for n in r.get("sandbox_network", []) if n.get("kind") == "HTTP:POST" and n.get("verdict") == "ALLOWED")
    return sum(r["passed"] and r.get("runtime") == ["openshell"] for r in rows), len(rows), posts


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def label_stability() -> tuple[int, int]:
    """Outcome-labelled prompts whose three label runs chose the same cheapest passing route, and how many were labelled."""
    path = ROOT / "classifier" / "data" / "labels.jsonl"
    if not path.exists():
        return 0, 0
    voted = [r for r in (json.loads(line) for line in path.read_text().splitlines()) if r.get("votes")]
    return sum(1 for r in voted if len(set(r["votes"])) == 1), len(voted)


def shot(slide, name, x, y, w, caption=None, max_h=None):
    """A screenshot; by default never lower than the footer, whatever its length."""
    if (SHOTS / name).exists():
        figure(slide, f"../screenshots/{name}", x, y, w, caption, max_h=max_h or (6.85 - y))


# ------------------------------------------------------------------- slides --

def build(template: Path, out: Path) -> None:
    prs = Presentation(str(template))
    drop_all_slides(prs)
    blank = layout(prs, "Light - Blank")
    meta = load(ROOT / "classifier" / "model" / "meta.json")
    ev = load(EVIDENCE / "classifier-eval.json")
    pay = {p["policy"]: p for p in ev["policies"]} if ev else None   # evidence/classifier-eval.json, by policy
    stable, labelled = label_stability()
    stable_pct = round(100 * stable / labelled) if labelled else 0
    appendix = []   # built in story order, moved behind the conclusion: the classifier in depth, for questions

    # 1 · cover
    s = prs.slides.add_slide(layout(prs, "Title/Cover_5"))
    for ph in s.placeholders:
        if ph.placeholder_format.idx == 0:
            ph.text = "The Right Model for Every Request"
        elif ph.name.startswith("Text Placeholder 2"):
            ph.text = "LiteLLM routing across 20 OCI models"
        elif ph.name.startswith("Text Placeholder 3"):
            ph.text = "Federico Kamelhar"
        elif ph.name.startswith("Text Placeholder 4"):
            ph.text = "Senior Principal Software Engineer, Agentic AI\nOracle\nOctober 2026"
    for ph in list(s.placeholders):
        if ph.has_text_frame and not ph.text_frame.text.strip():
            ph._element.getparent().remove(ph._element)
    rect(s, 2.62, 1.1, 0.02, 0.4, RGBColor(0x8F, 0xA6, 0xAD))
    text(s, 2.82, 1.06, 2.4, 0.45, "LiteLLM", size=22, color=WHITE, bold=True)
    notes(s, "Audience: the LiteLLM team. Everything here runs on LiteLLM 1.104.0 from PyPI, unmodified: the complexity router with "
             "classifier_type custom, tags, fallbacks, context-window checks. The last slides are what we found and what we would upstream.")

    # 2 · agenda
    s = prs.slides.add_slide(blank)
    header(s, "One story, one live demo", "Agenda")
    agenda = [("The blog", "LiteLLM natively supports OCI Generative AI", "3–4"),
              ("LiteLLM", "the architecture, what LiteLLM gives you, isolation and why this order, one request", "5–9"),
              ("Why route", "the portfolio, the toolbox, the use cases, the criteria", "10–13"),
              ("The router", "LiteLLM's plugin point, the classifier we plugged in, and where it is wrong", "14–19"),
              ("Live demo", "the demo screen and the agent trace, then back to the slides", "20–26"),
              ("Codex and Kubernetes", "skills as the harness; Kubernetes; field notes; what we would upstream", "27–31"),
              ("Appendix", "the classifier in depth: fine-tuning, fresh prompts and a second judge", "33–35")]
    for i, (t, sub, pages) in enumerate(agenda):
        y = 1.85 + i * 0.7
        rect(s, 0.72, y, 11.9, 0.6, SAND if i % 2 == 0 else WHITE, line=CARD_LINE)
        rect(s, 0.72, y, 0.07, 0.6, RED if t in ("LiteLLM", "The router", "Live demo") else TEAL)
        text(s, 1.0, y + 0.15, 0.5, 0.35, f"{i + 1:02d}", size=15, color=RED, bold=True, font=MONO)
        text(s, 1.65, y + 0.14, 3.6, 0.35, t, size=16, color=INK, bold=True)
        text(s, 5.3, y + 0.17, 6.0, 0.35, sub, size=13.5, color=BODY)
        text(s, 11.3, y + 0.17, 1.2, 0.35, pages, size=12, color=MUTED, align=PP_ALIGN.RIGHT)
    notes(s, "The thread: the blog made OCI a first-class LiteLLM provider; this talk puts its routing to work and shows a classifier we trained deciding where each request goes.")

    # 3 · the blog
    s = prs.slides.add_slide(blank)
    header(s, "Oracle AI & Data Science blog", "LiteLLM natively supports OCI Generative AI")
    text(s, 0.72, 1.75, 6.3, 0.8, [[("blogs.oracle.com/ai-and-datascience/litellm-natively-supports-generative-ai", {"font": MONO, "size": 11, "color": TEAL})]])
    bullets(s, 0.72, 2.25, 6.2, 4.4, [
        ("A first-class provider.", "Every OCI model family through one OpenAI-compatible endpoint: Meta Llama, xAI Grok, Cohere Command and Embed, Google Gemini, OpenAI GPT-5."),
        ("Signing handled.", "OCI Signature v1 lives in the gateway, including Instance Principal and OKE Workload Identity."),
        ("Production controls.", "Virtual keys, budgets, routing, fallbacks, caching, guardrails, audit and cost tracking, the same for every provider."),
        ("Agents on top.", "The OpenAI Agents SDK talks to the gateway with no OCI credential and no new model class."),
    ], size=13.5)
    figure(s, "blog-architecture.png", 7.25, 1.75, 5.35, "The blog's architecture: agent → LiteLLM AI Gateway → Oracle Generative AI Infrastructure.")
    notes(s, "Present the blog first: what shipped (BerriAI/litellm#28223, the provider guide) and why it matters. The rest of the talk is what you can build on it: routing.")

    # 4 · what it covers
    s = prs.slides.add_slide(blank)
    header(s, "What the integration supports", "One API shape for every OCI model family")
    table(s, 0.72, 1.85, 11.9, [
        ["Capability", "Coverage on OCI", "Used in this demo"],
        ["Chat, sync and streaming", "every vendor family", "every route"],
        ["Tool calling", "Cohere and the generic families", "the agent's policy, account and calculator tools"],
        ["Vision", "GPT-6, GPT-5.4, Gemini 2.5, Grok, Llama 4", "the VISION route (GPT-6-luna, Gemini 2.5 Flash; Llama 4 Maverick backup)"],
        ["Reasoning controls", "GPT-5/6, Grok, o-series", "the REASONING route (Grok 4.20 reasoning, Grok 4.7)"],
        ["Embeddings", "Cohere Embed, batches up to 96", "available as a group; the classifier embeds locally"],
        ["Auth", "API key, env vars, SDK signer, Instance Principal, OKE Workload Identity", "SDK signer with the operator's OCI session"],
    ], col_w=[2.6, 4.6, 4.7], size=12)
    text(s, 0.72, 5.55, 11.9, 0.9, [[("Every OCI model is ", {"size": 13.5, "color": INK}), ("oci/<vendor.model>", {"font": MONO, "size": 13, "color": TEAL}),
        (". Applications never branch on the vendor: the gateway picks the adapter, transforms the request, signs it and normalises the response.", {"size": 13.5, "color": INK})]], line=1.15)
    notes(s, "Source: the blog's capability matrix. The demo exercises chat, tools, vision and reasoning on OCI in us-chicago-1.")

    # 5 · architecture
    s = prs.slides.add_slide(blank)
    header(s, "The whole LiteLLM architecture", "One gateway between every app and every model")
    figure(s, "figure1-architecture.png", 0.72, 1.7, 8.0)
    bullets(s, 8.95, 1.85, 3.7, 4.8, [
        ("Routing", "decides where a request goes: classifiers, tags, context windows, fallbacks, load balancing."),
        ("Governance", "decides whether and how: keys, budgets, rate limits, cache, guardrails, spend."),
        ("Signing", "keeps OCI credentials in the gateway; apps hold a gateway key."),
    ], size=13)
    repo(s, "gateway/config.yaml · gateway/oci_session_signer.py")
    notes(s, "Left: anything that speaks the OpenAI API, including our langchain-oci agent and Codex. Middle: one process with one config file. Right: twenty OCI models across five vendors.")

    # 5a · what LiteLLM gives you
    s = prs.slides.add_slide(blank)
    header(s, "Every capability here is LiteLLM's; the demo only configures and plugs in", "What LiteLLM gives you")
    table(s, 0.72, 1.75, 11.9, [
        ["Benefit", "How LiteLLM does it", "Proved in this demo"],
        ["One API for every model", "an OpenAI-compatible endpoint; the oci/ provider covers every OCI vendor", "20 OCI models from 5 vendors; the agent names a model group, never a vendor model"],
        ["Routing as configuration", "complexity router, tags, context-window checks, latency balancing", "8 routes; our classifier plugs in as classifier_type: custom" + (
            ": {:.0%} good answers at {:.0%} less than always-reasoning".format(pay["trained"]["quality"], 1 - pay["trained"]["cost_usd"] / pay["always REASONING"]["cost_usd"]) if pay else "")],
        ["Keys, budgets, limits", "virtual keys with allowed models, budget, rate limit and spend (Postgres)", "the OpenShell agent's key: 5 model groups, $5 per 30 days, 120 requests a minute; anything else is a 403"],
        ["Reliability", "fallbacks, retries, timeouts, cooldowns", "a failing deployment falls back; a classifier outage routes to fallback_tier; {0} of {1} use cases answered".format(*sandbox_run())],
        ["Observability", "cost and route on every response, spend per key, logging callbacks", "x-litellm-* headers on every call; one ROUTE line per request in the console; the agent trace reads them call by call"],
        ["Extensibility", "CustomLogger hooks, CustomLLM providers, classifier plugins", "OCI signing hook, the decision header, Codex through OCI's Responses API"],
        ["Credentials in one place", "provider auth lives in the gateway; applications hold a virtual key", "the sandbox holds a placeholder; only LiteLLM signs to OCI"],
    ], col_w=[2.5, 4.3, 5.1], size=11)
    text(s, 0.72, 6.2, 11.9, 0.5, "No fork: LiteLLM 1.104 from PyPI and its official container image, unmodified. Everything we added is a documented extension point.",
         size=13, color=INK, bold=True)
    repo(s, "gateway/config.yaml · gateway/*.py (hooks, provider, plugin) · scripts/oci/deploy.sh (virtual keys)")
    notes(s, "Lead with this slide for a LiteLLM audience: each row is a LiteLLM feature, and the third column is the evidence in this repository.")

    # 5b · isolation
    s = prs.slides.add_slide(blank)
    header(s, "OpenShell holds the agent; LiteLLM holds the decisions and the keys", "The agent holds nothing")
    figure(s, "figure6-isolation.png", 2.95, 1.5, 7.4)
    repo(s, "sandbox/ (image, profile, policy) · scripts/openshell.sh · gateway/route_headers.py · scripts/oci/deploy.sh")
    notes(s, "The agent runs in an OpenShell sandbox with a placeholder key and one allowed endpoint: POST /v1/chat/completions on LiteLLM. "
             "OpenShell's gateway holds the agent's LiteLLM virtual key and swaps it in on the way out. LiteLLM checks that key (5 model groups, "
             "$5 per 30 days, 120 rpm), classifies with our plugin, routes, signs to OCI as the node, and accounts. Measured: {0} of {1} use cases ran "
             "entirely in the sandbox; its only connections were {2} chat-completion POSTs to the gateway;".format(*sandbox_run()) + " OCI directly, api.openai.com and the "
             "gateway's /key admin API were refused.")

    # 5b2 · why this order
    s = prs.slides.add_slide(blank)
    header(s, "Sandbox the code you do not trust; make the gateway its only way out", "Why this order?")
    versus(s, 1.9, 3.6, "Agent → OpenShell → LiteLLM → OCI  (this demo)", "LiteLLM → OpenShell → OCI",
           [("OpenShell contains the untrusted part.", "The agent runs plans and tools a model wrote, and can be prompt-injected."),
            ("LiteLLM is trusted infrastructure.", "One shared service many apps call: it decides the model, checks the key, keeps the budget and the costs."),
            ("Result:", "the agent can reach nothing but the gateway, and every call it makes is checked, routed and accounted.")],
           [("Benefit:", "the gateway itself would hold no OCI credential; OpenShell would sign the calls."),
            ("But:", "a sandbox is built to run an agent's outbound calls, not a shared server that many apps call into."),
            ("And:", "on OKE the gateway already holds no stored key: it signs as the node.")], chosen_left=True)
    text(s, 0.72, 5.75, 11.9, 0.9, [[("Next step, both layers: ", {"bold": True, "color": INK, "size": 14}),
        ("keep agent → LiteLLM, and run LiteLLM in its own sandbox with OpenShell signing the OCI calls. Then neither the agent nor the gateway holds an OCI credential.",
         {"color": BODY, "size": 13.5})]], line=1.15)
    notes(s, "OpenShell isolates code; LiteLLM decides. Proxy-side OCI signing in OpenShell is NVIDIA/OpenShell#3962 (open).")

    # 5c · sequence
    s = prs.slides.add_slide(blank)
    header(s, "One request, in order: what happens between the agent and the model", "The sequence")
    figure(s, "figure7-sequence.png", 3.25, 1.45, 6.8)
    repo(s, "gateway/route_headers.py · gateway/trained_classifier.py · gateway/oci_session_signer.py · sandbox/profile/litellm-gateway.yaml")
    notes(s, "Walk it top to bottom: the sandbox sends a placeholder; OpenShell swaps in the virtual key; LiteLLM checks it, asks the classifier "
             "(complexity router, custom plugin), picks the deployment, signs in a pre-call hook, calls OCI, falls back on an error, and returns "
             "the answer with x-litellm-* headers, including the classifier's full decision.")

    # 6 · why route: the portfolio as deployed
    s = prs.slides.add_slide(blank)
    pf = load(EVIDENCE / "model-portfolio.json")
    header(s, f"{pf['models']} OCI models, five vendors, one gateway" if pf else "The portfolio", "Why route")
    if pf:
        short = {"SIMPLE": "fast", "MEDIUM": "balanced", "COMPLEX": "strong", "REASONING": "reasoning", "CODE": "code", "VISION": "vision",
                 "LONG_CONTEXT": "long", "MULTILINGUAL": "language"}
        def uses(r):
            out = []
            for u in r["uses"]:
                name = short.get(u["route"], u["route"])
                role = u["role"].split()[0]
                out.append(name if role == "primary" else f"{role} lane" if name == "tag lane" else name if name in ("judge", "LLM classifier") else f"{name} ({role})")
            return ", ".join(dict.fromkeys(out))
        def src(r):
            t = r["price_source"]
            return "OCI" if t.startswith("OCI price list") else "vendor" if t.startswith("vendor") else "map*"
        rows = [["Model on OCI", "Route", "$ in / out per 1M", "Price"]] + [
            [r["model"].split(".", 1)[1].replace("-17b-16e-instruct", "").replace("-17b-128e-instruct-fp8", "").replace("-instruct", ""),
             uses(r), f"{r['price_per_1m'][0]:.2f} / {r['price_per_1m'][1]:.2f}", src(r)] for r in pf["rows"]]
        half = (len(rows) + 1) // 2
        table(s, 0.5, 1.5, 6.15, rows[:half], col_w=[1.9, 2.4, 1.2, 0.65], size=8.5)
        table(s, 6.75, 1.5, 6.15, [rows[0]] + rows[half:], col_w=[1.9, 2.4, 1.2, 0.65], size=8.5)
        rp = pf["route_pass_rate"]
        text(s, 0.5, 6.42, 12.4, 0.4, [[("Good answers by route, 359 judged prompts: ", {"bold": True, "color": INK, "size": 10}),
            (f"fast {rp['SIMPLE']:.0%} · balanced {rp['MEDIUM']:.0%} · strong {rp['COMPLEX']:.0%} · reasoning {rp['REASONING']:.0%}.  "
             "Price: OCI = OCI's public price list · vendor = the vendor's list price (OCI publishes none) · "
             "map* = LiteLLM's map; OCI bills Meta and Cohere per character.", {"color": BODY, "size": 9})]], line=1.05)
    repo(s, "gateway/config.yaml · scripts/portfolio.py · evidence/model-portfolio.json · classifier/model_trial.py")
    notes(s, "Price sources, part numbers in evidence/model-portfolio.json: Gemini 2.5 Flash B111851/B111853, Flash-Lite B111854/B111856, "
             "Grok 4.20 B111910/B112076, Grok 4.7 B113303/B113305, Grok 4.3 B112080/B112082. "
             "Chosen by a trial: every candidate answered the same 40 prompts, one judge graded them (evidence/model-trial.json). "
             "The code route is GPT-5.3-codex, which OCI serves only on its Responses API: gateway/oci_responses.py is a LiteLLM provider for it. "
             "LiteLLM's price map undercounts OCI Gemini 2.5 Flash about 4x and has no entry for the newer models: every deployment states its price.")

    # 7 · the routing toolbox
    s = prs.slides.add_slide(blank)
    header(s, "Five kinds of decision, all in config", "LiteLLM's routing toolbox")
    table(s, 0.72, 1.85, 11.9, [
        ["What decides", "LiteLLM feature", "In this demo"],
        ["what the request needs", "complexity router + a classifier", "eight routes: SIMPLE … MULTILINGUAL"],
        ["who is calling", "tag routing, team routing", "oci-chat: premium tag → GPT-5.2, default → Gemini Flash"],
        ["the prompt does not fit", "context-window check and fallback", "oci-compact (2k window) → oci-long, before the call"],
        ["a deployment fails", "fallbacks, retries, cooldowns", "oci-flaky always fails → oci-balanced; every route has a backup"],
        ["several can serve", "load balancing: latency, cost, usage, weights", "two models in most routes, latency-based; vision mixes OpenAI and Google"],
    ], col_w=[2.8, 4.0, 5.1], size=12.5)
    text(s, 0.72, 5.25, 11.9, 1.0, [[("Every decision comes back in the response: ", {"bold": True, "color": INK, "size": 13.5}),
        ("x-litellm-complexity-router-tier, -cause, x-litellm-model-name, x-litellm-attempted-fallbacks, x-litellm-response-cost. The control room shows them live.", {"color": BODY, "size": 13})]], line=1.15)
    repo(s, "gateway/config.yaml · scripts/probe_routes.py (one probe per feature)")
    notes(s, "All of these are plain config in the open-source gateway. probe_routes.py proves each one with a real OCI call: ROUTES OK.")

    # 8 · use cases
    s = prs.slides.add_slide(blank)
    header(s, "Same gateway, different requests", "Use cases and the route each needs")
    table(s, 0.72, 1.85, 11.9, [
        ["Use case", "Request", "Route", "Answered by"],
        ["Customer support", "FAQ · billing dispute · SLA escalation", "SIMPLE · MEDIUM · REASONING", "GPT-6-luna · GPT-5.4-mini · Grok 4.20"],
        ["Coding assistant", "explain a line · debug a race condition", "CODE", "GPT-5.3-codex (Responses API), backup GPT-5.1"],
        ["Analyst", "one number · a forecast under a cap", "SIMPLE · REASONING", "GPT-6-luna · Grok 4.20 / 4.7"],
        ["Document analysis", "a 300-page contract", "LONG_CONTEXT", "Gemini 2.5 Flash (1M tokens)"],
        ["Multilingual service", "Spanish, Japanese, French …", "MULTILINGUAL", "Cohere Command A"],
        ["Vision", "a photo of an invoice", "VISION", "GPT-6-luna · Gemini 2.5 Flash"],
        ["Premium customer", "the same request, a premium contract", "tag: premium", "GPT-5.2"],
        ["Resilience", "a model is down", "fallback", "the next group, no app change"],
    ], col_w=[2.3, 3.8, 2.7, 3.1], size=11.5)
    text(s, 0.72, 6.05, 11.9, 0.4, "The route each request needs, measured. Today's router sends the SLA escalation and the forecast to the strong route instead: see \u201cWhere the router is wrong\u201d.",
         size=10.5, color=MUTED)
    repo(s, "app/scenarios.py (each use case, with the route it should take)")
    notes(s, "Every row is a button in the control room. Northwind Cloud is a fictional company; no real customer data.")

    # 9 · the criteria
    s = prs.slides.add_slide(blank)
    header(s, "What decides a route", "The criteria")
    for i, (t, b, c) in enumerate([
        ("1 · Facts in the request", "Checked by rules, exactly: an image goes to VISION; a very long prompt to LONG_CONTEXT; a language other than English to MULTILINGUAL.", OCHRE),
        ("2 · What the request needs", "Predicted by our ladder: each route's chance of an answer a judge accepts (correctness, completeness, instruction-following); the cheapest route over the quality bar wins.", RED),
        ("3 · Business rules", "Applied by the gateway: customer tier (tags), team budgets (keys), latency (strategy), availability (fallbacks, retries, cooldowns).", INDIGO),
    ]):
        x = 0.72 + i * 4.02
        rect(s, x, 1.9, 3.82, 3.6, SAND, line=CARD_LINE)
        rect(s, x, 1.9, 3.82, 0.07, c)
        text(s, x + 0.25, 2.15, 3.35, 3.2, [[(t, {"bold": True, "size": 16, "color": c})], [(b, {"size": 13, "color": BODY})]], line=1.2)
    text(s, 0.72, 5.8, 11.9, 0.6, "Rules first, because they are certain; the model for judgement; the gateway's own features for everything a business decides.", size=13.5, color=INK, bold=True)
    notes(s, "Answer to 'what are the criteria': three layers, in that order. The judge criteria are the labelling contract, slide 13.")

    # 10 · where the classifier sits
    s = prs.slides.add_slide(blank)
    header(s, "LiteLLM's complexity router calls our plugin, before any model is called", "Where the classifier plugs in")
    figure(s, "figure2-classifier-path.png", 2.4, 1.65, 8.5)
    repo(s, "gateway/trained_classifier.py · classifier/router_model.py")
    notes(s, "LiteLLM's complexity router calls our plugin's classify(context) and gets back a route name; the route names a group; the group picks a deployment with latency, context-window and fallback logic. "
             "Everything after the route name is LiteLLM's. The classifier is a small CPU service, no GPU: a frozen e5-small encoder and logistic models, "
             "tens of milliseconds a decision on a laptop; if it is down or slow, LiteLLM routes to fallback_tier.")

    # 11 · classifier choices
    s = prs.slides.add_slide(blank)
    header(s, "LiteLLM lets you choose who decides", "Classifier options in the complexity router")
    table(s, 0.72, 1.85, 11.9, [
        ["classifier_type", "Who decides the route", "Cost per request", "In this demo"],
        ["heuristic", "local keyword and structure scoring", "none, under 1 ms", "oci-auto, the baseline"],
        ["llm", "a model grades the request against a rubric", "one extra model call", "oci-auto-llm: Gemini 2.5 Flash-Lite"],
        ["custom", "your classify() plugin", "what your code costs", "oci-auto-trained: ours"],
        ["oss_classifier", "open classifiers: Jev (TypeSafe), Laya, Bespoke; self-hostable", "one network call", "the path to a classifier on our own GPU"],
        ["capability", "forecasts whether the cheap model succeeds", "one extra model call", "—"],
    ], col_w=[2.3, 4.4, 2.3, 2.9], size=12)
    text(s, 0.72, 5.25, 11.9, 1.1, [[("Open-source limit: ", {"bold": True, "color": RED, "size": 13}),
        ("one router with custom routes per gateway; more need a licence. Ours is that one: eight routes instead of the four shipped tiers.", {"color": BODY, "size": 13})]], line=1.15)
    notes(s, "Upstream renamed classifier_type 'jev' to 'oss_classifier'. A model we train and serve on our own cluster plugs in through custom or oss_classifier with an api_base.")

    # 12 · mini-training
    s = prs.slides.add_slide(blank)
    header(s, "Label by outcome, train in seconds", "Mini-training the classifier")
    figure(s, "figure3-mini-training.png", 2.2, 1.65, 8.9)
    repo(s, "classifier/generate.py · label.py · train.py · evaluate.py")
    notes(s, "The key idea: a label is not someone's guess about difficulty; it is the cheapest route that actually produced an acceptable answer.")

    # 13 · from labels to a ladder
    s = prs.slides.add_slide(blank)
    pct = stable_pct   # from classifier/data/labels.jsonl: the three label runs agree
    header(s, "Predict each route's chance of a good answer, not one label", "Why a ladder")
    lad = (meta or {}).get("ladder")
    card(s, 0.72, 1.85, 5.6, 2.15, "One label is a coin flip",
         f"Labelled three times, only {pct}% of prompts got the same cheapest passing route every time (63% with the first portfolio). Accuracy against such labels "
         "tops out in the 60s and 70s for any model: bigger encoders (up to 568M weights) did not move it.", accent=OCHRE)
    card(s, 0.72, 4.25, 5.6, 2.2, "So predict pass probabilities",
         "Per route: a logistic model on the embedding and difficulty signals, averaged with the pass rates of the 12 most similar "
         "labelled requests. Take the cheapest route at least as likely as the quality bar.", accent=RED)
    if lad:
        rows_l = [["Quality bar", "Good answers", "Per request"]] + [
            [f"{round(c['bar'] * 100)}%" + ("  (trained)" if c["bar"] == lad["bar"] else ""), f"{round(c['quality'] * 100)}%", f"${c['cost_per_request']:.4f}"]
            for c in lad["held_out_curve"]] + [["always reasoning", f"{round(lad['held_out']['always REASONING']['quality'] * 100)}%",
                                                f"${lad['held_out']['always REASONING']['cost_per_request']:.4f}"],
                                               ["always balanced", f"{round(lad['held_out']['always MEDIUM']['quality'] * 100)}%",
                                                f"${lad['held_out']['always MEDIUM']['cost_per_request']:.4f}"]]
        table(s, 6.7, 1.85, 5.9, rows_l, col_w=[2.3, 1.8, 1.8], size=11)
        text(s, 6.7, 6.25, 5.9, 0.5, f"{lad['held_out_prompts']} prompts never seen in training or in choosing the bar.", size=10.5, color=MUTED)
    notes(s, "The bar was chosen inside the training split by 5-fold cross-validation: the cheapest bar at least as good as always-reasoning. "
             "On the unseen prompts the dial runs from always-balanced quality to always-reasoning quality at less cost.")

    # 13b · did we really train it
    s = prs.slides.add_slide(blank)
    header(s, "Frozen encoder versus fine-tuning the encoder itself", "Did we really train the model?")
    ft = load(EVIDENCE / "finetune-comparison.json")
    if ft:
        table(s, 0.72, 1.85, 11.9, [
            ["", "What was trained", "Weights trained", "Held-out accuracy", "Balanced accuracy", "Time"],
            ["Frozen", "the logistic-regression head", "1,540", f"{round(ft['frozen']['held_out_accuracy'] * 100, 1)}%",
             f"{round(ft['frozen']['held_out_balanced_accuracy'] * 100, 1)}%", "0.14 s, laptop CPU"],
            ["Fine-tuned", "every encoder weight, then the head", f"{ft['encoder_parameters'] / 1e6:.1f} M",
             f"{round(ft['fine_tuned']['held_out_accuracy'] * 100, 1)}%", f"{round(ft['fine_tuned']['held_out_balanced_accuracy'] * 100, 1)}%",
             f"{ft['fine_tuned']['fine_tune_seconds']:.0f} s, Mac GPU (MPS)"],
        ], col_w=[1.9, 3.1, 1.6, 1.8, 1.8, 1.7], size=12.5)
    bullets(s, 0.72, 3.7, 11.9, 2.8, [
        ("Yes: supervised learning on outcomes.", "The shipped router fits four logistic models, one per route (391 weights each), on what a judge actually accepted, plus a code head. The encoder stays frozen."),
        ("Fine-tuning the encoder is the next lever.", "In an earlier experiment on single-run labels (table above), training all 117.6 million encoder weights SetFit-style added about 8 points of label accuracy, in 47 s on the Mac's GPU. Read it as optimistic: two schedules were tried."),
        ("Why the small model ships.", "The ladder rebuilds from a 210 KB file and runs on one Ampere core in Kubernetes; a fine-tuned encoder is 470 MB. With more labelled traffic, fine-tune on an OCI GPU: same scripts."),
    ], size=13)
    repo(s, "classifier/train.py (frozen) · classifier/finetune.py (fine-tuned) · evidence/finetune-comparison.json")
    notes(s, "Answer to 'did we really train it?': yes. Be precise: the shipped router trains a head on frozen embeddings; the fine-tuning run trains the encoder too.")
    appendix.append(s)

    # 14 · results: does it pay
    s = prs.slides.add_slide(blank)
    header(s, "Quality and cost on the same held-out requests", "Does routing pay?")
    figure(s, "figure4-quality-cost.png", 2.4, 1.6, 8.5)
    repo(s, "evidence/classifier-eval.json · classifier/evaluate.py")
    if ev:
        pol = {p["policy"]: p for p in ev["policies"]}
        notes(s, "Policies on the held-out prompts: " + "; ".join(f"{p['policy']} {round(p['quality'] * 100)}% at ${p['cost_usd']:.3f}" for p in ev["policies"])
              + f". Through the real gateway, the ladder gives {round((pol['trained']['quality'] - pol['heuristic']['quality']) * 100)} more points of good answers than LiteLLM's heuristic, "
              f"{round((pol['trained']['quality'] - pol['llm']['quality']) * 100)} more than the LLM classifier at {round((1 - pol['trained']['cost_usd'] / pol['llm']['cost_usd']) * 100)}% less, "
              f"and stays {round((pol['always REASONING']['quality'] - pol['trained']['quality']) * 100)} points under always-reasoning at {round((1 - pol['trained']['cost_usd'] / pol['always REASONING']['cost_usd']) * 100)}% less.")

    # 14a · where the router is wrong: one request at a time, measured
    sv, rl = load(EVIDENCE / "strong-vs-reasoning.json"), load(EVIDENCE / "relabel-gpt-6.1-sol.json")
    if sv:
        s = prs.slides.add_slide(blank)
        header(s, "Routing is a prediction: measure it, one request at a time", "Where the router is wrong")
        sm = sv["summary"]
        what = {"support-escalation": "SLA escalation: three outages, the credit, a remediation plan",
                "analyst-forecast": "GPU budget: three growth scenarios under a quarterly cap"}
        frac = lambda k: f"{sm[k]['passed']} of {sm[k]['of']}"  # noqa: E731
        table(s, 0.72, 1.75, 11.9, [["Request (a demo use case)", "The router sends it to", "Strong passed", "Reasoning passed"]] + [
            [what[p], "strong · GPT-6-sol", frac(f"{p} oci-strong"), frac(f"{p} oci-reasoning")] for p in what], col_w=[5.6, 2.5, 1.9, 1.9], size=12.5)
        bullets(s, 0.72, 3.3, 11.9, 3.3, [
            ("What failed.", "Correctness: the strong model got the credit or the scenario arithmetic wrong. Same judge and pass rule as the labels, each answer graded on its own."),
            ("What we checked.", "GPT-6.1-sol had answered part of the strong route's labels and then left the route. {0} label runs were done again; {1} of {2} labels changed, and these two decisions did not. "
             "The ladder's estimate comes from similar labelled requests, and they say strong.".format(rl["runs_labelled_again"], rl["label_changed"], rl["prompts"]) if rl else ""),
            ("What LiteLLM gives you meanwhile.", "An app that knows a request is hard asks for a model group by name; the decision comes back in every response header, so each miss is visible and can be counted."),
            ("What fixes it.", "More labelled requests of this kind, constrained arithmetic, and the outcomes of live traffic fed back into the labels."),
        ], size=12.5)
        repo(s, "classifier/strong_vs_reasoning.py · evidence/strong-vs-reasoning.json · classifier/label.py --redo · evidence/relabel-gpt-6.1-sol.json")
        notes(s, f"{sv['n']} answers per route per prompt, graded by {sv['judge']}, pass = {sv['pass']}. The measurement puts the policy text in the prompt and gives no tools; "
                 "the live agent has a calculate tool and can do better. In the demo this is an optional step: the router's known miss.")

    # 14b · does it hold up: fresh prompts, a second judge
    rb = load(EVIDENCE / "robustness.json")
    if rb:
        s = prs.slides.add_slide(blank)
        fr = rb["fresh"]
        header(s, f"{fr['prompts']} new prompts nobody trained on, graded by two judges from different vendors", "Does it hold up?")
        names = [("ladder (ours)", "our ladder"), ("LiteLLM heuristic", "LiteLLM heuristic"), ("LiteLLM LLM classifier", "LiteLLM LLM classifier"),
                 ("always SIMPLE", "always fast"), ("always MEDIUM", "always balanced"), ("always COMPLEX", "always strong"),
                 ("always REASONING", "always reasoning"), ("oracle", "perfect routing")]
        js = list(fr["policies_by_judge"])
        rows_r = [["Policy", *[f"{j}: good answers" for j in js], "cost"]] + [
            [label, *[f"{fr['policies_by_judge'][j][k]['quality']:.0%}" for j in js], f"${fr['policies_by_judge'][js[0]][k]['cost_usd']:.3f}"]
            for k, label in names if k in fr["policies_by_judge"][js[0]]]
        table(s, 0.72, 1.75, 7.0, rows_r, col_w=[2.4, 1.75, 1.75, 1.1], size=11)
        text(s, 0.72, 5.75, 7.0, 0.9, [[("Plainly: ", {"bold": True, "color": INK}),
             ("the ladder sits on the cost frontier, but the strong route, which training left out, gives the most good answers on fresh prompts. "
              "Perfect routing costs less than the ladder: the headroom is in the predictor, not the models. We did not retune on this test.", {})]], size=11.5)
        code = rb["code"]["pass_rate"]; vis = rb["vision"]["exact_answer_rate"]
        card(s, 8.0, 1.75, 4.6, 1.55, f"The judges agree on {fr['judge_agreement']:.0%} of answers",
             f"GPT-5.2 (the training judge) and Gemini 2.5 Pro (another vendor, not in the portfolio). Prompts written by {fr['writer'].split('.', 1)[1].upper()}, which the router never uses.", accent=INDIGO)
        card(s, 8.0, 3.45, 4.6, 1.45, "Code: " + " · ".join(f"{k.split(' (')[0]} {v['gemini-2.5-pro']:.0%}" for k, v in code.items()),
             f"pass rate on {rb['code']['tasks']} coding tasks, judged by Gemini 2.5 Pro (GPT-5.2: " + " · ".join(f"{v['gpt-5.2']:.0%}" for v in code.values()) + ").", accent=TEAL)
        card(s, 8.0, 5.05, 4.6, 1.25, "Vision: " + " · ".join(f"{k} {v:.0%}" for k, v in vis.items()),
             f"exact total and due date read from {rb['vision']['images']} generated invoices.", accent=OCHRE)
        repo(s, "classifier/robustness.py · evidence/robustness.json")
        notes(s, "The held-out numbers on 'Does routing pay?' came from the same judge and the same prompt writer as the training labels. "
                 "This slide changes both: new prompts by a model outside the portfolio, and a second judge from another vendor.")
        appendix.append(s)

    # 15 · live demo divider
    s = prs.slides.add_slide(blank)
    rect(s, 0, 0, 13.333, 7.5, TEAL)
    text(s, 0.72, 2.2, 11.9, 0.4, "LIVE DEMO · SWITCH TO THE BROWSER", size=13, color=YELLOW, bold=True, spacing=220)
    text(s, 0.72, 2.7, 11.9, 1.0, "The routing control room", size=40, color=WHITE, bold=True)
    beats = ["Route a request: the agent runs in OpenShell; the trace shows each LiteLLM decision, each tool and its result",
             "Business rules in config: a premium tag takes another lane; the agent's key carries its models, budget and spend",
             "Use cases: support, code (to Codex), a forecast, Japanese, an invoice photo; each call on the route map",
             "A multi-step agent: a planner splits one job into tasks, and LiteLLM routes each task to its own model",
             "Under the hood: LiteLLM's heuristic, its LLM classifier and our ladder on the same request",
             "Try to escape: OCI, OpenAI and the admin API refused; a failing gateway fails over to the laptop"]
    text(s, 0.72, 3.85, 11.9, 3.0, [[(f"{i + 1}   ", {"bold": True, "color": YELLOW, "size": 15}), (b, {"color": WHITE, "size": 15})] for i, b in enumerate(beats)], line=1.5)
    text(s, 0.72, 7.08, 11.9, 0.3, FOOTER, size=8, color=RGBColor(0xC8, 0xD6, 0xDB))
    notes(s, "Before the talk: scripts/demo-up.sh, which ends with PREFLIGHT OK, and an OCI session with more than 30 minutes left. "
             "If the network fails, the control room replays recorded runs, labelled as replays; the screenshots on the next slides are the last resort.")

    # 16 · what you saw
    s = prs.slides.add_slide(blank)
    header(s, "Back to the slides", "What you just saw")
    table(s, 0.72, 1.85, 11.9, [
        ["In the demo", "What it shows", "The LiteLLM part"],
        ["a request routed and explained", "each route's chance of a good answer against the bar", "the complexity router calling our classifier"],
        ["the agent trace", "every call's decision, every tool's arguments and result", "LiteLLM's response headers, call by call"],
        ["the agent in OpenShell", "no key in the sandbox; one allowed endpoint", "a virtual key with models, budget and rate limit"],
        ["a premium tag on the same request", "another lane for another contract", "tag routing, in config"],
        ["the quality bar moving the route", "one dial between spend and answer quality", "a per-request setting the router passes through"],
        ["code going to Codex", "the right model for the task, on the API OCI serves it on", "a custom provider, plugged into the same routes"],
        ["one job split into tasks", "each task on the model it needs", "every step is its own request, routed on its own"],
        ["a failing model, then a failing gateway", "the answer still arrives", "fallbacks and retries in the router"],
        ["the console", "every request's key, route, model and cost", "LiteLLM's own callbacks and response headers"],
    ], col_w=[3.5, 4.4, 4.0], size=12)
    notes(s, "Land the demo, then show the screens in detail.")

    # 16b · ask and explain
    s = prs.slides.add_slide(blank)
    header(s, "Pick a use case, route it, and see every decision LiteLLM made", "The demo screen")
    shot(s, "00-ask-escape.png", 0.72, 1.7, 7.2)
    bullets(s, 8.15, 1.85, 4.5, 4.9, [
        ("Use cases, in the order of the talk.", "Each says the one thing it shows: a cheap model, reasoning, Codex, a rule, a fallback."),
        ("The request.", "One pass or multi-step, an image, and the quality bar."),
        ("Sandbox → LiteLLM → OCI.", "Where the request went: no key in the sandbox; key check, classify, route, sign and account in LiteLLM; the models that answered. 'Try to escape' shows the refusals."),
        ("What happened.", "The agent trace: every model call with LiteLLM's decision, every tool with its arguments and result, each task's result; click a call for its ladder. Then the answer, and why the first call got its route."),
    ], size=12.5)
    repo(s, "ui/sandbox.py · gateway/route_headers.py · classifier/explain.py · web/src/components/Ask.tsx")
    notes(s, "Nothing on this screen is written by a model after the fact: every sentence is built from the router's own numbers and the labels on file.")

    # 17 · the control room
    s = prs.slides.add_slide(blank)
    header(s, "LiteLLM classifies every call, not just the first", "What happened")
    shot(s, "02-this-run.png", 0.72, 1.7, 7.6)
    bullets(s, 8.5, 1.85, 4.1, 4.9, [
        ("Every call is classified.", "The agent calls the model, runs a tool, calls again: each call reaches LiteLLM, and each gets a decision."),
        ("One pass, one route.", "Every call carries the same request, so every call gets the same route. The screen says so, and points to multi-step."),
        ("The route map.", "Request, classifier, eight routes, every model: the path lights up live. Zoom, pan and full screen for the room."),
    ], size=12.5)
    repo(s, "app/agent.py · ui/server.py · web/src/components/Ask.tsx · web/src/components/RouteMap.tsx")
    notes(s, "The UI is a thin client over the gateway's own headers.")

    # 17a · the agent trace
    s = prs.slides.add_slide(blank)
    header(s, "Every model call, every tool and its result, in order", "The agent trace")
    shot(s, "09-agent-trace.png", 0.6, 1.5, 6.6, max_h=5.45)
    bullets(s, 7.5, 1.65, 5.2, 5.1, [
        ("LiteLLM's decision, per call.", "The route and why, the model it picked, which check decided and in how many milliseconds, tokens in and out, cost, fallbacks."),
        ("What the model did.", "Asked the agent to run a tool, or answered. Long answers fold; a task's last answer is its result, passed to the next task."),
        ("Every tool.", "Its arguments and what it returned: the policy text, the account, the arithmetic."),
        ("Reasoning models.", "A call shows how many reasoning tokens it spent. OCI returns the count, not the text, so the screen shows no more than that."),
        ("Live.", "While the agent works, one line says what is happening: classifying, running a tool, reading its result."),
    ], size=12)
    repo(s, "web/src/components/Timeline.tsx · app/agent.py (RouteRecorder) · gateway/route_headers.py")
    notes(s, "Everything on this screen comes from LiteLLM's response headers and the agent's own callbacks; no model writes any of it after the fact. "
             "Point at a tool's result, then at the next call: the model read it, and LiteLLM classified that call again.")

    # 17b · multi-step agent
    s = prs.slides.add_slide(blank)
    header(s, "One job, split into tasks; each task routed on its own", "A multi-step agent: a model per task")
    shot(s, "06-plan-panel.png", 0.6, 1.55, 6.4)
    bullets(s, 7.3, 1.7, 5.4, 5.2, [
        ("1 · Plan.", "A planner call splits the request into tasks. LiteLLM routes the planner like any other call."),
        ("2 · Route each task.", "Each task reaches LiteLLM as its own request, so each is classified on its own words: a lookup, a calculation, a reply and a function can each get a different model."),
        ("3 · Every call inside a task is classified too.", "The screen groups the calls by task, each with its decision."),
        ("Four jobs.", "Escalation, incident update, invoice photo, GPU budget pack. The invoice job's photo goes to the task that reads it, and from there to VISION; four runs each gave its facts right 13 times in 16; every miss was arithmetic on the balanced route."),
        ("What it found.", "A coding task in billing words went to balanced: no training example was worded that way. With 64 such requests and 64 counter-examples: 100% to Codex, 3% false alarms."),
        ("What it costs.", "The misses were a route's weakest member: LiteLLM's latency routing usually picked Grok 4.20 non-reasoning in the balanced route, right 3 in 8 on the overrun task alone; GPT-5.4-mini, same route, 8 in 8. Grok moved to the route's backup and the router was relabelled. An arithmetic task can still land on strong where reasoning does better."),
    ], size=11.5)
    notes(s, "Runs differ a little because the planner words tasks differently; "
             "every run in testing sent the coding task to Codex after the fix. Earlier results travel in the system prompt, which the router does not read, "
             "so a task is routed on its own words, not on the whole job's.")

    # 18 · compare
    s = prs.slides.add_slide(blank)
    header(s, "Same request, three classifiers", "Compare routers")
    shot(s, "06-compare-crop.png", 1.17, 1.65, 11.0)
    repo(s, "POST /api/compare · web/src/components/Compare.tsx")
    notes(s, "Same request through LiteLLM's heuristic, its LLM classifier and our ladder. Point at the route each chose and its cost; the held-out numbers behind the comparison are on the 'Does routing pay?' slide.")

    # 19 · codex
    s = prs.slides.add_slide(blank)
    header(s, "Ask in plain words; Codex follows the skills and reports what it ran", "Built and run with Codex")
    table(s, 0.72, 1.85, 7.6, [
        ["You ask Codex", "What it does"],
        ["“Get the demo ready for my talk”", "starts every piece, runs the preflight, applies the known fix for each failing check, reports"],
        ["“The control room stopped answering”", "reads LiteLLM's and OpenShell's log lines, finds the failing step, fixes it"],
        ["“Add this model to the balanced route”", "tests it on OCI, takes its price from OCI's list, measures it against the current one, updates the routes"],
        ["“Is the router still good?”", "re-runs the evaluation and every check, and reports quality and cost against each fixed route"],
    ], col_w=[3.0, 4.6], size=12)
    bullets(s, 8.6, 1.85, 4.05, 4.8, [
        ("Five skills.", "One per part: running the demo, the gateway, routing, the router, the checks. Codex loads the one the task needs."),
        ("House rules.", "No secrets, no clusters but the local one, no paid runs without asking, never change code to make a check pass."),
        ("You keep one step.", "The OCI login, in your own terminal; Codex says when it is needed."),
    ], size=12.5)
    repo(s, "AGENTS.md · .agents/skills/ · codex/README.md · codex/PROMPT-ops.md · evidence/codex/")
    notes(s, "Codex runs with workspace-write, not full access: it may read anywhere and write only to the demo's run state, kubectl's cache, Docker's socket and package caches. "
             "The recorded run is in evidence/codex/.")

    # 20 · on Kubernetes
    s = prs.slides.add_slide(blank)
    header(s, "The gateway and the classifier as two services on OKE", "On Kubernetes")
    figure(s, "figure5-kubernetes.png", 2.4, 1.6, 8.5)
    repo(s, "scripts/oci/up.sh · scripts/oci/deploy.sh · deploy/k8s/litellmdemo.yaml · scripts/oci/down.sh")
    notes(s, "Instance principal: the node signs, no key or token in the cluster; Workload Identity would scope it to the pod and needs an Enhanced cluster. "
             "Kill the classifier pod during a request: the plugin declines within 3 s, LiteLLM routes to fallback_tier MEDIUM, the request still answers. "
             "No registry: stock python image, pinned packages via an init container, code and the 7 KB head as ConfigMaps. "
             "Measured on the cluster (evidence/oke-run.json): route probes 11/11, use cases 13/13, browser test 20/20, 70-minute token-rotation soak 24/24; a classifier outage answered on MEDIUM; a killed pod is replaced in about 20 s; classification 79 ms median on one Ampere core.")

    # 21 · field notes
    s = prs.slides.add_slide(blank)
    header(s, "What cost real time", "Field notes")
    table(s, 0.72, 1.85, 11.9, [
        ["Where", "What we found"],
        ["Complexity router · Gemini, Llama 4", "It sets max_tokens from the model map: 65,536 for Gemini (OCI accepts less), 8,192 for Llama 4 (OCI allows 4,096). Every request fell back silently. Declare max_output_tokens."],
        ["Cohere vision", "LiteLLM sends cohere.* in Cohere format; OCI rejects it for command-a-vision. Route images to Gemini or Llama 4."],
        ["Model catalog", "Listed is not served everywhere: Grok 4 and Grok Code returned 404 on demand. Codex answers only on OCI's Responses API: a small LiteLLM custom provider translates chat requests to it."],
        ["LLM classifier", "Its default timeout is 3 s; GPT-5 nano took longer, so it silently fell back to the heuristic. Use the fastest model (Flash-Lite) and a longer timeout."],
        ["GPT-6 and tools", "OCI serves GPT-6 with reasoning on and refuses function tools; reasoning_effort none, sent only with tools, fixes it. GPT-6.1-sol refuses tools on chat completions at any effort, so it left the strong route."],
        ["Agent requests", "The agent's system prompt and tool turns drowned the request: every prompt looked alike, and Spanish read as English. Classify the user turns only."],
        ["Labels", f"Only 63% of prompts were label-stable across three runs ({stable_pct}% with today's models). Predict each route's pass probability, not one label."],
        ["A model leaves a route", "Its answers stay in the labels: 22% of the strong route's label runs were GPT-6.1-sol's. label.py --redo runs every one of them again with the current models."],
        ["OKE signing", "Instance-principal signing failed after ~20 minutes: LiteLLM's do_request_sign() skips the SDK's token refresh. Refresh in the pre-call hook."],
        ["OKE on a corporate network", "NAT sent port 6443 out of a different address than web traffic; the API allowlist must use the address seen on 6443."],
        ["Keep-alive", "The control room's client and LiteLLM's server both keep idle connections 5 s; a request on a just-closed one failed at once and marked a healthy gateway down. Expire idle connections at 2 s; retry a stale one once."],
    ], col_w=[3.0, 8.9], size=9.5)
    notes(s, "The first is worth an upstream fix: OCI-specific max_output_tokens in the model map.")

    # 22 · upstream
    s = prs.slides.add_slide(blank)
    header(s, "For the LiteLLM team", "What we would send upstream")
    table(s, 0.72, 1.85, 11.9, [
        ["Found", "Proposal", "Kind"],
        ["Instance, resource and workload principals stop signing after ~20 min: LiteLLM calls do_request_sign(), which skips the SDK's token refresh (only __call__ refreshes)", "Refresh before signing (signer._reset_signers() or sign via __call__); we patch it in our hook today", "provider fix"],
        ["OCI Gemini rejects max_tokens 65,536; OCI Llama 4 allows 4,096, the map says 8,192", "OCI-specific max_output_tokens in model_prices_and_context_window.json, so the complexity router stops failing over silently", "model map PR"],
        ["cohere.command-a-vision is sent in Cohere format; OCI rejects it", "Send vision-capable Cohere models in the generic format", "provider fix"],
        ["The classifier sees the whole conversation: an agent's system prompt and tool turns drowned the request", "Pass the user turns (or the last one) to classifier plugins, or document it", "router change"],
        ["The LLM classifier's 3 s timeout falls back to the heuristic with no error", "Log a warning and count classifier fallbacks; the cause header already exists", "observability"],
        ["We run the classifier as its own service", "classifier_type: http (URL + timeout), declining to fallback_tier on error: our plugin, offered as is", "feature"],
        ["A plugin's explanation is lost: routing_decision records only classifier-plugin:<tier>, and the response hook sees a copy of the metadata", "Let classify() return signals into routing_decision (we carry ours in x-litellm-route-decision today)", "router change"],
        ["Tool requests reach deployments that write tool calls as text (Llama 4 Scout on OCI)", "Finish the pre-call TODO: skip deployments without supports_function_calling when tools are sent", "router change"],
        ["The OCI provider speaks only the chat API; Codex models are served on OCI's Responses API", "OCI Responses support in the provider (we ship a CustomLLM for it today)", "provider"],
        ["The model map lacks the newer OCI models (cost is None) and prices OCI Gemini 2.5 Flash at $0.15 / $0.60; OCI's list says $0.30 / $2.50", "Refresh OCI entries from OCI's public price-list API", "model map PR"],
        ["OTel v2 reports provider \"oci\"", "gen_ai.provider.name = oracle_cloud.generative_ai: BerriAI/litellm#41824, open", "open PR"],
    ], col_w=[4.3, 6.0, 1.6], size=8.5)
    notes(s, "Each row has evidence in the repo: README field notes, evidence/, and the plugin in gateway/trained_classifier.py. Ask which they want as PRs first.")

    # 23 · next
    s = prs.slides.add_slide(blank)
    header(s, "From a laptop to an OCI GPU", "What is next")
    steps(s, 0.72, 1.95, 11.9, 2.8, [
        ("More data", "Thousands of prompts from real traffic logs (redacted), labelled by the same outcome contract; first where the router is wrong: constrained arithmetic.", TEAL),
        ("Bigger model", "Fine-tune the encoder (+8 points in an earlier test, in 47 s) or a small LLM on an OCI GPU, with the same scripts.", INDIGO),
        ("Serve it", "As an OCI Data Science model deployment or a vLLM endpoint; plugged in with custom or oss_classifier.", RED),
        ("Close the loop", "Log every decision and its outcome; retrain on what the gateway learns.", GREEN),
    ])
    text(s, 0.72, 5.05, 11.9, 1.2, [[("Nothing in the gateway changes: ", {"bold": True, "color": INK, "size": 14}),
        ("the classifier plugs in behind the same classify() contract, and the routes, tags and fallbacks stay as they are.", {"color": BODY, "size": 13.5})]], line=1.15)
    notes(s, "Any GPU work needs an explicit go-ahead; the demo runs on a laptop or on the one-node OKE cluster, plus OCI GenAI.")

    # 22 · conclusion
    s = prs.slides.add_slide(blank)
    rect(s, 0, 0, 13.333, 7.5, TEAL)
    text(s, 0.72, 0.7, 11.9, 0.35, "CONCLUSION", size=12, color=YELLOW, bold=True, spacing=200)
    text(s, 0.72, 1.15, 11.9, 1.7, [[("The right model for every request", {"size": 34, "bold": True, "color": WHITE})],
        [("LiteLLM makes every OCI model one API; routing makes each request go to the cheapest model that does it well; a classifier we trained in seconds decides which.", {"size": 15, "color": WHITE})]], line=1.15)
    closing = [("1  One gateway", "LiteLLM gives every OCI model one API, with keys, budgets, fallbacks and cost tracking built in."),
               ("2  Route and isolate", "LiteLLM classifies, routes, signs and accounts; the agent in OpenShell holds no key at all."),
               ("3  Train your router", "Label by outcome, mini-train, plug in as classifier_type custom.")]
    for i, (t, b) in enumerate(closing):
        x = 0.72 + i * 4.12
        rect(s, x, 3.85, 3.86, 1.9, RGBColor(0x03, 0x45, 0x5C), line=RGBColor(0x0B, 0x63, 0x80))
        rect(s, x, 3.85, 3.86, 0.07, YELLOW)
        text(s, x + 0.22, 4.05, 3.42, 2.0, [[(t, {"bold": True, "size": 16, "color": WHITE})], [(b, {"size": 12.5, "color": RGBColor(0xD8, 0xE6, 0xEA)})]], line=1.15)
    text(s, 0.72, 6.6, 11.9, 0.5, "Every number on these slides comes from a file in the repository's evidence/ and classifier/ folders.", size=15, color=YELLOW, bold=True)
    text(s, 0.72, 7.08, 11.9, 0.3, FOOTER, size=8, color=RGBColor(0xC8, 0xD6, 0xDB))
    notes(s, "Close on the method: one gateway, routing in config, a classifier trained on outcomes.")

    # appendix · the classifier in depth, behind the conclusion
    s = prs.slides.add_slide(blank)
    rect(s, 0, 0, 13.333, 7.5, TEAL)
    text(s, 0.72, 2.6, 11.9, 0.4, "APPENDIX", size=13, color=YELLOW, bold=True, spacing=220)
    text(s, 0.72, 3.1, 11.9, 1.0, "The classifier in depth", size=40, color=WHITE, bold=True)
    text(s, 0.72, 4.2, 11.9, 0.6, "Did we really train it, and does it hold up on prompts nobody trained on?", size=16, color=WHITE)
    text(s, 0.72, 7.08, 11.9, 0.3, FOOTER, size=8, color=RGBColor(0xC8, 0xD6, 0xDB))
    notes(s, "For questions. The talk keeps the classifier to one use of LiteLLM's plugin point; these slides are the depth behind it.")
    ids = prs.slides._sldIdLst
    for moved in appendix:
        el = next(e for e in ids if int(e.get("id")) == moved.slide_id)
        ids.remove(el)
        ids.append(el)

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    print("wrote", out, len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path.home() / "Documents" / "LiteLLM-OCI-Routing-FY26.pptx")
    a = ap.parse_args()
    build(a.template.expanduser(), a.out)
