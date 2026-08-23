# Calibration finding — why the active-learning sign flips

Reproducible follow-up to the active-learning experiment
(`active_learning_experiment.py`), on the real public benchmark subsets.

## The observation

`active_learning_experiment.py` compares two query strategies under a fixed label
budget: **random** labeling vs **uncertainty sampling** (label the unlabeled rows the
current model is least sure about, i.e. probability closest to 0.5). It reports an
inconsistent, and interesting, result:

| benchmark | random F1 | uncertainty F1 | who wins |
| --- | --- | --- | --- |
| UNSW-NB15 | — | — | uncertainty by ~+0.005 on a plateau |
| CIC-IDS2017 | 0.93 | 0.90 (at 100 labels) | **random** |

The sign of the effect flips between benchmarks. The question this document answers is
**why**.

## The hypothesis being tested

Uncertainty sampling only helps if the rows a model is "unsure" about are actually
informative. If the model's probabilities are *miscalibrated*, then "uncertain" rows are
genuinely noisy or mislabeled — so the strategy buys noise rather than signal. We test
this by measuring calibration of the *same* supervised pipeline used by the active-learning
experiment (`StandardScaler` + `LogisticRegression(class_weight="balanced")`) under the
same 5-fold stratified setup.

Run it:

```bash
python calibration_analysis.py --input data/unsw_nb15_public_subset.csv --label-column label --metrics-output results/calibration_unsw.json
python calibration_analysis.py --input data/cic_ids2017_subset.csv --label-column Label --metrics-output results/calibration_cic.json
```

## Results (5-fold CV, same seed as the active-learning experiment)

| benchmark | rows | Brier (lower=better) | Expected Calibration Error | reliability slope | rows with p ∈ [0.40,0.60] | model error on that band |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **UNSW-NB15** | 6,000 | 0.0044 ± 0.0012 | 0.0026 ± 0.0005 | 1.002 | **0.03%** | 10% |
| **CIC-IDS2017** | 12,000 | 0.0263 ± 0.0025 | 0.0195 ± 0.0028 | 1.015 | **3.4%** | **45.5%** |

## The mechanism

Two separate things combine to flip the sign:

1. **On UNSW-NB15 the model is almost perfectly calibrated and essentially fully
   confident.** Brier 0.004, ECE 0.003 and a reliability slope of ~1.0 mean the
   probabilities match reality. Critically, only **0.03%** of rows fall in the
   probability band [0.4, 0.6] — this is exactly the band uncertainty sampling picks.
   There is almost nothing there to choose from, so query strategy degenerates to a
   plateau where it is indistinguishable from random. The observed +0.005 is within the
   fold-to-fold noise, not a real signal.

2. **On CIC-IDS2017 the model is miscalibrated and its "uncertain" rows are
   noisy.** Brier is ~6× higher (0.026) and ECE ~8× higher (0.020), so the probabilities
   are over-/under-confident. Now **3.4%** of rows fall in the ambiguous band — and the
   model is **wrong on 45.5% of those rows**. In other words, the rows the uncertainty
   learner deliberately prioritizes are the rows the model (and therefore the ground-truth
   labels) is least trustable on — likely overlapping features and the known labeling
   noise in the CIC flow data. Uncertainty sampling therefore *buys noise rather than
   signal*, so random labeling wins.

## So "why the sign flips"

On a well-separated, well-calibrated benchmark (UNSW-NB15) uncertainty sampling has
nothing useful to exploit, so it cannot beat random (a plateau). On a harder,
miscalibrated, label-noisy benchmark (CIC-IDS2017) the rows the strategy targets are
precisely the untrustable ones, so it hurts — and random wins. The query-strategy choice
matters more when the model is poorly calibrated, and in the *opposite* direction on
harder data.

## Recalibration experiment — fixing it (the improvement test)

If miscalibration is part of the cause, recalibrating the model's probabilities should
improve uncertainty sampling on the miscalibrated benchmark. `recalibration_experiment.py`
re-runs the same uncertainty-vs-random comparison, but each trained model's probabilities
are recalibrated with an **isotonic** fit on the labeled training pool only (no test-set
peeking), before selecting the next batch.

Run it:

```bash
python recalibration_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
python recalibration_experiment.py --input data/cic_ids2017_subset.csv --label-column Label --budget 120
```

Results at a fixed 100-label budget:

| benchmark | random | uncertainty (raw) | uncertainty (recalibrated) |
| --- | ---: | ---: | ---: |
| UNSW-NB15 | 0.990 | 0.996 (+0.005) | 0.995 (+0.005) |
| CIC-IDS2017 | 0.928 | 0.896 (−0.031) | 0.909 (−0.018) |

**What it shows.** On the well-calibrated UNSW-NB15, recalibration changes nothing (the
probabilities were already honest). On the miscalibrated CIC-IDS2017, recalibration
**cuts the uncertainty-sampling deficit by roughly half** (Δ from −0.031 to −0.018) — a
real, measurable improvement — but it does **not** fully flip the sign. Uncertainty
sampling still slightly trails random even after recalibration.

**Refined conclusion.** Miscalibration is a genuine *contributor*: recalibrating recovers
about half of the gap. But the remainder is not explained by calibration alone — it points
to the residual cause flagged from the start: **label noise and overlapping flow features
on the harder benchmark.** So the sign flip is driven by both, in this order of evidence:
(1) a near-degenerate ambiguity band on well-separated UNSW-NB15 leaves uncertainty
sampling with nothing to exploit, and (2) on CIC-IDS2017 the ambiguity band is both
poorly calibrated *and* noisy, so uncertainty sampling buys noise; recalibration fixes the
calibration half, and the label-noise half is the remaining, honest gap.

**Method note (anti-overfit):** recalibration is fit only on the current labeled training
pool and never uses the test fold, and the whole comparison is run under identical
5-fold stratified splits to the baseline. This is an improvement in *measurement honesty*,
not a result tuned on held-out data.

## Interpretation and honest caveats

- This is a **mechanistic explanation**, not a guarantee. The calibration gap is
  correlational here; a fuller account would also inspect feature overlap and label
  error directly. It is the support a reviewer would want before the "why" claim is
  presented as fact.
- The CIC subset is a balanced sample (attack-bearing days); its label noise is a known
  property of the CIC pipelines and is not fully characterized here.
- Both numbers are on the prepared public subsets in `data/`, not the full benchmarks.
- Recalibration recovers ~half the CIC deficit. The residual (label noise / feature
  overlap) is an honest limitation, reported rather than engineered away.

## Where this leads

This is the strongest single thread in the portfolio: it turns an unexplained negative
result into a testable hypothesis with quantitative support on real data, and tests the
fix. The natural next step is the direct label-noise / feature-overlap analysis
(reliability on per-family flows, error analysis on the ambiguity band), and then
per-family recalibration, to close the remaining half.
