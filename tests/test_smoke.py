import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class NetworkAnomalyDetectorSmokeTests(unittest.TestCase):
    def test_labeled_sample_run_produces_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_csv = tmp_path / "anomaly_report.csv"
            summary_json = tmp_path / "summary.json"
            metrics_json = tmp_path / "metrics.json"
            plot_dir = tmp_path / "plots"

            # sys.executable rather than "python" so the subprocess uses the same
            # environment as the test runner.
            subprocess.run(
                [
                    sys.executable,
                    "detector.py",
                    "--input",
                    "data/labeled_research_sample.csv",
                    "--label-column",
                    "label",
                    "--output",
                    str(output_csv),
                    "--summary",
                    str(summary_json),
                    "--metrics-output",
                    str(metrics_json),
                    "--plot-dir",
                    str(plot_dir),
                ],
                cwd=PROJECT_DIR,
                check=True,
            )

            self.assertTrue(output_csv.exists())
            self.assertTrue(summary_json.exists())
            self.assertTrue(metrics_json.exists())
            self.assertTrue((plot_dir / "feature_scatter.png").exists())


if __name__ == "__main__":
    unittest.main()
