"""Pillar 2: Statistical Falsification Gatekeeper & Multi-Window Tests."""

from __future__ import annotations

from xsmn_alpha.falsification.gatekeeper import (
    FalsificationGatekeeper,
    classify_cage_gate_status,
    classify_station_overall_status,
    compute_top2_prob_and_lift,
    estimate_dirichlet_calibrated_probs,
    evaluate_cage_falsification,
    evaluate_station_falsification,
)
from xsmn_alpha.falsification.monte_carlo import (
    MonteCarloNullResult,
    compute_empirical_mc_p_value,
    generate_synthetic_cage_history,
    simulate_monte_carlo_null,
)
from xsmn_alpha.falsification.stats_tests import (
    WindowTestResult,
    dirichlet_multinomial_bf10,
    markov_transition_chi_square_test,
    multinomial_chi_square_test,
    normalized_shannon_entropy,
    run_multi_window_tests,
    run_station_multi_window_tests,
    run_window_tests,
    validate_counts_matrix,
    wald_wolfowitz_runs_test,
)

__all__ = [
    "FalsificationGatekeeper",
    "MonteCarloNullResult",
    "WindowTestResult",
    "classify_cage_gate_status",
    "classify_station_overall_status",
    "compute_empirical_mc_p_value",
    "compute_top2_prob_and_lift",
    "dirichlet_multinomial_bf10",
    "estimate_dirichlet_calibrated_probs",
    "evaluate_cage_falsification",
    "evaluate_station_falsification",
    "generate_synthetic_cage_history",
    "markov_transition_chi_square_test",
    "multinomial_chi_square_test",
    "normalized_shannon_entropy",
    "run_multi_window_tests",
    "run_station_multi_window_tests",
    "run_window_tests",
    "simulate_monte_carlo_null",
    "validate_counts_matrix",
    "wald_wolfowitz_runs_test",
]
