"""The trained routing classifier: rules for hard facts, a small model for the rest.

Criteria, in order:
1. Rules on facts the request states outright: an image part routes to VISION;
   a prompt beyond LONG_CONTEXT_CHARS routes to LONG_CONTEXT; a prompt not in
   English (py3langid) routes to MULTILINGUAL.
2. Code: a logistic regression head on the request's embedding
   (multilingual-e5-small, run locally) recognises programming requests.
3. The ladder (classifier/ladder.py) for everything else: it predicts how
   likely each route's answer is to pass the judge and picks the cheapest
   route that clears the operator's quality bar. Trained on outcome labels
   (classifier/label.py): every route answered every prompt, judged.

`classify(messages)` returns the route, the criterion that decided it, the
class probabilities and the time it took. The LiteLLM plugin
(gateway/trained_classifier.py) and the web app both call it.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent / "model"
ENCODER = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "                 # what e5 encoders expect for a query
LONG_CONTEXT_CHARS = 120_000            # about 30k tokens
LEARNED = ("SIMPLE", "MEDIUM", "REASONING", "CODE")


def learned_label(route: str) -> str | None:
    """The label the model learns for an outcome label; None for rule-decided routes."""
    return {"COMPLEX": "REASONING"}.get(route, route) if route in (*LEARNED, "COMPLEX") else None


_identifier = None


MIN_LETTERS = 12
MIN_LANGUAGE_CONFIDENCE = 0.5


def language(text: str) -> str:
    """ISO code of the text's language; "en" unless the identifier is confident.

    Short or mostly numeric text ("What is 18 percent of 4,217.50?") gives
    py3langid little to go on, so the language rule needs a few words and 50%
    confidence before it overrides the model.
    """
    lang, confidence = language_confidence(text)
    return lang if lang == "en" or confidence >= MIN_LANGUAGE_CONFIDENCE else "en"


def language_confidence(text: str) -> tuple[str, float]:
    """py3langid's raw guess and its normalised confidence ("en", 0.0 for too few letters)."""
    global _identifier
    if sum(ch.isalpha() for ch in text) < MIN_LETTERS:
        return "en", 0.0
    if _identifier is None:
        from py3langid.langid import MODEL_FILE, LanguageIdentifier

        _identifier = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
    lang, confidence = _identifier.classify(text[:2000])
    return lang, float(confidence)


@dataclass
class Decision:
    route: str
    criterion: str                       # "rule: image", "rule: length", "rule: language (xx)", "model: code", "ladder", "fallback"
    probabilities: dict[str, float] = field(default_factory=dict)   # ladder: P(pass) per route; code: class probabilities
    milliseconds: float = 0.0
    details: dict = field(default_factory=dict)                     # ladder: the bar, the two predictors, costs

    def as_dict(self) -> dict:
        return asdict(self)


def text_of(messages: list[dict]) -> tuple[str, bool]:
    """The user's text in a chat request, and whether it carries an image.

    Only user turns count: an agent's system prompt and its tool-call turns are
    the same for every request and would drown the request itself.
    """
    parts: list[str] = []
    image = False
    for m in messages:
        if m.get("role", "user") not in ("user", "human"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for p in content:
                if isinstance(p, dict):
                    if p.get("type") in ("image_url", "input_image", "image"):
                        image = True
                    elif isinstance(p.get("text"), str):
                        parts.append(p["text"])
    return "\n".join(parts), image


class RouterModel:
    def __init__(self, model_dir: Path = MODEL_DIR):
        self.model_dir = model_dir
        self._lock = threading.Lock()
        self._encoder = None
        self._head = None
        self._ladder: dict | None = None
        self.meta: dict = {}

    @property
    def trained(self) -> bool:
        return (self.model_dir / "head.joblib").exists()

    def _load(self) -> None:
        if self._head is not None:
            return
        with self._lock:
            if self._head is not None:
                return
            import joblib
            from sentence_transformers import SentenceTransformer

            self.meta = json.loads((self.model_dir / "meta.json").read_text())
            self._encoder = SentenceTransformer(self.meta.get("encoder", ENCODER), device="cpu")
            self._head = joblib.load(self.model_dir / "head.joblib")
            if (self.model_dir / "ladder.npz").exists():
                from classifier import ladder

                self._ladder = ladder.load(self.model_dir / "ladder.npz")

    @property
    def default_bar(self) -> float:
        self._load()
        return float(self.meta.get("ladder", {}).get("bar", 0.8))

    def embed(self, texts: list[str]):
        self._load()
        return self._encoder.encode([QUERY_PREFIX + t for t in texts], normalize_embeddings=True, show_progress_bar=False)

    def classify(self, messages: list[dict], bar: float | None = None) -> Decision:
        started = time.perf_counter()
        text, image = text_of(messages)
        if image:
            return Decision("VISION", "rule: image", milliseconds=_ms(started))
        if len(text) > LONG_CONTEXT_CHARS:
            return Decision("LONG_CONTEXT", "rule: length", milliseconds=_ms(started))
        lang = language(text)
        if lang != "en":
            return Decision("MULTILINGUAL", f"rule: language ({lang})", milliseconds=_ms(started))
        if not self.trained:
            return Decision("MEDIUM", "fallback: no trained model", milliseconds=_ms(started))
        vector = self.embed([text[:4000]])
        probs = self._head.predict_proba(vector)[0]
        labels = list(self._head.classes_)
        ranked = dict(sorted(zip(labels, (round(float(p), 3) for p in probs), strict=True), key=lambda kv: -kv[1]))
        top = next(iter(ranked))
        if top == "CODE" or self._ladder is None:
            return Decision(top, "model: code" if top == "CODE" else "model", ranked, _ms(started))
        from classifier import ladder

        bar = self.default_bar if bar is None else float(bar)
        pred = ladder.predict(self._ladder, vector, [text[:4000]])
        p = pred["pass"][0]
        route = ladder.ROUTES[int(ladder.choose(self._ladder, pred["pass"], bar)[0])]
        r3 = lambda a: {k: round(float(v), 3) for k, v in zip(ladder.ROUTES, a, strict=True)}  # noqa: E731
        order = [ladder.ROUTES[i] for i in np.argsort(self._ladder["typical_cost"])]
        return Decision(route, "ladder", r3(p), _ms(started), {
            "bar": bar, "cost_order": order, "cleared": route in [r for r in order if p[ladder.ROUTES.index(r)] >= bar],
            "logistic": r3(pred["logistic"][0]), "precedent": r3(pred["precedent"][0]),
            "typical_cost": {k: round(float(v), 6) for k, v in zip(ladder.ROUTES, self._ladder["typical_cost"], strict=True)},
            "code_probability": ranked.get("CODE", 0.0)})


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


_shared: RouterModel | None = None


def shared() -> RouterModel:
    global _shared
    if _shared is None:
        _shared = RouterModel()
    return _shared
