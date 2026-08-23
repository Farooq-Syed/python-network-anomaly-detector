"""Calibration / label-noise analysis behind 'why does the query-strategy sign flip?'

active_learning_experiment.py shows that uncertainty sampling beats random sampling by
~0.005 on UNSW-NB15 but loses on CIC-IDS2017 (F1 0.90 vs 0.93 at 100 labels). This script
tests the documented hypothesis for why: the supervised model's *probabilities* are
miscalibrated on one benchmark but not the other, and uncertainty sampling — which picks
rows whose predicted probability is closest to 0.5 — therefore buys noisy/ambiguous rows on
the poorly-calibrated benchmark and not the other.

It measures, under the identical 5-fold stratified setup and the identical
StandardScaler + LogisticRegression pipeline used by active-learning:

  - Brier score           (lower = better calibrated; random guessing = 0.25)
  - Expected Calibration Error (ECE, 10 bins; lower = better calibrated)
  - reliability slope      (== 1.0 means model confidence matches observed frequency)
  - fraction of rows with probability in [0.40, 0.60]  (the 'uncertainty region' the
    active learner actually targets) and the observed attack rate of those rows
  - how often the model is *wrong* on the uncertainty region (label-noise-adjacent signal)

Run on each public subset:
  python calibration_analysis.py --input data/unsw_nb15_public_subset.csv --label-column label
  python calibration_analysis.py --input data/cic_ids2017_subset.csv --label-column Label
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from detector import normalize_label, select_numeric_columns

LOW, HIGH = 0.40, 0.60


def load_labeled(path: Path, label_column: str):
    frame = pd.read_csv(path)
    feature_columns = select_numeric_columns(frame, label_column)
    features = frame[feature_columns].to_numpy(dtype=float)
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    return features, truth


def _ece(prob: np.ndarray, truth: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error (lower = better)."""
    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    n = len(prob)
    for i in range(bins):
        mask = (prob >= bin_edges[i]) & (prob < bin_edges[i + 1])
        if mask.sum() > 0:
            conf = prob[mask].mean()
            acc = truth[mask].mean()
            ece += (mask.sum() / n) * abs(conf - acc)
    return float(ece)


def _reliability_slope(prob: np.ndarray, truth: np.ndarray) -> float:
    """Linear regression of observed label rate on predicted probability (slope)."""
    a, b = np.polyfit(prob, truth, 1)
    return float(a)


def analyze(features: np.ndarray, truth: np.ndarray, folds: int, random_state: int) -> Dict[str, float]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    brier, ece, slope = [], [], []
    unc_frac, unc_wrong = [], []

    for train_idx, test_idx in splitter.split(features, truth):
        x_train, x_test = features[train_idx], features[test_idx]
        y_train, y_test = truth[train_idx], truth[test_idx]
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train, y_train)
        prob = model.predict_proba(x_test)[:, 1]

        brier.append(brier_score_loss(y_test, prob))
        ece.append(_ece(prob, y_test))
        slope.append(_reliability_slope(prob, y_test))

        amb = (prob >= LOW) & (prob <= HIGH)
        amb_frac = amb.mean()
        amb_wrong = 0.0
        if amb.sum() > 0:
            amb_labels = y_test[amb]
            amb_pred = (prob[amb] >= 0.5).astype(int)
            amb_wrong = float((amb_pred != amb_labels).mean())
        unc_frac.append(float(amb_frac))
        unc_wrong.append(amb_wrong)

    return {
        "brier_mean": round(float(np.mean(brier)), 4),
        "brier_std": round(float(np.std(brier)), 4),
        "ece_mean": round(float(np.mean(ece)), 4),
        "ece_std": round(float(np.std(ece)), 4),
        "reliability_slope_mean": round(float(np.mean(slope)), 4),
        "uncertainty_region_fraction": round(float(np.mean(unc_frac)), 4),
        "uncertainty_region_error_rate": round(float(np.mean(unc_wrong)), 4),
        "n_rows": int(len(truth)),
        "n_attacks": int(truth.sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibration / label-noise analysis.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--label-column", default="label")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--metrics-output", default="")
    args = ap.parse_args()

    features, truth = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows ({int(truth.sum())} attacks) from {args.input}")
    res = analyze(features, truth, args.folds, args.random_state)

    print("\nmetric                              value")
    print(f"{'rows / attacks':<38} {res['n_rows']} / {res['n_attacks']}")
    print(f"{'Brier score (lower=better)':<38} {res['brier_mean']} ± {res['brier_std']}")
    print(f"{'Expected Calibration Error':<38} {res['ece_mean']} ± {res['ece_std']}")
    print(f"{'Reliability slope (1.0=calibrated)':<38} {res['reliability_slope_mean']}")
    print(f"{'Rows with p in [0.4,0.6] (unc. region)':<38} {res['uncertainty_region_fraction']*100:.1f}%")
    print(f"{'Model error on that region':<38} {res['uncertainty_region_error_rate']*100:.1f}%")
    print("\nInterpretation: a HIGH ECE / HIGH error-on-uncertainty-region means the rows the")
    print("uncertainty active learner intentionally picks are exactly the rows the model is")
    print("wrong about / poorly calibrated for -> uncertainty sampling buys noise rather than")
    print("signal, so random labeling wins. This is the proposed mechanism for the sign flip.")

    if args.metrics_output:
        out = Path(args.metrics_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"input": args.input, "label_column": args.label_column,
                                   "folds": args.folds, "random_state": args.random_state, **res},
                                  indent=2), encoding="utf-8")
        print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
