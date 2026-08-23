"""Tests for active_learning_stats.py (repeated-seed statistics)."""

import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import active_learning_stats as astats  # noqa: E402


def separable(n_per_class=120, seed=0):
    rng = np.random.default_rng(seed)
    benign = rng.normal(0.0, 1.0, size=(n_per_class, 4))
    attack = rng.normal(5.0, 1.0, size=(n_per_class, 4))
    features = np.vstack([benign, attack])
    truth = np.array([0] * n_per_class + [1] * n_per_class)
    return features, truth


class CIandPairedTests(unittest.TestCase):
    def test_ci_bounds_contain_mean(self):
        values = [0.9, 0.95, 0.88, 0.92, 0.96]
        mean, lo, hi, n = astats._ci(values)
        self.assertEqual(n, len(values))
        self.assertLessEqual(lo, mean)
        self.assertGreaterEqual(hi, mean)

    def test_paired_test_returns_expected_keys(self):
        random_f1 = [0.8, 0.81, 0.79, 0.80]
        alt_f1 = [0.70, 0.71, 0.69, 0.70]
        res = astats.paired_test(random_f1, alt_f1)
        for key in ("paired_diff_mean", "wilcoxon_p", "ttest_p", "n_pairs"):
            self.assertIn(key, res)

    def test_paired_test_detects_clear_difference(self):
        random_f1 = [0.9] * 6
        alt_f1 = [0.5] * 6
        res = astats.paired_test(random_f1, alt_f1)
        self.assertLess(res["wilcoxon_p"], 0.05)


class RepeatedRunTests(unittest.TestCase):
    def test_run_repeated_structure(self):
        X, y = separable()
        out = astats.run_repeated(X, y, folds=2, seed_size=4, batch_size=4,
                                  budget=12, seeds=[0, 1], strategies=["random", "uncertainty"])
        for strategy in ("random", "uncertainty"):
            self.assertIn(strategy, out)
            self.assertTrue(len(out[strategy]) > 0)


if __name__ == "__main__":
    unittest.main()
