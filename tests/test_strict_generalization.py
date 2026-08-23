"""Tests for strict_generalization.py (family/day hold-out evaluation)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import strict_generalization as sg  # noqa: E402


def _frame(n_per=40):
    rng = np.random.default_rng(0)
    rows = []
    families = ["Fuzzers", "Worms", "DoS"]
    for fam in families:
        for _ in range(n_per):
            rows.append({"f1": rng.normal(2.0, 1.0), "f2": rng.normal(2.0, 1.0),
                         "family": fam, "label": 1})
    for _ in range(n_per):
        rows.append({"f1": rng.normal(0.0, 1.0), "f2": rng.normal(0.0, 1.0),
                     "family": "Benign", "label": 0})
    return pd.DataFrame(rows)


def _frame_by_day(n_per=40):
    rng = np.random.default_rng(0)
    rows = []
    for day in ["Monday", "Tuesday", "Wednesday"]:
        for _ in range(n_per):
            rows.append({"f1": rng.normal(2.0, 1.0), "f2": rng.normal(2.0, 1.0),
                         "day": day, "label": 1})
        for _ in range(n_per):
            rows.append({"f1": rng.normal(0.0, 1.0), "f2": rng.normal(0.0, 1.0),
                         "day": day, "label": 0})
    return pd.DataFrame(rows)


class SplitBenignTests(unittest.TestCase):
    def test_split_benign_partitions_without_overlap(self):
        idx = np.arange(0, 50, 2)  # sparse but ascending
        heldout, train = sg._split_benign(idx)
        self.assertEqual(len(set(heldout) & set(train)), 0)
        self.assertEqual(sorted(set(heldout) | set(train)), sorted(set(idx.tolist())))
        self.assertGreater(len(heldout), 0)
        self.assertGreater(len(train), 0)

    def test_split_benign_respects_frac(self):
        idx = np.arange(1000)
        heldout, train = sg._split_benign(idx)
        self.assertAlmostEqual(len(heldout) / len(idx), 0.2, delta=0.02)


class FamilyHoldoutTests(unittest.TestCase):
    def test_held_out_family_is_fully_unseen_in_train(self):
        frame = _frame()
        labels = frame["family"]
        truth = frame["label"].to_numpy()
        feats = frame[["f1", "f2"]]
        res = sg.evaluate_family_pool(feats, truth, labels, "Worms")
        self.assertEqual(res["test_attacks"], 40)
        self.assertIn("roc_auc", res)
        self.assertIn("f1", res)
        # 0 <= F1 <= 1 whenever the pool is non-degenerate.
        self.assertGreaterEqual(res["f1"], 0.0)
        self.assertLessEqual(res["f1"], 1.0)


class DayHoldoutTests(unittest.TestCase):
    def test_day_holdout_holds_out_entire_day_including_benign(self):
        frame = _frame_by_day()
        labels = frame["day"]
        truth = frame["label"].to_numpy()
        feats = frame[["f1", "f2"]]
        res = sg.evaluate_day_pool(feats, truth, labels, "Wednesday")
        # Every Wednesday row is test-only: 40 attacks AND 40 benign.
        self.assertEqual(res["test_attacks"], 40)
        self.assertEqual(res["test_benign"], 40)
        # None of the held-out day rows are in training:
        # train count == Monday + Tuesday rows.
        self.assertEqual(res["n_train"], 160)
        self.assertIn("unsupervised_f1_heldout", res)

    def test_day_holdout_has_no_day_leakage(self):
        # A true temporal hold-out never uses held-out-day rows in training.
        frame = _frame_by_day()
        labels = frame["day"]
        truth = frame["label"].to_numpy()
        feats = frame[["f1", "f2"]]
        is_held = (labels == "Wednesday").to_numpy()
        res = sg.evaluate_day_pool(feats, truth, labels, "Wednesday")
        train_idx = np.where(~is_held)[0]
        self.assertEqual(res["n_train"], 160)
        self.assertEqual(len(train_idx), 160)

    def test_load_frame_requires_metadata_column(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
            _frame().to_csv(fh.name, index=False)
            path = Path(fh.name)
        try:
            with self.assertRaises(ValueError):
                sg.load_frame(path, "label", "missing_column")
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
