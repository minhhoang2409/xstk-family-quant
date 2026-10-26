"""Pillar 3: Dual-Branch Calibrated Probability Engine & SimplexCalibrationGate."""

from __future__ import annotations

from xsmn_alpha.engine.bocd_dirichlet import (
    BayesianDirichletBOCD,
    CausalPastWindowOptimizer,
    optimize_causal_past_window,
    predict_bocd_probabilities,
)
from xsmn_alpha.engine.calibration_pooler import (
    CalibratedProbabilityPooler,
    CalibrationPooler,
    SimplexCalibrationGate,
    combine_convex_probabilities,
    compute_conviction_score,
    compute_multiclass_brier_score,
    optimize_brier_pooling_weights,
    validate_convex_weights,
    validate_simplex_probabilities,
)
from xsmn_alpha.engine.markov_gap_model import (
    RegularizedMarkovGapModel,
    predict_markov_gap_probabilities,
)

__all__ = [
    "BayesianDirichletBOCD",
    "CalibratedProbabilityPooler",
    "CalibrationPooler",
    "CausalPastWindowOptimizer",
    "RegularizedMarkovGapModel",
    "SimplexCalibrationGate",
    "combine_convex_probabilities",
    "compute_conviction_score",
    "compute_multiclass_brier_score",
    "optimize_brier_pooling_weights",
    "optimize_causal_past_window",
    "predict_bocd_probabilities",
    "predict_markov_gap_probabilities",
    "validate_convex_weights",
    "validate_simplex_probabilities",
]
