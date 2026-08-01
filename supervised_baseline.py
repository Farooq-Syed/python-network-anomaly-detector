"""Supervised baseline for the network anomaly detector.

The main tool (detector.py) is unsupervised: it flags anomalies without ever seeing
a label. This script answers the natural follow-up question — how much do the labels
actually buy you? — by training supervised classifiers on the same labeled dataset
and comparing them, under identical cross-validation, against the unsupervised
ensemble.

To keep the comparison honest, every supervised model is wrapped in a scikit-learn
Pipeline so that feature scaling is fit inside each training fold only. This prevents
the scaler from seeing held-out rows (a subtle form of leakage) and makes the
cross-validated estimate trustworthy.

Usage:
    python supervised_baseline.py --input data/unsw_nb15_public_subset.csv --label-column label
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Reuse the detector's label parsing and leakage-aware feature selection so the two
# scripts agree exactly on which columns are features and how labels are read.
from detector import normalize_label, select_numeric_columns

DEFAULT_INPUT = "data/unsw_nb15_public_subset.csv"
DEFAULT_METRICS = "output/supervised_metrics.json"
DEFAULT_PLOT = "output/plots/supervised_vs_unsupervised.png"

# The unsupervised ensemble's F1 on this UNSW-NB15 subset, reported by detector.py.
# Used only as a reference bar in the comparison plot.
UNSUPERVISED_ENSEMBLE_F1 = 0.27


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train supervised baselines and compare them to the unsupervised ensemble."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to the labeled CSV.")
    parser.add_argument("--label-column", default="label", help="Name of the label column.")
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS, help="Where to write metrics JSON.")
    parser.add_argument("--plot", default=DEFAULT_PLOT, help="Where to write the comparison plot.")
    parser.add_argument("--folds", type=int, default=5, help="Cross-validation folds.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed.")
    return parser


def load_labeled(path: Path, label_column: str):
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    dataframe = pd.read_csv(path)
    if label_column not in dataframe.columns:
        raise ValueError(f"Label column '{label_column}' not found in the dataset.")
    feature_columns = select_numeric_columns(dataframe, label_column)
    features = dataframe[feature_columns].astype(float)
    truth = dataframe[label_column].apply(normalize_label)
    return features, truth, feature_columns


def evaluate_model(name, model, features, truth, splitter) -> Dict[str, float]:
    """Cross-validated metrics for one model, including ROC-AUC from probabilities."""
    predictions = cross_val_predict(model, features, truth, cv=splitter, method="predict")
    probabilities = cross_val_predict(
        model, features, truth, cv=splitter, method="predict_proba"
    )[:, 1]
    return {
        "precision": round(precision_score(truth, predictions, zero_division=0), 4),
        "recall": round(recall_score(truth, predictions, zero_division=0), 4),
        "f1_score": round(f1_score(truth, predictions, zero_division=0), 4),
        "accuracy": round(accuracy_score(truth, predictions), 4),
        "roc_auc": round(roc_auc_score(truth, probabilities), 4),
    }


def run(features, truth, folds: int, random_state: int) -> Dict[str, Dict[str, float]]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    models = {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced"),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            random_state=random_state,
            class_weight="balanced",
            min_samples_leaf=2,
            n_jobs=-1,
        ),
    }
    return {name: evaluate_model(name, model, features, truth, splitter)
            for name, model in models.items()}


def save_metrics(metrics: Dict[str, Dict[str, float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(metrics)
    payload["unsupervised_ensemble_f1_reference"] = UNSUPERVISED_ENSEMBLE_F1
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plot_comparison(metrics: Dict[str, Dict[str, float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")
    names = ["Unsupervised\nensemble"] + [n.replace("_", "\n") for n in metrics]
    f1s = [UNSUPERVISED_ENSEMBLE_F1] + [metrics[n]["f1_score"] for n in metrics]
    colors = ["#6c757d"] + ["#2a9d8f"] * len(metrics)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, f1s, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("F1 score (5-fold CV)")
    ax.set_title("Supervised vs. unsupervised detection on UNSW-NB15")
    for bar, value in zip(bars, f1s):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.2f}",
                ha="center", va="bottom", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def print_summary(metrics: Dict[str, Dict[str, float]]) -> None:
    print(f"{'MODEL':<22}{'PREC':>7}{'RECALL':>8}{'F1':>7}{'AUC':>7}")
    for name, m in metrics.items():
        print(f"{name:<22}{m['precision']:>7.3f}{m['recall']:>8.3f}"
              f"{m['f1_score']:>7.3f}{m['roc_auc']:>7.3f}")
    best = max(metrics.items(), key=lambda kv: kv[1]["f1_score"])
    gap = best[1]["f1_score"] - UNSUPERVISED_ENSEMBLE_F1
    print(f"\nUnsupervised ensemble F1 (reference): {UNSUPERVISED_ENSEMBLE_F1:.2f}")
    print(f"Best supervised model: {best[0]} (F1={best[1]['f1_score']:.3f})")
    print(f"F1 improvement from labels: +{gap:.2f}")


def main() -> None:
    args = build_parser().parse_args()
    features, truth, feature_columns = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows, {len(feature_columns)} features, "
          f"{int(truth.sum())} attack rows.\n")

    metrics = run(features, truth, args.folds, args.random_state)
    save_metrics(metrics, Path(args.metrics_output))
    plot_comparison(metrics, Path(args.plot))
    print_summary(metrics)
    print(f"\nMetrics written to: {args.metrics_output}")
    print(f"Plot written to: {args.plot}")


if __name__ == "__main__":
    main()
