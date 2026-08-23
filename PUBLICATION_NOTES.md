# Publication Notes

**Project:** `python-network-anomaly-detector`  
**Status date:** August 23, 2026

## Core claim

For flow-based intrusion detection, the difference between **unsupervised** and
**supervised** learning is much larger than the difference between individual
unsupervised detectors, and a small label budget closes most of that gap — but
query strategy (active learning) is **not reliably better than random labeling**,
and is **significantly worse** on the harder benchmark once split leakage and
imbalance are accounted for.

## Narrow, evidence-backed novelty line

> Uncertainty-based active learning is not reliably better than random labeling for
> intrusion-detection data; calibration and label noise help explain when it fails,
> and the near-perfect balanced random-CV numbers do not survive strict family/day/
> cross-dataset splits or a realistic class imbalance.

## Why this is interesting

- It preserves an honest negative result: unsupervised detection remains weak on
  mixed traffic even when multiple detectors vote.
- It quantifies how much labels buy under the same feature representation.
- It turns the expected active-learning win into a falsifiable question and answers
  "no" on the harder data, backed by repeated-seed paired tests.

## Strongest evidence in the repo

- UNSW-NB15: unsupervised F1 ≈ 0.27 vs supervised ≈ 0.996; CIC-IDS2017: 0.27 vs 0.97;
  CSE-CIC-IDS2018: 0.18 vs 0.92.
- 4 genuinely distinct query strategies (random, posterior-uncertainty,
  diversity/representativeness, query-by-committee). `margin`/`entropy` are collapsed
  into posterior-uncertainty because they rank rows identically for a binary
  logistic-regression posterior.
- Repeated-seed paired tests (`active_learning_stats.py`): on CIC-IDS2017 all
  non-random strategies are **significantly worse than random** (Bonferroni p ≈ 0.02);
  on UNSW-NB15 indistinguishable (none survive Bonferroni).
- Strict splits (`strict_generalization.py`): UNSW generalizes across families
  (F1 0.67-1.00); CIC-IDS2017 collapses across **entire held-out days** (F1 0.00-0.75),
  a true temporal split with no day leakage.
- Cross-dataset (`cross_dataset.py`): CIC-IDS2017 → CSE-CIC-IDS2018 transfer F1 ≈ 0.01
  (vs 0.52 CV-on-train); UNSW/CIC share zero features, so no number there.
- Imbalance/operating points (`imbalance_eval.py`): on a 5% reweighted subset,
  recall @ 1% FPR is 0.59-0.67 on CIC-IDS2017 (0.93-0.94 on UNSW); balanced F1 0.97 is an
  artifact of the 50/50 subset.
- 64 passing tests.

## Main reviewer risks

1. Benchmarks are public and heavily studied; novelty must come from the comparison
   framing and the label-efficiency / negative-result question, not dataset novelty.
2. Some data passes rely on subsets or prepared samples, so the preparation logic and
   leakage guards must be described very clearly.
3. Small-family and low-attack-day F1 estimates carry wide CIs; state this plainly.
4. The cross-dataset transfer uses only the 27 shared CIC features — be explicit.
5. The day hold-out removes Monday (its sampled subset has no attacks) and the
   low-attack days (Tuesday 152, Thursday 35) yield very low F1; state that these are
   small-sample estimates within a wider confidence interval.
6. The 5% positive-rate experiment is a *reweighted balanced subset*, not a naturally
   imbalanced trace; do not call it "realistic traffic."

## Best venue fit

- workshop on intrusion detection, applied ML for security, or usable/evaluated
  security analytics
- secondarily, a short paper emphasizing the label-budget and active-learning result

## One-sentence novelty line

This project turns the usual "which anomaly detector wins?" question into the more
useful one: **how much do labels and active labeling actually help, once you stop
leaking the answer across your splits and use a realistic operating point?**
