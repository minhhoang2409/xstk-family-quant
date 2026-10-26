"""Pillar 2C: Falsification Gatekeeper (Gate 4 — Anti-White-Noise Cash Brake)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from xsmn_alpha.constants import (
    BE_PROB_2D_NUMBER,
    BE_PROB_SINGLE_BALL,
    BF10_ALPHA_THRESHOLD,
    BF10_WEAK_THRESHOLD,
    CAGE_NUM_BALLS,
    DEFAULT_MONTE_CARLO_SIMS,
    DEFAULT_RANDOM_SEED,
    DIRICHLET_PRIOR_ALPHA0,
    FALSIFICATION_WINDOWS,
    MIN_SAMPLE_SIZE_DRAWS,
    UNIFORM_BALL_PROB,
    VALID_HORIZONS,
    VALID_STATIONS,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.falsification.monte_carlo import (
    MonteCarloNullResult,
    simulate_monte_carlo_null,
)
from xsmn_alpha.falsification.stats_tests import (
    run_multi_window_tests,
    validate_counts_matrix,
)
from xsmn_alpha.schemas import (
    CageFalsificationResult,
    CageName,
    CageWindowTestResult,
    CanonicalDrawRecord,
    FalsificationReport,
    GatekeeperStatus,
    HorizonCode,
    StationCode,
    validate_probability_simplex,
)


def compute_top2_prob_and_lift(probs: Sequence[float]) -> tuple[float, float]:
    """Compute the mean probability of the Top 2 balls and relative lift vs 0.10."""
    validated = validate_probability_simplex(probs, expected_len=CAGE_NUM_BALLS)
    sorted_desc = sorted(validated, reverse=True)
    top2_mean = 0.5 * (sorted_desc[0] + sorted_desc[1])
    top2_lift = (top2_mean / UNIFORM_BALL_PROB) - 1.0
    return (float(top2_mean), float(top2_lift))


def estimate_dirichlet_calibrated_probs(
    window_results: Sequence[CageWindowTestResult],
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> list[float]:
    """Estimate Dirichlet-shrunk posterior probabilities on the strongest window W* in {15, 30, 60}.

    Formula: p_hat_i = (alpha_0 + O_i^{(W*)}) / (10 * alpha_0 + 18 * W*).
    Selects the window W* that maximizes the Top-2 shrunk posterior probability mean.
    """
    if not window_results:
        raise DataIntegrityError("window_results cannot be empty.")
    if (
        isinstance(alpha0, bool)
        or not isinstance(alpha0, (int, float))
        or not math.isfinite(alpha0)
        or alpha0 <= 0.0
    ):
        raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")

    a0 = float(alpha0)
    sum_a0 = float(CAGE_NUM_BALLS) * a0

    best_probs: list[float] | None = None
    best_top2_mean = -1.0

    for win_res in window_results:
        denom = sum_a0 + float(win_res.total_trials)
        probs_w = [(a0 + float(cnt)) / denom for cnt in win_res.observed_counts]
        top2_mean_w, _ = compute_top2_prob_and_lift(probs_w)
        if top2_mean_w > best_top2_mean:
            best_top2_mean = top2_mean_w
            best_probs = probs_w

    assert best_probs is not None
    return validate_probability_simplex(best_probs, expected_len=CAGE_NUM_BALLS)


def classify_cage_gate_status(
    *,
    observed_chi2_max: float,
    observed_bf10_max: float,
    null_chi2_max_p90: float,
    null_chi2_max_p95: float,
    top2_calibrated_prob_mean: float,
) -> tuple[GatekeeperStatus, float]:
    """Classify cage status per spec.md Section 5.3.B and return (status, capital_multiplier)."""
    strong_statistical_signal = (
        observed_chi2_max >= null_chi2_max_p95 or observed_bf10_max >= BF10_ALPHA_THRESHOLD
    )
    weak_statistical_signal = (
        observed_chi2_max >= null_chi2_max_p90 or observed_bf10_max >= BF10_WEAK_THRESHOLD
    )
    exceeds_break_even_lift = top2_calibrated_prob_mean >= BE_PROB_SINGLE_BALL

    if strong_statistical_signal and exceeds_break_even_lift:
        return ("PASS_ALPHA", 1.0)
    if strong_statistical_signal or weak_statistical_signal:
        return ("WARN_WEAK_SIGNAL", 0.25)
    return ("FAIL_WHITE_NOISE_CASH_BRAKE", 0.0)


def classify_station_overall_status(
    tens_cage: CageFalsificationResult,
    units_cage: CageFalsificationResult,
) -> tuple[GatekeeperStatus, float]:
    """Combine tens_cage and units_cage results into station-level status and multiplier."""
    combined_2d_top2_prob = (
        tens_cage.top2_calibrated_prob_mean * units_cage.top2_calibrated_prob_mean
    )
    both_pass = tens_cage.gate_status == "PASS_ALPHA" and units_cage.gate_status == "PASS_ALPHA"
    either_pass_with_2d_be = (
        tens_cage.gate_status == "PASS_ALPHA" or units_cage.gate_status == "PASS_ALPHA"
    ) and (combined_2d_top2_prob >= BE_PROB_2D_NUMBER)

    if both_pass or either_pass_with_2d_be:
        return ("PASS_ALPHA", 1.0)
    if (
        tens_cage.gate_status != "FAIL_WHITE_NOISE_CASH_BRAKE"
        or units_cage.gate_status != "FAIL_WHITE_NOISE_CASH_BRAKE"
    ):
        return ("WARN_WEAK_SIGNAL", 0.25)
    return ("FAIL_WHITE_NOISE_CASH_BRAKE", 0.0)


def evaluate_cage_falsification(
    counts_history: np.ndarray | Sequence[Sequence[int]],
    *,
    cage_name: CageName = "tens_cage",
    calibrated_probs: Sequence[float] | None = None,
    mc_null: MonteCarloNullResult | None = None,
    null_sims: int = DEFAULT_MONTE_CARLO_SIMS,
    seed: int = DEFAULT_RANDOM_SEED,
    windows: Sequence[int] = FALSIFICATION_WINDOWS,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> CageFalsificationResult:
    """Evaluate a single cage against multi-window statistical tests and 1,000 Monte Carlo Nulls."""
    if cage_name not in ("tens_cage", "units_cage"):
        raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")
    if not windows:
        raise DataIntegrityError("windows cannot be empty.")
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
            raise DataIntegrityError(f"Invalid window size {w!r}; must be integer >= 2.")
        clean_windows.append(w)

    required_min = max(MIN_SAMPLE_SIZE_DRAWS, max(clean_windows))
    mat = validate_counts_matrix(counts_history, min_draws=required_min)
    sample_size_draws = int(mat.shape[0])

    window_results = run_multi_window_tests(
        mat,
        windows=clean_windows,
        min_sample_size=required_min,
        alpha0=alpha0,
    )
    observed_chi2_max = float(max(r.chi2_stat for r in window_results))
    observed_bf10_max = float(max(r.bf10_dirichlet for r in window_results))

    if mc_null is None:
        mc_null = simulate_monte_carlo_null(
            sample_size_draws=sample_size_draws,
            null_sims=null_sims,
            seed=seed,
            windows=clean_windows,
        )

    mc_p_val = mc_null.empirical_p_value(observed_chi2_max)

    if calibrated_probs is not None:
        probs = validate_probability_simplex(calibrated_probs, expected_len=CAGE_NUM_BALLS)
    else:
        from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler

        pooler = CalibratedProbabilityPooler(alpha0=alpha0)
        probs = pooler.predict_cage(mat, cage_name=cage_name).p_ai

    top2_mean, top2_lift = compute_top2_prob_and_lift(probs)
    gate_status, cap_mult = classify_cage_gate_status(
        observed_chi2_max=observed_chi2_max,
        observed_bf10_max=observed_bf10_max,
        null_chi2_max_p90=mc_null.null_p90_chi2_max,
        null_chi2_max_p95=mc_null.null_p95_chi2_max,
        top2_calibrated_prob_mean=top2_mean,
    )

    return CageFalsificationResult(
        cage_name=cage_name,
        sample_size_draws=sample_size_draws,
        window_results=list(window_results),
        observed_chi2_max=observed_chi2_max,
        observed_bf10_max=observed_bf10_max,
        null_chi2_max_p90=mc_null.null_p90_chi2_max,
        null_chi2_max_p95=mc_null.null_p95_chi2_max,
        mc_p_value=mc_p_val,
        top2_calibrated_prob_mean=top2_mean,
        top2_calibrated_lift=top2_lift,
        gate_status=gate_status,
        recommended_capital_multiplier=cap_mult,
    )


def evaluate_station_falsification(
    draws_or_tens: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
    units_counts: np.ndarray | Sequence[Sequence[int]] | None = None,
    *,
    station_code: StationCode = "XSHCM",
    horizon: HorizonCode = "5y",
    tens_calibrated_probs: Sequence[float] | None = None,
    units_calibrated_probs: Sequence[float] | None = None,
    mc_null: MonteCarloNullResult | None = None,
    null_sims: int = DEFAULT_MONTE_CARLO_SIMS,
    seed: int = DEFAULT_RANDOM_SEED,
    windows: Sequence[int] = FALSIFICATION_WINDOWS,
    alpha0: float = DIRICHLET_PRIOR_ALPHA0,
) -> FalsificationReport:
    """Evaluate both cages of a station and produce a station-level FalsificationReport."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    if horizon not in VALID_HORIZONS:
        raise DataIntegrityError(f"Invalid horizon {horizon!r}.")

    if units_counts is None:
        if not isinstance(draws_or_tens, Sequence) or isinstance(draws_or_tens, (str, bytes)):
            raise DataIntegrityError(
                "When units_counts is omitted, draws_or_tens must be a "
                "sequence of CanonicalDrawRecord."
            )
        if len(draws_or_tens) < MIN_SAMPLE_SIZE_DRAWS:
            raise InsufficientSampleSizeError(
                f"Sample size {len(draws_or_tens)} is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
            )
        for item in draws_or_tens:
            if not isinstance(item, CanonicalDrawRecord):
                raise DataIntegrityError(
                    "All elements in draws sequence must be CanonicalDrawRecord instances."
                )
        tens_mat = np.array([d.tens_counts for d in draws_or_tens], dtype=np.int64)
        units_mat = np.array([d.units_counts for d in draws_or_tens], dtype=np.int64)
    else:
        required_min = max(MIN_SAMPLE_SIZE_DRAWS, max(int(w) for w in windows))
        tens_mat = validate_counts_matrix(draws_or_tens, min_draws=required_min)  # type: ignore[arg-type]
        units_mat = validate_counts_matrix(units_counts, min_draws=required_min)
        if tens_mat.shape[0] != units_mat.shape[0]:
            raise DataIntegrityError(
                f"tens_counts length ({tens_mat.shape[0]}) != "
                f"units_counts length ({units_mat.shape[0]})."
            )

    sample_size_draws = int(tens_mat.shape[0])
    if mc_null is None:
        mc_null = simulate_monte_carlo_null(
            sample_size_draws=sample_size_draws,
            null_sims=null_sims,
            seed=seed,
            windows=windows,
        )

    tens_res = evaluate_cage_falsification(
        tens_mat,
        cage_name="tens_cage",
        calibrated_probs=tens_calibrated_probs,
        mc_null=mc_null,
        null_sims=null_sims,
        seed=seed,
        windows=windows,
        alpha0=alpha0,
    )
    units_res = evaluate_cage_falsification(
        units_mat,
        cage_name="units_cage",
        calibrated_probs=units_calibrated_probs,
        mc_null=mc_null,
        null_sims=null_sims,
        seed=seed,
        windows=windows,
        alpha0=alpha0,
    )

    overall_status, cap_mult = classify_station_overall_status(tens_res, units_res)

    return FalsificationReport(
        station_code=station_code,
        horizon=horizon,
        sample_size_draws=sample_size_draws,
        null_simulations=mc_null.null_simulations,
        seed=mc_null.seed,
        tens_cage=tens_res,
        units_cage=units_res,
        overall_status=overall_status,
        recommended_capital_multiplier=cap_mult,
    )


class FalsificationGatekeeper:
    """Gate 4: Statistical Falsification Gatekeeper with cached Monte Carlo Null benchmarks."""

    def __init__(
        self,
        *,
        null_sims: int = DEFAULT_MONTE_CARLO_SIMS,
        seed: int = DEFAULT_RANDOM_SEED,
        windows: Sequence[int] = FALSIFICATION_WINDOWS,
        alpha0: float = DIRICHLET_PRIOR_ALPHA0,
    ) -> None:
        if isinstance(null_sims, bool) or not isinstance(null_sims, int) or null_sims <= 0:
            raise DataIntegrityError(f"null_sims must be a positive integer, got {null_sims!r}.")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise DataIntegrityError(f"seed must be an integer, got {seed!r}.")
        if not windows:
            raise DataIntegrityError("windows cannot be empty.")
        clean_windows: list[int] = []
        for w in windows:
            if isinstance(w, bool) or not isinstance(w, int) or w < 2:
                raise DataIntegrityError(f"Invalid window size {w!r}; must be integer >= 2.")
            clean_windows.append(w)
        if (
            isinstance(alpha0, bool)
            or not isinstance(alpha0, (int, float))
            or not math.isfinite(alpha0)
            or alpha0 <= 0.0
        ):
            raise DataIntegrityError(f"alpha0 must be a finite positive float, got {alpha0!r}.")

        self.null_sims = null_sims
        self.seed = seed
        self.windows = tuple(clean_windows)
        self.alpha0 = float(alpha0)
        self._null_cache: dict[int, MonteCarloNullResult] = {}

    def get_null_benchmark(self, sample_size_draws: int) -> MonteCarloNullResult:
        """Retrieve or compute the deterministic Monte Carlo Null benchmark for T draws."""
        if sample_size_draws not in self._null_cache:
            self._null_cache[sample_size_draws] = simulate_monte_carlo_null(
                sample_size_draws=sample_size_draws,
                null_sims=self.null_sims,
                seed=self.seed,
                windows=self.windows,
            )
        return self._null_cache[sample_size_draws]

    def evaluate_cage(
        self,
        counts_history: np.ndarray | Sequence[Sequence[int]],
        cage_name: CageName = "tens_cage",
        calibrated_probs: Sequence[float] | None = None,
    ) -> CageFalsificationResult:
        """Evaluate a single cage (tens_cage or units_cage) and return CageFalsificationResult."""
        required_min = max(MIN_SAMPLE_SIZE_DRAWS, max(self.windows))
        mat = validate_counts_matrix(counts_history, min_draws=required_min)
        mc_null = self.get_null_benchmark(int(mat.shape[0]))
        return evaluate_cage_falsification(
            mat,
            cage_name=cage_name,
            calibrated_probs=calibrated_probs,
            mc_null=mc_null,
            null_sims=self.null_sims,
            seed=self.seed,
            windows=self.windows,
            alpha0=self.alpha0,
        )

    def evaluate_station(
        self,
        draws_or_tens: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
        units_counts: np.ndarray | Sequence[Sequence[int]] | None = None,
        *,
        station_code: StationCode = "XSHCM",
        horizon: HorizonCode = "5y",
        tens_calibrated_probs: Sequence[float] | None = None,
        units_calibrated_probs: Sequence[float] | None = None,
    ) -> FalsificationReport:
        """Evaluate both cages of a station and return FalsificationReport."""
        if units_counts is None:
            if not isinstance(draws_or_tens, Sequence) or isinstance(draws_or_tens, (str, bytes)):
                raise DataIntegrityError(
                    "When units_counts is omitted, draws_or_tens must be a "
                    "sequence of CanonicalDrawRecord."
                )
            if len(draws_or_tens) < MIN_SAMPLE_SIZE_DRAWS:
                raise InsufficientSampleSizeError(
                    f"Sample size {len(draws_or_tens)} is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
                )
            mc_null = self.get_null_benchmark(len(draws_or_tens))
        else:
            required_min = max(MIN_SAMPLE_SIZE_DRAWS, max(self.windows))
            tens_mat = validate_counts_matrix(draws_or_tens, min_draws=required_min)  # type: ignore[arg-type]
            mc_null = self.get_null_benchmark(int(tens_mat.shape[0]))

        return evaluate_station_falsification(
            draws_or_tens,
            units_counts,
            station_code=station_code,
            horizon=horizon,
            tens_calibrated_probs=tens_calibrated_probs,
            units_calibrated_probs=units_calibrated_probs,
            mc_null=mc_null,
            null_sims=self.null_sims,
            seed=self.seed,
            windows=self.windows,
            alpha0=self.alpha0,
        )

    def falsify(
        self,
        draws_or_tens: Sequence[CanonicalDrawRecord] | np.ndarray | Sequence[Sequence[int]],
        units_counts: np.ndarray | Sequence[Sequence[int]] | None = None,
        *,
        station_code: StationCode = "XSHCM",
        horizon: HorizonCode = "5y",
        tens_calibrated_probs: Sequence[float] | None = None,
        units_calibrated_probs: Sequence[float] | None = None,
    ) -> FalsificationReport:
        """Alias for evaluate_station."""
        return self.evaluate_station(
            draws_or_tens,
            units_counts,
            station_code=station_code,
            horizon=horizon,
            tens_calibrated_probs=tens_calibrated_probs,
            units_calibrated_probs=units_calibrated_probs,
        )
