"""The ladder router: predict how likely each route's answer is good enough, then pick the best value.

For a request, two predictors estimate P(pass) for every route on the ladder
(SIMPLE, MEDIUM, COMPLEX, REASONING), where "pass" is the labelling contract:
the judge scores the answer at least 4 of 5 on correctness, completeness and
instruction-following.

- a logistic model per route on the request's embedding and a few difficulty
  signals (length, numbers, step and constraint words), trained on fractional
  outcomes: a prompt whose cheap answer passed 2 of 3 label runs counts 2/3 pass;
- precedent: the similarity-weighted pass rates of the k most similar labelled
  requests.

Their average is the pass probability. The route is the cheapest one (by
typical cost) whose pass probability reaches the quality bar; when none does,
the one most likely to pass. A higher bar buys better answers, a lower bar
spends less. (A linear "P(pass) - dial * cost" rule did as well on average but
made indefensible single choices: a planning task sent to the cheapest model
at 54% likely to pass.) train.py fits it and picks the default bar;
router_model.py runs it; ladder_lab.py compares predictors.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

ROUTES = ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING")
K = 12            # precedent: neighbours per request
SHARPNESS = 8     # precedent: similarity ** SHARPNESS weights the nearest far more
C_REG = 2.0       # logistic models: inverse regularisation strength

STEP_WORDS = re.compile(r"\b(then|step|steps|first|second|finally|constraint|constraints|must|cannot|at most|at least|"
                        r"prove|derive|optimi[sz]e|schedule|minimi[sz]e|maximi[sz]e|scenario|scenarios|trade-?offs?|"
                        r"compare|plan|budget|forecast)\b", re.I)
SIGNALS = ("log length", "log words", "numbers per 10 words", "questions", "step/constraint words", "list items", "code")


def signals(text: str) -> list[float]:
    """Cheap, explainable difficulty signals the embedding carries poorly."""
    words = len(text.split())
    return [float(np.log1p(len(text))), float(np.log1p(words)),
            len(re.findall(r"\d+(?:[.,]\d+)?", text)) / max(1, words) * 10, float(text.count("?")),
            float(len(STEP_WORDS.findall(text))), float(len(re.findall(r"^\s*(?:[-*•]|\d+[.)])", text, re.M))),
            float(bool(re.search(r"```|def |SELECT |function |class ", text)))]


def outcomes(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Pass rate and cost per prompt and route, shape (prompts, routes), from the outcome labels."""
    P = np.zeros((len(rows), len(ROUTES)))
    C = np.zeros((len(rows), len(ROUTES)))
    for i, r in enumerate(rows):
        for j, route in enumerate(ROUTES[:3]):
            t = next(x for x in r["tiers"] if x["tier"] == route)
            P[i, j], C[i, j] = t.get("pass_rate", float(t["passed"])), t["cost"]
        P[i, 3], C[i, 3] = float(r["reasoning"]["passed"]), r["reasoning"]["cost"]
    return P, C


def fit(E: np.ndarray, texts: list[str], P: np.ndarray, C: np.ndarray) -> dict:
    from sklearn.linear_model import LogisticRegression

    S = np.array([signals(t) for t in texts])
    mean, std = S.mean(0), S.std(0) + 1e-9
    X = np.c_[E, (S - mean) / std]
    coef, intercept = np.zeros((len(ROUTES), X.shape[1])), np.zeros(len(ROUTES))
    for j in range(len(ROUTES)):
        y = np.r_[np.ones(len(X)), np.zeros(len(X))]
        w = np.r_[P[:, j], 1 - P[:, j]] + 1e-6
        m = LogisticRegression(max_iter=5000, C=C_REG).fit(np.r_[X, X], y, sample_weight=w)
        coef[j], intercept[j] = m.coef_[0], m.intercept_[0]
    typical = C.mean(0)
    return {"coef": coef, "intercept": intercept, "signal_mean": mean, "signal_std": std,
            "precedent_vectors": E.astype(np.float16), "precedent_pass": P.astype(np.float32),
            "typical_cost": typical, "cost_scale": np.array(typical.mean())}


def predict(params: dict, E: np.ndarray, texts: list[str]) -> dict:
    S = (np.array([signals(t) for t in texts]) - params["signal_mean"]) / params["signal_std"]
    logistic = 1 / (1 + np.exp(-(np.c_[E, S] @ params["coef"].T + params["intercept"])))
    sims = E @ params["precedent_vectors"].T
    idx = np.argsort(-sims, axis=1)[:, :K]
    w = np.clip(np.take_along_axis(sims, idx, axis=1), 0, None) ** SHARPNESS + 1e-12
    precedent = np.einsum("nk,nkr->nr", w, params["precedent_pass"][idx]) / w.sum(1, keepdims=True)
    return {"pass": (logistic + precedent) / 2, "logistic": logistic, "precedent": precedent, "neighbours": idx}


def choose(params: dict, pass_probability: np.ndarray, bar: float, routes: list[str] | None = None) -> np.ndarray:
    """Cheapest allowed route with P(pass) >= bar; the most likely allowed route when none clears it.

    `routes` (default: params["routes"] when trained with a route set, else all) limits
    the ladder: a route that costs as much as a better one is never worth climbing to.
    """
    p = np.atleast_2d(pass_probability)
    allowed = routes or [str(r) for r in params.get("routes", ROUTES)]
    idx = [ROUTES.index(r) for r in allowed]
    order = sorted(idx, key=lambda j: params["typical_cost"][j])
    clears = p[:, order] >= bar
    best = np.array(idx)[np.argmax(p[:, idx], axis=1)]
    return np.where(clears.any(1), np.array(order)[np.argmax(clears, axis=1)], best)


def save(params: dict, path: Path) -> None:
    np.savez_compressed(path, **params)


def load(path: Path) -> dict:
    """Load for serving: precedent vectors are stored as float16 (half the size) and widened once here."""
    with np.load(path) as z:
        params = {k: z[k] for k in z.files}
    params["precedent_vectors"] = params["precedent_vectors"].astype(np.float32)
    return params
