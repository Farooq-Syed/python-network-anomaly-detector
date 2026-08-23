"""Can we decide which flows to label, instead of labeling at random?

label_budget_experiment.py shows that a few dozen random labels recover most of the
unsupervised -> supervised gap on UNSW-NB15. This script asks whether an *active*
learner can do even better: with a fixed labeling budget, does choosing the most
uncertain unlabeled flows (uncertainty sampling) beat choosing them at random?

Mechanics, kept deliberately simple:
  - a small random seed of labels gets the model started
  - each round, the model predicts probabilities on the unlabeled rows; the
    uncertainty strategy labels the `batch` rows whose probability is closest to
    0.5, the random strategy labels `batch` random rows
  - both strategies are compared under the same folds and the same budget

Usage:
    python active_learning_experiment.py --input data/unsw_nb15_public_subset.csv --label-column label
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from detector import normalize_label, select_numeric_columns

DEFAULT_INPUT = "data/unsw_nb15_public_subset.csv"
DEFAULT_METRICS = "output/active_learning_metrics.json"
DEFAULT_PLOT = "output/plots/active_learning_curve.png"

UNSUPERVISED_ENSEMBLE_F1 = 0.27
FULLY_SUPERVISED_F1 = 0.996

DEFAULT_SEED = 10
DEFAULT_BATCH = 10
DEFAULT_BUDGET = 240
STRATEGIES = ["random", "uncertainty", "diversity", "committee"]

# Diversity sampling k-means components (a cheap representativeness approximant,
# not a state-of-the-art Coreset/BADGE).
DIVERSITY_CLUSTERS = 10
# Query-by-committee size.
COMMITTEE_SIZE = 10
# Entropy is computed from the two-class posterior (used by the committee vote).
ENTROPY_EPS = 1e-12


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare random labeling against uncertainty-sampling active learning."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS)
    parser.add_argument("--plot", default=DEFAULT_PLOT)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed-size", type=int, default=DEFAULT_SEED, help="Labels to seed the learner.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH, help="Labels added per round.")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Total labels allowed.")
    parser.add_argument(
        "--strategies", nargs="+", default=STRATEGIES,
        choices=STRATEGIES, help="Query strategies to compare.",
    )
    parser.add_argument("--unsupervised-reference", type=float, default=UNSUPERVISED_ENSEMBLE_F1, help="Reference unsupervised F1 (drawn on the plot).")
    parser.add_argument("--supervised-reference", type=float, default=FULLY_SUPERVISED_F1, help="Reference fully-supervised F1 (drawn on the plot).")
    parser.add_argument("--random-state", type=int, default=42)
    return parser


def load_labeled(path: Path, label_column: str):
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    frame = pd.read_csv(path)
    if label_column not in frame.columns:
        raise ValueError(f"Label column '{label_column}' not found.")
    feature_columns = select_numeric_columns(frame, label_column)
    features = frame[feature_columns].to_numpy(dtype=float)
    truth = frame[label_column].apply(normalize_label).to_numpy(dtype=int)
    return features, truth


def _make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


def _entropy(probabilities: np.ndarray) -> np.ndarray:
    """Binary entropy of the positive posterior, in [0, 1]."""
    p = np.clip(probabilities, ENTROPY_EPS, 1 - ENTROPY_EPS)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def select_queries(probabilities: np.ndarray, n: int, strategy: str, rng: np.random.Generator,
                   pool_features: np.ndarray | None = None,
                   labeled_pool: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    """Pick the next rows to label under a query strategy.

    All strategies return indices into the candidate (unlabeled) pool, i.e. rows of
    the ``pool_features`` / ``probabilities`` arrays.

    For a binary logistic-regression model, ``uncertainty`` (posterior closest to
    0.5), ``margin`` (smallest |p1 - p0|), and ``entropy`` (highest binary entropy)
    rank the samples *identically* — they are three names for one
    posterior-uncertainty signal. We therefore report a single ``uncertainty``
    baseline rather than three that are really one.

    * ``uncertainty`` — the rows whose positive posterior is closest to 0.5.
    * ``diversity``  — a cheap representativeness approximant: k-means cluster centers
      in feature space (not a state-of-the-art Coreset/BADGE).
    * ``committee``  — query-by-committee: a small ensemble of bootstrapped classifiers
      trained on the labeled pool; the query is the rows with the highest vote entropy.
      This disagreement metric is independent of the single-model posterior.
    * ``random``     — the fully random baseline to beat.
    """
    if strategy == "uncertainty":
        return np.argsort(np.abs(probabilities - 0.5))[:n]
    if strategy == "diversity":
        if pool_features is None:
            raise ValueError("diversity sampling requires the feature matrix.")
        return _diversity_queries(pool_features, n, rng)
    if strategy == "committee":
        if pool_features is None or labeled_pool is None:
            raise ValueError("committee sampling requires both the pool and the labeled pool.")
        return _committee_queries(pool_features, labeled_pool, n, rng)
    return rng.choice(len(probabilities), size=n, replace=False)


def _committee_queries(pool_features: np.ndarray, labeled_pool: tuple[np.ndarray, np.ndarray],
                       n: int, rng: np.random.Generator) -> np.ndarray:
    """Query-by-committee (QBC): label rows the committee disagrees about most.

    A committee of ``COMMITTEE_SIZE`` bootstrapped logistic regressions is trained on
    the already-labeled pool (``labeled_pool`` = (features, labels)); each member casts a
    *hard* vote (class 0/1) on the unlabeled pool, and rows with the highest committee
    disagreement are queried. Disagreement is measured as either vote entropy or vote
    variance over the committee's hard predictions — a committee split 50/50 (even if
    each member is confident) scores maximally uncertain, which is the defining property
    of query-by-committee. This is genuinely different from the single model's posterior.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x_labeled, y_labeled = labeled_pool
    if len(x_labeled) < 2 or len(x_labeled) < COMMITTEE_SIZE:
        return rng.choice(len(pool_features), size=n, replace=False)
    votes = np.zeros((COMMITTEE_SIZE, len(pool_features)), dtype=int)
    for i in range(COMMITTEE_SIZE):
        # Each member trains on a random 80% subset of the labeled pool, drawn WITHOUT
        # replacement (not a bootstrap, and no resizing). Varying the subset across
        # members is what produces honest committee disagreement.
        idx = rng.choice(len(x_labeled), size=max(2, int(0.8 * len(x_labeled))), replace=False)
        y_sub = y_labeled[idx]
        if len(np.unique(y_sub)) < 2:
            votes[i] = np.full(len(pool_features), 0, dtype=int)
            continue
        member = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        )
        member.fit(x_labeled[idx], y_sub)
        votes[i] = (member.predict_proba(pool_features)[:, 1] >= 0.5).astype(int)
    # Committee disagreement over hard votes: half attack (1) / half benign (0).
    disagreement = _vote_entropy(votes)
    return np.argsort(-disagreement)[:n]


def _vote_entropy(votes: np.ndarray) -> np.ndarray:
    """Committee disagreement over hard votes, as normalized vote entropy.

    votes is (committee_size, n_pool). For each pool row the fraction voting positive
    (class 1) is p; binary entropy H(p) is maximized when the committee is evenly
    split (p = 0.5), regardless of how confident each member is. Entropy is normalized
    by log(2) so it lies in [0, 1].
    """
    p = votes.mean(axis=0)
    p = np.clip(p, ENTROPY_EPS, 1 - ENTROPY_EPS)
    entropy = -(p * np.log(p) + (1 - p) * np.log(1 - p))
    return entropy / np.log(2)


def _diversity_queries(features: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Representativeness sampling via k-means cluster centers (farthest-first from seeds).

    A practical stand-in for diversity-based active learning: cluster the unlabeled
    pool and label the rows closest to each cluster center, so the query draws from
    distinct regions rather than one borderline band. Uses a deterministic init to
    keep results reproducible per seed.
    """
    from sklearn.cluster import KMeans

    k = min(DIVERSITY_CLUSTERS, n, len(features))
    if k <= 1:
        return rng.choice(len(features), size=n, replace=False)
    model = KMeans(n_clusters=k, random_state=int(rng.integers(0, 2**31 - 1)), n_init=2)
    model.fit(features)
    queries: list[int] = []
    centers = model.cluster_centers_
    # Farthest-first: pick the row nearest each center, iterating to avoid repeats.
    remaining = np.arange(len(features))
    for center in centers:
        if len(queries) >= n:
            break
        dist = np.linalg.norm(features[remaining] - center, axis=1)
        nearest_global = remaining[np.argmin(dist)]
        queries.append(int(nearest_global))
        remaining = remaining[remaining != nearest_global]
        if len(remaining) == 0:
            break
    # Fill any shortfall randomly (e.g. fewer cluster centers than requested).
    while len(queries) < n and len(remaining) > 0:
        idx = int(rng.choice(len(remaining)))
        queries.append(int(remaining[idx]))
        remaining = np.delete(remaining, idx)
    return np.asarray(queries, dtype=int)


def _seed_labels(y_train: np.ndarray, seed_size: int, rng: np.random.Generator) -> np.ndarray:
    """Pick a starting labeled set that contains both classes."""
    positive = np.where(y_train == 1)[0]
    negative = np.where(y_train == 0)[0]
    if len(positive) < 1 or len(negative) < 1:
        raise ValueError("Seed labels require at least one row of each class in the training fold.")
    take = min(seed_size // 2, len(positive), len(negative))
    chosen = np.concatenate([rng.choice(positive, size=take, replace=False), rng.choice(negative, size=take, replace=False)])
    return chosen


def run_fold(features, truth, train_idx, test_idx, strategy, seed_size, batch_size, budget, random_state) -> Dict[str, float]:
    x_train, x_test = features[train_idx], features[test_idx]
    y_train, y_test = truth[train_idx], truth[test_idx]
    rng = np.random.default_rng(random_state)

    labeled = _seed_labels(y_train, seed_size, rng)
    labeled = np.asarray(labeled, dtype=int)
    unlabeled_mask = np.ones(len(y_train), dtype=bool)
    unlabeled_mask[labeled] = False

    result: Dict[str, float] = {}
    while len(labeled) <= budget and unlabeled_mask.any():
        model = _make_model()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train[labeled], y_train[labeled])
        f1 = f1_score(y_test, model.predict(x_test), zero_division=0)
        result[len(labeled)] = round(float(f1), 4)

        remaining = np.where(unlabeled_mask)[0]
        probabilities = model.predict_proba(x_train[remaining])[:, 1]
        next_size = min(batch_size, budget - len(labeled))
        if next_size <= 0:
            break
        queries = select_queries(
            probabilities, next_size, strategy, rng,
            pool_features=x_train[remaining],
            labeled_pool=(x_train[labeled], y_train[labeled]),
        )
        chosen = remaining[queries]
        labeled = np.concatenate([labeled, chosen])
        unlabeled_mask[chosen] = False

    return result


def run(features, truth, folds, seed_size, batch_size, budget, random_state, strategies=STRATEGIES) -> Dict[str, Dict[int, Dict[str, float]]]:
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    per_strategy: Dict[str, Dict[int, List[float]]] = {strategy: {} for strategy in strategies}
    for train_idx, test_idx in splitter.split(features, truth):
        for strategy in strategies:
            fold_result = run_fold(features, truth, train_idx, test_idx, strategy, seed_size, batch_size, budget, random_state)
            for label_count, f1 in fold_result.items():
                per_strategy[strategy].setdefault(label_count, []).append(f1)

    averaged: Dict[str, Dict[int, Dict[str, float]]] = {}
    for strategy, counts in per_strategy.items():
        averaged[strategy] = {}
        for count, scores in sorted(counts.items()):
            averaged[strategy][count] = {
                "f1_mean": round(float(np.mean(scores)), 4),
                "f1_std": round(float(np.std(scores)), 4),
            }
    return averaged


def save_metrics(results: Dict[str, Dict[int, Dict[str, float]]], path: Path, unsupervised_ref: float, supervised_ref: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "unsupervised_ensemble_f1": unsupervised_ref,
        "fully_supervised_f1": supervised_ref,
        "strategies": {
            strategy: [{"labels": count, **scores} for count, scores in counts.items()]
            for strategy, counts in results.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plot_curves(results: Dict[str, Dict[int, Dict[str, float]]], path: Path, unsupervised_ref: float, supervised_ref: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    palette = {"random": "#e76f51", "uncertainty": "#2a9d8f",
               "margin": "#6a4c93", "entropy": "#f4a261", "diversity": "#457b9d"}
    for strategy, scores in results.items():
        counts = list(scores.keys())
        f1s = [scores[c]["f1_mean"] for c in counts]
        ax.plot(counts, f1s, "o-", color=palette.get(strategy, "#333"), label=f"{strategy} sampling")
    ax.axhline(supervised_ref, color="#264653", ls=":", lw=1.5, label=f"Fully supervised ({supervised_ref:.2f})")
    ax.axhline(unsupervised_ref, color="#c1121f", ls=":", lw=1.5, label=f"Unsupervised ensemble ({unsupervised_ref:.2f})")
    ax.set_xlabel("Number of labeled flows (budget)")
    ax.set_ylabel("F1 score (5-fold CV)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Query strategies under a label budget")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def print_summary(
    results: Dict[str, Dict[int, Dict[str, float]]],
    unsupervised_ref: float,
    supervised_ref: float,
) -> None:
    strategies = list(results.keys())
    counts = sorted(next(iter(results.values())).keys())
    header = f"{'labels':>8}" + "".join(f"{s:>14}" for s in strategies)
    print(header)
    for count in counts:
        cells = []
        for s in strategies:
            cells.append(f"{results[s][count]['f1_mean']:>8.3f}±{results[s][count]['f1_std']:.3f}")
        print(f"{count:>8}" + "".join(cells))
    print(f"\nreference  unsupervised ensemble F1 = {unsupervised_ref:.2f}"
          f"   fully supervised F1 = {supervised_ref:.2f}")


def main() -> None:
    args = build_parser().parse_args()
    features, truth = load_labeled(Path(args.input), args.label_column)
    print(f"Loaded {len(truth)} rows, {int(truth.sum())} attacks.\n")
    results = run(features, truth, args.folds, args.seed_size, args.batch_size, args.budget, args.random_state, args.strategies)
    save_metrics(results, Path(args.metrics_output), args.unsupervised_reference, args.supervised_reference)
    plot_curves(results, Path(args.plot), args.unsupervised_reference, args.supervised_reference)
    print_summary(results, args.unsupervised_reference, args.supervised_reference)
    print(f"\nMetrics -> {args.metrics_output}")
    print(f"Plot    -> {args.plot}")


if __name__ == "__main__":
    main()
