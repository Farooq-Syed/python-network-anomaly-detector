# Real Dataset Guide

## Recommended Dataset

For this project, `UNSW-NB15` is the best next step because:

- it is widely cited in intrusion detection research
- it includes labeled network flow records
- it is easier to work with than raw packet captures
- it fits well with the anomaly detection methods already used in this repository

## Official Sources

- UNSW official dataset page: https://research.unsw.edu.au/projects/unsw-nb15-dataset
- CIC-IDS2017 official dataset page: https://www.unb.ca/cic/datasets/ids-2017.html

## Recommended Workflow

1. Download the official `UNSW_NB15_training-set.csv` and `UNSW_NB15_testing-set.csv`
2. Place them somewhere local on your machine
3. Run the preparation script in this repository
4. Run the detector against the prepared subset

## Prepare a Portfolio-Friendly Subset

Example command:

```powershell
python prepare_unsw_nb15.py `
  --train "C:\path\to\UNSW_NB15_training-set.csv" `
  --test "C:\path\to\UNSW_NB15_testing-set.csv"
```

This creates:

```text
data/unsw_nb15_portfolio_subset.csv
```

The preparation script:

- merges the train and test files
- keeps a curated subset of useful numeric columns
- preserves the `label` field
- samples a balanced subset so experiments stay manageable and GitHub-friendly

## Run the Detector on UNSW-NB15

```powershell
python detector.py --input data/unsw_nb15_portfolio_subset.csv --label-column label
```

## Why This Helps Your Profile

Using an official public dataset makes the project more credible because you can now say:

- the methods were evaluated on a recognized benchmark
- the results are reproducible
- the project is closer to academic cybersecurity research than a toy demo

## Suggested README Result Language

You can later add a short section like this:

> Evaluated anomaly detection methods on a balanced subset derived from the official UNSW-NB15 intrusion detection dataset. Compared statistical and unsupervised learning approaches using precision, recall, F1-score, and ensemble voting.
