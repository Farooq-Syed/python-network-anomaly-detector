"""Tests for cross_dataset.py (cross-dataset generalization)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import cross_dataset as cd  # noqa: E402


def _shared_frame(n=80, seed=0, value_bias=0.0):
    rng = np.random.default_rng(seed)
    benign = pd.DataFrame({"Flow Duration": rng.normal(0, 1, n),
                           "Total Fwd Packets": rng.normal(0, 1, n),
                           "label": [0] * n})
    attack = pd.DataFrame({"Flow Duration": rng.normal(5 + value_bias, 1, n),
                           "Total Fwd Packets": rng.normal(5 + value_bias, 1, n),
                           "label": [1] * n})
    return pd.concat([benign, attack], ignore_index=True)


class LoadFrameTests(unittest.TestCase):
    def test_load_frame_parses_numeric_and_label(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
            _shared_frame().to_csv(fh.name, index=False)
            path = Path(fh.name)
        try:
            feats, truth = cd.load_frame(path, "label")
            self.assertEqual(set(feats.columns), {"Flow Duration", "Total Fwd Packets"})
            self.assertEqual(len(feats), len(truth))
            self.assertEqual(len(truth), 160)
        finally:
            path.unlink()


class SchemaDetectionTests(unittest.TestCase):
    def test_shared_features_identical_schema(self):
        x1 = _shared_frame()[["Flow Duration", "Total Fwd Packets"]]
        x2 = _shared_frame(value_bias=1.0)[["Flow Duration", "Total Fwd Packets"]]
        shared = [c for c in x1.columns if c in x2.columns]
        self.assertEqual(len(shared), 2)

    def test_shared_features_none_when_disjoint(self):
        x1 = pd.DataFrame({"a": [1.0], "b": [2.0]})
        x2 = pd.DataFrame({"c": [1.0], "d": [2.0]})
        shared = [c for c in x1.columns if c in x2.columns]
        self.assertEqual(len(shared), 0)


if __name__ == "__main__":
    unittest.main()
