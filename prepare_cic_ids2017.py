"""Prepare a manageable CIC-IDS2017 subset for the anomaly detector.

CIC-IDS2017 is a large public intrusion detection benchmark (the flow CSVs total
several gigabytes). This script builds a small, balanced subset from either:

- local files: pass one or more of the official per-day CSVs with --files
- a Hugging Face mirror: pass the dataset id with --hf-dataset plus the file names
  under it (defaults to the `machine_learning/` flow CSVs of bvsam/cic-ids-2017)

Whichever source is used, the output is a CSV of the numeric flow features plus a
binary Label column (BENIGN = 0, anything else = 1), which the detector's
schema-aware loader (`prepare_benchmark`) consumes directly.

Usage:
    python prepare_cic_ids2017.py --files "C:\\data\\Wednesday-workingHours.pcap_ISCX.csv"
    python prepare_cic_ids2017.py --hf-dataset bvsam/cic-ids-2017 --output data/cic_ids2017_subset.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_OUTPUT = "data/cic_ids2017_subset.csv"

# Default Hugging Face mirror and its flow files (the preprocessed, label-carrying
# "machine learning" split rather than the raw pcap exports).
DEFAULT_HF_DATASET = "bvsam/cic-ids-2017"
DEFAULT_HF_FILES = [
    "Monday-WorkingHours.pcap_ISCX.csv.parquet",
    "Tuesday-WorkingHours.pcap_ISCX.csv.parquet",
    "Wednesday-workingHours.pcap_ISCX.csv.parquet",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv.parquet",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv.parquet",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a smaller CIC-IDS2017 CSV for the detector project.")
    parser.add_argument("--files", nargs="*", help="Paths to local CIC-IDS2017 flow CSV or parquet files.")
    parser.add_argument("--hf-dataset", default=DEFAULT_HF_DATASET, help="Hugging Face dataset id, for example bvsam/cic-ids-2017.")
    parser.add_argument("--hf-prefix", default="machine_learning/", help="Folder prefix within the HF dataset.")
    parser.add_argument("--hf-files", nargs="*", help="File names within the HF dataset; defaults to all 8 flow days.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to the prepared output CSV.")
    parser.add_argument("--rows-per-class", type=int, default=6000, help="Maximum rows to keep for each label class.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed used when sampling.")
    return parser


def _load_one(path: str) -> pd.DataFrame:
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)


def load_hf(dataset_id: str, prefix: str, file_names: list[str]) -> pd.DataFrame:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError(
            "The Hugging Face workflow requires the 'datasets' package. "
            "Install it with: python -m pip install datasets pyarrow"
        ) from exc

    data_files = [
        f"https://huggingface.co/datasets/{dataset_id}/resolve/main/{prefix}{name}"
        for name in file_names
    ]
    dataset = load_dataset("parquet", data_files=data_files, split="train")
    return dataset.to_pandas()


def find_label_column(dataframe: pd.DataFrame) -> str:
    for candidate in ("Label", "label", "Class"):
        if candidate in dataframe.columns:
            return candidate
    raise ValueError("No label column ('Label'/'label') was found in the CIC-IDS2017 data.")


def select_numeric_features(dataframe: pd.DataFrame, label_column: str) -> pd.DataFrame:
    numeric_columns = dataframe.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_columns:
        raise ValueError("No numeric feature columns were found in the CIC-IDS2017 data.")
    prepared = dataframe[numeric_columns + [label_column]].copy()
    prepared[label_column] = prepared[label_column].apply(
        lambda value: 0 if str(value).strip().lower() == "benign" else 1
    )
    # Rate-style columns (e.g. "Flow Bytes/s") carry inf where a flow had zero
    # duration; replace those with NaN so the dropna() below removes the row.
    prepared = prepared.replace([float("inf"), float("-inf")], float("nan"))
    return prepared.dropna()


def sample_balanced(dataframe: pd.DataFrame, label_column: str, rows_per_class: int, random_state: int) -> pd.DataFrame:
    parts = []
    for label_value, group in dataframe.groupby(label_column):
        sample_size = min(rows_per_class, len(group))
        parts.append(group.sample(n=sample_size, random_state=random_state))
    return pd.concat(parts, ignore_index=True).sample(frac=1, random_state=random_state).reset_index(drop=True)


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output)

    if args.files:
        frames = [_load_one(path) for path in args.files]
        combined = pd.concat(frames, ignore_index=True)
        source_description = f"{len(frames)} local file(s)"
    elif args.hf_dataset:
        file_names = args.hf_files or DEFAULT_HF_FILES
        combined = load_hf(args.hf_dataset, args.hf_prefix, file_names)
        source_description = f"Hugging Face dataset {args.hf_dataset}"
    else:
        raise ValueError("Provide --files or --hf-dataset.")
    label_column = find_label_column(combined)
    prepared = select_numeric_features(combined, label_column)
    prepared = sample_balanced(prepared, label_column, args.rows_per_class, args.random_state)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output_path, index=False)

    benign_count = int((prepared[label_column] == 0).sum())
    attack_count = int((prepared[label_column] == 1).sum())
    print(f"Source            : {source_description}")
    print(f"Prepared dataset  : {output_path}")
    print(f"Rows              : {len(prepared)}")
    print(f"Numeric features  : {len(prepared.columns) - 1}")
    print(f"Benign rows       : {benign_count}")
    print(f"Attack rows       : {attack_count}")


if __name__ == "__main__":
    main()
