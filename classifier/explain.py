"""Why a request got its route, from evidence rather than a story.

    from classifier.explain import explain
    explain(messages)   # -> {"decision", "checks", "precedent", "meaning", "summary"}

The explanation retraces what `RouterModel.classify` did, check by check:

1. the rules, in order (image, length, language), with what each saw;
2. for requests the rules pass on, the model's probabilities and how close
   the call was;
3. precedent: the most similar labelled training requests, with what the
   outcome labels recorded for them (which routes' answers passed the judge,
   in how many of the label runs, and what they cost);
4. what the route means: its outcome contract.

Nothing here asks a model to justify the route after the fact; every sentence
is built from the classifier's own numbers and the labels on file.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from classifier.router_model import (LONG_CONTEXT_CHARS, MIN_LANGUAGE_CONFIDENCE, MIN_LETTERS, language_confidence,
                                     learned_label, shared, text_of)

LABELS = Path(__file__).resolve().parent / "data" / "labels.jsonl"
LADDER = ("SIMPLE", "MEDIUM", "COMPLEX")
MEANING = {
    "SIMPLE": "The cheapest models answer requests like this well: on similar requests their answers scored at least "
              "4 of 5 on correctness, completeness and instruction-following.",
    "MEDIUM": "The cheapest models fall short on requests like this, and the balanced models pass.",
    "REASONING": "Neither the cheap, the balanced nor the strong models reliably pass requests like this; "
                 "they need a model that reasons before answering.",
    "CODE": "Writing, reviewing, explaining or debugging code or SQL goes to the code models.",
    "VISION": "The request carries an image, so only image-capable models can answer it.",
    "LONG_CONTEXT": "The request is longer than about 30k tokens, so it goes to models with a long context window.",
    "MULTILINGUAL": "The request is not in English, so it goes to the model chosen for other languages.",
}
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French", "de": "German", "ja": "Japanese", "pt": "Portuguese",
                  "it": "Italian", "zh": "Chinese", "en": "English", "af": "Afrikaans", "da": "Danish", "nl": "Dutch"}

_lock = threading.Lock()
_index: dict | None = None


def _load_index() -> dict:
    """Embeddings of every labelled prompt, rebuilt when labels.jsonl changes."""
    global _index
    with _lock:
        stamp = LABELS.stat().st_mtime
        if _index is None or _index["stamp"] != stamp:
            rows = [json.loads(line) for line in LABELS.read_text().splitlines()]
            vectors = shared().embed([r["prompt"][:4000] for r in rows])
            _index = {"stamp": stamp, "rows": rows, "vectors": np.asarray(vectors)}
        return _index


def _precedent_of(row: dict, similarity: float) -> dict:
    tiers = []
    for t in sorted(row.get("tiers", []), key=lambda t: LADDER.index(t["tier"]) if t["tier"] in LADDER else 9):
        rate = t.get("pass_rate", 1.0 if t["passed"] else 0.0)
        tiers.append({"route": t["tier"], "deployment": t.get("deployment"), "pass_rate": round(rate, 2),
                      "cost": t.get("cost")})
    return {"prompt": row["prompt"][:220] + ("…" if len(row["prompt"]) > 220 else ""),
            "similarity": round(float(similarity), 3), "label": row["route"],
            "learned_as": learned_label(row["route"]), "votes": row.get("votes"),
            "source": row.get("label_source"), "tiers": tiers}


def _language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def explain(messages: list[dict], k: int = 3) -> dict:
    decision = shared().classify(messages)
    text, image = text_of(messages)
    letters = sum(ch.isalpha() for ch in text)
    lang, lang_conf = language_confidence(text)
    checks = [
        {"check": "image", "fired": image, "saw": "an image part" if image else "no image"},
        {"check": "length", "fired": len(text) > LONG_CONTEXT_CHARS,
         "saw": f"{len(text):,} characters (limit {LONG_CONTEXT_CHARS:,})"},
        {"check": "language", "fired": decision.route == "MULTILINGUAL",
         "saw": (f"too short to tell ({letters} letters, needs {MIN_LETTERS})" if letters < MIN_LETTERS else
                 f"{_language_name(lang)} at {lang_conf:.0%} confidence"
                 + ("" if lang == "en" or lang_conf >= MIN_LANGUAGE_CONFIDENCE else
                    f", below {MIN_LANGUAGE_CONFIDENCE:.0%}: treated as English"))},
    ]
    rule = next((c for c in checks if c["fired"]), None)
    if rule:
        checks = checks[:checks.index(rule) + 1]   # the first rule that fires decides; later checks never run
    else:
        checks.append({"check": "model", "fired": True,
                       "saw": ", ".join(f"{r} {p:.0%}" for r, p in decision.probabilities.items())})

    precedent: list[dict] = []
    if text.strip():
        index = _load_index()
        sims = index["vectors"] @ np.asarray(shared().embed([text[:4000]]))[0]
        precedent = [_precedent_of(index["rows"][i], sims[i]) for i in np.argsort(-sims)[:k]]

    return {"decision": decision.as_dict(), "checks": checks, "precedent": precedent,
            "meaning": MEANING.get(decision.route, ""), "summary": _summary(decision, rule, precedent, lang, lang_conf)}


def _summary(decision, rule, precedent, lang, lang_conf) -> str:
    route = decision.route
    if rule and rule["check"] == "image":
        return f"It carries an image, so the image rule sent it to {route} before the model ran."
    if rule and rule["check"] == "length":
        return f"It is longer than the context limit for ordinary routes, so the length rule sent it to {route}."
    if rule and rule["check"] == "language":
        return f"It is written in {_language_name(lang)} ({lang_conf:.0%} sure), so the language rule sent it to {route}."
    if decision.criterion.startswith("fallback"):
        return f"The classifier could not decide ({decision.criterion}), so the gateway used its fallback route."
    probs = list(decision.probabilities.items())
    (top, p1), (second, p2) = probs[0], probs[1]
    call = "a close call" if p1 - p2 < 0.05 else "a clear lead" if p1 - p2 >= 0.15 else "a modest lead"
    parts = [f"The model chose {top} at {p1:.0%} against {second} at {p2:.0%}: {call}."]
    same = [p for p in precedent if p["learned_as"] == top]
    if same:
        parts.append(f"{len(same)} of the {len(precedent)} most similar training requests were labelled {top}.")
    if top == "SIMPLE":
        cheap = [t["pass_rate"] for p in precedent for t in p["tiers"] if t["route"] == "SIMPLE"]
        if cheap:
            parts.append(f"On them the cheapest models passed the judge in {np.mean(cheap):.0%} of label runs.")
    elif top == "MEDIUM":
        cheap = [t["pass_rate"] for p in precedent for t in p["tiers"] if t["route"] == "SIMPLE"]
        mid = [t["pass_rate"] for p in precedent for t in p["tiers"] if t["route"] == "MEDIUM"]
        if cheap and mid:
            parts.append(f"On them the cheapest models passed {np.mean(cheap):.0%} of the time, the balanced models {np.mean(mid):.0%}.")
    return " ".join(parts)
