"""Pillar 4: Walk-Forward Sweet-Spot Portfolio Backtester & Rank-Ordered Alpha Decay."""

from __future__ import annotations

from xsmn_alpha.backtest.alpha_decay import (
    compute_rank_ordered_alpha_decay,
    rank_balls_from_probabilities,
)
from xsmn_alpha.backtest.runner import (
    WalkForwardRunner,
    build_stage3_handoff_contract,
)
from xsmn_alpha.backtest.sweet_spot_sim import (
    compute_19_state_hit_distribution,
    compute_all_portfolio_19_state_distributions,
    compute_portfolio_set_probability,
    evaluate_all_sweet_spot_portfolios,
    evaluate_sweet_spot_portfolio,
    score_single_draw_portfolio,
    select_hybrid_core_satellite_sets,
    select_sweet_spot_numbers,
)

__all__ = [
    "WalkForwardRunner",
    "build_stage3_handoff_contract",
    "compute_19_state_hit_distribution",
    "compute_all_portfolio_19_state_distributions",
    "compute_portfolio_set_probability",
    "compute_rank_ordered_alpha_decay",
    "evaluate_all_sweet_spot_portfolios",
    "evaluate_sweet_spot_portfolio",
    "rank_balls_from_probabilities",
    "score_single_draw_portfolio",
    "select_hybrid_core_satellite_sets",
    "select_sweet_spot_numbers",
]
