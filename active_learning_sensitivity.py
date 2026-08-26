"""Learner-family and label-budget sensitivity for active learning.

Repeats the matched active-learning protocol with the original logistic learner
and a nonlinear histogram gradient-boosting learner. Posterior-based queries for
the nonlinear learner use sigmoid calibration fit only on the currently labeled
training pool. Multiple budgets are read from one trajectory per seed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from active_learning_experiment import MODEL_FAMILIES, STRATEGIES, load_labeled
from active_learning_stats import _ci, paired_test, run_repeated


def summarize(per_strategy, budgets, folds, strategies):
    output = {}
    for budget in budgets:
        per_seed = {strategy: [] for strategy in strategies}
        for strategy in strategies:
            values = per_strategy[strategy].get(budget, [])
            for start in range(0, len(values) - len(values) % folds, folds):
                per_seed[strategy].append(
                    round(float(np.mean(values[start:start + folds])), 4)
                )

        summary = {}
        for strategy, values in per_seed.items():
            mean, lo, hi, n = _ci(values)
            summary[strategy] = {
                "f1_mean": round(mean, 4), "ci_low": round(lo, 4),
                "ci_high": round(hi, 4), "n_seeds": n,
            }

        comparisons = {}
        n_tests = max(1, len(strategies) - 1)
        for strategy in strategies:
            if strategy == "random":
                continue
            use = min(len(per_seed["random"]), len(per_seed[strategy]))
            comparison = paired_test(
                per_seed["random"][:use], per_seed[strategy][:use]
            )
            comparison["bonferroni_p"] = round(
                min(1.0, comparison["wilcoxon_p"] * n_tests), 6
            )
            comparisons[strategy] = comparison

        output[str(budget)] = {
            "summary": summary,
            "random_vs_alternative": comparisons,
            "per_seed_f1": per_seed,
        }
    return output


def run_sensitivity(features, truth, folds, seed_size, batch_size, budgets,
                    seeds, strategies, model_families):
    results = {}
    for model_family in model_families:
        trajectories = run_repeated(
            features, truth, folds, seed_size, batch_size, max(budgets),
            seeds, strategies, model_family=model_family,
        )
        results[model_family] = summarize(
            trajectories, budgets, folds, strategies
        )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Active-learning sensitivity across learner families and budgets."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed-size", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--budgets", type=int, nargs="+", default=[20, 50, 100, 240])
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--random-state-start", type=int, default=0)
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=STRATEGIES)
    parser.add_argument("--model-families", nargs="+", choices=MODEL_FAMILIES,
                        default=MODEL_FAMILIES)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if any(budget < args.seed_size for budget in args.budgets):
        raise ValueError("Every budget must be at least the seed size.")
    if any((budget - args.seed_size) % args.batch_size for budget in args.budgets):
        raise ValueError("Each budget must be reachable from seed-size in batch-size steps.")

    features, truth = load_labeled(Path(args.input), args.label_column)
    seeds = list(range(args.random_state_start, args.random_state_start + args.seeds))
    budgets = sorted(set(args.budgets))
    results = run_sensitivity(
        features, truth, args.folds, args.seed_size, args.batch_size,
        budgets, seeds, args.strategies, args.model_families,
    )
    payload = {
        "input": args.input, "label_column": args.label_column,
        "folds": args.folds, "seed_size": args.seed_size,
        "batch_size": args.batch_size, "budgets": budgets,
        "seeds": seeds, "strategies": args.strategies,
        "model_families": args.model_families,
        "nonlinear_calibration": (
            "CalibratedClassifierCV(method='sigmoid', cv=2) fitted only on the "
            "currently labeled training pool; test rows never select queries or calibration."
        ),
        "nonlinear_model": (
            "HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15, "
            "min_samples_leaf=2, learning_rate=0.08, l2_regularization=1.0). "
            "The small leaf minimum is required because trajectories begin with 10 labels."
        ),
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
