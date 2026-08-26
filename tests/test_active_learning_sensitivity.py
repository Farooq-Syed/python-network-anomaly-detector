import numpy as np

import active_learning_sensitivity as sensitivity


def test_summarize_reports_each_budget_and_paired_comparisons():
    trajectories = {
        "random": {10: [0.7, 0.8, 0.6, 0.7], 20: [0.8, 0.9, 0.7, 0.8]},
        "uncertainty": {10: [0.6, 0.7, 0.5, 0.6], 20: [0.7, 0.8, 0.6, 0.7]},
    }
    result = sensitivity.summarize(
        trajectories, budgets=[10, 20], folds=2,
        strategies=["random", "uncertainty"],
    )
    assert set(result) == {"10", "20"}
    assert result["20"]["summary"]["random"]["n_seeds"] == 2
    assert np.isclose(
        result["20"]["random_vs_alternative"]["uncertainty"]["paired_diff_mean"],
        -0.1,
    )
