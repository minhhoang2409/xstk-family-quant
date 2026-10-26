"""Pillar 2B: Deterministic 1,000 Monte Carlo Null Benchmark (PCG64 seed=42)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import Field, model_validator

from xsmn_alpha.constants import (
    CAGE_NUM_BALLS,
    DEFAULT_MONTE_CARLO_SIMS,
    DEFAULT_RANDOM_SEED,
    FALSIFICATION_WINDOWS,
    MIN_SAMPLE_SIZE_DRAWS,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.schemas import StrictBaseModel, validate_probability_simplex


class MonteCarloNullResult(StrictBaseModel):
    """Result of B=1,000 Monte Carlo Null histories for multi-window max Chi-Square."""

    sample_size_draws: int
    null_simulations: int = Field(default=DEFAULT_MONTE_CARLO_SIMS, gt=0)
    seed: int = Field(default=DEFAULT_RANDOM_SEED)
    windows: tuple[int, ...] = Field(default=FALSIFICATION_WINDOWS)
    null_chi2_max_values: list[float]
    null_p90_chi2_max: float = Field(ge=0.0)
    null_p95_chi2_max: float = Field(ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def _validate_sample_size_before(cls, data: object) -> object:
        if isinstance(data, Mapping):
            sample_size = data.get("sample_size_draws")
            if isinstance(sample_size, bool):
                raise DataIntegrityError("sample_size_draws cannot be a boolean.")
            if isinstance(sample_size, int) and sample_size < MIN_SAMPLE_SIZE_DRAWS:
                raise InsufficientSampleSizeError(
                    f"Sample size {sample_size} draws is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
                )
            for int_field in ("null_simulations", "seed"):
                if isinstance(data.get(int_field), bool):
                    raise DataIntegrityError(f"{int_field} cannot be a boolean.")
            raw_wins = data.get("windows")
            if isinstance(raw_wins, Sequence) and not isinstance(raw_wins, (str, bytes)):
                for w in raw_wins:
                    if isinstance(w, bool) or not isinstance(w, int) or w < 2:
                        raise DataIntegrityError(
                            f"Invalid window {w!r} in MonteCarloNullResult.windows."
                        )
        return data

    @model_validator(mode="after")
    def _validate_result_invariants(self) -> MonteCarloNullResult:
        if self.sample_size_draws < MIN_SAMPLE_SIZE_DRAWS:
            raise InsufficientSampleSizeError(
                f"Sample size {self.sample_size_draws} < {MIN_SAMPLE_SIZE_DRAWS}."
            )
        if len(self.null_chi2_max_values) != self.null_simulations:
            raise DataIntegrityError(
                f"len(null_chi2_max_values)={len(self.null_chi2_max_values)} != "
                f"null_simulations={self.null_simulations}."
            )
        if self.null_p95_chi2_max < self.null_p90_chi2_max:
            raise DataIntegrityError(
                f"95th percentile ({self.null_p95_chi2_max}) < "
                f"90th percentile ({self.null_p90_chi2_max})."
            )
        return self

    @property
    def p90(self) -> float:
        """Alias for null_p90_chi2_max."""
        return self.null_p90_chi2_max

    @property
    def p95(self) -> float:
        """Alias for null_p95_chi2_max."""
        return self.null_p95_chi2_max

    @property
    def null_chi2_max_p90(self) -> float:
        """Schema-aligned alias for null_p90_chi2_max."""
        return self.null_p90_chi2_max

    @property
    def null_chi2_max_p95(self) -> float:
        """Schema-aligned alias for null_p95_chi2_max."""
        return self.null_p95_chi2_max

    def empirical_p_value(self, observed_chi2_max: float) -> float:
        """Compute empirical Monte Carlo p-value against this null distribution."""
        return compute_empirical_mc_p_value(observed_chi2_max, self.null_chi2_max_values)


def compute_empirical_mc_p_value(
    observed_chi2_max: float,
    null_chi2_max_values: Sequence[float] | np.ndarray,
) -> float:
    """Compute empirical Monte Carlo p-value: (1 + sum(chi2_null >= chi2_obs)) / (B + 1)."""
    if (
        isinstance(observed_chi2_max, bool)
        or not isinstance(observed_chi2_max, (int, float))
        or not math.isfinite(float(observed_chi2_max))
        or float(observed_chi2_max) < 0.0
    ):
        raise DataIntegrityError(
            f"observed_chi2_max must be a finite non-negative float, got {observed_chi2_max!r}."
        )
    if isinstance(null_chi2_max_values, (str, bytes)):
        raise DataIntegrityError("null_chi2_max_values must be a sequence or array of floats.")

    arr = np.asarray(null_chi2_max_values, dtype=np.float64)
    if arr.ndim != 1 or arr.shape[0] == 0:
        raise DataIntegrityError("null_chi2_max_values must be a non-empty 1D numeric sequence.")
    if not np.all(np.isfinite(arr)):
        raise DataIntegrityError("null_chi2_max_values contains NaN or Inf.")

    obs = float(observed_chi2_max)
    num_Sims = int(arr.shape[0])
    exceed_count = int(np.sum(arr >= obs))
    p_mc = float(1 + exceed_count) / float(num_Sims + 1)
    return float(np.clip(p_mc, 0.0, 1.0))


def simulate_monte_carlo_null(
    sample_size_draws: int,
    *,
    null_sims: int = DEFAULT_MONTE_CARLO_SIMS,
    seed: int = DEFAULT_RANDOM_SEED,
    windows: Sequence[int] = FALSIFICATION_WINDOWS,
) -> MonteCarloNullResult:
    """Simulate B=null_sims uniform 10% draw histories of length T using PCG64(seed).

    Computes the multi-window max Chi-Square statistic across W in windows for each
    simulated history and extracts the 90th and 95th percentiles.
    """
    if isinstance(sample_size_draws, bool) or not isinstance(sample_size_draws, int):
        raise DataIntegrityError(
            f"sample_size_draws must be an integer, got {sample_size_draws!r}."
        )
    if sample_size_draws < MIN_SAMPLE_SIZE_DRAWS:
        raise InsufficientSampleSizeError(
            f"sample_size_draws={sample_size_draws} is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
        )
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
        if w > sample_size_draws:
            raise InsufficientSampleSizeError(
                f"Window size W={w} exceeds sample_size_draws={sample_size_draws}."
            )
        clean_windows.append(w)

    rng = np.random.Generator(np.random.PCG64(seed))
    uniform_probs = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)

    # Vectorized generation of (null_sims, sample_size_draws, 10) multinomial counts
    sim_histories = rng.multinomial(
        PRIZES_PER_DRAW,
        uniform_probs,
        size=(null_sims, sample_size_draws),
    )

    chi2_per_window: list[np.ndarray] = []
    for w in clean_windows:
        obs_w = sim_histories[:, -w:, :].sum(axis=1).astype(np.float64)
        expected_e = UNIFORM_BALL_PROB * float(PRIZES_PER_DRAW * w)
        chi2_w = np.sum((obs_w - expected_e) ** 2 / expected_e, axis=1)
        chi2_per_window.append(chi2_w)

    chi2_max_arr = np.max(np.vstack(chi2_per_window), axis=0)
    p90 = float(np.percentile(chi2_max_arr, 90.0))
    p95 = float(np.percentile(chi2_max_arr, 95.0))

    return MonteCarloNullResult(
        sample_size_draws=sample_size_draws,
        null_simulations=null_sims,
        seed=seed,
        windows=tuple(clean_windows),
        null_chi2_max_values=[float(x) for x in chi2_max_arr.tolist()],
        null_p90_chi2_max=p90,
        null_p95_chi2_max=p95,
    )


def generate_synthetic_cage_history(
    sample_size_draws: int,
    ball_probs: Sequence[float] | None = None,
    *,
    seed: int = DEFAULT_RANDOM_SEED,
) -> np.ndarray:
    """Generate a synthetic (T, 10) cage draw count matrix using PCG64(seed)."""
    if isinstance(sample_size_draws, bool) or not isinstance(sample_size_draws, int):
        raise DataIntegrityError(
            f"sample_size_draws must be an integer, got {sample_size_draws!r}."
        )
    if sample_size_draws < MIN_SAMPLE_SIZE_DRAWS:
        raise InsufficientSampleSizeError(
            f"sample_size_draws={sample_size_draws} is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
        )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise DataIntegrityError(f"seed must be an integer, got {seed!r}.")

    if ball_probs is None:
        probs = [UNIFORM_BALL_PROB] * CAGE_NUM_BALLS
    else:
        probs = validate_probability_simplex(ball_probs, expected_len=CAGE_NUM_BALLS)

    rng = np.random.Generator(np.random.PCG64(seed))
    counts = rng.multinomial(
        PRIZES_PER_DRAW,
        np.asarray(probs, dtype=np.float64),
        size=sample_size_draws,
    )
    return counts.astype(np.int64)
