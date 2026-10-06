"""Fine-tune the encoder itself, then compare with the frozen encoder on the same held-out prompts.

    uv run python classifier/finetune.py     # -> classifier/model-finetuned/, evidence/finetune-comparison.json

train.py keeps multilingual-e5-small frozen and trains only a logistic
regression head (1,540 weights). This script also trains the encoder's own
weights (~118M parameters), SetFit-style: a batch-all triplet loss pulls
prompts with the same route together and pushes different routes apart, on
the training split only. Then it fits the same head and scores the same
held-out prompts as train.py, so the two numbers compare directly.

Runs on the Mac's GPU (MPS) in minutes; the same script runs on a CUDA GPU.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier.router_model import ENCODER, MODEL_DIR, QUERY_PREFIX, learned_label  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "classifier" / "data"
OUT_DIR = ROOT / "classifier" / "model-finetuned"
EPOCHS = 12


def main() -> None:
    from datasets import Dataset
    from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer, SentenceTransformerTrainingArguments
    from sentence_transformers.losses import BatchAllTripletLoss

    rows = {r["id"]: r for r in (json.loads(line) for line in (DATA / "labels.jsonl").read_text().splitlines())}
    split = json.loads((DATA / "split.json").read_text())
    train = [rows[i] for i in split["train"]]
    held = [rows[i] for i in split["held_out"]]
    classes = sorted({learned_label(r["route"]) for r in train})
    index = {c: i for i, c in enumerate(classes)}
    text = lambda r: QUERY_PREFIX + r["prompt"]  # noqa: E731
    y_tr = np.array([learned_label(r["route"]) for r in train])
    y_te = np.array([learned_label(r["route"]) for r in held])
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")

    def head_score(model) -> tuple[float, float]:
        X_tr = model.encode([text(r) for r in train], normalize_embeddings=True, show_progress_bar=False)
        X_te = model.encode([text(r) for r in held], normalize_embeddings=True, show_progress_bar=False)
        head = LogisticRegression(max_iter=4000, class_weight="balanced", C=json.loads((MODEL_DIR / "meta.json").read_text())["C"])
        head.fit(X_tr, y_tr)
        pred = head.predict(X_te)
        return float((pred == y_te).mean()), float(balanced_accuracy_score(y_te, pred))

    frozen = SentenceTransformer(ENCODER, device=device)
    frozen_acc, frozen_bal = head_score(frozen)
    trainable = sum(p.numel() for p in frozen.parameters())

    model = SentenceTransformer(ENCODER, device=device)
    ds = Dataset.from_dict({"sentence": [text(r) for r in train], "label": [index[c] for c in y_tr]})
    args = SentenceTransformerTrainingArguments(
        output_dir=str(ROOT / "out" / "finetune"), num_train_epochs=EPOCHS, per_device_train_batch_size=32,
        learning_rate=5e-5, warmup_steps=0.1, logging_steps=5, save_strategy="no", report_to=[], seed=7)
    started = time.time()
    SentenceTransformerTrainer(model=model, args=args, train_dataset=ds, loss=BatchAllTripletLoss(model)).train()
    seconds = time.time() - started
    tuned_acc, tuned_bal = head_score(model)
    model.save(str(OUT_DIR))

    result = {
        "encoder": ENCODER, "device": device, "train_prompts": len(train), "held_out": len(held), "epochs": EPOCHS,
        "encoder_parameters": trainable,
        "frozen": {"trained": "logistic regression head only", "held_out_accuracy": round(frozen_acc, 3),
                   "held_out_balanced_accuracy": round(frozen_bal, 3)},
        "fine_tuned": {"trained": "every encoder weight, then the same head", "held_out_accuracy": round(tuned_acc, 3),
                       "held_out_balanced_accuracy": round(tuned_bal, 3), "fine_tune_seconds": round(seconds, 1)},
    }
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence" / "finetune-comparison.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
