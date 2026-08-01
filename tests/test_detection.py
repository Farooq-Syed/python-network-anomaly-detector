"""Unit tests for detector.py.

Focus areas: label normalization, the feature-selection leakage guard, the z-score
detector, and the ensemble voting rule. Model-based detectors are covered
end-to-end by the smoke test; here we test the deterministic pieces directly.
"""

import sys
import unittest
import warnings
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import detector  # noqa: E402


class NormalizeLabelTests(unittest.TestCase):
    def test_positive_and_negative_synonyms(self):
        for value in ["1", "true", "attack", "anomaly", "malicious", "yes"]:
            self.assertEqual(detector.normalize_label(value), 1)
        for value in ["0", "false", "benign", "normal", "no"]:
            self.assertEqual(detector.normalize_label(value), 0)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            detector.normalize_label("unsure")


class FeatureSelectionTests(unittest.TestCase):
    def test_named_label_excluded(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "label": [0, 1]})
        cols = detector.select_numeric_columns(df, "label")
        self.assertNotIn("label", cols)
        self.assertEqual(set(cols), {"a", "b"})

    def test_unnamed_label_still_excluded_with_warning(self):
        # The key regression: a numeric label column left in as a feature would
        # hand the unsupervised detectors the ground truth. Even without
        # --label-column it must be dropped.
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "label": [0, 1]})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cols = detector.select_numeric_columns(df, None)
        self.assertNotIn("label", cols)
        self.assertTrue(any("leakage" in str(w.message).lower() for w in caught))

    def test_non_label_columns_are_kept(self):
        df = pd.DataFrame({"bytes_sent": [1, 2], "packets": [3, 4]})
        cols = detector.select_numeric_columns(df, None)
        self.assertEqual(set(cols), {"bytes_sent", "packets"})

    def test_no_numeric_columns_raises(self):
        df = pd.DataFrame({"proto": ["tcp", "udp"], "label": [0, 1]})
        with self.assertRaises(ValueError):
            detector.select_numeric_columns(df, "label")


class ZScoreTests(unittest.TestCase):
    def test_outlier_against_tight_cluster_is_flagged(self):
        # A tight cluster of normal rows plus one clear outlier. Here the outlier
        # is large enough relative to the spread that its own z-score clears the
        # threshold, so it is flagged.
        df = pd.DataFrame({"packets": [10, 11, 9, 10, 12, 10, 9, 11, 10, 60]})
        result = detector.compute_z_score_method(df, ["packets"], threshold=2.5)
        self.assertEqual(int(result["z_score_flag"].iloc[-1]), 1)
        self.assertEqual(int(result["z_score_flag"].iloc[0]), 0)

    def test_single_extreme_value_masks_itself(self):
        # Documents a real limitation of the z-score method rather than a bug: a
        # lone, very large value inflates the standard deviation so much that its
        # own z-score falls below the threshold. With [10,11,9,10,500] the 500 has
        # z=2.0, under the 2.5 threshold, so it is NOT flagged. This is why the
        # ensemble pairs z-score with density/isolation methods that do not share
        # this failure mode.
        df = pd.DataFrame({"packets": [10, 11, 9, 10, 500]})
        result = detector.compute_z_score_method(df, ["packets"], threshold=2.5)
        self.assertEqual(int(result["z_score_flag"].iloc[-1]), 0)

    def test_constant_column_never_flags(self):
        # Zero standard deviation must not divide-by-zero or flag anything.
        df = pd.DataFrame({"packets": [5, 5, 5, 5]})
        result = detector.compute_z_score_method(df, ["packets"], threshold=2.5)
        self.assertEqual(int(result["z_score_flag"].sum()), 0)


class EnsembleTests(unittest.TestCase):
    def test_two_votes_required(self):
        df = pd.DataFrame(
            {
                "bytes_sent": [1, 2, 3, 4, 500],
                "packets": [1, 2, 3, 4, 500],
            }
        )
        cols = detector.select_numeric_columns(df, None)
        report = detector.build_report(
            df, cols, label_column=None, z_threshold=2.0,
            contamination=0.2, random_state=42,
        )
        expected = (report["ensemble_votes"] >= 2).astype(int)
        self.assertTrue((report["is_anomaly"] == expected).all())


if __name__ == "__main__":
    unittest.main()
