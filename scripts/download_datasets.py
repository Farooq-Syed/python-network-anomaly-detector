"""Download the raw public IDS datasets and prepare metadata-retaining subsets.

The committed numeric-only subsets in ``data/`` drop the attack-family / day
metadata that strict generalization experiments require. This script fetches the
raw sources and re-runs the preparation with ``--include-metadata`` so the family
and day columns are retained.

Sources (public, used only for research):
  * UNSW-NB15        - Hugging Face mirror ``Mouwiya/UNSW-NB15`` (0.26 GB).
    Ships ``UNSW_NB15_training-set.csv`` (32 MB) plus two parquet shards read
    by ``prepare_unsw_nb15.py``. Contains ``attack_cat`` (attack family).
  * CIC-IDS2017      - Hugging Face mirror ``bvsam/cic-ids-2017``, the small
    ``machine_learning/`` flow exports (22-67 MB per day) already used by
    ``prepare_cic_ids2017.py``.

Usage:
    python scripts/download_datasets.py --unsw --cic
    python scripts/download_datasets.py --all

Outputs (created under ``data/``):
    unsw_nb15_subset_with_family.csv
    cic_ids2017_subset_with_day.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from prepare_cic_ids2017 import _day_from_name, find_label_column, load_hf, select_numeric_features  # noqa: E402
from prepare_unsw_nb15 import select_features  # noqa: E402

UNSW_OUT = PROJECT_ROOT / "data" / "unsw_nb15_subset_with_family.csv"
CIC_OUT = PROJECT_ROOT / "data" / "cic_ids2017_subset_with_day.csv"

UNSW_HF = "Mouwiya/UNSW-NB15"
CIC_HF = "bvsam/cic-ids-2017"
CIC_FILES = [
    "Monday-WorkingHours.pcap_ISCX.csv.parquet",
    "Tuesday-WorkingHours.pcap_ISCX.csv.parquet",
    "Wednesday-workingHours.pcap_ISCX.csv.parquet",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv.parquet",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv.parquet",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv.parquet",
]


def prepare_unsw_bundle(force: bool = False) -> Path:
    """Prepare the UNSW metadata subset from the HF mirror (split, family label)."""
    if UNSW_OUT.exists() and not force:
        print(f"[UNSW-NB15] existing {UNSW_OUT.name}; use --force to rebuild")
        return UNSW_OUT
    print("[UNSW-NB15] loading the full dataset (training + test parquet shards) ...")
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pip install datasets pyarrow") from exc

    dataset = load_dataset(UNSW_HF, split="train")
    frame = dataset.to_pandas()
    # The mirror keeps the raw UNSW columns (e.g. 'label' 0/1 and 'attack_cat').
    for alias in ("Sload", "Dload", "Spkts", "Dpkts", "Sintpkt", "Dintpkt"):
        if alias in frame.columns and alias.lower() not in frame.columns:
            frame = frame.rename(columns={alias: alias.lower()})

    prepared = select_features(frame, include_metadata=True)
    # Keep a balanced per-class sample so the file stays manageable.
    benign = prepared[prepared["label"] == 0].sample(n=6000, random_state=42)
    attack = prepared[prepared["label"] == 1].sample(n=6000, random_state=42)
    subset = pd.concat([benign, attack], ignore_index=True).sample(frac=1, random_state=42).reset_index(drop=True)
    subset.to_csv(UNSW_OUT, index=False)
    print(f"[UNSW-NB15] wrote {len(subset)} rows -> {UNSW_OUT.name}")
    print(f"    families: {subset['family'].value_counts().to_dict()}")
    return UNSW_OUT


def prepare_cic_bundle(force: bool = False) -> Path:
    """Prepare the CIC-IDS2017 day-metadata subset from the machine_learning flows."""
    if CIC_OUT.exists() and not force:
        print(f"[CIC-IDS2017] existing {CIC_OUT.name}; use --force to rebuild")
        return CIC_OUT
    print("[CIC-IDS2017] fetching day flow exports (8 files, ~250 MB) ...")
    frames: list[tuple[str, pd.DataFrame]] = []
    for name in CIC_FILES:
        frame = load_hf(CIC_HF, "machine_learning/", [name])
        frames.append((name, frame))
        print(f"    <- {name}  ({len(frame)} rows)")
    tagged = _concatenate_tagged(frames)
    label = find_label_column(tagged)
    prepared = select_numeric_features(tagged, label, include_metadata=True)
    benign = prepared[prepared[label] == 0].sample(n=6000, random_state=42)
    attack = prepared[prepared[label] == 1].sample(n=6000, random_state=42)
    subset = pd.concat([benign, attack], ignore_index=True).sample(frac=1, random_state=42).reset_index(drop=True)
    subset.to_csv(CIC_OUT, index=False)
    print(f"[CIC-IDS2017] wrote {len(subset)} rows -> {CIC_OUT.name}")
    print(f"    days: {subset['day'].value_counts().to_dict()}")
    return CIC_OUT


def _concatenate_tagged(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    parts = []
    for name, frame in frames:
        tagged = frame.copy()
        tagged["day"] = _day_from_name(name)
        parts.append(tagged)
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Download + prepare metadata subsets for PNAD.")
    ap.add_argument("--unsw", action="store_true")
    ap.add_argument("--cic", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="Rebuild existing metadata subsets.")
    args = ap.parse_args()

    if args.all or args.unsw:
        prepare_unsw_bundle(force=args.force)
    if args.all or args.cic:
        prepare_cic_bundle(force=args.force)
    if not (args.all or args.unsw or args.cic):
        ap.print_help()


if __name__ == "__main__":
    main()
