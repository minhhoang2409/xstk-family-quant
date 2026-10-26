"""Pillar 3 Branch 1: Bayesian Online Changepoint Detection (BOCD) with Dirichlet Shrinkage
and Causal Past-Window Optimizer (W*_{t-1}).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.special import gammaln, logsumexp

from xsmn_alpha.constants import (
    BOCD_MAX_RUN_LENGTH,
    BOCD_REGIME_LAMBDA,
    CAGE_NUM_BALLS,
    CANDIDATE_PAST_WINDOWS,
    DIRICHLET_PRIOR_ALPHA0,
    LAG1_EXHAUSTION_PENALTY,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
    compute_theoretical_noise_std,
)
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.features.extractor import (
    _validate_counts_history_array,
    enforce_pre_draw_cutoff,
)
from xsmn_alpha.schemas import (
    CageName,
    CanonicalDrawRecord,
    validate_probability_simplex,
)


def _validate_single_draw_counts(draw_counts: Sequence[int] | np.ndarray) -> np.ndarray:
    """Validate that draw_counts is a 10-element integer vector in 0..18 summing to 18."""
    if isinstance(draw_counts, (str, bytes)):
        raise DataIntegrityError("draw_counts must be a 10-element integer sequence or array.")
    try:
        arr = np.asarray(draw_counts)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert draw_counts to array: {exc}") from exc

    if arr.ndim != 1 or arr.shape[0] != CAGE_NUM_BALLS:
        raise DataIntegrityError(
            f"draw_counts must be a 1D vector of length {CAGE_NUM_BALLS}, got shape {arr.shape}."
        )
    if arr.dtype == np.bool_:
        raise DataIntegrityError("draw_counts cannot contain boolean values.")
    if np.issubdtype(arr.dtype, np.floating):
        if not np.all(np.isfinite(arr)):
            raise DataIntegrityError("draw_counts contains NaN or Inf values.")
        if not np.all(arr == np.floor(arr)):
            raise DataIntegrityError("draw_counts must contain integer values.")
    elif not np.issubdtype(arr.dtype, np.integer):
        raise DataIntegrityError(f"Unsupported draw_counts dtype: {arr.dtype}.")

    int_vec = arr.astype(np.int64, copy=False)
    if np.any(int_vec < 0) or np.any(int_vec > PRIZES_PER_DRAW):
        raise DataIntegrityError(f"draw_counts elements must be in 0..{PRIZES_PER_DRAW}.")
    total = int(int_vec.sum())
    if total != PRIZES_PER_DRAW:
        raise DataIntegrityError(f"draw_counts sum must equal {PRIZES_PER_DRAW}, got {total}.")
    return int_vec.astype(np.float64)


class CausalPastWindowOptimizer:
    """Causal Past-Window Optimizer (W*_{t-1}) with Lag-1 Burst Exhaustion Filter
    over statistically convergent windows {15, 20, 25, 30, 40, 50, 60}.

    At any time step t (with today's draw `draws[t]` strictly masked), evaluates each candidate
    lookback window W in `CANDIDATE_PAST_WINDOWS` strictly on historical transitions tau <= t-1
    (using `draws[tau - W : tau]` adjusted by the lag-1 burst exhaustion penalty
    `gamma_lag1 * (W / 20) * n_{tau-1, i}` to predict `draws[tau]`) to select the optimal past
    window length W*_{t-1} independently for each cage (`tens_cage` and `units_cage`), along with
    its problem-derived theoretical noise standard error sigma_nhieu(W*) = 1 / sqrt(200 * W*).
    """

    def __init__(
        self,
        *,
        candidate_windows: Sequence[int] = CANDIDATE_PAST_WINDOWS,
        eval_horizon: int = 22,
        eval_lookback: int | None = None,
        alpha0: float = DIRICHLET_PRIOR_ALPHA0,
        prior_draws: float = 4.0,
        lag1_penalty: float = LAG1_EXHAUSTION_PENALTY,
    ) -> None:
        if eval_lookback is not None:
            eval_horizon = eval_lookback
        if not candidate_windows:
            raise DataIntegrityError("candidate_windows must not be empty.")
        cleaned_w: list[int] = []
        for w in candidate_windows:
            if isinstance(w, bool) or not isinstance(w, int) or w < 1:
                raise DataIntegrityError(f"Invalid candidate window {w!r}.")
            cleaned_w.append(int(w))
        if isinstance(eval_horizon, bool) or not isinstance(eval_horizon, int) or eval_horizon < 5:
            raise DataIntegrityError(f"eval_horizon must be an int >= 5, got {eval_horizon!r}.")
        if (
            isinstance(alpha0, bool)
            or not isinstance(alpha0, (int, float))
            or not math.isfinite(alpha0)
            or float(alpha0) <= 0.0
        ):
            raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")
        if (
            isinstance(lag1_penalty, bool)
            or not isinstance(lag1_penalty, (int, float))
            or not math.isfinite(lag1_penalty)
            or float(lag1_penalty) < 0.0
        ):
            raise DataIntegrityError(
                f"lag1_penalty must be a finite non-negative float, got {lag1_penalty!r}."
            )

        self.candidate_windows: tuple[int, ...] = tuple(sorted(set(cleaned_w)))
        self.eval_horizon: int = int(eval_horizon)
        self.alpha0: float = float(alpha0)
        self.prior_draws: float = float(prior_draws)
        self.lag1_penalty: float = float(lag1_penalty)

    def compute_lag1_adjusted_window_proba(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
        w_star: int,
    ) -> np.ndarray:
        """Compute Dirichlet-smoothed 10-ball simplex vector with Lag-1 Burst Exhaustion Filter.

        Formula:
            N_tilde_{t-1, i}^{(W*)} = max(
                0, sum_{k=1}^{W*} n_{t-k, i} - gamma_lag1 * (W*/20) * n_{t-1, i}
            )
            P_W*(i) = (alpha_0 + N_tilde_{t-1, i}^{(W*)}) / sum_j (alpha_0 + N_tilde_{t-1, j})
        """
        if (
            isinstance(w_star, bool)
            or not isinstance(w_star, (int, np.integer))
            or int(w_star) <= 0
        ):
            raise DataIntegrityError(f"w_star must be a positive integer, got {w_star!r}.")
        try:
            arr = _validate_counts_history_array(counts_history).astype(np.float64)
        except Exception as exc:
            if isinstance(exc, DataIntegrityError):
                raise
            raise DataIntegrityError(
                f"Invalid counts_history in compute_lag1_adjusted_window_proba: {exc}"
            ) from exc

        tau = int(arr.shape[0])
        eff_w = min(max(1, int(w_star)), tau)
        raw_win = arr[tau - eff_w : tau].sum(axis=0)
        lag1_vec = arr[tau - 1]
        adj_win = np.maximum(0.0, raw_win - self.lag1_penalty * (float(eff_w) / 20.0) * lag1_vec)
        numer = self.alpha0 + adj_win
        denom = float(np.sum(numer))
        if denom <= 0.0 or not math.isfinite(denom):
            return np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)
        return numer / denom

    def select_optimal_window(
        self,
        counts_history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
        target_draw: CanonicalDrawRecord | None = None,
        cage_name: CageName = "tens_cage",
    ) -> tuple[int, float]:
        """Select optimal past window W*_{t-1} and sigma_nhieu(W*_{t-1}) from history 0..t-1.

        Returns:
            (optimal_window_draws, theoretical_noise_std)
        """
        if cage_name not in ("tens_cage", "units_cage"):
            raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

        if target_draw is not None:
            if not isinstance(counts_history, Sequence) or isinstance(counts_history, (str, bytes)):
                raise DataIntegrityError(
                    "counts_history must be a sequence of CanonicalDrawRecord."
                )
            enforce_pre_draw_cutoff(counts_history, target_draw)  # type: ignore[arg-type]
            raw_mat = np.array(
                [
                    rec.tens_counts if cage_name == "tens_cage" else rec.units_counts
                    for rec in counts_history  # type: ignore[union-attr]
                ],
                dtype=np.int64,
            )
            counts_mat = _validate_counts_history_array(raw_mat).astype(np.float64)
        elif (
            isinstance(counts_history, Sequence)
            and len(counts_history) > 0
            and isinstance(counts_history[0], CanonicalDrawRecord)
        ):
            raw_mat = np.array(
                [
                    rec.tens_counts if cage_name == "tens_cage" else rec.units_counts
                    for rec in counts_history
                ],
                dtype=np.int64,
            )
            counts_mat = _validate_counts_history_array(raw_mat).astype(np.float64)
        else:
            counts_mat = _validate_counts_history_array(counts_history).astype(np.float64)  # type: ignore[arg-type]

        t = int(counts_mat.shape[0])
        min_w = self.candidate_windows[0]
        if t < min_w + 6:
            eff_w = min(max(1, t), min_w)
            return eff_w, compute_theoretical_noise_std(eff_w)

        csum = np.vstack(
            [np.zeros((1, CAGE_NUM_BALLS), dtype=np.float64), np.cumsum(counts_mat, axis=0)]
        )
        best_w = min_w
        best_obj = -1e18
        prior_hits = self.prior_draws * (2.0 * float(PRIZES_PER_DRAW) * UNIFORM_BALL_PROB)
        trials_per_draw = 2.0 * float(PRIZES_PER_DRAW)

        for w in self.candidate_windows:
            if w > t - 6:
                continue
            start_tau = max(w, t - self.eval_horizon)
            raw_win = csum[start_tau:t] - csum[start_tau - w : t - w]
            lag1_slice = counts_mat[start_tau - 1 : t - 1]
            win_counts = np.maximum(
                0.0, raw_win - self.lag1_penalty * (float(w) / 20.0) * lag1_slice
            )
            actual_tau = counts_mat[start_tau:t]
            n_eval = int(actual_tau.shape[0])
            if n_eval <= 0:
                continue

            top2_idx = np.argsort(-win_counts, axis=1, kind="stable")[:, :2]
            top2_hits_mat = np.take_along_axis(actual_tau, top2_idx, axis=1)
            r1_hits = float(top2_hits_mat[:, 0].sum())
            r2_hits = float(top2_hits_mat[:, 1].sum())
            hits = r1_hits + r2_hits
            shrunk_top2_rate = (hits + prior_hits) / (
                (float(n_eval) + self.prior_draws) * trials_per_draw
            )
            r1_superiority = (r1_hits - r2_hits) / (
                (float(n_eval) + self.prior_draws) * float(PRIZES_PER_DRAW)
            )
            numer_w = self.alpha0 + win_counts
            p_w = numer_w / np.sum(numer_w, axis=1, keepdims=True)
            y_freq = actual_tau / float(PRIZES_PER_DRAW)
            brier = float(np.sum((p_w - y_freq) ** 2)) / float(n_eval)

            obj = shrunk_top2_rate + 1e-5 * r1_superiority - 1e-3 * brier
            if obj > best_obj:
                best_obj = obj
                best_w = w

        return best_w, compute_theoretical_noise_std(best_w)

    def precompute_rolling_optimal_windows(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Vectorized precomputation of (W*_{tau-1}, sigma_nhieu(W*_{tau-1})) for tau in 0..t."""
        counts_mat = _validate_counts_history_array(counts_history).astype(np.float64)
        t = int(counts_mat.shape[0])
        csum = np.vstack(
            [np.zeros((1, CAGE_NUM_BALLS), dtype=np.float64), np.cumsum(counts_mat, axis=0)]
        )
        y_freq_all = counts_mat / float(PRIZES_PER_DRAW)

        min_w = self.candidate_windows[0]
        cum_hits_by_w: dict[int, np.ndarray] = {}
        cum_r1_diff_by_w: dict[int, np.ndarray] = {}
        cum_brier_by_w: dict[int, np.ndarray] = {}

        for w in self.candidate_windows:
            if w >= t:
                continue
            raw_win = csum[w:t] - csum[0 : t - w]
            lag1_slice = counts_mat[w - 1 : t - 1]
            win_counts = np.maximum(
                0.0, raw_win - self.lag1_penalty * (float(w) / 20.0) * lag1_slice
            )
            actual_slice = counts_mat[w:t]
            top2_idx = np.argsort(-win_counts, axis=1, kind="stable")[:, :2]
            top2_hits_mat = np.take_along_axis(actual_slice, top2_idx, axis=1)
            step_hits = top2_hits_mat.sum(axis=1)
            step_r1_diff = top2_hits_mat[:, 0] - top2_hits_mat[:, 1]
            numer_w = self.alpha0 + win_counts
            p_w = numer_w / np.sum(numer_w, axis=1, keepdims=True)
            step_brier = np.sum((p_w - y_freq_all[w:t]) ** 2, axis=1)

            hits_full = np.zeros(t + 1, dtype=np.float64)
            r1_diff_full = np.zeros(t + 1, dtype=np.float64)
            brier_full = np.zeros(t + 1, dtype=np.float64)
            hits_full[w + 1 :] = np.cumsum(step_hits)
            r1_diff_full[w + 1 :] = np.cumsum(step_r1_diff)
            brier_full[w + 1 :] = np.cumsum(step_brier)
            cum_hits_by_w[w] = hits_full
            cum_r1_diff_by_w[w] = r1_diff_full
            cum_brier_by_w[w] = brier_full

        opt_windows = np.zeros(t + 1, dtype=np.int64)
        opt_sigmas = np.zeros(t + 1, dtype=np.float64)
        prior_hits = self.prior_draws * (2.0 * float(PRIZES_PER_DRAW) * UNIFORM_BALL_PROB)
        trials_per_draw = 2.0 * float(PRIZES_PER_DRAW)

        for tau in range(t + 1):
            if tau < min_w + 6:
                eff_w = min(max(1, tau), min_w)
                opt_windows[tau] = eff_w
                opt_sigmas[tau] = compute_theoretical_noise_std(eff_w)
                continue

            best_w = min_w
            best_obj = -1e18
            for w in self.candidate_windows:
                if w > tau - 6 or w not in cum_hits_by_w:
                    continue
                start_step = max(w, tau - self.eval_horizon)
                n_eval = tau - start_step
                if n_eval <= 0:
                    continue
                hits_sum = cum_hits_by_w[w][tau] - cum_hits_by_w[w][start_step]
                r1_diff_sum = cum_r1_diff_by_w[w][tau] - cum_r1_diff_by_w[w][start_step]
                brier_sum = cum_brier_by_w[w][tau] - cum_brier_by_w[w][start_step]
                shrunk_top2_rate = (hits_sum + prior_hits) / (
                    (float(n_eval) + self.prior_draws) * trials_per_draw
                )
                r1_superiority = r1_diff_sum / (
                    (float(n_eval) + self.prior_draws) * float(PRIZES_PER_DRAW)
                )
                brier = brier_sum / float(n_eval)
                obj = shrunk_top2_rate + 1e-5 * r1_superiority - 1e-3 * brier
                if obj > best_obj:
                    best_obj = obj
                    best_w = w

            opt_windows[tau] = best_w
            opt_sigmas[tau] = compute_theoretical_noise_std(best_w)

        return opt_windows, opt_sigmas


def optimize_causal_past_window(
    history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
    target_draw: CanonicalDrawRecord | None = None,
    cage_name: CageName = "tens_cage",
    *,
    candidate_windows: Sequence[int] = CANDIDATE_PAST_WINDOWS,
    eval_horizon: int = 22,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> tuple[int, float]:
    """Find optimal (W*_{t-1}, sigma_nhieu(W*_{t-1})) strictly from history 0..t-1."""
    optimizer = CausalPastWindowOptimizer(
        candidate_windows=candidate_windows,
        eval_horizon=eval_horizon,
        alpha0=alpha0,
    )
    return optimizer.select_optimal_window(history, target_draw=target_draw, cage_name=cage_name)


class BayesianDirichletBOCD:
    """Adams & MacKay (2007) Bayesian Online Changepoint Detection with Dirichlet Shrinkage
    and Causal Past-Window Optimizer (W*_{t-1}).

    Maintains run-length posterior P(r_{t-1} = r | c_{1:t-1}) for r in {0, 1, ..., R_max}
    exclusively in log-space using scipy.special.gammaln and scipy.special.logsumexp,
    integrates with the Causal Past-Window Optimizer W*_{t-1} over candidate windows
    {3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60}, and immediately yields to short run lengths
    within <= 4 draws whenever the 2-sample G^2 changepoint detector fires.
    """

    def __init__(
        self,
        *,
        max_run_length: int = BOCD_MAX_RUN_LENGTH,
        regime_lambda: float = BOCD_REGIME_LAMBDA,
        hazard_rate: float | None = None,
        alpha0: float = DIRICHLET_PRIOR_ALPHA0,
        surprise_g2_threshold: float = 24.0,
        candidate_windows: Sequence[int] = CANDIDATE_PAST_WINDOWS,
    ) -> None:
        if (
            isinstance(max_run_length, bool)
            or not isinstance(max_run_length, int)
            or max_run_length < 1
        ):
            raise DataIntegrityError(
                f"max_run_length must be an integer >= 1, got {max_run_length!r}."
            )
        if (
            isinstance(regime_lambda, bool)
            or not isinstance(regime_lambda, (int, float))
            or not math.isfinite(regime_lambda)
            or float(regime_lambda) <= 1.0
        ):
            raise DataIntegrityError(
                f"regime_lambda must be a finite float > 1.0, got {regime_lambda!r}."
            )
        resolved_hazard = 1.0 / float(regime_lambda) if hazard_rate is None else float(hazard_rate)
        if (
            isinstance(hazard_rate, bool)
            or not math.isfinite(resolved_hazard)
            or resolved_hazard <= 0.0
            or resolved_hazard >= 1.0
        ):
            raise DataIntegrityError(f"hazard_rate must be in (0.0, 1.0), got {resolved_hazard!r}.")
        if (
            isinstance(alpha0, bool)
            or not isinstance(alpha0, (int, float))
            or not math.isfinite(alpha0)
            or float(alpha0) <= 0.0
        ):
            raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")
        if (
            isinstance(surprise_g2_threshold, bool)
            or not isinstance(surprise_g2_threshold, (int, float))
            or not math.isfinite(surprise_g2_threshold)
            or float(surprise_g2_threshold) <= 0.0
        ):
            raise DataIntegrityError(
                f"surprise_g2_threshold must be a finite positive float, "
                f"got {surprise_g2_threshold!r}."
            )

        self.max_run_length: int = int(max_run_length)
        self.regime_lambda: float = float(regime_lambda)
        self.hazard_rate: float = resolved_hazard
        self.alpha0: float = float(alpha0)
        self.surprise_g2_threshold: float = float(surprise_g2_threshold)
        self.window_optimizer = CausalPastWindowOptimizer(
            candidate_windows=candidate_windows,
            alpha0=self.alpha0,
        )

        self._step_count: int = 0
        self._suff_stats: np.ndarray = np.zeros(
            (self.max_run_length + 1, CAGE_NUM_BALLS), dtype=np.float64
        )
        self._log_r_post: np.ndarray = np.full(self.max_run_length + 1, -np.inf, dtype=np.float64)
        self._r_post: np.ndarray = np.zeros(self.max_run_length + 1, dtype=np.float64)
        self._history_buffer: list[np.ndarray] = []
        self._optimal_past_window: int = int(self.window_optimizer.candidate_windows[0])
        self._theoretical_noise_std: float = compute_theoretical_noise_std(
            self._optimal_past_window
        )
        self._changepoint_cooldown: int = 0
        self._bocd_map_run_length: int = 0
        self._draws_since_changepoint: int = 0
        self.reset()

    def reset(self) -> None:
        """Reset BOCD state to t=0 prior (P(r=0) = 1.0, zero accumulated counts)."""
        self._step_count = 0
        self._suff_stats.fill(0.0)
        self._log_r_post.fill(-np.inf)
        self._log_r_post[0] = 0.0
        self._r_post.fill(0.0)
        self._r_post[0] = 1.0
        self._history_buffer = []
        self._optimal_past_window = int(self.window_optimizer.candidate_windows[0])
        self._theoretical_noise_std = compute_theoretical_noise_std(self._optimal_past_window)
        self._changepoint_cooldown = 0
        self._bocd_map_run_length = 0
        self._draws_since_changepoint = 0

    @property
    def step_count(self) -> int:
        """Return number of draw count vectors observed so far."""
        return self._step_count

    @property
    def optimal_past_window(self) -> int:
        """Return the causal optimal past window W*_{t-1} selected from draws[0:t]."""
        return self._optimal_past_window

    @property
    def theoretical_noise_std(self) -> float:
        """Return problem-derived noise std sigma_nhieu(W*_{t-1}) = 1 / sqrt(200 * W*_{t-1})."""
        return self._theoretical_noise_std

    @property
    def run_length_posterior(self) -> np.ndarray:
        """Return a copy of the current run-length posterior P(r_{t-1} = r | c_{1:t-1})."""
        return self._r_post.copy()

    def get_run_length_posterior(self) -> np.ndarray:
        """Return a copy of the current run-length posterior P(r_{t-1} = r | c_{1:t-1})."""
        return self._r_post.copy()

    @property
    def map_run_length(self) -> int:
        """Return the Maximum A Posteriori (MAP) run length r in {0, ..., R_max}."""
        return int(np.argmax(self._r_post))

    def short_run_mass(self, max_r: int = 4) -> float:
        """Return posterior probability mass on short run lengths r in {0, ..., max_r}."""
        bound = max(0, min(int(max_r), self.max_run_length))
        return float(np.sum(self._r_post[: bound + 1]))

    def conditional_predictive_matrix(self) -> np.ndarray:
        """Compute conditional predictive matrix P_BOCD(i | r) of shape (R_max + 1, 10)."""
        r_grid = np.arange(self.max_run_length + 1, dtype=np.float64)[:, None]
        numer = self.alpha0 + self._suff_stats
        denom = 10.0 * self.alpha0 + float(PRIZES_PER_DRAW) * r_grid
        cond = numer / denom
        if self._step_count < self.max_run_length:
            cond[self._step_count + 1 :] = UNIFORM_BALL_PROB
        return cond

    def _effective_causal_window(self, w_star: int) -> int:
        """Return effective window length capped by post-changepoint regime age when applicable."""
        eff_w = min(
            int(w_star), self._draws_since_changepoint, self._step_count, self.max_run_length
        )
        return max(1, eff_w) if self._step_count >= 1 else 0

    def _apply_causal_window_posterior_concentration(self, w_star: int) -> None:
        """Concentrate long-run posterior P(r_t >= 6) onto causal optimal window W*_{t-1}
        without crushing short_run_mass(max_r=5).
        """
        eff_w = self._effective_causal_window(w_star)
        short_mass = self.short_run_mass(max_r=5)
        long_mass = float(np.sum(self._r_post[6:]))
        if (
            self._step_count >= 8
            and self._changepoint_cooldown == 0
            and short_mass < 0.45
            and eff_w >= 6
            and long_mass > 1e-12
        ):
            gamma = 0.92 * long_mass
            r_post = self._r_post.copy()
            scale_long = max(0.0, (long_mass - gamma) / long_mass)
            r_post[6:] *= scale_long
            r_post[eff_w] += gamma
            r_post = np.maximum(0.0, r_post)
            r_post /= float(np.sum(r_post))
            self._r_post = r_post

    def _predict_proba_array(self) -> np.ndarray:
        """Fast internal numpy computation of marginalized P_BOCD(0..9) = r_post @ cond_mat."""
        cond_mat = self.conditional_predictive_matrix()
        marginal = self._r_post @ cond_mat
        marginal = np.maximum(0.0, marginal)
        total = float(np.sum(marginal))
        if total <= 0.0 or not math.isfinite(total):
            return np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)
        return marginal / total

    def predict_lag1_adjusted_proba(
        self,
        counts_prefix: np.ndarray | Sequence[Sequence[int]] | None = None,
    ) -> np.ndarray:
        """Compute P_BOCD(0..9) incorporating the Lag-1 Burst Exhaustion Filter at W*_{t-1}."""
        base_marginal = self._predict_proba_array()
        short_mass_4 = self.short_run_mass(max_r=4)
        if self._step_count > 8 and short_mass_4 > 0.50:
            shrink_u = 0.80 * short_mass_4
            shrunk = (1.0 - shrink_u) * base_marginal + shrink_u * UNIFORM_BALL_PROB
            return shrunk / float(np.sum(shrunk))

        short_mass = self.short_run_mass(max_r=5)
        eff_w = self._effective_causal_window(self._optimal_past_window)
        if (
            self._step_count >= 8
            and self._changepoint_cooldown == 0
            and short_mass < 0.45
            and eff_w >= 3
        ):
            src_mat = (
                counts_prefix
                if counts_prefix is not None
                else np.asarray(self._history_buffer, dtype=np.float64)
            )
            p_adj_w = self.window_optimizer.compute_lag1_adjusted_window_proba(
                src_mat,
                eff_w,
            )
            gamma = 0.92 * (1.0 - short_mass)
            blended = (1.0 - gamma) * base_marginal + gamma * p_adj_w
            blended = np.maximum(0.0, blended)
            total = float(np.sum(blended))
            if total > 0.0 and math.isfinite(total):
                return blended / total
        return base_marginal

    def predict_proba(self) -> list[float]:
        """Compute marginalized 10-ball predictive distribution P_BOCD(0..9) summing to 1.0."""
        marginal = self.predict_lag1_adjusted_proba()
        return validate_probability_simplex(marginal.tolist(), expected_len=CAGE_NUM_BALLS)

    def update(self, draw_counts: Sequence[int] | np.ndarray) -> list[float]:
        """Update BOCD run-length trellis with observed draw c_t in log-space and return P_BOCD."""
        c_vec = _validate_single_draw_counts(draw_counts)
        self._history_buffer.append(c_vec.astype(np.int64))
        self._update_unchecked(c_vec)
        hist_mat = np.asarray(self._history_buffer, dtype=np.int64)
        w_star, sigma_w = self.window_optimizer.select_optimal_window(hist_mat)
        self._optimal_past_window = w_star
        self._theoretical_noise_std = sigma_w
        if len(self._history_buffer) >= 8:
            self._apply_causal_window_posterior_concentration(w_star)
        return self.predict_proba()

    def _update_unchecked(self, c_vec: np.ndarray) -> None:
        """Internal log-space BOCD trellis update given validated float64 c_vec."""
        prev_max_r = min(self._step_count, self.max_run_length)
        prev_short_mass_4 = self.short_run_mass(max_r=4)

        # 1. Compute Dirichlet-Multinomial log predictive probabilities for r in 0..prev_max_r
        r_grid = np.arange(prev_max_r + 1, dtype=np.float64)
        alpha_mat = self.alpha0 + self._suff_stats[: prev_max_r + 1]
        a_sum = 10.0 * self.alpha0 + float(PRIZES_PER_DRAW) * r_grid
        multinomial_const = float(gammaln(float(PRIZES_PER_DRAW) + 1.0)) - float(
            np.sum(gammaln(c_vec + 1.0))
        )
        log_pred = (
            multinomial_const
            + gammaln(a_sum)
            - gammaln(a_sum + float(PRIZES_PER_DRAW))
            + np.sum(gammaln(alpha_mat + c_vec[None, :]) - gammaln(alpha_mat), axis=1)
        )

        # 2. Advance sufficient statistics S_t^{(r')} = S_{t-1}^{(r'-1)} + c_t for r' >= 1
        new_suff = np.zeros_like(self._suff_stats)
        new_suff[1 : self.max_run_length + 1] = (
            self._suff_stats[0 : self.max_run_length] + c_vec[None, :]
        )
        self._suff_stats = new_suff
        self._step_count += 1
        self._draws_since_changepoint += 1
        new_max_r = min(self._step_count, self.max_run_length)

        # 3. Compute post-observation log weights for grown run lengths r' = r + 1
        log_grown = np.full(self.max_run_length + 1, -np.inf, dtype=np.float64)
        grown_weights = self._log_r_post[: prev_max_r + 1] + log_pred
        if prev_max_r < self.max_run_length:
            log_grown[1 : prev_max_r + 2] = grown_weights
        else:
            log_grown[1 : self.max_run_length] = grown_weights[:-2]
            log_grown[self.max_run_length] = float(logsumexp(grown_weights[-2:]))

        # 4. Posterior-weighted two-sample Multinomial G^2 changepoint test on r' >= 5
        pre_grown_norm = log_grown[: new_max_r + 1] - float(logsumexp(log_grown[: new_max_r + 1]))
        pre_grown_probs = np.exp(pre_grown_norm)
        long_mass_before = (
            float(np.sum(pre_grown_probs[5 : new_max_r + 1])) if new_max_r >= 5 else 0.0
        )

        h_vec = np.full(new_max_r + 1, self.hazard_rate, dtype=np.float64)
        weighted_g2_excess = 0.0
        if new_max_r > 8:
            w_rec = 4
            s_recent = self._suff_stats[w_rec]
            m_rec = float(PRIZES_PER_DRAW * w_rec)
            p_rec = (1.0 + s_recent) / (10.0 + m_rec)

            r_long = np.arange(5, new_max_r + 1, dtype=np.float64)
            s_old = self._suff_stats[5 : new_max_r + 1] - s_recent[None, :]
            m_old = float(PRIZES_PER_DRAW) * (r_long - float(w_rec))
            p_old = (1.0 + s_old) / (10.0 + m_old[:, None])

            kl_rec_old = np.sum(p_rec[None, :] * np.log(p_rec[None, :] / p_old), axis=1)
            eff_n = (m_rec * m_old) / (m_rec + m_old)
            g2_stat = 2.0 * eff_n * np.maximum(0.0, kl_rec_old)
            g2_excess = np.maximum(0.0, g2_stat - self.surprise_g2_threshold)
            weighted_g2_excess = float(np.sum(pre_grown_probs[5 : new_max_r + 1] * g2_excess))
            if np.any(g2_excess > 0.0):
                log_grown[5 : new_max_r + 1] -= 1.5 * g2_excess
                h_vec[5 : new_max_r + 1] = np.minimum(0.78, self.hazard_rate + 0.08 * g2_excess)

        if weighted_g2_excess > 0.5 and long_mass_before > 0.10:
            self._changepoint_cooldown = 4
        elif self._changepoint_cooldown > 0:
            self._changepoint_cooldown -= 1

        log_grown_norm = log_grown - float(logsumexp(log_grown))

        # 5. Apply per-run-length hazard transition to form pre-draw posterior P(r_t)
        log_h_vec = np.log(h_vec[1 : new_max_r + 1])
        log_one_minus_h_vec = np.log(1.0 - h_vec[1 : new_max_r + 1])

        new_log_r = np.full(self.max_run_length + 1, -np.inf, dtype=np.float64)
        new_log_r[0] = float(logsumexp(log_h_vec + log_grown_norm[1 : new_max_r + 1]))
        new_log_r[1 : new_max_r + 1] = log_one_minus_h_vec + log_grown_norm[1 : new_max_r + 1]

        log_norm = float(logsumexp(new_log_r))
        self._log_r_post = new_log_r - log_norm
        r_post = np.exp(self._log_r_post)
        r_post = np.maximum(0.0, r_post)
        r_post /= float(np.sum(r_post))
        self._r_post = r_post
        self._bocd_map_run_length = int(np.argmax(r_post))
        new_short_mass_4 = self.short_run_mass(max_r=4)
        if self._step_count > 8 and new_short_mass_4 > 0.50 and prev_short_mass_4 <= 0.50:
            self._draws_since_changepoint = int(np.argmax(r_post[1:5])) + 1

    def predict_rolling_history(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
    ) -> np.ndarray:
        """Compute pre-draw BOCD predictive distributions for every step tau in 0..t-1."""
        counts_mat = _validate_counts_history_array(counts_history)
        c_float = counts_mat.astype(np.float64)
        t = int(c_float.shape[0])
        opt_windows, opt_sigmas = self.window_optimizer.precompute_rolling_optimal_windows(
            counts_mat
        )
        preds = np.zeros((t, CAGE_NUM_BALLS), dtype=np.float64)
        self.reset()
        for tau in range(t):
            preds[tau] = self.predict_lag1_adjusted_proba(c_float[:tau])
            self._update_unchecked(c_float[tau])
            w_next = int(opt_windows[tau + 1])
            self._optimal_past_window = w_next
            self._theoretical_noise_std = float(opt_sigmas[tau + 1])
            if (tau + 1) >= 8:
                self._apply_causal_window_posterior_concentration(w_next)
        self._history_buffer = [row.copy() for row in counts_mat]
        return preds

    def fit_predict(
        self,
        history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
        target_draw: CanonicalDrawRecord | None = None,
        *,
        cage_name: CageName = "tens_cage",
    ) -> list[float]:
        """Fit BOCD on history 0..t-1 (enforcing PreDrawCutoffGate) and predict for draw t."""
        if cage_name not in ("tens_cage", "units_cage"):
            raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

        if target_draw is not None:
            if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
                raise DataIntegrityError("history must be a sequence of CanonicalDrawRecord.")
            enforce_pre_draw_cutoff(history, target_draw)  # type: ignore[arg-type]
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

        self.predict_rolling_history(counts_mat)
        adj_now = self.predict_lag1_adjusted_proba(counts_mat.astype(np.float64))
        return validate_probability_simplex(adj_now.tolist(), expected_len=CAGE_NUM_BALLS)


def predict_bocd_probabilities(
    history: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
    target_draw: CanonicalDrawRecord | None = None,
    *,
    cage_name: CageName = "tens_cage",
    max_run_length: int = BOCD_MAX_RUN_LENGTH,
    regime_lambda: float = BOCD_REGIME_LAMBDA,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> list[float]:
    """Convenience function to run BayesianDirichletBOCD on pre-draw history 0..t-1."""
    bocd = BayesianDirichletBOCD(
        max_run_length=max_run_length,
        regime_lambda=regime_lambda,
        alpha0=alpha0,
    )
    return bocd.fit_predict(history, target_draw=target_draw, cage_name=cage_name)
