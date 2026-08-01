"""Tests for label_budget_experiment.py.

Uses a small separable synthetic dataset so the run is fast, and checks the
mechanics: the labeled-subset selector always includes both classes, and the
budget sweep returns the expected structure with F1 values that rise as the label
budget grows.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import label_budget_experiment as lbe  # noqa: E402


def separable(n_per_class=150, seed=0):
    rng = np.random.default_rng(seed)
    benign = rng.normal(0.0, 1.0, size=(n_per_class, 4))
    attack = rng.normal(5.0, 1.0, size=(n_per_class, 4))
    features = np.vstack([benign, attack])
    truth = np.array([0] * n_per_class + [1] * n_per_class)
    return features, truth


class LabeledSubsetTests(unittest.TestCase):
    def test_subset_contains_both_classes(self):
        _, y = separable()
        rng = np.random.default_rng(0)
        # Even a tiny fraction must yield a labeled subset with both classes.
        idx = lbe._labeled_subset(y, fraction=0.02, rng=rng)
        self.assertEqual(len(np.unique(y[idx])), 2)

    def test_minimum_of_four_labels(self):
        _, y = separable()
        idx = lbe._labeled_subset(y, fraction=0.0, rng=np.random.default_rng(0))
        self.assertGreaterEqual(len(idx), 4)


class BudgetSweepTests(unittest.TestCase):
    def test_run_returns_expected_keys(self):
        X, y = separable()
        results = lbe.run(X, y, budgets=[0.05, 0.5], folds=3, random_state=0)
        self.assertEqual(len(results), 2)
        for row in results:
            for key in ("labeled_fraction", "approx_labeled_rows",
                        "supervised_f1", "self_training_f1"):
                self.assertIn(key, row)

    def test_more_labels_do_not_hurt(self):
        # On a separable problem, more labels should give F1 at least as high
        # (allowing a small tolerance for CV noise).
        X, y = separable()
        results = lbe.run(X, y, budgets=[0.02, 0.5], folds=3, random_state=0)
        self.assertGreaterEqual(
            results[1]["supervised_f1"], results[0]["supervised_f1"] - 0.05
        )


if __name__ == "__main__":
    unittest.main()
