# Python-Based Network Anomaly Detector

This project explores anomaly detection for network traffic using a mix of statistical and unsupervised machine learning methods. It was built as a small security analytics project around flow-level features such as packet counts, byte volume, duration, failed logins, and port activity.

The current pipeline compares four detectors:

- `Z-score`
- `Isolation Forest`
- `Local Outlier Factor`
- `One-Class SVM`

The final anomaly decision is made with a simple ensemble rule: a row is flagged when at least two methods identify it as anomalous.

## Features

- CSV-based workflow for traffic or flow records
- automatic numeric feature selection
- comparison across multiple anomaly detection methods
- optional evaluation with labeled data
- exported reports, metrics, and plots
- helper script for preparing `UNSW-NB15`

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
|   `-- labeled_research_sample.csv
|-- assets/
|   |-- ensemble_confusion_matrix_sample.png
|   |-- feature_scatter_sample.png
|   `-- method_comparison_sample.png
|-- notebooks/
|   `-- network_anomaly_analysis.ipynb
`-- docs/
    `-- real_dataset_guide.md
```

## Installation

```powershell
python -m pip install -r requirements.txt
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

Prepare and run a subset from `UNSW-NB15`:

```powershell
python prepare_unsw_nb15.py --train "C:\path\to\UNSW_NB15_training-set.csv" --test "C:\path\to\UNSW_NB15_testing-set.csv"
python detector.py --input data/unsw_nb15_portfolio_subset.csv --label-column label
```

## Output

The detector writes its results to `output/`:

- `anomaly_report.csv`
- `summary.json`
- `metrics.json` when a label column is provided
- plots such as feature scatter, method comparison charts, and an ensemble confusion matrix

## Methods

### Z-score

Provides a simple statistical baseline by flagging rows with unusually large deviations in one or more numeric fields.

### Isolation Forest

Detects anomalies by isolating observations that are easier to separate from the rest of the dataset.

### Local Outlier Factor

Measures how isolated a row is relative to the density of its local neighborhood.

### One-Class SVM

Learns a boundary around normal-looking traffic and flags rows that fall outside it.

### Ensemble

Uses a majority-style vote across the four methods to reduce dependence on any single detector.

## Sample Results

On the included labeled research sample (`24` rows, `4` attack rows), the ensemble flagged all four malicious rows.

Sample metrics from `output/metrics.json`:

| Method | Precision | Recall | F1-score | Accuracy |
| --- | --- | --- | --- | --- |
| Z-score | 1.00 | 1.00 | 1.00 | 1.00 |
| Isolation Forest | 1.00 | 0.75 | 0.86 | 0.96 |
| Local Outlier Factor | 1.00 | 0.75 | 0.86 | 0.96 |
| One-Class SVM | 1.00 | 0.50 | 0.67 | 0.92 |
| Ensemble | 1.00 | 1.00 | 1.00 | 1.00 |

These numbers come from a small synthetic sample and are mainly useful for validating the pipeline. The next step is to run the same workflow on a larger public dataset such as `UNSW-NB15`.

## Sample Visuals

Feature scatter:

![Feature scatter](assets/feature_scatter_sample.png)

Method comparison:

![Method comparison](assets/method_comparison_sample.png)

Ensemble confusion matrix:

![Confusion matrix](assets/ensemble_confusion_matrix_sample.png)

## Notebook

The repository includes `notebooks/network_anomaly_analysis.ipynb` for a lightweight exploratory analysis workflow. It uses the labeled sample dataset and can be extended later for public benchmark datasets.

## Real Dataset Notes

The repository includes `docs/real_dataset_guide.md` and `prepare_unsw_nb15.py` to convert the official `UNSW-NB15` train and test CSV files into a smaller subset for experimentation.

Official dataset pages:

- [UNSW-NB15](https://research.unsw.edu.au/projects/unsw-nb15-dataset)
- [CIC-IDS2017](https://www.unb.ca/cic/datasets/ids-2017.html)

## Limitations

- the included datasets are small and intended for demonstration
- results are sensitive to feature selection and model parameters
- unsupervised methods can still produce false positives on borderline traffic patterns

## Next Steps

- run the pipeline on the official `UNSW-NB15` data
- add a short notebook for exploratory analysis
- include confusion matrices and parameter sensitivity checks

## License

Released under the MIT License.
