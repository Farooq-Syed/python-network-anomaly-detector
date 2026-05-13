"""
Prepare a manageable UNSW-NB15 subset for the anomaly detector.

Expected input files from the official UNSW-NB15 split:
- UNSW_NB15_training-set.csv
- UNSW_NB15_testing-set.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_OUTPUT = "data/unsw_nb15_portfolio_subset.csv"

FEATURE_CANDIDATES = [
    "dur",
    "spkts",
    "dpkts",
    "sbytes",
    "dbytes",
    "sttl",
    "dttl",
    "sload",
    "dload",
    "sloss",
    "dloss",
    "smean",
    "dmean",
    "sinpkt",
    "dinpkt",
    "tcprtt",
    "synack",
    "ackdat",
    "ct_srv_src",
    "ct_dst_ltm",
    "ct_src_ltm",
    "ct_dst_src_ltm",
    "ct_state_ttl",
    "ct_flw_http_mthd",
    "is_sm_ips_ports",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a smaller UNSW-NB15 CSV for the detector project.")
    parser.add_argument("--train", required=True, help="Path to UNSW_NB15_training-set.csv")
    parser.add_argument("--test", required=True, help="Path to UNSW_NB15_testing-set.csv")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to the prepared output CSV.")
    parser.add_argument(
        "--rows-per-class",
        type=int,
        default=4000,
        help="Maximum number of rows to keep for each label class.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed used when sampling.",
    )
    return parser


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    dataframe = pd.read_csv(path)
    if dataframe.empty:
        raise ValueError(f"Input file is empty: {path}")
    return dataframe


def sample_balanced(dataframe: pd.DataFrame, rows_per_class: int, random_state: int) -> pd.DataFrame:
    parts = []
    for label_value, group in dataframe.groupby("label"):
        sample_size = min(rows_per_class, len(group))
        parts.append(group.sample(n=sample_size, random_state=random_state))
    return pd.concat(parts, ignore_index=True).sample(frac=1, random_state=random_state).reset_index(drop=True)


def main() -> None:
    args = build_parser().parse_args()
    train_path = Path(args.train)
    test_path = Path(args.test)
    output_path = Path(args.output)

    combined = pd.concat([load_csv(train_path), load_csv(test_path)], ignore_index=True)

    if "label" not in combined.columns:
        raise ValueError("Expected a 'label' column in the UNSW-NB15 CSV files.")

    selected_columns = [column for column in FEATURE_CANDIDATES if column in combined.columns]
    if not selected_columns:
        raise ValueError("None of the expected UNSW-NB15 numeric feature columns were found.")

    prepared = combined[selected_columns + ["label"]].copy()
    prepared["label"] = prepared["label"].astype(int)
    prepared = prepared.dropna()
    prepared = sample_balanced(prepared, args.rows_per_class, args.random_state)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output_path, index=False)

    benign_count = int((prepared["label"] == 0).sum())
    attack_count = int((prepared["label"] == 1).sum())

    print(f"Prepared dataset written to: {output_path}")
    print(f"Rows: {len(prepared)}")
    print(f"Features kept: {len(selected_columns)}")
    print(f"Benign rows: {benign_count}")
    print(f"Attack rows: {attack_count}")


if __name__ == "__main__":
    main()
