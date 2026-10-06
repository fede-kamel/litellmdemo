"""Choose the ladder router on what matters: good answers per dollar, on prompts it never saw.

    uv run python classifier/ladder_lab.py      # -> evidence/ladder-lab.json

For every outcome-labelled prompt the labels hold, per route, how often its
answer passed the judge (SIMPLE, MEDIUM, COMPLEX: three runs; REASONING: one)
and what it cost. A ladder router predicts each route's pass probability and
sends the request to the cheapest route that clears a quality bar
(classifier/ladder.py). Predictions are 5-fold cross-validated: every prompt
is scored by a model that never saw it. The script compares predictors and
reports, for each, the frontier over bars and the cheapest bar that is at
least as good as always using the REASONING route.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.router_model import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "classifier" / "data"
ROUTES = ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING")
BARS = [0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def outcomes(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """pass rate and cost, shape (prompts, routes)."""
    P = np.zeros((len(rows), len(ROUTES)))
    C = np.zeros((len(rows), len(ROUTES)))
    for i, r in enumerate(rows):
        for j, route in enumerate(ROUTES[:3]):
            t = next(x for x in r["tiers"] if x["tier"] == route)
            P[i, j], C[i, j] = t.get("pass_rate", float(t["passed"])), t["cost"]
        P[i, 3], C[i, 3] = float(r["reasoning"]["passed"]), r["reasoning"]["cost"]
    return P, C


STEP_WORDS = re.compile(r"\b(then|and then|step|steps|first|second|finally|constraint|constraints|must|cannot|at most|"
                        r"at least|prove|derive|optimi[sz]e|schedule|minimi[sz]e|maximi[sz]e|scenario|scenarios|trade-?offs?|"
                        r"compare|plan|budget|forecast)\b", re.I)


def signals(text: str) -> list[float]:
    """Cheap, explainable difficulty signals the embedding does not carry well."""
    words = len(text.split())
    return [np.log1p(len(text)), np.log1p(words), len(re.findall(r"\d+(?:[.,]\d+)?", text)) / max(1, words) * 10,
            text.count("?"), len(STEP_WORDS.findall(text)), len(re.findall(r"^\s*(?:[-*•]|\d+[.)])", text, re.M)),
            float(bool(re.search(r"```|def |SELECT |function |class ", text)))]


def fit_predict_lr(Xtr, Ptr, Xte, C=2.0):
    """One logistic model per route, trained on fractional outcomes (each prompt counted as pass and fail by rate)."""
    out = np.zeros((len(Xte), len(ROUTES)))
    for j in range(len(ROUTES)):
        y = np.r_[np.ones(len(Xtr)), np.zeros(len(Xtr))]
        w = np.r_[Ptr[:, j], 1 - Ptr[:, j]] + 1e-6
        m = LogisticRegression(max_iter=5000, C=C).fit(np.r_[Xtr, Xtr], y, sample_weight=w)
        out[:, j] = m.predict_proba(Xte)[:, 1]
    return out


def fit_predict_knn(Etr, Ptr, Ete, k=12):
    """Precedent: the similarity-weighted pass rates of the k most similar labelled prompts."""
    S = Ete @ Etr.T
    idx = np.argsort(-S, axis=1)[:, :k]
    w = np.take_along_axis(S, idx, axis=1) ** 8
    return np.einsum("nk,nkr->nr", w, Ptr[idx]) / w.sum(1, keepdims=True)


def route_with(pred: np.ndarray, C: np.ndarray, bar: float) -> np.ndarray:
    # a router does not know this prompt's cost; it knows each route's typical cost
    from classifier import ladder

    return ladder.choose({"typical_cost": C.mean(0)}, pred, bar)


def evaluate(choice: np.ndarray, P: np.ndarray, C: np.ndarray) -> tuple[float, float]:
    n = np.arange(len(choice))
    return float(P[n, choice].mean()), float(C[n, choice].sum())


def main() -> None:
    rows = [json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r.get("label_source") == "outcome" and "reasoning" in r]
    P, C = outcomes(rows)
    texts = [r["prompt"][:4000] for r in rows]
    E = np.asarray(shared().embed(texts))
    S = np.array([signals(t) for t in texts])
    S = (S - S.mean(0)) / (S.std(0) + 1e-9)

    folds = list(KFold(5, shuffle=True, random_state=7).split(E))
    preds: dict[str, np.ndarray] = {name: np.zeros_like(P) for name in ("embedding", "embedding+signals", "precedent", "ensemble")}
    for tr, te in folds:
        a = fit_predict_lr(E[tr], P[tr], E[te])
        b = fit_predict_lr(np.c_[E[tr], S[tr]], P[tr], np.c_[E[te], S[te]])
        c = fit_predict_knn(E[tr], P[tr], E[te])
        preds["embedding"][te], preds["embedding+signals"][te], preds["precedent"][te] = a, b, c
        preds["ensemble"][te] = (b + c) / 2

    n = len(rows)
    base = {f"always {r}": evaluate(np.full(n, j), P, C) for j, r in enumerate(ROUTES)}
    best = np.argmax(P - 1e-9 * C, axis=1)
    base["oracle (best answer, then cheapest)"] = evaluate(best, P, C)
    target_q = base["always REASONING"][0]

    report = {"prompts": n, "baselines": {k: {"quality": round(q, 3), "cost_usd": round(c, 3)} for k, (q, c) in base.items()},
              "predictors": {}}
    print(f"{n} prompts, 5-fold cross-validated\n")
    for k, (q, c) in base.items():
        print(f"  {k:38s} quality {q:6.1%}   cost ${c:7.3f}")
    for name, pred in preds.items():
        frontier = []
        for b in BARS:
            ch = route_with(pred, C, b)
            q, c = evaluate(ch, P, C)
            frontier.append({"bar": b, "quality": round(q, 3), "cost_usd": round(c, 3),
                             "mix": {r: round(float((ch == j).mean()), 3) for j, r in enumerate(ROUTES)}})
        beats = [f for f in frontier if f["quality"] >= target_q]
        pick = min(beats, key=lambda f: f["cost_usd"]) if beats else max(frontier, key=lambda f: f["quality"])
        top = max(frontier, key=lambda f: f["quality"])
        report["predictors"][name] = {"frontier": frontier, "matches_always_reasoning": pick if beats else None, "best_quality": top}
        print(f"\n{name}")
        for f in frontier:
            mark = " <" if f is pick else ""
            print(f"  bar {f['bar']:<5} quality {f['quality']:6.1%}   cost ${f['cost_usd']:7.3f}   "
                  + " ".join(f"{r[0]}{f['mix'][r]:.0%}" for r in ROUTES) + mark)
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence" / "ladder-lab.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
