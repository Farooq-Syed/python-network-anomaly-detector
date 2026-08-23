"""Cross-dataset generalization (leave-one-dataset-out).

The three benchmarks use different feature schemas, so a naive cross-dataset
transfer is not apples-to-apples:

  * UNSW-NB15 uses its own 21 numeric features (``dur``, ``spkts``, ...).
  * CIC-IDS2017 / CSE-CIC-IDS2018 use CICFlowMeter names (``Flow Duration``, ...).

There is **zero** feature-name overlap between UNSW and CIC, so no honest
cross-dataset training is possible there. CIC-IDS2017 and CSE-CIC-IDS2018 DO
share a CICFlowMeter feature set, so a leave-one-dataset-out test is meaningful
between them.

This script:
  1. Reports the shared feature intersection for a given train/test dataset pair.
  2. If the intersection is non-empty, trains a supervised model on the training
     dataset's shared features and evaluates on the test dataset's shared
     features (5-fold CV within the train set for a reference, direct transfer to
     the test set), reporting the generalization drop.
  3. If the intersection is empty (e.g. UNSW against CIC), it documents the
     schema incompatibility rather than fabricating a number.

Usage:
    python cross_dataset.py --train data/cic_ids2017_subset_with_day.csv \\
        --test data/cse_cic_ids2018_subset.csv --label-column Label
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from detector import normalize_label

DEFAULT_METRICS = "output/cross_dataset.json"


def load_frame(path: Path, label_column: str):
    frame = pd.read_csv(path)
    if label_column not in frame.columns:
        raise ValueError(f"Label column '{label_column}' not found in {path}")
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    numeric = [c for c in frame.select_dtypes(include=["number"]).columns
               if c != label_column and c != "is_attack" and c != "attack_cat"]
    return frame[numeric], truth


def _cv_reference(X: pd.DataFrame, y: np.ndarray, folds: int):
    splitter = StratifiedKFold(n_splits=min(folds, int(max(2, (y == 1).sum()))), shuffle=True, random_state=42)
    f1s, roc_aucs = [], []
    for tr, te in splitter.split(X, y):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        model.fit(X.iloc[tr], y[tr])
        prob = model.predict_proba(X.iloc[te])[:, 1]
        f1s.append(f1_score(y[te], model.predict(X.iloc[te]), zero_division=0))
        roc_aucs.append(roc_auc_score(y[te], prob))
    return round(float(np.mean(f1s)), 4), round(float(np.mean(roc_aucs)), 4)


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-dataset (leave-one-dataset-out) evaluation.")
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--label-column", default="Label", help="Common label column name.")
    ap.add_argument("--train-label", default=None, help="Training label column (overrides --label-column).")
    ap.add_argument("--test-label", default=None, help="Test label column (overrides --label-column).")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--metrics-output", default=DEFAULT_METRICS)
    args = ap.parse_args()

    x_train_full, y_train = load_frame(Path(args.train), args.train_label or args.label_column)
    x_test_full, y_test = load_frame(Path(args.test), args.test_label or args.label_column)

    shared = [c for c in x_train_full.columns if c in x_test_full.columns]
    payload = {
        "train": str(args.train), "test": str(args.test),
        "train_features": len(x_train_full.columns),
        "test_features": len(x_test_full.columns),
        "shared_feature_count": len(shared),
        "shared_features": shared,
    }

    if len(shared) == 0:
        payload["status"] = "schema-incompatible"
        payload["note"] = (
            "The train and test datasets share no feature names, so a leave-one-dataset-out "
            "transfer is not meaningful. This is the honest limitation: UNSW-NB15 and CIC "
            "use different feature pipelines, so no common numerical representation exists "
            "without a manual cross-schema mapping."
        )
    else:
        x_train = x_train_full[shared]
        x_test = x_test_full[shared]
        payload["status"] = "evaluated"
        ref_f1, ref_auc = _cv_reference(x_train, y_train, args.folds)
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        model.fit(x_train, y_train)
        prob = model.predict_proba(x_test)[:, 1]
        pred = model.predict(x_test)
        transfer = {
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, prob)), 4),
            "train_f1_cv_reference": ref_f1,
            "train_roc_auc_cv_reference": ref_auc,
            "generalization_drop": round(ref_f1 - float(f1_score(y_test, pred, zero_division=0)), 4),
        }
        payload["transfer"] = transfer

    out = Path(args.metrics_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Train features: {payload['train_features']}  Test features: {payload['test_features']}")
    print(f"Shared features: {payload['shared_feature_count']}")
    if payload["status"] == "evaluated":
        t = payload["transfer"]
        print(f"\nCV-on-train reference: F1={t['train_f1_cv_reference']} AUC={t['train_roc_auc_cv_reference']}")
        print(f"Transfer to test     : F1={t['f1']} P={t['precision']} R={t['recall']} AUC={t['roc_auc']}")
        print(f"Generalization drop  : {t['generalization_drop']:+.4f}")
    else:
        print("\n" + payload["note"])
    print(f"\nMetrics -> {out}")


if __name__ == "__main__":
    main()
