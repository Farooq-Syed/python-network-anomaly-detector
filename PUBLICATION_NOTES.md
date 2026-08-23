# Publication Notes

**Project:** `python-network-anomaly-detector`  
**Status date:** August 22, 2026

## Core claim

For flow-based intrusion detection on realistic benchmark traffic, the difference
between **unsupervised** and **supervised** learning is much larger than the
difference between individual unsupervised detectors, and a small label budget closes
most of that gap.

## Why this is interesting

- It preserves an honest negative result: unsupervised detection remains weak on
  mixed traffic even when multiple detectors vote.
- It quantifies how much labels buy under the same feature representation.
- It tests whether active querying helps, and finds that the answer depends more on
  benchmark difficulty than hype around active learning would suggest.

## Strongest evidence already in the repo

- UNSW-NB15: unsupervised F1 about `0.27` vs supervised F1 about `0.996`
- CIC-IDS2017: unsupervised F1 about `0.27` vs supervised F1 about `0.97`
- CSE-CIC-IDS2018-style pass: the same family gap persists on harder data
- 28 passing tests

## Main reviewer risks

1. Benchmarks are public and heavily studied; novelty must come from the **comparison
   framing** and the label-efficiency question, not dataset novelty.
2. Some data passes rely on subsets or prepared samples, so the preparation logic and
   leakage guards must be described very clearly.
3. A reviewer may read the low unsupervised F1 as weakness unless the paper makes the
   "honest result" contribution explicit.

## Best venue fit

- workshop on intrusion detection, applied ML for security, or usable/evaluated
  security analytics
- secondarily, a short paper emphasizing the label-budget and active-learning result

## Experiments still worth adding

- calibration check for uncertainty-based active learning
- one table showing mean and standard deviation across all benchmark passes
- one ablation showing ensemble threshold sensitivity

## One-sentence novelty line

This project turns the usual "which anomaly detector wins?" question into the more
useful one: **how much do labels matter, and when does active labeling actually help?**
