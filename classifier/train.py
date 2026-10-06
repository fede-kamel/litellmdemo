"""Mini-train the routing classifier on the outcome labels.

    uv run python classifier/train.py        # labels.jsonl -> model/head.joblib, model/meta.json

1. Embed every prompt with a multilingual sentence encoder, locally. Routes
   decided by rules (MULTILINGUAL, VISION, LONG_CONTEXT) are not learned;
   COMPLEX outcome labels are learned as REASONING (see router_model.py).
2. Hold out 20% of prompts, stratified by route (data/split.json).
3. Fit a logistic regression head on the rest; its regularisation strength is
   chosen by 5-fold cross-validation inside the training split only.
4. Report held-out accuracy, per-route recall and the confusion matrix, and
   save the head with its metadata.

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
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.router_model import ENCODER, LEARNED, MODEL_DIR, QUERY_PREFIX, learned_label  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


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

    X_tr, X_te, y_tr, y_te, id_tr, id_te = train_test_split(X, y, ids, test_size=0.2, stratify=y, random_state=7)
    started = time.time()
    search = GridSearchCV(LogisticRegression(max_iter=4000, class_weight="balanced"),
                          {"C": [0.5, 1, 2, 4, 8, 16]}, cv=StratifiedKFold(5, shuffle=True, random_state=7),
                          scoring="balanced_accuracy")
    search.fit(X_tr, y_tr)
    head = search.best_estimator_
    train_seconds = time.time() - started

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
        "held_out_recall": {c: round(report[c]["recall"], 3) for c in labels},
        "confusion_matrix": {"labels": labels, "rows_true_cols_predicted": cm},
        "embed_seconds": round(embed_seconds, 1), "train_seconds": round(train_seconds, 2),
    }
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    (DATA / "split.json").write_text(json.dumps({"train": id_tr.tolist(), "held_out": id_te.tolist()}, indent=1))
    print(json.dumps({k: meta[k] for k in ("examples", "held_out", "C", "cv_balanced_accuracy",
                                           "held_out_accuracy", "held_out_recall", "train_seconds")}, indent=1))
    print("confusion (rows true, cols predicted):", labels)
    for name, row in zip(labels, cm, strict=True):
        print(f"  {name:12s} {row}")


if __name__ == "__main__":
    main()
