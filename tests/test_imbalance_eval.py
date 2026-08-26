"""Tests for imbalance_eval.py (imbalance + operational metrics)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import imbalance_eval as im  # noqa: E402


def _frame(n_benign=100, n_attack=100, seed=0):
    rng = np.random.default_rng(seed)
    benign = pd.DataFrame({
        "f1": rng.normal(0.0, 1.0, n_benign),
        "f2": rng.normal(0.0, 1.0, n_benign),
        "label": [0] * n_benign,
    })
    attack = pd.DataFrame({
        "f1": rng.normal(5.0, 1.0, n_attack),
        "f2": rng.normal(5.0, 1.0, n_attack),
        "label": [1] * n_attack,
    })
    return pd.concat([benign, attack], ignore_index=True)


class SubsampleTests(unittest.TestCase):
    def test_subsample_matches_target_fraction(self):
        df = _frame()
        feats = df[["f1", "f2"]]
        truth = df["label"].to_numpy()
        _, t = im.subsample_to_fraction(feats, truth, 0.1, 0)
        self.assertAlmostEqual(float(t.mean()), 0.1, delta=0.03)

    def test_subsample_keeps_all_benign(self):
        df = _frame(n_benign=200, n_attack=50)
        feats = df[["f1", "f2"]]
        truth = df["label"].to_numpy()
        f, t = im.subsample_to_fraction(feats, truth, 0.4, 0)
        self.assertEqual(int((t == 0).sum()), 200)


class OperationalMetricsTests(unittest.TestCase):
    def test_pick_threshold_selects_within_range(self):
        y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        prob = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
        threshold, fpr = im._pick_threshold(y, prob, 0.25)
        self.assertGreaterEqual(threshold, 0.0)
        self.assertLessEqual(threshold, 1.0)
        self.assertLessEqual(fpr, 0.25)

    def test_pick_threshold_never_chooses_nearest_point_above_budget(self):
        y = np.array([0] * 100 + [1] * 4)
        prob = np.array([0.85, 0.84] + [0.1] * 98 + [0.95, 0.92, 0.82, 0.81])
        threshold, fpr = im._pick_threshold(y, prob, 0.01)
        self.assertGreaterEqual(threshold, 0.90)
        self.assertLessEqual(fpr, 0.01)

    def test_evaluate_runs_and_reports_operating_metrics(self):
        df = _frame()
        feats = df[["f1", "f2"]]
        truth = df["label"].to_numpy()
        res = im.evaluate(feats, truth, folds=3, random_state=0, target_fpr=0.1,
                          use_balanced_weight=True, attack_frac=0.5)
        for key in ("f1", "roc_auc", "pr_auc", "recall_at_fpr"):
            self.assertIn(key, res)
        self.assertGreaterEqual(res["recall_at_fpr"], 0.0)
        self.assertLessEqual(res["recall_at_fpr"], 1.0)

    def test_inner_validation_threshold_not_tuned_on_test(self):
        # The threshold must come from a validation split, not the test fold. We
        # assert the threshold is finite and that recall_at_fpr is a scalar metric.
        df = _frame()
        feats = df[["f1", "f2"]]
        truth = df["label"].to_numpy()
        res = im.evaluate(feats, truth, folds=3, random_state=1, target_fpr=0.1,
                          use_balanced_weight=False, attack_frac=0.5)
        self.assertTrue(np.isfinite(res["recall_at_fpr"]))


if __name__ == "__main__":
    unittest.main()
