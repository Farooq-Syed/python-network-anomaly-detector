"""Tests for the additive --include-metadata paths in the prepare_*.py scripts."""

import numpy as np
import pandas as pd

from prepare_cic_ids2017 import select_numeric_features as cic_features
from prepare_cic_ids2017 import find_label_column
from prepare_cic_ids2017 import _day_from_name
from prepare_unsw_nb15 import FEATURE_CANDIDATES, select_features as unsw_features

UNSW_FAMILIES = ["Fuzzers", "Analysis", "Backdoors", "DoS", "Exploits",
                 "Generic", "Reconnaissance", "Shellcode", "Worms"]


def _unsw_frame() -> pd.DataFrame:
    rows = []
    for label, fam in [(0, "Normal")] + [(1, f) for f in UNSW_FAMILIES]:
        for _ in range(3):
            row = {col: float(np.random.rand()) for col in FEATURE_CANDIDATES}
            row["label"] = label
            row["attack_cat"] = fam
            rows.append(row)
    return pd.DataFrame(rows)


def test_unsw_metadata_retains_family() -> None:
    out = unsw_features(_unsw_frame(), include_metadata=True)
    assert "family" in out.columns
    assert "is_attack" in out.columns
    assert (out.loc[out["label"] == 0, "family"] == "Benign").all()
    expected = set(UNSW_FAMILIES) | {"Benign"}
    assert set(out["family"].unique()) == expected
    assert (out.loc[out["label"] == 1].groupby("family").size() == 3).all()


def test_unsw_default_path_is_numeric_only() -> None:
    out = unsw_features(_unsw_frame(), include_metadata=False)
    assert "family" not in out.columns
    assert "is_attack" not in out.columns
    assert all(col in out.columns for col in FEATURE_CANDIDATES + ["label"])


def test_unsw_metadata_requires_attack_cat_column() -> None:
    frame = _unsw_frame().drop(columns=["attack_cat"])
    try:
        unsw_features(frame, include_metadata=True)
    except ValueError as exc:
        assert "attack_cat" in str(exc)
    else:
        raise AssertionError("expected ValueError when attack_cat is missing")


def _cic_frame() -> pd.DataFrame:
    cols = ["Flow Duration", "Total Fwd Packets", "Flow Bytes/s", "Dst Port"]
    rows = []
    labels = ["BENIGN", "DDoS", "PortScan", "BENIGN", "FTP-Patator",
              "Web Attack - Brute Force"]
    for i, lab in enumerate(labels):
        row = {c: float(i + 1) for c in cols}
        row["Label"] = lab
        rows.append(row)
    return pd.DataFrame(rows)


def test_cic_features_binarizes_and_reads_label_column() -> None:
    frame = _cic_frame()
    label = find_label_column(frame)
    assert label == "Label"
    out = cic_features(frame, label)
    # Repeated header rows are removed and the numeric columns survive.
    assert "Label" in out.columns
    assert set(out["Label"].unique()) <= {0, 1}
    assert (out["Label"] == 1).sum() >= 4


def test_cic_metadata_retains_day_and_label_name() -> None:
    frame = _cic_frame()
    frame["day"] = "Wednesday"
    label = find_label_column(frame)
    out = cic_features(frame, label, include_metadata=True)
    assert "day" in out.columns
    assert "label_name" in out.columns
    assert (out["day"] == "Wednesday").all()
    assert "DDoS" in set(out["label_name"].unique())
    assert (out["Label"] == 1).sum() == (out["label_name"] != "BENIGN").sum()


def test_cic_day_from_name_extracts_weekday() -> None:
    assert _day_from_name("Wednesday-workingHours.pcap_ISCX.csv") == "Wednesday"
    assert _day_from_name("Thursday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv") == "Thursday"
    assert _day_from_name("Friday-WorkingHours-Morning.pcap_ISCX.csv") == "Friday"
