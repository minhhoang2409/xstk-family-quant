"""Pydantic v2 Fail-Closed Schemas and Adversarial Gates for Stage 2 XSMN Alpha Discovery."""

from __future__ import annotations

import datetime
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    BE_PROB_2D_NUMBER,
    BE_PROB_SINGLE_BALL,
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    BENCHMARK_PAYOUT_PER_HIT_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    BF10_ALPHA_THRESHOLD,
    CAGE_ANOMALY_BF10_THRESHOLD,
    CAGE_NUM_BALLS,
    HOUSE_MONEY_MAX_SURPLUS_FRACTION,
    HOUSE_MONEY_MIN_BUFFER_DAYS,
    KELLY_NUM_STATES,
    MIN_SAMPLE_SIZE_DRAWS,
    PEAK_CONVICTION_JOINT_R1_PCT,
    PRIZES_PER_DRAW,
    REAL_PAYOUT_1D,
    SELECTIVE_ALPHA_JOINT_R1_MIN_PCT,
    SIMPLEX_TOLERANCE,
    STAGE4_MAX_STAKE_MULTIPLIER,
    STAGE4_SWEET_SPOT_CONFIGS,
    STAGE4_TICKET_CONFIGS,
    SWEET_SPOT_CONFIGS,
    UNIFORM_BALL_PROB,
    VALID_HORIZONS,
    VALID_STATIONS,
    WEEKLY_SCHEDULE_PLAY_DAYS,
    WEEKLY_SCHEDULE_REST_DAYS,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    CapitalDisciplineError,
    DataIntegrityError,
    InsufficientSampleSizeError,
    TemporalLeakageError,
)

StationCode = Literal["XSHCM", "XSVL"]
HorizonCode = Literal["5y", "3y"]
CageName = Literal["tens_cage", "units_cage"]
GatekeeperStatus = Literal[
    "PASS_ALPHA",
    "WARN_WEAK_SIGNAL",
    "FAIL_WHITE_NOISE_CASH_BRAKE",
]

_ASCII_TWO_DIGIT_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)


def validate_two_digit_ascii(token: Any) -> str:
    """Validate that a token is strictly a 2-digit ASCII string '00'..'99'."""
    if (
        not isinstance(token, str)
        or not token.isascii()
        or not _ASCII_TWO_DIGIT_RE.fullmatch(token)
    ):
        raise DataIntegrityError(
            f"Invalid 2-digit prize token {token!r}; must match strict ASCII '^[0-9]{{2}}$'."
        )
    return token


def validate_iso_date(date_str: Any) -> str:
    """Validate that a string is a strict ASCII YYYY-MM-DD calendar date."""
    if (
        not isinstance(date_str, str)
        or not date_str.isascii()
        or not _ISO_DATE_RE.fullmatch(date_str)
    ):
        raise DataIntegrityError(
            f"Invalid draw_date {date_str!r}; must be strict ASCII ISO format 'YYYY-MM-DD'."
        )
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError as exc:
        raise DataIntegrityError(f"Invalid calendar date {date_str!r}: {exc}") from exc
    return date_str


def _is_valid_2x2_cartesian_core(nums: Sequence[str]) -> bool:
    """Return True iff nums is 4 unique 2-digit strings forming {a1, a2} x {b1, b2}."""
    if len(nums) != 4 or len(set(nums)) != 4:
        return False
    tens_digits = {n[0] for n in nums}
    units_digits = {n[1] for n in nums}
    if len(tens_digits) != 2 or len(units_digits) != 2:
        return False
    expected = {f"{a}{b}" for a in tens_digits for b in units_digits}
    return set(nums) == expected


def _contains_2x2_cartesian_subset(nums_5: Sequence[str]) -> bool:
    """Return True iff 5 unique 2-digit numbers contain at least one 2x2 Cartesian rectangle."""
    if len(nums_5) != 5 or len(set(nums_5)) != 5:
        return False
    items = list(nums_5)
    for skip_idx in range(5):
        subset_4 = [items[i] for i in range(5) if i != skip_idx]
        if _is_valid_2x2_cartesian_core(subset_4):
            return True
    return False


def validate_probability_simplex(
    probs: Sequence[float],
    expected_len: int = CAGE_NUM_BALLS,
    tol: float | None = None,
) -> list[float]:
    """Enforce Gate 3 (SimplexCalibrationGate) on a discrete probability distribution."""
    if not isinstance(probs, Sequence) or isinstance(probs, (str, bytes)):
        raise CalibrationIntegrityError("Probability distribution must be a sequence of floats.")
    if len(probs) != expected_len:
        raise CalibrationIntegrityError(
            f"Expected probability vector of length {expected_len}, got {len(probs)}."
        )
    eff_tol = float(tol) if tol is not None else SIMPLEX_TOLERANCE * CAGE_NUM_BALLS
    cleaned: list[float] = []
    for idx, val in enumerate(probs):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise CalibrationIntegrityError(
                f"Probability element at index {idx} is not numeric: {val!r}."
            )
        fval = float(val)
        if not math.isfinite(fval):
            raise CalibrationIntegrityError(
                f"Probability element at index {idx} is non-finite ({fval})."
            )
        if fval < -1e-9 or fval > 1.0 + eff_tol:
            raise CalibrationIntegrityError(
                f"Probability element at index {idx} out of [0, 1] bounds: {fval}."
            )
        cleaned.append(0.0 if fval < 0.0 else fval)

    total = math.fsum(cleaned)
    if abs(total - 1.0) > eff_tol or total <= 0.0:
        raise CalibrationIntegrityError(
            f"Probability simplex sum violation: sum={total:.9f} (tolerance={eff_tol})."
        )
    return [x / total for x in cleaned]


def validate_pooling_weights(
    w1: float,
    w2: float,
    tol: float = SIMPLEX_TOLERANCE,
) -> tuple[float, float]:
    """Enforce Gate 3 (SimplexCalibrationGate) on convex pooling weights (w1, w2)."""
    if (
        isinstance(w1, bool)
        or isinstance(w2, bool)
        or not isinstance(w1, (int, float))
        or not isinstance(w2, (int, float))
    ):
        raise CalibrationIntegrityError("Pooling weights (w1, w2) must be numeric floats.")
    fw1, fw2 = float(w1), float(w2)
    if not (math.isfinite(fw1) and math.isfinite(fw2)):
        raise CalibrationIntegrityError(f"Non-finite pooling weights: ({fw1}, {fw2}).")
    if fw1 < -tol or fw2 < -tol:
        raise CalibrationIntegrityError(
            f"Negative pooling weights forbidden: w1={fw1:.6f}, w2={fw2:.6f}."
        )
    if fw1 + fw2 > 1.0 + tol:
        raise CalibrationIntegrityError(
            f"Convex pooling weights exceed 1.0: w1 + w2 = {fw1 + w2:.6f} > 1.0."
        )
    cw1 = 0.0 if fw1 < 0.0 else fw1
    cw2 = 0.0 if fw2 < 0.0 else fw2
    w_sum = cw1 + cw2
    if w_sum > 1.0:
        cw1 /= w_sum
        cw2 /= w_sum
    return (cw1, cw2)


class StrictBaseModel(BaseModel):
    """Base Pydantic v2 model enforcing strict fail-closed validation."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        validate_assignment=True,
    )


class CanonicalDrawRecord(StrictBaseModel):
    """Canonical representation of 1 XSMN draw (18 prizes) decomposed into 2 cages."""

    station_code: StationCode
    draw_date: str
    draw_index: int
    prizes_last2: list[str]
    tens_counts: list[int]
    units_counts: list[int]

    @model_validator(mode="before")
    @classmethod
    def _gate1_data_schema_precheck(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        data = dict(data)

        allowed_keys = {
            "station_code",
            "draw_date",
            "draw_index",
            "prizes_last2",
            "tens_counts",
            "units_counts",
        }
        extra_keys = set(data.keys()) - allowed_keys
        if extra_keys:
            raise DataIntegrityError(
                f"Unexpected extra fields in CanonicalDrawRecord: {sorted(extra_keys)}"
            )

        station = data.get("station_code")
        if station not in VALID_STATIONS:
            raise DataIntegrityError(
                f"Invalid station_code {station!r}; must be one of {sorted(VALID_STATIONS)}."
            )

        validate_iso_date(data.get("draw_date"))

        draw_index = data.get("draw_index")
        if isinstance(draw_index, bool) or not isinstance(draw_index, int) or draw_index < 0:
            raise DataIntegrityError(
                f"Invalid draw_index {draw_index!r}; must be a non-negative integer."
            )

        prizes = data.get("prizes_last2")
        if (
            not isinstance(prizes, Sequence)
            or isinstance(prizes, (str, bytes))
            or len(prizes) != PRIZES_PER_DRAW
        ):
            count = len(prizes) if isinstance(prizes, Sequence) else "non-sequence"
            raise DataIntegrityError(
                f"prizes_last2 must contain exactly {PRIZES_PER_DRAW} prizes, got {count}."
            )
        for token in prizes:
            validate_two_digit_ascii(token)

        for field_name in ("tens_counts", "units_counts"):
            vec = data.get(field_name)
            if (
                not isinstance(vec, Sequence)
                or isinstance(vec, (str, bytes))
                or len(vec) != CAGE_NUM_BALLS
            ):
                raise DataIntegrityError(
                    f"{field_name} must be a 10-element integer list, got {vec!r}."
                )
            for item in vec:
                if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 18:
                    raise DataIntegrityError(
                        f"Invalid count element {item!r} in {field_name}; must be int in 0..18."
                    )
            if sum(vec) != PRIZES_PER_DRAW:
                raise DataIntegrityError(
                    f"{field_name} sum must equal {PRIZES_PER_DRAW}, got {sum(vec)}."
                )

        return data

    @model_validator(mode="after")
    def _gate1_verify_counts_match_prizes(self) -> CanonicalDrawRecord:
        if self.station_code not in VALID_STATIONS:
            raise DataIntegrityError(
                f"Invalid station_code {self.station_code!r}; "
                f"must be one of {sorted(VALID_STATIONS)}."
            )
        validate_iso_date(self.draw_date)
        if (
            isinstance(self.draw_index, bool)
            or not isinstance(self.draw_index, int)
            or self.draw_index < 0
        ):
            raise DataIntegrityError(
                f"Invalid draw_index {self.draw_index!r}; must be a non-negative integer."
            )
        if len(self.prizes_last2) != PRIZES_PER_DRAW:
            raise DataIntegrityError(
                f"prizes_last2 must contain {PRIZES_PER_DRAW} prizes, got {len(self.prizes_last2)}."
            )

        expected_tens = [0] * CAGE_NUM_BALLS
        expected_units = [0] * CAGE_NUM_BALLS
        for prize in self.prizes_last2:
            validate_two_digit_ascii(prize)
            expected_tens[ord(prize[0]) - 48] += 1
            expected_units[ord(prize[1]) - 48] += 1

        if len(self.tens_counts) != CAGE_NUM_BALLS or self.tens_counts != expected_tens:
            raise DataIntegrityError(
                f"tens_counts {self.tens_counts} does not match prizes_last2 {expected_tens}."
            )
        if len(self.units_counts) != CAGE_NUM_BALLS or self.units_counts != expected_units:
            raise DataIntegrityError(
                f"units_counts {self.units_counts} does not match prizes_last2 {expected_units}."
            )
        return self

    @classmethod
    def from_prizes(
        cls,
        station_code: StationCode,
        draw_date: str,
        draw_index: int,
        prizes_last2: Sequence[str],
    ) -> CanonicalDrawRecord:
        """Construct a validated CanonicalDrawRecord by computing cage counts from 18 prizes."""
        if (
            not isinstance(prizes_last2, Sequence)
            or isinstance(prizes_last2, (str, bytes))
            or len(prizes_last2) != PRIZES_PER_DRAW
        ):
            raise DataIntegrityError(f"prizes_last2 must contain exactly {PRIZES_PER_DRAW} prizes.")
        cleaned_prizes = [validate_two_digit_ascii(p) for p in prizes_last2]
        tens_counts = [0] * CAGE_NUM_BALLS
        units_counts = [0] * CAGE_NUM_BALLS
        for prize in cleaned_prizes:
            tens_counts[ord(prize[0]) - 48] += 1
            units_counts[ord(prize[1]) - 48] += 1
        return cls(
            station_code=station_code,
            draw_date=draw_date,
            draw_index=draw_index,
            prizes_last2=cleaned_prizes,
            tens_counts=tens_counts,
            units_counts=units_counts,
        )


class PreDrawFeatureVector(StrictBaseModel):
    """Pillar 1B: 3-group physical and statistical feature vector locked at cutoff t-1."""

    station_code: StationCode
    cage_name: CageName
    target_draw_index: int = Field(ge=1)
    target_draw_date: str
    history_length: int = Field(ge=1)
    regime_counts: dict[int, list[int]]
    regime_freqs: dict[int, list[float]]
    zero_hit_gaps: list[int]
    gap_z_scores: list[float]
    deficit_10_z_scores: list[float]
    burst_rebound_indicators: list[int]
    burst_rebound_rates: list[float]
    markov_transition_matrix: list[list[float]]
    session_early_ratios: list[float]
    last_draw_counts: list[int] | None = Field(
        default=None,
        description="Optional 10-ball count vector at draw t-1 (sum == 18).",
    )

    @field_validator("target_draw_date")
    @classmethod
    def _check_date(cls, v: str) -> str:
        return validate_iso_date(v)

    @model_validator(mode="after")
    def _validate_feature_dimensions(self) -> PreDrawFeatureVector:
        if self.target_draw_index < self.history_length:
            raise DataIntegrityError(
                f"target_draw_index ({self.target_draw_index}) < "
                f"history_length ({self.history_length})."
            )
        for vec_name in (
            "zero_hit_gaps",
            "gap_z_scores",
            "deficit_10_z_scores",
            "burst_rebound_indicators",
            "burst_rebound_rates",
            "session_early_ratios",
        ):
            vec = getattr(self, vec_name)
            if len(vec) != CAGE_NUM_BALLS:
                raise DataIntegrityError(
                    f"{vec_name} must have length {CAGE_NUM_BALLS}, got {len(vec)}."
                )

        for idx, g in enumerate(self.zero_hit_gaps):
            if isinstance(g, bool) or not isinstance(g, int) or g < 0 or g > self.history_length:
                raise DataIntegrityError(
                    f"zero_hit_gaps[{idx}]={g!r} must be in 0..{self.history_length}."
                )
        for idx, ind in enumerate(self.burst_rebound_indicators):
            if isinstance(ind, bool) or ind not in (0, 1):
                raise DataIntegrityError(f"burst_rebound_indicators[{idx}]={ind!r} must be 0 or 1.")
        for vec_name in ("burst_rebound_rates", "session_early_ratios"):
            vec = getattr(self, vec_name)
            for idx, r in enumerate(vec):
                if isinstance(r, bool) or not math.isfinite(r) or r < 0.0 or r > 1.0:
                    raise DataIntegrityError(f"{vec_name}[{idx}]={r!r} must be in [0.0, 1.0].")

        if not self.regime_counts or set(self.regime_counts.keys()) != set(
            self.regime_freqs.keys()
        ):
            raise DataIntegrityError(
                "regime_counts and regime_freqs must be non-empty with identical window keys."
            )
        for w, counts_vec in self.regime_counts.items():
            if isinstance(w, bool) or not isinstance(w, int) or w < 1:
                raise DataIntegrityError(f"Invalid regime window key {w!r}; must be int >= 1.")
            freqs_vec = self.regime_freqs[w]
            if len(counts_vec) != CAGE_NUM_BALLS or len(freqs_vec) != CAGE_NUM_BALLS:
                raise DataIntegrityError(
                    f"regime_counts[{w}] and regime_freqs[{w}] must have length {CAGE_NUM_BALLS}."
                )
            eff_w = min(w, self.history_length)
            expected_sum = PRIZES_PER_DRAW * eff_w
            for c in counts_vec:
                if isinstance(c, bool) or not isinstance(c, int) or c < 0 or c > expected_sum:
                    raise DataIntegrityError(
                        f"Invalid count {c!r} in regime_counts[{w}]; must be in 0..{expected_sum}."
                    )
            if sum(counts_vec) != expected_sum:
                raise DataIntegrityError(
                    f"sum(regime_counts[{w}])={sum(counts_vec)} != 18 * min(w, T) ({expected_sum})."
                )
            for f in freqs_vec:
                if isinstance(f, bool) or not math.isfinite(f) or f < 0.0 or f > 1.0:
                    raise DataIntegrityError(
                        f"Invalid frequency {f!r} in regime_freqs[{w}]; must be in [0.0, 1.0]."
                    )
            if abs(math.fsum(freqs_vec) - 1.0) > SIMPLEX_TOLERANCE:
                raise DataIntegrityError(
                    f"regime_freqs[{w}] sum={math.fsum(freqs_vec):.9f} violates simplex."
                )

        if self.last_draw_counts is not None:
            if len(self.last_draw_counts) != CAGE_NUM_BALLS:
                raise DataIntegrityError(
                    f"last_draw_counts must have length {CAGE_NUM_BALLS}, "
                    f"got {len(self.last_draw_counts)}."
                )
            for item in self.last_draw_counts:
                if (
                    isinstance(item, bool)
                    or not isinstance(item, int)
                    or item < 0
                    or item > PRIZES_PER_DRAW
                ):
                    raise DataIntegrityError(
                        f"Invalid element {item!r} in last_draw_counts; must be int in 0..18."
                    )
            if sum(self.last_draw_counts) != PRIZES_PER_DRAW:
                raise DataIntegrityError(
                    f"sum(last_draw_counts) must equal {PRIZES_PER_DRAW}, "
                    f"got {sum(self.last_draw_counts)}."
                )

        if len(self.markov_transition_matrix) != CAGE_NUM_BALLS:
            raise DataIntegrityError("markov_transition_matrix must have 10 rows.")
        for row in self.markov_transition_matrix:
            validate_probability_simplex(row, expected_len=CAGE_NUM_BALLS)
        return self


class CageWindowTestResult(StrictBaseModel):
    """Pillar 2: Statistical test results for a single cage over window W in {15, 30, 60}."""

    window_draws: int = Field(gt=0)
    total_trials: int = Field(gt=0)
    observed_counts: list[int]
    chi2_stat: float = Field(ge=0.0)
    chi2_p_value: float = Field(ge=0.0, le=1.0)
    bf10_dirichlet: float = Field(gt=0.0)
    normalized_entropy: float = Field(ge=0.0, le=1.000001)
    runs_test_min_p_value: float = Field(ge=0.0, le=1.0)
    runs_test_max_abs_z: float = Field(default=0.0, ge=0.0)
    markov_chi2_stat: float = Field(ge=0.0)
    markov_chi2_p_value: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_window_invariants(self) -> CageWindowTestResult:
        expected_trials = self.window_draws * PRIZES_PER_DRAW
        if self.total_trials != expected_trials:
            raise DataIntegrityError(
                f"total_trials ({self.total_trials}) != 18 * window_draws ({expected_trials})."
            )
        if len(self.observed_counts) != CAGE_NUM_BALLS:
            raise DataIntegrityError("observed_counts must have 10 elements.")
        if sum(self.observed_counts) != expected_trials:
            raise DataIntegrityError(
                f"sum(observed_counts)={sum(self.observed_counts)} != {expected_trials}."
            )
        return self


class CageFalsificationResult(StrictBaseModel):
    """Pillar 2: Multi-window falsification and Monte Carlo Null comparison for 1 cage."""

    cage_name: CageName
    sample_size_draws: int
    window_results: list[CageWindowTestResult]
    observed_chi2_max: float = Field(ge=0.0)
    observed_bf10_max: float = Field(gt=0.0)
    null_chi2_max_p90: float = Field(ge=0.0)
    null_chi2_max_p95: float = Field(ge=0.0)
    mc_p_value: float = Field(ge=0.0, le=1.0)
    top2_calibrated_prob_mean: float = Field(default=0.10, ge=0.0, le=1.0)
    top2_calibrated_lift: float = Field(default=0.0)
    gate_status: GatekeeperStatus
    recommended_capital_multiplier: float = Field(ge=0.0)

    @field_validator("window_results", mode="before")
    @classmethod
    def _coerce_dict_window_results(cls, v: Any) -> Any:
        if isinstance(v, Mapping):
            return list(v.values())
        return v

    @model_validator(mode="before")
    @classmethod
    def _check_sample_size_before(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            data = dict(data)
            sample_size = data.get("sample_size_draws")
            if (
                isinstance(sample_size, int)
                and not isinstance(sample_size, bool)
                and sample_size < MIN_SAMPLE_SIZE_DRAWS
            ):
                raise InsufficientSampleSizeError(
                    f"Sample size {sample_size} draws is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
                )
        return data

    @model_validator(mode="after")
    def _validate_gatekeeper_rules(self) -> CageFalsificationResult:
        if self.sample_size_draws < MIN_SAMPLE_SIZE_DRAWS:
            raise InsufficientSampleSizeError(
                f"Sample size {self.sample_size_draws} < {MIN_SAMPLE_SIZE_DRAWS}."
            )
        if len(self.window_results) == 0:
            raise DataIntegrityError("window_results cannot be empty.")
        if (
            self.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.recommended_capital_multiplier != 0.0
        ):
            raise DataIntegrityError(
                "FAIL_WHITE_NOISE_CASH_BRAKE requires recommended_capital_multiplier == 0.0."
            )
        if self.gate_status == "PASS_ALPHA":
            if (
                self.mc_p_value > 0.05 + 1e-9
                or self.observed_bf10_max < BF10_ALPHA_THRESHOLD - 1e-9
            ):
                raise DataIntegrityError(
                    "PASS_ALPHA requires mc_p_value <= 0.05 and observed_bf10_max >= 3.0."
                )
            if self.top2_calibrated_prob_mean < BE_PROB_SINGLE_BALL - 1e-9:
                raise DataIntegrityError(
                    f"PASS_ALPHA requires top2_calibrated_prob_mean >= {BE_PROB_SINGLE_BALL:.6f}."
                )
            if self.recommended_capital_multiplier <= 0.0:
                raise DataIntegrityError(
                    "PASS_ALPHA requires recommended_capital_multiplier > 0.0."
                )
        return self


class FalsificationReport(StrictBaseModel):
    """Pillar 2: Station-level falsification report combining tens_cage and units_cage."""

    station_code: StationCode
    horizon: HorizonCode
    sample_size_draws: int
    null_simulations: int = Field(default=1000, gt=0)
    seed: int = Field(default=42)
    tens_cage: CageFalsificationResult
    units_cage: CageFalsificationResult
    overall_status: GatekeeperStatus
    recommended_capital_multiplier: float = Field(ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def _check_sample_size_before(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            data = dict(data)
            sample_size = data.get("sample_size_draws")
            if (
                isinstance(sample_size, int)
                and not isinstance(sample_size, bool)
                and sample_size < MIN_SAMPLE_SIZE_DRAWS
            ):
                raise InsufficientSampleSizeError(
                    f"Sample size {sample_size} draws is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
                )
        return data

    @model_validator(mode="after")
    def _validate_report_consistency(self) -> FalsificationReport:
        if self.tens_cage.cage_name != "tens_cage":
            raise DataIntegrityError("tens_cage field must have cage_name == 'tens_cage'.")
        if self.units_cage.cage_name != "units_cage":
            raise DataIntegrityError("units_cage field must have cage_name == 'units_cage'.")

        both_fail = (
            self.tens_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.units_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        )
        if both_fail and self.overall_status != "FAIL_WHITE_NOISE_CASH_BRAKE":
            raise DataIntegrityError(
                "When both cages are FAIL_WHITE_NOISE_CASH_BRAKE, "
                "overall_status must be FAIL_WHITE_NOISE_CASH_BRAKE."
            )
        if not both_fail and self.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE":
            raise DataIntegrityError(
                "overall_status cannot be FAIL_WHITE_NOISE_CASH_BRAKE when a cage has signal."
            )

        both_pass = (
            self.tens_cage.gate_status == "PASS_ALPHA"
            and self.units_cage.gate_status == "PASS_ALPHA"
        )
        either_pass = (
            self.tens_cage.gate_status == "PASS_ALPHA"
            or self.units_cage.gate_status == "PASS_ALPHA"
        )
        combined_2d = (
            self.tens_cage.top2_calibrated_prob_mean * self.units_cage.top2_calibrated_prob_mean
        )
        if (both_pass or (either_pass and combined_2d >= BE_PROB_2D_NUMBER - 1e-9)) and (
            self.overall_status != "PASS_ALPHA"
        ):
            raise DataIntegrityError(
                "overall_status must be PASS_ALPHA when cage alpha criteria are met."
            )
        if self.overall_status == "PASS_ALPHA" and not either_pass:
            raise DataIntegrityError(
                "overall_status cannot be PASS_ALPHA when neither cage is PASS_ALPHA."
            )

        if (
            self.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.recommended_capital_multiplier != 0.0
        ):
            raise DataIntegrityError(
                "FAIL_WHITE_NOISE_CASH_BRAKE requires recommended_capital_multiplier == 0.0."
            )
        if (
            self.overall_status != "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.recommended_capital_multiplier <= 0.0
        ):
            raise DataIntegrityError(
                f"{self.overall_status} requires recommended_capital_multiplier > 0.0."
            )
        return self


class CalibratedCagePrediction(StrictBaseModel):
    """Pillar 3: Calibrated 10-ball probability prediction for a single cage at draw t."""

    cage_name: CageName
    target_draw_index: int = Field(ge=0)
    target_draw_date: str
    p_bocd: list[float]
    p_seq: list[float]
    p_ai: list[float]
    weights: tuple[float, float]
    uniform_weight: float
    ranked_balls: list[int]
    top2_mean_prob: float = Field(ge=0.0, le=1.0)
    top2_lift_vs_uniform: float
    exceeds_break_even_ball_threshold: bool
    conviction_score: float = Field(ge=0.0)
    oos_brier_score: float = Field(default=0.0, ge=0.0)
    naive_brier_score: float = Field(default=0.0, ge=0.0)
    map_run_length: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _gate3_simplex_precheck(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)
        for prob_key in ("p_bocd", "p_seq", "p_ai"):
            if prob_key in copied:
                copied[prob_key] = validate_probability_simplex(
                    copied[prob_key], expected_len=CAGE_NUM_BALLS
                )
        if "weights" in copied:
            w = copied["weights"]
            if not isinstance(w, Sequence) or isinstance(w, (str, bytes)) or len(w) != 2:
                raise CalibrationIntegrityError(f"weights must be a 2-tuple (w1, w2), got {w!r}.")
            w1, w2 = validate_pooling_weights(w[0], w[1])
            copied["weights"] = (w1, w2)
        return copied

    @field_validator("target_draw_date")
    @classmethod
    def _check_date(cls, v: str) -> str:
        return validate_iso_date(v)

    @model_validator(mode="after")
    def _gate3_verify_calibration_invariants(self) -> CalibratedCagePrediction:
        validate_probability_simplex(self.p_bocd, expected_len=CAGE_NUM_BALLS)
        validate_probability_simplex(self.p_seq, expected_len=CAGE_NUM_BALLS)
        validate_probability_simplex(self.p_ai, expected_len=CAGE_NUM_BALLS)
        w1, w2 = validate_pooling_weights(self.weights[0], self.weights[1])
        if (
            isinstance(self.uniform_weight, bool)
            or not math.isfinite(self.uniform_weight)
            or self.uniform_weight < 0.0
            or self.uniform_weight > 1.0 + SIMPLEX_TOLERANCE
        ):
            raise CalibrationIntegrityError(
                f"uniform_weight must be in [0.0, 1.0], got {self.uniform_weight}."
            )
        if abs((w1 + w2 + self.uniform_weight) - 1.0) > SIMPLEX_TOLERANCE:
            raise CalibrationIntegrityError(
                f"Pooling weights must sum to 1.0: "
                f"w1={w1}, w2={w2}, uniform_weight={self.uniform_weight}."
            )
        for idx in range(CAGE_NUM_BALLS):
            expected_p = (
                w1 * self.p_bocd[idx]
                + w2 * self.p_seq[idx]
                + self.uniform_weight * UNIFORM_BALL_PROB
            )
            if abs(self.p_ai[idx] - expected_p) > 1e-4:
                raise CalibrationIntegrityError(
                    f"p_ai[{idx}]={self.p_ai[idx]:.6f} does not match convex combination "
                    f"{expected_p:.6f} (diff={abs(self.p_ai[idx] - expected_p):.6f} > 1e-4)."
                )
        if (
            len(self.ranked_balls) != CAGE_NUM_BALLS
            or any(isinstance(b, bool) or not isinstance(b, int) for b in self.ranked_balls)
            or set(self.ranked_balls) != set(range(CAGE_NUM_BALLS))
        ):
            raise CalibrationIntegrityError(
                f"ranked_balls must be a permutation of 0..9, got {self.ranked_balls}."
            )
        for rank_idx in range(CAGE_NUM_BALLS - 1):
            b_curr = self.ranked_balls[rank_idx]
            b_next = self.ranked_balls[rank_idx + 1]
            if self.p_ai[b_curr] + 1e-9 < self.p_ai[b_next]:
                raise CalibrationIntegrityError(
                    f"ranked_balls not sorted in non-increasing order of p_ai at rank {rank_idx}: "
                    f"ball {b_curr} (p_ai={self.p_ai[b_curr]:.6f}) < "
                    f"ball {b_next} (p_ai={self.p_ai[b_next]:.6f})."
                )
        return self


class SweetSpotPortfolioMetrics(StrictBaseModel):
    """Pillar 4: Out-of-sample walk-forward performance metrics for a Sweet-Spot config."""

    config_id: str
    game_type: str
    evaluated_draws: int = Field(gt=0)
    cost_per_draw: float = Field(gt=0.0)
    total_cost: float = Field(ge=0.0)
    total_revenue: float = Field(ge=0.0)
    net_profit: float
    roi_pct: float
    total_hits: float = Field(ge=0.0)
    hits_per_30_draws: float = Field(ge=0.0)
    break_even_hits_30_draws: float = Field(gt=0.0)
    daily_win_rate: float = Field(ge=0.0, le=1.0)
    multi_hit_rate_ge2: float = Field(ge=0.0, le=1.0)
    zero_hit_rate_k0: float = Field(ge=0.0, le=1.0)
    max_losing_streak: int = Field(ge=0)
    max_drawdown: float = Field(ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def _precheck_rate_bounds(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            copied = dict(data)
            for rate_key in ("daily_win_rate", "multi_hit_rate_ge2", "zero_hit_rate_k0"):
                if rate_key in copied:
                    val = copied[rate_key]
                    if (
                        isinstance(val, bool)
                        or not isinstance(val, (int, float))
                        or not math.isfinite(float(val))
                        or float(val) < 0.0
                        or float(val) > 1.0
                    ):
                        raise DataIntegrityError(f"{rate_key} must be in [0.0, 1.0], got {val!r}.")
            return copied
        return data

    @field_validator("config_id")
    @classmethod
    def _validate_config_id(cls, v: str) -> str:
        if v not in STAGE4_SWEET_SPOT_CONFIGS:
            raise DataIntegrityError(
                f"Unknown portfolio config_id {v!r}; "
                f"must be in {sorted(STAGE4_SWEET_SPOT_CONFIGS)}."
            )
        return v

    @model_validator(mode="after")
    def _validate_rate_consistency(self) -> SweetSpotPortfolioMetrics:
        if self.daily_win_rate + self.zero_hit_rate_k0 > 1.0 + 1e-6:
            raise DataIntegrityError(
                f"SweetSpotPortfolioMetrics daily_win_rate ({self.daily_win_rate}) + "
                f"zero_hit_rate_k0 ({self.zero_hit_rate_k0}) cannot exceed 1.0."
            )
        if self.multi_hit_rate_ge2 + self.zero_hit_rate_k0 > 1.0 + 1e-6:
            raise DataIntegrityError(
                f"SweetSpotPortfolioMetrics multi_hit_rate_ge2 ({self.multi_hit_rate_ge2}) + "
                f"zero_hit_rate_k0 ({self.zero_hit_rate_k0}) cannot exceed 1.0."
            )
        if (
            self.cost_per_draw <= 2.0 * BAO_LO_PAYOUT_PER_HIT + 1e-6
            and self.multi_hit_rate_ge2 > self.daily_win_rate + 1e-6
        ):
            raise DataIntegrityError(
                f"SweetSpotPortfolioMetrics multi_hit_rate_ge2 ({self.multi_hit_rate_ge2}) "
                f"cannot exceed daily_win_rate ({self.daily_win_rate})."
            )
        return self


class HorizonBacktestReport(StrictBaseModel):
    """Pillar 4: Complete walk-forward evaluation report for a station and horizon (5y or 3y)."""

    station_code: StationCode
    horizon: HorizonCode
    total_draws: int = Field(ge=MIN_SAMPLE_SIZE_DRAWS)
    warmup_draws: int = Field(ge=1)
    evaluated_draws: int = Field(ge=1)
    falsification_report: FalsificationReport
    latest_tens_prediction: CalibratedCagePrediction
    latest_units_prediction: CalibratedCagePrediction
    tens_rank_alpha_decay: list[float]
    units_rank_alpha_decay: list[float]
    tens_oos_brier_score: float = Field(ge=0.0)
    tens_naive_brier_score: float = Field(ge=0.0)
    units_oos_brier_score: float = Field(ge=0.0)
    units_naive_brier_score: float = Field(ge=0.0)
    portfolio_metrics: dict[str, SweetSpotPortfolioMetrics]

    @model_validator(mode="before")
    @classmethod
    def _precheck_decay_simplex(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            copied = dict(data)
            for key in ("tens_rank_alpha_decay", "units_rank_alpha_decay"):
                if key in copied:
                    copied[key] = validate_probability_simplex(
                        copied[key], expected_len=CAGE_NUM_BALLS
                    )
            return copied
        return data

    @model_validator(mode="after")
    def _validate_horizon_consistency(self) -> HorizonBacktestReport:
        if self.evaluated_draws != self.total_draws - self.warmup_draws:
            raise DataIntegrityError(
                f"evaluated_draws ({self.evaluated_draws}) != "
                f"total_draws ({self.total_draws}) - warmup_draws ({self.warmup_draws})."
            )
        if self.falsification_report.station_code != self.station_code:
            raise DataIntegrityError("Mismatch in falsification_report.station_code.")
        if self.falsification_report.horizon != self.horizon:
            raise DataIntegrityError("Mismatch in falsification_report.horizon.")
        validate_probability_simplex(self.tens_rank_alpha_decay, expected_len=CAGE_NUM_BALLS)
        validate_probability_simplex(self.units_rank_alpha_decay, expected_len=CAGE_NUM_BALLS)
        if not self.portfolio_metrics:
            raise DataIntegrityError("portfolio_metrics cannot be empty.")
        return self


class DualHorizonStationReport(StrictBaseModel):
    """Dual-horizon (5Y vs 3Y) comparison report for a single station (XSHCM or XSVL)."""

    station_code: StationCode
    station_name: str
    draws_per_week: int = Field(ge=1, le=7)
    horizon_5y: HorizonBacktestReport
    horizon_3y: HorizonBacktestReport

    @model_validator(mode="after")
    def _validate_dual_horizons(self) -> DualHorizonStationReport:
        if (
            self.horizon_5y.station_code != self.station_code
            or self.horizon_3y.station_code != self.station_code
        ):
            raise DataIntegrityError("Station code mismatch in DualHorizonStationReport.")
        if self.horizon_5y.horizon != "5y":
            raise DataIntegrityError("horizon_5y must have horizon == '5y'.")
        if self.horizon_3y.horizon != "3y":
            raise DataIntegrityError("horizon_3y must have horizon == '3y'.")
        return self


class Stage3HandoffContract(StrictBaseModel):
    """Downstream Stage 3 Handoff Contract for Generalized Multi-Outcome Kelly Criterion."""

    contract_version: str = Field(default="stage2-to-stage3-v1")
    station_code: StationCode
    as_of_draw_date: str
    as_of_draw_index: int = Field(ge=0)
    gatekeeper_status: GatekeeperStatus
    recommended_capital_multiplier: float = Field(ge=0.0)
    p_ai_tens: list[float]
    p_ai_units: list[float]
    conviction_score: float = Field(ge=0.0)
    recommended_portfolio_config: str = Field(default="2x2")
    selected_numbers_2d: list[str]
    hit_count_distribution_19: list[float]
    portfolio_hit_distributions_19: dict[str, list[float]] = Field(default_factory=dict)
    horizon_5y_summary: HorizonBacktestReport
    horizon_3y_summary: HorizonBacktestReport
    real_payout_1d: float = Field(default=REAL_PAYOUT_1D)
    bao_lo_payout_per_hit: float = Field(default=BAO_LO_PAYOUT_PER_HIT)

    @model_validator(mode="before")
    @classmethod
    def _precheck_handoff_simplexes(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)
        for cage_key in ("p_ai_tens", "p_ai_units"):
            if cage_key in copied:
                copied[cage_key] = validate_probability_simplex(
                    copied[cage_key], expected_len=CAGE_NUM_BALLS
                )
        if "hit_count_distribution_19" in copied:
            copied["hit_count_distribution_19"] = validate_probability_simplex(
                copied["hit_count_distribution_19"], expected_len=KELLY_NUM_STATES
            )
        if "portfolio_hit_distributions_19" in copied and isinstance(
            copied["portfolio_hit_distributions_19"], Mapping
        ):
            cleaned_dists: dict[str, list[float]] = {}
            for cfg_id, dist in copied["portfolio_hit_distributions_19"].items():
                if cfg_id not in SWEET_SPOT_CONFIGS:
                    raise DataIntegrityError(f"Unknown config_id {cfg_id!r} in distributions.")
                cleaned_dists[cfg_id] = validate_probability_simplex(
                    dist, expected_len=KELLY_NUM_STATES
                )
            copied["portfolio_hit_distributions_19"] = cleaned_dists
        return copied

    @field_validator("as_of_draw_date")
    @classmethod
    def _check_date(cls, v: str) -> str:
        return validate_iso_date(v)

    @model_validator(mode="after")
    def _validate_stage3_contract_invariants(self) -> Stage3HandoffContract:
        validate_probability_simplex(self.p_ai_tens, expected_len=CAGE_NUM_BALLS)
        validate_probability_simplex(self.p_ai_units, expected_len=CAGE_NUM_BALLS)
        validate_probability_simplex(self.hit_count_distribution_19, expected_len=KELLY_NUM_STATES)
        for cfg_id, dist in self.portfolio_hit_distributions_19.items():
            if cfg_id not in SWEET_SPOT_CONFIGS:
                raise DataIntegrityError(f"Unknown config_id {cfg_id!r}.")
            validate_probability_simplex(dist, expected_len=KELLY_NUM_STATES)

        if self.recommended_portfolio_config not in SWEET_SPOT_CONFIGS:
            raise DataIntegrityError(
                f"Invalid recommended_portfolio_config {self.recommended_portfolio_config!r}."
            )
        if not self.selected_numbers_2d:
            raise DataIntegrityError("selected_numbers_2d cannot be empty.")
        for num in self.selected_numbers_2d:
            validate_two_digit_ascii(num)
        if len(set(self.selected_numbers_2d)) != len(self.selected_numbers_2d):
            raise DataIntegrityError("selected_numbers_2d must contain unique 2-digit numbers.")
        expected_num_count = int(
            SWEET_SPOT_CONFIGS[self.recommended_portfolio_config]["num_numbers"]
        )
        if len(self.selected_numbers_2d) != expected_num_count:
            raise DataIntegrityError(
                f"selected_numbers_2d count ({len(self.selected_numbers_2d)}) does not match "
                f"{self.recommended_portfolio_config!r} num_numbers ({expected_num_count})."
            )

        if (
            self.gatekeeper_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.recommended_capital_multiplier != 0.0
        ):
            raise DataIntegrityError(
                "FAIL_WHITE_NOISE_CASH_BRAKE requires recommended_capital_multiplier == 0.0."
            )
        if (
            self.gatekeeper_status != "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.recommended_capital_multiplier <= 0.0
        ):
            raise DataIntegrityError(
                f"{self.gatekeeper_status} requires recommended_capital_multiplier > 0.0."
            )

        if (
            self.horizon_5y_summary.station_code != self.station_code
            or self.horizon_3y_summary.station_code != self.station_code
        ):
            raise DataIntegrityError("Station code mismatch in Stage3HandoffContract summaries.")
        if (
            self.horizon_5y_summary.horizon != VALID_HORIZONS[0]
            or self.horizon_3y_summary.horizon != VALID_HORIZONS[1]
        ):
            raise DataIntegrityError(
                "horizon_5y_summary must be '5y' and horizon_3y_summary must be '3y'."
            )
        status_5y = self.horizon_5y_summary.falsification_report.overall_status
        status_3y = self.horizon_3y_summary.falsification_report.overall_status
        if (
            status_5y == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and status_3y == "FAIL_WHITE_NOISE_CASH_BRAKE"
            and self.gatekeeper_status != "FAIL_WHITE_NOISE_CASH_BRAKE"
        ):
            raise DataIntegrityError(
                "Stage3HandoffContract gatekeeper_status must be FAIL_WHITE_NOISE_CASH_BRAKE "
                "when both 5Y and 3Y falsification reports are FAIL_WHITE_NOISE_CASH_BRAKE."
            )
        if (
            self.gatekeeper_status == "PASS_ALPHA"
            and status_5y != "PASS_ALPHA"
            and status_3y != "PASS_ALPHA"
        ):
            raise DataIntegrityError(
                "Stage3HandoffContract gatekeeper_status cannot be PASS_ALPHA when neither "
                "5Y nor 3Y falsification report achieved PASS_ALPHA."
            )

        if abs(self.real_payout_1d - REAL_PAYOUT_1D) > 1e-9:
            raise DataIntegrityError(f"real_payout_1d must equal {REAL_PAYOUT_1D}.")
        if abs(self.bao_lo_payout_per_hit - BAO_LO_PAYOUT_PER_HIT) > 1e-9:
            raise DataIntegrityError(f"bao_lo_payout_per_hit must equal {BAO_LO_PAYOUT_PER_HIT}.")
        return self


# ===========================================================================
# Stage 3 Schemas & Adversarial Gates (Gates 1, 2, 3, 4, 5)
# ===========================================================================

DailyVerdictTier = Literal[
    "PLAY_PEAK",
    "PLAY_STANDARD",
    "PLAY_CAUTIOUS",
    "SKIP_NO_EDGE",
]
SettlementStatus = Literal["PENDING", "SETTLED"]
RegionName = Literal["Miền Nam", "Miền Trung"]
DrawTimeICT = Literal["16:15", "17:15"]


def _get_valid_35_station_codes() -> frozenset[str]:
    from xsmn_alpha.live.registry import VALID_35_STATION_CODES

    return VALID_35_STATION_CODES


def validate_station_code_35(station_code: Any) -> str:
    """Enforce Gate 1 (DataSchemaGate) against the canonical 35-station registry."""
    valid_codes = _get_valid_35_station_codes()
    if not isinstance(station_code, str) or station_code not in valid_codes:
        raise DataIntegrityError(
            f"Invalid station_code {station_code!r}; must be one of the 35 valid station codes."
        )
    return station_code


def validate_joint_100_matrix(
    matrix: Any,
    tol: float | None = None,
) -> list[list[float]]:
    """Enforce Gate 3 (SimplexCalibrationGate) on a 10x10 joint probability matrix (00..99)."""
    if (
        not isinstance(matrix, Sequence)
        or isinstance(matrix, (str, bytes))
        or len(matrix) != CAGE_NUM_BALLS
    ):
        raise CalibrationIntegrityError(
            f"joint_100_matrix must be a 10x10 sequence of rows, got {type(matrix).__name__}."
        )
    eff_tol = float(tol) if tol is not None else SIMPLEX_TOLERANCE * CAGE_NUM_BALLS
    flat: list[float] = []
    for row_idx, row in enumerate(matrix):
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or len(row) != CAGE_NUM_BALLS
        ):
            raise CalibrationIntegrityError(f"joint_100_matrix row {row_idx} must have length 10.")
        for col_idx, val in enumerate(row):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise CalibrationIntegrityError(
                    f"Non-numeric cell at ({row_idx}, {col_idx}): {val!r}."
                )
            fval = float(val)
            if not math.isfinite(fval) or fval < -1e-9 or fval > 1.0 + eff_tol:
                raise CalibrationIntegrityError(
                    f"Invalid probability cell at ({row_idx}, {col_idx}): {fval}."
                )
            flat.append(0.0 if fval < 0.0 else fval)

    norm_flat = validate_probability_simplex(flat, expected_len=100, tol=eff_tol)
    return [norm_flat[r * CAGE_NUM_BALLS : (r + 1) * CAGE_NUM_BALLS] for r in range(CAGE_NUM_BALLS)]


class Stage3CanonicalDrawRecord(StrictBaseModel):
    """Canonical 18-prize draw record supporting all 35 XSMN/XSMT stations (Gate 1)."""

    station_code: str
    draw_date: str
    draw_index: int = Field(default=0, ge=0)
    prizes_last2: list[str]
    tens_counts: list[int]
    units_counts: list[int]

    @model_validator(mode="before")
    @classmethod
    def _gate1_stage3_draw_precheck(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)

        allowed_keys = {
            "station_code",
            "draw_date",
            "draw_index",
            "prizes_last2",
            "tens_counts",
            "units_counts",
        }
        extra_keys = set(copied.keys()) - allowed_keys
        if extra_keys:
            raise DataIntegrityError(
                f"Unexpected extra fields in Stage3CanonicalDrawRecord: {sorted(extra_keys)}"
            )

        validate_station_code_35(copied.get("station_code"))
        validate_iso_date(copied.get("draw_date"))

        draw_index = copied.get("draw_index", 0)
        if isinstance(draw_index, bool) or not isinstance(draw_index, int) or draw_index < 0:
            raise DataIntegrityError(
                f"Invalid draw_index {draw_index!r}; must be a non-negative integer."
            )
        copied["draw_index"] = draw_index

        prizes = copied.get("prizes_last2")
        if (
            not isinstance(prizes, Sequence)
            or isinstance(prizes, (str, bytes))
            or len(prizes) != PRIZES_PER_DRAW
        ):
            count = len(prizes) if isinstance(prizes, Sequence) else "non-sequence"
            raise DataIntegrityError(
                f"prizes_last2 must contain exactly {PRIZES_PER_DRAW} prizes, got {count}."
            )
        cleaned_prizes = [validate_two_digit_ascii(tok) for tok in prizes]
        copied["prizes_last2"] = cleaned_prizes

        expected_tens = [0] * CAGE_NUM_BALLS
        expected_units = [0] * CAGE_NUM_BALLS
        for prize in cleaned_prizes:
            expected_tens[ord(prize[0]) - 48] += 1
            expected_units[ord(prize[1]) - 48] += 1

        if "tens_counts" not in copied or copied["tens_counts"] is None:
            copied["tens_counts"] = expected_tens
        if "units_counts" not in copied or copied["units_counts"] is None:
            copied["units_counts"] = expected_units

        for field_name in ("tens_counts", "units_counts"):
            vec = copied.get(field_name)
            if (
                not isinstance(vec, Sequence)
                or isinstance(vec, (str, bytes))
                or len(vec) != CAGE_NUM_BALLS
            ):
                raise DataIntegrityError(
                    f"{field_name} must be a 10-element integer list, got {vec!r}."
                )
            for item in vec:
                if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 18:
                    raise DataIntegrityError(
                        f"Invalid count element {item!r} in {field_name}; must be int in 0..18."
                    )
            if sum(vec) != PRIZES_PER_DRAW:
                raise DataIntegrityError(
                    f"{field_name} sum must equal {PRIZES_PER_DRAW}, got {sum(vec)}."
                )

        return copied

    @model_validator(mode="after")
    def _gate1_stage3_verify_counts(self) -> Stage3CanonicalDrawRecord:
        validate_station_code_35(self.station_code)
        validate_iso_date(self.draw_date)
        if len(self.prizes_last2) != PRIZES_PER_DRAW:
            raise DataIntegrityError(
                f"prizes_last2 must contain {PRIZES_PER_DRAW} prizes, got {len(self.prizes_last2)}."
            )
        expected_tens = [0] * CAGE_NUM_BALLS
        expected_units = [0] * CAGE_NUM_BALLS
        for prize in self.prizes_last2:
            validate_two_digit_ascii(prize)
            expected_tens[ord(prize[0]) - 48] += 1
            expected_units[ord(prize[1]) - 48] += 1
        if self.tens_counts != expected_tens:
            raise DataIntegrityError(
                f"tens_counts {self.tens_counts} does not match prizes_last2 {expected_tens}."
            )
        if self.units_counts != expected_units:
            raise DataIntegrityError(
                f"units_counts {self.units_counts} does not match prizes_last2 {expected_units}."
            )
        return self

    @classmethod
    def from_prizes(
        cls,
        station_code: str,
        draw_date: str,
        draw_index: int,
        prizes_last2: Sequence[str],
    ) -> Stage3CanonicalDrawRecord:
        """Construct a validated Stage3CanonicalDrawRecord from 18 2-digit prizes."""
        return cls(
            station_code=station_code,
            draw_date=draw_date,
            draw_index=draw_index,
            prizes_last2=list(prizes_last2),
            tens_counts=None,  # type: ignore[arg-type]
            units_counts=None,  # type: ignore[arg-type]
        )

    def to_stage2_canonical(self, *, allow_stage2_proxy: bool = True) -> CanonicalDrawRecord:
        """Convert to a Stage 2 CanonicalDrawRecord for Pillar 2/3/4 engines."""
        if self.station_code in VALID_STATIONS:
            proxy_station: StationCode = self.station_code  # type: ignore[assignment]
        elif not allow_stage2_proxy:
            raise DataIntegrityError(
                f"Station {self.station_code!r} is not a Stage 2 station {sorted(VALID_STATIONS)} "
                "and allow_stage2_proxy=False."
            )
        else:
            from xsmn_alpha.live.registry import STATION_REGISTRY_35

            draws_pw = int(STATION_REGISTRY_35[self.station_code]["draws_per_week"])
            proxy_station = "XSHCM" if draws_pw >= 2 else "XSVL"
        return CanonicalDrawRecord(
            station_code=proxy_station,
            draw_date=self.draw_date,
            draw_index=self.draw_index,
            prizes_last2=list(self.prizes_last2),
            tens_counts=list(self.tens_counts),
            units_counts=list(self.units_counts),
        )


RawDrawRecord = Stage3CanonicalDrawRecord


class HitDetailRecord(StrictBaseModel):
    """Details of a single winning prize hit within an 18-prize draw."""

    prize_index: int = Field(ge=0, lt=PRIZES_PER_DRAW)
    prize_label: str = Field(min_length=1)
    number: str

    @field_validator("number")
    @classmethod
    def _validate_number(cls, v: str) -> str:
        return validate_two_digit_ascii(v)


class BenchmarkLedgerEntry(StrictBaseModel):
    """Single day entry in the Reference Benchmark Fund ledger (1,000,000 VND initial principal)."""

    draw_date: str
    weekday_vn: str = Field(min_length=1)
    settlement_status: SettlementStatus
    verdict_tier: DailyVerdictTier
    chosen_station_code: str
    chosen_station_name: str = Field(min_length=1)
    chosen_region: RegionName
    chosen_config_id: str
    selected_numbers: list[str]
    recommended_multiplier: float = Field(ge=0.0)
    bankroll_before_vnd: int = Field(ge=0)
    house_money_before_vnd: int = Field(ge=0)
    cost_vnd: int = Field(ge=0)
    actual_prizes_last2: list[str] = Field(default_factory=list)
    hit_count_k: int | None = Field(default=None)
    hit_details: list[HitDetailRecord] = Field(default_factory=list)
    revenue_vnd: int = Field(default=0, ge=0)
    net_profit_vnd: int = Field(default=0)
    bankroll_after_vnd: int = Field(ge=0)
    house_money_after_vnd: int = Field(ge=0)

    @field_validator("draw_date")
    @classmethod
    def _check_draw_date(cls, v: str) -> str:
        return validate_iso_date(v)

    @field_validator("chosen_station_code")
    @classmethod
    def _check_station_code(cls, v: str) -> str:
        return validate_station_code_35(v)

    @field_validator("chosen_config_id")
    @classmethod
    def _check_config_id(cls, v: str) -> str:
        if v not in STAGE4_SWEET_SPOT_CONFIGS:
            raise DataIntegrityError(f"Unknown chosen_config_id {v!r}.")
        return v

    @model_validator(mode="after")
    def _validate_gate4_and_gate5_invariants(self) -> BenchmarkLedgerEntry:
        from xsmn_alpha.live.registry import (
            STATION_REGISTRY_35,
            get_station_codes_for_weekday,
            get_weekday_vn_label,
        )

        for num in self.selected_numbers:
            validate_two_digit_ascii(num)
        if len(set(self.selected_numbers)) != len(self.selected_numbers):
            raise DataIntegrityError("selected_numbers must not contain duplicates.")

        expected_num_numbers = int(STAGE4_SWEET_SPOT_CONFIGS[self.chosen_config_id]["num_numbers"])
        if self.selected_numbers and len(self.selected_numbers) != expected_num_numbers:
            raise DataIntegrityError(
                f"len(selected_numbers) ({len(self.selected_numbers)}) != "
                f"expected num_numbers ({expected_num_numbers}) for {self.chosen_config_id!r}."
            )
        if self.chosen_config_id == "sweet_5" and self.selected_numbers:
            Weekly52AndFlatStakeGate.enforce_sweet_5(self.selected_numbers)
        if self.chosen_config_id == "core_2x2_sat_3x3" and self.selected_numbers:
            if not _is_valid_2x2_cartesian_core(self.selected_numbers[:4]):
                raise DataIntegrityError(
                    f"core_2x2_sat_3x3 requires selected_numbers[:4] ({self.selected_numbers[:4]}) "
                    "to form a valid 2x2 Cartesian core rectangle."
                )

        draw_dt = datetime.date.fromisoformat(self.draw_date)
        expected_weekday_vn = get_weekday_vn_label(draw_dt)
        if self.weekday_vn != expected_weekday_vn:
            raise DataIntegrityError(
                f"weekday_vn ({self.weekday_vn!r}) does not match calendar date "
                f"{self.draw_date} ({expected_weekday_vn!r})."
            )
        scheduled_codes = get_station_codes_for_weekday(draw_dt.weekday())
        if self.chosen_station_code not in scheduled_codes:
            raise DataIntegrityError(
                f"Station {self.chosen_station_code!r} is not scheduled on {self.draw_date} "
                f"(weekday={draw_dt.weekday()}, scheduled={scheduled_codes})."
            )
        station_meta = STATION_REGISTRY_35[self.chosen_station_code]
        if self.chosen_region != station_meta["region"]:
            raise DataIntegrityError(
                f"chosen_region ({self.chosen_region!r}) does not match registry region "
                f"({station_meta['region']!r}) for {self.chosen_station_code}."
            )

        # Gate 4: FalsificationCashBrakeGate
        if self.verdict_tier == "SKIP_NO_EDGE":
            if (
                self.recommended_multiplier != 0.0
                or self.cost_vnd != 0
                or self.revenue_vnd != 0
                or self.net_profit_vnd != 0
            ):
                raise DataIntegrityError(
                    "SKIP_NO_EDGE requires recommended_multiplier == 0.0, cost_vnd == 0, "
                    "revenue_vnd == 0, and net_profit_vnd == 0."
                )
        else:
            if not self.selected_numbers:
                raise DataIntegrityError("selected_numbers cannot be empty when playing.")
            if self.recommended_multiplier <= 0.0 or self.cost_vnd <= 0:
                raise DataIntegrityError(
                    f"{self.verdict_tier} requires recommended_multiplier > 0.0 and cost_vnd > 0."
                )

        # Gate 5: HouseMoneyAndLedgerIntegrityGate
        allowed_multipliers = (0.0, 1.0, 1.25, 1.5)
        if not any(abs(self.recommended_multiplier - m) <= 1e-9 for m in allowed_multipliers):
            raise CapitalDisciplineError(
                f"Invalid recommended_multiplier {self.recommended_multiplier}; "
                f"must be one of {allowed_multipliers}."
            )

        if (
            self.verdict_tier != "SKIP_NO_EDGE"
            and self.bankroll_before_vnd < BENCHMARK_INITIAL_BANKROLL_VND
        ):
            raise CapitalDisciplineError(
                f"Cannot place a bet when bankroll_before_vnd ({self.bankroll_before_vnd}) "
                f"is below initial principal ({BENCHMARK_INITIAL_BANKROLL_VND})."
            )

        if self.house_money_before_vnd == 0:
            initial_principal = max(BENCHMARK_INITIAL_BANKROLL_VND, self.bankroll_before_vnd)
        else:
            initial_principal = self.bankroll_before_vnd - self.house_money_before_vnd
            if initial_principal < BENCHMARK_INITIAL_BANKROLL_VND:
                raise CapitalDisciplineError(
                    f"house_money_before_vnd ({self.house_money_before_vnd}) implies initial "
                    f"principal ({initial_principal}) < {BENCHMARK_INITIAL_BANKROLL_VND}."
                )

        expected_hm_before = max(0, self.bankroll_before_vnd - initial_principal)
        if self.house_money_before_vnd != expected_hm_before:
            raise CapitalDisciplineError(
                f"house_money_before_vnd ({self.house_money_before_vnd}) != "
                f"max(0, bankroll_before_vnd - {initial_principal}) ({expected_hm_before})."
            )

        expected_hm_after = max(0, self.bankroll_after_vnd - initial_principal)
        if self.house_money_after_vnd != expected_hm_after:
            raise CapitalDisciplineError(
                f"house_money_after_vnd ({self.house_money_after_vnd}) != "
                f"max(0, bankroll_after_vnd - {initial_principal}) ({expected_hm_after})."
            )

        unit_cost = float(STAGE4_SWEET_SPOT_CONFIGS[self.chosen_config_id]["cost_per_draw"])
        base_config_cost_vnd = int(round(unit_cost * BENCHMARK_STAKE_PER_NUMBER_VND))

        if self.verdict_tier != "SKIP_NO_EDGE":
            if (
                self.verdict_tier == "PLAY_CAUTIOUS"
                and abs(self.recommended_multiplier - 1.0) > 1e-9
            ):
                raise CapitalDisciplineError(
                    f"PLAY_CAUTIOUS requires recommended_multiplier == 1.0, "
                    f"got {self.recommended_multiplier}."
                )
            if self.verdict_tier == "PLAY_STANDARD" and not any(
                abs(self.recommended_multiplier - m) <= 1e-9 for m in (1.0, 1.25)
            ):
                raise CapitalDisciplineError(
                    f"PLAY_STANDARD requires recommended_multiplier in (1.0, 1.25), "
                    f"got {self.recommended_multiplier}."
                )
            if self.verdict_tier == "PLAY_PEAK" and not any(
                abs(self.recommended_multiplier - m) <= 1e-9 for m in (1.0, 1.5)
            ):
                raise CapitalDisciplineError(
                    f"PLAY_PEAK requires recommended_multiplier in (1.0, 1.5), "
                    f"got {self.recommended_multiplier}."
                )

            expected_cost_vnd = int(round(base_config_cost_vnd * self.recommended_multiplier))
            if self.cost_vnd != expected_cost_vnd:
                raise CapitalDisciplineError(
                    f"cost_vnd ({self.cost_vnd}) != expected config cost ({expected_cost_vnd}) "
                    f"for config {self.chosen_config_id!r} at {self.recommended_multiplier}x."
                )
            if self.cost_vnd > self.bankroll_before_vnd:
                raise CapitalDisciplineError(
                    f"cost_vnd ({self.cost_vnd}) exceeds bankroll_before_vnd "
                    f"({self.bankroll_before_vnd})."
                )

        if self.recommended_multiplier > 1.0 + 1e-9:
            if self.verdict_tier not in ("PLAY_PEAK", "PLAY_STANDARD"):
                raise CapitalDisciplineError(
                    f"Cannot boost multiplier ({self.recommended_multiplier}x) on "
                    f"{self.verdict_tier}."
                )
            if self.bankroll_before_vnd < initial_principal:
                raise CapitalDisciplineError(
                    "Cannot boost multiplier > 1.0x when bankroll is below initial principal."
                )
            min_buffer = HOUSE_MONEY_MIN_BUFFER_DAYS * base_config_cost_vnd
            if self.house_money_before_vnd < min_buffer:
                raise CapitalDisciplineError(
                    f"Cannot boost multiplier ({self.recommended_multiplier}x) when "
                    f"house_money_before_vnd ({self.house_money_before_vnd}) < {min_buffer}."
                )
            extra_cost = max(0, self.cost_vnd - base_config_cost_vnd)
            max_extra = int(self.house_money_before_vnd * HOUSE_MONEY_MAX_SURPLUS_FRACTION)
            if extra_cost > max_extra:
                raise CapitalDisciplineError(
                    f"Extra cost ({extra_cost}) exceeds 50% of house money ({max_extra})."
                )
            if self.bankroll_before_vnd - self.cost_vnd < initial_principal:
                raise CapitalDisciplineError(
                    f"Bet cost risks breaching initial {initial_principal:,} VND principal."
                )

        if self.settlement_status == "PENDING":
            if (
                self.actual_prizes_last2
                or self.hit_count_k is not None
                or self.hit_details
                or self.revenue_vnd != 0
                or self.net_profit_vnd != 0
                or self.bankroll_after_vnd != self.bankroll_before_vnd
            ):
                raise CapitalDisciplineError(
                    "PENDING entry must have empty actual_prizes_last2, hit_count_k=None, "
                    "empty hit_details, revenue_vnd=0, net_profit_vnd=0, and "
                    "bankroll_after == bankroll_before."
                )
        else:
            if self.verdict_tier == "SKIP_NO_EDGE":
                if not self.actual_prizes_last2:
                    if self.hit_count_k not in (0, None) or self.hit_details:
                        raise DataIntegrityError(
                            "SETTLED SKIP_NO_EDGE entry without actual_prizes_last2 must have "
                            "hit_count_k in (0, None) and empty hit_details, "
                            f"got hit_count_k={self.hit_count_k!r}, "
                            f"hit_details={self.hit_details!r}."
                        )
                else:
                    if len(self.actual_prizes_last2) != PRIZES_PER_DRAW:
                        raise DataIntegrityError(
                            f"SETTLED SKIP_NO_EDGE entry with actual_prizes_last2 requires "
                            f"{PRIZES_PER_DRAW} prizes, got {len(self.actual_prizes_last2)}."
                        )
                    for p in self.actual_prizes_last2:
                        validate_two_digit_ascii(p)
                    selected_set = set(self.selected_numbers)
                    expected_hit_indices = [
                        idx
                        for idx, prize in enumerate(self.actual_prizes_last2)
                        if prize in selected_set
                    ]
                    expected_k = len(expected_hit_indices)
                    if self.hit_count_k != expected_k or len(self.hit_details) != expected_k:
                        raise DataIntegrityError(
                            f"SETTLED SKIP_NO_EDGE entry hit_count_k ({self.hit_count_k}) / "
                            f"len(hit_details) ({len(self.hit_details)}) != "
                            f"expected ({expected_k})."
                        )
                    for detail, exp_idx in zip(self.hit_details, expected_hit_indices, strict=True):
                        if (
                            detail.prize_index != exp_idx
                            or detail.number != self.actual_prizes_last2[exp_idx]
                        ):
                            raise DataIntegrityError(
                                f"hit_details mismatch at prize_index {detail.prize_index}: "
                                f"expected index {exp_idx} ({self.actual_prizes_last2[exp_idx]!r})."
                            )
            else:
                if len(self.actual_prizes_last2) != PRIZES_PER_DRAW:
                    raise DataIntegrityError(
                        f"SETTLED entry requires {PRIZES_PER_DRAW} actual_prizes_last2, "
                        f"got {len(self.actual_prizes_last2)}."
                    )
                for p in self.actual_prizes_last2:
                    validate_two_digit_ascii(p)
                if (
                    self.hit_count_k is None
                    or self.hit_count_k < 0
                    or self.hit_count_k > PRIZES_PER_DRAW
                ):
                    raise DataIntegrityError(
                        f"SETTLED entry requires hit_count_k in 0..18, got {self.hit_count_k!r}."
                    )
                selected_set = set(self.selected_numbers)
                expected_hit_indices = [
                    idx
                    for idx, prize in enumerate(self.actual_prizes_last2)
                    if prize in selected_set
                ]
                expected_k = len(expected_hit_indices)
                if self.hit_count_k != expected_k:
                    raise DataIntegrityError(
                        f"SETTLED entry hit_count_k ({self.hit_count_k}) does not match "
                        f"actual prize hits ({expected_k})."
                    )
                if len(self.hit_details) != expected_k:
                    raise DataIntegrityError(
                        f"SETTLED entry len(hit_details) ({len(self.hit_details)}) != "
                        f"hit_count_k ({expected_k})."
                    )
                for detail, exp_idx in zip(self.hit_details, expected_hit_indices, strict=True):
                    if (
                        detail.prize_index != exp_idx
                        or detail.number != self.actual_prizes_last2[exp_idx]
                    ):
                        raise DataIntegrityError(
                            f"hit_details mismatch at prize_index {detail.prize_index}: "
                            f"expected index {exp_idx} ({self.actual_prizes_last2[exp_idx]!r})."
                        )
                if self.chosen_config_id == "core_2x2_sat_3x3":
                    core_set = set(self.selected_numbers[:4])
                    core_hits = sum(1 for hd in self.hit_details if hd.number in core_set)
                    sat_hits = len(self.hit_details) - core_hits
                    expected_revenue = int(
                        round(
                            (float(core_hits) + 0.5 * float(sat_hits))
                            * BENCHMARK_PAYOUT_PER_HIT_VND
                            * self.recommended_multiplier
                        )
                    )
                else:
                    payout_per_hit = int(
                        round(BENCHMARK_PAYOUT_PER_HIT_VND * self.recommended_multiplier)
                    )
                    expected_revenue = expected_k * payout_per_hit
                if self.revenue_vnd != expected_revenue:
                    raise CapitalDisciplineError(
                        f"SETTLED entry revenue_vnd ({self.revenue_vnd}) != "
                        f"expected_revenue ({expected_revenue}) for config "
                        f"{self.chosen_config_id!r}."
                    )
            if self.net_profit_vnd != self.revenue_vnd - self.cost_vnd:
                raise CapitalDisciplineError(
                    f"net_profit_vnd ({self.net_profit_vnd}) != "
                    f"revenue_vnd ({self.revenue_vnd}) - cost_vnd ({self.cost_vnd})."
                )
            expected_after = self.bankroll_before_vnd + self.revenue_vnd - self.cost_vnd
            if self.bankroll_after_vnd != expected_after:
                raise CapitalDisciplineError(
                    f"bankroll_after_vnd ({self.bankroll_after_vnd}) != "
                    f"bankroll_before_vnd + revenue_vnd - cost_vnd ({expected_after})."
                )
        return self


class BenchmarkLedgerState(StrictBaseModel):
    """Cumulative state of the Reference Benchmark Fund ledger (data/live/benchmark_ledger.json)."""

    schema_version: str = Field(default="3.0.0")
    starting_bankroll_vnd: int = Field(default=BENCHMARK_INITIAL_BANKROLL_VND, gt=0)
    base_stake_per_number_vnd: int = Field(default=BENCHMARK_STAKE_PER_NUMBER_VND, gt=0)
    payout_per_hit_vnd: int = Field(default=BENCHMARK_PAYOUT_PER_HIT_VND, gt=0)
    current_bankroll_vnd: int = Field(ge=0)
    house_money_surplus_vnd: int = Field(ge=0)
    peak_bankroll_vnd: int = Field(ge=0)
    min_bankroll_vnd: int = Field(ge=0)
    max_drawdown_vnd: int = Field(ge=0)
    total_tracked_days: int = Field(ge=0)
    played_days: int = Field(ge=0)
    rest_days: int = Field(ge=0)
    win_days: int = Field(ge=0)
    loss_days: int = Field(ge=0)
    total_cost_vnd: int = Field(ge=0)
    total_revenue_vnd: int = Field(ge=0)
    net_profit_vnd: int
    updated_at: str = Field(min_length=1)
    sha256: str = Field(default="")
    entries: list[BenchmarkLedgerEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ledger_state_invariants(self) -> BenchmarkLedgerState:
        expected_net = self.total_revenue_vnd - self.total_cost_vnd
        if self.net_profit_vnd != expected_net:
            raise CapitalDisciplineError(
                f"Ledger net_profit_vnd ({self.net_profit_vnd}) != "
                f"total_revenue_vnd - total_cost_vnd ({expected_net})."
            )
        expected_bankroll = self.starting_bankroll_vnd + self.net_profit_vnd
        if self.current_bankroll_vnd != expected_bankroll:
            raise CapitalDisciplineError(
                f"Ledger current_bankroll_vnd ({self.current_bankroll_vnd}) != "
                f"starting_bankroll_vnd + net_profit_vnd ({expected_bankroll})."
            )
        expected_hm = max(0, self.current_bankroll_vnd - self.starting_bankroll_vnd)
        if self.house_money_surplus_vnd != expected_hm:
            raise CapitalDisciplineError(
                f"Ledger house_money_surplus_vnd ({self.house_money_surplus_vnd}) != {expected_hm}."
            )
        if self.peak_bankroll_vnd < max(self.starting_bankroll_vnd, self.current_bankroll_vnd):
            raise CapitalDisciplineError(
                f"peak_bankroll_vnd ({self.peak_bankroll_vnd}) cannot be less than "
                f"max(starting_bankroll_vnd, current_bankroll_vnd) "
                f"({max(self.starting_bankroll_vnd, self.current_bankroll_vnd)})."
            )
        if self.min_bankroll_vnd > min(self.starting_bankroll_vnd, self.current_bankroll_vnd):
            raise CapitalDisciplineError(
                f"min_bankroll_vnd ({self.min_bankroll_vnd}) cannot exceed "
                f"min(starting_bankroll_vnd, current_bankroll_vnd) "
                f"({min(self.starting_bankroll_vnd, self.current_bankroll_vnd)})."
            )
        if self.played_days + self.rest_days != self.total_tracked_days:
            raise DataIntegrityError("played_days + rest_days must equal total_tracked_days.")
        if self.win_days + self.loss_days > self.played_days:
            raise DataIntegrityError("win_days + loss_days cannot exceed played_days.")

        seen_dates: set[str] = set()
        prev_date: str | None = None
        running_bankroll = self.starting_bankroll_vnd
        calc_peak = self.starting_bankroll_vnd
        calc_min = self.starting_bankroll_vnd
        calc_max_dd = 0
        calc_played = 0
        calc_rest = 0
        calc_win = 0
        calc_loss = 0
        calc_cost = 0
        calc_rev = 0

        for entry in self.entries:
            if entry.draw_date in seen_dates:
                raise DataIntegrityError(
                    f"Duplicate draw_date {entry.draw_date!r} in BenchmarkLedgerState.entries."
                )
            if prev_date is not None and entry.draw_date < prev_date:
                raise DataIntegrityError(
                    f"Out-of-order draw_date in BenchmarkLedgerState.entries: "
                    f"{entry.draw_date!r} < {prev_date!r}."
                )
            seen_dates.add(entry.draw_date)
            prev_date = entry.draw_date

            if entry.bankroll_before_vnd != running_bankroll:
                raise CapitalDisciplineError(
                    f"Broken bankroll chain at {entry.draw_date}: "
                    f"entry.bankroll_before_vnd ({entry.bankroll_before_vnd}) != "
                    f"running_bankroll ({running_bankroll})."
                )
            expected_entry_hm_before = max(
                0, entry.bankroll_before_vnd - self.starting_bankroll_vnd
            )
            if entry.house_money_before_vnd != expected_entry_hm_before:
                raise CapitalDisciplineError(
                    f"Entry {entry.draw_date} house_money_before_vnd "
                    f"({entry.house_money_before_vnd}) != max(0, bankroll_before_vnd - "
                    f"starting_bankroll_vnd) ({expected_entry_hm_before})."
                )
            expected_entry_hm_after = max(0, entry.bankroll_after_vnd - self.starting_bankroll_vnd)
            if entry.house_money_after_vnd != expected_entry_hm_after:
                raise CapitalDisciplineError(
                    f"Entry {entry.draw_date} house_money_after_vnd "
                    f"({entry.house_money_after_vnd}) != max(0, bankroll_after_vnd - "
                    f"starting_bankroll_vnd) ({expected_entry_hm_after})."
                )
            running_bankroll = entry.bankroll_after_vnd
            calc_peak = max(calc_peak, running_bankroll)
            calc_min = min(calc_min, running_bankroll)
            calc_max_dd = max(calc_max_dd, calc_peak - running_bankroll)

            if entry.verdict_tier == "SKIP_NO_EDGE":
                calc_rest += 1
            else:
                calc_played += 1
                if entry.settlement_status == "SETTLED":
                    calc_cost += entry.cost_vnd
                    calc_rev += entry.revenue_vnd
                    if entry.net_profit_vnd > 0:
                        calc_win += 1
                    else:
                        calc_loss += 1

        if self.entries:
            if self.total_tracked_days != len(self.entries):
                raise DataIntegrityError(
                    f"total_tracked_days ({self.total_tracked_days}) != "
                    f"len(entries) ({len(self.entries)})."
                )
            if self.played_days != calc_played or self.rest_days != calc_rest:
                raise DataIntegrityError(
                    f"played_days/rest_days ({self.played_days}/{self.rest_days}) != "
                    f"entries count ({calc_played}/{calc_rest})."
                )
            if self.win_days != calc_win or self.loss_days != calc_loss:
                raise DataIntegrityError(
                    f"win_days/loss_days ({self.win_days}/{self.loss_days}) != "
                    f"entries count ({calc_win}/{calc_loss})."
                )
            if self.total_cost_vnd != calc_cost:
                raise CapitalDisciplineError(
                    f"total_cost_vnd ({self.total_cost_vnd}) != "
                    f"sum of settled entry costs ({calc_cost})."
                )
            if self.total_revenue_vnd != calc_rev:
                raise CapitalDisciplineError(
                    f"total_revenue_vnd ({self.total_revenue_vnd}) != "
                    f"sum of settled entry revenues ({calc_rev})."
                )
            if self.current_bankroll_vnd != running_bankroll:
                raise CapitalDisciplineError(
                    f"current_bankroll_vnd ({self.current_bankroll_vnd}) != "
                    f"entries[-1].bankroll_after_vnd ({running_bankroll})."
                )
            if self.peak_bankroll_vnd != calc_peak or self.min_bankroll_vnd != calc_min:
                raise CapitalDisciplineError(
                    f"peak/min bankroll ({self.peak_bankroll_vnd}/{self.min_bankroll_vnd}) != "
                    f"calculated ({calc_peak}/{calc_min})."
                )
            if self.max_drawdown_vnd != calc_max_dd:
                raise CapitalDisciplineError(
                    f"max_drawdown_vnd ({self.max_drawdown_vnd}) != calculated ({calc_max_dd})."
                )
        return self


class SampleCapitalAllocationRow(StrictBaseModel):
    """VND conversion row for a sample family capital tier (500k, 1M, 2M, 5M)."""

    capital_tier_vnd: int = Field(gt=0)
    tier_label: str = Field(min_length=1)
    scale_factor: float = Field(gt=0.0)
    recommended_multiplier: float = Field(ge=0.0)
    stake_per_number_vnd: int = Field(ge=0)
    num_numbers: int = Field(default=4, ge=0)
    total_daily_cost_vnd: int = Field(ge=0)
    payout_per_hit_vnd: int = Field(ge=0)
    net_profit_1hit_vnd: int
    net_profit_2hits_vnd: int
    net_profit_3hits_vnd: int = Field(default=0)

    @model_validator(mode="after")
    def _validate_row_math(self) -> SampleCapitalAllocationRow:
        if self.recommended_multiplier == 0.0:
            if (
                self.stake_per_number_vnd != 0
                or self.total_daily_cost_vnd != 0
                or self.payout_per_hit_vnd != 0
                or self.net_profit_1hit_vnd != 0
                or self.net_profit_2hits_vnd != 0
                or self.net_profit_3hits_vnd != 0
            ):
                raise DataIntegrityError(
                    "When recommended_multiplier == 0.0, all sample stakes/costs/profits must be 0."
                )
        else:
            if (
                self.stake_per_number_vnd <= 0
                or self.num_numbers <= 0
                or self.payout_per_hit_vnd <= 0
            ):
                raise DataIntegrityError(
                    "When recommended_multiplier > 0.0, stake_per_number_vnd, num_numbers, "
                    "and payout_per_hit_vnd must be positive."
                )
            if self.total_daily_cost_vnd != self.num_numbers * self.stake_per_number_vnd:
                raise DataIntegrityError(
                    f"total_daily_cost_vnd ({self.total_daily_cost_vnd}) != "
                    f"num_numbers * stake_per_number_vnd "
                    f"({self.num_numbers * self.stake_per_number_vnd})."
                )
            if self.net_profit_1hit_vnd != self.payout_per_hit_vnd - self.total_daily_cost_vnd:
                raise DataIntegrityError("net_profit_1hit_vnd mismatch.")
            if self.net_profit_2hits_vnd != 2 * self.payout_per_hit_vnd - self.total_daily_cost_vnd:
                raise DataIntegrityError("net_profit_2hits_vnd mismatch.")
            if self.net_profit_3hits_vnd != 3 * self.payout_per_hit_vnd - self.total_daily_cost_vnd:
                raise DataIntegrityError("net_profit_3hits_vnd mismatch.")
        return self


class CapitalGuidanceContract(StrictBaseModel):
    """CPPI / House-Money capital sizing guidance and sample VND conversion table."""

    verdict_tier: DailyVerdictTier
    should_play_today: bool
    recommended_multiplier: float = Field(ge=0.0)
    initial_bankroll_vnd: int = Field(default=BENCHMARK_INITIAL_BANKROLL_VND, gt=0)
    benchmark_bankroll_vnd: int = Field(ge=0)
    house_money_surplus_vnd: int = Field(ge=0)
    base_daily_cost_vnd: int = Field(default=BENCHMARK_BASE_DAILY_COST_4NUM_VND, gt=0)
    benchmark_bet_vnd: int = Field(ge=0)
    stake_per_number_vnd: int = Field(default=0, ge=0)
    payout_per_hit_vnd: int = Field(default=0, ge=0)
    sample_allocations: list[SampleCapitalAllocationRow]
    sizing_rationale_vi: str = Field(default="")

    @model_validator(mode="after")
    def _validate_gate4_and_gate5_guidance(self) -> CapitalGuidanceContract:
        # Gate 4: FalsificationCashBrakeGate
        if self.verdict_tier == "SKIP_NO_EDGE":
            if (
                self.should_play_today
                or self.recommended_multiplier != 0.0
                or self.benchmark_bet_vnd != 0
                or self.stake_per_number_vnd != 0
                or self.payout_per_hit_vnd != 0
                or any(r.total_daily_cost_vnd != 0 for r in self.sample_allocations)
            ):
                raise DataIntegrityError(
                    "SKIP_NO_EDGE requires should_play_today=False, recommended_multiplier=0.0, "
                    "benchmark_bet_vnd=0, stake_per_number_vnd=0, payout_per_hit_vnd=0, "
                    "and all sample_allocations total_daily_cost_vnd=0."
                )
        else:
            if (
                not self.should_play_today
                or self.recommended_multiplier <= 0.0
                or self.benchmark_bet_vnd <= 0
                or self.stake_per_number_vnd <= 0
                or self.payout_per_hit_vnd <= self.stake_per_number_vnd
            ):
                raise DataIntegrityError(
                    f"{self.verdict_tier} requires should_play_today=True, "
                    "recommended_multiplier > 0.0, benchmark_bet_vnd > 0, "
                    "stake_per_number_vnd > 0, and payout_per_hit_vnd > stake_per_number_vnd."
                )

        if not self.sample_allocations:
            raise DataIntegrityError("sample_allocations cannot be empty.")
        for row in self.sample_allocations:
            if abs(row.recommended_multiplier - self.recommended_multiplier) > 1e-9:
                raise DataIntegrityError(
                    f"Sample allocation row multiplier ({row.recommended_multiplier}) != "
                    f"guidance recommended_multiplier ({self.recommended_multiplier})."
                )
            if (
                self.verdict_tier != "SKIP_NO_EDGE"
                and row.capital_tier_vnd == self.initial_bankroll_vnd
            ):
                if (
                    row.total_daily_cost_vnd != self.benchmark_bet_vnd
                    or row.stake_per_number_vnd != self.stake_per_number_vnd
                    or row.payout_per_hit_vnd != self.payout_per_hit_vnd
                ):
                    raise CapitalDisciplineError(
                        f"Reference tier ({row.capital_tier_vnd:,} VND) allocation "
                        f"(cost={row.total_daily_cost_vnd}, stake={row.stake_per_number_vnd}, "
                        f"payout={row.payout_per_hit_vnd}) does not match guidance "
                        f"(bet={self.benchmark_bet_vnd}, stake={self.stake_per_number_vnd}, "
                        f"payout={self.payout_per_hit_vnd})."
                    )

        # Gate 5: HouseMoneyAndLedgerIntegrityGate
        allowed_multipliers = (0.0, 1.0, 1.25, 1.5)
        if not any(abs(self.recommended_multiplier - m) <= 1e-9 for m in allowed_multipliers):
            raise CapitalDisciplineError(
                f"Invalid recommended_multiplier {self.recommended_multiplier}; "
                f"must be one of {allowed_multipliers}."
            )

        expected_hm = max(0, self.benchmark_bankroll_vnd - self.initial_bankroll_vnd)
        if self.house_money_surplus_vnd != expected_hm:
            raise CapitalDisciplineError(
                f"house_money_surplus_vnd ({self.house_money_surplus_vnd}) != {expected_hm}."
            )

        if self.verdict_tier != "SKIP_NO_EDGE":
            if self.benchmark_bankroll_vnd < self.initial_bankroll_vnd:
                raise CapitalDisciplineError(
                    f"Cannot play ({self.verdict_tier}) when benchmark_bankroll_vnd "
                    f"({self.benchmark_bankroll_vnd}) < initial_bankroll_vnd "
                    f"({self.initial_bankroll_vnd})."
                )
            if (
                self.verdict_tier == "PLAY_CAUTIOUS"
                and abs(self.recommended_multiplier - 1.0) > 1e-9
            ):
                raise CapitalDisciplineError(
                    f"PLAY_CAUTIOUS requires recommended_multiplier == 1.0, "
                    f"got {self.recommended_multiplier}."
                )
            if self.verdict_tier == "PLAY_STANDARD" and not any(
                abs(self.recommended_multiplier - m) <= 1e-9 for m in (1.0, 1.25)
            ):
                raise CapitalDisciplineError(
                    f"PLAY_STANDARD requires recommended_multiplier in (1.0, 1.25), "
                    f"got {self.recommended_multiplier}."
                )
            if self.verdict_tier == "PLAY_PEAK" and not any(
                abs(self.recommended_multiplier - m) <= 1e-9 for m in (1.0, 1.5)
            ):
                raise CapitalDisciplineError(
                    f"PLAY_PEAK requires recommended_multiplier in (1.0, 1.5), "
                    f"got {self.recommended_multiplier}."
                )
            expected_bet_vnd = int(round(self.base_daily_cost_vnd * self.recommended_multiplier))
            if self.benchmark_bet_vnd != expected_bet_vnd:
                raise CapitalDisciplineError(
                    f"benchmark_bet_vnd ({self.benchmark_bet_vnd}) != "
                    f"round(base_daily_cost_vnd * recommended_multiplier) ({expected_bet_vnd})."
                )
            if self.benchmark_bet_vnd > self.benchmark_bankroll_vnd:
                raise CapitalDisciplineError(
                    f"benchmark_bet_vnd ({self.benchmark_bet_vnd}) exceeds "
                    f"benchmark_bankroll_vnd ({self.benchmark_bankroll_vnd})."
                )

        if self.recommended_multiplier > 1.0 + 1e-9:
            if self.verdict_tier not in ("PLAY_PEAK", "PLAY_STANDARD"):
                raise CapitalDisciplineError(
                    f"Cannot boost multiplier ({self.recommended_multiplier}x) on "
                    f"{self.verdict_tier}."
                )
            min_buffer = HOUSE_MONEY_MIN_BUFFER_DAYS * self.base_daily_cost_vnd
            if self.house_money_surplus_vnd < min_buffer:
                raise CapitalDisciplineError(
                    f"House money surplus ({self.house_money_surplus_vnd}) < "
                    f"minimum 2-day buffer ({min_buffer})."
                )
            extra_cost = max(0, self.benchmark_bet_vnd - self.base_daily_cost_vnd)
            max_extra = int(self.house_money_surplus_vnd * HOUSE_MONEY_MAX_SURPLUS_FRACTION)
            if extra_cost > max_extra:
                raise CapitalDisciplineError(
                    f"Extra cost ({extra_cost}) exceeds 50% of house money ({max_extra})."
                )
            if self.benchmark_bankroll_vnd - self.benchmark_bet_vnd < self.initial_bankroll_vnd:
                raise CapitalDisciplineError("Bet risks breaching initial 1,000,000 VND principal.")
        return self


class TicketConfigRecommendation(StrictBaseModel):
    """Evaluation and concrete 2-digit numbers for 1 of the Stage 3/4 ticket configs."""

    config_id: str
    label: str = Field(min_length=1)
    num_numbers: int = Field(gt=0)
    selected_numbers: list[str]
    core_numbers: list[str] = Field(default_factory=list)
    satellite_numbers: list[str] = Field(default_factory=list)
    unit_cost_per_draw: float = Field(gt=0.0)
    benchmark_1x_cost_vnd: int = Field(gt=0)
    single_prize_hit_prob: float = Field(ge=0.0, le=1.0)
    hit_at_least_1_in_18_prob: float = Field(ge=0.0, le=1.0)
    oos_roi_3y_pct: float
    oos_win_rate_3y_pct: float = Field(ge=0.0, le=100.0)
    oos_hits_per_30_draws: float = Field(ge=0.0)
    be_hits_30_draws: float = Field(gt=0.0)
    is_recommended_primary: bool = Field(default=False)

    @property
    def oos_roi_pct(self) -> float:
        """Alias for oos_roi_3y_pct."""
        return self.oos_roi_3y_pct

    @field_validator("config_id")
    @classmethod
    def _check_config_id(cls, v: str) -> str:
        if v not in STAGE4_SWEET_SPOT_CONFIGS:
            raise DataIntegrityError(f"Unknown ticket config_id {v!r}.")
        return v

    @model_validator(mode="after")
    def _validate_numbers(self) -> TicketConfigRecommendation:
        cfg_meta = STAGE4_SWEET_SPOT_CONFIGS[self.config_id]
        expected_num = int(cfg_meta["num_numbers"])
        if self.num_numbers != expected_num:
            raise DataIntegrityError(
                f"num_numbers ({self.num_numbers}) != expected {expected_num} "
                f"for config_id {self.config_id!r}."
            )
        expected_unit_cost = float(cfg_meta["cost_per_draw"])
        if abs(self.unit_cost_per_draw - expected_unit_cost) > 1e-6:
            raise DataIntegrityError(
                f"unit_cost_per_draw ({self.unit_cost_per_draw}) != expected "
                f"{expected_unit_cost} for config_id {self.config_id!r}."
            )
        expected_1x_cost = int(round(expected_unit_cost * BENCHMARK_STAKE_PER_NUMBER_VND))
        if self.benchmark_1x_cost_vnd != expected_1x_cost:
            raise DataIntegrityError(
                f"benchmark_1x_cost_vnd ({self.benchmark_1x_cost_vnd}) != expected "
                f"{expected_1x_cost} for config_id {self.config_id!r}."
            )
        expected_be_30 = float(cfg_meta["be_hits_30_draws"])
        if abs(self.be_hits_30_draws - expected_be_30) > 0.05:
            raise DataIntegrityError(
                f"be_hits_30_draws ({self.be_hits_30_draws}) != expected "
                f"{expected_be_30:.2f} for config_id {self.config_id!r}."
            )
        if self.hit_at_least_1_in_18_prob + 1e-6 < self.single_prize_hit_prob:
            raise DataIntegrityError(
                f"hit_at_least_1_in_18_prob ({self.hit_at_least_1_in_18_prob}) cannot be "
                f"less than single_prize_hit_prob ({self.single_prize_hit_prob})."
            )
        for num in self.selected_numbers:
            validate_two_digit_ascii(num)
        if len(set(self.selected_numbers)) != len(self.selected_numbers):
            raise DataIntegrityError("selected_numbers must be unique.")
        if len(self.selected_numbers) != self.num_numbers:
            raise DataIntegrityError(
                f"len(selected_numbers) ({len(self.selected_numbers)}) != "
                f"num_numbers ({self.num_numbers})."
            )
        for num in self.core_numbers:
            validate_two_digit_ascii(num)
        if len(set(self.core_numbers)) != len(self.core_numbers):
            raise DataIntegrityError("core_numbers must be unique.")
        for num in self.satellite_numbers:
            validate_two_digit_ascii(num)
        if len(set(self.satellite_numbers)) != len(self.satellite_numbers):
            raise DataIntegrityError("satellite_numbers must be unique.")
        if not set(self.core_numbers).isdisjoint(set(self.satellite_numbers)):
            raise DataIntegrityError("core_numbers and satellite_numbers must be disjoint.")
        if self.config_id == "sweet_5":
            if len(self.core_numbers) != 4 or len(self.satellite_numbers) != 1:
                raise DataIntegrityError("sweet_5 requires 4 core_numbers and 1 satellite_numbers.")
            if not _is_valid_2x2_cartesian_core(self.core_numbers):
                raise DataIntegrityError(
                    f"sweet_5 core_numbers ({self.core_numbers}) must form a valid "
                    "2x2 Cartesian rectangle."
                )
            if set(self.core_numbers) | set(self.satellite_numbers) != set(self.selected_numbers):
                raise DataIntegrityError(
                    "Union of core_numbers and satellite_numbers must equal selected_numbers."
                )
            Weekly52AndFlatStakeGate.enforce_sweet_5(self.selected_numbers, self.core_numbers)
        elif self.core_numbers or self.satellite_numbers:
            if set(self.core_numbers) | set(self.satellite_numbers) != set(self.selected_numbers):
                raise DataIntegrityError(
                    "Union of core_numbers and satellite_numbers must equal selected_numbers."
                )
            if self.config_id == "core_2x2_sat_3x3":
                if len(self.core_numbers) != 4 or len(self.satellite_numbers) != 5:
                    raise DataIntegrityError(
                        "core_2x2_sat_3x3 requires 4 core_numbers and 5 satellite_numbers."
                    )
                if not _is_valid_2x2_cartesian_core(self.core_numbers):
                    raise DataIntegrityError(
                        f"core_2x2_sat_3x3 core_numbers ({self.core_numbers}) must form a valid "
                        "2x2 rectangle."
                    )
            else:
                if len(self.core_numbers) != self.num_numbers or self.satellite_numbers:
                    raise DataIntegrityError(
                        f"{self.config_id!r} requires core_numbers == selected_numbers "
                        "and empty satellite_numbers."
                    )
        return self


class WeekdayCageBalanceSummary(StrictBaseModel):
    """Cage balance & deviation summary for 1 of the 7 weekdays (0=Mon .. 6=Sun) strictly < D."""

    weekday: int = Field(ge=0, le=6)
    weekday_vn: str = Field(min_length=1)
    balance_rank: int = Field(ge=1, le=7)
    num_stations: int = Field(ge=5, le=7)
    station_codes: list[str]
    lead_station_code: str
    lead_station_name: str = Field(min_length=1)
    max_chi2_overall: float = Field(ge=0.0)
    mean_chi2_overall: float = Field(ge=0.0)
    max_bf10_overall: float = Field(gt=0.0)
    min_entropy_overall: float = Field(ge=0.0, le=1.000001)
    is_rest_day: bool

    @model_validator(mode="before")
    @classmethod
    def _precheck_weekday_summary(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)
        wd = copied.get("weekday")
        if isinstance(wd, bool) or not isinstance(wd, int) or wd < 0 or wd > 6:
            raise DataIntegrityError(f"weekday must be an int in 0..6, got {wd!r}.")
        br = copied.get("balance_rank")
        if isinstance(br, bool) or not isinstance(br, int) or br < 1 or br > 7:
            raise DataIntegrityError(f"balance_rank must be an int in 1..7, got {br!r}.")
        ns = copied.get("num_stations")
        if isinstance(ns, bool) or not isinstance(ns, int) or ns < 5 or ns > 7:
            raise DataIntegrityError(f"num_stations must be an int in 5..7, got {ns!r}.")
        return copied

    @model_validator(mode="after")
    def _validate_weekday_summary_invariants(self) -> WeekdayCageBalanceSummary:
        from xsmn_alpha.live.registry import (
            STATION_REGISTRY_35,
            WEEKDAY_VN_LABELS,
            get_station_codes_for_weekday,
        )

        expected_wd_vn = WEEKDAY_VN_LABELS[self.weekday]
        if self.weekday_vn != expected_wd_vn:
            raise DataIntegrityError(
                f"weekday_vn ({self.weekday_vn!r}) != expected {expected_wd_vn!r} "
                f"for weekday {self.weekday}."
            )
        expected_rest = self.balance_rank in (1, 2)
        if self.is_rest_day != expected_rest:
            raise DataIntegrityError(
                f"WeekdayCageBalanceSummary balance_rank={self.balance_rank} requires "
                f"is_rest_day={expected_rest}, got {self.is_rest_day}."
            )
        if self.mean_chi2_overall > self.max_chi2_overall + 1e-9:
            raise DataIntegrityError(
                f"mean_chi2_overall ({self.mean_chi2_overall}) cannot exceed "
                f"max_chi2_overall ({self.max_chi2_overall})."
            )
        if len(self.station_codes) != self.num_stations:
            raise DataIntegrityError(
                f"len(station_codes) ({len(self.station_codes)}) != "
                f"num_stations ({self.num_stations})."
            )
        for code in self.station_codes:
            validate_station_code_35(code)
        if len(set(self.station_codes)) != len(self.station_codes):
            raise DataIntegrityError("station_codes must not contain duplicates.")
        expected_codes = set(get_station_codes_for_weekday(self.weekday))
        if set(self.station_codes) != expected_codes:
            raise DataIntegrityError(
                f"station_codes ({self.station_codes}) do not match scheduled stations "
                f"for weekday {self.weekday} ({sorted(expected_codes)})."
            )
        validate_station_code_35(self.lead_station_code)
        if self.lead_station_code not in self.station_codes:
            raise DataIntegrityError(
                f"lead_station_code ({self.lead_station_code!r}) must be in "
                f"station_codes ({self.station_codes})."
            )
        expected_lead_name = str(STATION_REGISTRY_35[self.lead_station_code]["name"])
        if self.lead_station_name != expected_lead_name:
            raise DataIntegrityError(
                f"lead_station_name ({self.lead_station_name!r}) != registry name "
                f"({expected_lead_name!r}) for {self.lead_station_code}."
            )
        return self


class WeeklySchedule52Analysis(StrictBaseModel):
    """Weekly 5/2 Cage-Balance Schedule ranking all 7 weekdays strictly before target_date (< D)."""

    as_of_date: str
    target_weekday: int = Field(ge=0, le=6)
    target_weekday_vn: str = Field(min_length=1)
    today_balance_rank: int = Field(ge=1, le=7)
    is_today_scheduled_rest_day: bool
    rest_weekdays: tuple[int, int]
    rest_weekdays_vn: tuple[str, str]
    play_weekdays: tuple[int, int, int, int, int]
    play_weekdays_vn: tuple[str, str, str, str, str]
    weekday_rankings: list[WeekdayCageBalanceSummary]
    schedule_summary_vi: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _gate6_precheck_weekly_schedule(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)
        validate_iso_date(copied.get("as_of_date"))

        twd = copied.get("target_weekday")
        if isinstance(twd, bool) or not isinstance(twd, int) or twd < 0 or twd > 6:
            raise DataIntegrityError(f"target_weekday must be an int in 0..6, got {twd!r}.")
        tbr = copied.get("today_balance_rank")
        if isinstance(tbr, bool) or not isinstance(tbr, int) or tbr < 1 or tbr > 7:
            raise DataIntegrityError(f"today_balance_rank must be an int in 1..7, got {tbr!r}.")

        for key, exp_len in (
            ("rest_weekdays", WEEKLY_SCHEDULE_REST_DAYS),
            ("rest_weekdays_vn", WEEKLY_SCHEDULE_REST_DAYS),
            ("play_weekdays", WEEKLY_SCHEDULE_PLAY_DAYS),
            ("play_weekdays_vn", WEEKLY_SCHEDULE_PLAY_DAYS),
            ("weekday_rankings", 7),
        ):
            seq = copied.get(key)
            if (
                not isinstance(seq, Sequence)
                or isinstance(seq, (str, bytes))
                or len(seq) != exp_len
            ):
                got_len = len(seq) if isinstance(seq, Sequence) else "non-sequence"
                raise DataIntegrityError(
                    f"Gate 6 violation: {key} must have exactly {exp_len} elements, got {got_len}."
                )
        return copied

    @model_validator(mode="after")
    def _gate6_validate_weekly_52_invariants(self) -> WeeklySchedule52Analysis:
        from xsmn_alpha.live.registry import WEEKDAY_VN_LABELS

        validate_iso_date(self.as_of_date)
        expected_target_wd = datetime.date.fromisoformat(self.as_of_date).weekday()
        if self.target_weekday != expected_target_wd:
            raise DataIntegrityError(
                f"Gate 6 violation: target_weekday ({self.target_weekday}) does not match "
                f"as_of_date {self.as_of_date!r} (weekday={expected_target_wd})."
            )
        expected_target_vn = WEEKDAY_VN_LABELS[self.target_weekday]
        if self.target_weekday_vn != expected_target_vn:
            raise DataIntegrityError(
                f"Gate 6 violation: target_weekday_vn ({self.target_weekday_vn!r}) != "
                f"expected ({expected_target_vn!r})."
            )
        if len(self.weekday_rankings) != 7:
            raise DataIntegrityError(
                f"Gate 6 violation: weekday_rankings must have 7 items, "
                f"got {len(self.weekday_rankings)}."
            )

        weekdays = [r.weekday for r in self.weekday_rankings]
        if len(set(weekdays)) != 7 or set(weekdays) != set(range(7)):
            raise DataIntegrityError(
                f"Gate 6 violation: weekday_rankings must contain all 7 unique weekdays 0..6, "
                f"got {weekdays}."
            )

        ranks = [r.balance_rank for r in self.weekday_rankings]
        if ranks != [1, 2, 3, 4, 5, 6, 7]:
            raise DataIntegrityError(
                f"Gate 6 violation: weekday_rankings must be ordered by balance_rank 1..7, "
                f"got {ranks}."
            )

        for idx in range(len(self.weekday_rankings) - 1):
            curr = self.weekday_rankings[idx]
            nxt = self.weekday_rankings[idx + 1]
            curr_key = (
                round(curr.max_chi2_overall, 2),
                round(curr.max_bf10_overall, 3),
                round(curr.mean_chi2_overall, 2),
                curr.weekday,
            )
            nxt_key = (
                round(nxt.max_chi2_overall, 2),
                round(nxt.max_bf10_overall, 3),
                round(nxt.mean_chi2_overall, 2),
                nxt.weekday,
            )
            if curr_key >= nxt_key:
                raise DataIntegrityError(
                    f"Gate 6 violation: weekday_rankings must be strictly ordered by "
                    f"BC-02 key (round(max_chi2_overall, 2), round(max_bf10_overall, 3), "
                    f"round(mean_chi2_overall, 2), weekday), but rank {curr.balance_rank} "
                    f"{curr_key} >= rank {nxt.balance_rank} {nxt_key}."
                )

        rest_items = [r for r in self.weekday_rankings if r.is_rest_day]
        play_items = [r for r in self.weekday_rankings if not r.is_rest_day]
        if (
            len(rest_items) != WEEKLY_SCHEDULE_REST_DAYS
            or len(play_items) != WEEKLY_SCHEDULE_PLAY_DAYS
        ):
            raise DataIntegrityError(
                f"Gate 6 violation: Weekly 5/2 schedule requires {WEEKLY_SCHEDULE_REST_DAYS} "
                f"rest days and {WEEKLY_SCHEDULE_PLAY_DAYS} play days, got "
                f"{len(rest_items)} rest and {len(play_items)} play."
            )

        if [r.balance_rank for r in rest_items] != [1, 2] or [
            r.balance_rank for r in play_items
        ] != [3, 4, 5, 6, 7]:
            raise DataIntegrityError(
                "Gate 6 violation: balance_rank 1..2 must have is_rest_day=True and "
                "balance_rank 3..7 must have is_rest_day=False."
            )

        expected_rest_wds = (self.weekday_rankings[0].weekday, self.weekday_rankings[1].weekday)
        expected_rest_vns = (
            self.weekday_rankings[0].weekday_vn,
            self.weekday_rankings[1].weekday_vn,
        )
        expected_play_wds = tuple(r.weekday for r in self.weekday_rankings[2:])
        expected_play_vns = tuple(r.weekday_vn for r in self.weekday_rankings[2:])

        if self.rest_weekdays != expected_rest_wds:
            raise DataIntegrityError(
                f"Gate 6 violation: rest_weekdays ({self.rest_weekdays}) != "
                f"top-2 balanced weekdays ({expected_rest_wds})."
            )
        if self.rest_weekdays_vn != expected_rest_vns:
            raise DataIntegrityError(
                f"Gate 6 violation: rest_weekdays_vn ({self.rest_weekdays_vn}) != "
                f"expected ({expected_rest_vns})."
            )
        if self.play_weekdays != expected_play_wds:
            raise DataIntegrityError(
                f"Gate 6 violation: play_weekdays ({self.play_weekdays}) != "
                f"rank 3..7 weekdays ({expected_play_wds})."
            )
        if self.play_weekdays_vn != expected_play_vns:
            raise DataIntegrityError(
                f"Gate 6 violation: play_weekdays_vn ({self.play_weekdays_vn}) != "
                f"expected ({expected_play_vns})."
            )

        today_item = next(
            (r for r in self.weekday_rankings if r.weekday == self.target_weekday),
            None,
        )
        if today_item is None:
            raise DataIntegrityError(
                f"Gate 6 violation: target_weekday {self.target_weekday} missing in rankings."
            )
        if self.today_balance_rank != today_item.balance_rank:
            raise DataIntegrityError(
                f"Gate 6 violation: today_balance_rank ({self.today_balance_rank}) != "
                f"ranking for target_weekday ({today_item.balance_rank})."
            )
        if self.target_weekday_vn != today_item.weekday_vn:
            raise DataIntegrityError(
                f"Gate 6 violation: target_weekday_vn ({self.target_weekday_vn!r}) != "
                f"expected ({today_item.weekday_vn!r})."
            )
        expected_today_rest = self.target_weekday in self.rest_weekdays
        if self.is_today_scheduled_rest_day != expected_today_rest:
            raise DataIntegrityError(
                f"Gate 6 violation: is_today_scheduled_rest_day "
                f"({self.is_today_scheduled_rest_day}) != "
                f"(target_weekday in rest_weekdays) ({expected_today_rest})."
            )
        return self


class Weekly52AndFlatStakeGate:
    """Gate 6: Enforces Weekly 5/2 Cage-Balance Schedule invariants, sweet_5 subset rules,
    and Flat 1.0x Stake Discipline (no 1.25x or 1.50x escalation when lock_flat_1x=True).
    """

    @staticmethod
    def enforce_schedule(schedule: WeeklySchedule52Analysis) -> WeeklySchedule52Analysis:
        """Validate a WeeklySchedule52Analysis instance against all Gate 6 invariants."""
        if not isinstance(schedule, WeeklySchedule52Analysis):
            raise DataIntegrityError(
                f"Expected WeeklySchedule52Analysis, got {type(schedule).__name__}."
            )
        return schedule._gate6_validate_weekly_52_invariants()

    @staticmethod
    def enforce_sweet_5(
        sweet_5_numbers: Sequence[str],
        core_2x2_numbers: Sequence[str] | None = None,
    ) -> list[str]:
        """Validate that sweet_5_numbers has 5 unique 2-digit numbers including all 4 of 2x2."""
        if (
            not isinstance(sweet_5_numbers, Sequence)
            or isinstance(sweet_5_numbers, (str, bytes))
            or len(sweet_5_numbers) != 5
        ):
            count = len(sweet_5_numbers) if isinstance(sweet_5_numbers, Sequence) else "invalid"
            raise DataIntegrityError(
                f"Gate 6 violation: sweet_5_numbers must contain exactly 5 numbers, got {count}."
            )
        cleaned = [validate_two_digit_ascii(num) for num in sweet_5_numbers]
        if len(set(cleaned)) != 5:
            raise DataIntegrityError(
                f"Gate 6 violation: sweet_5_numbers must contain 5 unique numbers, got {cleaned}."
            )
        if not _contains_2x2_cartesian_subset(cleaned):
            raise DataIntegrityError(
                f"Gate 6 violation: sweet_5_numbers ({cleaned}) must contain at least one "
                "valid 2x2 Cartesian product subset."
            )
        if core_2x2_numbers is not None:
            if (
                not isinstance(core_2x2_numbers, Sequence)
                or isinstance(core_2x2_numbers, (str, bytes))
                or len(core_2x2_numbers) != 4
            ):
                raise DataIntegrityError(
                    f"Gate 6 violation: core_2x2_numbers must have exactly 4 elements, "
                    f"got {core_2x2_numbers!r}."
                )
            core_cleaned = [validate_two_digit_ascii(c) for c in core_2x2_numbers]
            core_set = set(core_cleaned)
            if (
                len(core_set) != 4
                or not _is_valid_2x2_cartesian_core(core_cleaned)
                or not core_set.issubset(set(cleaned))
            ):
                raise DataIntegrityError(
                    f"Gate 6 violation: sweet_5_numbers ({cleaned}) must contain all 4 "
                    f"core 2x2 numbers ({sorted(core_set)})."
                )
        return cleaned

    @staticmethod
    def enforce_flat_stake(
        recommended_multiplier: float,
        *,
        should_play_today: bool = True,
        lock_flat_1x: bool = True,
    ) -> float:
        """Enforce flat 1.0x stake ceiling on play days and 0.0x on rest days under Stage 4."""
        if isinstance(recommended_multiplier, bool) or not isinstance(
            recommended_multiplier, (int, float)
        ):
            raise CapitalDisciplineError(
                f"Invalid recommended_multiplier {recommended_multiplier!r}; must be float."
            )
        mult = float(recommended_multiplier)
        if not math.isfinite(mult) or mult < 0.0:
            raise CapitalDisciplineError(
                f"Invalid recommended_multiplier {mult}; must be finite >= 0.0."
            )
        if not should_play_today:
            if abs(mult) > 1e-9:
                raise DataIntegrityError(
                    f"Gate 6 violation: rest day requires multiplier == 0.0, got {mult}."
                )
            return 0.0
        if lock_flat_1x:
            if mult > STAGE4_MAX_STAKE_MULTIPLIER + 1e-9:
                raise CapitalDisciplineError(
                    f"Gate 6 (Weekly52AndFlatStakeGate) violation: multiplier ({mult}x) "
                    f"exceeds Stage 4 flat stake ceiling ({STAGE4_MAX_STAKE_MULTIPLIER}x)."
                )
            if abs(mult - STAGE4_MAX_STAKE_MULTIPLIER) > 1e-9:
                raise CapitalDisciplineError(
                    f"Gate 6 violation: Stage 4 play day requires flat "
                    f"recommended_multiplier == {STAGE4_MAX_STAKE_MULTIPLIER}x, got {mult}x."
                )
        return mult


class StationDailyScorecard(StrictBaseModel):
    """Complete pre-draw (< D) statistical & calibrated scorecard for 1 station opening on day D."""

    station_code: str
    station_name: str = Field(min_length=1)
    region: RegionName
    draw_time_ict: DrawTimeICT
    sample_draws_3y: int = Field(ge=MIN_SAMPLE_SIZE_DRAWS)
    evaluated_oos_draws: int = Field(default=111, ge=1)
    last_draw_date_before_d: str
    chi2_15_tens: float = Field(ge=0.0)
    chi2_30_tens: float = Field(ge=0.0)
    chi2_60_tens: float = Field(ge=0.0)
    chi2_15_units: float = Field(ge=0.0)
    chi2_30_units: float = Field(ge=0.0)
    chi2_60_units: float = Field(ge=0.0)
    chi2_max_tens: float = Field(ge=0.0)
    chi2_max_units: float = Field(ge=0.0)
    chi2_max_overall: float = Field(ge=0.0)
    null_chi2_p90: float = Field(ge=0.0)
    null_chi2_p95: float = Field(ge=0.0)
    bf10_max_tens: float = Field(gt=0.0)
    bf10_max_units: float = Field(gt=0.0)
    bf10_max_overall: float = Field(gt=0.0)
    normalized_entropy_tens: float = Field(ge=0.0, le=1.000001)
    normalized_entropy_units: float = Field(ge=0.0, le=1.000001)
    bocd_map_run_length_tens: int = Field(ge=0)
    bocd_map_run_length_units: int = Field(ge=0)
    bocd_map_run_length: int = Field(ge=0)
    bocd_changepoint_warning: bool
    p_ai_tens: list[float]
    p_bocd_tens: list[float]
    p_seq_tens: list[float]
    ranked_balls_tens: list[int]
    p_ai_units: list[float]
    p_bocd_units: list[float]
    p_seq_units: list[float]
    ranked_balls_units: list[int]
    joint_100_matrix: list[list[float]]
    oos_rank1_freq_tens_pct: float = Field(ge=0.0, le=100.0)
    oos_rank1_freq_units_pct: float = Field(ge=0.0, le=100.0)
    joint_r1_pct: float = Field(ge=0.0, le=100.0)
    recommended_config_id: str
    recommended_numbers: list[str]
    best_oos_roi_pct: float
    ticket_configs: dict[str, TicketConfigRecommendation]
    station_alpha_score: float

    @property
    def best_config_oos_roi_pct(self) -> float:
        """Alias for best_oos_roi_pct."""
        return self.best_oos_roi_pct

    passes_selective_alpha: bool
    strong_convergence: bool = Field(default=False)
    rank_in_day: int = Field(default=1, ge=1)
    role_label_vi: str = Field(default="")
    rationale_vi: str = Field(min_length=1)
    sweet_5_numbers: list[str] = Field(default_factory=list)
    sweet_5_config: TicketConfigRecommendation | None = Field(default=None)
    cage_anomaly_detected: bool = Field(default=False)
    cage_anomaly_summary_vi: str = Field(default="")
    cold_balls_tens: list[int] = Field(default_factory=list)
    cold_balls_units: list[int] = Field(default_factory=list)
    passes_weekly_5_2_play: bool = Field(default=False)

    @field_validator("ticket_configs", mode="before")
    @classmethod
    def _coerce_ticket_configs(cls, v: Any) -> Any:
        if isinstance(v, Sequence) and not isinstance(v, (str, bytes)):
            out: dict[str, Any] = {}
            for item in v:
                cid = (
                    item["config_id"]
                    if isinstance(item, Mapping)
                    else getattr(item, "config_id", "")
                )
                out[str(cid)] = item
            return out
        return v

    @model_validator(mode="before")
    @classmethod
    def _gate3_precheck_scorecard_simplexes(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        copied = dict(data)
        for key in (
            "p_ai_tens",
            "p_bocd_tens",
            "p_seq_tens",
            "p_ai_units",
            "p_bocd_units",
            "p_seq_units",
        ):
            if key in copied:
                copied[key] = validate_probability_simplex(copied[key], expected_len=CAGE_NUM_BALLS)
        if "joint_100_matrix" in copied:
            copied["joint_100_matrix"] = validate_joint_100_matrix(copied["joint_100_matrix"])
        return copied

    @model_validator(mode="after")
    def _validate_scorecard_invariants(self) -> StationDailyScorecard:
        validate_station_code_35(self.station_code)
        validate_iso_date(self.last_draw_date_before_d)
        for key in (
            "p_ai_tens",
            "p_bocd_tens",
            "p_seq_tens",
            "p_ai_units",
            "p_bocd_units",
            "p_seq_units",
        ):
            validate_probability_simplex(getattr(self, key), expected_len=CAGE_NUM_BALLS)
        validate_joint_100_matrix(self.joint_100_matrix)

        for ranks_name, probs_name in (
            ("ranked_balls_tens", "p_ai_tens"),
            ("ranked_balls_units", "p_ai_units"),
        ):
            ranks = getattr(self, ranks_name)
            probs = getattr(self, probs_name)
            if (
                len(ranks) != CAGE_NUM_BALLS
                or any(isinstance(b, bool) or not isinstance(b, int) for b in ranks)
                or set(ranks) != set(range(CAGE_NUM_BALLS))
            ):
                raise CalibrationIntegrityError(
                    f"{ranks_name} must be a permutation of 0..9, got {ranks!r}."
                )
            for idx in range(CAGE_NUM_BALLS - 1):
                b_curr = ranks[idx]
                b_next = ranks[idx + 1]
                if probs[b_curr] + 1e-9 < probs[b_next]:
                    raise CalibrationIntegrityError(
                        f"{ranks_name} not sorted in non-increasing order of {probs_name} "
                        f"at rank {idx}: ball {b_curr} ({probs[b_curr]:.6f}) < "
                        f"ball {b_next} ({probs[b_next]:.6f})."
                    )

        for a in range(CAGE_NUM_BALLS):
            for b in range(CAGE_NUM_BALLS):
                expected_cell = self.p_ai_tens[a] * self.p_ai_units[b]
                if abs(self.joint_100_matrix[a][b] - expected_cell) > 1e-5:
                    raise CalibrationIntegrityError(
                        f"joint_100_matrix[{a}][{b}] ({self.joint_100_matrix[a][b]:.6f}) "
                        f"!= p_ai_tens[{a}] * p_ai_units[{b}] ({expected_cell:.6f})."
                    )

        if self.recommended_config_id not in STAGE4_TICKET_CONFIGS:
            raise DataIntegrityError(
                f"recommended_config_id {self.recommended_config_id!r} must be in "
                f"{STAGE4_TICKET_CONFIGS}."
            )
        for num in self.recommended_numbers:
            validate_two_digit_ascii(num)
        if self.recommended_config_id not in self.ticket_configs:
            raise DataIntegrityError(
                f"recommended_config_id {self.recommended_config_id!r} missing from ticket_configs."
            )
        expected_rec_nums = self.ticket_configs[self.recommended_config_id].selected_numbers
        if list(self.recommended_numbers) != list(expected_rec_nums):
            raise DataIntegrityError(
                f"recommended_numbers ({self.recommended_numbers}) != "
                f"ticket_configs[{self.recommended_config_id!r}].selected_numbers "
                f"({expected_rec_nums})."
            )

        # Gate 6: Validate sweet_5_numbers & sweet_5_config when present
        expected_2x2_from_ranks = sorted(
            f"{a}{b}" for a in self.ranked_balls_tens[:2] for b in self.ranked_balls_units[:2]
        )
        core_2x2_nums = (
            self.ticket_configs["2x2"].selected_numbers
            if "2x2" in self.ticket_configs
            else expected_2x2_from_ranks
        )
        if self.sweet_5_numbers:
            Weekly52AndFlatStakeGate.enforce_sweet_5(self.sweet_5_numbers, core_2x2_nums)

        if self.sweet_5_config is not None:
            if self.sweet_5_config.config_id != "sweet_5":
                raise DataIntegrityError(
                    f"sweet_5_config must have config_id == 'sweet_5', "
                    f"got {self.sweet_5_config.config_id!r}."
                )
            Weekly52AndFlatStakeGate.enforce_sweet_5(
                self.sweet_5_config.selected_numbers, core_2x2_nums
            )
            if self.sweet_5_numbers and list(self.sweet_5_config.selected_numbers) != list(
                self.sweet_5_numbers
            ):
                raise DataIntegrityError(
                    f"sweet_5_config.selected_numbers ({self.sweet_5_config.selected_numbers}) "
                    f"!= sweet_5_numbers ({self.sweet_5_numbers})."
                )
            if set(self.sweet_5_config.core_numbers) != set(core_2x2_nums):
                raise DataIntegrityError(
                    f"sweet_5_config.core_numbers ({self.sweet_5_config.core_numbers}) "
                    f"must match core 2x2 numbers ({core_2x2_nums})."
                )

        if "sweet_5" in self.ticket_configs:
            tc_s5 = self.ticket_configs["sweet_5"]
            Weekly52AndFlatStakeGate.enforce_sweet_5(tc_s5.selected_numbers, core_2x2_nums)
            if self.sweet_5_numbers and list(tc_s5.selected_numbers) != list(self.sweet_5_numbers):
                raise DataIntegrityError(
                    f"ticket_configs['sweet_5'].selected_numbers ({tc_s5.selected_numbers}) "
                    f"!= sweet_5_numbers ({self.sweet_5_numbers})."
                )
            if self.sweet_5_config is not None and list(tc_s5.selected_numbers) != list(
                self.sweet_5_config.selected_numbers
            ):
                raise DataIntegrityError(
                    f"ticket_configs['sweet_5'].selected_numbers ({tc_s5.selected_numbers}) "
                    f"!= sweet_5_config.selected_numbers ({self.sweet_5_config.selected_numbers})."
                )

        for cold_field in ("cold_balls_tens", "cold_balls_units"):
            cold_vec = getattr(self, cold_field)
            for b in cold_vec:
                if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b >= CAGE_NUM_BALLS:
                    raise DataIntegrityError(
                        f"Invalid ball index {b!r} in {cold_field}; must be int in 0..9."
                    )
            if len(set(cold_vec)) != len(cold_vec):
                raise DataIntegrityError(f"{cold_field} must not contain duplicate ball indices.")

        expected_anomaly = bool(
            self.chi2_max_overall > self.null_chi2_p95
            and self.bf10_max_overall >= CAGE_ANOMALY_BF10_THRESHOLD - 1e-9
        )
        if self.cage_anomaly_detected:
            if not expected_anomaly:
                raise DataIntegrityError(
                    f"cage_anomaly_detected=True requires chi2_max_overall "
                    f"({self.chi2_max_overall}) > null_chi2_p95 ({self.null_chi2_p95}) "
                    f"and bf10_max_overall ({self.bf10_max_overall}) >= "
                    f"{CAGE_ANOMALY_BF10_THRESHOLD}."
                )
            if not self.cage_anomaly_summary_vi.strip():
                raise DataIntegrityError(
                    "cage_anomaly_detected=True requires non-empty cage_anomaly_summary_vi."
                )
        else:
            if (
                self.cage_anomaly_summary_vi.strip()
                or self.cold_balls_tens
                or self.cold_balls_units
            ):
                raise DataIntegrityError(
                    "cage_anomaly_detected=False requires empty cage_anomaly_summary_vi, "
                    "cold_balls_tens, and cold_balls_units."
                )
            if self.sweet_5_config is not None and expected_anomaly:
                raise DataIntegrityError(
                    f"cage_anomaly_detected=False conflicts with Stage 4 anomaly metrics "
                    f"(chi2_max_overall={self.chi2_max_overall} > {self.null_chi2_p95}, "
                    f"bf10_max_overall={self.bf10_max_overall} >= {CAGE_ANOMALY_BF10_THRESHOLD})."
                )

        expected_passes_alpha = bool(
            self.joint_r1_pct >= SELECTIVE_ALPHA_JOINT_R1_MIN_PCT - 1e-9
            and self.best_oos_roi_pct > 0.0
        )
        if self.passes_selective_alpha != expected_passes_alpha:
            raise DataIntegrityError(
                f"passes_selective_alpha ({self.passes_selective_alpha}) conflicts with "
                f"joint_r1_pct={self.joint_r1_pct} (min={SELECTIVE_ALPHA_JOINT_R1_MIN_PCT}) "
                f"and best_oos_roi_pct={self.best_oos_roi_pct} (> 0.0)."
            )
        if self.strong_convergence and not self.passes_selective_alpha:
            raise DataIntegrityError(
                "strong_convergence cannot be True when passes_selective_alpha is False."
            )
        if self.strong_convergence and not (
            self.joint_r1_pct >= PEAK_CONVICTION_JOINT_R1_PCT - 1e-9
            or self.best_oos_roi_pct >= 8.0 - 1e-9
        ):
            raise DataIntegrityError(
                f"strong_convergence=True requires joint_r1_pct >= {PEAK_CONVICTION_JOINT_R1_PCT} "
                f"or best_oos_roi_pct >= 8.0."
            )
        return self


class DataPipelineAuditRecord(StrictBaseModel):
    """Data pipeline sync and schema gate audit log for the 35 stations."""

    audit_timestamp_ict: str = Field(default="")
    target_date: str = Field(default="")
    total_stations_35: int = Field(default=35, ge=1)
    stations_synced_ok: int = Field(ge=0)
    fallback_used_count: int = Field(default=0, ge=0)
    schema_gate_passed: bool
    latest_settled_date: str = Field(default="")
    notes_vi: str = Field(default="")

    @model_validator(mode="after")
    def _validate_audit_dates(self) -> DataPipelineAuditRecord:
        if self.target_date:
            validate_iso_date(self.target_date)
        if self.latest_settled_date:
            validate_iso_date(self.latest_settled_date)
        if self.stations_synced_ok > self.total_stations_35:
            raise DataIntegrityError("stations_synced_ok cannot exceed total_stations_35.")
        return self


class ExecutiveNLGContract(StrictBaseModel):
    """Deterministic Quantitative NLG answers to the 4 core family tactical questions."""

    yesterday_settlement_summary_vi: str = Field(default="")
    q1_should_play_and_why: str = Field(min_length=1)
    q2_which_station_and_region: str = Field(min_length=1)
    q3_which_numbers_and_config: str = Field(min_length=1)
    q4_how_to_allocate_capital: str = Field(min_length=1)


class DailyQuantReportContract(StrictBaseModel):
    """Complete 05:00 AM quantitative report contract for JSON audit, Web HTML, and Telegram."""

    schema_version: str = Field(default="3.0.0")
    report_date: str
    weekday_vn: str = Field(min_length=1)
    generated_at_ict: str = Field(min_length=1)
    data_pipeline_audit: DataPipelineAuditRecord
    yesterday_settlement: BenchmarkLedgerEntry | None = Field(default=None)
    yesterday_summary_vi: str = Field(default="")
    verdict_tier: DailyVerdictTier
    should_play_today: bool
    primary_station: StationDailyScorecard
    secondary_station: StationDailyScorecard | None = Field(default=None)
    skipped_stations: list[StationDailyScorecard] = Field(default_factory=list)
    all_today_stations: list[StationDailyScorecard]
    capital_guidance: CapitalGuidanceContract
    executive_nlg_vi: ExecutiveNLGContract
    telegram_message_html: str = Field(default="")
    weekly_5_2_schedule: WeeklySchedule52Analysis | None = Field(default=None)

    @field_validator("report_date")
    @classmethod
    def _check_report_date(cls, v: str) -> str:
        return validate_iso_date(v)

    @model_validator(mode="after")
    def _validate_daily_report_invariants(self) -> DailyQuantReportContract:
        from xsmn_alpha.live.registry import get_weekday_vn_label

        expected_wd_vn = get_weekday_vn_label(self.report_date)
        if self.weekday_vn != expected_wd_vn:
            raise DataIntegrityError(
                f"DailyQuantReportContract weekday_vn ({self.weekday_vn!r}) != "
                f"expected ({expected_wd_vn!r}) for report_date {self.report_date!r}."
            )
        if not self.all_today_stations:
            raise DataIntegrityError("all_today_stations cannot be empty.")
        if not self.data_pipeline_audit.schema_gate_passed:
            raise DataIntegrityError(
                "DailyQuantReportContract requires data_pipeline_audit.schema_gate_passed=True."
            )
        if (
            self.data_pipeline_audit.latest_settled_date
            and self.data_pipeline_audit.latest_settled_date > self.report_date
        ):
            raise TemporalLeakageError(
                f"data_pipeline_audit.latest_settled_date "
                f"({self.data_pipeline_audit.latest_settled_date}) > report_date "
                f"({self.report_date})."
            )
        if (
            self.yesterday_settlement is not None
            and self.yesterday_settlement.draw_date >= self.report_date
        ):
            raise TemporalLeakageError(
                f"yesterday_settlement.draw_date ({self.yesterday_settlement.draw_date}) >= "
                f"report_date ({self.report_date})."
            )

        # Gate 2: PreDrawCutoffGate — strictly no station may use draw_date >= report_date
        all_referenced_stations = [
            self.primary_station,
            *([self.secondary_station] if self.secondary_station is not None else []),
            *self.skipped_stations,
            *self.all_today_stations,
        ]
        for sc in all_referenced_stations:
            sc._validate_scorecard_invariants()
            if sc.last_draw_date_before_d >= self.report_date:
                raise TemporalLeakageError(
                    f"Station {sc.station_code} last_draw_date_before_d "
                    f"({sc.last_draw_date_before_d}) >= report_date ({self.report_date})."
                )

        # Gate 4: FalsificationCashBrakeGate consistency between report and capital_guidance
        if self.verdict_tier != self.capital_guidance.verdict_tier:
            raise DataIntegrityError(
                f"verdict_tier ({self.verdict_tier}) != "
                f"capital_guidance.verdict_tier ({self.capital_guidance.verdict_tier})."
            )
        if self.should_play_today != self.capital_guidance.should_play_today:
            raise DataIntegrityError(
                "should_play_today must match capital_guidance.should_play_today."
            )
        if self.verdict_tier == "SKIP_NO_EDGE":
            if (
                self.should_play_today
                or self.capital_guidance.recommended_multiplier != 0.0
                or self.capital_guidance.benchmark_bet_vnd != 0
                or self.secondary_station is not None
            ):
                raise DataIntegrityError(
                    "SKIP_NO_EDGE report must lock should_play_today=False, "
                    "secondary_station=None, recommended_multiplier=0.0, and benchmark_bet_vnd=0."
                )
        else:
            if not self.should_play_today:
                raise DataIntegrityError(f"{self.verdict_tier} requires should_play_today=True.")
            if not (
                self.primary_station.passes_selective_alpha
                or self.primary_station.passes_weekly_5_2_play
            ):
                raise DataIntegrityError(
                    f"{self.verdict_tier} requires primary_station.passes_selective_alpha=True "
                    f"or primary_station.passes_weekly_5_2_play=True "
                    f"(got both False for {self.primary_station.station_code})."
                )
        if self.secondary_station is not None and not self.secondary_station.passes_selective_alpha:
            raise DataIntegrityError(
                f"secondary_station ({self.secondary_station.station_code}) must have "
                "passes_selective_alpha=True."
            )

        # Gate 6: Weekly52AndFlatStakeGate consistency when weekly_5_2_schedule is present
        if self.weekly_5_2_schedule is None:
            if any(sc.passes_weekly_5_2_play for sc in all_referenced_stations):
                raise DataIntegrityError(
                    "Gate 6 violation: passes_weekly_5_2_play cannot be True when "
                    "weekly_5_2_schedule is None."
                )
        else:
            Weekly52AndFlatStakeGate.enforce_schedule(self.weekly_5_2_schedule)
            if self.weekly_5_2_schedule.as_of_date != self.report_date:
                raise DataIntegrityError(
                    f"Gate 6 violation: weekly_5_2_schedule.as_of_date "
                    f"({self.weekly_5_2_schedule.as_of_date!r}) != report_date "
                    f"({self.report_date!r})."
                )
            Weekly52AndFlatStakeGate.enforce_flat_stake(
                self.capital_guidance.recommended_multiplier,
                should_play_today=self.should_play_today,
                lock_flat_1x=True,
            )
            if self.weekly_5_2_schedule.is_today_scheduled_rest_day:
                if (
                    self.should_play_today
                    or self.verdict_tier != "SKIP_NO_EDGE"
                    or abs(self.capital_guidance.recommended_multiplier) > 1e-9
                    or any(sc.passes_weekly_5_2_play for sc in all_referenced_stations)
                ):
                    raise DataIntegrityError(
                        "Gate 6 (EARS-S01) violation: scheduled 5/2 rest day requires "
                        "should_play_today=False, verdict_tier='SKIP_NO_EDGE', "
                        "recommended_multiplier=0.0, and passes_weekly_5_2_play=False "
                        "on all stations."
                    )
            else:
                if (
                    not self.should_play_today
                    or self.verdict_tier != "PLAY_STANDARD"
                    or abs(self.capital_guidance.recommended_multiplier - 1.0) > 1e-9
                    or not self.primary_station.passes_weekly_5_2_play
                    or any(
                        sc.passes_weekly_5_2_play
                        for sc in self.all_today_stations
                        if sc.station_code != self.primary_station.station_code
                    )
                ):
                    raise DataIntegrityError(
                        "Gate 6 (EARS-S02) violation: scheduled 5/2 play day requires "
                        "should_play_today=True, verdict_tier='PLAY_STANDARD', "
                        "recommended_multiplier=1.0, and "
                        "primary_station.passes_weekly_5_2_play=True."
                    )
        return self
