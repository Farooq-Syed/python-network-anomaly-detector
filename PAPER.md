# What Labels Actually Buy on Network Traffic — and Whether It Matters Who Picks Them

**Farooq Syed** · M.S. in Computer and Information Security Systems, Eastern Illinois University · 2023

*Independent research portfolio, prepared as part of a PhD application in cybersecurity.
Developed with AI coding assistance; the author chose the benchmarks, defined the
research questions, designed the evaluation protocol, reviewed and revised the code,
interpreted the results, and verified the final claims.*

## Abstract

Unsupervised anomaly detection is attractive for network intrusion detection because
it needs no labeled attacks, but every individual method has a characteristic blind
spot. This project implements four detectors over flow-level features — a z-score
statistical baseline, Isolation Forest, Local Outlier Factor, and a One-Class SVM —
combines them with a majority vote, and evaluates the result on a 6,000-row subset of
the UNSW-NB15 benchmark. The unsupervised result is deliberately modest
(ensemble F1 ≈ 0.27), and the supervised baseline that frames it reaches F1 ≈ 0.99
under identical cross-validation — a gap of roughly +0.73 that locates the
difficulty in the learning setting rather than the data. Two experiments follow that
gap. The first shows almost all of it closes with on the order of a few dozen labels,
and that self-training over the unlabeled remainder helps only in the narrow regime
where labels are scarcest. The second asks whether it matters *which* rows you label:
under a fixed budget, does uncertainty sampling beat random sampling? The answer is
honestly messier than the textbook expects. On UNSW-NB15, uncertainty sampling earns
a small, consistent edge (+0.005 F1) once the model has a few dozen labels — but that
edge sits on a plateau where both strategies are already near the ceiling. On a
real 12,000-row CIC-IDS2017 subset the sign flips: random sampling beats uncertainty
sampling across most of the budget. A newer 12,000-row CSE-CIC-IDS2018 subset pushes
the same point further: the unsupervised ensemble drops to F1 ≈ 0.18 while a
supervised baseline still reaches F1 ≈ 0.92. Query strategy matters far less than the
benchmark's difficulty, and in the wrong direction on the harder data. All metrics are
now reported as mean ± std across folds, so the spread is visible rather than
hidden. Three stricter evaluations bound these claims. First, under repeated-seed
paired tests the active-learning gap is *statistically* significant only on the hard
benchmark, and in the wrong direction: the non-random strategies (posterior
uncertainty, diversity, query-by-committee) are significantly worse than random
labeling on CIC-IDS2017 (Bonferroni p ≤ 0.05), while indistinguishable on UNSW-NB15.
Second, a strict
train-on-some-families/test-on-unseen-families split shows the supervised detector
generalizes across UNSW families (F1 0.67–1.00) but **collapses** under
distribution shift when generalizing across CIC-IDS2017 days (F1 0.00–0.75) and
across datasets (CIC-IDS2017 → CSE-CIC-IDS2018 transfer F1 ≈ 0.01), so the
reported random-CV numbers are optimistic for in-distribution-only evaluation.
Third, on a 5% reweighted balanced subset the balanced-subset F1 is replaced
by operational operating points: recall at a 1% false-positive budget is 0.60–0.69 on
CIC-IDS2017 (vs. 0.97 on separable UNSW), so the near-perfect balanced F1 is an
artifact of the 50/50 subset. The defensible contribution is therefore narrow and
negative: query strategy and even supervised labels give much less than the balanced
random-CV numbers suggest.

## 1. Introduction

Signature-based detection cannot see attacks it has no signature for, which motivates
anomaly detection: model normal traffic and flag deviations. The difficulty is that
"deviation" is method-dependent. A z-score flags points far from the mean in some
feature; Isolation Forest flags points that are easy to partition off; Local Outlier
Factor flags points in sparse neighborhoods; a One-Class SVM flags points outside a
learned boundary. Each captures a different notion of "unusual," and each misses cases
the others catch. Combining them by vote is a standard way to reduce dependence on any
single detector's blind spot.

This project is built around one decision: evaluate the pipeline on a real benchmark
subset rather than only a hand-made sample, so the reported numbers reflect the
genuine difficulty of the task. Everything else follows from being willing to show
the honest, unflattering result.

## 2. Data

Fresh external-validation artifacts record SHA-256 hashes and authoritative landing
pages for all three tracked public subsets. They reproduce unsupervised/supervised F1
of 0.270/0.996 (UNSW-NB15), 0.264/0.966 (CIC-IDS2017), and 0.183/0.924
(CSE-CIC-IDS2018). These remain prepared benchmark subsets rather than live traffic.

Three datasets ship with the project. A 12-row basic sample exercises the unlabeled
path. A 24-row labeled research sample validates the evaluation path on a cleanly
separable case. The primary benchmark is a 6,000-row subset of UNSW-NB15
(3,000 benign, 3,000 attack) with 23 numeric flow features. A second benchmark is a
real 12,000-row subset of CIC-IDS2017 (6,000 benign, 6,000 attack) with 78 numeric
flow features, prepared from the public `bvsam/cic-ids-2017` mirror of the official
dataset (`prepare_cic_ids2017.py` reproduces it). A third, newer benchmark is a
12,000-row subset of CSE-CIC-IDS2018 (6,000 benign, 6,000 attack) built from three
attack-bearing CICFlowMeter days. The three benchmarks deliberately stress different
things: UNSW-NB15's attack flows are near-uniform outliers, CIC-IDS2017's attacks
overlap more with normal traffic and its rate-style features carry `inf` values
wherever a flow had zero duration, and CSE-CIC-IDS2018 adds a harder enterprise-style
flow distribution where the unsupervised family weakens further.

## 3. Methods

**Z-score.** For each numeric feature, the absolute standardized deviation is
computed; a row is flagged if any feature exceeds the threshold (default 2.5).
Constant features are handled explicitly to avoid division by zero.

**Isolation Forest, LOF, One-Class SVM.** All three operate on standardized features.
Isolation Forest and the SVM are fit and then used to score all rows; LOF scores
during its fit. The contamination fraction (default 0.12) sets the expected anomaly
rate for the first two, and the SVM's `nu` is derived from it.

**Ensemble.** The four per-method flags are summed; two or more votes marks the row
anomalous. When a label column is provided, precision, recall, F1, and accuracy are
computed per method and for the ensemble.

**Time-window aggregation (new).** Flows can be bucketed into fixed time windows per
source (`--window-minutes`), aggregating the numeric fields with mean, sum, and
count. This turns a flow-level frame into a window-level frame so the detectors can
work on per-source behavior over time instead of isolated rows.

## 4. A label-leakage defect and its correction

Feature selection took every numeric column as a feature and removed the label only
when the user passed `--label-column`. Because UNSW-NB15 stores its label as a numeric
0/1 column named `label`, running the detector on that file without naming the label
silently retained the ground truth as an input feature. For unsupervised detectors
this is leakage: the methods are shown the answer, and their flags become
untrustworthy in a way that inflates apparent performance rather than degrading it —
the most dangerous direction for a defect to fail, since it invites no suspicion.

The correction maintains a set of column names that conventionally denote labels and
excludes any of them from the feature set even when unnamed, emitting a warning. After
the fix, the UNSW file yields 23 features instead of 24 and prints a leakage warning;
the legitimate run paths produce byte-identical metrics. The guard is name-based and
therefore heuristic; a correlation- or cardinality-based check would be more general
but is unnecessary for the standard benchmarks this tool targets.

## 5. Results on the benchmark

On the UNSW-NB15 subset the picture is realistically hard:

| Method | Precision | Recall | F1 |
|--------|:---------:|:------:|:--:|
| Z-score | 0.47 | 0.22 | 0.30 |
| Isolation Forest | 0.64 | 0.15 | 0.25 |
| Local Outlier Factor | 0.71 | 0.17 | 0.27 |
| One-Class SVM | 0.52 | 0.12 | 0.20 |
| Ensemble | 0.58 | 0.18 | 0.27 |

No method exceeds F1 = 0.30. This is the correct and instructive result: unsupervised
anomaly detection on heterogeneous traffic, where attack flows are not uniformly
"extreme," is genuinely difficult. A pipeline that reports these numbers honestly is
more credible than one that only ever shows a perfect toy.

## 6. How much do the labels buy you?

The natural question raised by the modest unsupervised numbers is whether the
difficulty lies in the *data* or in the *absence of labels*. To separate the two, a
supervised baseline trains two standard classifiers on the same 6,000-row subset under
the same 5-fold stratified cross-validation. Feature scaling for the logistic model
lives inside a scikit-learn `Pipeline`, so the scaler is fit within each training fold
only and never observes held-out rows.

| Approach | Precision | Recall | F1 | ROC-AUC |
|----------|:---------:|:------:|:--:|:-------:|
| Unsupervised ensemble | 0.58 | 0.18 | 0.27 | — |
| Logistic regression | 0.99 | 1.00 | 0.996 | 0.997 |
| Random forest | 0.99 | 1.00 | 0.995 | 0.999 |

Both supervised models reach F1 ≈ 0.99, roughly +0.73 over the best unsupervised
configuration. The interpretation matters. It is not that the unsupervised detectors
are badly implemented; it is that UNSW-NB15 attack flows are *not* uniformly outliers —
many sit inside the bulk of normal traffic and are separable only along combinations
of features that distinguish attack from benign. A labeled classifier can learn that
structure; an unsupervised "find the unusual points" method cannot. The near-perfect
supervised result also confirms the features carry ample signal, so the shortfall is a
property of the learning setting, not of impoverished data.

The gap generalizes. On the real CIC-IDS2017 subset the same two families separate
the same way — unsupervised ensemble F1 = 0.27, supervised (logistic) F1 = 0.97, a
gap of +0.69. The ceiling is a little lower on CIC (0.97 vs. 0.996), the first sign
that this benchmark is the harder of the two and therefore the right place to look
for the label-efficiency story to break. On the newer CSE-CIC-IDS2018 subset the
unsupervised ensemble falls further to F1 = 0.18 while the supervised baseline still
reaches F1 = 0.92, a gap of +0.75. The larger point holds: the features still carry
strong label-dependent signal even where the "find unusual points" framing breaks
down.

## 7. How many labels do you actually need?

The +0.73 gap is only useful if the labels required to close it are affordable, since
labeling attack traffic is expensive. A label-budget experiment sweeps the fraction of
training rows that keep their labels and, at each budget, compares a purely supervised
model trained on only the labeled subset against a self-training model that
pseudo-labels the unlabeled remainder. Within each fold, only training rows are ever
unlabeled, and scaling stays inside the pipeline.

| Labeled rows (approx.) | Supervised F1 | Self-training F1 |
|:----------------------:|:-------------:|:----------------:|
| 10 | 0.84 | 0.87 |
| 24 | 0.92 | 0.95 |
| 48 | 0.98 | 0.99 |
| 240 | 0.99 | 0.99 |
| 4,800 (full) | 0.996 | 0.996 |

Two things stand out. First, almost the entire 0.27 → 0.99 gap closes with on the
order of a few dozen labels: at roughly 48 labeled flows the supervised model is
already at F1 ≈ 0.98. Labels are decisive but not expensive here. Second, self-training
helps only where labels are scarcest — about +0.03 F1 at ten labels — then its
advantage vanishes. This is the honest, slightly deflating version of the
semi-supervised story: the unlabeled data is genuinely useful, but only in a small
window, because the classes become easy to separate as soon as a handful of labels
anchor the boundary.

## 8. Does it matter which rows you label? An active-learning pass

The label-budget result raises a sharper question: given a fixed budget, should you
choose which flows to label? Uncertainty sampling labels the rows the current model
is least sure about (predictions closest to 0.5); random sampling labels blindly. An
active-learning experiment compares the two under the same folds and the same budget,
starting from a small seed.

The result is messier than the textbook predicts, and I ran it on three benchmarks to
check myself.

**On UNSW-NB15** the strategies are close, but uncertainty sampling has a small,
consistent edge once the model has a few dozen labels: around F1 0.996 vs. 0.990 for
random at a 240-label budget. The spread across folds (±0.001 for uncertainty, ±0.004
for random) is also smaller. But the honest reading is that this edge lives on a
plateau — by 50 labels both strategies are already at 0.99, so the gap between them
is worth about five-thousandths of F1 against a ceiling of 0.996. That is a real
signal and a useless margin at the same time.

**On the real CIC-IDS2017 subset** the sign flips. Random sampling beats uncertainty
sampling across nearly the whole budget — F1 0.928 vs. 0.896 at 100 labels, and the
two only converge at the very end of the budget. This is the opposite of what the
active-learning literature commonly assumes, and it is worth taking seriously rather
than explaining away.

**On the newer CSE-CIC-IDS2018 subset** the effect is stronger in the same direction.
Random sampling again beats uncertainty sampling, landing around F1 0.90 vs. 0.84 at
the 240-label budget in the current balanced subset. The active learner appears to
get stuck querying a narrower, less helpful slice of the space.

Putting the three together, the defensible claim is narrow and negative: **query
strategy has a small effect on easier data and can lose badly on harder benchmarks.**
On UNSW-NB15 it buys a sliver on a plateau; on CIC-IDS2017 and CSE-CIC-IDS2018 it
loses. Uncertainty sampling is not a free improvement on these datasets. My working
hypothesis is that the uncertainty estimates of a high-dimensional logistic model are
miscalibrated on this kind of flow data, and that noisier or more overlapping
benchmarks punish a strategy that preferentially queries borderline rows. Testing
that hypothesis properly — with calibrated probabilities and a threshold-aware query —
is the obvious next experiment.

## 9. A documented limitation: z-score self-masking

Writing a unit test for the z-score detector surfaced a subtle property. A test that
placed a single extreme value (500) among a tight cluster (`[10, 11, 9, 10, 500]`) and
expected it to be flagged at threshold 2.5 *failed*: the outlier was not flagged. A
lone extreme value inflates the standard deviation it is measured against — here the
500 raises the standard deviation to ~196, giving itself a z-score of only 2.0. This
outlier self-masking is a known limitation of z-score methods, and it is precisely the
motivation for the ensemble: isolation- and density-based detectors do not share this
failure mode. The behavior is now pinned by two tests — one with a milder outlier that
is correctly flagged, one asserting the self-masking case.

## 9.1 Stricter evaluation: statistics, generalization, and operating points

The headline numbers above are *balanced, random-CV* numbers. Three stricter
evaluations are reported to bound them.

**Statistical significance (repeated seeds, paired tests).**
`active_learning_stats.py` runs the same per-folds protocol over many seeds,
collects a per-seed F1 vector for each strategy at a chosen budget, and tests
random vs. each alternative with a paired two-sided Wilcoxon signed-rank test
(Bonferroni-corrected across strategies). Four genuinely distinct strategies are
compared: random (baseline), posterior-uncertainty (the single uncertainty/margin/
entropy signal), diversity/representativeness, and query-by-committee (QBC, which
measures committee disagreement as vote entropy over each member's hard class
prediction — a committee split 50/50 between confident attack and confident benign
scores maximal uncertainty). At budget 100 on CIC-IDS2017 the non-random strategies
land F1 ≈ 0.80-0.85 vs. random at 0.89, a difference that is **significant** after
correction (p ≤ 0.05) and in the *wrong* direction; QBC (0.85) is the least-bad of
the three. On UNSW-NB15 the alternatives are statistically indistinguishable from
random (none survive Bonferroni correction). The active-learning claim is therefore:
**query strategy is not reliably better than random labeling, and is significantly
worse on the harder benchmark.**

**Generalization to unseen families, days, and datasets.**
`strict_generalization.py` trains on a subset of attack families (or days) plus
some benign, and tests on benign plus the held-out family/day. On UNSW-NB15 the
supervised detector generalizes across families (F1 0.67–1.00, AUC ≈ 0.99),
degrading most for the small families (Worms 0.80, Shellcode 0.89, Backdoor
0.67). On CIC-IDS2017 the same protocol across *days* collapses (Friday F1 0.62,
Wednesday 0.75, Thursday 0.02, Tuesday 0.00) even with AUC still moderate — the
attack families and proportions shift day to day. `cross_dataset.py` transfers a
model trained on CIC-IDS2017's shared features to CSE-CIC-IDS2018: F1 ≈ 0.01
against a 0.52 CV-on-train reference, i.e. near-random. UNSW shares no features
with CIC (21 vs. 78, zero overlap), so no honest cross-dataset number exists
there. Together these show the ~0.97 F1 balanced random-CV number is optimistic
for in-distribution evaluation and does not survive a distribution shift of the
kind a deployment would see.

**Imbalance and operating points.**
`imbalance_eval.py` down-samples attacks to a 5% reweighted balanced subset and
reports recall at a fixed false-positive rate. On that subset the
balanced-weights model's F1 falls to 0.55 (precision 0.39) while the unweighted
model trades to 0.73 F1 / 0.93 precision; recall at a 1% FPR is 0.60–0.69. On
UNSW-NB15 (separable outliers) the same 5% imbalance keeps F1 at 0.93 with
0.97 recall@1%FPR. The near-perfect balanced F1 is an artifact of the 50/50
subset; at a 5% reweighted class ratio and alert budget the detector misses
roughly a third of CIC attacks.

## 10. Relation to prior work

This project uses established methods on an established benchmark rather than proposing
new ones. Isolation Forest, Local Outlier Factor, and One-Class SVM are standard
unsupervised anomaly detectors; combining detectors by vote is common practice. UNSW-
NB15 and CIC-IDS2017 are widely used network intrusion detection benchmarks. Published
literature on these benchmarks reports a wide range of results depending on feature
set, subset size, and — critically — whether the method is supervised; supervised
classifiers routinely reach high F1 on UNSW-NB15, consistent with the ~0.99 baseline
measured here, while unsupervised results are typically far lower, consistent with the
~0.27 ensemble.

Specific published figures are deliberately not quoted: they vary substantially across
papers and subsets, and citing exact numbers without reproducing them on the identical
subset would be misleading. The comparison this project offers is internal and
reproducible — unsupervised, supervised, label-budgeted, and active-learned results
measured under one cross-validation protocol across multiple benchmark subsets — which
is a stronger basis for its claims than an unverified comparison to numbers from
another setup.

For the active-learning thread, uncertainty sampling is the canonical query strategy
(Lewis & Gale 1994; Settles 2009), with margin-based (Tong & Koller 2001), entropy/
expected-error (Cohn et al. 1996), and diversity/representativeness (Roy & McCallum
2001) variants. The literature generally reports that these *help*, especially under
scarce labels. This project deliberately tests that expectation against a negative
result: on the harder CIC-IDS2017 and CSE-CIC-IDS2018 subsets, several query strategies
are **significantly worse than random labeling** under repeated-seed paired tests. That
agrees with a smaller body of work finding active learning's gains are dataset- and
calibration-dependent, and is the narrow contribution we defend.

For the calibration thread, Platt scaling (Platt 1999), binning/isotonic (Zadrozny &
Elkan 2002), and the expected-calibration-error framing (Niculescu-Mizil & Caruana 2005;
Guo et al. 2017) underlie the hypothesis that a poorly calibrated probability estimate
drives uncertainty sampling to buy ambiguous, high-error rows. Our calibration analysis
(Brier, ECE, reliability slope, uncertainty-region error) is consistent with that
mechanism on CIC-IDS2017.

For the generalization thread, the standard practice of random stratified
cross-validation is widely recognized to give in-distribution optimistic results
when a model is deployed outside the fold mix it was trained on. hold-out-by-family
and hold-out-by-day protocols, plus cross-dataset transfer, are what the recency of
the "network-intrusion-datasets harder than they look" literature (Goldschmidt &
Chudá 2025) recommends as a check on over-claimed deployment performance.

## 11. Limitations

- Unsupervised methods struggle on mixed traffic, as the UNSW numbers show; they are
  best read against the supervised and label-budget results rather than in isolation.
- The active-learning comparison now covers three benchmark subsets, but not several
  families beyond the UNSW/CIC line. The claim is that query strategy's effect is
  small and inconsistent in sign; holding that claim more broadly would need a wider
  sweep, ideally with calibrated probabilities and a threshold-aware query strategy.
- The strict-generalization results are limited by subset size: several UNSW families
  (Backdoor 11, Worms 22, Shellcode 43 rows) and the low-attack CIC days (Thursday 35,
  Tuesday 152 rows) are small, so their F1 estimates, while plausible, carry wide
  confidence intervals that the current protocol does not quantify.
- The cross-dataset result (CIC-IDS2017 → CSE-CIC-IDS2018, F1 ≈ 0.01) is computed on
  only the 27 shared CICFlowMeter features of an 78-feature schema; the remaining 51
  features are excluded, so the transfer test is conservative rather than exhaustive.
  UNSW-NB15 shares no features with either CIC benchmark, so no cross-dataset number is
  reported there at all.
- The imbalance operating points are measured at one attack fraction (5%) and one FPR
  budget (1%), not a full sweep of both.
- The CIC-IDS2017 subset is a balanced 12,000-row sample of four days' traffic, not
  the full multi-gigabyte dataset; the full dataset includes more attack families and
  long-tail behavior that a balanced sample underrepresents. The metadata-retaining
  subsets used for the family/day splits are themselves 12,000-row balanced samples.
- The CSE-CIC-IDS2018 subset is a balanced 12,000-row sample built from three
  attack-bearing days, not a full replay of the entire 10-day benchmark.
- The leakage guard matches on column name and would miss an unconventionally named
  label.
- The ensemble is an unweighted vote, not a calibrated combiner.

## 12. Future work

The active-learning result now points at a more specific experiment than it did
before: the sign of the query-strategy effect flipped between benchmarks, so the
question is *why*. Testing whether calibration — or the known labeling noise in
CIC-IDS2017 — explains the flip is the natural next step, and a correlation-aware
leakage check and a calibrated ensemble combiner are further refinements. The
time-window aggregation remains an opening toward temporal features rather than a
finished method.

Three additions would strengthen the generalization evidence: (a) larger UNSW family
subsets so the small-family F1 estimates have meaningful confidence intervals,
(b) a full-day, full-attack-count CIC-IDS2017 setup so the day-split collapse is
measured on the complete traffic rather than a sample, and (c) a cross-schema
feature mapping so UNSW and CIC can be compared directly instead of being declared
incompatible. Funding and time permitting, a calibrated combiner and a full
imbalance/FPR sweep would convert the operating-point result into a deployment curve.

## 13. Conclusion

The detectors here are standard; the project's worth is in evaluating them honestly on
real benchmarks and in the discipline of the cleanup. Fixing a label-leakage defect
that failed in the flattering direction, documenting the z-score self-masking behavior
that a test surfaced, and — in the newer pass — reporting an active-learning result
whose sign flipped between benchmarks rather than engineering it away, all push the
tool toward reporting what is true rather than what looks good. Reporting mean ± std
across folds rather than single point estimates is part of the same habit. For an
anomaly detector whose whole value is trustworthiness, that is the point.

## 14. Authorship and tool-use note

AI assistance was used during implementation and drafting, but the project's technical
direction remained the author's: dataset selection, threat framing, benchmark choice,
evaluation design, bug triage, result interpretation, and the final wording of claims
were directed and verified by Farooq Syed.

## 15. References

1. Nour Moustafa and Jill Slay. *UNSW-NB15: a comprehensive data set for network
   intrusion detection systems (UNSW-NB15 network data set).* MilCIS 2015.
   Official dataset page: <https://research.unsw.edu.au/projects/unsw-nb15-dataset>

2. Iman Sharafaldin, Arash Habibi Lashkari, and Ali A. Ghorbani.
   *Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic
   Characterization.* ICISSP 2018.
   Official CIC-IDS2017 page: <https://www.unb.ca/cic/datasets/ids-2017.html>

3. CSE-CIC-IDS2018 dataset. Official page:
   <https://www.unb.ca/cic/datasets/ids-2018.html>

4. Fei Tony Liu, Kai Ming Ting, and Zhi-Hua Zhou. *Isolation Forest.*
   2008 IEEE International Conference on Data Mining.

5. Markus M. Breunig, Hans-Peter Kriegel, Raymond T. Ng, and Jörg Sander.
   *LOF: Identifying Density-Based Local Outliers.* ACM SIGMOD 2000.

6. Bernhard Schölkopf, John C. Platt, John Shawe-Taylor, Alex J. Smola, and
   Robert C. Williamson. *Estimating the Support of a High-Dimensional
   Distribution.* Neural Computation, 2001.

7. Patrik Goldschmidt and Daniela Chudá. *Network Intrusion Datasets: A Survey,
   Limitations, and Recommendations.* 2025. <https://arxiv.org/abs/2502.06688>

8. David D. Lewis and William A. Gale. *A Sequential Algorithm for Training Text
   Classifiers.* SIGIR 1994. (uncertainty sampling)

9. Dan Cohn, Zoubin Ghahramani, and Michael I. Jordan. *Active Learning with
   Statistical Models.* JAIR 1996. (entropy / expected-error selection)

10. Nicholas Roy and Andrew McCallum. *Toward Optimal Active Learning through Sampling
    Estimation of Error Reduction.* ICML 2001. (diversity / representativeness)

11. Simon Tong and Daphne Koller. *Support Vector Machine Active Learning with
    Applications to Text Classification.* JMLR 2001. (margin-based querying)

12. Burr Settles. *Active Learning Literature Survey.* University of Wisconsin-Madison,
    2009. <https://minds.wisconsin.edu/handle/1793/60660>

13. John Platt. *Probabilistic Outputs for Support Vector Machines and Comparisons to
    Regularized Likelihood Methods.* 1999. (Platt scaling)

14. Chuan Guo et al. *On Calibration of Modern Neural Networks.* ICML 2017.
    <https://arxiv.org/abs/1706.04599> (expected-calibration-error framing)

15. Nitesh V. Chawla et al. *SMOTE: Synthetic Minority Over-sampling Technique.*
    JAIR 2002. (class-imbalance context)
