# Python-Based Network Anomaly Detector

[![CI](https://github.com/Farooq-Syed/python-network-anomaly-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/Farooq-Syed/python-network-anomaly-detector/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-non--commercial-purple)

This project explores anomaly detection for network traffic using a mix of statistical and unsupervised machine learning methods. It was built around flow-level features such as packet counts, byte volume, duration, timing, and connection statistics.

Developed with AI coding assistance; the author chose the benchmarks, designed the
comparisons, reviewed and revised the code, interpreted the results, and verified the
final claims.

## Results at a glance

![Results panel](assets/results_panel.png)

Four detectors vote on each flow. Evaluated on a 6,000-row UNSW-NB15 subset, no method
exceeds F1 = 0.30, and the same broad result holds on newer benchmark checks
(`CIC-IDS2017` and `CSE-CIC-IDS2018`). That is the honest, unglamorous reality of
unsupervised detection on mixed traffic, and more credible than a toy that scores
perfectly. See [PAPER.md](PAPER.md) for the method, [JOURNAL.md](JOURNAL.md) for the
development notes, and [REFERENCES.md](REFERENCES.md) for the benchmark and method
citations.

The pipeline compares four detectors:

- `Z-score`
- `Isolation Forest`
- `Local Outlier Factor`
- `One-Class SVM`

## Public-benchmark validation and provenance

The three tracked benchmark subsets now have fresh comparison artifacts under
`results/external_validation_*.json`. Each artifact records the exact input SHA-256,
canonical dataset landing page, random state, fold count, row count, and run timestamp.
The rerun reproduced the central result:

| Public benchmark subset | Rows | Unsupervised F1 | Supervised F1 | F1 gap |
| --- | ---: | ---: | ---: | ---: |
| UNSW-NB15 | 6,000 | 0.270 | 0.996 | +0.726 |
| CIC-IDS2017 | 12,000 | 0.264 | 0.966 | +0.703 |
| CSE-CIC-IDS2018 | 12,000 | 0.183 | 0.924 | +0.741 |

These are prepared public benchmark subsets, not live enterprise traffic. The
provenance record improves reproducibility but does not remove benchmark-age,
subset-selection, or deployment-validity limitations.

**Results re-verified** on 2026-08-23 by re-running `benchmark_compare.py` on each
bundled public subset; the figures below reproduce exactly (UNSW-NB15: 0.270 / 0.996;
CIC-IDS2017: 0.264 / 0.966; CSE-CIC-IDS2018: 0.183 / 0.924). Run the three
reproductions with:

```powershell
python benchmark_compare.py --input data/unsw_nb15_public_subset.csv --label-column label
python benchmark_compare.py --input data/cic_ids2017_subset.csv --label-column Label
python benchmark_compare.py --input data/cse_cic_ids2018_subset.csv --label-column Label
```

The final anomaly decision is made with a simple ensemble rule: a row is flagged when at least two methods identify it as anomalous.

## Features

- CSV-based workflow for traffic or flow records
- automatic numeric feature selection with a label-leakage guard
- comparison across multiple anomaly detection methods
- optional evaluation with labeled data
- exported reports, metrics, and plots
- reproducible UNSW-NB15 subset preparation
- schema-aware loader for CIC-IDS2017-style data
- optional per-source time-window aggregation (`--window-minutes`)
- supervised baseline, label-budget, and active-learning experiments
- calibration analysis + recalibration experiment (explains the active-learning sign flip) —
  `calibration_analysis.py`, `recalibration_experiment.py`; see `CALIBRATION_FINDING.md`
- benchmark-preparation utilities for `UNSW-NB15`, `CIC-IDS2017`, and compatible
  `CICFlowMeter` exports such as `CSE-CIC-IDS2018`

## Project Structure

```text
.
|-- .gitignore
|-- detector.py
|-- prepare_unsw_nb15.py
|-- requirements.txt
|-- LICENSE
|-- data/
|   |-- sample_network_traffic.csv
|   |-- labeled_research_sample.csv
|   `-- unsw_nb15_public_subset.csv
|-- assets/
|   |-- ensemble_confusion_matrix_sample.png
|   |-- feature_scatter_sample.png
|   |-- method_comparison_sample.png
|   |-- unsw_ensemble_confusion_matrix.png
|   |-- unsw_f1_comparison.png
|   |-- unsw_feature_scatter.png
|   `-- unsw_method_comparison.png
|-- notebooks/
|   `-- network_anomaly_analysis.ipynb
|-- results/
|   |-- unsw_nb15_subset_metrics.json
|   |-- unsw_nb15_subset_summary.json
|   |-- supervised_metrics.json
|   |-- label_budget_metrics.json
|   |-- active_learning_metrics.json
|   |-- unsw_benchmark_comparison.json
|   |-- cic_benchmark_comparison.json
|   `-- cic_active_learning_metrics.json
`-- docs/
    `-- real_dataset_guide.md
```

## Installation

```powershell
python -m pip install -r requirements.txt
```

Optional, only if you want to pull the public Hugging Face mirrors of `UNSW-NB15` or
`CIC-IDS2017` directly:

```powershell
python -m pip install datasets pyarrow
```

## Usage

Run the basic sample:

```powershell
python detector.py
```

Run the labeled sample with evaluation:

```powershell
python detector.py --input data/labeled_research_sample.csv --label-column label
```

Run the supervised baseline to see how much the labels are worth (this is the
`supervised_vs_unsupervised` comparison used in the paper):

```powershell
python supervised_baseline.py --input data/unsw_nb15_public_subset.csv --label-column label
```

Run the label-budget experiment (how few labels are needed, and whether
self-training over the unlabeled remainder helps):

```powershell
python label_budget_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
```

Run the active-learning experiment (does choosing *which* rows to label beat random
labeling under a fixed budget?):

```powershell
python active_learning_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
```

**Why does the query-strategy sign flip between benchmarks?** The active-learning result is
inconsistent — uncertainty sampling edges random on UNSW-NB15 but loses on CIC-IDS2017.
A calibration analysis (`calibration_analysis.py`) gives a quantitative, reproducible
answer: UNSW-NB15 is near-perfectly calibrated with essentially **no** rows in the
ambiguity band the strategy targets (so it degenerates to a plateau), while CIC-IDS2017 is
miscalibrated and the rows the strategy picks are **wrong ~45% of the time** — uncertainty
sampling buys label noise, so random wins. See
[CALIBRATION_FINDING.md](CALIBRATION_FINDING.md).

Compare unsupervised vs. supervised detection on the CIC-IDS2017 benchmark (a real
12,000-row subset, prepared from the `bvsam/cic-ids-2017` mirror, ships in `data/`;
a tiny synthetic CIC-style sample exercises the schema path too):

```powershell
python benchmark_compare.py --input data/cic_ids2017_subset.csv --label-column Label
python benchmark_compare.py --input data/sample_cic_ids2017_style.csv
```

Run the active-learning comparison on CIC-IDS2017 (the harder benchmark, where the
query-strategy result flips), passing the measured supervised reference:

```powershell
python active_learning_experiment.py --input data/cic_ids2017_subset.csv --label-column Label --supervised-reference 0.966
```

Prepare and compare a newer `CSE-CIC-IDS2018` subset from compatible CICFlowMeter CSVs:

```powershell
python prepare_cic_ids2017.py --files "C:\path\to\Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv" `
                              "C:\path\to\Thursday-01-03-2018_TrafficForML_CICFlowMeter.csv" `
                              "C:\path\to\Friday-02-03-2018_TrafficForML_CICFlowMeter.csv" `
                              --output data/cse_cic_ids2018_subset.csv --rows-per-class 6000
python benchmark_compare.py --input data/cse_cic_ids2018_subset.csv --label-column Label
```

Prepare a CIC-IDS2017 subset from the Hugging Face mirror or from local files:

```powershell
python prepare_cic_ids2017.py --rows-per-class 6000 --output data/cic_ids2017_subset.csv
python prepare_cic_ids2017.py --files "C:\data\Wednesday-workingHours.pcap_ISCX.csv"
```

Aggregate flows into per-source time windows before detection:

```powershell
python detector.py --input data/sample_network_traffic.csv --window-minutes 30
```

Prepare a subset from official `UNSW-NB15` train and test CSV files:

```powershell
python prepare_unsw_nb15.py --train "C:\path\to\UNSW_NB15_training-set.csv" --test "C:\path\to\UNSW_NB15_testing-set.csv"
python detector.py --input data/unsw_nb15_portfolio_subset.csv --label-column label
```

Prepare a subset from a public Hugging Face mirror of the dataset:

```powershell
python prepare_unsw_nb15.py --hf-dataset Mouwiya/UNSW-NB15 --output data/unsw_nb15_public_subset.csv --rows-per-class 3000
python detector.py --input data/unsw_nb15_public_subset.csv --label-column label
```

## Output

The detector writes its results to `output/`:

- `anomaly_report.csv`
- `summary.json`
- `metrics.json` when a label column is provided
- plots such as feature scatter, method comparison charts, F1 comparison, and an ensemble confusion matrix

## Methods

### Z-score

Provides a simple statistical baseline by flagging rows with unusually large deviations in one or more numeric fields.

### Isolation Forest

Detects anomalies by isolating observations that are easier to separate from the rest of the dataset.

### Local Outlier Factor

Measures how isolated a row is relative to the density of its local neighborhood.
The implementation now includes a duplicate-aware retry path for benchmark-style
data, because public flow datasets often contain repeated rows that make naive LOF
neighborhoods unstable.

### One-Class SVM

Learns a boundary around normal-looking traffic and flags rows that fall outside it.

### Ensemble

Uses a majority-style vote across the four methods to reduce dependence on any single detector.

## Sample Results

On the included labeled research sample (`24` rows, `4` attack rows), the ensemble flagged all four malicious rows.

| Method | Precision | Recall | F1-score | Accuracy |
| --- | --- | --- | --- | --- |
| Z-score | 1.00 | 1.00 | 1.00 | 1.00 |
| Isolation Forest | 1.00 | 0.75 | 0.86 | 0.96 |
| Local Outlier Factor | 1.00 | 0.75 | 0.86 | 0.96 |
| One-Class SVM | 1.00 | 0.50 | 0.67 | 0.92 |
| Ensemble | 1.00 | 1.00 | 1.00 | 1.00 |

These numbers are mainly useful for validating the pipeline on a small labeled example.

## UNSW-NB15 Subset Results

The repository also includes a tracked subset, `data/unsw_nb15_public_subset.csv`, derived from the public `UNSW-NB15` dataset with `3000` benign and `3000` attack rows. This subset was used to test the pipeline on a more realistic benchmark.

Metrics from `results/unsw_nb15_subset_metrics.json`:

| Method | Precision | Recall | F1-score | Accuracy |
| --- | --- | --- | --- | --- |
| Z-score | 0.4712 | 0.2157 | 0.2959 | 0.4868 |
| Isolation Forest | 0.6375 | 0.1530 | 0.2468 | 0.5330 |
| Local Outlier Factor | 0.7097 | 0.1703 | 0.2747 | 0.5503 |
| One-Class SVM | 0.5153 | 0.1237 | 0.1995 | 0.5037 |
| Ensemble | 0.5796 | 0.1760 | 0.2700 | 0.5242 |

These results are much less “perfect” than the toy sample, which is what I would expect from a real intrusion detection benchmark. They show the difficulty of anomaly detection on mixed traffic and make the project more credible than a toy-only example.

## Cross-benchmark check

The current repository also includes a broader benchmark story beyond UNSW-NB15:

| Benchmark | Unsupervised ensemble F1 | Supervised F1 |
| --- | --- | --- |
| `UNSW-NB15` subset | 0.270 | 0.996 |
| `CIC-IDS2017` subset | 0.272 | 0.966 |
| `CSE-CIC-IDS2018` subset | 0.178 | 0.924 |

The main conclusion survives the newer benchmark: labels matter a lot, and the
unsupervised ensemble gets weaker rather than stronger on the harder 2018 data.

## Visuals

Sample labeled dataset visuals:

![Feature scatter sample](assets/feature_scatter_sample.png)

![Method comparison sample](assets/method_comparison_sample.png)

![Sample confusion matrix](assets/ensemble_confusion_matrix_sample.png)

UNSW-NB15 subset visuals:

![UNSW feature scatter](assets/unsw_feature_scatter.png)

![UNSW method comparison](assets/unsw_method_comparison.png)

![UNSW confusion matrix](assets/unsw_ensemble_confusion_matrix.png)

## Notebook

The repository includes `notebooks/network_anomaly_analysis.ipynb` for a lightweight exploratory analysis workflow. It can be extended later for larger public benchmark datasets.

## Real Dataset Notes

The repository includes `docs/real_dataset_guide.md` and `prepare_unsw_nb15.py` to convert the official `UNSW-NB15` train and test CSV files, or a public mirror of the dataset, into a smaller subset for experimentation.

Official dataset pages:

- [UNSW-NB15](https://research.unsw.edu.au/projects/unsw-nb15-dataset)
- [CIC-IDS2017](https://www.unb.ca/cic/datasets/ids-2017.html)
- [CSE-CIC-IDS2018](https://www.unb.ca/cic/datasets/ids-2018.html)

## Authorship and AI use

- The project ideas, benchmark choices, evaluation protocol, error analysis, and final
  interpretations are the author's.
- AI assistance was used for coding support and drafting help.
- The author reviewed, edited, tested, and verified the final code and claims.

## Suggested citation

If you want a compact scholarly grounding for this repo, start with
[REFERENCES.md](REFERENCES.md). The most directly relevant citations are:

- Moustafa and Slay (2015) for `UNSW-NB15`
- Sharafaldin, Lashkari, and Ghorbani (2018) for `CIC-IDS2017`
- the official `CSE-CIC-IDS2018` dataset page for the newer benchmark
- Liu, Ting, and Zhou (2008), Breunig et al. (2000), and Schölkopf et al. (2001) for
  the core anomaly-detection methods used here

## Limitations

- the included UNSW and CIC subsets are intentionally smaller than the full benchmarks
- results are sensitive to feature selection and model parameters
- unsupervised methods can still produce false positives on borderline traffic patterns
- the current ensemble uses a simple vote rather than tuned model calibration
- the CIC subset is a balanced sample of four days' traffic, which underrepresents
  long-tail attack families
- the `CSE-CIC-IDS2018` subset currently uses three attack-bearing CICFlowMeter days,
  which is enough for a meaningful comparison but not a full replay of the entire
  10-day benchmark
- the metadata-retaining subsets used for the strict family/day splits are 12,000-row
  balanced samples; several UNSW families and two CIC days are small, so their held-out
  F1 estimates carry wide confidence intervals
- the balanced, random-cross-validation numbers are optimistic for in-distribution
  evaluation; they do not survive strict family/day splits (UNSW generalizes, CIC
  collapses) or cross-dataset transfer (CIC-IDS2017 → CSE-CIC-IDS2018 is near-random) —
  see [RESULTS_STRICT_EVALUATION.md](RESULTS_STRICT_EVALUATION.md)
- the day hold-out skips Monday (its sampled subset has no attacks) and the low-attack
  days (Tuesday 152, Thursday 35) yield very low F1; count these as small-sample estimates

## Next Steps

- ~~compare against supervised baselines on labeled public data~~ - done
  (`supervised_baseline.py`, +0.73 F1 over the unsupervised ensemble)
- ~~quantify the semi-supervised label budget~~ - done
  (`label_budget_experiment.py`; see [PAPER.md](PAPER.md) §7)
- ~~compare random vs. uncertainty sampling under a fixed label budget~~ - done on both
  benchmarks (`active_learning_experiment.py`; on UNSW-NB15 uncertainty wins a
  five-thousandths-of-F1 margin on a plateau, on CIC-IDS2017 random wins outright —
  see [PAPER.md](PAPER.md) §8)
- ~~add more query strategies + significance testing~~ - done
  (`diversity`, `query-by-committee`; `margin`/`entropy` are collapsed into the single
  posterior-uncertainty strategy because they rank rows identically for a binary
  logistic-regression posterior; `active_learning_stats.py` repeated-seed paired tests:
  non-random strategies are significantly *worse* than random on CIC-IDS2017,
  indistinguishable on UNSW-NB15)
- ~~strict family/day and cross-dataset generalization~~ - done
  (`strict_generalization.py`, `cross_dataset.py`; the day hold-out is a true temporal
  split — the entire held-out day, benign and attack, is test-only; see §2-3 of
  [RESULTS_STRICT_EVALUATION.md](RESULTS_STRICT_EVALUATION.md))
- ~~imbalance + operating-point metrics~~ - done
  (`imbalance_eval.py`; on a 5% reweighted subset recall @ 1% FPR is 0.59-0.67 on
  CIC-IDS2017, 0.93-0.94 on UNSW; the threshold is set on an inner validation split)
- explain *why* the query-strategy effect flips sign between benchmarks (calibration?
  labeling noise?) - calibration analysis exists; a threshold-aware query and a full
  imbalance/FPR sweep are the remaining nice-to-haves
- add parameter sensitivity experiments
- explore feature engineering and dimensionality reduction

## License

Released under the **Non-Commercial Personal-Use License** (see `LICENSE`): free to use
and study for personal/research use, not for commercial sale or production use without
permission, and attribution required.
