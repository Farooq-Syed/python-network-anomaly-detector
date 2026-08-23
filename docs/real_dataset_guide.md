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

If you want a faster setup path, the repository also supports a public Hugging Face mirror of the dataset through the `--hf-dataset` option.

## Prepare a Portfolio-Friendly Subset

Example command:

```powershell
python prepare_unsw_nb15.py `
  --train "C:\path\to\UNSW_NB15_training-set.csv" `
  --test "C:\path\to\UNSW_NB15_testing-set.csv"
```

Alternative using a public mirror:

```powershell
python -m pip install datasets pyarrow
python prepare_unsw_nb15.py --hf-dataset Mouwiya/UNSW-NB15 --output data/unsw_nb15_public_subset.csv --rows-per-class 3000
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

## Metadata-retaining subsets (for strict family/day splits)

The committed numeric-only subsets drop the attack-family / day metadata that strict
generalization experiments require. Two additive options retain it:

- `prepare_unsw_nb15.py --include-metadata` keeps a `family` column (UNSW `attack_cat`,
  with `Normal` mapped to `Benign`) plus an `is_attack` marker.
- `prepare_cic_ids2017.py --include-metadata` (or `scripts/download_datasets.py`) keeps a
  `day` column (per flow-sheet weekday) and a `label_name` column (the full attack-type
  string) alongside the binary `Label`.

The `--include-metadata` flag is off by default, so existing numeric-only outputs and all
committed artifacts are byte-for-byte unchanged.

One-shot download + prepare (fetches UNSW-NB15 from the `Mouwiya/UNSW-NB15` HF mirror and
the CIC-IDS2017 `machine_learning/` flows from `bvsam/cic-ids-2017`):

```powershell
python scripts/download_datasets.py --all
```

This writes:

```text
data/unsw_nb15_subset_with_family.csv
data/cic_ids2017_subset_with_day.csv
```

`data/unsw_nb15_public_subset.csv` (and the other shipped numeric subsets) are unchanged.

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
