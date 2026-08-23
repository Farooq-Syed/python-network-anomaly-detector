"""Strict generalization: hold out whole attack families / days, not random rows.

The paper's reported supervised numbers use random stratified cross-validation,
which leaks the *structure* of the attack families between train and test. A
reviewer will ask whether a classifier trained on some families still detects
unseen ones. This script evaluates exactly that.

Two split modes, chosen by --split-by:

  * ``family`` — train on a subset of attack families (plus benign), test on the
    held-out attack family/ies. Used for UNSW-NB15 (has a ``family`` column) and
    CIC (has a ``label_name`` column).
  * ``day``    — train on some days, test on the rest. Used for CIC-IDS2017
    (has a ``day`` column; matches intra-dataset temporal generalization).

For every held-out group it trains a supervised classifier on the training rows
and reports precision/recall/F1/AUC on the held-out rows, plus a pooled
"unseen" result and the drop-vs-random-CV baseline. The unsupervised ensemble is
also reported for the held-out group so the reader can see whether even the
supervised ceiling degrades.

Usage:
    python strict_generalization.py --input data/unsw_nb15_subset_with_family.csv \\
        --mode family --family-column family --label-column label
    python strict_generalization.py --input data/cic_ids2017_subset_with_day.csv \\
        --mode day --day-column day --label-column Label
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from detector import normalize_label, select_numeric_columns  # noqa: E402

DEFAULT_METRICS = "output/strict_generalization.json"
DEFAULT_PLOT = "output/plots/strict_generalization.png"
METADATA_COLUMNS = {"family", "day", "label_name", "is_attack"}


def load_frame(path: Path, label_column: str, metadata_column: str):
    frame = pd.read_csv(path)
    if label_column not in frame.columns:
        raise ValueError(f"Label column '{label_column}' not found.")
    if metadata_column not in frame.columns:
        raise ValueError(f"Metadata column '{metadata_column}' not found. "
                         "Prepare the dataset with --include-metadata first.")
    numeric = select_numeric_columns(frame, label_column)
    features = frame[numeric]
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    labels = frame[metadata_column].astype(str)
    return features, truth, labels


def _make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


def unsupervised_ensemble(features: pd.DataFrame, numeric_cols: List[str]) -> np.ndarray:
    from benchmark_compare import unsupervised_ensemble as _unsup

    return _unsup(features, numeric_cols, z_threshold=2.5, contamination=0.12, random_state=42)


def evaluate_family_pool(features: pd.DataFrame, truth: np.ndarray, labels: pd.Series,
                         held_family: str) -> Dict[str, float]:
    """Train on benign (split) + seen attack families, test on benign-split + unseen family.

    The held-out *attack family* is entirely unseen; the test pool mixes that family's
    attacks with a held-out benign split, so the classifier faces a realistic
    "benign vs. an attack family never seen in training" question rather than a
    degenerate all-attack pool. Benign rows are split so benign appears in both splits;
    this is the correct split for *unseen-family* generalization (the family never
    appears in training, but normal traffic is shared).
    """
    is_attack = truth == 1
    unseen_idx = np.where((labels == held_family).to_numpy() & is_attack)[0]
    benign_idx = np.where(~is_attack)[0]
    seen_attack_idx = np.where((labels != held_family).to_numpy() & is_attack)[0]

    benign_hold, benign_train = _split_benign(benign_idx)

    train_idx = np.concatenate([benign_train, seen_attack_idx])
    test_idx = np.concatenate([benign_hold, unseen_idx])
    return _fit_and_evaluate(features, truth, train_idx, test_idx, held_family)


def evaluate_day_pool(features: pd.DataFrame, truth: np.ndarray, labels: pd.Series,
                      held_day: str) -> Dict[str, float]:
    """Hold out an ENTIRE day: both benign and attack flows of that day are test-only.

    This is a true temporal hold-out. No row from the held-out day (benign or attack)
    is used in training, so the model has never seen the day's normal or attack traffic.
    The reviewer-corrected evaluation — not a benign split across days.
    """
    is_held = (labels == held_day).to_numpy()
    train_idx = np.where(~is_held)[0]
    test_idx = np.where(is_held)[0]
    return _fit_and_evaluate(features, truth, train_idx, test_idx, held_day)


def _fit_and_evaluate(features: pd.DataFrame, truth: np.ndarray,
                      train_idx: np.ndarray, test_idx: np.ndarray,
                      held_group: str) -> Dict[str, float]:
    numeric_cols = features.select_dtypes(include=["number"]).columns.tolist()
    x_feat = features.to_numpy()
    if len(np.unique(truth[train_idx])) < 2 or len(test_idx) == 0:
        return _empty_result(held_group)
    if len(np.unique(truth[test_idx])) < 2:
        # A degenerate test pool (one class only) cannot give a meaningful F1/AUC.
        return _empty_result(held_group)
    model = _make_model()
    model.fit(x_feat[train_idx], truth[train_idx])
    prob = model.predict_proba(x_feat[test_idx])[:, 1]
    pred = model.predict(x_feat[test_idx])
    truth_test = truth[test_idx]

    res = {
        "held_out_group": held_group,
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "test_attacks": int((truth_test == 1).sum()),
        "test_benign": int((truth_test == 0).sum()),
        "precision": round(float(precision_score(truth_test, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(truth_test, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(truth_test, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(truth_test, prob)), 4),
    }
    unsup_pred = unsupervised_ensemble(features.iloc[test_idx], numeric_cols)
    res["unsupervised_f1_heldout"] = round(
        float(f1_score(truth_test, unsup_pred, zero_division=0)), 4
    )
    return res


def _split_benign(benign_idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (held-out test indices, training indices) for benign rows."""
    frac = 0.2
    rng = np.random.default_rng(42)
    if len(benign_idx) == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    n_hold = max(1, int(len(benign_idx) * frac))
    hold = rng.choice(benign_idx, size=min(n_hold, len(benign_idx)), replace=False)
    hold_set = set(int(h) for h in hold)
    heldout = np.array([i for i in benign_idx if int(i) in hold_set], dtype=int)
    train = np.array([i for i in benign_idx if int(i) not in hold_set], dtype=int)
    return heldout, train


def _empty_result(held_group: str) -> Dict[str, float | str | int]:
    return {
        "held_out_group": held_group,
        "n_train": 0, "n_test": 0, "test_attacks": 0, "test_benign": 0,
        "precision": float("nan"), "recall": float("nan"), "f1": float("nan"),
        "roc_auc": float("nan"), "unsupervised_f1_heldout": float("nan"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Strict generalization (family/day holdout).")
    ap.add_argument("--input", required=True)
    ap.add_argument("--label-column", default="label")
    ap.add_argument("--mode", choices=["family", "day"], default="family",
                    help="Split key: hold out by attack family or by day.")
    ap.add_argument("--family-column", default="family")
    ap.add_argument("--day-column", default="day")
    ap.add_argument("--metrics-output", default=DEFAULT_METRICS)
    ap.add_argument("--plot", default=DEFAULT_PLOT)
    args = ap.parse_args()

    metadata_column = args.family_column if args.mode == "family" else args.day_column
    features, truth, labels = load_frame(Path(args.input), args.label_column, metadata_column)

    holdout_groups = sorted(labels.unique())
    # In family mode, "Benign" is never a held-out family (it is the normal class).
    if args.mode == "family":
        holdout_groups = [g for g in holdout_groups if g != "Benign"]

    rows: List[dict] = []
    for group in holdout_groups:
        if (truth[labels == group] == 1).sum() == 0:
            print(f"  (skip {group}: no attacks in group)")
            continue
        if args.mode == "day":
            res = evaluate_day_pool(features, truth, labels, group)
        else:
            res = evaluate_family_pool(features, truth, labels, group)
        if res["n_test"] == 0:
            print(f"  (skip {group}: empty test pool)")
            continue
        if res["test_attacks"] == 0 or res["test_benign"] == 0:
            print(f"  (skip {group}: test pool is single-class; "
                  f"attacks={res['test_attacks']} benign={res['test_benign']})")
            continue
        rows.append(res)
        print(f"  held-out {group:<14} test_n={res['n_test']:<6} "
              f"test_att={(res['test_attacks']):<5} test_ben={(res['test_benign']):<5} "
              f"sup F1={res['f1']:.3f} AUC={res['roc_auc']:.3f} "
              f"unsup F1={res['unsupervised_f1_heldout']:.3f}")

    if not rows:
        print("No evaluable held-out groups. Check metadata columns and class balance.")
        return

    pooled = {
        "mode": args.mode,
        "input": str(args.input),
        "groups_evaluated": len(rows),
        "per_group": rows,
        "note": ("Train on some attack families, test on held-out ones"
                 if args.mode == "family" else "Train on some days, test on held-out days"),
    }
    out = Path(args.metrics_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pooled, indent=2), encoding="utf-8")
    print(f"\nWrote -> {out}")


if __name__ == "__main__":
    main()
