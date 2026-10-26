"""Pillar 1B: 3-Group Physical & Statistical Feature Extractor with PreDrawCutoffGate."""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from typing import Any, Literal, overload

import numpy as np

from xsmn_alpha.constants import (
    BURST_THRESHOLD_HITS,
    CAGE_NUM_BALLS,
    DEFICIT_10_EXPECTED,
    DEFICIT_10_STD,
    GAP_MEAN_MU,
    GAP_STD_SIGMA,
    LAPLACE_SMOOTHING_ALPHA,
    MARKOV_ACTIVE_THRESHOLD_HITS,
    PRIZES_PER_DRAW,
    REGIME_WINDOWS,
    UNIFORM_BALL_PROB,
)
from xsmn_alpha.exceptions import DataIntegrityError, TemporalLeakageError
from xsmn_alpha.schemas import (
    CageName,
    CanonicalDrawRecord,
    PreDrawFeatureVector,
    StationCode,
    StrictBaseModel,
    validate_two_digit_ascii,
)


def enforce_pre_draw_cutoff(
    history: Sequence[CanonicalDrawRecord],
    target_draw: CanonicalDrawRecord,
) -> None:
    """Enforce Gate 2 (PreDrawCutoffGate) to prevent look-ahead and intra-draw leakage.

    Raises TemporalLeakageError immediately if:
    - history is empty or not a sequence of CanonicalDrawRecord,
    - history is not strictly contiguous in draw_index (0 .. target_draw.draw_index - 1),
    - draw_date in history is not strictly increasing,
    - any draw in history has draw_index >= target_draw.draw_index,
      draw_date >= target_draw.draw_date, or mismatched station_code.
    """
    if not isinstance(target_draw, CanonicalDrawRecord):
        raise TemporalLeakageError(
            f"PreDrawCutoffGate: target_draw must be a CanonicalDrawRecord, "
            f"got {type(target_draw).__name__}."
        )
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)) or len(history) == 0:
        raise TemporalLeakageError(
            "PreDrawCutoffGate: history cannot be empty when extracting pre-draw features."
        )
    if target_draw.draw_index < 1:
        raise TemporalLeakageError(
            f"PreDrawCutoffGate: target_draw.draw_index must be >= 1, got {target_draw.draw_index}."
        )

    prev_date: str | None = None
    for expected_idx, rec in enumerate(history):
        if not isinstance(rec, CanonicalDrawRecord):
            raise TemporalLeakageError(
                f"PreDrawCutoffGate: history[{expected_idx}] must be CanonicalDrawRecord, "
                f"got {type(rec).__name__}."
            )
        if rec.station_code != target_draw.station_code:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate: station mismatch in history[{expected_idx}] "
                f"({rec.station_code!r} != {target_draw.station_code!r})."
            )
        if rec.draw_index >= target_draw.draw_index:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate look-ahead violation: history draw_index "
                f"{rec.draw_index} >= target_draw.draw_index {target_draw.draw_index}."
            )
        if rec.draw_date >= target_draw.draw_date:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate temporal leakage: history draw_date "
                f"{rec.draw_date!r} >= target_draw.draw_date {target_draw.draw_date!r}."
            )
        if rec.draw_index != expected_idx:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate contiguity violation at pos {expected_idx}: "
                f"expected draw_index {expected_idx}, got {rec.draw_index}."
            )
        if prev_date is not None and rec.draw_date <= prev_date:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate chronological violation in history: "
                f"{rec.draw_date!r} <= {prev_date!r}."
            )
        prev_date = rec.draw_date

    if history[-1].draw_index != target_draw.draw_index - 1:
        raise TemporalLeakageError(
            f"PreDrawCutoffGate cutoff mismatch: history[-1].draw_index "
            f"({history[-1].draw_index}) != target_draw.draw_index - 1 "
            f"({target_draw.draw_index - 1})."
        )


class PreDrawCutoffGate:
    """Gate 2 adversarial guard blocking temporal look-ahead and intra-draw leakage."""

    @staticmethod
    def enforce(
        history: Sequence[CanonicalDrawRecord],
        target_draw: CanonicalDrawRecord,
    ) -> None:
        """Enforce strict pre-draw cutoff invariants on (history, target_draw)."""
        enforce_pre_draw_cutoff(history, target_draw)

    @staticmethod
    def validate(
        history: Sequence[CanonicalDrawRecord],
        target_draw: CanonicalDrawRecord,
    ) -> None:
        """Alias for enforce(history, target_draw)."""
        enforce_pre_draw_cutoff(history, target_draw)

    def __call__(
        self,
        history: Sequence[CanonicalDrawRecord],
        target_draw: CanonicalDrawRecord,
    ) -> None:
        """Allow PreDrawCutoffGate instances to be called as a function."""
        enforce_pre_draw_cutoff(history, target_draw)


class CageFeatureVector(PreDrawFeatureVector):
    """Pre-draw feature vector for a single cage with ergonomic property and mapping aliases."""

    @property
    def deficit_z_scores(self) -> list[float]:
        """Alias for deficit_10_z_scores."""
        return self.deficit_10_z_scores

    @property
    def burst_indicators_t_minus_1(self) -> list[int]:
        """Alias for burst_rebound_indicators at draw t-1."""
        return self.burst_rebound_indicators

    @property
    def burst_rebound(self) -> list[float]:
        """Alias for historical burst_rebound_rates."""
        return self.burst_rebound_rates

    @property
    def markov_matrix(self) -> list[list[float]]:
        """Alias for 10x10 markov_transition_matrix."""
        return self.markov_transition_matrix

    @property
    def session_late_ratios(self) -> list[float]:
        """Proportion of hits in the last 9 prizes (index 9..17) at draw t-1."""
        return [1.0 - r for r in self.session_early_ratios]

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-style key lookup alongside attribute access."""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


class DualCageFeatureBundle(StrictBaseModel):
    """Combined pre-draw feature bundle for both tens_cage and units_cage at draw t."""

    station_code: StationCode
    target_draw_index: int
    target_draw_date: str
    history_length: int
    tens_cage: CageFeatureVector
    units_cage: CageFeatureVector

    @property
    def tens(self) -> CageFeatureVector:
        """Alias for tens_cage feature vector."""
        return self.tens_cage

    @property
    def units(self) -> CageFeatureVector:
        """Alias for units_cage feature vector."""
        return self.units_cage

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-style lookup by 'tens_cage', 'tens', 'units_cage', or 'units'."""
        if key in ("tens_cage", "tens"):
            return self.tens_cage
        if key in ("units_cage", "units"):
            return self.units_cage
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        """Check whether a cage or field name exists in this bundle."""
        return key in {
            "tens_cage",
            "units_cage",
            "tens",
            "units",
            "station_code",
            "target_draw_index",
            "target_draw_date",
            "history_length",
        }

    def keys(self) -> tuple[str, str]:
        """Return canonical cage keys."""
        return ("tens_cage", "units_cage")

    def values(self) -> tuple[CageFeatureVector, CageFeatureVector]:
        """Return feature vectors for (tens_cage, units_cage)."""
        return (self.tens_cage, self.units_cage)

    def items(self) -> tuple[tuple[str, CageFeatureVector], tuple[str, CageFeatureVector]]:
        """Return (cage_name, feature_vector) pairs."""
        return (("tens_cage", self.tens_cage), ("units_cage", self.units_cage))

    def __iter__(self) -> Iterator[str]:
        """Iterate over canonical cage names."""
        return iter(("tens_cage", "units_cage"))


def _validate_counts_history_array(
    counts_history: np.ndarray | Sequence[Sequence[int]],
) -> np.ndarray:
    """Validate and convert a cage counts history into an integer ndarray of shape (t, 10)."""
    if isinstance(counts_history, (str, bytes)):
        raise DataIntegrityError("counts_history must be a 2D array or sequence of count rows.")
    try:
        arr = np.asarray(counts_history)
    except Exception as exc:
        raise DataIntegrityError(f"Cannot convert counts_history to ndarray: {exc}") from exc

    if arr.size == 0 or arr.shape[0] == 0:
        raise TemporalLeakageError("PreDrawCutoffGate: counts_history cannot be empty.")
    if arr.ndim != 2 or arr.shape[1] != CAGE_NUM_BALLS:
        raise DataIntegrityError(
            f"counts_history must have shape (t, {CAGE_NUM_BALLS}), got {arr.shape}."
        )
    if np.issubdtype(arr.dtype, np.floating):
        if not np.all(np.isfinite(arr)):
            raise DataIntegrityError("counts_history contains NaN or Inf values.")
        if not np.all(arr == np.floor(arr)):
            raise DataIntegrityError("counts_history must contain integer values.")
    elif not np.issubdtype(arr.dtype, np.integer):
        raise DataIntegrityError(f"Unsupported counts_history dtype: {arr.dtype}.")

    int_arr = arr.astype(np.int64, copy=False)
    if np.any(int_arr < 0) or np.any(int_arr > PRIZES_PER_DRAW):
        raise DataIntegrityError(f"counts_history elements must be in 0..{PRIZES_PER_DRAW}.")
    row_sums = int_arr.sum(axis=1)
    if not np.all(row_sums == PRIZES_PER_DRAW):
        bad_idx = int(np.flatnonzero(row_sums != PRIZES_PER_DRAW)[0])
        raise DataIntegrityError(
            f"counts_history row {bad_idx} sum is {int(row_sums[bad_idx])}, "
            f"expected {PRIZES_PER_DRAW}."
        )
    return int_arr


def _compute_session_early_ratios(
    last_draw_counts: np.ndarray,
    prizes_last2_history: Sequence[Sequence[str]] | None,
    cage_name: CageName,
    *,
    expected_history_len: int | None = None,
) -> list[float]:
    """Compute proportion of hits in the first 9 prizes (index 0..8) at draw t-1."""
    if prizes_last2_history is None:
        return [0.5] * CAGE_NUM_BALLS
    if not isinstance(prizes_last2_history, Sequence) or isinstance(
        prizes_last2_history, (str, bytes)
    ):
        raise DataIntegrityError("prizes_last2_history must be a sequence of prize lists.")
    if len(prizes_last2_history) == 0:
        return [0.5] * CAGE_NUM_BALLS
    if expected_history_len is not None and len(prizes_last2_history) != expected_history_len:
        raise DataIntegrityError(
            f"prizes_last2_history length ({len(prizes_last2_history)}) must match "
            f"counts_history length ({expected_history_len})."
        )

    last_prizes = prizes_last2_history[-1]
    if (
        not isinstance(last_prizes, Sequence)
        or isinstance(last_prizes, (str, bytes))
        or len(last_prizes) != PRIZES_PER_DRAW
    ):
        raise DataIntegrityError(f"Last draw prizes_last2 must contain {PRIZES_PER_DRAW} prizes.")

    char_pos = 0 if cage_name == "tens_cage" else 1
    early_counts = [0] * CAGE_NUM_BALLS
    total_counts = [0] * CAGE_NUM_BALLS
    for prize_idx, token in enumerate(last_prizes):
        cleaned = validate_two_digit_ascii(token)
        digit = ord(cleaned[char_pos]) - 48
        total_counts[digit] += 1
        if prize_idx < 9:
            early_counts[digit] += 1

    expected_last = [int(x) for x in last_draw_counts.tolist()]
    if total_counts != expected_last:
        raise DataIntegrityError(
            f"Last draw prizes_last2 digit counts {total_counts} do not match "
            f"counts_history[-1] {expected_last} for {cage_name}."
        )

    ratios: list[float] = []
    for ball in range(CAGE_NUM_BALLS):
        tot = int(last_draw_counts[ball])
        if tot <= 0:
            ratios.append(0.5)
        else:
            ratios.append(float(early_counts[ball]) / float(tot))
    return ratios


def extract_cage_features(
    counts_history: np.ndarray | Sequence[Sequence[int]],
    prizes_last2_history: Sequence[Sequence[str]] | None = None,
    *,
    cage_name: CageName = "tens_cage",
    station_code: StationCode = "XSHCM",
    target_draw_index: int | None = None,
    target_draw_date: str = "2026-10-25",
    windows: Sequence[int] = REGIME_WINDOWS,
) -> CageFeatureVector:
    """Extract all 3 groups of pre-draw features for a single cage over history 0..t-1."""
    if cage_name not in ("tens_cage", "units_cage"):
        raise DataIntegrityError(f"Invalid cage_name {cage_name!r}.")

    if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)) or len(windows) == 0:
        raise DataIntegrityError("windows must be a non-empty sequence of positive integers.")
    validated_windows: list[int] = []
    for w in windows:
        if isinstance(w, bool) or not isinstance(w, int) or w < 1:
            raise DataIntegrityError(
                f"Each window in windows must be a positive integer >= 1, got {w!r}."
            )
        validated_windows.append(int(w))

    counts_mat = _validate_counts_history_array(counts_history)
    t = int(counts_mat.shape[0])
    if target_draw_index is None:
        resolved_target_idx = t
    else:
        if isinstance(target_draw_index, bool) or not isinstance(target_draw_index, int):
            raise TemporalLeakageError(
                f"PreDrawCutoffGate: target_draw_index must be an int, got {target_draw_index!r}."
            )
        if target_draw_index < t:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate violation in extract_cage_features: "
                f"target_draw_index ({target_draw_index}) < history_length ({t})."
            )
        resolved_target_idx = int(target_draw_index)

    # ------------------------------------------------------------------
    # Group 1: Regime Count Vectors & Normalized Frequencies
    # ------------------------------------------------------------------
    regime_counts: dict[int, list[int]] = {}
    regime_freqs: dict[int, list[float]] = {}
    for w_int in validated_windows:
        eff_w = min(t, w_int)
        denom = float(PRIZES_PER_DRAW * eff_w)
        win_sum = counts_mat[-eff_w:].sum(axis=0)
        counts_list = [int(x) for x in win_sum.tolist()]
        freqs_list = [float(x) / denom for x in counts_list]
        regime_counts[w_int] = counts_list
        regime_freqs[w_int] = freqs_list

    # Ensure window 10 is available for Deficit Z-Score calculation
    if 10 in regime_counts:
        counts_w10 = regime_counts[10]
    else:
        eff_10 = min(t, 10)
        counts_w10 = [int(x) for x in counts_mat[-eff_10:].sum(axis=0).tolist()]

    # ------------------------------------------------------------------
    # Group 2: Recency, Standardized Gap Z-Score & Multi-Hit Rebound
    # ------------------------------------------------------------------
    zero_hit_gaps: list[int] = []
    gap_z_scores: list[float] = []
    for ball in range(CAGE_NUM_BALLS):
        gap = 0
        for tau in range(t - 1, -1, -1):
            if counts_mat[tau, ball] == 0:
                gap += 1
            else:
                break
        zero_hit_gaps.append(gap)
        z_gap = (float(gap) - GAP_MEAN_MU) / GAP_STD_SIGMA
        gap_z_scores.append(float(z_gap))

    eff_def_w = min(t, 10)
    if eff_def_w == 10:
        expected_def_hits = DEFICIT_10_EXPECTED
        std_def_hits = DEFICIT_10_STD
    else:
        expected_def_hits = float(PRIZES_PER_DRAW) * (float(eff_def_w) / 10.0)
        std_def_hits = math.sqrt(
            float(PRIZES_PER_DRAW * eff_def_w) * UNIFORM_BALL_PROB * (1.0 - UNIFORM_BALL_PROB)
        )
    deficit_10_z_scores = [(expected_def_hits - float(c10)) / std_def_hits for c10 in counts_w10]

    last_counts = counts_mat[t - 1]
    burst_rebound_indicators = [
        1 if int(last_counts[i]) >= BURST_THRESHOLD_HITS else 0 for i in range(CAGE_NUM_BALLS)
    ]

    # Historical Laplace-smoothed per-prize hit rate at tau given n_{tau-1, i} >= 3
    burst_rebound_rates: list[float] = []
    if t >= 2:
        burst_prev = (counts_mat[:-1] >= BURST_THRESHOLD_HITS).astype(np.float64)
        next_hits = counts_mat[1:].astype(np.float64)
        for i in range(CAGE_NUM_BALLS):
            num_bursts = float(burst_prev[:, i].sum())
            rebound_hits = float((burst_prev[:, i] * next_hits[:, i]).sum())
            rate = (LAPLACE_SMOOTHING_ALPHA + rebound_hits) / (
                float(CAGE_NUM_BALLS) * LAPLACE_SMOOTHING_ALPHA
                + float(PRIZES_PER_DRAW) * num_bursts
            )
            burst_rebound_rates.append(rate)
    else:
        burst_rebound_rates = [UNIFORM_BALL_PROB] * CAGE_NUM_BALLS

    # ------------------------------------------------------------------
    # Group 3: Smoothed First-Order Markov Transitions & Session Split
    # ------------------------------------------------------------------
    if t >= 2:
        active_prev = (counts_mat[:-1] >= MARKOV_ACTIVE_THRESHOLD_HITS).astype(np.float64)
        next_counts = counts_mat[1:].astype(np.float64)
        # Transition numerators: 1.0 + sum_{tau=1}^{t-1} S_{tau-1, i} * n_{tau, j}
        trans_num = LAPLACE_SMOOTHING_ALPHA + (active_prev.T @ next_counts)
        # Transition denominators: 10.0 + 18.0 * sum_{tau=1}^{t-1} S_{tau-1, i}
        active_sums = active_prev.sum(axis=0, keepdims=True).T
        trans_den = (
            float(CAGE_NUM_BALLS) * LAPLACE_SMOOTHING_ALPHA + float(PRIZES_PER_DRAW) * active_sums
        )
        markov_arr = trans_num / trans_den
        markov_transition_matrix = [[float(val) for val in row] for row in markov_arr.tolist()]
    else:
        markov_transition_matrix = [
            [UNIFORM_BALL_PROB] * CAGE_NUM_BALLS for _ in range(CAGE_NUM_BALLS)
        ]

    session_early_ratios = _compute_session_early_ratios(
        last_draw_counts=last_counts,
        prizes_last2_history=prizes_last2_history,
        cage_name=cage_name,
        expected_history_len=t,
    )

    return CageFeatureVector(
        station_code=station_code,
        cage_name=cage_name,
        target_draw_index=resolved_target_idx,
        target_draw_date=target_draw_date,
        history_length=t,
        regime_counts=regime_counts,
        regime_freqs=regime_freqs,
        zero_hit_gaps=zero_hit_gaps,
        gap_z_scores=gap_z_scores,
        deficit_10_z_scores=deficit_10_z_scores,
        burst_rebound_indicators=burst_rebound_indicators,
        burst_rebound_rates=burst_rebound_rates,
        markov_transition_matrix=markov_transition_matrix,
        session_early_ratios=session_early_ratios,
        last_draw_counts=[int(x) for x in last_counts.tolist()],
    )


@overload
def extract_features(
    history: Sequence[CanonicalDrawRecord],
    target_draw: CanonicalDrawRecord,
    cage: None = None,
) -> DualCageFeatureBundle: ...


@overload
def extract_features(
    history: Sequence[CanonicalDrawRecord],
    target_draw: CanonicalDrawRecord,
    cage: Literal["tens", "tens_cage", "units", "units_cage"] | str,
) -> CageFeatureVector: ...


def extract_features(
    history: Sequence[CanonicalDrawRecord],
    target_draw: CanonicalDrawRecord,
    cage: str | None = None,
) -> DualCageFeatureBundle | CageFeatureVector:
    """Extract pre-draw features for target_draw strictly from history 0..t-1.

    Enforces PreDrawCutoffGate before reading any data. Notice that target_draw's
    prizes_last2 / tens_counts / units_counts are NEVER accessed.
    """
    enforce_pre_draw_cutoff(history, target_draw)

    for rec in history:
        if (
            not isinstance(rec.prizes_last2, Sequence)
            or isinstance(rec.prizes_last2, (str, bytes))
            or len(rec.prizes_last2) != PRIZES_PER_DRAW
        ):
            raise DataIntegrityError(
                f"History draw {rec.draw_date!r} must have {PRIZES_PER_DRAW} prizes_last2."
            )
        exp_t = [0] * CAGE_NUM_BALLS
        exp_u = [0] * CAGE_NUM_BALLS
        for tok in rec.prizes_last2:
            cleaned = validate_two_digit_ascii(tok)
            exp_t[ord(cleaned[0]) - 48] += 1
            exp_u[ord(cleaned[1]) - 48] += 1
        if list(rec.tens_counts) != exp_t or list(rec.units_counts) != exp_u:
            raise DataIntegrityError(
                f"History draw {rec.draw_date!r} cage counts do not match prizes_last2."
            )

    prizes_history = [rec.prizes_last2 for rec in history]

    if cage is not None:
        normalized_cage = cage.strip().lower()
        if normalized_cage in ("tens", "tens_cage"):
            tens_history = [rec.tens_counts for rec in history]
            return extract_cage_features(
                tens_history,
                prizes_history,
                cage_name="tens_cage",
                station_code=target_draw.station_code,
                target_draw_index=target_draw.draw_index,
                target_draw_date=target_draw.draw_date,
            )
        if normalized_cage in ("units", "units_cage"):
            units_history = [rec.units_counts for rec in history]
            return extract_cage_features(
                units_history,
                prizes_history,
                cage_name="units_cage",
                station_code=target_draw.station_code,
                target_draw_index=target_draw.draw_index,
                target_draw_date=target_draw.draw_date,
            )
        raise DataIntegrityError(
            f"Invalid cage selector {cage!r}; must be 'tens_cage', 'units_cage', or None."
        )

    tens_history = [rec.tens_counts for rec in history]
    units_history = [rec.units_counts for rec in history]

    tens_vec = extract_cage_features(
        tens_history,
        prizes_history,
        cage_name="tens_cage",
        station_code=target_draw.station_code,
        target_draw_index=target_draw.draw_index,
        target_draw_date=target_draw.draw_date,
    )
    units_vec = extract_cage_features(
        units_history,
        prizes_history,
        cage_name="units_cage",
        station_code=target_draw.station_code,
        target_draw_index=target_draw.draw_index,
        target_draw_date=target_draw.draw_date,
    )

    return DualCageFeatureBundle(
        station_code=target_draw.station_code,
        target_draw_index=target_draw.draw_index,
        target_draw_date=target_draw.draw_date,
        history_length=len(history),
        tens_cage=tens_vec,
        units_cage=units_vec,
    )
