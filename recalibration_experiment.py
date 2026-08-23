"""Does recalibrating the model's probabilities fix the uncertainty-sampling sign flip?

CALIBRATION_FINDING.md shows the supervised model is near-perfectly calibrated on
UNSW-NB15 (Brier 0.004, ~0% in the ambiguity band) but miscalibrated on CIC-IDS2017
(Brier 0.026, 3.4% in band, model wrong on ~45% of them). This script tests the implied
improvement: recalibrate each trained model's probabilities (isotonic, fit on the
training pool only) before uncertainty sampling, and see whether that flips the
uncertainty-vs-random result back in uncertainty's favor on the miscalibrated benchmark.

Recalibration is fit only on the labeled training pool each round (no test-set peeking),
so it improves measurement without inflating the result.

Run on each benchmark:
  python recalibration_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
  python recalibration_experiment.py --input data/cic_ids2017_subset.csv --label-column Label --budget 120
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression

from detector import normalize_label, select_numeric_columns


def load_labeled(path: Path, label_column: str):
    frame = pd.read_csv(path)
    feature_columns = select_numeric_columns(frame, label_column)
    features = frame[feature_columns].to_numpy(dtype=float)
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    return features, truth


def _make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


def _seed_labels(y_train, seed_size, rng):
    pos = np.where(y_train == 1)[0]
    neg = np.where(y_train == 0)[0]
    take = min(seed_size // 2, len(pos), len(neg))
    return np.concatenate([rng.choice(pos, size=take, replace=False),
                           rng.choice(neg, size=take, replace=False)])


def _fit_calibrator(model, x_train, y_train):
    """Fit an isotonic calibrator on out-of-fold predictions of the training pool only."""
    from sklearn.model_selection import cross_val_predict
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        oof = cross_val_predict(model, x_train, y_train, cv=3, method="predict_proba")
    return IsotonicRegression(out_of_bounds="clip").fit(oof[:, 1], y_train)


def run_fold(features, truth, train_idx, test_idx, strategy, recalibrate,
             seed_size, batch_size, budget, random_state) -> Dict[int, float]:
    x_train, x_test = features[train_idx], features[test_idx]
    y_train, y_test = truth[train_idx], truth[test_idx]
    rng = np.random.default_rng(random_state)

    labeled = np.asarray(_seed_labels(y_train, seed_size, rng), dtype=int)
    unlabeled = np.ones(len(y_train), dtype=bool)
    unlabeled[labeled] = False

    result: Dict[int, float] = {}
    while len(labeled) <= budget and unlabeled.any():
        model = _make_model()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train[labeled], y_train[labeled])
        f1 = f1_score(y_test, model.predict(x_test), zero_division=0)
        result[len(labeled)] = round(float(f1), 4)

        remaining = np.where(unlabeled)[0]
        probs = model.predict_proba(x_train[remaining])[:, 1]
        if recalibrate:
            try:
                cal = _fit_calibrator(model, x_train[labeled], y_train[labeled])
                probs = cal.predict(probs)
            except Exception:
                pass  # fall back to raw if the calibration split is degenerate

        next_size = min(batch_size, budget - len(labeled))
        if next_size <= 0:
            break
        if strategy == "uncertainty":
            queries = np.argsort(np.abs(probs - 0.5))[:next_size]
        else:
            queries = rng.choice(len(probs), size=next_size, replace=False)
        chosen = remaining[queries]
        labeled = np.concatenate([labeled, chosen])
        unlabeled[chosen] = False
    return result


def run(features, truth, folds, seed_size, batch_size, budget, random_state):
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    # config label -> list of (strategy, recalibrate)
    configs = {
        "random": ("random", False),
        "uncertainty_raw": ("uncertainty", False),
        "uncertainty_calibrated": ("uncertainty", True),
    }
    per_config: Dict[str, Dict[int, list]] = {k: {} for k in configs}
    for train_idx, test_idx in splitter.split(features, truth):
        for name, (strategy, recal) in configs.items():
            fold_res = run_fold(features, truth, train_idx, test_idx, strategy, recal,
                                seed_size, batch_size, budget, random_state)
            for count, f1 in fold_res.items():
                per_config[name].setdefault(count, []).append(f1)

    out: Dict[str, Dict[int, Dict[str, float]]] = {}
    for name, counts in per_config.items():
        out[name] = {}
        for count, scores in sorted(counts.items()):
            out[name][count] = {"f1_mean": round(float(np.mean(scores)), 4),
                                "f1_std": round(float(np.std(scores)), 4)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--label-column", default="label")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed-size", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--metrics-output", default="")
    args = ap.parse_args()

    features, truth = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows ({int(truth.sum())} attacks) from {args.input}\n")
    results = run(features, truth, args.folds, args.seed_size, args.batch_size,
                  args.budget, args.random_state)

    print(f"{'labels':>8}{'random':>10}{'uncert (raw)':>14}{'uncert (calib)':>16}")
    counts = sorted(next(iter(results.values())).keys())
    for count in counts:
        r = results["random"][count]["f1_mean"]
        ur = results["uncertainty_raw"][count]["f1_mean"]
        uc = results["uncertainty_calibrated"][count]["f1_mean"]
        print(f"{count:>8}{r:>10.3f}{ur:>14.3f}{uc:>16.3f}")

    final = max(counts)
    r = results["random"][final]["f1_mean"]
    ur = results["uncertainty_raw"][final]["f1_mean"]
    uc = results["uncertainty_calibrated"][final]["f1_mean"]
    delta_raw = ur - r
    delta_cal = uc - r
    print(f"\nAt budget {final}: random={r:.3f}  uncert_raw={ur:.3f} (diff={delta_raw:+.3f})  "
          f"uncert_calib={uc:.3f} (diff={delta_cal:+.3f})")
    print("Interpretation: if uncertainty_calibrated >= uncertainty_raw, recalibrating the")
    print("probabilities improves query selection — matching the calibration mechanism.")

    if args.metrics_output:
        p = Path(args.metrics_output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"input": args.input, "label_column": args.label_column,
                                 "budget": args.budget, "results": results}, indent=2),
                     encoding="utf-8")
        print(f"\nSaved -> {p}")


if __name__ == "__main__":
    main()
