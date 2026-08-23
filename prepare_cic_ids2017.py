"""Prepare a manageable CIC-style subset for the anomaly detector.

CIC-IDS2017 is a large public intrusion detection benchmark (the flow CSVs total
several gigabytes). This script builds a small, balanced subset from either:

- local files: pass one or more of the official per-day CSVs with --files
- a Hugging Face mirror: pass the dataset id with --hf-dataset plus the file names
  under it (defaults to the `machine_learning/` flow CSVs of bvsam/cic-ids-2017)

Whichever source is used, the output is a CSV of the numeric flow features plus a
binary Label column (BENIGN = 0, anything else = 1), which the detector's
schema-aware loader (`prepare_benchmark`) consumes directly.

Although the filename keeps the original project name, the preparation logic also
works on closely related CICFlowMeter exports such as CSE-CIC-IDS2018, which share
the same broad schema (numeric flow features plus a string label column).

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
    parser.add_argument("--include-metadata", action="store_true",
        help="Retain a 'day' column (per source/flow file, used for day splits) and a "
             "'label_name' column with the original attack-type string, so strict "
             "train-on-one-day/test-on-unseen-day and family evaluation is possible. "
             "Off by default to keep outputs byte-identical to the existing numeric subsets.")
    return parser


def _load_one(path: str) -> pd.DataFrame:
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


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


def select_numeric_features(dataframe: pd.DataFrame, label_column: str, include_metadata: bool = False) -> pd.DataFrame:
    """Keep numeric CICFlowMeter features and a clean binary label.

    Some real CIC CSV exports contain repeated header rows in the middle of the file,
    which show up as rows whose label is literally "Label". Those rows are metadata,
    not traffic, and must be removed before binarizing the label column.

    With ``include_metadata``, the original attack-type string is also retained as
    ``label_name`` and any ``day`` column present is passed through, so strict
    family/day splits are possible downstream.
    """
    valid_rows = dataframe[label_column].astype(str).str.strip().str.lower() != label_column.lower()
    filtered = dataframe.loc[valid_rows].copy()

    # Preserve an explicitly-attached day/source tag when metadata is requested,
    # so strict day-based splits are possible downstream.
    day_values = filtered["day"].copy() if include_metadata and "day" in filtered.columns else None

    # CICFlowMeter CSVs can pick up repeated header rows mid-file, which may force
    # pandas to infer some otherwise-numeric columns as object dtype. Coerce every
    # non-label column back toward numeric and keep the ones that succeed.
    feature_candidates = [column for column in filtered.columns if column != label_column and column != "day"]
    coerced_features = filtered[feature_candidates].apply(pd.to_numeric, errors="coerce")
    coerced_features = coerced_features.dropna(axis=1, how="all")
    numeric_columns = coerced_features.columns.tolist()
    if not numeric_columns:
        raise ValueError("No numeric feature columns were found in the CIC-style data.")

    prepared = coerced_features[numeric_columns].copy()
    if day_values is not None:
        prepared["day"] = day_values.values
    prepared[label_column] = filtered[label_column].values
    label_name = prepared[label_column].astype(str)
    prepared[label_column] = prepared[label_column].apply(
        lambda value: 0 if str(value).strip().lower() == "benign" else 1
    )
    if include_metadata:
        prepared["label_name"] = label_name.values
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


def _day_from_name(name: str) -> str:
    """Derive a stable day tag from a CIC flow-sheet filename.

    HF/local names look like ``Monday-WorkingHours...`` or
    ``Thursday-WorkingHours-Morning-WebAttacks...``. Extract the leading
    weekday token and fall back to the file stem when it is absent.
    """
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday")
    for day in weekdays:
        if day.lower() in name.lower():
            return day
    return Path(name).stem.lower()


def _tag_day(dataframe: pd.DataFrame, source_name: str, single: bool) -> pd.DataFrame:
    """Attach a ``day`` column to a frame from a single flow-sheet source."""
    tagged = dataframe.copy()
    tagged["day"] = _day_from_name(source_name)
    return tagged


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output)

    if args.files:
        frames = [_load_one(path) for path in args.files]
        if args.include_metadata:
            frames = [_tag_day(df, name, single=True) for df, name in zip(frames, args.files)]
        combined = pd.concat(frames, ignore_index=True)
        source_description = f"{len(frames)} local file(s)"
    elif args.hf_dataset:
        file_names = args.hf_files or DEFAULT_HF_FILES
        if args.include_metadata:
            frames = []
            for name in file_names:
                frame = load_hf(args.hf_dataset, args.hf_prefix, [name])
                frames.append(_tag_day(frame, name, single=True))
            combined = pd.concat(frames, ignore_index=True)
        else:
            combined = load_hf(args.hf_dataset, args.hf_prefix, file_names)
        source_description = f"Hugging Face dataset {args.hf_dataset}"
    else:
        raise ValueError("Provide --files or --hf-dataset.")
    label_column = find_label_column(combined)
    prepared = select_numeric_features(combined, label_column, args.include_metadata)
    prepared = sample_balanced(prepared, label_column, args.rows_per_class, args.random_state)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output_path, index=False)

    benign_count = int((prepared[label_column] == 0).sum())
    attack_count = int((prepared[label_column] == 1).sum())
    print(f"Source            : {source_description}")
    print(f"Prepared dataset  : {output_path}")
    print(f"Rows              : {len(prepared)}")
    extra = 2 if args.include_metadata else 0  # label_name + day
    print(f"Numeric features  : {len(prepared.columns) - 1 - extra}")
    print(f"Benign rows       : {benign_count}")
    print(f"Attack rows       : {attack_count}")


if __name__ == "__main__":
    main()
