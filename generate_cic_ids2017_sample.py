"""Generate a small synthetic CIC-IDS2017-style sample.

The full CIC-IDS2017 dataset is a multi-gigabyte download, which is fine to fetch
when you want the real thing but wrong for a repo. This script emits a small,
deterministic CSV in the CIC column vocabulary (Flow Duration, Total Fwd Packets,
..., Label) so the benchmark comparison pipeline has a second, different schema to
exercise. The distributions are invented and the file is meant for pipeline tests,
not as a stand-in for the real benchmark.

Usage:
    python generate_cic_ids2017_sample.py --output data/sample_cic_ids2017_style.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_OUTPUT = "data/sample_cic_ids2017_style.csv"

COLUMNS = [
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Fwd Packet Length Mean",
    "Bwd Packet Length Mean",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Avg Fwd Segment Size",
    "Avg Bwd Segment Size",
    "Init_Win_bytes_forward",
    "Init_Win_bytes_backward",
    "Active Mean",
    "Idle Mean",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a small synthetic CIC-IDS2017-style CSV.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to the generated CSV.")
    parser.add_argument("--rows", type=int, default=400, help="Number of rows to generate.")
    parser.add_argument("--random-state", type=int, default=42)
    return parser


def generate(rows: int, random_state: int) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    data = {
        "Flow ID": [f"f-{i}" for i in range(rows)],
        "Label": [],
    }
    values = {}
    for column in COLUMNS:
        benign = rng.lognormal(mean=6.0, sigma=1.2, size=rows)
        attacks = benign * rng.uniform(2.0, 8.0, size=rows)
        is_attack = np.zeros(rows, dtype=bool)
        is_attack[: rows // 5] = True  # roughly 20% attack rows, shuffled later
        rng.shuffle(is_attack)
        values[column] = np.where(is_attack, attacks, benign)
    frame = pd.DataFrame(values)
    frame["Flow ID"] = data["Flow ID"]
    frame["Label"] = np.where(is_attack, rng.choice(["DoS Hulk", "PortScan", "DDoS"], size=rows), "BENIGN")
    return frame[["Flow ID", *COLUMNS, "Label"]]


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output)
    frame = generate(args.rows, args.random_state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    print(f"Generated {len(frame)} rows with {int((frame['Label'] != 'BENIGN').sum())} attacks.")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
