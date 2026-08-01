"""How many labels does network intrusion detection actually need?

The unsupervised ensemble (detector.py) reaches F1 ~= 0.27 on the UNSW-NB15 subset;
a fully supervised model (supervised_baseline.py) reaches ~= 0.99. That leaves an
obvious question: attack labels are expensive, so how much of that gap can a *small*
number of labels recover, and does treating the unlabeled remainder as data (via
self-training) help when labels are scarce?

This script sweeps a range of label budgets. For each budget it compares:
  - supervised   : a logistic-regression model trained on only the labeled subset
  - self-training: the same base model, but allowed to iteratively pseudo-label the
                   unlabeled remainder (scikit-learn SelfTrainingClassifier)

Everything runs under stratified 5-fold cross-validation. Within each fold, only the
chosen fraction of *training* rows keep their labels; the rest are hidden. Scaling is
inside the pipeline, so it is fit per fold and never sees the held-out test rows.

Usage:
    python label_budget_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Dict, List

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
from sklearn.semi_supervised import SelfTrainingClassifier

from detector import normalize_label, select_numeric_columns

DEFAULT_INPUT = "data/unsw_nb15_public_subset.csv"
DEFAULT_METRICS = "output/label_budget_metrics.json"
DEFAULT_PLOT = "output/plots/label_budget_curve.png"

# Reference points from the other two evaluations, drawn as horizontal lines.
UNSUPERVISED_ENSEMBLE_F1 = 0.27
FULLY_SUPERVISED_F1 = 0.996

DEFAULT_BUDGETS = [0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.00]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sweep label budgets and compare supervised vs. self-training F1."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS)
    parser.add_argument("--plot", default=DEFAULT_PLOT)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=42)
    return parser


def load_labeled(path: Path, label_column: str):
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    frame = pd.read_csv(path)
    if label_column not in frame.columns:
        raise ValueError(f"Label column '{label_column}' not found.")
    feature_columns = select_numeric_columns(frame, label_column)
    features = frame[feature_columns].to_numpy(dtype=float)
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    return features, truth


def _make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )


def _labeled_subset(y_train: np.ndarray, fraction: float, rng: np.random.Generator) -> np.ndarray:
    """Pick indices of a labeled subset, ensuring both classes are represented."""
    n_labeled = max(4, int(round(fraction * len(y_train))))
    order = rng.permutation(len(y_train))
    labeled = order[:n_labeled]
    # Reshuffle until both classes appear; a one-class labeled set can't train.
    attempts = 0
    while len(np.unique(y_train[labeled])) < 2 and attempts < 100:
        rng.shuffle(order)
        labeled = order[:n_labeled]
        attempts += 1
    return labeled


def run_budget(features, truth, fraction, folds, random_state) -> Dict[str, float]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    rng = np.random.default_rng(random_state)
    supervised_scores: List[float] = []
    selftrain_scores: List[float] = []

    for train_idx, test_idx in splitter.split(features, truth):
        x_train, x_test = features[train_idx], features[test_idx]
        y_train, y_test = truth[train_idx], truth[test_idx]
        labeled = _labeled_subset(y_train, fraction, rng)

        supervised = _make_model()
        supervised.fit(x_train[labeled], y_train[labeled])
        supervised_scores.append(f1_score(y_test, supervised.predict(x_test)))

        # Self-training: mark the unlabeled remainder as -1.
        y_semi = np.full(len(y_train), -1)
        y_semi[labeled] = y_train[labeled]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # frac=1.0 legitimately has no unlabeled rows
            self_training = SelfTrainingClassifier(_make_model())
            self_training.fit(x_train, y_semi)
        selftrain_scores.append(f1_score(y_test, self_training.predict(x_test)))

    n_labeled = max(4, int(round(fraction * len(truth) * (folds - 1) / folds)))
    return {
        "labeled_fraction": fraction,
        "approx_labeled_rows": n_labeled,
        "supervised_f1": round(float(np.mean(supervised_scores)), 4),
        "self_training_f1": round(float(np.mean(selftrain_scores)), 4),
    }


def run(features, truth, budgets, folds, random_state) -> List[Dict[str, float]]:
    return [run_budget(features, truth, b, folds, random_state) for b in budgets]


def save_metrics(results, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "unsupervised_ensemble_f1": UNSUPERVISED_ENSEMBLE_F1,
        "fully_supervised_f1": FULLY_SUPERVISED_F1,
        "budgets": results,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plot_curve(results, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")
    fractions = [r["labeled_fraction"] * 100 for r in results]
    sup = [r["supervised_f1"] for r in results]
    self_t = [r["self_training_f1"] for r in results]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(fractions, sup, "o-", color="#2a9d8f", label="Supervised (labeled subset only)")
    ax.plot(fractions, self_t, "s--", color="#6a4c93", label="Self-training (+ unlabeled)")
    ax.axhline(FULLY_SUPERVISED_F1, color="#264653", ls=":", lw=1.5,
               label=f"Fully supervised ({FULLY_SUPERVISED_F1:.2f})")
    ax.axhline(UNSUPERVISED_ENSEMBLE_F1, color="#c1121f", ls=":", lw=1.5,
               label=f"Unsupervised ensemble ({UNSUPERVISED_ENSEMBLE_F1:.2f})")
    ax.set_xscale("log")
    ax.set_xlabel("Percent of training rows labeled (log scale)")
    ax.set_ylabel("F1 score (5-fold CV)")
    ax.set_ylim(0, 1.05)
    ax.set_title("How many labels does UNSW-NB15 detection need?")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def print_summary(results) -> None:
    print(f"{'labeled %':>10}{'~rows':>8}{'supervised':>12}{'self-train':>12}")
    for r in results:
        print(f"{r['labeled_fraction'] * 100:>9.1f}%{r['approx_labeled_rows']:>8}"
              f"{r['supervised_f1']:>12.3f}{r['self_training_f1']:>12.3f}")
    print(f"\nreference  unsupervised ensemble F1 = {UNSUPERVISED_ENSEMBLE_F1:.2f}"
          f"   fully supervised F1 = {FULLY_SUPERVISED_F1:.2f}")


def main() -> None:
    args = build_parser().parse_args()
    features, truth = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows, {int(truth.sum())} attacks.\n")
    results = run(features, truth, DEFAULT_BUDGETS, args.folds, args.random_state)
    save_metrics(results, Path(args.metrics_output))
    plot_curve(results, Path(args.plot))
    print_summary(results)
    print(f"\nMetrics -> {args.metrics_output}")
    print(f"Plot    -> {args.plot}")


if __name__ == "__main__":
    main()
