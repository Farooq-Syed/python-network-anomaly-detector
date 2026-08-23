# PNAD Publication-Readiness Plan

Grounded in the current repo state (Reviewed 2026-08-23). This file is a **plan only** — no code has been changed.

## Where the paper already is

The current `PAPER.md`, scripts, and committed artifacts already go further than the
generic reviewer feedback assumes. Before planning work, the existing state is:

- **Real benchmarks, not just UNSW:** UNSW-NB15 (F1 0.270/0.996), CIC-IDS2017
  (0.264/0.966), CSE-CIC-IDS2018 (0.183/0.924). `benchmark_compare.py` + fresh SHA-256
  provenance artifacts.
- **Clear negative/positive result:** unsupervised ensemble ≈ 0.27 → supervised ≈ 0.99
  (+0.73), and the active-learning sign flip (uncertainty wins by ~0.005 on UNSW, loses on
  CIC-IDS2017 and CSE-CIC-IDS2018).
- **Calibration analysis is done** (`calibration_analysis.py`): Brier, ECE, reliability
  slope, uncertainty-region error rate — the mechanism behind the sign flip is already
  measured across all three subsets.
- **Mean ± std across folds** everywhere, plus a documented **label-leakage guard** and the
  **z-score self-masking** limitation.

So the "best first paper" angle from the reviewer — *uncertainty active learning is not
reliably better than random labeling; calibration and label noise help explain when it
fails* — is already the abstract's thesis. The plan below closes the *remaining* gaps that
would make it submission-grade, not re-invent it.

## The one hard constraint (read before planning split experiments)

All three committed subsets in `data/` are **fully numeric** — the attack-family column is
dropped:
- `unsw_nb15_public_subset.csv`: no `attack_cat` / family column survives.
- `cic_ids2017_subset.csv` / `cse_cic_ids2018_subset.csv`: label is binarized to 0/1; the
  string `Label`/attack-type names are gone.

**Consequence:** the reviewer's central "train on one family/day, test on unseen
families/days" split **cannot be run on the shipped CSVs**. It needs new preparation that
retains the family / day / source metadata. This is item A below and it is the
prerequisite for items B and the strict-evaluation claims.

---

## Proposed work, in dependency order

### A. Retain attack-family / day / source metadata in the subsets  (prerequisite)

- Modify `prepare_unsw_nb15.py` to keep `attack_cat` (family) and a `day` / split tag
  instead of dropping them, and emit both a binary `label` and a `family` column.
- Modify `prepare_cic_ids2017.py` to keep the day-origin (per-file day) and the full
  string label (attack type) alongside the binary label, so family/day splits are possible.
- Add an optional `--include-metadata` flag so the existing numeric-only path (and all
  current tests/artifacts) remain unchanged by default.
- Reproduce the 3 subsets with metadata retained; re-run `doc:real_dataset_guide.md`
  commands. **Do not break** the existing numeric-subset artifacts — the current paper
  numbers depend on them.

New files: `data/unsw_nb15_family.csv`, `data/cic_ids2017_day.csv`.

### B. Strict generalization evaluation (the reviewer's #1)

New script `strict_generalization.py`:
- **UNSW:** stratify by `attack_cat` — hold out whole families (e.g. one of Fuzzers,
  Exploits, Worms, Shellcode, Reconnaissance, DoS, Analysis, Generic) as test; pick the
  most-frequently-dropped families to keep sizes usable. Report per-held-out-family and
  pooled results.
- **CIC-IDS2017 / CSE-CIC-IDS2018:** split by **day** (train on Monday–Wednesday, test on
  Thursday/Friday) and by attack family.
- Baseline to beat: the existing supervised model; report the **drop** vs the same-model
  random-CV number so the gap is legible.
- Compare supervised vs supervised here (the honest target for family/dataset generalization).

### C. Live/dataset-level leave-one-dataset-out (extend the "cross-dataset" claim)

`benchmark_compare.py` already computes per-dataset numbers. Add a `--leave-one-dataset-out`
mode (or a small `cross_dataset.py`) that trains on two of the three subsets and tests on
the third. This is weaker than family splits (schemas differ across datasets — UNSW uses 23
features, CIC uses ~78) so it needs a shared-feature projection documented explicitly, or be
presented only as "schema-consistent, feature-subset" evidence. Flag this honestly.

### D. Active-learning baselines: entropy, margin, diversity (reviewer's #3)

`active_learning_experiment.py` currently implements only `random` and `uncertainty`.
Extend `STRATEGIES` to:
- `margin` — label the rows with the smallest |p1 − p0| (a margin version already implied by
  the uncertainty framing but not separated).
- `entropy` — label the rows with highest prediction entropy.
- `diversity` — a simple cluster-based / representativeness sampler (k-means centers or
  farthest-first), clearly documented as a cheap approximant, not a state-of-the-art BADGE
  or Coreset.
- Keep `uncertainty` as-is for continuity, and add a `--strategy` CLI arg (currently hard-coded
  to the two).
All strategies run under identical folds/seeds/budget so comparisons are like-for-like.

### E. Confidence intervals + paired statistical tests (reviewer's #4)

- Add a repeated-seed / multiple-split driver (e.g. 10 seeds × 5 folds) collecting per-seed
  metric vectors.
- Compute 95% CI (or bootstrap) on the metric means.
- Run **paired** significance tests across strategies (e.g. paired t-test / Wilcoxon on
  per-seed differences, or a Pratt/paired bootstrap), and **Bonferroni-correct** for the
  multiple budget points tested. Report whether the active-learning gains are even
  statistically distinguishable from random.
- This is the item that makes the "not reliably better" negative claim *evidence-backed*
  rather than "small but sometimes opposite in sign."

### F. Realistic class imbalance + operational operating points (reviewer's #5)

- Fix the balanced-subset limitation: build imbalanced variants (e.g. 90:10, 99:1 attack:benign
  matching real-world rates, or reverse for realistic benign:attack) using the retained
  metadata.
- Add operational metrics: recall at a **fixed FPR** (e.g. @1% and @10%), precision-recall
  AUC, and F1 at the detection operating point implied by the contamination budget.
- Report detection rate at the realistic alert budget, not just F1 at the balanced default.

### G. Related work + narrow, evidence-backed novelty claim (reviewer's #6)

- Expand `REFERENCES.md` / `PAPER.md` §10 from the current deliberate "no specific figures"
  stance into a proper related-work section: cite the uncertainty-vs-random active learning
  literature on tabular/IDS data, calibration literature (Platt, isotonic, temperature),
  and label-noise literature, and state explicitly where the contribution differs from
  (or confirms) prior results.
- Narrow the claim to: **"On these three IDS benchmarks, the sign and significance of the
  query-strategy effect are dataset-dependent, and calibration is a plausible shared
  mechanism."** Present the negative result as the contribution, backed by E/G statistics.

### H. Reproducibility artifact (reviewer's #7)

- `requirements.txt` is only single-line; pin exact versions (freeze) into a
  `requirements-lock.txt` (or `constraints.txt`).
- Add dataset **download scripts** (`scripts/download_*.py` or extend the `prepare_*.py`
  files) that fetch and checksum the sources.
- Freeze **split IDs and seeds** into a single config/JSON so every number is reproducible.
- Add a metadata header to every artifact JSON (input SHA-256, seed, split definition,
  environment).
- Prepare an **anonymized repository** checklist (remove author-identifying paths — note
  `PAPER.md` embeds `D:\Projects\...` paths; strip real source URLs if a blind review).

---

## What I will NOT touch (and why)

- The existing numeric-only subsets and their committed artifacts — the current published
  numbers depend on them. All new work is additive (`--include-metadata`, new files).
- The existing `random`/`uncertainty` results — new baselines are additive.
- HBBMAAD, THLA, VSART, TAIM, Duress-Guard work — out of scope for this plan; the reviewer
  ranked them behind PNAD.

## Suggested execution order

1. A (retain metadata) → reproduce subsets.
2. D (baselines) — independent, small, high-value, gives immediate comparisons.
3. E (stats driver) — needed to interpret D's output.
4. B (family/day split) and F (imbalance/operational) — depend on A.
5. C (cross-dataset) — dependent on schema alignment; do last, flag honestly.
6. G and H — writing and reproducibility, once the numbers stabilize.
