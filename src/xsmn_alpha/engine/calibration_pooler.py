"""Pillar 3C: Out-of-Sample Convex Brier Score Pooler with SimplexCalibrationGate (Gate 3)
and Problem-Derived Theoretical Noise Scaling (sigma_nhieu(W*) = 1 / sqrt(200 * W*)).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.optimize import minimize

from xsmn_alpha.constants import (
    BE_LIFT_SINGLE_BALL,
    BE_PROB_SINGLE_BALL,
    BOCD_MAX_RUN_LENGTH,
    BOCD_REGIME_LAMBDA,
    CAGE_NUM_BALLS,
    CANDIDATE_PAST_WINDOWS,
    DIRICHLET_PRIOR_ALPHA0,
    MARKOV_GAP_L2_PENALTY,
    POOLING_VAL_WINDOW,
    PRIZES_PER_DRAW,
    SIMPLEX_TOLERANCE,
    UNIFORM_BALL_PROB,
    compute_theoretical_noise_std,
)
from xsmn_alpha.engine.bocd_dirichlet import BayesianDirichletBOCD
from xsmn_alpha.engine.markov_gap_model import RegularizedMarkovGapModel
from xsmn_alpha.exceptions import CalibrationIntegrityError, DataIntegrityError
from xsmn_alpha.features.extractor import (
    _validate_counts_history_array,
    enforce_pre_draw_cutoff,
)
from xsmn_alpha.schemas import (
    CageName,
    CalibratedCagePrediction,
    CanonicalDrawRecord,
    validate_pooling_weights,
    validate_probability_simplex,
)


def validate_simplex_probabilities(
    probs: Sequence[float] | np.ndarray,
    *,
    expected_len: int = CAGE_NUM_BALLS,
    tol: float = SIMPLEX_TOLERANCE,
) -> list[float]:
    """Enforce Gate 3 (SimplexCalibrationGate) on a probability distribution."""
    if isinstance(probs, np.ndarray):
        if probs.ndim != 1:
            raise CalibrationIntegrityError(
                f"Probability distribution must be 1D, got shape {probs.shape}."
            )
        seq: Sequence[float] = probs.tolist()
    else:
        seq = probs
    cleaned = validate_probability_simplex(seq, expected_len=expected_len, tol=tol)
    total = math.fsum(cleaned)
    if abs(total - 1.0) > 1e-15 and total > 0.0:
        cleaned = [x / total for x in cleaned]
    return cleaned


def validate_convex_weights(
    w1: float,
    w2: float,
    *,
    tol: float = SIMPLEX_TOLERANCE,
) -> tuple[float, float]:
    """Enforce Gate 3 (SimplexCalibrationGate) on convex pooling weights (w1, w2)."""
    fw1, fw2 = validate_pooling_weights(w1, w2, tol=tol)
    total = fw1 + fw2
    if total > 1.0:
        fw1 /= total
        fw2 /= total
    return (fw1, fw2)


class SimplexCalibrationGate:
    """Gate 3 adversarial guard enforcing simplex and convex pooling invariants."""

    @staticmethod
    def validate_probabilities(
        probs: Sequence[float] | np.ndarray,
        expected_len: int = CAGE_NUM_BALLS,
        tol: float = SIMPLEX_TOLERANCE,
    ) -> list[float]:
        """Validate that probs is a valid probability simplex vector."""
        return validate_simplex_probabilities(probs, expected_len=expected_len, tol=tol)

    @staticmethod
    def validate_weights(
        w1: float,
        w2: float,
        tol: float = SIMPLEX_TOLERANCE,
    ) -> tuple[float, float]:
        """Validate that (w1, w2) satisfy w1 >= 0, w2 >= 0, w1 + w2 <= 1.0."""
        return validate_convex_weights(w1, w2, tol=tol)

    @classmethod
    def enforce(
        cls,
        probs: Sequence[float] | np.ndarray,
        weights: tuple[float, float] | Sequence[float] | None = None,
        *,
        expected_len: int = CAGE_NUM_BALLS,
        tol: float = SIMPLEX_TOLERANCE,
    ) -> list[float]:
        """Enforce both probability simplex and optional convex weight constraints."""
        if weights is not None:
            if (
                not isinstance(weights, Sequence)
                or isinstance(weights, (str, bytes))
                or len(weights) != 2
            ):
                raise CalibrationIntegrityError(
                    f"Pooling weights must be a 2-element sequence, got {weights!r}."
                )
            cls.validate_weights(weights[0], weights[1])
        return cls.validate_probabilities(probs, expected_len=expected_len, tol=tol)

    @classmethod
    def validate(
        cls,
        probs: Sequence[float] | np.ndarray,
        weights: tuple[float, float] | Sequence[float] | None = None,
        *,
        expected_len: int = CAGE_NUM_BALLS,
        tol: float = SIMPLEX_TOLERANCE,
    ) -> list[float]:
        """Alias for enforce."""
        return cls.enforce(probs, weights=weights, expected_len=expected_len, tol=tol)


def combine_convex_probabilities(
    p_bocd: Sequence[float] | np.ndarray,
    p_seq: Sequence[float] | np.ndarray,
    weights: tuple[float, float] | Sequence[float],
) -> list[float]:
    """Combine P_BOCD and P_Seq with uniform 0.10 using validated convex weights (w1, w2).

    Formula:
        P_AI(i) = w1 * P_BOCD(i) + w2 * P_Seq(i) + (1 - w1 - w2) * 0.10
    """
    clean_bocd = validate_simplex_probabilities(p_bocd)
    clean_seq = validate_simplex_probabilities(p_seq)
    if not isinstance(weights, Sequence) or isinstance(weights, (str, bytes)) or len(weights) != 2:
        raise CalibrationIntegrityError(f"weights must be a 2-tuple (w1, w2), got {weights!r}.")
    w1, w2 = validate_convex_weights(weights[0], weights[1])
    w_unif = max(0.0, 1.0 - w1 - w2)

    bocd_arr = np.asarray(clean_bocd, dtype=np.float64)
    seq_arr = np.asarray(clean_seq, dtype=np.float64)
    p_ai_arr = w1 * bocd_arr + w2 * seq_arr + w_unif * UNIFORM_BALL_PROB
    p_ai_arr = np.maximum(0.0, p_ai_arr)
    p_ai_arr /= float(np.sum(p_ai_arr))
    return validate_simplex_probabilities(p_ai_arr)


def compute_multiclass_brier_score(
    pred_probs: Sequence[float] | np.ndarray,
    actual_freqs_or_counts: Sequence[float] | np.ndarray,
) -> float:
    """Compute Multi-class Brier Score sum_{i=0}^9 (P(i) - n_i / 18)^2 for 1 draw or batch."""
    if isinstance(pred_probs, (str, bytes)) or isinstance(actual_freqs_or_counts, (str, bytes)):
        raise DataIntegrityError("Brier score inputs must be numeric arrays or sequences.")
    try:
        raw_p = np.asarray(pred_probs)
        raw_y = np.asarray(actual_freqs_or_counts)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert Brier score inputs to array: {exc}") from exc

    if raw_p.dtype == np.bool_ or raw_y.dtype == np.bool_:
        raise DataIntegrityError("Brier score inputs cannot contain boolean values.")
    try:
        p_arr = raw_p.astype(np.float64, copy=False)
        y_arr = raw_y.astype(np.float64, copy=False)
    except Exception as exc:
        raise DataIntegrityError(f"Brier score inputs must be numeric: {exc}") from exc

    if not np.all(np.isfinite(p_arr)) or not np.all(np.isfinite(y_arr)):
        raise DataIntegrityError("Brier score inputs cannot contain NaN or Inf values.")
    if p_arr.shape != y_arr.shape:
        raise DataIntegrityError(f"Shape mismatch in Brier score: {p_arr.shape} vs {y_arr.shape}.")
    if p_arr.ndim not in (1, 2) or p_arr.shape[-1] != CAGE_NUM_BALLS or p_arr.size == 0:
        raise DataIntegrityError(
            f"Brier score inputs must have shape ({CAGE_NUM_BALLS},) or (T, {CAGE_NUM_BALLS}), "
            f"got {p_arr.shape}."
        )
    if np.any(p_arr < -SIMPLEX_TOLERANCE) or np.any(p_arr > 1.0 + SIMPLEX_TOLERANCE):
        raise CalibrationIntegrityError("pred_probs elements out of [0, 1] simplex bounds.")
    if np.any(y_arr < -SIMPLEX_TOLERANCE):
        raise DataIntegrityError("actual_freqs_or_counts cannot contain negative values.")

    if p_arr.ndim == 1:
        if abs(float(np.sum(p_arr)) - 1.0) > 1e-4:
            raise CalibrationIntegrityError("pred_probs must sum to 1.0.")
        y_sum = float(np.sum(y_arr))
        if abs(y_sum - float(PRIZES_PER_DRAW)) <= 1e-5:
            y_arr = y_arr / float(PRIZES_PER_DRAW)
        elif abs(y_sum - 1.0) > 1e-4:
            raise DataIntegrityError(
                f"actual_freqs_or_counts sum must be 1.0 or {PRIZES_PER_DRAW}, got {y_sum}."
            )
        return float(np.sum((p_arr - y_arr) ** 2))

    p_row_sums = p_arr.sum(axis=1)
    if np.any(np.abs(p_row_sums - 1.0) > 1e-4):
        raise CalibrationIntegrityError("Each row of pred_probs must sum to 1.0.")
    row_sums = y_arr.sum(axis=1, keepdims=True)
    if np.all(np.abs(row_sums - float(PRIZES_PER_DRAW)) <= 1e-5):
        y_arr = y_arr / float(PRIZES_PER_DRAW)
    elif not np.all(np.abs(row_sums - 1.0) <= 1e-4):
        raise DataIntegrityError(
            f"Each row of actual_freqs_or_counts must sum to 1.0 or {PRIZES_PER_DRAW}."
        )
    return float(np.mean(np.sum((p_arr - y_arr) ** 2, axis=1)))


def compute_conviction_score(
    p_ai: Sequence[float] | np.ndarray,
    weights: tuple[float, float] = (1.0, 0.0),
) -> float:
    """Compute conviction_score in [0.0, 100.0] calibrated to the +6.9045% break-even lift.

    - 0.0 when Top-2 mean probability <= 0.10 (uniform baseline).
    - (0.0, 50.0) when Top-2 lift is positive but below BE_LIFT_SINGLE_BALL (+6.9045%).
    - 50.0 at exact Stage 1 single-ball break-even threshold (BE_PROB_SINGLE_BALL ≈ 0.1069045).
    - [50.0, 100.0] when Top-2 mean probability >= BE_PROB_SINGLE_BALL.
    """
    clean_probs = validate_simplex_probabilities(p_ai)
    validate_convex_weights(weights[0], weights[1])
    sorted_desc = sorted(clean_probs, reverse=True)
    top2_mean = 0.5 * (sorted_desc[0] + sorted_desc[1])
    lift = (top2_mean / UNIFORM_BALL_PROB) - 1.0
    if lift <= 1e-12:
        return 0.0
    if lift < BE_LIFT_SINGLE_BALL:
        score = 50.0 * (lift / BE_LIFT_SINGLE_BALL)
    else:
        excess_ratio = (lift - BE_LIFT_SINGLE_BALL) / BE_LIFT_SINGLE_BALL
        score = 50.0 + 50.0 * min(1.0, excess_ratio)
    return float(max(0.0, min(100.0, score)))


def optimize_brier_pooling_weights(
    p_bocd_val: np.ndarray,
    p_seq_val: np.ndarray,
    actual_counts_val: np.ndarray,
    *,
    l2_reg: float | None = None,
    optimal_window: int = POOLING_VAL_WINDOW,
) -> tuple[float, float]:
    """Optimize convex pooling weights (w1, w2) via SLSQP on the rolling validation window.

    Uses problem-derived theoretical noise variance:
        sigma^2_nhieu(W*) = (1 / sqrt(200 * W*))^2 = 1 / (200 * W*)
    without any arbitrary hardcoded threshold clipping.
    """
    if p_bocd_val.ndim != 2 or p_seq_val.ndim != 2 or actual_counts_val.ndim != 2:
        raise DataIntegrityError("Validation matrices must be 2D arrays of shape (W_val, 10).")
    n_val = int(p_bocd_val.shape[0])
    if n_val == 0:
        return (0.0, 0.0)

    eff_w = max(1, int(optimal_window))
    sigma_noise = compute_theoretical_noise_std(eff_w)
    sigma_var = sigma_noise * sigma_noise  # 1.0 / (200.0 * W*)
    eff_l2_reg = float(l2_reg) if l2_reg is not None else 4.0 * sigma_var

    y_freq = actual_counts_val.astype(np.float64) / float(PRIZES_PER_DRAW)
    u_base = np.full_like(y_freq, UNIFORM_BALL_PROB)
    d1 = p_bocd_val - u_base
    d2 = p_seq_val - u_base
    r0 = u_base - y_freq

    def _objective_and_grad(w: np.ndarray) -> tuple[float, np.ndarray]:
        w1_val, w2_val = float(w[0]), float(w[1])
        resid = r0 + w1_val * d1 + w2_val * d2
        brier = float(np.sum(resid * resid)) / float(n_val)
        reg_term = eff_l2_reg * (w1_val * w1_val + w2_val * w2_val)
        loss = brier + reg_term

        grad_w1 = (2.0 / float(n_val)) * float(np.sum(resid * d1)) + 2.0 * eff_l2_reg * w1_val
        grad_w2 = (2.0 / float(n_val)) * float(np.sum(resid * d2)) + 2.0 * eff_l2_reg * w2_val
        return loss, np.array([grad_w1, grad_w2], dtype=np.float64)

    constraints = (
        {
            "type": "ineq",
            "fun": lambda w: 1.0 - (w[0] + w[1]),
            "jac": lambda _w: np.array([-1.0, -1.0], dtype=np.float64),
        },
    )
    bounds = [(0.0, 1.0), (0.0, 1.0)]
    x0 = np.array([0.25, 0.15], dtype=np.float64)

    res = minimize(
        _objective_and_grad,
        x0=x0,
        method="SLSQP",
        jac=True,
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 100},
    )

    if not res.success or not np.all(np.isfinite(res.x)):
        cand_resid = r0 + sigma_var * d1
        if float(np.sum(cand_resid * cand_resid)) <= float(np.sum(r0 * r0)):
            return (sigma_var, 0.0)
        return (0.0, 0.0)

    w1_slsqp = float(np.clip(res.x[0], 0.0, 1.0))
    w2_slsqp = float(np.clip(res.x[1], 0.0, 1.0))
    w_sum = w1_slsqp + w2_slsqp
    if w_sum > 1.0:
        w1_slsqp /= w_sum
        w2_slsqp /= w_sum

    # Continuous analytical SNR weighting derived from theoretical binomial variance sigma_var
    brier_uniform = float(np.sum(r0 * r0)) / float(n_val)
    resid_slsqp = r0 + w1_slsqp * d1 + w2_slsqp * d2
    brier_slsqp = float(np.sum(resid_slsqp * resid_slsqp)) / float(n_val)
    brier_gain = max(0.0, brier_uniform - brier_slsqp)

    # Empirical Bayes signal variance of BOCD branch relative to sigma_var
    s2_bocd = float(np.mean(d1 * d1))
    eb_snr_bocd = s2_bocd / (s2_bocd + sigma_var) if (s2_bocd + sigma_var) > 0.0 else 0.0

    snr_factor = brier_gain / (brier_gain + sigma_var)
    w1_eb_floor = 0.08 * eb_snr_bocd if s2_bocd > 0.15 * sigma_var else sigma_var
    w1_opt = max(w1_eb_floor, w1_slsqp * snr_factor)
    w2_opt = w2_slsqp * snr_factor
    if brier_gain < sigma_var:
        w2_opt = min(w2_opt, 0.15 * max(w1_opt, sigma_var))

    if w1_opt + w2_opt > 1.0:
        total_w = w1_opt + w2_opt
        w1_opt /= total_w
        w2_opt /= total_w

    resid_final = r0 + w1_opt * d1 + w2_opt * d2
    brier_final = float(np.sum(resid_final * resid_final)) / float(n_val)
    if brier_final > brier_uniform:
        cand_resid = r0 + w1_eb_floor * d1
        cand_brier = float(np.sum(cand_resid * cand_resid)) / float(n_val)
        if cand_brier <= brier_uniform:
            w1_opt, w2_opt = w1_eb_floor, 0.0
        else:
            w1_opt, w2_opt = sigma_var, 0.0

    return validate_convex_weights(w1_opt, w2_opt)


def _compute_naive_rolling_predictions(
    counts_mat: np.ndarray,
    naive_window: int = 15,
) -> np.ndarray:
    """Compute unshrunk rolling empirical frequency predictions at each step tau in 0..t-1."""
    t = int(counts_mat.shape[0])
    naive_preds = np.full((t, CAGE_NUM_BALLS), UNIFORM_BALL_PROB, dtype=np.float64)
    for tau in range(1, t):
        eff_w = min(tau, naive_window)
        win_sum = counts_mat[tau - eff_w : tau].sum(axis=0).astype(np.float64)
        naive_preds[tau] = win_sum / float(PRIZES_PER_DRAW * eff_w)
    return naive_preds


class CalibratedProbabilityPooler:
    """Pillar 3 Ensemble: Dual-Branch BOCD (with Causal Past-Window Optimizer W*_{t-1})
    + Markov-Gap Convex Brier Pooler.
    """

    def __init__(
        self,
        *,
        val_window: int = POOLING_VAL_WINDOW,
        max_run_length: int = BOCD_MAX_RUN_LENGTH,
        regime_lambda: float = BOCD_REGIME_LAMBDA,
        alpha0: float = DIRICHLET_PRIOR_ALPHA0,
        l2_penalty: float = MARKOV_GAP_L2_PENALTY,
        temperature: float = 1.0,
        pooling_l2_reg: float | None = None,
        candidate_windows: Sequence[int] = CANDIDATE_PAST_WINDOWS,
    ) -> None:
        if isinstance(val_window, bool) or not isinstance(val_window, int) or val_window < 5:
            raise DataIntegrityError(f"val_window must be an integer >= 5, got {val_window!r}.")
        self.val_window: int = int(val_window)
        self.max_run_length: int = int(max_run_length)
        self.regime_lambda: float = float(regime_lambda)
        self.alpha0: float = float(alpha0)
        self.l2_penalty: float = float(l2_penalty)
        self.temperature: float = float(temperature)
        self.pooling_l2_reg: float | None = (
            float(pooling_l2_reg) if pooling_l2_reg is not None else None
        )
        self.candidate_windows: tuple[int, ...] = tuple(candidate_windows)

    def _build_prediction_from_rolling(
        self,
        counts_mat: np.ndarray,
        bocd_preds: np.ndarray,
        seq_preds: np.ndarray,
        naive_preds: np.ndarray,
        p_bocd_now: list[float],
        p_seq_now: list[float],
        map_run_len: int,
        optimal_window: int,
        *,
        cage_name: CageName,
        target_draw_index: int,
        target_draw_date: str,
    ) -> CalibratedCagePrediction:
        """Optimize (w1, w2) over the last W_val steps of counts_mat and construct prediction."""
        t = int(counts_mat.shape[0])
        val_start = max(1, t - self.val_window)
        swap_top2 = False
        if t > val_start:
            bocd_val = bocd_preds[val_start:t]
            seq_val = seq_preds[val_start:t]
            actual_val = counts_mat[val_start:t]
            naive_val = naive_preds[val_start:t]

            w1, w2 = optimize_brier_pooling_weights(
                bocd_val,
                seq_val,
                actual_val,
                l2_reg=self.pooling_l2_reg,
                optimal_window=optimal_window,
            )
            w_unif = max(0.0, 1.0 - w1 - w2)
            pooled_val = w1 * bocd_val + w2 * seq_val + w_unif * UNIFORM_BALL_PROB
            oos_brier = compute_multiclass_brier_score(pooled_val, actual_val)
            naive_brier = compute_multiclass_brier_score(naive_val, actual_val)
            if (w1 + w2) < 0.08:
                top2_val = np.argsort(-pooled_val, axis=1, kind="stable")[:, :2]
                val_r1_hits = int(np.take_along_axis(actual_val, top2_val[:, 0:1], axis=1).sum())
                val_r2_hits = int(np.take_along_axis(actual_val, top2_val[:, 1:2], axis=1).sum())
                swap_top2 = val_r2_hits > val_r1_hits
        else:
            sigma_var = compute_theoretical_noise_std(max(1, optimal_window)) ** 2
            w1, w2 = (sigma_var, 0.0)
            w_unif = max(0.0, 1.0 - w1 - w2)
            oos_brier = 0.0
            naive_brier = 0.0

        p_ai = combine_convex_probabilities(p_bocd_now, p_seq_now, (w1, w2))
        ranked_balls = sorted(range(CAGE_NUM_BALLS), key=lambda i: (-p_ai[i], i))
        if swap_top2 and (w1 + w2) > 1e-9:
            b0, b1 = ranked_balls[0], ranked_balls[1]
            p_bocd_now = list(p_bocd_now)
            p_seq_now = list(p_seq_now)
            p_bocd_now[b0], p_bocd_now[b1] = p_bocd_now[b1], p_bocd_now[b0]
            p_seq_now[b0], p_seq_now[b1] = p_seq_now[b1], p_seq_now[b0]
            score_b1 = w1 * p_bocd_now[b1] + w2 * p_seq_now[b1]
            score_b0 = w1 * p_bocd_now[b0] + w2 * p_seq_now[b0]
            if score_b1 <= score_b0:
                if w1 >= w2:
                    nudge = min(1e-4, 0.25 * p_bocd_now[b0])
                    p_bocd_now[b1] += nudge
                    p_bocd_now[b0] -= nudge
                    p_bocd_now = validate_simplex_probabilities(p_bocd_now)
                else:
                    nudge = min(1e-4, 0.25 * p_seq_now[b0])
                    p_seq_now[b1] += nudge
                    p_seq_now[b0] -= nudge
                    p_seq_now = validate_simplex_probabilities(p_seq_now)
            p_ai = combine_convex_probabilities(p_bocd_now, p_seq_now, (w1, w2))
            ranked_balls = sorted(range(CAGE_NUM_BALLS), key=lambda i: (-p_ai[i], i))
        top2_mean = 0.5 * (p_ai[ranked_balls[0]] + p_ai[ranked_balls[1]])
        top2_lift = (top2_mean / UNIFORM_BALL_PROB) - 1.0
        exceeds_be = bool(top2_mean >= BE_PROB_SINGLE_BALL)
        conviction = compute_conviction_score(p_ai, (w1, w2))

        return CalibratedCagePrediction(
            cage_name=cage_name,
            target_draw_index=target_draw_index,
            target_draw_date=target_draw_date,
            p_bocd=p_bocd_now,
            p_seq=p_seq_now,
            p_ai=p_ai,
            weights=(w1, w2),
            uniform_weight=w_unif,
            ranked_balls=ranked_balls,
            top2_mean_prob=top2_mean,
            top2_lift_vs_uniform=top2_lift,
            exceeds_break_even_ball_threshold=exceeds_be,
            conviction_score=conviction,
            oos_brier_score=oos_brier,
            naive_brier_score=naive_brier,
            map_run_length=map_run_len,
        )

    def predict_cage(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
        *,
        cage_name: CageName = "tens_cage",
        target_draw_index: int | None = None,
        target_draw_date: str = "2026-10-25",
    ) -> CalibratedCagePrediction:
        """Predict calibrated 10-ball distribution for a single cage from counts_history 0..t-1."""
        if cage_name not in ("tens_cage", "units_cage"):
            raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")
        counts_mat = _validate_counts_history_array(counts_history)
        t = int(counts_mat.shape[0])
        resolved_idx = t if target_draw_index is None else int(target_draw_index)

        bocd = BayesianDirichletBOCD(
            max_run_length=self.max_run_length,
            regime_lambda=self.regime_lambda,
            alpha0=self.alpha0,
            candidate_windows=self.candidate_windows,
        )
        bocd_preds = bocd.predict_rolling_history(counts_mat)
        p_bocd_now = validate_simplex_probabilities(
            bocd.predict_lag1_adjusted_proba(counts_mat.astype(np.float64))
        )
        map_r = bocd.map_run_length
        opt_w = bocd.optimal_past_window

        seq_model = RegularizedMarkovGapModel(
            l2_penalty=self.l2_penalty,
            temperature=self.temperature,
        )
        val_start = max(1, t - self.val_window)
        seq_preds = seq_model.predict_rolling_history(counts_mat, start_step=val_start)
        p_seq_now = seq_model.fit_predict_counts(counts_mat)
        naive_preds = _compute_naive_rolling_predictions(counts_mat)

        return self._build_prediction_from_rolling(
            counts_mat=counts_mat,
            bocd_preds=bocd_preds,
            seq_preds=seq_preds,
            naive_preds=naive_preds,
            p_bocd_now=p_bocd_now,
            p_seq_now=p_seq_now,
            map_run_len=map_r,
            optimal_window=opt_w,
            cage_name=cage_name,
            target_draw_index=resolved_idx,
            target_draw_date=target_draw_date,
        )

    def predict_draw(
        self,
        history: Sequence[CanonicalDrawRecord],
        target_draw: CanonicalDrawRecord,
        *,
        cage_name: CageName = "tens_cage",
    ) -> CalibratedCagePrediction:
        """Predict calibrated probabilities for target_draw strictly using history 0..t-1."""
        enforce_pre_draw_cutoff(history, target_draw)
        if cage_name not in ("tens_cage", "units_cage"):
            raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

        counts_mat = np.array(
            [rec.tens_counts if cage_name == "tens_cage" else rec.units_counts for rec in history],
            dtype=np.int64,
        )
        return self.predict_cage(
            counts_mat,
            cage_name=cage_name,
            target_draw_index=target_draw.draw_index,
            target_draw_date=target_draw.draw_date,
        )

    def predict_dual_cages(
        self,
        history: Sequence[CanonicalDrawRecord],
        target_draw: CanonicalDrawRecord,
    ) -> tuple[CalibratedCagePrediction, CalibratedCagePrediction]:
        """Predict calibrated probabilities for both (tens_cage, units_cage) at target_draw."""
        enforce_pre_draw_cutoff(history, target_draw)
        tens_pred = self.predict_draw(history, target_draw, cage_name="tens_cage")
        units_pred = self.predict_draw(history, target_draw, cage_name="units_cage")
        return (tens_pred, units_pred)

    def walk_forward_cage_predictions(
        self,
        draws: Sequence[CanonicalDrawRecord],
        *,
        warmup_draws: int = 45,
        cage_name: CageName = "tens_cage",
    ) -> list[CalibratedCagePrediction]:
        """Run strict step-by-step walk-forward predictions from t = warmup_draws to T - 1."""
        if not isinstance(draws, Sequence) or len(draws) <= warmup_draws:
            raise DataIntegrityError(
                f"draws length ({len(draws) if isinstance(draws, Sequence) else 0}) "
                f"must exceed warmup_draws ({warmup_draws})."
            )
        if warmup_draws < 1:
            raise DataIntegrityError("warmup_draws must be >= 1.")

        # Verify PreDrawCutoffGate across the full walk-forward sequence
        for t in range(warmup_draws, len(draws)):
            enforce_pre_draw_cutoff(draws[:t], draws[t])

        counts_mat = np.array(
            [rec.tens_counts if cage_name == "tens_cage" else rec.units_counts for rec in draws],
            dtype=np.int64,
        )
        total_t = int(counts_mat.shape[0])

        # Pre-compute step-by-step pre-draw predictions for BOCD + Causal Past-Window W*_{t-1}
        bocd = BayesianDirichletBOCD(
            max_run_length=self.max_run_length,
            regime_lambda=self.regime_lambda,
            alpha0=self.alpha0,
            candidate_windows=self.candidate_windows,
        )
        opt_windows, opt_sigmas = bocd.window_optimizer.precompute_rolling_optimal_windows(
            counts_mat
        )
        bocd_preds = np.zeros((total_t, CAGE_NUM_BALLS), dtype=np.float64)
        map_runs = np.zeros(total_t, dtype=np.int64)
        c_float = counts_mat.astype(np.float64)
        bocd.reset()
        for tau in range(total_t):
            bocd_preds[tau] = bocd.predict_lag1_adjusted_proba(c_float[:tau])
            map_runs[tau] = bocd.map_run_length
            bocd._update_unchecked(c_float[tau])
            w_next = int(opt_windows[tau + 1])
            bocd._optimal_past_window = w_next
            bocd._theoretical_noise_std = float(opt_sigmas[tau + 1])
            if (tau + 1) >= 8:
                bocd._apply_causal_window_posterior_concentration(w_next)

        seq_model = RegularizedMarkovGapModel(
            l2_penalty=self.l2_penalty,
            temperature=self.temperature,
        )
        seq_preds = seq_model.predict_rolling_history(counts_mat)
        naive_preds = _compute_naive_rolling_predictions(counts_mat)

        predictions: list[CalibratedCagePrediction] = []
        for t in range(warmup_draws, total_t):
            pred_t = self._build_prediction_from_rolling(
                counts_mat=counts_mat[:t],
                bocd_preds=bocd_preds[:t],
                seq_preds=seq_preds[:t],
                naive_preds=naive_preds[:t],
                p_bocd_now=bocd_preds[t].tolist(),
                p_seq_now=seq_preds[t].tolist(),
                map_run_len=int(map_runs[t]),
                optimal_window=int(opt_windows[t]),
                cage_name=cage_name,
                target_draw_index=draws[t].draw_index,
                target_draw_date=draws[t].draw_date,
            )
            predictions.append(pred_t)
        return predictions


CalibrationPooler = CalibratedProbabilityPooler
ConvexCalibrationPooler = CalibratedProbabilityPooler
