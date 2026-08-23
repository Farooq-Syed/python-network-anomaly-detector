"""Repeated-seed statistical comparison of active-learning query strategies.

``active_learning_experiment.py`` reports mean ± std across folds for a single
seed/split. That shows the spread but not whether one strategy is reliably
different from another. This driver runs the identical seed-and-fold protocol
over many seeds, collects a per-seed F1 vector for each strategy at a chosen
budget, and asks the two questions a reviewer actually cares about:

  1. Is the difference between random and each alternative strategy
     *statistically significant*, or is it within run-to-run noise?
  2. What is the uncertainty (95% CI) on each strategy's F1 at that budget?

Statistics: per-seed differences between random and the alternative are compared
with a paired two-sided Wilcoxon signed-rank test and a paired t-test, and the
p-values are Bonferroni-corrected for the number of strategies tested. The
Wilcoxon is the primary test because F1 distributions are not reliably normal and
because it only ranks the sign of the per-seed differences.

Usage:
    python active_learning_stats.py --input data/cic_ids2017_subset_with_day.csv \\
        --label-column Label --budget 100 --seeds 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy import stats
from sklearn.model_selection import StratifiedKFold

from active_learning_experiment import STRATEGIES, load_labeled, run_fold

DEFAULT_METRICS = "output/active_learning_stats.json"

# A strategy must differ from random by this F1 to be called "better"/"worse";
# smaller differences are reported as noise regardless of a significant p-value.
EFFECT_SIZE_EPS = 0.005


def run_repeated(features, truth, folds, seed_size, batch_size, budget,
                 seeds, strategies) -> Dict[str, Dict[int, List[float]]]:
    """Run one active-learning trajectory per seed, return per-seed F1 per strategy.

    Returns {strategy: {label_count: [f1_seed0, f1_seed1, ...]}}.
    """
    per_strategy: Dict[str, Dict[int, List[float]]] = {s: {} for s in strategies}
    for seed in seeds:
        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        for train_idx, test_idx in splitter.split(features, truth):
            for strategy in strategies:
                fold_result = run_fold(features, truth, train_idx, test_idx,
                                       strategy, seed_size, batch_size, budget, seed)
                for label_count, f1 in fold_result.items():
                    per_strategy[strategy].setdefault(label_count, []).append(f1)
    return per_strategy


def _ci(values: List[float]) -> tuple[float, float, float, int]:
    """Mean and 95% CI (t-based). Returns (mean, ci_low, ci_high, n)."""
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr))
    if len(arr) < 2:
        return mean, mean, mean, len(arr)
    se = float(np.std(arr, ddof=1)) / np.sqrt(len(arr))
    half = float(stats.t.ppf(0.975, df=len(arr) - 1)) * se
    return mean, mean - half, mean + half, len(arr)


def paired_test(random_f1: List[float], alt_f1: List[float]) -> Dict[str, float | None]:
    """Paired significance test of alternative vs random on the same seeds."""
    diff = np.asarray(alt_f1, dtype=float) - np.asarray(random_f1, dtype=float)
    n = int(len(diff))
    with np.errstate(invalid="ignore"):
        wilcox = stats.wilcoxon(diff)
        tstat = stats.ttest_rel(alt_f1, random_f1)
    return {
        "n_pairs": n,
        "paired_diff_mean": round(float(np.mean(diff)), 4),
        "paired_diff_median": round(float(np.median(diff)), 4),
        "wilcoxon_p": round(float(wilcox.pvalue), 6),
        "ttest_p": round(float(tstat.pvalue), 6),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Repeated-seed statistics for active-learning strategies.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--label-column", default="label")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed-size", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--seeds", type=int, default=20, help="Number of independent seeds >= 1.")
    ap.add_argument("--random-state-start", type=int, default=0, help="First seed value.")
    ap.add_argument("--strategies", nargs="+", default=STRATEGIES, choices=STRATEGIES)
    ap.add_argument("--metrics-output", default=DEFAULT_METRICS)
    args = ap.parse_args()

    features, truth = load_labeled(Path(args.input), args.label_column)
    seeds = list(range(args.random_state_start, args.random_state_start + args.seeds))
    print(f"Loaded {len(truth)} rows, {int(truth.sum())} attacks. "
          f"{len(seeds)} seeds x {args.folds} folds, budget={args.budget}")

    per_strategy = run_repeated(features, truth, args.folds, args.seed_size,
                                args.batch_size, args.budget, seeds, args.strategies)

    # Pool fold-level F1 per seed so each seed contributes one value per strategy.
    per_seed: Dict[str, List[float]] = {s: [] for s in args.strategies}
    for strategy in args.strategies:
        # Average across the folds within a seed; label_count == budget is the
        # terminal budget point. Group by seed is implicit: fold results alternate
        # seed-major, so block-average every `folds` values.
        values = per_strategy[strategy].get(args.budget, [])
        for i in range(0, len(values) - len(values) % args.folds, args.folds):
            per_seed[strategy].append(round(float(np.mean(values[i:i + args.folds])), 4))

    n_tests = max(1, len(args.strategies) - 1)
    summary: Dict[str, dict] = {}
    for strategy in args.strategies:
        mean, lo, hi, n = _ci(per_seed[strategy])
        summary[strategy] = {"f1_mean": round(mean, 4), "ci_low": round(lo, 4),
                             "ci_high": round(hi, 4), "n_seeds": n}

    comparisons = {}
    for strategy in args.strategies:
        if strategy == "random":
            continue
        # Subset to the seeds present in both (they all share the same seeds).
        use = min(len(per_seed["random"]), len(per_seed[strategy]))
        res = paired_test(per_seed["random"][:use], per_seed[strategy][:use])
        res["bonferroni_p"] = round(min(1.0, res["wilcoxon_p"] * n_tests), 6)
        raw_mean_diff = res["paired_diff_mean"]
        if abs(raw_mean_diff) < EFFECT_SIZE_EPS:
            effect = "no-meaningful-effect"
        elif raw_mean_diff > 0:
            effect = "better-than-random"
        else:
            effect = "worse-than-random"
        res["effect_size_decision"] = effect
        comparisons[strategy] = res

    payload = {
        "input": args.input,
        "label_column": args.label_column,
        "budget": args.budget,
        "seeds": len(seeds),
        "folds": args.folds,
        "strategies": args.strategies,
        "effect_size_threshold": EFFECT_SIZE_EPS,
        "per_seed_f1": per_seed,
        "summary": summary,
        "random_vs_alternative": comparisons,
    }
    out = Path(args.metrics_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nPer-strategy F1 @ budget {args.budget} (95% CI, n={args.seeds} seeds):")
    for strategy in args.strategies:
        s = summary[strategy]
        print(f"  {strategy:<12} {s['f1_mean']:.4f}  [{s['ci_low']:.4f}, {s['ci_high']:.4f}]")

    print("\nRandom vs alternative (paired, Bonferroni-corrected):")
    for strategy, c in comparisons.items():
        sig = "SIGNIFICANT" if c["bonferroni_p"] < 0.05 else "not significant"
        print(f"  random -> {strategy:<12} diff={c['paired_diff_mean']:+.4f} "
              f"p_wilcox={c['wilcoxon_p']:.5f} p_bonf={c['bonferroni_p']:.5f} "
              f"({c['effect_size_decision']}) {sig}")
    print(f"\nMetrics -> {out}")


if __name__ == "__main__":
    main()
