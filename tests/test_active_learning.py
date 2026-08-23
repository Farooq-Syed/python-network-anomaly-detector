"""Tests for the active-learning query strategies.

Also exercises the reproducibility guard: on a fully separable problem with a
deterministic seed, the run must produce deterministic F1 values across two
successive runs.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import active_learning_experiment as ale  # noqa: E402

STRATEGIES = ["random", "uncertainty", "diversity", "committee"]


def separable(n_per_class=150, seed=0):
    rng = np.random.default_rng(seed)
    benign = rng.normal(0.0, 1.0, size=(n_per_class, 4))
    attack = rng.normal(5.0, 1.0, size=(n_per_class, 4))
    features = np.vstack([benign, attack])
    truth = np.array([0] * n_per_class + [1] * n_per_class)
    return features, truth


class QueryStrategyTests(unittest.TestCase):
    def test_uncertainty_takes_most_ambiguous(self):
        probs = np.array([0.5, 0.9, 0.05, 0.6, 0.45])
        idx = ale.select_queries(probs, 2, "uncertainty", np.random.default_rng(0))
        self.assertTrue(set(idx) == {0, 4})

    def test_uncertainty_takes_most_ambiguous(self):
        probs = np.array([0.5, 0.9, 0.05, 0.6, 0.45])
        idx = ale.select_queries(probs, 2, "uncertainty", np.random.default_rng(0))
        self.assertTrue(set(idx) == {0, 4})

    def test_posterior_uncertainty_ranks_margin_and_entropy_identically(self):
        # For a binary posterior, uncertainty (closest to 0.5), margin (smallest
        # |p1-p0|) and entropy (highest) rank rows identically. Test this directly.
        probs = np.array([0.5, 0.9, 0.05, 0.6, 0.45])
        rng = np.random.default_rng(0)
        unc = ale.select_queries(probs, 2, "uncertainty", np.random.default_rng(0))
        margin = np.argsort(np.abs(probs - (1 - probs)))[:2]
        entropy = np.argsort(-ale._entropy(probs))[:2]
        self.assertEqual(set(unc), set(margin))
        self.assertEqual(set(unc), set(entropy))

    def test_diversity_requires_features(self):
        with self.assertRaises(ValueError):
            ale.select_queries(np.array([0.5, 0.5]), 1, "diversity", np.random.default_rng(0), None)

    def test_diversity_returns_requested_count(self):
        X, _ = separable(60)
        probs = np.full(len(X), 0.5)
        idx = ale.select_queries(probs, 5, "diversity", np.random.default_rng(0), X)
        self.assertEqual(len(idx), 5)
        self.assertEqual(len(set(idx)), 5)

    def test_committee_returns_requested_count(self):
        X, y = separable(80)
        probs = np.full(len(X), 0.5)
        labeled = (X[:20], y[:20])
        idx = ale.select_queries(probs, 5, "committee", np.random.default_rng(0), X, labeled)
        self.assertEqual(len(idx), 5)
        self.assertEqual(len(set(idx)), 5)

    def test_vote_entropy_ranks_confident_split_highest(self):
        # The defining QBC property: a committee evenly split between confident attack
        # and confident benign predictions must score MAXIMUM disagreement. This is the
        # case the old mean-|p-0.5| metric got wrong (it reported such rows as certain).
        votes = np.array([
            [1, 1, 0],   # confident attack on rows 0,1; confident benign on row 2
            [0, 0, 0],   # confident benign everywhere
            [1, 0, 0],   # row 0: attack; rows 1,2 benign
            [0, 1, 0],   # row 1: attack; rows 0,2 benign
            [1, 1, 0],
            [0, 0, 1],   # row 2: attack; rows 0,1 benign
            [1, 0, 0],
            [0, 1, 0],
            [1, 1, 0],
            [0, 0, 0],
        ])
        ent = ale._vote_entropy(votes)
        # Row 0: 5 attack / 5 benign -> p=0.5 -> max entropy (=1.0).
        self.assertAlmostEqual(float(ent[0]), 1.0, delta=0.05)
        # Row 2: 2 attack / 8 benign -> p=0.2 -> lower entropy than row 0.
        self.assertLess(ent[2], ent[0])
        # Row 0 must out-rank the confident-unanimous rows.
        self.assertEqual(int(np.argmax(ent)), 0)

    def test_vote_entropy_unanimous_committee_is_zero(self):
        votes = np.zeros((10, 4), dtype=int)  # every member votes benign everywhere
        ent = ale._vote_entropy(votes)
        self.assertTrue(np.allclose(ent, 0.0, atol=0.05))

    def test_committee_requires_labeled_pool(self):
        with self.assertRaises(ValueError):
            ale.select_queries(np.array([0.5, 0.5]), 1, "committee", np.random.default_rng(0), None, None)

    def test_random_returns_requested_count(self):
        probs = np.full(100, 0.5)
        idx = ale.select_queries(probs, 7, "random", np.random.default_rng(0))
        self.assertEqual(len(idx), 7)
        self.assertEqual(len(set(idx)), 7)

    def test_entropy_of_certain_points_is_near_zero(self):
        # Binary entropy peaks at log(2) ~ 0.693 for p=0.5 and is ~0 for p near 0/1.
        self.assertAlmostEqual(float(ale._entropy(np.array([0.999]))[0]), 0.0, delta=0.01)
        self.assertAlmostEqual(float(ale._entropy(np.array([0.5]))[0]), 0.693, delta=0.05)


class ReproducibilityTests(unittest.TestCase):
    def test_run_is_deterministic_for_same_seed(self):
        X, y = separable()
        opts = dict(folds=3, seed_size=4, batch_size=4, budget=24, random_state=7)
        first = ale.run(X, y, strategies=["random", "uncertainty"], **opts)
        second = ale.run(X, y, strategies=["random", "uncertainty"], **opts)
        for strategy in ("random", "uncertainty"):
            for count in first[strategy]:
                self.assertEqual(
                    first[strategy][count]["f1_mean"],
                    second[strategy][count]["f1_mean"],
                )


if __name__ == "__main__":
    unittest.main()
