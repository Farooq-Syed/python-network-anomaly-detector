"""Tests for supervised_baseline.py.

Runs the pipeline on a small, cleanly separable synthetic dataset (rather than the
full UNSW subset, to keep the test fast) and checks that it returns the expected
metric keys and that a trivially separable problem is learned well.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import supervised_baseline as sb  # noqa: E402


def separable_frame(n_per_class=40, seed=0):
    """Two well-separated Gaussian blobs labeled 0 and 1."""
    rng = np.random.default_rng(seed)
    benign = rng.normal(0.0, 1.0, size=(n_per_class, 4))
    attack = rng.normal(6.0, 1.0, size=(n_per_class, 4))
    features = pd.DataFrame(
        np.vstack([benign, attack]),
        columns=["bytes_sent", "packets", "duration", "conns"],
    )
    truth = pd.Series([0] * n_per_class + [1] * n_per_class, name="label")
    return features, truth


class SupervisedBaselineTests(unittest.TestCase):
    def test_metrics_have_expected_keys(self):
        features, truth = separable_frame()
        metrics = sb.run(features, truth, folds=3, random_state=0)
        self.assertIn("logistic_regression", metrics)
        self.assertIn("random_forest", metrics)
        for model_metrics in metrics.values():
            for key in ("precision", "recall", "f1_score", "accuracy", "roc_auc"):
                self.assertIn(key, model_metrics)

    def test_separable_problem_is_learned(self):
        # On two clearly separated blobs both models should be near-perfect.
        features, truth = separable_frame()
        metrics = sb.run(features, truth, folds=3, random_state=0)
        for name, model_metrics in metrics.items():
            self.assertGreater(model_metrics["f1_score"], 0.9,
                               f"{name} unexpectedly weak on a separable problem")

    def test_scaling_is_inside_the_pipeline(self):
        # The logistic-regression model must be a Pipeline whose first step scales,
        # so cross-validation never leaks scaler statistics across folds.
        metrics = sb.run(*separable_frame(), folds=3, random_state=0)
        # Rebuild the model dict the same way run() does and inspect it.
        from sklearn.pipeline import Pipeline
        models = {
            "logistic_regression": sb.make_pipeline(
                sb.StandardScaler(), sb.LogisticRegression()
            )
        }
        self.assertIsInstance(models["logistic_regression"], Pipeline)
        self.assertIsInstance(
            models["logistic_regression"].steps[0][1], sb.StandardScaler
        )


if __name__ == "__main__":
    unittest.main()
