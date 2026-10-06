"""Mini-train the routing classifier on the outcome labels.

    uv run python classifier/train.py        # labels.jsonl -> model/head.joblib, model/meta.json

1. Embed every prompt with a multilingual sentence encoder, locally. Routes
   decided by rules (MULTILINGUAL, VISION, LONG_CONTEXT) are not learned;
   COMPLEX outcome labels are learned as REASONING (see router_model.py).
2. Hold out 20% of prompts, stratified by route (data/split.json). The split
   is stable: prompts already assigned keep their side, and only new prompts
   are split, so adding data never moves a held-out prompt into training.
3. Fit a logistic regression head on the rest; its regularisation strength is
   chosen by 5-fold cross-validation inside the training split only.
4. Report held-out accuracy, per-route recall and the confusion matrix, and
   save the head with its metadata.

5. Fit the ladder router (classifier/ladder.py) on the outcome-labelled
   prompts of the training split. Its quality bar is chosen by 5-fold
   cross-validation inside the training split: the cheapest bar whose
   answers are at least as good as always using the REASONING route. The
   held-out prompts then score it once, against every fixed route.

Training takes seconds on a laptop CPU; the same script runs unchanged on a
GPU node with a larger encoder.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import (GridSearchCV, RepeatedStratifiedKFold, StratifiedKFold, cross_val_score,
                                     train_test_split)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.router_model import ENCODER, LEARNED, MODEL_DIR, QUERY_PREFIX, learned_label  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


BARS = [0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def fit_ladder(encoder, held: set) -> dict:
    from sklearn.model_selection import KFold

    from classifier import ladder

    rows = [json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r.get("label_source") == "outcome" and "reasoning" in r]
    tr = [r for r in rows if r["id"] not in held]
    te = [r for r in rows if r["id"] in held]
    def embed(rs):
        return encoder.encode([QUERY_PREFIX + r["prompt"][:4000] for r in rs], normalize_embeddings=True,
                              show_progress_bar=False, batch_size=32)
    E_tr, E_te = embed(tr), embed(te)
    P_tr, C_tr = ladder.outcomes(tr)
    P_te, C_te = ladder.outcomes(te)
    t_tr, t_te = [r["prompt"][:4000] for r in tr], [r["prompt"][:4000] for r in te]

    def score(choice, P, C):
        n = np.arange(len(choice))
        return float(P[n, choice].mean()), float(C[n, choice].mean())

    # choose the quality bar inside the training split only
    cv_pass = np.zeros_like(P_tr)
    for a, b in KFold(5, shuffle=True, random_state=7).split(E_tr):
        params = ladder.fit(E_tr[a], [t_tr[i] for i in a], P_tr[a], C_tr[a])
        cv_pass[b] = ladder.predict(params, E_tr[b], [t_tr[i] for i in b])["pass"]
    target = P_tr[:, 3].mean()                     # always REASONING, on the training split
    params = ladder.fit(E_tr, t_tr, P_tr, C_tr)
    # the route set and the bar, both chosen here: the cheapest combination at least as
    # good as always-REASONING (a route as costly as a better one is dropped this way)
    sets = [list(ladder.ROUTES), ["SIMPLE", "MEDIUM", "REASONING"], ["SIMPLE", "REASONING"], ["SIMPLE", "COMPLEX", "REASONING"]]
    grid = [(tuple(rs), b, *score(ladder.choose(params, cv_pass, b, rs), P_tr, C_tr)) for rs in sets for b in BARS]
    good = [g for g in grid if g[2] >= target]
    routes, bar = (min(good, key=lambda g: g[3]) if good else max(grid, key=lambda g: g[2]))[:2]
    routes = list(routes)
    params["routes"] = np.array(routes)
    curve = [(b, q, c) for rs, b, q, c in grid if list(rs) == routes]

    ladder.save(params, MODEL_DIR / "ladder.npz")
    held_choice = ladder.choose(params, ladder.predict(params, E_te, t_te)["pass"], bar, routes)
    n = len(te)
    result = {"bar": bar, "routes": routes, "train_prompts": len(tr), "held_out_prompts": n,
              "cv_grid_on_train": [{"routes": list(rs), "bar": b, "quality": round(q, 3), "cost_per_request": round(c, 6)}
                                   for rs, b, q, c in grid],
              "cv_curve_on_train": [{"bar": b, "quality": round(q, 3), "cost_per_request": round(c, 6)} for b, q, c in curve]}
    held_eval = {"ladder": score(held_choice, P_te, C_te)}
    for j, r in enumerate(ladder.ROUTES):
        held_eval[f"always {r}"] = score(np.full(n, j), P_te, C_te)
    held_eval["oracle"] = score(np.argmax(P_te - 1e-9 * C_te, axis=1), P_te, C_te)
    result["held_out"] = {k: {"quality": round(q, 3), "cost_per_request": round(c, 6)} for k, (q, c) in held_eval.items()}
    # reported, never used to choose: how every bar does on the held-out prompts
    held_pass = ladder.predict(params, E_te, t_te)["pass"]
    result["held_out_curve"] = [{"bar": b, **dict(zip(("quality", "cost_per_request"),
                                 (round(v, 6) for v in score(ladder.choose(params, held_pass, b, routes), P_te, C_te))))} for b in BARS]
    result["held_out_mix"] = {r: round(float((held_choice == j).mean()), 3) for j, r in enumerate(ladder.ROUTES)}
    return result


def main() -> None:
    from sentence_transformers import SentenceTransformer

    rows = [json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines()]
    rows = [{**r, "learned": learned_label(r["route"])} for r in rows]
    rows = [r for r in rows if r["learned"]]      # MULTILINGUAL, VISION, LONG_CONTEXT are decided by rules
    texts = [QUERY_PREFIX + r["prompt"] for r in rows]
    y = np.array([r["learned"] for r in rows])
    ids = np.array([r["id"] for r in rows])

    started = time.time()
    encoder = SentenceTransformer(ENCODER, device="cpu")
    X = encoder.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
    embed_seconds = time.time() - started

    split_path = DATA / "split.json"
    old = json.loads(split_path.read_text()) if split_path.exists() else {"train": [], "held_out": []}
    held = set(old["held_out"])
    assigned = held | set(old["train"])
    new = np.array([i for i, x in enumerate(ids) if x not in assigned])
    if len(new):
        y_new = y[new]
        strat = y_new if min(Counter(y_new.tolist()).values()) >= 2 else None
        _, new_held = train_test_split(new, test_size=0.2, stratify=strat, random_state=7)
        held |= {ids[i] for i in new_held}
    te = np.array([x in held for x in ids])
    X_tr, X_te, y_tr, y_te, id_tr, id_te = X[~te], X[te], y[~te], y[te], ids[~te], ids[te]
    started = time.time()
    search = GridSearchCV(LogisticRegression(max_iter=4000, class_weight="balanced"),
                          {"C": [0.5, 1, 2, 4, 8, 16]}, cv=StratifiedKFold(5, shuffle=True, random_state=7),
                          scoring="balanced_accuracy")
    search.fit(X_tr, y_tr)
    head = search.best_estimator_
    train_seconds = time.time() - started

    # One held-out split of this size moves 1-2 points per prompt; 5x5 repeated
    # cross-validation over every prompt is the steadier number.
    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=7)
    rcv_acc = cross_val_score(LogisticRegression(max_iter=4000, class_weight="balanced", C=search.best_params_["C"]),
                              X, y, cv=rcv, scoring="accuracy")
    pred = head.predict(X_te)
    labels = [c for c in LEARNED if c in set(y)]
    report = classification_report(y_te, pred, labels=labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, pred, labels=labels).tolist()
    accuracy = float((pred == y_te).mean())

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(head, MODEL_DIR / "head.joblib")
    meta = {
        "encoder": ENCODER, "classes": labels, "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "examples": len(rows), "train": int(len(y_tr)), "held_out": int(len(y_te)),
        "label_counts": dict(Counter(y.tolist())), "C": search.best_params_["C"],
        "cv_balanced_accuracy": round(float(search.best_score_), 3),
        "held_out_accuracy": round(accuracy, 3),
        "repeated_cv_accuracy": round(float(rcv_acc.mean()), 3), "repeated_cv_std": round(float(rcv_acc.std()), 3),
        "labels_from_votes": sum(1 for r in rows if r.get("votes")),
        "held_out_recall": {c: round(report[c]["recall"], 3) for c in labels},
        "confusion_matrix": {"labels": labels, "rows_true_cols_predicted": cm},
        "embed_seconds": round(embed_seconds, 1), "train_seconds": round(train_seconds, 2),
    }
    meta["ladder"] = fit_ladder(encoder, held)
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    (DATA / "split.json").write_text(json.dumps({"train": id_tr.tolist(), "held_out": id_te.tolist()}, indent=1))
    print("ladder:", json.dumps({k: meta["ladder"][k] for k in ("routes", "bar", "held_out", "held_out_mix")}, indent=1))
    print(json.dumps({k: meta[k] for k in ("examples", "held_out", "C", "cv_balanced_accuracy",
                                           "held_out_accuracy", "repeated_cv_accuracy", "held_out_recall", "train_seconds")}, indent=1))
    print("confusion (rows true, cols predicted):", labels)
    for name, row in zip(labels, cm, strict=True):
        print(f"  {name:12s} {row}")


if __name__ == "__main__":
    main()
