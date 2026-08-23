"""Compare unsupervised and supervised detection on a chosen public benchmark.

detector.py reports F1 ~= 0.27 for the unsupervised ensemble on the UNSW-NB15
subset, and supervised_baseline.py reports ~= 0.99. Both numbers come from one
benchmark. This script is the generalization check: point it at another benchmark
(CIC-IDS2017, or a different UNSW subset) and it runs the same two families under
the same cross-validation, so the question "is the gap specific to UNSW-NB15 or
does it hold across benchmarks?" has a reproducible answer.

The label handling is schema-aware via detector.prepare_benchmark, so a CIC
file and an UNSW file are consumed the same way from the caller's perspective.

Usage:
    python benchmark_compare.py --input data/sample_cic_ids2017_style.csv
    python benchmark_compare.py --input data/unsw_nb15_public_subset.csv --label-column label
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from detector import (
    compute_model_methods,
    compute_z_score_method,
    normalize_label,
    prepare_benchmark,
    scale_features,
    select_numeric_columns,
)

DEFAULT_INPUT = "data/sample_cic_ids2017_style.csv"
DEFAULT_METRICS = "output/benchmark_comparison.json"
DEFAULT_PLOT = "output/plots/benchmark_comparison.png"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run unsupervised and supervised detection on a public network benchmark."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to the benchmark CSV.")
    parser.add_argument("--label-column", default=None, help="Label column (UNSW/generic CSVs).")
    parser.add_argument("--z-threshold", type=float, default=2.5)
    parser.add_argument("--contamination", type=float, default=0.12)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS)
    parser.add_argument("--plot", default=DEFAULT_PLOT)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--dataset-name", default=None, help="Canonical dataset name for provenance.")
    parser.add_argument("--source-url", default=None, help="Authoritative dataset landing page.")
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unsupervised_ensemble(features: pd.DataFrame, numeric_columns: List[str], z_threshold: float, contamination: float, random_state: int) -> np.ndarray:
    """Recreate the main tool's four-detector vote on a feature frame."""
    z_report = compute_z_score_method(features, numeric_columns, z_threshold)
    scaled = scale_features(features, numeric_columns)
    model_report = compute_model_methods(scaled, contamination, random_state)
    votes = (
        z_report["z_score_flag"]
        + model_report["isolation_forest_flag"]
        + model_report["lof_flag"]
        + model_report["one_class_svm_flag"]
    )
    return (votes >= 2).astype(int).to_numpy()


def supervised_cv(features: pd.DataFrame, truth: np.ndarray, folds: int, random_state: int) -> Dict[str, float]:
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []
    aucs: List[float] = []
    for train_idx, test_idx in splitter.split(features, truth):
        model.fit(features.iloc[train_idx], truth[train_idx])
        predicted = model.predict(features.iloc[test_idx])
        probabilities = model.predict_proba(features.iloc[test_idx])[:, 1]
        precisions.append(precision_score(truth[test_idx], predicted, zero_division=0))
        recalls.append(recall_score(truth[test_idx], predicted, zero_division=0))
        f1s.append(f1_score(truth[test_idx], predicted, zero_division=0))
        aucs.append(roc_auc_score(truth[test_idx], probabilities))
    return {
        "precision": round(float(np.mean(precisions)), 4),
        "precision_std": round(float(np.std(precisions)), 4),
        "recall": round(float(np.mean(recalls)), 4),
        "recall_std": round(float(np.std(recalls)), 4),
        "f1": round(float(np.mean(f1s)), 4),
        "f1_std": round(float(np.std(f1s)), 4),
        "roc_auc": round(float(np.mean(aucs)), 4),
        "roc_auc_std": round(float(np.std(aucs)), 4),
    }


def save_metrics(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plot_comparison(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["Unsupervised\nensemble", "Supervised\n(logistic regression)"]
    f1_values = [payload["unsupervised"]["f1"], payload["supervised"]["f1"]]
    bars = ax.bar(labels, f1_values, color=["#c1121f", "#2a9d8f"])
    for bar, value in zip(bars, f1_values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{value:.3f}", ha="center")
    ax.set_ylabel("F1 score (CV)")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{payload['schema']} — labels vs. no labels")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    features, truth, schema = prepare_benchmark(input_path, args.label_column)
    numeric_columns = features.select_dtypes(include=["number"]).columns.tolist()

    unsupervised_pred = unsupervised_ensemble(features, numeric_columns, args.z_threshold, args.contamination, args.random_state)
    unsupervised = {
        "precision": round(float(precision_score(truth, unsupervised_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(truth, unsupervised_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(truth, unsupervised_pred, zero_division=0)), 4),
    }
    supervised = supervised_cv(features, truth, args.folds, args.random_state)

    payload = {
        "provenance": {
            "dataset_name": args.dataset_name or schema,
            "source_url": args.source_url,
            "input_path": str(input_path),
            "input_sha256": sha256_file(input_path),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "random_state": args.random_state,
            "folds": args.folds,
        },
        "schema": schema,
        "rows": int(len(truth)),
        "attacks": int(truth.sum()),
        "numeric_features": numeric_columns,
        "unsupervised": unsupervised,
        "supervised": supervised,
        "gap_f1": round(supervised["f1"] - unsupervised["f1"], 4),
    }
    save_metrics(payload, Path(args.metrics_output))
    plot_comparison(payload, Path(args.plot))

    print(f"Benchmark schema : {schema} ({len(truth)} rows, {int(truth.sum())} attacks)")
    print(f"Unsupervised      : precision={unsupervised['precision']:.3f} recall={unsupervised['recall']:.3f} f1={unsupervised['f1']:.3f}")
    print(f"Supervised        : precision={supervised['precision']:.3f} recall={supervised['recall']:.3f} f1={supervised['f1']:.3f} auc={supervised['roc_auc']:.3f}")
    print(f"F1 gap            : +{payload['gap_f1']:.3f}")
    print(f"\nMetrics -> {args.metrics_output}")
    print(f"Plot    -> {args.plot}")


if __name__ == "__main__":
    main()
