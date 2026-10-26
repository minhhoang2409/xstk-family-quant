"""Pillar 2A: Multi-Window Statistical Falsification Tests (W in {15, 30, 60})."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.special import gammaln
from scipy.stats import chi2, norm

from xsmn_alpha.constants import (
    CAGE_NUM_BALLS,
    DIRICHLET_PRIOR_ALPHA0,
    FALSIFICATION_WINDOWS,
    MARKOV_ACTIVE_THRESHOLD_HITS,
    MIN_SAMPLE_SIZE_DRAWS,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.schemas import CageName, CageWindowTestResult, CanonicalDrawRecord

_LOG_10 = math.log(float(CAGE_NUM_BALLS))
_LOG_UNIFORM_PROB = math.log(UNIFORM_BALL_PROB)


class WindowTestResult(CageWindowTestResult):
    """CageWindowTestResult subclass with ergonomic property aliases."""

    @property
    def window(self) -> int:
        """Alias for window_draws."""
        return self.window_draws

    @property
    def bf10(self) -> float:
        """Alias for bf10_dirichlet."""
        return self.bf10_dirichlet

    @property
    def h_norm(self) -> float:
        """Alias for normalized_entropy."""
        return self.normalized_entropy

    @property
    def entropy_norm(self) -> float:
        """Alias for normalized_entropy."""
        return self.normalized_entropy

    @property
    def runs_p_value(self) -> float:
        """Alias for runs_test_min_p_value."""
        return self.runs_test_min_p_value

    @property
    def runs_z_stat(self) -> float:
        """Alias for runs_test_max_abs_z."""
        return self.runs_test_max_abs_z

    @property
    def markov_p_value(self) -> float:
        """Alias for markov_chi2_p_value."""
        return self.markov_chi2_p_value


def validate_counts_matrix(
    counts: np.ndarray | Sequence[Sequence[int]],
    *,
    min_draws: int = MIN_SAMPLE_SIZE_DRAWS,
) -> np.ndarray:
    """Validate a 2D cage counts matrix of shape (T, 10) with row sums == 18 and T >= min_draws."""
    if isinstance(min_draws, bool) or not isinstance(min_draws, (int, np.integer)) or min_draws < 1:
        raise DataIntegrityError(f"min_draws must be a positive integer, got {min_draws!r}.")
    if isinstance(counts, (str, bytes)):
        raise DataIntegrityError("counts must be a 2D array or sequence of 10-ball count rows.")
    try:
        arr = np.asarray(counts)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert counts to ndarray: {exc}") from exc

    if arr.dtype == np.bool_:
        raise DataIntegrityError("counts matrix cannot contain boolean values.")
    if np.issubdtype(arr.dtype, np.floating):
        if not np.all(np.isfinite(arr)):
            raise DataIntegrityError("counts matrix contains NaN or Inf values.")
        if not np.all(arr == np.floor(arr)):
            raise DataIntegrityError("counts matrix must contain integer values.")
    elif not np.issubdtype(arr.dtype, np.integer):
        raise DataIntegrityError(f"Unsupported counts dtype: {arr.dtype}.")

    if arr.ndim != 2 or arr.shape[1] != CAGE_NUM_BALLS:
        raise DataIntegrityError(
            f"counts matrix must have shape (T, {CAGE_NUM_BALLS}), got {arr.shape}."
        )
    if arr.shape[0] < int(min_draws):
        raise InsufficientSampleSizeError(
            f"Sample size T={arr.shape[0]} is below minimum threshold {int(min_draws)} draws."
        )

    int_arr = arr.astype(np.int64, copy=False)
    if np.any(int_arr < 0) or np.any(int_arr > PRIZES_PER_DRAW):
        raise DataIntegrityError(
            f"counts matrix contains negative or out-of-range values outside 0..{PRIZES_PER_DRAW}."
        )
    row_sums = int_arr.sum(axis=1)
    if not np.all(row_sums == PRIZES_PER_DRAW):
        bad_row = int(np.flatnonzero(row_sums != PRIZES_PER_DRAW)[0])
        raise DataIntegrityError(
            f"counts matrix row {bad_row} sum is {int(row_sums[bad_row])}, "
            f"expected {PRIZES_PER_DRAW}."
        )
    return int_arr


def _validate_observed_1d(
    observed_counts: Sequence[int] | np.ndarray,
    window_draws: int | None = None,
) -> np.ndarray:
    """Validate a 10-element observed counts vector O_0..O_9."""
    if window_draws is not None and (
        isinstance(window_draws, bool)
        or not isinstance(window_draws, (int, np.integer))
        or int(window_draws) < 1
    ):
        raise DataIntegrityError(f"window_draws must be a positive integer, got {window_draws!r}.")
    if isinstance(observed_counts, (str, bytes)):
        raise DataIntegrityError("observed_counts must be a 10-element numeric sequence.")
    try:
        arr = np.asarray(observed_counts)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert observed_counts to ndarray: {exc}") from exc

    if arr.ndim != 1 or arr.shape[0] != CAGE_NUM_BALLS:
        raise DataIntegrityError(
            f"observed_counts must be a 1D vector of length {CAGE_NUM_BALLS}, got {arr.shape}."
        )
    if arr.dtype == np.bool_:
        raise DataIntegrityError("observed_counts cannot contain boolean values.")
    if np.issubdtype(arr.dtype, np.floating):
        if not np.all(np.isfinite(arr)):
            raise DataIntegrityError("observed_counts contains NaN or Inf.")
        if not np.all(arr == np.floor(arr)):
            raise DataIntegrityError("observed_counts must contain integer counts.")
    elif not np.issubdtype(arr.dtype, np.integer):
        raise DataIntegrityError(f"Unsupported observed_counts dtype: {arr.dtype}.")

    int_arr = arr.astype(np.int64, copy=False)
    if np.any(int_arr < 0):
        raise DataIntegrityError("observed_counts cannot contain negative values.")
    total_trials = int(int_arr.sum())
    if total_trials <= 0:
        raise DataIntegrityError("Sum of observed_counts must be strictly positive.")
    if window_draws is not None:
        expected_trials = int(window_draws) * PRIZES_PER_DRAW
        if total_trials != expected_trials:
            raise DataIntegrityError(
                f"sum(observed_counts)={total_trials} != 18 * window_draws ({expected_trials})."
            )
    return int_arr


def multinomial_chi_square_test(
    observed_counts: Sequence[int] | np.ndarray,
    window_draws: int | None = None,
) -> tuple[float, float]:
    """Compute Multinomial Chi-Square statistic (df=9) and p-value against uniform null 0.10."""
    obs = _validate_observed_1d(observed_counts, window_draws=window_draws)
    m_w = float(obs.sum())
    expected_e = UNIFORM_BALL_PROB * m_w
    obs_f = obs.astype(np.float64)
    chi2_stat = float(np.sum((obs_f - expected_e) ** 2 / expected_e))
    p_value = float(chi2.sf(chi2_stat, df=CAGE_NUM_BALLS - 1))
    return (max(0.0, chi2_stat), float(np.clip(p_value, 0.0, 1.0)))


def dirichlet_multinomial_bf10(
    observed_counts: Sequence[int] | np.ndarray,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> float:
    """Compute Dirichlet-Multinomial Bayes Factor BF10 in log-space using scipy.special.gammaln."""
    if (
        isinstance(alpha0, bool)
        or not isinstance(alpha0, (int, float))
        or not math.isfinite(alpha0)
        or alpha0 <= 0.0
    ):
        raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")
    obs = _validate_observed_1d(observed_counts)
    obs_f = obs.astype(np.float64)
    m_w = float(obs_f.sum())
    a0 = float(alpha0)
    sum_alpha0 = float(CAGE_NUM_BALLS) * a0

    ln_p_h1 = float(gammaln(sum_alpha0) - gammaln(sum_alpha0 + m_w)) + float(
        np.sum(gammaln(a0 + obs_f) - gammaln(a0))
    )
    ln_p_h0 = m_w * _LOG_UNIFORM_PROB
    log_bf10 = float(np.clip(ln_p_h1 - ln_p_h0, -700.0, 700.0))
    return float(math.exp(log_bf10))


def normalized_shannon_entropy(
    observed_counts: Sequence[int] | np.ndarray,
) -> float:
    """Compute normalized Shannon entropy H_norm in [0, 1] over 10 balls."""
    obs = _validate_observed_1d(observed_counts)
    if bool(np.all(obs == obs[0])):
        return 1.0
    m_w = float(obs.sum())
    probs = obs.astype(np.float64) / m_w
    pos = probs[probs > 0.0]
    raw_entropy = -float(np.sum(pos * np.log(pos)))
    h_norm = raw_entropy / _LOG_10
    if abs(h_norm - 1.0) <= 1e-14:
        return 1.0
    return float(np.clip(h_norm, 0.0, 1.0))


def _runs_test_1d_binary(binary_seq: np.ndarray) -> tuple[float, float]:
    """Compute two-sided Wald-Wolfowitz Runs Test (p_value, abs_z) on a 1D binary sequence."""
    n = int(binary_seq.shape[0])
    if n < 2:
        return (1.0, 0.0)
    n1 = int(np.sum(binary_seq))
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return (1.0, 0.0)

    runs = 1 + int(np.sum(binary_seq[1:] != binary_seq[:-1]))
    prod = 2.0 * float(n1) * float(n0)
    mu_r = 1.0 + prod / float(n)
    var_num = prod * (prod - float(n))
    var_den = float(n * n * (n - 1))
    if var_den <= 0.0 or var_num <= 1e-12:
        return (1.0, 0.0)

    sigma_r = math.sqrt(var_num / var_den)
    abs_z = abs(float(runs) - mu_r) / sigma_r
    p_val = float(2.0 * norm.sf(abs_z))
    return (float(np.clip(p_val, 0.0, 1.0)), float(abs_z))


def wald_wolfowitz_runs_test(
    window_counts: np.ndarray | Sequence[Sequence[int]] | Sequence[int],
    *,
    active_threshold: int = MARKOV_ACTIVE_THRESHOLD_HITS,
) -> tuple[float, float]:
    """Compute Wald-Wolfowitz Runs Test (min_p_value, max_abs_z) on S_{tau, i} = I(n_{tau, i} >= 2).

    Accepts either a 2D (W, 10) counts matrix or a 1D integer count sequence (in 0..18).
    """
    if (
        isinstance(active_threshold, bool)
        or not isinstance(active_threshold, (int, np.integer))
        or int(active_threshold) < 1
        or int(active_threshold) > PRIZES_PER_DRAW
    ):
        raise DataIntegrityError(
            f"active_threshold must be an integer in 1..{PRIZES_PER_DRAW}, "
            f"got {active_threshold!r}."
        )
    if isinstance(window_counts, (str, bytes)):
        raise DataIntegrityError("window_counts must be a numeric array or sequence.")
    try:
        arr = np.asarray(window_counts)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert window_counts to ndarray: {exc}") from exc

    if arr.dtype == np.bool_:
        raise DataIntegrityError("window_counts cannot contain boolean values.")

    if arr.ndim == 1:
        if arr.size < 2:
            raise DataIntegrityError("1D window_counts must have at least 2 elements.")
        if np.issubdtype(arr.dtype, np.floating):
            if not np.all(np.isfinite(arr)):
                raise DataIntegrityError("window_counts contains NaN or Inf.")
            if not np.all(arr == np.floor(arr)):
                raise DataIntegrityError("window_counts must contain integer counts.")
        elif not np.issubdtype(arr.dtype, np.integer):
            raise DataIntegrityError(f"Unsupported window_counts dtype: {arr.dtype}.")

        int_arr = arr.astype(np.int64, copy=False)
        if np.any(int_arr < 0) or np.any(int_arr > PRIZES_PER_DRAW):
            raise DataIntegrityError(f"1D window_counts elements must be in 0..{PRIZES_PER_DRAW}.")
        if (
            not isinstance(window_counts, np.ndarray)
            and int(int_arr.max()) <= 1
            and int(active_threshold) == MARKOV_ACTIVE_THRESHOLD_HITS
        ):
            bin_seq = int_arr
        else:
            bin_seq = (int_arr >= int(active_threshold)).astype(np.int64)
        return _runs_test_1d_binary(bin_seq)

    w_mat = validate_counts_matrix(arr, min_draws=2)
    active_mat = (w_mat >= int(active_threshold)).astype(np.int64)
    min_p = 1.0
    max_z = 0.0
    for ball in range(CAGE_NUM_BALLS):
        p_i, z_i = _runs_test_1d_binary(active_mat[:, ball])
        if p_i < min_p:
            min_p = p_i
        if z_i > max_z:
            max_z = z_i
    return (min_p, max_z)


def markov_transition_chi_square_test(
    window_counts: np.ndarray | Sequence[Sequence[int]],
) -> tuple[float, float]:
    """Compute Markov Transition Chi-Square and p-value on 10x10 transition table C_{i,j}.

    Normalizes each draw's transition row contribution by 1 / |A_{tau-1}| (the number of
    co-active balls at draw tau-1) so a draw with multiple active balls contributes total
    weight 18 across all active rows instead of inflating Chi-Square up to 9x.
    """
    if isinstance(window_counts, (str, bytes)):
        raise DataIntegrityError("window_counts must be a 2D numeric array or sequence.")
    raw_arr = np.asarray(window_counts)
    if raw_arr.ndim == 2 and raw_arr.shape[0] < 2:
        raise DataIntegrityError("Markov transition test requires at least 2 draws.")
    w_mat = validate_counts_matrix(window_counts, min_draws=2)
    active_prev = (w_mat[:-1] >= MARKOV_ACTIVE_THRESHOLD_HITS).astype(np.float64)
    next_counts = w_mat[1:].astype(np.float64)

    active_per_draw = active_prev.sum(axis=1, keepdims=True)
    weights_prev = np.where(
        active_per_draw > 0.0,
        active_prev / np.maximum(1.0, active_per_draw),
        0.0,
    )

    # Normalized 10x10 table: C_{i,j} = sum_{tau} (S_{tau-1, i} / |A_{tau-1}|) * n_{tau, j}
    trans_table = weights_prev.T @ next_counts
    row_totals = trans_table.sum(axis=1)
    active_rows = row_totals > 0.0
    num_active_rows = int(np.sum(active_rows))
    if num_active_rows == 0:
        return (0.0, 1.0)

    active_table = trans_table[active_rows]
    expected_table = UNIFORM_BALL_PROB * row_totals[active_rows, np.newaxis]
    chi2_stat = float(np.sum((active_table - expected_table) ** 2 / expected_table))
    df = (CAGE_NUM_BALLS - 1) * num_active_rows
    p_val = float(chi2.sf(chi2_stat, df=df))
    return (max(0.0, chi2_stat), float(np.clip(p_val, 0.0, 1.0)))


def run_window_tests(
    counts_or_observed: np.ndarray | Sequence[Sequence[int]] | Sequence[int],
    window_draws: int,
    *,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> WindowTestResult:
    """Run all 4 falsification statistical tests on a single window W."""
    if isinstance(window_draws, bool) or not isinstance(window_draws, int) or window_draws < 2:
        raise DataIntegrityError(f"window_draws must be an integer >= 2, got {window_draws!r}.")
    if (
        isinstance(alpha0, bool)
        or not isinstance(alpha0, (int, float))
        or not math.isfinite(alpha0)
        or alpha0 <= 0.0
    ):
        raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")

    arr = np.asarray(counts_or_observed)
    if arr.ndim == 1:
        obs_arr = _validate_observed_1d(arr, window_draws=window_draws)
        obs_list = [int(x) for x in obs_arr.tolist()]
        chi2_stat, chi2_p = multinomial_chi_square_test(obs_arr, window_draws=window_draws)
        bf10 = dirichlet_multinomial_bf10(obs_arr, alpha0=alpha0)
        h_norm = normalized_shannon_entropy(obs_arr)
        runs_min_p, runs_max_z = 1.0, 0.0
        markov_chi2, markov_p = 0.0, 1.0
    else:
        mat = validate_counts_matrix(arr, min_draws=window_draws)
        win_mat = mat[-window_draws:]
        obs_arr = win_mat.sum(axis=0)
        obs_list = [int(x) for x in obs_arr.tolist()]
        chi2_stat, chi2_p = multinomial_chi_square_test(obs_arr, window_draws=window_draws)
        bf10 = dirichlet_multinomial_bf10(obs_arr, alpha0=alpha0)
        h_norm = normalized_shannon_entropy(obs_arr)
        runs_min_p, runs_max_z = wald_wolfowitz_runs_test(win_mat)
        markov_chi2, markov_p = markov_transition_chi_square_test(win_mat)

    return WindowTestResult(
        window_draws=window_draws,
        total_trials=window_draws * PRIZES_PER_DRAW,
        observed_counts=obs_list,
        chi2_stat=chi2_stat,
        chi2_p_value=chi2_p,
        bf10_dirichlet=bf10,
        normalized_entropy=h_norm,
        runs_test_min_p_value=runs_min_p,
        runs_test_max_abs_z=runs_max_z,
        markov_chi2_stat=markov_chi2,
        markov_chi2_p_value=markov_p,
    )


def run_multi_window_tests(
    counts_history: np.ndarray | Sequence[Sequence[int]],
    windows: Sequence[int] = FALSIFICATION_WINDOWS,
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE_DRAWS,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> list[WindowTestResult]:
    """Run the 4 statistical tests across all windows W in {15, 30, 60} for a single cage."""
    if not windows:
        raise DataIntegrityError("windows sequence cannot be empty.")
    if (
        isinstance(min_sample_size, bool)
        or not isinstance(min_sample_size, int)
        or min_sample_size < 2
    ):
        raise DataIntegrityError(
            f"min_sample_size must be an integer >= 2, got {min_sample_size!r}."
        )
    if (
        isinstance(alpha0, bool)
        or not isinstance(alpha0, (int, float))
        or not math.isfinite(alpha0)
        or alpha0 <= 0.0
    ):
        raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")
    clean_windows: list[int] = []
    for w in windows:
        if isinstance(w, bool) or not isinstance(w, int) or w < 2:
            raise DataIntegrityError(f"Window size must be an integer >= 2, got {w!r}.")
        clean_windows.append(w)

    required_min = max(int(min_sample_size), max(clean_windows))
    mat = validate_counts_matrix(counts_history, min_draws=required_min)

    results: list[WindowTestResult] = []
    for w in clean_windows:
        results.append(run_window_tests(mat, w, alpha0=alpha0))
    return results


def run_station_multi_window_tests(
    draws: Sequence[CanonicalDrawRecord],
    windows: Sequence[int] = FALSIFICATION_WINDOWS,
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE_DRAWS,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> dict[CageName, list[WindowTestResult]]:
    """Run multi-window statistical tests for both tens_cage and units_cage on canonical draws."""
    if (
        isinstance(min_sample_size, bool)
        or not isinstance(min_sample_size, int)
        or min_sample_size < 2
    ):
        raise DataIntegrityError(
            f"min_sample_size must be an integer >= 2, got {min_sample_size!r}."
        )
    if not isinstance(draws, Sequence) or isinstance(draws, (str, bytes)):
        raise DataIntegrityError("draws must be a sequence of CanonicalDrawRecord.")
    if len(draws) < min_sample_size:
        raise InsufficientSampleSizeError(
            f"Station draw history length {len(draws)} is below minimum {min_sample_size}."
        )
    for rec in draws:
        if not isinstance(rec, CanonicalDrawRecord):
            raise DataIntegrityError("All elements in draws must be CanonicalDrawRecord.")

    tens_mat = np.array([rec.tens_counts for rec in draws], dtype=np.int64)
    units_mat = np.array([rec.units_counts for rec in draws], dtype=np.int64)

    return {
        "tens_cage": run_multi_window_tests(
            tens_mat,
            windows=windows,
            min_sample_size=min_sample_size,
            alpha0=alpha0,
        ),
        "units_cage": run_multi_window_tests(
            units_mat,
            windows=windows,
            min_sample_size=min_sample_size,
            alpha0=alpha0,
        ),
    }
