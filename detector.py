"""
Research-style network anomaly detector for a cybersecurity portfolio project.

This script supports:
- statistical anomaly detection with z-scores
- unsupervised machine learning with Isolation Forest
- density-based anomaly detection with Local Outlier Factor
- boundary-based anomaly detection with One-Class SVM
- evaluation metrics for labeled datasets
- plots and summary files for GitHub or application materials
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM


DEFAULT_INPUT = "data/sample_network_traffic.csv"
DEFAULT_OUTPUT = "output/anomaly_report.csv"
DEFAULT_SUMMARY = "output/summary.json"
DEFAULT_PLOT_DIR = "output/plots"
DEFAULT_METRICS = "output/metrics.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect unusual network traffic rows from a CSV file.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to the input CSV file.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to write the anomaly report CSV.")
    parser.add_argument("--summary", default=DEFAULT_SUMMARY, help="Path to write a JSON summary.")
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS, help="Path to write model metrics JSON.")
    parser.add_argument("--plot-dir", default=DEFAULT_PLOT_DIR, help="Directory for generated plots.")
    parser.add_argument("--label-column", default=None, help="Optional label column for evaluation, for example 'label'.")
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=2.5,
        help="Z-score threshold used to flag unusual behavior.",
    )
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.12,
        help="Estimated fraction of anomalies for unsupervised models.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducible results.",
    )
    return parser


def load_dataset(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

    dataframe = pd.read_csv(csv_path)
    if dataframe.empty:
        raise ValueError("The input CSV file is empty.")
    return dataframe


def normalize_label(value: object) -> int:
    text = str(value).strip().lower()
    if text in {"1", "true", "attack", "anomaly", "malicious", "yes"}:
        return 1
    if text in {"0", "false", "benign", "normal", "no"}:
        return 0
    raise ValueError(f"Unsupported label value: {value}")


def select_numeric_columns(dataframe: pd.DataFrame, label_column: str | None) -> List[str]:
    numeric_columns = dataframe.select_dtypes(include=["number"]).columns.tolist()
    if label_column and label_column in numeric_columns:
        numeric_columns.remove(label_column)
    if not numeric_columns:
        raise ValueError("No numeric columns were found in the input data.")
    return numeric_columns


def scale_features(dataframe: pd.DataFrame, numeric_columns: List[str]) -> pd.DataFrame:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(dataframe[numeric_columns].astype(float))
    return pd.DataFrame(scaled, columns=numeric_columns, index=dataframe.index)


def compute_z_score_method(dataframe: pd.DataFrame, numeric_columns: List[str], threshold: float) -> pd.DataFrame:
    z_scores = pd.DataFrame(index=dataframe.index)
    for column in numeric_columns:
        series = dataframe[column].astype(float)
        std_dev = series.std(ddof=0)
        if std_dev == 0:
            z_scores[column] = 0.0
        else:
            z_scores[column] = ((series - series.mean()) / std_dev).abs()

    result = pd.DataFrame(index=dataframe.index)
    result["z_score_max"] = z_scores.max(axis=1).round(4)
    result["z_score_flag"] = z_scores.ge(threshold).any(axis=1).astype(int)
    result["z_score_reason"] = z_scores.apply(
        lambda row: "; ".join(
            f"{column}={dataframe.loc[row.name, column]} (z={row[column]:.2f})"
            for column in numeric_columns
            if row[column] >= threshold
        ) or "baseline behavior",
        axis=1,
    )
    return result


def compute_model_methods(
    scaled_features: pd.DataFrame,
    contamination: float,
    random_state: int,
) -> pd.DataFrame:
    result = pd.DataFrame(index=scaled_features.index)

    isolation_forest = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=300,
    )
    isolation_forest.fit(scaled_features)
    result["isolation_forest_flag"] = (isolation_forest.predict(scaled_features) == -1).astype(int)
    result["isolation_forest_score"] = (-isolation_forest.score_samples(scaled_features)).round(4)

    lof = LocalOutlierFactor(contamination=contamination, n_neighbors=min(20, max(2, len(scaled_features) - 1)))
    lof_predictions = lof.fit_predict(scaled_features)
    result["lof_flag"] = (lof_predictions == -1).astype(int)
    result["lof_score"] = (-lof.negative_outlier_factor_).round(4)

    one_class_svm = OneClassSVM(nu=max(0.01, min(0.5, contamination)), kernel="rbf", gamma="scale")
    one_class_svm.fit(scaled_features)
    result["one_class_svm_flag"] = (one_class_svm.predict(scaled_features) == -1).astype(int)
    result["one_class_svm_score"] = (-one_class_svm.score_samples(scaled_features)).round(4)

    return result


def build_report(
    dataframe: pd.DataFrame,
    numeric_columns: List[str],
    label_column: str | None,
    z_threshold: float,
    contamination: float,
    random_state: int,
) -> pd.DataFrame:
    z_method = compute_z_score_method(dataframe, numeric_columns, z_threshold)
    scaled_features = scale_features(dataframe, numeric_columns)
    model_methods = compute_model_methods(scaled_features, contamination, random_state)

    report = pd.concat([dataframe.copy(), z_method, model_methods], axis=1)
    report.insert(0, "row_id", range(1, len(report) + 1))

    vote_columns = [
        "z_score_flag",
        "isolation_forest_flag",
        "lof_flag",
        "one_class_svm_flag",
    ]
    report["ensemble_votes"] = report[vote_columns].sum(axis=1)
    report["is_anomaly"] = (report["ensemble_votes"] >= 2).astype(int)
    report["anomaly_reason"] = report.apply(describe_anomaly_reason, axis=1)

    if label_column and label_column in report.columns:
        report["ground_truth"] = report[label_column].apply(normalize_label)

    return report


def describe_anomaly_reason(row: pd.Series) -> str:
    if row["is_anomaly"] == 0:
        return "baseline behavior"

    reasons: List[str] = []
    if row["z_score_flag"] == 1:
        reasons.append(row["z_score_reason"])
    if row["isolation_forest_flag"] == 1:
        reasons.append("Isolation Forest flagged an unusual feature combination")
    if row["lof_flag"] == 1:
        reasons.append("Local Outlier Factor detected a sparse neighborhood pattern")
    if row["one_class_svm_flag"] == 1:
        reasons.append("One-Class SVM flagged the row outside the learned boundary")

    return "; ".join(dict.fromkeys(reasons))


def compute_metrics(report: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    truth = report["ground_truth"]
    metric_targets = {
        "z_score": report["z_score_flag"],
        "isolation_forest": report["isolation_forest_flag"],
        "local_outlier_factor": report["lof_flag"],
        "one_class_svm": report["one_class_svm_flag"],
        "ensemble": report["is_anomaly"],
    }

    metrics: Dict[str, Dict[str, float]] = {}
    for method_name, predictions in metric_targets.items():
        metrics[method_name] = {
            "precision": round(precision_score(truth, predictions, zero_division=0), 4),
            "recall": round(recall_score(truth, predictions, zero_division=0), 4),
            "f1_score": round(f1_score(truth, predictions, zero_division=0), 4),
            "accuracy": round(accuracy_score(truth, predictions), 4),
            "predicted_anomalies": int(predictions.sum()),
        }
    return metrics


def save_summary(
    report: pd.DataFrame,
    numeric_columns: List[str],
    summary_path: Path,
    z_threshold: float,
    contamination: float,
    metrics: Dict[str, Dict[str, float]] | None,
) -> None:
    summary = {
        "rows_processed": int(len(report)),
        "numeric_features": numeric_columns,
        "anomalies_detected": int(report["is_anomaly"].sum()),
        "z_score_threshold": z_threshold,
        "model_contamination": contamination,
        "flagged_row_ids": report.loc[report["is_anomaly"] == 1, "row_id"].tolist(),
    }
    if metrics:
        best_method = max(metrics.items(), key=lambda item: item[1]["f1_score"])[0]
        summary["best_method_by_f1"] = best_method
        summary["metrics_available"] = True
    else:
        summary["metrics_available"] = False

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def save_metrics(metrics: Dict[str, Dict[str, float]], metrics_path: Path) -> None:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def generate_plots(report: pd.DataFrame, numeric_columns: List[str], plot_dir: Path, metrics: Dict[str, Dict[str, float]] | None) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")

    x_column = "bytes_sent" if "bytes_sent" in report.columns else numeric_columns[0]
    y_column = "packets" if "packets" in report.columns else numeric_columns[min(1, len(numeric_columns) - 1)]
    colors = report["is_anomaly"].map({1: "#c1121f", 0: "#1d3557"})

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(report[x_column], report[y_column], c=colors)
    ax.set_title(f"{x_column} vs {y_column}")
    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    fig.tight_layout()
    fig.savefig(plot_dir / "feature_scatter.png", dpi=180)
    plt.close(fig)

    method_counts = {
        "Z-score": int(report["z_score_flag"].sum()),
        "Isolation Forest": int(report["isolation_forest_flag"].sum()),
        "LOF": int(report["lof_flag"].sum()),
        "One-Class SVM": int(report["one_class_svm_flag"].sum()),
        "Ensemble": int(report["is_anomaly"].sum()),
    }
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(method_counts.keys(), method_counts.values(), color=["#457b9d", "#1d3557", "#588157", "#6a4c93", "#c1121f"])
    ax.set_title("Anomalies Flagged by Detection Method")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(plot_dir / "method_comparison.png", dpi=180)
    plt.close(fig)

    if metrics:
        fig, ax = plt.subplots(figsize=(10, 5))
        method_names = list(metrics.keys())
        f1_scores = [metrics[name]["f1_score"] for name in method_names]
        ax.bar(method_names, f1_scores, color="#c1121f")
        ax.set_title("F1 Score by Detection Method")
        ax.set_ylabel("F1 Score")
        ax.tick_params(axis="x", rotation=15)
        fig.tight_layout()
        fig.savefig(plot_dir / "f1_comparison.png", dpi=180)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6, 5))
        matrix = confusion_matrix(report["ground_truth"], report["is_anomaly"])
        display = ConfusionMatrixDisplay(confusion_matrix=matrix, display_labels=["benign", "attack"])
        display.plot(ax=ax, colorbar=False)
        ax.set_title("Ensemble Confusion Matrix")
        fig.tight_layout()
        fig.savefig(plot_dir / "ensemble_confusion_matrix.png", dpi=180)
        plt.close(fig)


def print_summary(report: pd.DataFrame, numeric_columns: List[str], metrics: Dict[str, Dict[str, float]] | None) -> None:
    print("Numeric features used:")
    for column in numeric_columns:
        print(f"  - {column}")

    print(f"\nProcessed {len(report)} rows.")
    print(f"Flagged {int(report['is_anomaly'].sum())} potential anomalies with the ensemble method.")

    anomaly_rows = report.loc[report["is_anomaly"] == 1, ["row_id", "anomaly_reason"]]
    if anomaly_rows.empty:
        print("No anomalies were found.")
    else:
        print("\nFlagged rows:")
        for _, row in anomaly_rows.iterrows():
            print(f"  - row {int(row['row_id'])}: {row['anomaly_reason']}")

    if metrics:
        best_method = max(metrics.items(), key=lambda item: item[1]["f1_score"])
        print("\nEvaluation metrics:")
        for method_name, method_metrics in metrics.items():
            print(
                f"  - {method_name}: precision={method_metrics['precision']:.2f}, "
                f"recall={method_metrics['recall']:.2f}, f1={method_metrics['f1_score']:.2f}"
            )
        print(f"\nBest method by F1-score: {best_method[0]}")


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    metrics_path = Path(args.metrics_output)
    plot_dir = Path(args.plot_dir)

    dataframe = load_dataset(input_path)
    numeric_columns = select_numeric_columns(dataframe, args.label_column)
    report = build_report(
        dataframe,
        numeric_columns,
        args.label_column,
        z_threshold=args.z_threshold,
        contamination=args.contamination,
        random_state=args.random_state,
    )

    metrics = None
    if args.label_column:
        if args.label_column not in report.columns:
            raise ValueError(f"Label column '{args.label_column}' was not found in the dataset.")
        metrics = compute_metrics(report)
        save_metrics(metrics, metrics_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    save_summary(report, numeric_columns, summary_path, args.z_threshold, args.contamination, metrics)
    generate_plots(report, numeric_columns, plot_dir, metrics)
    print_summary(report, numeric_columns, metrics)
    print(f"\nReport written to: {output_path}")
    print(f"Summary written to: {summary_path}")
    if metrics:
        print(f"Metrics written to: {metrics_path}")
    print(f"Plots written to: {plot_dir}")


if __name__ == "__main__":
    main()
