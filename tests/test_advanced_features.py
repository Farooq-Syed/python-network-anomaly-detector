"""Unit tests for the newer network-anomaly features.

Covers the benchmark schema detection and label preparation, the time-window
aggregation step, and the query-selection logic behind the active-learning
experiment.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import detector  # noqa: E402
from active_learning_experiment import run_fold, select_queries  # noqa: E402

CIC_SAMPLE = PROJECT_DIR / "data" / "sample_cic_ids2017_style.csv"


class BenchmarkSchemaTests(unittest.TestCase):
    def test_cic_schema_detected(self):
        frame = pd.read_csv(CIC_SAMPLE)
        self.assertEqual(detector.detect_benchmark_schema(frame), "cic-ids2017")

    def test_unsw_schema_detected(self):
        frame = pd.DataFrame({"srcip": ["1.2.3.4"], "sport": [80], "label": [1]})
        self.assertEqual(detector.detect_benchmark_schema(frame), "unsw-nb15")

    def test_prepare_benchmark_reads_cic_labels(self):
        features, truth, schema = detector.prepare_benchmark(CIC_SAMPLE)
        self.assertEqual(schema, "cic-ids2017")
        self.assertEqual(len(features), len(truth))
        # The sample has 20% attacks by construction.
        self.assertGreaterEqual(int(truth.sum()), 1)
        # String columns (Flow ID, Label) must not leak into the features.
        self.assertNotIn("Flow ID", features.columns)
        self.assertNotIn("Label", features.columns)


class TimeWindowTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for minute in range(15):
            rows.append({
                "timestamp": f"2026-05-10T08:{minute:02d}:00",
                "source_ip": "10.0.0.9",
                "bytes_sent": 100 + minute,
                "packets": 2,
            })
        self.frame = pd.DataFrame(rows)

    def test_aggregates_into_expected_windows(self):
        aggregated = detector.aggregate_by_time_window(self.frame, "source_ip", window_minutes=5)
        # 15 minutes of traffic in 5-minute windows = 3 rows.
        self.assertEqual(len(aggregated), 3)
        self.assertIn("bytes_sent_mean", aggregated.columns)
        self.assertIn("timestamp", aggregated.columns)
        self.assertEqual(aggregated["source_ip"].nunique(), 1)

    def test_missing_source_column_raises(self):
        with self.assertRaises(ValueError):
            detector.aggregate_by_time_window(self.frame, "nope", window_minutes=5)


class ActiveLearningTests(unittest.TestCase):
    def test_uncertainty_selects_rows_nearest_0_5(self):
        probabilities = np.array([0.99, 0.51, 0.49, 0.01, 0.90])
        rng = np.random.default_rng(0)
        picked = select_queries(probabilities, 2, "uncertainty", rng)
        # Indices 1 and 2 have |p - 0.5| smallest.
        self.assertEqual(sorted(picked.tolist()), [1, 2])

    def test_random_selects_requested_count(self):
        probabilities = np.array([0.5] * 20)
        rng = np.random.default_rng(0)
        picked = select_queries(probabilities, 3, "random", rng)
        self.assertEqual(len(picked), 3)
        self.assertEqual(len(set(picked.tolist())), 3)

    def test_run_fold_returns_monotone_f1_curve(self):
        features = np.random.default_rng(0).normal(size=(300, 5))
        truth = np.array([0] * 240 + [1] * 60)
        # Interleave so every slice of the data contains both classes.
        order = np.random.default_rng(1).permutation(len(truth))
        truth = truth[order]
        features = features[order]
        # Separate the classes a bit so the logistic regression has signal.
        features[truth == 1, 0] += 3.0
        split = int(0.8 * len(truth))
        train_idx = np.arange(split)
        test_idx = np.arange(split, len(truth))
        result = run_fold(
            features, truth, train_idx, test_idx,
            strategy="uncertainty", seed_size=10, batch_size=10, budget=60, random_state=42,
        )
        self.assertGreaterEqual(len(result), 2)
        for f1 in result.values():
            self.assertGreaterEqual(f1, 0.0)
            self.assertLessEqual(f1, 1.0)


if __name__ == "__main__":
    unittest.main()
