# Strict Evaluation Results

**Date:** 2026-08-23 (reviewer-corrected revision) · Complements `PAPER.md`. Reproducibility
figures for the strict-evaluation additions: repeated-seed statistics, family/day
generalization, cross-dataset transfer, and imbalance/operating points. Every number is
produced by a script named against it, with seeds in `reproducibility_config.json`.

> The headline and strict supervised results use
> `StandardScaler + LogisticRegression(class_weight='balanced')`; the learner-sensitivity
> section additionally evaluates a calibrated histogram-gradient-boosting learner. The
> unsupervised ensemble is the four-detector vote. Splits are `StratifiedKFold` unless a
> strict hold-out is specified.

**Terminology.** The balanced, random-cross-validation numbers are described as
*in-distribution random-CV optimism*, not "split leakage" — the mechanism is that the CV
fold mix matches the test mix, not that information leaks. The 5% positive-rate
experiment is a *5% reweighted balanced subset*, not "realistic traffic" (it is not a
naturally imbalanced trace).

**Reviewer corrections applied in this revision.**
1. `margin` and `entropy` are collapsed into the single posterior-uncertainty strategy
   (for a binary logistic-regression posterior they rank rows identically to
   `uncertainty`). `query-by-committee` (QBC) is added as a genuinely distinct strategy.
2. The day hold-out is a true temporal split: the **entire** held-out day (benign + attack
   flows) is test-only; no held-out-day row appears in training.
3. The recall@FPR threshold is selected on an inner validation split of each training fold
   and applied once to the untouched test fold.
4. QBC now measures **committee disagreement** as vote entropy over each member's *hard*
   class prediction (see `_vote_entropy`), not a mean posterior-certainty. This is the
   defining QBC property: a committee split 50/50 between confident attack and confident
   benign scores maximum disagreement. The earlier mean-|p−0.5| metric reported such rows
   as *certain* — the opposite of QBC.

---

## 1. Active-learning statistics (repeated-seed, paired tests)

`active_learning_stats.py` — budget=100, 5 folds, 8 seeds. Per-seed F1 at the terminal
budget; paired two-sided Wilcoxon signed-rank + paired t-test, Bonferroni-corrected.

### CIC-IDS2017 (hard)
| strategy | F1 (95% CI) | diff vs random | Wilcoxon p | Bonferroni p | decision |
|---|---:|---:|---:|---:|---|
| random | 0.8887 [0.8824, 0.8951] | — | — | — | — |
| uncertainty | 0.8079 [0.7827, 0.8330] | −0.0809 | 0.0078 | 0.023 | significantly worse |
| diversity | 0.7973 [0.7676, 0.8270] | −0.0914 | 0.0078 | 0.023 | significantly worse |
| committee | 0.8458 [0.8172, 0.8744] | −0.0429 | 0.0156 | 0.047 | significantly worse |

**Reading:** on the harder benchmark every non-random strategy is **significantly worse
than random**. QBC (committee disagreement by vote entropy) is the least-bad of the three,
but still significantly behind random. The sign is inverted vs. the active-learning
literature's usual expectation.

### UNSW-NB15 (easy, separable)
| strategy | F1 (95% CI) | diff vs random | Wilcoxon p | Bonferroni p | decision |
|---|---:|---:|---:|---:|---|
| random | 0.9902 [0.9873, 0.9932] | — | — | — | — |
| uncertainty | 0.9794 [0.9387, 1.0202] | −0.0108 | 0.437 | 1.00 | not significant |
| diversity | 0.9247 [0.8903, 0.9591] | −0.0655 | 0.031 | 0.094 | not significant |
| committee | 0.9954 [0.9951, 0.9957] | +0.0052 | 0.031 | 0.094 | not significant |

**Reading:** on the easy benchmark the non-random strategies are **statistically
indistinguishable** from random (diversity and committee approach significance at p≈0.09
but do not survive Bonferroni). Query strategy buys nothing at the ceiling. QBC is the
best single estimate here (+0.005) but the margin is within noise.

---

## 2. Generalization to unseen families / days

`strict_generalization.py`.

### UNSW-NB15 — hold out one attack family (test = family attacks + 20% benign split)
| held-out family | test attacks | supervised F1 | supervised AUC | unsupervised F1 |
|---|---:|---:|---:|---:|
| Analysis | 145 | 0.964 | 0.993 | 0.505 |
| Backdoor | 11 | 0.667 | 0.994 | 0.112 |
| Backdoors | 91 | 0.943 | 0.995 | 0.399 |
| DoS | 406 | 0.987 | 0.994 | 0.418 |
| Exploits | 2299 | 0.998 | 0.994 | 0.231 |
| Fuzzers | 984 | 0.994 | 0.994 | 0.317 |
| Generic | 1471 | 0.996 | 0.993 | 0.265 |
| Reconnaissance | 528 | 0.990 | 0.996 | 0.366 |
| Shellcode | 43 | 0.887 | 0.997 | 0.351 |
| Worms | 22 | 0.800 | 0.996 | 0.211 |

**Reading:** the supervised baseline retains high performance on most of these bounded
family holdouts (F1 0.67–1.00, AUC ≈ 0.99); the drop is largest for the smallest families.
Unsupervised family-agnostic detection is weaker
(F1 0.11–0.51).

### CIC-IDS2017 — hold out one ENTIRE day (benign + attacks, no day leakage)
| held-out day | test attacks | test benign | supervised F1 | supervised AUC | unsupervised F1 |
|---|---:|---:|---:|---:|---:|
| Friday | 3111 | 1098 | 0.620 | 0.897 | 0.188 |
| Wednesday | 2702 | 1224 | 0.750 | 0.706 | 0.188 |
| Thursday | 35 | 1198 | 0.007 | 0.674 | 0.015 |
| Tuesday | 152 | 1099 | 0.000 | 0.688 | 0.068 |

*(Monday has no sampled attacks, so it is skipped.)*

**Reading:** with a true temporal hold-out the supervised result becomes highly day-dependent
(F1 0.00–0.75) even where AUC stays moderate; attack families and proportions shift day to
day. The balanced random-CV number (0.97) is in-distribution-optimistic and does not describe
every held-out day.

---

## 3. Cross-dataset transfer

`cross_dataset.py` — trains on the shared feature intersection, tests on the other dataset's
shared features.

| train → test | shared features | CV-on-train F1 | transfer F1 | transfer AUC | status |
|---|---:|---:|---:|---:|---|
| CIC-IDS2017 → CSE-CIC-IDS2018 | 27 / 78 | 0.516 | 0.006 | 0.574 | near-random |
| UNSW-NB15 → CIC-IDS2017 | 0 | — | — | — | schema-incompatible |

**Reading:** even between the two schema-compatible CIC datasets, transfer collapses to
F1 ≈ 0.01 (AUC 0.57, barely above chance). UNSW shares zero features with CIC, so no honest
number is reported.

---

## 4. Imbalance and operating points (corrected threshold)

`imbalance_eval.py` — 5% reweighted balanced subset, 5-fold outer CV. Within each outer
training fold, the first split of a stratified 5-fold inner partition reserves 20% for
validation. The model is fitted on the remaining 80%; the threshold maximizes validation
recall subject to validation FPR ≤ 1% and is applied once to the untouched outer test fold.
The 5% subset is constructed deterministically before CV by retaining every benign row and
sampling attack rows; it is not a naturally observed prevalence.

### CIC-IDS2017 (5% attacks)
| model | precision | recall | F1 | ROC-AUC | PR-AUC | recall @ 1% FPR |
|---|---:|---:|---:|---:|---:|---:|
| balanced weights | 0.393 | 0.946 | 0.556 | 0.971 | 0.773 | 0.579 |
| unweighted | 0.926 | 0.608 | 0.733 | 0.974 | 0.807 | 0.665 |

### UNSW-NB15 (5% attacks)
| model | precision | recall | F1 | ROC-AUC | PR-AUC | recall @ 1% FPR |
|---|---:|---:|---:|---:|---:|---:|
| balanced weights | 0.868 | 0.997 | 0.928 | 0.997 | 0.885 | 0.972 |
| unweighted | 0.873 | 0.975 | 0.921 | 0.994 | 0.882 | 0.975 |

**Reading:** on a 5% reweighted subset the balanced-weights model's precision collapses on
CIC (0.39 → most alerts are false), F1 drops to 0.56, and recall at a 1% validation-FPR
budget is only 0.579–0.665. Mean selected validation FPR is 0.0077 and achieved outer-test
FPR is 0.0057 for both models. On UNSW (separable outliers) the same settings keep F1 at
0.92–0.93 with 0.972–0.975 recall@1%FPR; achieved test FPR is 0.0075–0.0078. The
near-perfect balanced random-CV F1 (0.97) is conditional on the prepared 50/50 reference
subset and is not an operational-prevalence estimate.

---

## Reproduce

```powershell
python -m pip install -r requirements-lock.txt
python active_learning_stats.py --input data/cic_ids2017_subset_with_day.csv --label-column Label --budget 100 --seeds 8
python active_learning_stats.py --input data/unsw_nb15_subset_with_family.csv --label-column label --budget 100 --seeds 6
python strict_generalization.py --input data/unsw_nb15_subset_with_family.csv --mode family --family-column family --label-column label
python strict_generalization.py --input data/cic_ids2017_subset_with_day.csv --mode day --day-column day --label-column Label
python cross_dataset.py --train data/cic_ids2017_subset_with_day.csv --test data/cse_cic_ids2018_subset.csv --label-column Label
python imbalance_eval.py --input data/cic_ids2017_subset_with_day.csv --label-column Label --attack-frac 0.05 --fpr 0.01
```

Strategy/split definitions and seeds: `reproducibility_config.json`.
