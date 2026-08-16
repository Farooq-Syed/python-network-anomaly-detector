"""Can we decide which flows to label, instead of labeling at random?

label_budget_experiment.py shows that a few dozen random labels recover most of the
unsupervised -> supervised gap on UNSW-NB15. This script asks whether an *active*
learner can do even better: with a fixed labeling budget, does choosing the most
uncertain unlabeled flows (uncertainty sampling) beat choosing them at random?

Mechanics, kept deliberately simple:
  - a small random seed of labels gets the model started
  - each round, the model predicts probabilities on the unlabeled rows; the
    uncertainty strategy labels the `batch` rows whose probability is closest to
    0.5, the random strategy labels `batch` random rows
  - both strategies are compared under the same folds and the same budget

Usage:
    python active_learning_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
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

from detector import normalize_label, select_numeric_columns

DEFAULT_INPUT = "data/unsw_nb15_public_subset.csv"
DEFAULT_METRICS = "output/active_learning_metrics.json"
DEFAULT_PLOT = "output/plots/active_learning_curve.png"

UNSUPERVISED_ENSEMBLE_F1 = 0.27
FULLY_SUPERVISED_F1 = 0.996

DEFAULT_SEED = 10
DEFAULT_BATCH = 10
DEFAULT_BUDGET = 240
STRATEGIES = ["random", "uncertainty"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare random labeling against uncertainty-sampling active learning."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS)
    parser.add_argument("--plot", default=DEFAULT_PLOT)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed-size", type=int, default=DEFAULT_SEED, help="Labels to seed the learner.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH, help="Labels added per round.")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Total labels allowed.")
    parser.add_argument("--unsupervised-reference", type=float, default=UNSUPERVISED_ENSEMBLE_F1, help="Reference unsupervised F1 (drawn on the plot).")
    parser.add_argument("--supervised-reference", type=float, default=FULLY_SUPERVISED_F1, help="Reference fully-supervised F1 (drawn on the plot).")
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
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


def select_queries(probabilities: np.ndarray, n: int, strategy: str, rng: np.random.Generator) -> np.ndarray:
    """Pick the next rows to label under a query strategy.

    Uncertainty sampling labels the rows the current model is least sure about —
    the predictions closest to 0.5. Random sampling is the baseline to beat.
    """
    if strategy == "uncertainty":
        return np.argsort(np.abs(probabilities - 0.5))[:n]
    return rng.choice(len(probabilities), size=n, replace=False)


def _seed_labels(y_train: np.ndarray, seed_size: int, rng: np.random.Generator) -> np.ndarray:
    """Pick a starting labeled set that contains both classes."""
    positive = np.where(y_train == 1)[0]
    negative = np.where(y_train == 0)[0]
    if len(positive) < 1 or len(negative) < 1:
        raise ValueError("Seed labels require at least one row of each class in the training fold.")
    take = min(seed_size // 2, len(positive), len(negative))
    chosen = np.concatenate([rng.choice(positive, size=take, replace=False), rng.choice(negative, size=take, replace=False)])
    return chosen


def run_fold(features, truth, train_idx, test_idx, strategy, seed_size, batch_size, budget, random_state) -> Dict[str, float]:
    x_train, x_test = features[train_idx], features[test_idx]
    y_train, y_test = truth[train_idx], truth[test_idx]
    rng = np.random.default_rng(random_state)

    labeled = _seed_labels(y_train, seed_size, rng)
    labeled = np.asarray(labeled, dtype=int)
    unlabeled_mask = np.ones(len(y_train), dtype=bool)
    unlabeled_mask[labeled] = False

    result: Dict[str, float] = {}
    while len(labeled) <= budget and unlabeled_mask.any():
        model = _make_model()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train[labeled], y_train[labeled])
        f1 = f1_score(y_test, model.predict(x_test), zero_division=0)
        result[len(labeled)] = round(float(f1), 4)

        remaining = np.where(unlabeled_mask)[0]
        probabilities = model.predict_proba(x_train[remaining])[:, 1]
        next_size = min(batch_size, budget - len(labeled))
        if next_size <= 0:
            break
        queries = select_queries(probabilities, next_size, strategy, rng)
        chosen = remaining[queries]
        labeled = np.concatenate([labeled, chosen])
        unlabeled_mask[chosen] = False

    return result


def run(features, truth, folds, seed_size, batch_size, budget, random_state) -> Dict[str, Dict[int, Dict[str, float]]]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    per_strategy: Dict[str, Dict[int, List[float]]] = {strategy: {} for strategy in STRATEGIES}
    for train_idx, test_idx in splitter.split(features, truth):
        for strategy in STRATEGIES:
            fold_result = run_fold(features, truth, train_idx, test_idx, strategy, seed_size, batch_size, budget, random_state)
            for label_count, f1 in fold_result.items():
                per_strategy[strategy].setdefault(label_count, []).append(f1)

    averaged: Dict[str, Dict[int, Dict[str, float]]] = {}
    for strategy, counts in per_strategy.items():
        averaged[strategy] = {}
        for count, scores in sorted(counts.items()):
            averaged[strategy][count] = {
                "f1_mean": round(float(np.mean(scores)), 4),
                "f1_std": round(float(np.std(scores)), 4),
            }
    return averaged


def save_metrics(results: Dict[str, Dict[int, Dict[str, float]]], path: Path, unsupervised_ref: float, supervised_ref: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "unsupervised_ensemble_f1": unsupervised_ref,
        "fully_supervised_f1": supervised_ref,
        "strategies": {
            strategy: [{"labels": count, **scores} for count, scores in counts.items()]
            for strategy, counts in results.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plot_curves(results: Dict[str, Dict[int, Dict[str, float]]], path: Path, unsupervised_ref: float, supervised_ref: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = {"random": "#e76f51", "uncertainty": "#2a9d8f"}
    for strategy, scores in results.items():
        counts = list(scores.keys())
        f1s = [scores[c]["f1_mean"] for c in counts]
        ax.plot(counts, f1s, "o-", color=colors[strategy], label=f"{strategy} sampling")
    ax.axhline(supervised_ref, color="#264653", ls=":", lw=1.5, label=f"Fully supervised ({supervised_ref:.2f})")
    ax.axhline(unsupervised_ref, color="#c1121f", ls=":", lw=1.5, label=f"Unsupervised ensemble ({unsupervised_ref:.2f})")
    ax.set_xlabel("Number of labeled flows (budget)")
    ax.set_ylabel("F1 score (5-fold CV)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Random vs. uncertainty sampling under a label budget")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def print_summary(results: Dict[str, Dict[int, Dict[str, float]]]) -> None:
    counts = sorted(next(iter(results.values())).keys())
    print(f"{'labels':>8}{'random':>10}{'uncertainty':>12}")
    for count in counts:
        random_f1 = results["random"][count]["f1_mean"]
        random_std = results["random"][count]["f1_std"]
        uncertainty_f1 = results["uncertainty"][count]["f1_mean"]
        uncertainty_std = results["uncertainty"][count]["f1_std"]
        print(f"{count:>8}{random_f1:>8.3f}±{random_std:.3f}{uncertainty_f1:>8.3f}±{uncertainty_std:.3f}")
    print(f"\nreference  unsupervised ensemble F1 = {UNSUPERVISED_ENSEMBLE_F1:.2f}"
          f"   fully supervised F1 = {FULLY_SUPERVISED_F1:.2f}")


def main() -> None:
    args = build_parser().parse_args()
    features, truth = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows, {int(truth.sum())} attacks.\n")
    results = run(features, truth, args.folds, args.seed_size, args.batch_size, args.budget, args.random_state)
    save_metrics(results, Path(args.metrics_output), args.unsupervised_reference, args.supervised_reference)
    plot_curves(results, Path(args.plot), args.unsupervised_reference, args.supervised_reference)
    print_summary(results)
    print(f"\nMetrics -> {args.metrics_output}")
    print(f"Plot    -> {args.plot}")


if __name__ == "__main__":
    main()
