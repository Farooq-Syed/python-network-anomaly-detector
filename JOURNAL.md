# Dev journal — network anomaly detector

This is the most finished of the four projects — it already had a real benchmark
(a UNSW-NB15 subset) and honest, unimpressive numbers on it, which I respect more
than a toy that scores 1.00 on everything. So this pass was about finding the sharp
edges, not rebuilding anything.

## Baseline before touching it

Three runs to anchor myself:

- basic sample (12 rows): 3 flagged, nothing else to check, no labels
- labeled research sample (24 rows, 4 attacks): ensemble F1 = 1.00, z-score also
  1.00, IF/LOF ~0.86, OCSVM 0.67
- UNSW subset (6000 rows): ensemble F1 ≈ 0.27, z-score best at 0.30, everything
  else in the 0.20–0.27 range

All three reproduced the README tables basically exactly, which was reassuring — the
numbers in the docs are real and current.

## The bug that actually matters: silent label leakage

`select_numeric_columns` picks every numeric column as a feature and removes the
label — but *only if you pass `--label-column`*. Here's the trap: in the UNSW file
the label is a numeric 0/1 column literally named `label`. If you run the detector
on that file **without** `--label-column` (say you just want an anomaly report, not
an evaluation), the label column stays in the feature set. So the unsupervised
detectors get handed the ground truth as an input feature. I confirmed it:

```
label in feature columns when --label-column omitted?: True
n features: 24
```

For unsupervised anomaly detection this is proper leakage — the model is looking at
the answer. It wouldn't crash, it wouldn't warn, it'd just quietly give you
suspiciously good-looking flags. That's the worst kind of bug: it makes you look
*better*, so you never question it.

Fix: keep a small set of column names that are almost always labels (`label`,
`attack`, `attack_cat`, `class`, `target`, `is_anomaly`, `ground_truth`, `y`) and
drop any of them from the feature set even when they aren't the named eval label —
with a warning so the user knows it happened. After the fix, running UNSW without
`--label-column` gives 23 features and prints a leakage warning. All three normal
runs still produce identical metrics, so I didn't break the legitimate path where the
label is correctly named and removed.

## The test that failed and taught me something

I wrote what I thought was a trivial z-score test: put `[10,11,9,10,500]` in a
column, the 500 is obviously an outlier, assert it gets flagged at threshold 2.5.

It failed. The 500 was *not* flagged.

Sat with it for a minute, then it clicked — this is outlier self-masking. With only
five values and one enormous one, the outlier drags the standard deviation up to
~196, so its own distance from the mean is only z = 2.0, under the 2.5 threshold:

```
values:     [10, 11, 9, 10, 500]
mean=108.0  std=196.0
z-scores:   [0.5, 0.49, 0.51, 0.5, 2.0]   <- the 500 masks itself
```

This isn't a bug in the code, it's a textbook limitation of the z-score method: a
lone extreme value inflates the very statistic used to judge it. It's *the reason*
you'd want an ensemble in the first place — isolation and density methods don't share
this failure mode. So instead of deleting my broken test I kept two: one with a
milder outlier that does clear the threshold (proving the method works normally), and
one that pins the self-masking behavior explicitly with a comment explaining why. The
second test is more valuable than the one I set out to write, because it documents a
real gotcha future-me would otherwise rediscover the hard way.

Honestly this is my favorite moment of the whole cleanup. I went in to write a
formality and came out understanding the method better.

## Housekeeping

- `matplotlib.use("Agg")` before pyplot — headless safety, same as the others.
- Smoke test was using bare `"python"` in the subprocess; swapped for
  `sys.executable`. (This same bug was in all four projects. I'm now fairly sure it
  was copy-pasted from a template.)

## Tests

1 smoke test → 11 total. New unit file covers label normalization, the feature
selection + leakage guard (including a regression test that a numeric `label` column
gets dropped even unnamed), the z-score detector in both its working and
self-masking regimes, and the 2-vote ensemble rule.

## Next time

- The leakage guard is name-based, which is a heuristic. A more robust version would
  warn on any binary 0/1 column that correlates suspiciously with nothing else — but
  that's a bigger change and name-matching covers the common benchmarks.
- Try CIC-IDS2017 as a second benchmark like the README suggests.
- The UNSW numbers are low because unsupervised methods genuinely struggle on mixed
  traffic; a supervised baseline would make the comparison more honest.

## Feature pass: active learning, second benchmark, time windows

Three additions, and the active-learning one surprised me.

- **Active learning.** The label-budget experiment showed a few dozen random labels
  close most of the gap. The obvious follow-up: does *choosing* which labels help?
  ctive_learning_experiment.py compares uncertainty sampling (label the rows the
  model is most unsure about) against random sampling under the same budget and
  folds. Result: random keeps pace, and at several budgets beats uncertainty. That's
  the honest negative result - on UNSW-NB15 the classes separate so cleanly that the
  model's uncertainty isn't informative enough for query strategy to matter. It's the
  result that needs a harder benchmark to test, not a flattering one to hide.
- **Second benchmark.** The pipeline can now ingest CIC-IDS2017-style data via
  prepare_benchmark, which recognizes the schema and maps the string labels. A
  synthetic CIC-style sample ships so the path is tested; pointing it at the real
  dataset is a one-command job and the natural next experiment.
- **Time windows.** --window-minutes aggregates flows into per-source time windows
  (mean/sum/count) before detection. A first step toward temporal features rather
  than a finished method.

Test count is up to 26. The unsupervised 0.27 and supervised 0.99 numbers on the UNSW
subset are unchanged.

## Real CIC-IDS2017 pass

Took the second-benchmark claim from "one command away" to actually done.

- **Data.** Downloaded four days of the real CIC-IDS2017 flows from the
  bvsam/cic-ids-2017 mirror (Monday benign, Wednesday attacks, Friday PortScan +
  DDoS) and prepared a balanced 12,000-row, 78-feature subset. Two real-world
  gotchas worth remembering: the flow files carry inf wherever a flow had zero
  duration (a division-by-zero in the original dataset), and a pre-binarized label
  column breaks a loader that only understands "BENIGN" strings. Both are handled
  and pinned by tests now.
- **The result I did not expect.** On CIC-IDS2017, random sampling beats uncertainty
  sampling across almost the whole label budget (F1 0.93 vs 0.90 at 100 labels).
  That's the opposite of the UNSW-NB15 result, where uncertainty wins by about
  +0.005 F1 on a plateau. So the honest summary is: query strategy matters little,
  and its sign flips between benchmarks. My guess is miscalibrated probabilities on
  high-dimensional flow features, plus CIC's known labeling noise punishing a
  strategy that goes hunting for borderline rows. That is a hypothesis to test, not
  a number to hide.
- **Confidence intervals.** Every cross-validated number in this repo now carries a
  per-fold mean +/- std. It changed how I read my own results: the "wins" at the
  early budgets are all within noise, and only the late-budget UNSW edge survives.
