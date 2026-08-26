# Artifact Checklist (frozen revision)

**Revision:** 2026-08-25 publication-quality audit.
**Test suite:** `70 passed`. **Full portfolio validation:** run after the frozen sensitivity result is added.

This list ties every reported number to a command and an artifact so a reviewer (or a
future you) can reproduce the exact figures.

## Environment

```powershell
python -m pip install -r requirements-lock.txt
```

Pinned versions and the frozen seeds / split definitions are in
[`reproducibility_config.json`](reproducibility_config.json).

## 1. Build the metadata-retaining subsets

```powershell
# Fetches UNSW-NB15 from the Hugging Face mirror and the CIC-IDS2017
# machine_learning/ flow exports, then writes:
#   data/unsw_nb15_subset_with_family.csv
#   data/cic_ids2017_subset_with_day.csv
python scripts/download_datasets.py --all
```

## 2. Active-learning experiment + repeated-seed statistics

```powershell
# 5-fold, 4 strategies (random, uncertainty, diversity, committee):
python active_learning_experiment.py --input data/unsw_nb15_subset_with_family.csv --label-column label --budget 240
python active_learning_experiment.py --input data/cic_ids2017_subset_with_day.csv --label-column Label --budget 240 --supervised-reference 0.966

# Repeated-seed paired significance tests (Wilcoxon + paired t, Bonferroni-corrected):
python active_learning_stats.py --input data/cic_ids2017_subset_with_day.csv --label-column Label --budget 100 --seeds 8
python active_learning_stats.py --input data/unsw_nb15_subset_with_family.csv --label-column label --budget 100 --seeds 6

# Learner-family and multi-budget sensitivity (logistic + calibrated nonlinear learner):
python active_learning_sensitivity.py --input data/cic_ids2017_subset_with_day.csv \
    --label-column Label --budgets 20 50 100 240 --seeds 8 \
    --output results/cic_active_learning_model_budget_sensitivity.json
```

## 3. Strict generalization (family / true day hold-out)

```powershell
# Unseen-family (UNSW): test = family attacks + 20% benign split
python strict_generalization.py --input data/unsw_nb15_subset_with_family.csv --mode family --family-column family --label-column label

# True day hold-out (CIC): the ENTIRE held-out day (benign + attack) is test-only
python strict_generalization.py --input data/cic_ids2017_subset_with_day.csv --mode day --day-column day --label-column Label
```

## 4. Cross-dataset transfer

```powershell
# Schema-compatible pair (shares 27 CICFlowMeter features):
python cross_dataset.py --train data/cic_ids2017_subset_with_day.csv --test data/cse_cic_ids2018_subset.csv --label-column Label
```

## 5. Imbalance + operating points (threshold set on an inner validation split)

```powershell
python imbalance_eval.py --input data/unsw_nb15_subset_with_family.csv --label-column label --attack-frac 0.05 --fpr 0.01
python imbalance_eval.py --input data/cic_ids2017_subset_with_day.csv --label-column Label --attack-frac 0.05 --fpr 0.01
```

## 6. Tests

```powershell
python -m pytest -q         # 70 passed
```

## Reviewer-correction notes (this revision)

- `margin` and `entropy` are folded into one **posterior-uncertainty** strategy; they
  rank samples identically for a binary logistic-regression posterior. `query-by-committee`
  (§ in `active_learning_experiment.py`) is the genuinely distinct alternative.
- The day hold-out is a **temporal split** — the held-out day's benign and attack flows
  are all test-only (`evaluate_day_pool`).
- The recall@FPR threshold is selected on an **inner validation split** of each training
  fold by maximizing validation recall subject to FPR ≤ 1%, then applied once to the
  untouched test fold (`_pick_threshold` + `evaluate`).
- Terminology: "in-distribution random-CV optimism" and "distribution shift" (not
  "split leakage"); "5% reweighted balanced subset" (not "realistic traffic").
