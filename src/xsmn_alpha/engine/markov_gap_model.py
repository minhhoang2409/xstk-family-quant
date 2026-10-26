"""Pillar 3 Branch 2: Regularized Markov & Gap Multinomial Model (L2 Ridge + Softmax)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.special import logsumexp

from xsmn_alpha.constants import (
    BURST_THRESHOLD_HITS,
    CAGE_NUM_BALLS,
    GAP_MEAN_MU,
    GAP_STD_SIGMA,
    LAPLACE_SMOOTHING_ALPHA,
    MARKOV_ACTIVE_THRESHOLD_HITS,
    MARKOV_GAP_L2_PENALTY,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
)
from xsmn_alpha.exceptions import CalibrationIntegrityError, DataIntegrityError
from xsmn_alpha.features.extractor import (
    CageFeatureVector,
    _validate_counts_history_array,
    enforce_pre_draw_cutoff,
    extract_cage_features,
)
from xsmn_alpha.schemas import (
    CageName,
    CanonicalDrawRecord,
    PreDrawFeatureVector,
    validate_probability_simplex,
)


def _compute_all_step_feature_matrices(counts_mat: np.ndarray) -> np.ndarray:
    """Vectorized computation of pre-draw (10, 4) feature matrices for all prefixes.

    Returns an array X_all of shape (t, 10, 4) where X_all[tau - 1] is the exact (10, 4)
    sequential feature matrix extracted strictly from counts_mat[:tau] (for tau in 1..t).
    """
    t = int(counts_mat.shape[0])
    c_float = counts_mat.astype(np.float64)
    active_mat = (counts_mat >= MARKOV_ACTIVE_THRESHOLD_HITS).astype(np.float64)
    burst_mat = (counts_mat >= BURST_THRESHOLD_HITS).astype(np.float64)

    # 1. Cumulative Markov transitions for every prefix length tau in 1..t
    if t >= 2:
        step_trans = active_mat[:-1, :, None] * c_float[1:, None, :]  # (t-1, 10, 10)
        cum_trans = np.cumsum(step_trans, axis=0)
        cum_active = np.cumsum(active_mat[:-1], axis=0)  # (t-1, 10)

        step_burst_rebound = burst_mat[:-1] * c_float[1:]  # (t-1, 10)
        cum_burst_rebound = np.cumsum(step_burst_rebound, axis=0)
        cum_burst_count = np.cumsum(burst_mat[:-1], axis=0)
    else:
        cum_trans = np.zeros((0, CAGE_NUM_BALLS, CAGE_NUM_BALLS), dtype=np.float64)
        cum_active = np.zeros((0, CAGE_NUM_BALLS), dtype=np.float64)
        cum_burst_rebound = np.zeros((0, CAGE_NUM_BALLS), dtype=np.float64)
        cum_burst_count = np.zeros((0, CAGE_NUM_BALLS), dtype=np.float64)

    # 2. Zero-hit gaps at each prefix end tau - 1
    gaps_all = np.zeros((t, CAGE_NUM_BALLS), dtype=np.float64)
    running_gaps = np.zeros(CAGE_NUM_BALLS, dtype=np.float64)
    for idx in range(t):
        running_gaps = np.where(counts_mat[idx] == 0, running_gaps + 1.0, 0.0)
        gaps_all[idx] = running_gaps
    x_gap_all = (gaps_all - GAP_MEAN_MU) / GAP_STD_SIGMA

    # 3. 10-Draw Deficit Z-scores at each prefix end tau - 1
    csum = np.vstack([np.zeros((1, CAGE_NUM_BALLS), dtype=np.float64), np.cumsum(c_float, axis=0)])
    x_def10_all = np.zeros((t, CAGE_NUM_BALLS), dtype=np.float64)
    for tau in range(1, t + 1):
        eff_10 = min(tau, 10)
        c10 = csum[tau] - csum[tau - eff_10]
        exp_10 = float(PRIZES_PER_DRAW) * (float(eff_10) / 10.0)
        std_10 = math.sqrt(
            float(PRIZES_PER_DRAW * eff_10) * UNIFORM_BALL_PROB * (1.0 - UNIFORM_BALL_PROB)
        )
        x_def10_all[tau - 1] = (exp_10 - c10) / std_10

    # 4. Assemble (t, 10, 4) centered feature tensor
    x_all = np.zeros((t, CAGE_NUM_BALLS, 4), dtype=np.float64)
    for tau in range(1, t + 1):
        idx = tau - 1
        last_counts = c_float[idx]
        active_now = active_mat[idx]
        active_now_sum = float(active_now.sum())

        if tau >= 2:
            trans_num = LAPLACE_SMOOTHING_ALPHA + cum_trans[tau - 2]
            trans_den = (
                float(CAGE_NUM_BALLS) * LAPLACE_SMOOTHING_ALPHA
                + float(PRIZES_PER_DRAW) * cum_active[tau - 2, :, None]
            )
            markov_mat = trans_num / trans_den
        else:
            markov_mat = np.full(
                (CAGE_NUM_BALLS, CAGE_NUM_BALLS), UNIFORM_BALL_PROB, dtype=np.float64
            )

        if active_now_sum > 0.0:
            p_markov = (active_now @ markov_mat) / active_now_sum
        else:
            p_markov = (last_counts / float(PRIZES_PER_DRAW)) @ markov_mat

        x_markov = np.log(np.clip(p_markov, 1e-6, 1.0) / UNIFORM_BALL_PROB)

        burst_ind = burst_mat[idx]
        if tau >= 2 and np.any(burst_ind > 0.0):
            num_bursts = cum_burst_count[tau - 2]
            rebound_hits = cum_burst_rebound[tau - 2]
            burst_rates = (LAPLACE_SMOOTHING_ALPHA + rebound_hits) / (
                float(CAGE_NUM_BALLS) * LAPLACE_SMOOTHING_ALPHA
                + float(PRIZES_PER_DRAW) * num_bursts
            )
            x_burst = burst_ind * (
                1.0 - 0.25 * np.log(np.clip(burst_rates, 1e-6, 1.0) / UNIFORM_BALL_PROB)
            )
        else:
            x_burst = burst_ind.copy()

        mat_tau = np.column_stack([x_markov, x_gap_all[idx], x_def10_all[idx], x_burst])
        mat_tau = mat_tau - mat_tau.mean(axis=0, keepdims=True)
        x_all[idx] = mat_tau

    return x_all


def _features_from_vector(
    feature_vec: PreDrawFeatureVector,
    last_draw_counts: Sequence[int] | np.ndarray | None = None,
) -> np.ndarray:
    """Build the (10, 4) sequential feature matrix from a PreDrawFeatureVector."""
    markov_mat = np.asarray(feature_vec.markov_transition_matrix, dtype=np.float64)
    last_arr: np.ndarray | None = None
    vec_last_counts = getattr(feature_vec, "last_draw_counts", None)
    if last_draw_counts is not None:
        last_arr = np.asarray(last_draw_counts, dtype=np.float64)
        active_now = (last_arr >= float(MARKOV_ACTIVE_THRESHOLD_HITS)).astype(np.float64)
    elif vec_last_counts is not None:
        last_arr = np.asarray(vec_last_counts, dtype=np.float64)
        active_now = (last_arr >= float(MARKOV_ACTIVE_THRESHOLD_HITS)).astype(np.float64)
    elif 5 in feature_vec.regime_counts and feature_vec.history_length == 1:
        last_arr = np.asarray(feature_vec.regime_counts[5], dtype=np.float64)
        active_now = (last_arr >= float(MARKOV_ACTIVE_THRESHOLD_HITS)).astype(np.float64)
    else:
        gaps_arr = np.asarray(feature_vec.zero_hit_gaps, dtype=np.int64)
        burst_arr = np.asarray(feature_vec.burst_rebound_indicators, dtype=np.float64)
        early_arr = np.asarray(feature_vec.session_early_ratios, dtype=np.float64)
        fractional_early = (gaps_arr == 0) & (early_arr > 1e-6) & (early_arr < 1.0 - 1e-6)
        active_now = np.where((burst_arr > 0) | fractional_early, 1.0, 0.0)
        if float(active_now.sum()) == 0.0:
            active_now = np.where(gaps_arr == 0, 1.0, 0.0)

    active_sum = float(active_now.sum())
    if active_sum > 0.0:
        p_markov = (active_now @ markov_mat) / active_sum
    elif last_arr is not None:
        p_markov = (last_arr / float(PRIZES_PER_DRAW)) @ markov_mat
    else:
        p_markov = markov_mat.mean(axis=0)

    x_markov = np.log(np.clip(p_markov, 1e-6, 1.0) / UNIFORM_BALL_PROB)
    x_gap = np.asarray(feature_vec.gap_z_scores, dtype=np.float64)
    x_def10 = np.asarray(feature_vec.deficit_10_z_scores, dtype=np.float64)
    burst_ind = np.asarray(feature_vec.burst_rebound_indicators, dtype=np.float64)
    burst_rates = np.asarray(feature_vec.burst_rebound_rates, dtype=np.float64)
    x_burst = burst_ind * (1.0 - 0.25 * np.log(np.clip(burst_rates, 1e-6, 1.0) / UNIFORM_BALL_PROB))

    feat_mat = np.column_stack([x_markov, x_gap, x_def10, x_burst])
    feat_mat = feat_mat - feat_mat.mean(axis=0, keepdims=True)
    return feat_mat


class RegularizedMarkovGapModel:
    """Branch 2: L2-Regularized First-Order Markov & Gap Multinomial Estimator.

    Combines 1st-order Laplace-smoothed Markov transition probabilities from active balls
    at draw t-1 with standardized gap Z-score, 10-draw deficit Z-score, and lag-1 burst
    exhaustion indicators under strong L2 ridge regularization (lambda_L2 = 10.0) and
    temperature-scaled Softmax (tau_temp >= 1.0) to produce P_Seq(0..9).
    """

    def __init__(
        self,
        *,
        l2_penalty: float = MARKOV_GAP_L2_PENALTY,
        temperature: float = 1.0,
        fit_window: int = 60,
    ) -> None:
        if (
            isinstance(l2_penalty, bool)
            or not isinstance(l2_penalty, (int, float))
            or not math.isfinite(l2_penalty)
            or float(l2_penalty) <= 0.0
        ):
            raise CalibrationIntegrityError(
                f"l2_penalty must be a finite positive float, got {l2_penalty!r}."
            )
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or float(temperature) < 1.0
        ):
            raise CalibrationIntegrityError(
                f"Softmax temperature must be a finite float >= 1.0, got {temperature!r}."
            )
        if isinstance(fit_window, bool) or not isinstance(fit_window, int) or fit_window < 5:
            raise DataIntegrityError(f"fit_window must be an integer >= 5, got {fit_window!r}.")

        self.l2_penalty: float = float(l2_penalty)
        self.temperature: float = float(temperature)
        self.fit_window: int = int(fit_window)
        shrink_factor = 10.0 / (10.0 + self.l2_penalty)
        self._prior_beta = shrink_factor * np.array([0.85, 0.06, 0.06, -0.10], dtype=np.float64)
        self._coef: np.ndarray = self._prior_beta.copy()
        self._last_draw_counts: np.ndarray | None = None
        self._last_history_length: int | None = None
        self._last_regime_w5: list[int] | None = None

    @property
    def coefficients(self) -> np.ndarray:
        """Return a copy of the L2-regularized logit coefficients."""
        return self._coef.copy()

    def _logits_to_simplex_array(self, logits: np.ndarray) -> np.ndarray:
        """Fast internal numpy conversion of 10 raw logit scores to Softmax simplex."""
        centered = logits - float(np.mean(logits))
        scaled = np.clip(centered / self.temperature, -25.0, 25.0)
        log_probs = scaled - float(logsumexp(scaled))
        probs = np.exp(log_probs)
        probs = np.maximum(1e-12, probs)
        probs /= float(np.sum(probs))
        return probs

    def _logits_to_simplex(self, logits: np.ndarray) -> list[float]:
        """Convert 10 raw logit scores into a temperature-scaled Softmax simplex vector."""
        if logits.shape != (CAGE_NUM_BALLS,) or not np.all(np.isfinite(logits)):
            raise CalibrationIntegrityError(
                "Invalid non-finite logits in RegularizedMarkovGapModel."
            )
        probs = self._logits_to_simplex_array(logits)
        return validate_probability_simplex(probs.tolist(), expected_len=CAGE_NUM_BALLS)

    def predict_from_features(
        self,
        feature_vec: PreDrawFeatureVector | CageFeatureVector,
        *,
        last_draw_counts: Sequence[int] | np.ndarray | None = None,
    ) -> list[float]:
        """Predict P_Seq(0..9) from an already extracted PreDrawFeatureVector at t-1."""
        if not isinstance(feature_vec, PreDrawFeatureVector):
            raise DataIntegrityError(
                f"Expected PreDrawFeatureVector, got {type(feature_vec).__name__}."
            )
        resolved_last = last_draw_counts
        if (
            resolved_last is None
            and getattr(feature_vec, "last_draw_counts", None) is None
            and self._last_draw_counts is not None
            and feature_vec.history_length == self._last_history_length
            and (
                5 not in feature_vec.regime_counts
                or list(feature_vec.regime_counts[5]) == self._last_regime_w5
            )
        ):
            resolved_last = self._last_draw_counts
        feat_mat = _features_from_vector(feature_vec, last_draw_counts=resolved_last)
        logits = feat_mat @ self._coef
        return self._logits_to_simplex(logits)

    def _fit_beta_for_step(
        self,
        x_all: np.ndarray,
        y_all: np.ndarray,
        t: int,
    ) -> np.ndarray:
        """Fit L2-penalized ridge coefficients strictly on steps < t."""
        shrink_factor = 10.0 / (10.0 + self.l2_penalty)
        if t < 4:
            return self._prior_beta.copy()

        start_tau = max(2, t - self.fit_window)
        # At transition tau (in start_tau .. t-1), features are x_all[tau - 1]
        x_design = x_all[start_tau - 1 : t - 1].reshape(-1, 4)
        y_target = y_all[start_tau:t].reshape(-1)
        n_samples = float(x_design.shape[0])
        ridge_reg = self.l2_penalty * max(1.0, n_samples / 10.0)
        xtx = x_design.T @ x_design + ridge_reg * np.eye(4, dtype=np.float64)
        xty = x_design.T @ y_target + ridge_reg * self._prior_beta
        beta_hat = np.linalg.solve(xtx, xty)
        beta_out = shrink_factor * beta_hat
        # Constrain w_burst (index 3) < 0.0 so lag-1 burst penalty never flips positive
        if float(beta_out[3]) > 0.0:
            beta_out[3] = 0.5 * float(self._prior_beta[3])
        return beta_out

    def _record_last_history_state(self, counts_mat: np.ndarray) -> None:
        """Cache last draw counts and 5-draw regime signature for feature-vector parity."""
        t = int(counts_mat.shape[0])
        self._last_draw_counts = counts_mat[t - 1].copy()
        self._last_history_length = t
        eff_5 = min(t, 5)
        self._last_regime_w5 = [int(x) for x in counts_mat[-eff_5:].sum(axis=0).tolist()]

    def fit_predict_counts(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
    ) -> list[float]:
        """Fit L2-penalized ridge model on counts_history (0..t-1) and predict for step t."""
        counts_mat = _validate_counts_history_array(counts_history)
        t = int(counts_mat.shape[0])
        self._record_last_history_state(counts_mat)
        x_all = _compute_all_step_feature_matrices(counts_mat)
        emp_freq = counts_mat.astype(np.float64) / float(PRIZES_PER_DRAW)
        y_all = (emp_freq - UNIFORM_BALL_PROB) / UNIFORM_BALL_PROB

        self._coef = self._fit_beta_for_step(x_all, y_all, t)
        logits = x_all[t - 1] @ self._coef
        return self._logits_to_simplex(logits)

    def predict_rolling_history(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
        *,
        start_step: int = 1,
    ) -> np.ndarray:
        """Compute pre-draw P_Seq(0..9) for steps tau in start_step..t-1 in a single fast pass."""
        counts_mat = _validate_counts_history_array(counts_history)
        t = int(counts_mat.shape[0])
        self._record_last_history_state(counts_mat)
        preds = np.full((t, CAGE_NUM_BALLS), UNIFORM_BALL_PROB, dtype=np.float64)
        x_all = _compute_all_step_feature_matrices(counts_mat)
        emp_freq = counts_mat.astype(np.float64) / float(PRIZES_PER_DRAW)
        y_all = (emp_freq - UNIFORM_BALL_PROB) / UNIFORM_BALL_PROB

        first_tau = max(1, int(start_step))
        for tau in range(first_tau, t):
            beta_tau = self._fit_beta_for_step(x_all, y_all, tau)
            logits_tau = x_all[tau - 1] @ beta_tau
            preds[tau] = self._logits_to_simplex_array(logits_tau)

        self._coef = self._fit_beta_for_step(x_all, y_all, t)
        return preds

    def fit_predict(
        self,
        history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
        target_draw: CanonicalDrawRecord | None = None,
        *,
        cage_name: CageName = "tens_cage",
    ) -> list[float]:
        """Fit on history 0..t-1 (enforcing PreDrawCutoffGate) and output P_Seq(0..9) for draw t."""
        if cage_name not in ("tens_cage", "units_cage"):
            raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

        if target_draw is not None:
            if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
                raise DataIntegrityError("history must be a sequence of CanonicalDrawRecord.")
            enforce_pre_draw_cutoff(history, target_draw)  # type: ignore[arg-type]
            _ = extract_cage_features(
                [
                    rec.tens_counts if cage_name == "tens_cage" else rec.units_counts
                    for rec in history  # type: ignore[union-attr]
                ],
                [rec.prizes_last2 for rec in history],  # type: ignore[union-attr]
                cage_name=cage_name,
                station_code=target_draw.station_code,
                target_draw_index=target_draw.draw_index,
                target_draw_date=target_draw.draw_date,
            )
            counts_mat = np.array(
                [
                    rec.tens_counts if cage_name == "tens_cage" else rec.units_counts
                    for rec in history  # type: ignore[union-attr]
                ],
                dtype=np.int64,
            )
        elif (
            isinstance(history, Sequence)
            and len(history) > 0
            and isinstance(history[0], CanonicalDrawRecord)
        ):
            counts_mat = np.array(
                [
                    rec.tens_counts if cage_name == "tens_cage" else rec.units_counts
                    for rec in history
                ],
                dtype=np.int64,
            )
        else:
            counts_mat = _validate_counts_history_array(history)  # type: ignore[arg-type]

        return self.fit_predict_counts(counts_mat)


def predict_markov_gap_probabilities(
    history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
    target_draw: CanonicalDrawRecord | None = None,
    *,
    cage_name: CageName = "tens_cage",
    l2_penalty: float = MARKOV_GAP_L2_PENALTY,
    temperature: float = 1.0,
) -> list[float]:
    """Convenience function to compute P_Seq(0..9) strictly from history 0..t-1."""
    model = RegularizedMarkovGapModel(l2_penalty=l2_penalty, temperature=temperature)
    return model.fit_predict(history, target_draw=target_draw, cage_name=cage_name)
