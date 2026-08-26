"""Imbalance and operational metric evaluation.

The reported F1 numbers come from *balanced* 50/50 subsets, which is not how a
real NIDS operates — attack traffic is a small fraction of total traffic. F1 at a
balanced operating point overstates value. This script evaluates the supervised
detector on **imbalanced** traffic, where attacks (the positive class) are a small
minority, and reports operational metrics that matter to an analyst:

  * F1 and precision/recall at a *fixed* false-positive rate (recall @ FPR).
  * ROC-AUC and PR-AUC (PR-AUC is the right summary metric for heavy imbalance).
  * detection rate at a specified validation false-positive budget.

Imbalance is produced two ways:
  1. ``--attack-frac`` downsamples the positive class to a target fraction of the
     data (e.g. 0.05 = 5% attacks), while keeping the real feature distribution.
  2. ``--balanced`` uses the subset as-is (for reference/ablation).

The supervised model is identical to the one used elsewhere (StandardScaler +
LogisticRegression, class_weight='balanced' by default, plus a no-weights run for
comparison), under 5-fold stratified CV. The threshold is selected only from an
inner validation split. It maximizes validation recall subject to the requested
FPR budget and is then applied once to the untouched outer test fold.

Usage:
    python imbalance_eval.py --input data/cic_ids2017_subset_with_day.csv \\
        --label-column Label --attack-frac 0.05 --fpr 0.01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from detector import normalize_label, select_numeric_columns

DEFAULT_METRICS = "output/imbalance_eval.json"


def load_frame(path: Path, label_column: str):
    frame = pd.read_csv(path)
    numeric = select_numeric_columns(frame, label_column)
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    return frame[numeric], truth


def subsample_to_fraction(features: pd.DataFrame, truth: np.ndarray,
                          attack_frac: float, random_state: int) -> tuple[pd.DataFrame, np.ndarray]:
    """Downsample the positive (attack) class so it is ``attack_frac`` of the data.

    Benign rows are kept as-is (the real-world majority), and attack rows are
    sampled so that attacks make up the desired fraction. This preserves the true
    feature distribution of the majority class rather than synthesizing one.
    """
    n = len(truth)
    benign_idx = np.where(truth == 0)[0]
    attack_idx = np.where(truth == 1)[0]
    rng = np.random.default_rng(random_state)
    # Attack rows should make up ``attack_frac`` of the downsampled dataset, so
    # n_attacks / (n_benign + n_attacks) == attack_frac.
    n_attack_target = int(round(len(benign_idx) * attack_frac / (1 - attack_frac))) if 0 < attack_frac < 1 else len(attack_idx)
    n_attack_target = max(1, min(n_attack_target, len(attack_idx)))
    chosen_attack = rng.choice(attack_idx, size=n_attack_target, replace=False)
    keep = np.concatenate([benign_idx, chosen_attack])
    rng.shuffle(keep)
    return features.iloc[keep], truth[keep]


def _pick_threshold(y_val: np.ndarray, val_prob: np.ndarray, target_fpr: float) -> tuple[float, float]:
    """Select a decision threshold on a validation split to hit a target FPR.

    The threshold is chosen *only* from the validation-fold labels; it is then applied
    once to the untouched test fold. This avoids the optimistic estimate that comes
    from tuning the threshold on the same fold whose metrics are reported.
    """
    fpr, tpr, thresholds = roc_curve(y_val, val_prob)
    if len(thresholds) == 0:
        return float("nan"), float("nan")
    # roc_curve returns an inf threshold for the terminal operating point; keep only
    # finite ones so the chosen threshold is a usable probability cutoff.
    finite = np.isfinite(thresholds)
    if not finite.any():
        return float("nan"), float("nan")
    fpr_f = np.asarray(fpr)[finite]
    tpr_f = np.asarray(tpr)[finite]
    thr_f = np.asarray(thresholds)[finite]
    feasible = np.where(fpr_f <= target_fpr)[0]
    if len(feasible):
        best_tpr = np.max(tpr_f[feasible])
        candidates = feasible[tpr_f[feasible] == best_tpr]
        idx = int(candidates[np.argmax(thr_f[candidates])])
    else:
        idx = int(np.argmin(fpr_f))
    return float(thr_f[idx]), float(fpr_f[idx])


def evaluate(features: pd.DataFrame, truth: np.ndarray, folds: int, random_state: int,
             target_fpr: float, use_balanced_weight: bool, attack_frac: float) -> Dict[str, float]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    rows: Dict[str, List[float]] = {k: [] for k in (
        "precision", "recall", "f1", "roc_auc", "pr_auc", "recall_at_fpr",
        "validation_fpr", "actual_fpr")}
    for train_idx, test_idx in splitter.split(features, truth):
        # Hold out an inner validation split from the training fold so the FPR
        # threshold is set without touching the test fold.
        inner = StratifiedKFold(n_splits=min(max(folds, 2),
                                             int((truth[train_idx] == 1).sum()),
                                             int((truth[train_idx] == 0).sum())),
                                shuffle=True, random_state=random_state)
        inner_train, inner_val = next(iter(inner.split(features.iloc[train_idx], truth[train_idx])))
        inner_train_idx = train_idx[inner_train]
        inner_val_idx = train_idx[inner_val]

        cls = LogisticRegression(max_iter=2000,
                                 class_weight="balanced" if use_balanced_weight else None)
        model = make_pipeline(StandardScaler(), cls)
        model.fit(features.iloc[inner_train_idx], truth[inner_train_idx])
        val_prob = model.predict_proba(features.iloc[inner_val_idx])[:, 1]
        threshold, val_fpr = _pick_threshold(truth[inner_val_idx], val_prob, target_fpr)
        rows["validation_fpr"].append(val_fpr)

        prob = model.predict_proba(features.iloc[test_idx])[:, 1]
        y_test = truth[test_idx]

        # Metrics at the model's default 0.5 operating point.
        pred = (prob >= 0.5).astype(int)
        rows["precision"].append(precision_score(y_test, pred, zero_division=0))
        rows["recall"].append(recall_score(y_test, pred, zero_division=0))
        rows["f1"].append(f1_score(y_test, pred, zero_division=0))
        rows["roc_auc"].append(roc_auc_score(y_test, prob))
        rows["pr_auc"].append(average_precision_score(y_test, prob))

        # Operational metric: apply the threshold chosen on validation to the test fold.
        if np.isnan(threshold):
            rows["recall_at_fpr"].append(float("nan"))
            rows["actual_fpr"].append(float("nan"))
        else:
            op_pred = (prob >= threshold).astype(int)
            rows["recall_at_fpr"].append(recall_score(y_test, op_pred, zero_division=0))
            # Actual FPR achieved on the untouched test fold.
            rows["actual_fpr"].append(
                float((op_pred[y_test == 0] == 1).mean()) if (y_test == 0).any() else float("nan")
            )

    out = {"attack_frac": attack_frac, "weighted": use_balanced_weight,
           "target_fpr": target_fpr, "n_positive_class_frac": round(float(truth.mean()), 4)}
    for key, vals in rows.items():
        vals_clean = [v for v in vals if not np.isnan(v)]
        out[key] = round(float(np.mean(vals_clean)), 4) if vals_clean else float("nan")
        out[f"{key}_std"] = round(float(np.std(vals_clean)), 4) if vals_clean else float("nan")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Imbalance + operational metric evaluation.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--label-column", default="label")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--attack-frac", type=float, default=0.05,
                    help="Target attack fraction of the dataset (0<p<1). Use 0.5 for balanced.")
    ap.add_argument("--fpr", type=float, default=0.01, help="Target false-positive rate for recall_at_fpr.")
    ap.add_argument("--metrics-output", default=DEFAULT_METRICS)
    ap.add_argument("--balanced", action="store_true",
                    help="Use the subset as-is (no downsampling) as a reference.")
    args = ap.parse_args()

    features, truth = load_frame(Path(args.input), args.label_column)
    if not args.balanced:
        features, truth = subsample_to_fraction(features, truth, args.attack_frac, args.random_state)
        print(f"Subsampled: {len(truth)} rows, {float(truth.mean())*100:.1f}% attacks")
    else:
        args.attack_frac = round(float(truth.mean()), 4)

    results = {
        "input": args.input,
        "balanced": args.balanced,
        "weighted": evaluate(features, truth, args.folds, args.random_state, args.fpr, True, args.attack_frac),
        "unweighted": evaluate(features, truth, args.folds, args.random_state, args.fpr, False, args.attack_frac),
    }
    out = Path(args.metrics_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\nResults ({'balanced' if args.balanced else 'imbalanced'}, "
          f"attack frac={args.attack_frac}):")
    for label in ("weighted", "unweighted"):
        r = results[label]
        print(f"\n[{label}]")
        print(f"  precision={r['precision']} recall={r['recall']} f1={r['f1']}")
        print(f"  ROC-AUC={r['roc_auc']}  PR-AUC={r['pr_auc']}")
        print(f"  recall @ FPR={args.fpr}: {r['recall_at_fpr']} (actual FPR {r['actual_fpr']})")
    print(f"\nMetrics -> {out}")


if __name__ == "__main__":
    main()
