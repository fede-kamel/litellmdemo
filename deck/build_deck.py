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


def figure(slide, name, x, y, w, caption=None, frame=True):
    path = FIG / name
    if frame:
        rect(slide, x - 0.08, y - 0.08, w + 0.16, 0.1, WHITE)  # placeholder, resized below
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
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
    """Where to find it: the files behind the slide, so every claim is code you can open."""
    text(slide, 0.72, 6.72, 11.9, 0.3, [[("In the repo:  ", {"bold": True, "color": RED, "size": 10.5}),
                                         (paths, {"font": MONO, "color": BODY, "size": 10})]])


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


def versus(slide, y, h, left, right, left_items, right_items, size=12.5):
    """Two columns: without (red) and with (green)."""
    for i, (title, items, accent) in enumerate(((left, left_items, RED), (right, right_items, GREEN))):
        x = 0.72 + i * 6.05
        rect(slide, x, y, 5.85, h, SAND, line=CARD_LINE)
        rect(slide, x, y, 5.85, 0.07, accent)
        text(slide, x + 0.22, y + 0.2, 5.4, 0.4, title, size=15, color=accent, bold=True)
        paras = [[("✕  " if i == 0 else "✓  ", {"bold": True, "color": accent, "size": size}), (a + " ", {"bold": True, "color": INK, "size": size}),
                  (b, {"color": BODY, "size": size})] for a, b in items]
        box = text(slide, x + 0.22, y + 0.7, 5.4, h - 0.85, paras, line=1.12)
        for p in box.text_frame.paragraphs:
            p.space_after = Pt(8)


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def shot(slide, name, x, y, w, caption=None):
    if (SHOTS / name).exists():
        figure(slide, f"../screenshots/{name}", x, y, w, caption)


# ------------------------------------------------------------------- slides --

def build(template: Path, out: Path) -> None:
    prs = Presentation(str(template))
    drop_all_slides(prs)
    blank = layout(prs, "Light - Blank")
    meta = load(ROOT / "classifier" / "model" / "meta.json")
    ev = load(EVIDENCE / "classifier-eval.json")

    # 1 · cover
    s = prs.slides.add_slide(layout(prs, "Title/Cover_5"))
    for ph in s.placeholders:
        if ph.placeholder_format.idx == 0:
            ph.text = "The Right Model for Every Request"
        elif ph.name.startswith("Text Placeholder 2"):
            ph.text = "Built on LiteLLM's router, across fifteen OCI models"
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
              ("The architecture", "one gateway between every app and every model", "5"),
              ("Why route", "the price spread, the toolbox, the use cases, the criteria", "6–9"),
              ("The classifier", "where it sits, how we trained it, whether it pays", "10–15"),
              ("Live demo", "the routing control room, then back to the slides", "16–19"),
              ("Built with Codex, run on OKE", "skills as the harness; Kubernetes; field notes; what we would upstream", "20–25")]
    for i, (t, sub, pages) in enumerate(agenda):
        y = 1.85 + i * 0.7
        rect(s, 0.72, y, 11.9, 0.6, SAND if i % 2 == 0 else WHITE, line=CARD_LINE)
        rect(s, 0.72, y, 0.07, 0.6, RED if t in ("The classifier", "Live demo") else TEAL)
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
        ["Vision", "Llama 4, Gemini 2.5, Command A vision", "the VISION route (Gemini Flash, Llama 4 Maverick)"],
        ["Reasoning controls", "Gemini 2.5, GPT-5, Grok", "the REASONING route (Grok 4.20 reasoning, o3)"],
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
    notes(s, "Left: anything that speaks the OpenAI API, including our langchain-oci agent and Codex. Middle: one process with one config file. Right: fifteen OCI models across five vendors.")

    # 6 · why route
    s = prs.slides.add_slide(blank)
    header(s, "Not every request needs the strongest model", "Why route")
    table(s, 0.72, 1.85, 6.3, [
        ["Model on OCI", "$ per 1M output tokens"],
        ["Gemini 2.5 Flash-Lite", "0.30"], ["GPT-5 nano", "0.40"], ["Llama 4 Scout", "0.72"],
        ["GPT-5 mini", "2.00"], ["Grok 4.20 reasoning", "2.50"], ["o3", "8.00"],
        ["Gemini 2.5 Pro", "10.00"], ["GPT-5.2", "14.00"],
    ], col_w=[3.8, 2.5], size=12)
    pct = None
    labels = ROOT / "classifier" / "data" / "labels.jsonl"
    if labels.exists():
        rows = [json.loads(line) for line in labels.read_text().splitlines()]
        diff = [r for r in rows if r.get("label_source") == "outcome"]
        pct = round(100 * sum(r["route"] == "SIMPLE" for r in diff) / max(1, len(diff)))
    card(s, 7.3, 1.85, 5.3, 2.05, "A 47× price spread", "from the cheapest to the most expensive model in the same gateway, for the same request.", accent=TEAL)
    card(s, 7.3, 4.15, 5.3, 2.3, f"{pct}% passed on the cheapest route" if pct else "Most requests are easy",
         "When three routes answered the same 208 prompts and a judge graded them, the cheapest answer was good enough for most of them. Sending everything to the strongest model pays for quality nobody needed.", accent=RED)
    notes(s, "Prices are list prices from LiteLLM's model map for each model (OCI entries where present, the provider's own otherwise). The 62% comes from our outcome labels, slide 13.")

    # 7 · the routing toolbox
    s = prs.slides.add_slide(blank)
    header(s, "Five kinds of decision, all in config", "LiteLLM's routing toolbox")
    table(s, 0.72, 1.85, 11.9, [
        ["What decides", "LiteLLM feature", "In this demo"],
        ["what the request needs", "complexity router + a classifier", "eight routes: SIMPLE … MULTILINGUAL"],
        ["who is calling", "tag routing, team routing", "oci-chat: premium tag → GPT-5.2, default → Gemini Flash"],
        ["the prompt does not fit", "context-window check and fallback", "oci-compact (2k window) → oci-long, before the call"],
        ["a deployment fails", "fallbacks, retries, cooldowns", "oci-flaky always fails → oci-balanced; every route has a backup"],
        ["several can serve", "load balancing: latency, cost, usage, weights", "two vendors per route, latency-based"],
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
        ["Customer support", "FAQ · billing dispute · SLA escalation", "SIMPLE · MEDIUM · REASONING", "Llama 4 Scout · GPT-5 mini · Grok 4.20"],
        ["Coding assistant", "explain a line · debug a race condition", "CODE", "GPT-5.1, backup Grok 4.3"],
        ["Analyst", "one number · a forecast under a cap", "SIMPLE · REASONING", "Flash-Lite · Grok 4.20 / o3"],
        ["Document analysis", "a 300-page contract", "LONG_CONTEXT", "Gemini 2.5 Flash (1M tokens)"],
        ["Multilingual service", "Spanish, Japanese, French …", "MULTILINGUAL", "Cohere Command A"],
        ["Vision", "a photo of an invoice", "VISION", "Gemini 2.5 Flash · Llama 4 Maverick"],
        ["Premium customer", "the same request, a premium contract", "tag: premium", "GPT-5.2"],
        ["Resilience", "a model is down", "fallback", "the next group, no app change"],
    ], col_w=[2.3, 3.8, 2.7, 3.1], size=11.5)
    repo(s, "app/scenarios.py (each use case, with the route it should take)")
    notes(s, "Every row is a button in the control room. Northwind Cloud is a fictional company; no real customer data.")

    # 9 · the criteria
    s = prs.slides.add_slide(blank)
    header(s, "What decides a route", "The criteria")
    for i, (t, b, c) in enumerate([
        ("1 · Facts in the request", "Checked by rules, exactly: an image goes to VISION; a very long prompt to LONG_CONTEXT; a language other than English to MULTILINGUAL.", OCHRE),
        ("2 · What the request needs", "Learned by our classifier from outcomes: the cheapest route whose answer passes a judge on correctness, completeness and instruction-following.", RED),
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
    header(s, "Inside the gateway, before any model is called", "Where the classifier sits")
    figure(s, "figure2-classifier-path.png", 2.4, 1.65, 8.5)
    repo(s, "gateway/trained_classifier.py · classifier/router_model.py")
    notes(s, "LiteLLM's complexity router calls our plugin's classify(context) and gets back a route name; the route names a group; the group picks a deployment with latency, context-window and fallback logic.")

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

    # 13 · results: accuracy
    s = prs.slides.add_slide(blank)
    header(s, "A routing head trained on frozen embeddings, scored on prompts it never saw", "How accurate is it?")
    if meta:
        cm = meta["confusion_matrix"]
        rows_cm = [["right route \\ predicted", *cm["labels"]]] + [[cm["labels"][i], *row] for i, row in enumerate(cm["rows_true_cols_predicted"])]
        table(s, 0.72, 1.85, 6.6, rows_cm, col_w=[1.9] + [1.175] * len(cm["labels"]), size=11)
        card(s, 7.6, 1.85, 5.0, 1.75, f"{round(meta['held_out_accuracy'] * 100)}% on {meta['held_out']} unseen prompts",
             f"cross-validated balanced accuracy {round(meta['cv_balanced_accuracy'] * 100)}%. Trained: a logistic-regression head, 1,540 weights, in {meta['train_seconds']} s. The encoder stays frozen.", accent=RED)
        rec = meta["held_out_recall"]
        card(s, 7.6, 3.85, 5.0, 2.6, "Recall per route",
             "  ·  ".join(f"{k} {round(v * 100)}%" for k, v in rec.items()) + ". Rules add 56 of 56 non-English requests, every image and every very long prompt.", accent=TEAL)
    notes(s, "Read the matrix honestly: CODE and REASONING are learned well; MEDIUM is the noisy middle, where a cheap model passes some of the time.")

    # 13b · did we really train it
    s = prs.slides.add_slide(blank)
    header(s, "Frozen encoder versus fine-tuning the encoder itself", "Did we really train the model?")
    ft = load(EVIDENCE / "finetune-comparison.json")
    if ft:
        table(s, 0.72, 1.85, 11.9, [
            ["", "What was trained", "Weights trained", "Held-out accuracy", "Balanced accuracy", "Time"],
            ["Frozen (shipped)", "the logistic-regression head", "1,540", f"{round(ft['frozen']['held_out_accuracy'] * 100, 1)}%",
             f"{round(ft['frozen']['held_out_balanced_accuracy'] * 100, 1)}%", "0.14 s, laptop CPU"],
            ["Fine-tuned", "every encoder weight, then the head", f"{ft['encoder_parameters'] / 1e6:.1f} M",
             f"{round(ft['fine_tuned']['held_out_accuracy'] * 100, 1)}%", f"{round(ft['fine_tuned']['held_out_balanced_accuracy'] * 100, 1)}%",
             f"{ft['fine_tuned']['fine_tune_seconds']:.0f} s, Mac GPU (MPS)"],
        ], col_w=[1.9, 3.1, 1.6, 1.8, 1.8, 1.7], size=12.5)
    bullets(s, 0.72, 3.7, 11.9, 2.8, [
        ("Yes, both are real training.", "The head is fitted by supervised learning on outcome labels; fine-tuning also moves the encoder's 117.6 million weights, SetFit-style (a triplet loss pulls prompts with the same route together)."),
        ("Fine-tuning helped, a little.", "About four more held-out prompts right out of 52. Two training schedules were tried and the better one kept, so read the gain as optimistic."),
        ("Why the frozen head ships.", "It rebuilds from a 7 KB file in a second; the fine-tuned encoder is 470 MB. With more labelled data, fine-tuning on an OCI GPU is the next step: same script."),
    ], size=13)
    repo(s, "classifier/train.py (frozen) · classifier/finetune.py (fine-tuned) · evidence/finetune-comparison.json")
    notes(s, "Answer to 'did we really train it?': yes. Be precise: the shipped router trains a head on frozen embeddings; the fine-tuning run trains the encoder too.")

    # 14 · results: does it pay
    s = prs.slides.add_slide(blank)
    header(s, "Quality and cost on the same held-out requests", "Does routing pay?")
    figure(s, "figure4-quality-cost.png", 2.4, 1.6, 8.5)
    repo(s, "evidence/classifier-eval.json · classifier/evaluate.py")
    if ev:
        pol = {p["policy"]: p for p in ev["policies"]}
        notes(s, "Policies on the held-out prompts: " + "; ".join(f"{p['policy']} {round(p['quality'] * 100)}% at ${p['cost_usd']:.3f}" for p in ev["policies"])
              + f". The trained router matches the LLM classifier's quality ({round(pol['llm']['quality'] * 100)}%) at "
              f"{round((1 - pol['trained']['cost_usd'] / pol['llm']['cost_usd']) * 100)}% less, with no classifier call per request.")

    # 15 · live demo divider
    s = prs.slides.add_slide(blank)
    rect(s, 0, 0, 13.333, 7.5, TEAL)
    text(s, 0.72, 2.2, 11.9, 0.4, "LIVE DEMO · SWITCH TO THE BROWSER", size=13, color=YELLOW, bold=True, spacing=220)
    text(s, 0.72, 2.7, 11.9, 1.0, "The routing control room", size=40, color=WHITE, bold=True)
    beats = ["Support: FAQ, billing, SLA escalation: watch the route climb from SIMPLE to REASONING",
             "Japanese and an invoice photo: decided by rules in under a millisecond",
             "Compare routers: the heuristic, the LLM classifier and ours on the same request",
             "A failing deployment: the fallback, with no change to the app",
             "The classifier and the gateway tabs: the training numbers and every route"]
    text(s, 0.72, 3.85, 11.9, 3.0, [[(f"{i + 1}   ", {"bold": True, "color": YELLOW, "size": 15}), (b, {"color": WHITE, "size": 15})] for i, b in enumerate(beats)], line=1.5)
    text(s, 0.72, 7.08, 11.9, 0.3, FOOTER, size=8, color=RGBColor(0xC8, 0xD6, 0xDB))
    notes(s, "Before the talk: scripts/gateway.sh running, uvicorn ui.server:app on 8780, OCI session fresh (it lasts about an hour). Fallback: the screenshots on the next slides.")

    # 16 · what you saw
    s = prs.slides.add_slide(blank)
    header(s, "Back to the slides", "What you just saw")
    table(s, 0.72, 1.85, 11.9, [
        ["In the demo", "What it shows", "Where it comes from"],
        ["the route climbing with the request", "the classifier deciding by need, not by default", "complexity router, classifier_type custom"],
        ["Japanese and an image in under 1 ms", "certain facts decided by rules, before the model", "classifier/router_model.py"],
        ["three routers, three answers", "the heuristic misroutes; ours does not", "oci-auto · oci-auto-llm · oci-auto-trained"],
        ["fallback ×1 on the card", "a failing model skipped, the app unchanged", "router_settings.fallbacks"],
        ["cost on every call", "spend per request, from the gateway", "x-litellm-response-cost"],
    ], col_w=[3.7, 4.6, 3.6], size=12)
    notes(s, "Land the demo, then show the screens in detail.")

    # 17 · the control room
    s = prs.slides.add_slide(blank)
    header(s, "Each model call, as the gateway routed it", "The control room")
    shot(s, "02-escalation.png", 0.72, 1.7, 7.2)
    bullets(s, 8.15, 1.85, 4.5, 4.9, [
        ("Route trace.", "Every call the agent makes: the route, the criterion, the OCI model, latency, cost, fallbacks."),
        ("The agent.", "langchain-oci create_oci_agent; its model is the gateway, asked for oci-auto-trained."),
        ("The classifier's view.", "Its probabilities next to the route it took."),
    ], size=13)
    repo(s, "app/agent.py · ui/server.py · web/src/components/ControlRoom.tsx")
    notes(s, "The UI is a thin client over the gateway's own headers.")

    # 18 · compare
    s = prs.slides.add_slide(blank)
    header(s, "Same request, three classifiers", "Compare routers")
    shot(s, "06-compare-crop.png", 0.72, 1.7, 11.9)
    repo(s, "POST /api/compare · web/src/components/Compare.tsx")
    notes(s, "The SLA escalation, live: the built-in heuristic calls it SIMPLE and Llama 4 Scout guesses the policy; the LLM classifier sends it to Gemini 2.5 Pro at 4.7x the cost; ours sends it to Grok 4.20 reasoning, which does the arithmetic.")

    # 19 · codex
    s = prs.slides.add_slide(blank)
    header(s, "A coding agent operates the gateway from a spec and four skills", "Built and run with Codex")
    table(s, 0.72, 1.85, 7.4, [
        ["Skill (.agents/skills/)", "What it teaches Codex"],
        ["litellm-oci-gateway", "start and change the gateway; OCI signing; the OCI quirks"],
        ["litellm-oci-routing", "which routing feature fits which need; reading the headers"],
        ["litellm-route-classifier", "generate, label by outcome, train, evaluate, plug in"],
        ["litellm-route-verify", "probes, end-to-end, browser test, evidence without secrets"],
    ], col_w=[2.9, 4.5], size=12)
    bullets(s, 8.4, 1.85, 4.25, 4.8, [
        ("Skills, not a giant prompt.", "Codex loads a skill when the task needs it, in the open SKILL.md format."),
        ("A spec with checkpoints.", "codex/SPEC.md: preflight, start, probe, classifier, control room, report."),
        ("Rules it cannot override.", "AGENTS.md: no secrets, local only, no spend without asking, never edit code to pass a check."),
    ], size=13)
    repo(s, "codex/SPEC.md · codex/PROMPT.md · AGENTS.md · .agents/skills/")
    notes(s, "Same method as the Deep Agents demo: the harness is a spec plus skills, and Codex's transcripts are the evidence.")

    # 20 · on Kubernetes
    s = prs.slides.add_slide(blank)
    header(s, "The gateway and the classifier as two services on OKE", "On Kubernetes")
    figure(s, "figure5-kubernetes.png", 2.4, 1.6, 8.5)
    repo(s, "scripts/oci/up.sh · scripts/oci/deploy.sh · deploy/k8s/litellmdemo.yaml · scripts/oci/down.sh")
    notes(s, "Instance principal: the node signs, no key or token in the cluster; Workload Identity would scope it to the pod and needs an Enhanced cluster. "
             "Kill the classifier pod during a request: the plugin declines within 1.5 s, LiteLLM routes to fallback_tier MEDIUM, the request still answers. "
             "No registry: stock python image, pinned packages via an init container, code and the 7 KB head as ConfigMaps. "
             "Measured on the cluster (evidence/oke-run.json): route probes 11/11, browser test 14/14, use cases 11/13; the pod-kill run answered on MEDIUM during the outage and routed CODE again after.")

    # 21 · field notes
    s = prs.slides.add_slide(blank)
    header(s, "What cost real time", "Field notes")
    table(s, 0.72, 1.85, 11.9, [
        ["Where", "What we found"],
        ["Complexity router · Gemini", "It sets max_tokens from the model map (65,536); OCI's Gemini accepts < 65,536. Every SIMPLE request fell back silently. Declare max_output_tokens."],
        ["Complexity router · Llama 4", "The map says 8,192 output tokens; OCI allows 4,096. Same failure, same fix."],
        ["Cohere vision", "LiteLLM sends cohere.* in Cohere format; OCI rejects it for command-a-vision. Route images to Gemini or Llama 4."],
        ["Model catalog", "Listed is not served: Grok 4, Grok Code and the Codex models returned 404 on demand. Smoke-test before adding."],
        ["Prices", "Newer OCI models have no price-map entry: cost is None until you set it."],
        ["Open-source limit", "One router with custom routes per gateway."],
        ["LLM classifier", "Its default timeout is 3 s; GPT-5 nano took longer, so it silently fell back to the heuristic. Use the fastest model (Flash-Lite) and a longer timeout."],
        ["Labels", "The cheapest route passed 62% of prompts. Gemini 2.5 Pro thinks ~1.7k tokens, then answers tersely: the cheapest passing route for only 4 of 208."],
        ["Agent requests", "The agent's system prompt and tool turns drowned the request: every prompt looked alike, and Spanish read as English. Classify the user turns only."],
        ["OKE on a corporate network", "NAT sent port 6443 out of a different address than web traffic; the API allowlist must use the address seen on 6443."],
        ["Well-known is not hard", "Famous proofs (√2, infinitely many primes) pass on the cheapest model; the classifier learned SIMPLE for them. Constrained planning is what needs REASONING."],
    ], col_w=[3.0, 8.9], size=10)
    notes(s, "The first two are worth an upstream fix: OCI-specific max_output_tokens in the model map.")

    # 22 · upstream
    s = prs.slides.add_slide(blank)
    header(s, "For the LiteLLM team", "What we would send upstream")
    table(s, 0.72, 1.85, 11.9, [
        ["Found", "Proposal", "Kind"],
        ["OCI Gemini rejects max_tokens 65,536; OCI Llama 4 allows 4,096, the map says 8,192", "OCI-specific max_output_tokens in model_prices_and_context_window.json, so the complexity router stops failing over silently", "model map PR"],
        ["Newer OCI models have no price entry: cost is None", "Prices for the OCI GPT-5.x, Grok 4.x and Gemini 2.5 deployments we use", "model map PR"],
        ["cohere.command-a-vision is sent in Cohere format; OCI rejects it", "Send vision-capable Cohere models in the generic format", "provider fix"],
        ["The classifier sees the whole conversation: an agent's system prompt and tool turns drowned the request", "Pass the user turns (or the last one) to classifier plugins, or document it", "router change"],
        ["The LLM classifier's 3 s timeout falls back to the heuristic with no error", "Log a warning and count classifier fallbacks; the cause header already exists", "observability"],
        ["We run the classifier as its own service", "classifier_type: http (URL + timeout), declining to fallback_tier on error: our plugin, offered as is", "feature"],
        ["OTel v2 reports provider \"oci\"", "gen_ai.provider.name = oracle_cloud.generative_ai: BerriAI/litellm#41824, open", "open PR"],
    ], col_w=[4.3, 6.0, 1.6], size=10.5)
    notes(s, "Each row has evidence in the repo: README field notes, evidence/, and the plugin in gateway/trained_classifier.py. Ask which they want as PRs first.")

    # 23 · next
    s = prs.slides.add_slide(blank)
    header(s, "From a laptop to an OCI GPU", "What is next")
    steps(s, 0.72, 1.95, 11.9, 2.8, [
        ("More data", "Thousands of prompts from real traffic logs (redacted), labelled by the same outcome contract.", TEAL),
        ("Bigger model", "Fine-tune the encoder (finetune.py: +8 pts here, in 47 s) or a small LLM on an OCI GPU shape, same scripts.", INDIGO),
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
    closing = [("1  Read the blog", "LiteLLM natively supports OCI Generative AI: one gateway, every model family, signing handled."),
               ("2  Route by need", "Complexity router, tags, fallbacks and context-window checks: all in config."),
               ("3  Train your router", "Label by outcome, mini-train, plug in as classifier_type custom.")]
    for i, (t, b) in enumerate(closing):
        x = 0.72 + i * 4.12
        rect(s, x, 3.85, 3.86, 1.9, RGBColor(0x03, 0x45, 0x5C), line=RGBColor(0x0B, 0x63, 0x80))
        rect(s, x, 3.85, 3.86, 0.07, YELLOW)
        text(s, x + 0.22, 4.05, 3.42, 2.0, [[(t, {"bold": True, "size": 16, "color": WHITE})], [(b, {"size": 12.5, "color": RGBColor(0xD8, 0xE6, 0xEA)})]], line=1.15)
    text(s, 0.72, 6.6, 11.9, 0.5, "Every number on these slides comes from a file in the repository's evidence/ and classifier/ folders.", size=15, color=YELLOW, bold=True)
    text(s, 0.72, 7.08, 11.9, 0.3, FOOTER, size=8, color=RGBColor(0xC8, 0xD6, 0xDB))
    notes(s, "Close on the method: one gateway, routing in config, a classifier trained on outcomes.")

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    print("wrote", out, len(prs.slides._sldIdLst), "slides")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path.home() / "Documents" / "LiteLLM-OCI-Routing-FY26.pptx")
    a = ap.parse_args()
    build(a.template.expanduser(), a.out)
