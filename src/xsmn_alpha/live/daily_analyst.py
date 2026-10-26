"""Stage 3 Pillar 2 & 4: Pre-Draw (< D) Daily Station Analyst & Deterministic Vietnamese NLG.

Evaluates all stations opening on day D strictly using pre-draw history (draw_date < D),
computes multi-window hypothesis tests W in {15, 30, 60}, calibrated 10-ball simplex
probabilities (Brier convex pooler of Bayesian Dirichlet-Multinomial BOCD + Lag-1 and
L2-regularized Markov Gap Hazard), walk-forward Rank-1 hit frequencies, and all 5
ticket portfolio configurations ('2x2', '1x4', '4x1', '3x3', 'core_2x2_sat_3x3').
Produces 100% deterministic Vietnamese quantitative explanations for the 4 core family
questions without any external LLM/AI API dependency.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np

from xsmn_alpha.backtest.alpha_decay import compute_rank_ordered_alpha_decay
from xsmn_alpha.backtest.sweet_spot_sim import (
    evaluate_stage3_ticket_portfolios,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BE_PROB_SINGLE_BALL,
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    EXTENDED_SWEET_SPOT_CONFIGS,
    FALSIFICATION_WINDOWS,
    MIN_SAMPLE_SIZE_DRAWS,
    PEAK_CONVICTION_JOINT_R1_PCT,
    SELECTIVE_ALPHA_JOINT_R1_MIN_PCT,
    STAGE3_TICKET_CONFIGS,
)
from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler
from xsmn_alpha.exceptions import (
    DataIntegrityError,
    InsufficientSampleSizeError,
    TemporalLeakageError,
)
from xsmn_alpha.falsification.monte_carlo import (
    MonteCarloNullResult,
    simulate_monte_carlo_null,
)
from xsmn_alpha.falsification.stats_tests import run_multi_window_tests
from xsmn_alpha.ingest.canonicalizer import decompose_cage_counts
from xsmn_alpha.live.ledger import (
    DEFAULT_LEDGER_PATH,
    build_capital_guidance,
    initialize_empty_ledger,
    load_benchmark_ledger,
)
from xsmn_alpha.live.multi_fetcher import (
    DEFAULT_RAW_ALL_DIR,
    load_station_raw_cache,
)
from xsmn_alpha.live.registry import (
    VALID_35_STATION_CODES,
    WEEKDAY_VN_LABELS,
    get_station_codes_for_weekday,
    get_station_meta,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerEntry,
    BenchmarkLedgerState,
    CapitalGuidanceContract,
    DailyQuantReportContract,
    DailyVerdictTier,
    DataPipelineAuditRecord,
    ExecutiveNLGContract,
    Stage3CanonicalDrawRecord,
    StationDailyScorecard,
    TicketConfigRecommendation,
    validate_iso_date,
    validate_joint_100_matrix,
    validate_station_code_35,
)

Stage3TicketConfigId = Literal["2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3"]

# In-memory deterministic cache for Monte Carlo null thresholds
# keyed by (sample_draws, null_sims, seed)
_NULL_THRESHOLD_CACHE: dict[tuple[int, int, int], MonteCarloNullResult] = {}


def _coerce_iso_date(date_val: str | datetime.date) -> str:
    """Normalize a date string or datetime.date into strict YYYY-MM-DD format."""
    if isinstance(date_val, datetime.date) and not isinstance(date_val, datetime.datetime):
        return date_val.isoformat()
    if isinstance(date_val, str):
        return validate_iso_date(date_val)
    raise DataIntegrityError(f"Expected ISO date string or datetime.date, got {date_val!r}.")


def enforce_pre_draw_date_cutoff(
    history_draws: Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]],
    *,
    target_date: str | datetime.date,
    station_code: str | None = None,
) -> list[Stage3CanonicalDrawRecord]:
    """Gate 2 (PreDrawCutoffGate): Enforce strictly causal history (draw_date < target_date).

    Raises TemporalLeakageError immediately if:
      - history_draws is empty
      - any draw has draw_date >= target_date
      - draw_date values are not strictly increasing (duplicate or out-of-order dates)
    """
    target_iso = _coerce_iso_date(target_date)
    expected_code = validate_station_code_35(station_code) if station_code is not None else None

    if not isinstance(history_draws, Sequence) or len(history_draws) == 0:
        raise TemporalLeakageError(
            f"PreDrawCutoffGate violation: history_draws is empty for target_date={target_iso}."
        )

    validated: list[Stage3CanonicalDrawRecord] = []
    prev_date = ""

    for idx, item in enumerate(history_draws):
        if isinstance(item, Stage3CanonicalDrawRecord):
            rec = item if item.draw_index == idx else item.model_copy(update={"draw_index": idx})
        elif isinstance(item, Mapping):
            raw_code = str(item.get("station_code") or expected_code or "").strip().upper()
            raw_date = _coerce_iso_date(str(item.get("draw_date", "")))
            prizes = list(item.get("prizes_last2", []))
            if "tens_counts" in item and "units_counts" in item:
                t_counts = list(item["tens_counts"])
                u_counts = list(item["units_counts"])
            else:
                t_counts, u_counts = decompose_cage_counts(prizes)
            rec = Stage3CanonicalDrawRecord(
                station_code=raw_code,
                draw_date=raw_date,
                draw_index=idx,
                prizes_last2=prizes,
                tens_counts=t_counts,
                units_counts=u_counts,
            )
        else:
            raise DataIntegrityError(
                f"Invalid history draw element at index {idx}: {type(item).__name__}."
            )

        if expected_code is not None and rec.station_code != expected_code:
            raise DataIntegrityError(
                f"Station code mismatch at index {idx}: expected {expected_code}, "
                f"got {rec.station_code}."
            )

        if rec.draw_date >= target_iso:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate violation for {rec.station_code}: draw at index {idx} "
                f"has draw_date={rec.draw_date} >= target_date={target_iso}."
            )

        if prev_date and rec.draw_date <= prev_date:
            raise TemporalLeakageError(
                f"PreDrawCutoffGate violation for {rec.station_code}: draw dates must be "
                f"strictly increasing, but index {idx} ({rec.draw_date}) <= previous ({prev_date})."
            )

        prev_date = rec.draw_date
        validated.append(rec)

    return validated


class PreDrawCutoffGate:
    """Gate 2 (PreDrawCutoffGate) class interface for strict pre-draw (< D) causal validation."""

    @staticmethod
    def enforce(
        history_draws: Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]],
        *,
        target_date: str | datetime.date,
        station_code: str | None = None,
    ) -> list[Stage3CanonicalDrawRecord]:
        """Validate and return canonical records strictly before target_date (< D)."""
        return enforce_pre_draw_date_cutoff(
            history_draws,
            target_date=target_date,
            station_code=station_code,
        )

    @staticmethod
    def validate(
        history_draws: Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]],
        *,
        target_date: str | datetime.date,
        station_code: str | None = None,
    ) -> list[Stage3CanonicalDrawRecord]:
        """Alias for PreDrawCutoffGate.enforce."""
        return enforce_pre_draw_date_cutoff(
            history_draws,
            target_date=target_date,
            station_code=station_code,
        )


def select_optimal_ticket_config(
    *,
    tens_r1_pct: float,
    units_r1_pct: float,
    roi_2x2: float,
    roi_1x4: float,
    roi_4x1: float,
) -> Stage3TicketConfigId:
    """Select the optimal 4-number ticket configuration strictly from < D OOS metrics.

    Rules (Spec Section 5.3.A.4):
      1. If both Tens and Units Rank-1 hit frequencies >= 10.6904% (BE_PROB_SINGLE_BALL * 100)
         and roi_2x2 > 0.0:
         choose '2x2' (Symmetric 2 Tens x 2 Units).
      2. If Tens < 10.6904% and Units >= 10.50% and roi_1x4 > max(roi_2x2, roi_4x1):
         choose '1x4' (1 Tens x 4 Units).
      3. If Units >= 10.6904% (and Tens < 10.6904%) and roi_4x1 > max(roi_2x2, roi_1x4) + 1.5:
         choose '4x1' (4 Tens x 1 Units).
      4. Fallback: choose '4x1' when roi_4x1 dominates by > +1.5% (with units_r1_pct >= 10.50%
         or non-positive 2x2/1x4 ROI) or when roi_4x1 is the only positive-ROI 4-number config;
         otherwise choose '2x2' if roi_2x2 >= roi_1x4 else '1x4'.
    """
    be_pct = BE_PROB_SINGLE_BALL * 100.0
    if tens_r1_pct >= be_pct and roi_2x2 > 0.0:
        return "2x2"
    if tens_r1_pct < be_pct and units_r1_pct >= 10.50 and roi_1x4 > max(roi_2x2, roi_4x1):
        return "1x4"
    if units_r1_pct >= be_pct and roi_4x1 > max(roi_2x2, roi_1x4) + 1.5:
        return "4x1"
    if roi_4x1 > max(roi_2x2, roi_1x4) + 1.5 and (
        units_r1_pct >= 10.50 or max(roi_2x2, roi_1x4) <= 0.0
    ):
        return "4x1"
    if roi_4x1 > 0.0 and max(roi_2x2, roi_1x4) <= 0.0:
        return "4x1"
    return "2x2" if roi_2x2 >= roi_1x4 else "1x4"


def classify_daily_verdict_tier(
    joint_r1_pct: float,
    best_roi_pct: float,
) -> DailyVerdictTier:
    """Classify the daily tactical verdict tier from the primary station's < D metrics.

    Rules (Spec Section 5.3 & 5.4):
      - SKIP_NO_EDGE: joint_r1_pct < 1.105% or best_roi_pct <= 0.0%
      - PLAY_PEAK: passes selective alpha and (joint_r1_pct >= 1.150% or best_roi_pct >= 8.0%)
      - PLAY_STANDARD: passes selective alpha and (best_roi_pct >= 3.0% or joint_r1_pct >= 1.125%)
      - PLAY_CAUTIOUS: passes selective alpha with 0.0% < best_roi_pct < 3.0%
        and 1.105% <= joint_r1_pct < 1.125%
    """
    if joint_r1_pct < SELECTIVE_ALPHA_JOINT_R1_MIN_PCT or best_roi_pct <= 0.0:
        return "SKIP_NO_EDGE"
    if joint_r1_pct >= PEAK_CONVICTION_JOINT_R1_PCT or best_roi_pct >= 8.0:
        return "PLAY_PEAK"
    if best_roi_pct >= 3.0 or joint_r1_pct >= 1.125:
        return "PLAY_STANDARD"
    return "PLAY_CAUTIOUS"


def build_station_rationale_vi(
    *,
    station_code: str,
    station_name: str,
    region: str,
    joint_r1_pct: float,
    oos_rank1_freq_tens_pct: float,
    oos_rank1_freq_units_pct: float,
    chi2_max_overall: float,
    null_chi2_p90: float,
    null_chi2_p95: float,
    bf10_max_overall: float,
    bocd_map_run_length: int,
    bocd_changepoint_warning: bool,
    best_oos_roi_pct: float,
    recommended_config_id: Stage3TicketConfigId,
    recommended_numbers: Sequence[str],
    passes_selective_alpha: bool,
    strong_convergence: bool,
) -> str:
    """Build deterministic Vietnamese quantitative rationale for a single station scorecard."""
    nums_str = ", ".join(recommended_numbers)
    if passes_selective_alpha:
        tier_label = (
            "ĐẠT HỘI TỤ MẠNH (PEAK ALPHA)"
            if strong_convergence
            else "ĐẠT CHUẨN LỌC SELECTIVE ALPHA"
        )
        verdict_phrase = (
            f"Đài {station_name} ({station_code} - {region}) {tier_label}: "
            f"xác suất trúng đồng thời Hạng-1 hai lồng cầu đạt JointR1 = {joint_r1_pct:.3f}% "
            f"(>= ngưỡng {SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%; Lồng Hàng Chục = "
            f"{oos_rank1_freq_tens_pct:.2f}%, Lồng Hàng Đơn Vị = {oos_rank1_freq_units_pct:.2f}% "
            f"so với điểm hòa vốn 10.69%) và hiệu suất kiểm định thực nghiệm OOS 3 năm đạt "
            f"ROI = {best_oos_roi_pct:+.2f}% (> 0%)."
        )
    else:
        reasons: list[str] = []
        if joint_r1_pct < SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:
            reasons.append(
                f"JointR1 = {joint_r1_pct:.3f}% chưa đạt ngưỡng lọc "
                f"{SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%"
            )
        if best_oos_roi_pct <= 0.0:
            reasons.append(f"ROI thực nghiệm OOS 3 năm = {best_oos_roi_pct:+.2f}% <= 0%")
        reason_text = " và ".join(reasons) if reasons else "tín hiệu thuộc vùng nhiễu trắng"
        verdict_phrase = (
            f"Đài {station_name} ({station_code} - {region}) BÁO NGHỈ / BỎ QUA (Nhiễu trắng): "
            f"{reason_text} (Lồng Chục = {oos_rank1_freq_tens_pct:.2f}%, "
            f"Lồng Đơn Vị = {oos_rank1_freq_units_pct:.2f}%)."
        )

    stats_phrase = (
        f"Kiểm định đa khung W thuộc {{15, 30, 60}} ghi nhận Chi2_max = {chi2_max_overall:.2f} "
        f"(ngưỡng Monte Carlo P90 = {null_chi2_p90:.2f}, P95 = {null_chi2_p95:.2f}), "
        f"hệ số Bayes BF10_max = {bf10_max_overall:.2f}, "
        f"độ dài chế độ BOCD r_t = {bocd_map_run_length} kỳ. "
        f"Cấu hình tối ưu < D: {recommended_config_id} ({nums_str})."
    )

    if bocd_changepoint_warning:
        bocd_phrase = (
            f" CẢNH BÁO BOCD: Độ dài chuỗi chế độ r_t = {bocd_map_run_length} <= 4 kỳ "
            f"báo hiệu lồng cầu vừa có dấu hiệu đổi chế độ / thay bóng gần đây; "
            f"cần ưu tiên kỷ luật bảo toàn vốn."
        )
    else:
        bocd_phrase = ""

    return f"{verdict_phrase} {stats_phrase}{bocd_phrase}"


def _get_cached_monte_carlo_null(
    sample_size_draws: int,
    null_sims: int,
    seed: int,
) -> MonteCarloNullResult:
    """Return deterministic Monte Carlo null thresholds with in-memory caching."""
    key = (sample_size_draws, null_sims, seed)
    if key not in _NULL_THRESHOLD_CACHE:
        _NULL_THRESHOLD_CACHE[key] = simulate_monte_carlo_null(
            sample_size_draws=sample_size_draws,
            null_sims=null_sims,
            seed=seed,
        )
    return _NULL_THRESHOLD_CACHE[key]


def score_station_for_date(
    station_code: str,
    *,
    target_date: str | datetime.date,
    history_draws: Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]] | None = None,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    warmup_draws: int = 45,
    null_sims: int = 1000,
    seed: int = 42,
    trim_to_3y: bool = True,
) -> StationDailyScorecard:
    """Evaluate a single station strictly before target_date (< D)."""
    code = validate_station_code_35(station_code)
    meta = get_station_meta(code)
    target_iso = _coerce_iso_date(target_date)

    if history_draws is None:
        raw_cached = load_station_raw_cache(
            code,
            raw_dir=raw_dir,
            verify_sha256=True,
            allow_unhashed_legacy=True,
        )
        raw_before_d = [
            d for d in raw_cached if validate_iso_date(str(d.get("draw_date", ""))) < target_iso
        ]
        records = enforce_pre_draw_date_cutoff(
            raw_before_d,
            target_date=target_iso,
            station_code=code,
        )
    else:
        records = enforce_pre_draw_date_cutoff(
            history_draws,
            target_date=target_iso,
            station_code=code,
        )

    if len(records) < MIN_SAMPLE_SIZE_DRAWS:
        raise InsufficientSampleSizeError(
            f"Station {code} has only {len(records)} pre-draw records (< {target_iso}), "
            f"which is below MIN_SAMPLE_SIZE_DRAWS={MIN_SAMPLE_SIZE_DRAWS}."
        )

    target_3y = int(meta["target_3y"])
    if trim_to_3y and len(records) > target_3y:
        records = [
            rec.model_copy(update={"draw_index": idx})
            for idx, rec in enumerate(records[-target_3y:])
        ]

    n_draws = len(records)
    if n_draws <= warmup_draws:
        raise InsufficientSampleSizeError(
            f"Station {code} sample size ({n_draws}) must exceed warmup_draws ({warmup_draws})."
        )

    stage2_records = [rec.to_stage2_canonical() for rec in records]
    tens_mat = np.array([rec.tens_counts for rec in records], dtype=np.int64)
    units_mat = np.array([rec.units_counts for rec in records], dtype=np.int64)

    # 1. Multi-window statistical tests W in {15, 30, 60}
    t_win_results = {
        res.window_draws: res
        for res in run_multi_window_tests(tens_mat, windows=FALSIFICATION_WINDOWS)
    }
    u_win_results = {
        res.window_draws: res
        for res in run_multi_window_tests(units_mat, windows=FALSIFICATION_WINDOWS)
    }

    chi2_15_t = float(t_win_results[15].chi2_stat)
    chi2_30_t = float(t_win_results[30].chi2_stat)
    chi2_60_t = float(t_win_results[60].chi2_stat)
    chi2_15_u = float(u_win_results[15].chi2_stat)
    chi2_30_u = float(u_win_results[30].chi2_stat)
    chi2_60_u = float(u_win_results[60].chi2_stat)

    chi2_max_t = max(chi2_15_t, chi2_30_t, chi2_60_t)
    chi2_max_u = max(chi2_15_u, chi2_30_u, chi2_60_u)
    chi2_max_overall = max(chi2_max_t, chi2_max_u)

    bf10_max_t = max(float(r.bf10_dirichlet) for r in t_win_results.values())
    bf10_max_u = max(float(r.bf10_dirichlet) for r in u_win_results.values())
    bf10_max_overall = max(bf10_max_t, bf10_max_u)

    # Normalized Shannon entropy from the 30-draw window
    norm_entropy_t = float(t_win_results[30].normalized_entropy)
    norm_entropy_u = float(u_win_results[30].normalized_entropy)

    null_res = _get_cached_monte_carlo_null(n_draws, null_sims=null_sims, seed=seed)

    # 2. Walk-forward out-of-sample evaluation & today's (< D) calibrated prediction
    pooler = CalibratedProbabilityPooler()
    tens_wf_preds = pooler.walk_forward_cage_predictions(
        stage2_records,
        warmup_draws=warmup_draws,
        cage_name="tens_cage",
    )
    units_wf_preds = pooler.walk_forward_cage_predictions(
        stage2_records,
        warmup_draws=warmup_draws,
        cage_name="units_cage",
    )
    eval_draws = stage2_records[warmup_draws:]

    tens_decay = compute_rank_ordered_alpha_decay(
        tens_wf_preds,
        eval_draws,
        cage_name="tens_cage",
    )
    units_decay = compute_rank_ordered_alpha_decay(
        units_wf_preds,
        eval_draws,
        cage_name="units_cage",
    )

    t_r1_pct = float(tens_decay[0]) * 100.0
    u_r1_pct = float(units_decay[0]) * 100.0

    tens_today = pooler.predict_cage(
        tens_mat,
        cage_name="tens_cage",
        target_draw_index=n_draws,
        target_draw_date=target_iso,
    )
    units_today = pooler.predict_cage(
        units_mat,
        cage_name="units_cage",
        target_draw_index=n_draws,
        target_draw_date=target_iso,
    )

    bocd_r_t = int(tens_today.map_run_length)
    bocd_r_u = int(units_today.map_run_length)
    bocd_r_min = min(bocd_r_t, bocd_r_u)
    bocd_cp_warn = bool(bocd_r_min <= 4)

    # Build 10x10 joint probability matrix P(a, b) = P_tens(a) * P_units(b)
    raw_joint_matrix = [
        [float(tens_today.p_ai[a]) * float(units_today.p_ai[b]) for b in range(10)]
        for a in range(10)
    ]
    joint_matrix = validate_joint_100_matrix(raw_joint_matrix)

    # 3. Evaluate all 5 Stage 3 ticket portfolio configurations on OOS history
    portfolios_oos = evaluate_stage3_ticket_portfolios(
        tens_wf_preds,
        units_wf_preds,
        eval_draws,
    )

    roi_2x2 = float(portfolios_oos["2x2"].roi_pct)
    roi_1x4 = float(portfolios_oos["1x4"].roi_pct)
    roi_4x1 = float(portfolios_oos["4x1"].roi_pct)

    rec_cfg_id = select_optimal_ticket_config(
        tens_r1_pct=t_r1_pct,
        units_r1_pct=u_r1_pct,
        roi_2x2=roi_2x2,
        roi_1x4=roi_1x4,
        roi_4x1=roi_4x1,
    )

    ticket_configs_map: dict[str, TicketConfigRecommendation] = {}
    for cfg_id in STAGE3_TICKET_CONFIGS:
        cfg_spec = EXTENDED_SWEET_SPOT_CONFIGS[cfg_id]
        nums = select_sweet_spot_numbers(tens_today.p_ai, units_today.p_ai, cfg_id)
        if cfg_id == "core_2x2_sat_3x3":
            core_nums = select_sweet_spot_numbers(tens_today.p_ai, units_today.p_ai, "2x2")
            sat_nums = [n for n in nums if n not in set(core_nums)]
            nums = list(core_nums) + list(sat_nums)
            p_core = sum(joint_matrix[int(num[0])][int(num[1])] for num in core_nums)
            p_sat = sum(joint_matrix[int(num[0])][int(num[1])] for num in sat_nums)
            single_prob = float(p_core) + 0.5 * float(p_sat)
        else:
            core_nums = list(nums)
            sat_nums = []
            single_prob = sum(joint_matrix[int(num[0])][int(num[1])] for num in nums)

        single_prob_round = round(min(max(float(single_prob), 0.0), 1.0), 6)
        hit_18_prob_round = round(1.0 - (1.0 - single_prob_round) ** 18, 6)
        oos_m = portfolios_oos[cfg_id]
        unit_cost = float(cfg_spec["cost_per_draw"])
        bench_1x_cost = int(round(unit_cost * BENCHMARK_STAKE_PER_NUMBER_VND))
        ticket_configs_map[cfg_id] = TicketConfigRecommendation(
            config_id=cfg_id,
            label=str(cfg_spec["label"]),
            num_numbers=len(nums),
            selected_numbers=nums,
            core_numbers=core_nums,
            satellite_numbers=sat_nums,
            unit_cost_per_draw=unit_cost,
            benchmark_1x_cost_vnd=bench_1x_cost,
            single_prize_hit_prob=single_prob_round,
            hit_at_least_1_in_18_prob=hit_18_prob_round,
            oos_roi_3y_pct=round(float(oos_m.roi_pct), 2),
            oos_win_rate_3y_pct=round(float(oos_m.daily_win_rate) * 100.0, 2),
            oos_hits_per_30_draws=round(float(oos_m.hits_per_30_draws), 2),
            be_hits_30_draws=round(float(cfg_spec["be_hits_30_draws"]), 2),
            is_recommended_primary=(cfg_id == rec_cfg_id),
        )

    rec_numbers = list(ticket_configs_map[rec_cfg_id].selected_numbers)
    best_oos_roi_pct = max(
        ticket_configs_map[cid].oos_roi_3y_pct for cid in ("2x2", "1x4", "4x1", "3x3")
    )

    t_r1_round = round(t_r1_pct, 2)
    u_r1_round = round(u_r1_pct, 2)
    joint_r1_round = round((t_r1_round * u_r1_round) / 100.0, 3)
    best_roi_round = round(best_oos_roi_pct, 2)
    alpha_score_round = round((joint_r1_round - 1.0) * 100.0 + 0.25 * best_roi_round, 2)

    passes_selective = bool(
        joint_r1_round >= SELECTIVE_ALPHA_JOINT_R1_MIN_PCT and best_roi_round > 0.0
    )
    strong_conv = bool(
        passes_selective
        and (joint_r1_round >= PEAK_CONVICTION_JOINT_R1_PCT or best_roi_round >= 8.0)
    )

    rationale_vi = build_station_rationale_vi(
        station_code=code,
        station_name=str(meta["name"]),
        region=str(meta["region"]),
        joint_r1_pct=joint_r1_round,
        oos_rank1_freq_tens_pct=t_r1_round,
        oos_rank1_freq_units_pct=u_r1_round,
        chi2_max_overall=round(chi2_max_overall, 2),
        null_chi2_p90=round(float(null_res.p90), 2),
        null_chi2_p95=round(float(null_res.p95), 2),
        bf10_max_overall=round(bf10_max_overall, 3),
        bocd_map_run_length=bocd_r_min,
        bocd_changepoint_warning=bocd_cp_warn,
        best_oos_roi_pct=best_roi_round,
        recommended_config_id=rec_cfg_id,
        recommended_numbers=rec_numbers,
        passes_selective_alpha=passes_selective,
        strong_convergence=strong_conv,
    )

    role_label = "Đài Chủ Lực Tiềm Năng" if passes_selective else "Đứng Ngoài / Nhiễu Trắng (0x)"

    return StationDailyScorecard(
        station_code=code,
        station_name=str(meta["name"]),
        region=meta["region"],  # type: ignore[arg-type]
        draw_time_ict=meta["draw_time_ict"],  # type: ignore[arg-type]
        sample_draws_3y=n_draws,
        evaluated_oos_draws=len(eval_draws),
        last_draw_date_before_d=records[-1].draw_date,
        chi2_15_tens=round(chi2_15_t, 2),
        chi2_30_tens=round(chi2_30_t, 2),
        chi2_60_tens=round(chi2_60_t, 2),
        chi2_15_units=round(chi2_15_u, 2),
        chi2_30_units=round(chi2_30_u, 2),
        chi2_60_units=round(chi2_60_u, 2),
        chi2_max_tens=round(chi2_max_t, 2),
        chi2_max_units=round(chi2_max_u, 2),
        chi2_max_overall=round(chi2_max_overall, 2),
        null_chi2_p90=round(float(null_res.p90), 2),
        null_chi2_p95=round(float(null_res.p95), 2),
        bf10_max_tens=round(bf10_max_t, 3),
        bf10_max_units=round(bf10_max_u, 3),
        bf10_max_overall=round(bf10_max_overall, 3),
        normalized_entropy_tens=round(norm_entropy_t, 4),
        normalized_entropy_units=round(norm_entropy_u, 4),
        bocd_map_run_length_tens=bocd_r_t,
        bocd_map_run_length_units=bocd_r_u,
        bocd_map_run_length=bocd_r_min,
        bocd_changepoint_warning=bocd_cp_warn,
        oos_rank1_freq_tens_pct=t_r1_round,
        oos_rank1_freq_units_pct=u_r1_round,
        joint_r1_pct=joint_r1_round,
        p_ai_tens=list(tens_today.p_ai),
        p_bocd_tens=list(tens_today.p_bocd),
        p_seq_tens=list(tens_today.p_seq),
        p_ai_units=list(units_today.p_ai),
        p_bocd_units=list(units_today.p_bocd),
        p_seq_units=list(units_today.p_seq),
        ranked_balls_tens=list(tens_today.ranked_balls),
        ranked_balls_units=list(units_today.ranked_balls),
        joint_100_matrix=joint_matrix,
        ticket_configs=ticket_configs_map,
        recommended_config_id=rec_cfg_id,
        recommended_numbers=rec_numbers,
        best_oos_roi_pct=best_roi_round,
        station_alpha_score=alpha_score_round,
        passes_selective_alpha=passes_selective,
        strong_convergence=strong_conv,
        rank_in_day=1,
        role_label_vi=role_label,
        rationale_vi=rationale_vi,
    )


def rank_stations_for_day(
    scorecards: Sequence[StationDailyScorecard],
) -> tuple[
    list[StationDailyScorecard],
    StationDailyScorecard,
    StationDailyScorecard | None,
    list[StationDailyScorecard],
    DailyVerdictTier,
]:
    """Rank all stations opening on day D by (-station_alpha_score, station_code).

    Returns:
      (ranked_scorecards, primary_station, secondary_station, skipped_stations, verdict_tier)
    """
    if not scorecards:
        raise DataIntegrityError("scorecards cannot be empty when ranking stations for a day.")

    sorted_cards = sorted(
        scorecards,
        key=lambda sc: (-float(sc.station_alpha_score), sc.station_code),
    )

    first = sorted_cards[0]
    if not first.passes_selective_alpha:
        verdict_tier: DailyVerdictTier = "SKIP_NO_EDGE"
    else:
        verdict_tier = classify_daily_verdict_tier(
            first.joint_r1_pct,
            first.best_oos_roi_pct,
        )

    ranked: list[StationDailyScorecard] = []
    passing_idx = 0
    for idx, sc in enumerate(sorted_cards, start=1):
        if sc.passes_selective_alpha and verdict_tier != "SKIP_NO_EDGE":
            passing_idx += 1
            if passing_idx == 1:
                role = "Đài Chủ Lực (Hạng 1)"
            elif passing_idx == 2:
                role = "Đài Dự Phòng (Hạng 2)"
            else:
                role = f"Đài Đạt Chuẩn (Hạng {idx})"
        else:
            role = "Đứng Ngoài / Nhiễu Trắng (0x)"
        ranked.append(sc.model_copy(update={"rank_in_day": idx, "role_label_vi": role}))

    primary = ranked[0]
    passing_stations = [sc for sc in ranked if sc.passes_selective_alpha]
    secondary = passing_stations[1] if len(passing_stations) >= 2 else None
    skipped = [sc for sc in ranked if not sc.passes_selective_alpha]

    return (ranked, primary, secondary, skipped, verdict_tier)


def build_yesterday_settlement_summary_vi(
    yesterday_entry: BenchmarkLedgerEntry | None,
    *,
    report_date: str,
) -> str:
    """Build deterministic Vietnamese settlement summary for yesterday (D - 1) or latest settled."""
    report_dt = datetime.date.fromisoformat(_coerce_iso_date(report_date))
    yesterday_iso = (report_dt - datetime.timedelta(days=1)).isoformat()

    if yesterday_entry is None:
        return (
            f"Đối soát kỳ hôm qua ({yesterday_iso}): Chưa có bút toán đối soát đã chốt "
            f"trong Sổ cái Quỹ Chuẩn 1.000.000 VNĐ."
        )

    period_label = (
        f"kỳ hôm qua ({yesterday_entry.draw_date} - {yesterday_entry.weekday_vn})"
        if yesterday_entry.draw_date == yesterday_iso
        else f"kỳ gần nhất ({yesterday_entry.draw_date} - {yesterday_entry.weekday_vn})"
    )

    if yesterday_entry.verdict_tier == "SKIP_NO_EDGE" or yesterday_entry.cost_vnd == 0:
        return (
            f"Đối soát {period_label}: "
            f"Hệ thống kích hoạt kỷ luật BÁO NGHỈ (0.00x - Đứng ngoài bảo toàn vốn), "
            f"Chi phí = 0 VNĐ, Lãi/Lỗ ròng = +0 VNĐ, Số dư Quỹ Chuẩn giữ nguyên "
            f"{yesterday_entry.bankroll_after_vnd:,} VNĐ "
            f"(Lãi tích lũy House-Money = {yesterday_entry.house_money_after_vnd:,} VNĐ)."
        )

    if yesterday_entry.settlement_status != "SETTLED":
        return (
            f"Đối soát {period_label}: "
            f"Khuyến nghị đài {yesterday_entry.chosen_station_name} "
            f"({yesterday_entry.chosen_station_code}), gói {yesterday_entry.chosen_config_id} "
            f"({', '.join(yesterday_entry.selected_numbers)}) "
            f"đang chờ cập nhật bảng kết quả 18 giải."
        )

    hit_k = int(yesterday_entry.hit_count_k or 0)
    matched_nums = [f"{hd.number} ({hd.prize_label})" for hd in yesterday_entry.hit_details]
    hit_detail = (
        f"TRÚNG {hit_k} nháy ({', '.join(matched_nums)})" if hit_k > 0 else "Trượt (0 nháy)"
    )
    return (
        f"Đối soát {period_label}: "
        f"Đài {yesterday_entry.chosen_station_name} ({yesterday_entry.chosen_station_code}), "
        f"gói {yesterday_entry.chosen_config_id} ({', '.join(yesterday_entry.selected_numbers)}), "
        f"hệ số {yesterday_entry.recommended_multiplier:.2f}x -> {hit_detail} | "
        f"Chi = {yesterday_entry.cost_vnd:,} VNĐ, "
        f"Thu = {yesterday_entry.revenue_vnd:,} VNĐ, "
        f"Lãi/Lỗ ròng = {yesterday_entry.net_profit_vnd:+,} VNĐ | "
        f"Số dư Quỹ Chuẩn sau đối soát = {yesterday_entry.bankroll_after_vnd:,} VNĐ "
        f"(Lãi tích lũy House-Money = {yesterday_entry.house_money_after_vnd:,} VNĐ)."
    )


def build_executive_nlg_vi(
    *,
    report_date: str,
    weekday_vn: str,
    verdict_tier: DailyVerdictTier,
    primary_station: StationDailyScorecard,
    secondary_station: StationDailyScorecard | None,
    skipped_stations: Sequence[StationDailyScorecard],
    all_today_stations: Sequence[StationDailyScorecard],
    capital_guidance: CapitalGuidanceContract,
    yesterday_settlement: BenchmarkLedgerEntry | None = None,
) -> ExecutiveNLGContract:
    """Build 100% deterministic Vietnamese answers to the 4 core daily family questions.

    Every cited metric is mapped 1:1 from StationDailyScorecard and CapitalGuidanceContract.
    No LLM/AI API calls or random text templates are permitted.
    """
    p = primary_station
    be_pct = BE_PROB_SINGLE_BALL * 100.0  # 10.6904...%
    bocd_note = (
        f" Lưu ý cảnh báo BOCD: độ dài chế độ hiện tại r_t = {p.bocd_map_run_length} <= 4 kỳ "
        f"(nghi vấn lồng cầu vừa thay bóng / đổi chế độ mới)."
        if p.bocd_changepoint_warning
        else f" Độ dài chuỗi chế độ BOCD ổn định ở r_t = {p.bocd_map_run_length} kỳ (> 4 kỳ)."
    )

    yesterday_summary = build_yesterday_settlement_summary_vi(
        yesterday_settlement,
        report_date=report_date,
    )

    # -------------------------------------------------------------------------
    # Q1: Hôm nay có nên đánh không & Vì sao?
    # -------------------------------------------------------------------------
    rec_cfg = p.ticket_configs[p.recommended_config_id]
    roi_diff_clause = (
        f" (cấu hình khuyến nghị {p.recommended_config_id} đạt ROI = "
        f"{rec_cfg.oos_roi_3y_pct:+.2f}%)"
        if abs(p.best_oos_roi_pct - rec_cfg.oos_roi_3y_pct) > 1e-6
        else ""
    )
    if verdict_tier == "SKIP_NO_EDGE":
        q1_should_play = (
            f"🔴 KHUYẾN NGHỊ HÔM NAY ({report_date} - {weekday_vn}): BÁO NGHỈ — KHÔNG ĐÁNH "
            f"(ĐỨNG NGOÀI BẢO TOÀN VỐN 0.00x). "
            f"Qua tầm soát định lượng toàn bộ {len(all_today_stations)} đài mở thưởng hôm nay "
            f"bằng dữ liệu lịch sử trước giờ quay (< {report_date}), kể cả đài đứng đầu bảng là "
            f"{p.station_name} ({p.station_code}) cũng chỉ đạt xác suất trúng đồng thời "
            f"Hạng-1 hai lồng cầu JointR1 = {p.joint_r1_pct:.3f}% (so với ngưỡng lọc tối thiểu "
            f"{SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%; "
            f"Lồng Hàng Chục = {p.oos_rank1_freq_tens_pct:.2f}%, "
            f"Lồng Hàng Đơn Vị = {p.oos_rank1_freq_units_pct:.2f}% "
            f"so với điểm hòa vốn {be_pct:.2f}%) "
            f"và hiệu suất kiểm định OOS 3 năm đạt ROI = {p.best_oos_roi_pct:+.2f}%"
            f"{roi_diff_clause}. "
            f"Kiểm định đa khung W thuộc {{15, 30, 60}} ghi nhận "
            f"Chi2_max = {p.chi2_max_overall:.2f} "
            f"(ngưỡng Monte Carlo P90 = {p.null_chi2_p90:.2f}, P95 = {p.null_chi2_p95:.2f}), "
            f"Bayes Factor BF10_max = {p.bf10_max_overall:.2f}. "
            f"Toàn bộ các đài mở thưởng hôm nay đều đang nằm trong vùng nhiễu trắng "
            f"hoặc chưa đạt kỳ vọng dương sau phế, do đó hệ thống ra lệnh NGHỈ hoàn toàn "
            f"để bảo toàn 100% vốn.{bocd_note}"
        )
    else:
        tier_vn_map: dict[DailyVerdictTier, str] = {
            "PLAY_PEAK": "🟢 NÊN ĐÁNH — TÍN HIỆU HỘI TỤ ĐỈNH (PLAY_PEAK)",
            "PLAY_STANDARD": "🟢 NÊN ĐÁNH — TÍN HIỆU CHUẨN (PLAY_STANDARD)",
            "PLAY_CAUTIOUS": "🟡 NÊN ĐÁNH THĂM DÒ — TÍN HIỆU THẬN TRỌNG (PLAY_CAUTIOUS)",
            "SKIP_NO_EDGE": "🔴 BÁO NGHỈ",
        }
        q1_should_play = (
            f"{tier_vn_map[verdict_tier]} ngày {report_date} ({weekday_vn}). "
            f"Đài dẫn đầu {p.station_name} ({p.station_code} - {p.region}) vượt qua bộ lọc "
            f"Selective Alpha nghiêm ngặt (< {report_date}) với xác suất trúng đồng thời Hạng-1 "
            f"hai lồng cầu JointR1 = {p.joint_r1_pct:.3f}% (>= ngưỡng lọc "
            f"{SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%, nền đồng đều 1.000%; trong đó "
            f"Lồng Hàng Chục đạt {p.oos_rank1_freq_tens_pct:.2f}% và Lồng Hàng Đơn Vị đạt "
            f"{p.oos_rank1_freq_units_pct:.2f}% so với ngưỡng hòa vốn đơn lồng {be_pct:.2f}%) "
            f"cùng hiệu suất thực nghiệm Walk-Forward OOS 3 năm ({p.evaluated_oos_draws} kỳ) đạt "
            f"ROI = {p.best_oos_roi_pct:+.2f}% (> 0%{roi_diff_clause}). "
            f"Kiểm định thống kê đa cửa sổ W thuộc {{15, 30, 60}} đạt "
            f"Chi2_max = {p.chi2_max_overall:.2f} "
            f"(so với phân vị nhiễu trắng Monte Carlo P90 = {p.null_chi2_p90:.2f}, "
            f"P95 = {p.null_chi2_p95:.2f}), hệ số Bayes BF10_max = {p.bf10_max_overall:.2f}, "
            f"Entropy chuẩn hóa Chục/Đơn vị = "
            f"{p.normalized_entropy_tens:.4f}/{p.normalized_entropy_units:.4f}.{bocd_note}"
        )

    # -------------------------------------------------------------------------
    # Q2: Nên đánh đài gì, ở khu vực nào?
    # -------------------------------------------------------------------------
    skipped_desc_list = [
        f"{sk.station_name} ({sk.station_code} - {sk.region}, "
        f"AlphaScore={sk.station_alpha_score:+.2f}, "
        f"JointR1={sk.joint_r1_pct:.3f}%, ROI_OOS={sk.best_oos_roi_pct:+.2f}%)"
        for sk in skipped_stations
    ]
    skipped_clause = (
        f" Các đài loại bỏ / đứng ngoài hôm nay ({len(skipped_stations)} đài): "
        + "; ".join(skipped_desc_list)
        + "."
        if skipped_desc_list
        else " Toàn bộ các đài mở thưởng trong ngày đều vượt ngưỡng lọc Selective Alpha."
    )

    if verdict_tier == "SKIP_NO_EDGE":
        q2_station = (
            f"Trong tổng số {len(all_today_stations)} đài mở thưởng ngày "
            f"{report_date} ({weekday_vn}), KHÔNG có đài nào đủ tiêu chuẩn giải ngân. "
            f"Đài có điểm xếp hạng cao nhất trong ngày là {p.station_name} ({p.station_code}) "
            f"thuộc khu vực {p.region} (quay lúc {p.draw_time_ict} ICT) "
            f"với Station Alpha Score = {p.station_alpha_score:+.2f} "
            f"(JointR1 = {p.joint_r1_pct:.3f}%, ROI OOS 3 năm = {p.best_oos_roi_pct:+.2f}%), "
            f"nhưng vẫn phải đứng ngoài theo kỷ luật phanh tiền mặt."
            f"{skipped_clause}"
        )
    else:
        sec_clause = (
            f" Đài dự phòng / theo dõi phụ (Hạng 2): {secondary_station.station_name} "
            f"({secondary_station.station_code} - {secondary_station.region}, quay lúc "
            f"{secondary_station.draw_time_ict} ICT, AlphaScore = "
            f"{secondary_station.station_alpha_score:+.2f}, JointR1 = "
            f"{secondary_station.joint_r1_pct:.3f}%, ROI OOS = "
            f"{secondary_station.best_oos_roi_pct:+.2f}%, "
            f"cấu hình {secondary_station.recommended_config_id}: "
            f"{', '.join(secondary_station.recommended_numbers)})."
            if secondary_station is not None
            else " Không có đài dự phòng thứ 2 đạt chuẩn trong ngày hôm nay."
        )
        q2_station = (
            f"Ưu tiên số 1 (Đài Chủ Lực - Hạng 1/{len(all_today_stations)}): Đài {p.station_name} "
            f"({p.station_code}) thuộc khu vực {p.region}, mở thưởng lúc {p.draw_time_ict} ICT, "
            f"dẫn đầu bảng xếp hạng với Station Alpha Score = "
            f"{p.station_alpha_score:+.2f} (JointR1 = {p.joint_r1_pct:.3f}%, "
            f"ROI OOS 3 năm = {p.best_oos_roi_pct:+.2f}% trên mẫu {p.sample_draws_3y} kỳ, "
            f"kỳ gần nhất trước giờ quay là {p.last_draw_date_before_d})."
            f"{sec_clause}{skipped_clause}"
        )

    # -------------------------------------------------------------------------
    # Q3: Với đài nên đánh nhất thì đánh bộ số nào?
    # -------------------------------------------------------------------------
    rec_cfg = p.ticket_configs[p.recommended_config_id]
    top3_tens = [f"bóng {b} ({p.p_ai_tens[b] * 100.0:.2f}%)" for b in p.ranked_balls_tens[:3]]
    top4_units = [f"bóng {b} ({p.p_ai_units[b] * 100.0:.2f}%)" for b in p.ranked_balls_units[:4]]
    alt_cfgs_summary = "; ".join(
        f"gói {cid} ({', '.join(p.ticket_configs[cid].selected_numbers)}: "
        f"ROI_3Y={p.ticket_configs[cid].oos_roi_3y_pct:+.2f}%, "
        f"P(>=1 nháy/18 giải)={p.ticket_configs[cid].hit_at_least_1_in_18_prob * 100.0:.2f}%)"
        for cid in ("2x2", "1x4", "4x1", "3x3")
    )

    if verdict_tier == "SKIP_NO_EDGE":
        q3_numbers = (
            f"Do hôm nay hệ thống BÁO NGHỈ (0.00x), người chơi KHÔNG xuống tiền mua số thực tế. "
            f"Để phục vụ đối soát học thuật trên đài đứng đầu {p.station_name} ({p.station_code}), "
            f"cấu hình tham chiếu tốt nhất là gói {p.recommended_config_id} "
            f"gồm {rec_cfg.num_numbers} số: [{', '.join(p.recommended_numbers)}] "
            f"(xác suất trúng ít nhất 1 nháy trong 18 giải = "
            f"{rec_cfg.hit_at_least_1_in_18_prob * 100.0:.2f}%, ROI OOS 3 năm = "
            f"{rec_cfg.oos_roi_3y_pct:+.2f}%). Top 3 bóng Lồng Hàng Chục: {', '.join(top3_tens)}; "
            f"Top 4 bóng Lồng Hàng Đơn Vị: {', '.join(top4_units)}. "
            f"So sánh 4 cấu hình chuẩn: {alt_cfgs_summary}."
        )
    else:
        q3_numbers = (
            f"Trên Đài Chủ Lực {p.station_name} ({p.station_code}), hệ thống khuyến nghị đánh "
            f"cấu hình {p.recommended_config_id} gồm {rec_cfg.num_numbers} số hai chữ số "
            f"(Bao Lô 2 Số - 18 giải): [{', '.join(p.recommended_numbers)}]. "
            f"Phân tích xác suất bộ hợp chuẩn Brier: "
            f"Top 3 bóng Lồng Hàng Chục dẫn đầu là {', '.join(top3_tens)}; "
            f"Top 4 bóng Lồng Hàng Đơn Vị dẫn đầu là {', '.join(top4_units)}. "
            f"Gói {p.recommended_config_id} ({', '.join(p.recommended_numbers)}) "
            f"đạt xác suất trúng đơn giải {rec_cfg.single_prize_hit_prob * 100.0:.2f}%, "
            f"xác suất nổ ít nhất 1 nháy trong 18 giải đạt "
            f"{rec_cfg.hit_at_least_1_in_18_prob * 100.0:.2f}%, tần suất trúng trung bình "
            f"{rec_cfg.oos_hits_per_30_draws:.2f} nháy/30 kỳ và ROI thực nghiệm 3 năm đạt "
            f"{rec_cfg.oos_roi_3y_pct:+.2f}% "
            f"(tỷ lệ ngày có lãi {rec_cfg.oos_win_rate_3y_pct:.2f}%). "
            f"Đối chiếu toàn diện các cấu hình: {alt_cfgs_summary}."
        )

    # -------------------------------------------------------------------------
    # Q4: Đi vốn như thế nào?
    # -------------------------------------------------------------------------
    sample_rows_str = " | ".join(
        f"{row.tier_label if row.tier_label.startswith('Vốn') else f'Vốn {row.tier_label}'} "
        f"({row.capital_tier_vnd:,} VNĐ): "
        f"{row.stake_per_number_vnd:,} VNĐ/số -> Tổng chi = {row.total_daily_cost_vnd:,} VNĐ/ngày "
        f"(trúng 1 nháy thu {row.payout_per_hit_vnd:,} VNĐ, "
        f"lãi ròng {row.net_profit_1hit_vnd:+,} VNĐ)"
        for row in capital_guidance.sample_allocations
    )
    q4_capital = (
        f"Quy tắc Quản trị Vốn CPPI / House-Money (Bảo vệ đáy vốn gốc "
        f"{BENCHMARK_INITIAL_BANKROLL_VND:,} VNĐ, đơn vị chuẩn 4 số = "
        f"{BENCHMARK_BASE_DAILY_COST_4NUM_VND:,} VNĐ/ngày): "
        f"Số dư Quỹ Chuẩn hiện tại = {capital_guidance.benchmark_bankroll_vnd:,} VNĐ "
        f"(Lãi ròng tích lũy từ tiền nhà cái / House-Money Surplus = "
        f"{capital_guidance.house_money_surplus_vnd:,} VNĐ). "
        f"Hệ số đi vốn hôm nay: {capital_guidance.recommended_multiplier:.2f}x "
        f"({capital_guidance.sizing_rationale_vi}) -> Mức giải ngân chuẩn hôm nay = "
        f"{capital_guidance.benchmark_bet_vnd:,} VNĐ. "
        f"Bảng quy đổi tiền mẫu theo quy mô vốn gia đình: {sample_rows_str}."
    )

    return ExecutiveNLGContract(
        yesterday_settlement_summary_vi=yesterday_summary,
        q1_should_play_and_why=q1_should_play,
        q2_which_station_and_region=q2_station,
        q3_which_numbers_and_config=q3_numbers,
        q4_how_to_allocate_capital=q4_capital,
    )


def generate_daily_quant_report(
    report_date: str | datetime.date,
    *,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    station_histories: Mapping[str, Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]]]
    | None = None,
    ledger_state_or_path: BenchmarkLedgerState | str | Path | None = None,
    pipeline_audit: DataPipelineAuditRecord | None = None,
    generated_at_ict: str | None = None,
    warmup_draws: int = 45,
    null_sims: int = 1000,
    seed: int = 42,
    trim_to_3y: bool = True,
) -> DailyQuantReportContract:
    """Generate the complete Stage 3 DailyQuantReportContract for report_date (< D)."""
    report_iso = _coerce_iso_date(report_date)
    report_dt = datetime.date.fromisoformat(report_iso)
    weekday_py = report_dt.weekday()
    weekday_vn = WEEKDAY_VN_LABELS[weekday_py]

    if generated_at_ict is None:
        resolved_generated_at = f"{report_iso}T05:00:00+07:00"
    else:
        resolved_generated_at = generated_at_ict

    # 1. Identify stations scheduled to open on report_date
    today_codes = get_station_codes_for_weekday(weekday_py)
    if not today_codes:
        raise DataIntegrityError(f"No stations scheduled for weekday {weekday_py} ({report_iso}).")

    # 2. Score each station strictly before report_iso (< D)
    scorecards: list[StationDailyScorecard] = []
    latest_date_seen = ""
    for code in today_codes:
        if station_histories is not None and code in station_histories:
            explicit_hist: Sequence[Stage3CanonicalDrawRecord | Mapping[str, Any]] | None = (
                station_histories[code]
            )
        else:
            raw_cached = load_station_raw_cache(
                code,
                raw_dir=raw_dir,
                verify_sha256=True,
                allow_unhashed_legacy=True,
            )
            explicit_hist = [
                d for d in raw_cached if validate_iso_date(str(d.get("draw_date", ""))) < report_iso
            ]
        sc = score_station_for_date(
            code,
            target_date=report_iso,
            history_draws=explicit_hist,
            raw_dir=raw_dir,
            warmup_draws=warmup_draws,
            null_sims=null_sims,
            seed=seed,
            trim_to_3y=trim_to_3y,
        )
        scorecards.append(sc)
        if sc.last_draw_date_before_d > latest_date_seen:
            latest_date_seen = sc.last_draw_date_before_d

    # 3. Rank stations and determine daily verdict tier
    ranked, primary, secondary, skipped, verdict_tier = rank_stations_for_day(scorecards)
    should_play = verdict_tier != "SKIP_NO_EDGE"

    # 4. Load or resolve BenchmarkLedgerState (Strictly < report_iso for capital sizing)
    if isinstance(ledger_state_or_path, BenchmarkLedgerState):
        ledger_state = ledger_state_or_path
    elif isinstance(ledger_state_or_path, (str, Path)):
        ledger_path = Path(ledger_state_or_path)
        if ledger_path.exists():
            ledger_state = load_benchmark_ledger(ledger_path)
        else:
            ledger_state = initialize_empty_ledger(updated_at=resolved_generated_at)
    else:
        if DEFAULT_LEDGER_PATH.exists():
            ledger_state = load_benchmark_ledger(DEFAULT_LEDGER_PATH)
        else:
            ledger_state = initialize_empty_ledger(updated_at=resolved_generated_at)

    # Compute current bankroll from settled entries strictly before report_iso
    settled_before_d = sorted(
        (
            e
            for e in ledger_state.entries
            if e.settlement_status == "SETTLED" and e.draw_date < report_iso
        ),
        key=lambda e: e.draw_date,
    )
    current_bankroll_vnd = (
        settled_before_d[-1].bankroll_after_vnd
        if settled_before_d
        else ledger_state.starting_bankroll_vnd
    )

    rec_num_count = len(primary.recommended_numbers) if should_play else 4
    capital_guidance = build_capital_guidance(
        verdict_tier,
        current_bankroll_vnd=current_bankroll_vnd,
        initial_bankroll_vnd=ledger_state.starting_bankroll_vnd,
        base_daily_cost_vnd=BENCHMARK_BASE_DAILY_COST_4NUM_VND,
        base_stake_per_number_vnd=ledger_state.base_stake_per_number_vnd,
        base_payout_per_hit_vnd=ledger_state.payout_per_hit_vnd,
        num_numbers=rec_num_count,
    )

    # 5. Yesterday (D - 1) settlement lookup & Vietnamese summary
    yesterday_iso = (report_dt - datetime.timedelta(days=1)).isoformat()
    yesterday_entry: BenchmarkLedgerEntry | None = None
    for entry in reversed(ledger_state.entries):
        if entry.draw_date == yesterday_iso:
            yesterday_entry = entry
            break
    if yesterday_entry is None and settled_before_d:
        yesterday_entry = settled_before_d[-1]

    yesterday_summary_vi = build_yesterday_settlement_summary_vi(
        yesterday_entry,
        report_date=report_iso,
    )

    # 6. Build deterministic Vietnamese Executive NLG (4 Core Questions)
    executive_nlg = build_executive_nlg_vi(
        report_date=report_iso,
        weekday_vn=weekday_vn,
        verdict_tier=verdict_tier,
        primary_station=primary,
        secondary_station=secondary,
        skipped_stations=skipped,
        all_today_stations=ranked,
        capital_guidance=capital_guidance,
        yesterday_settlement=yesterday_entry,
    )

    # 7. Resolve DataPipelineAuditRecord
    if pipeline_audit is None:
        raw_dir_path = Path(raw_dir)
        disk_synced = (
            sum(
                1
                for st_code in VALID_35_STATION_CODES
                if (raw_dir_path / f"{st_code}_draws.json").is_file()
            )
            if raw_dir_path.is_dir()
            else 0
        )
        in_mem_synced = (
            sum(1 for st_code in VALID_35_STATION_CODES if st_code in station_histories)
            if station_histories is not None
            else 0
        )
        if station_histories is not None:
            actual_synced_ok = min(
                len(VALID_35_STATION_CODES),
                max(disk_synced, in_mem_synced, len(ranked)),
            )
        else:
            actual_synced_ok = max(disk_synced, len(ranked))
        resolved_audit = DataPipelineAuditRecord(
            audit_timestamp_ict=resolved_generated_at,
            target_date=report_iso,
            total_stations_35=len(VALID_35_STATION_CODES),
            stations_synced_ok=actual_synced_ok,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date=latest_date_seen or yesterday_iso,
            notes_vi=(
                f"Đã kiểm định PreDrawCutoffGate (< {report_iso}) và DataSchemaGate "
                f"trên {len(ranked)} đài mở thưởng ({weekday_vn}); "
                f"đồng bộ thực tế {actual_synced_ok}/{len(VALID_35_STATION_CODES)} đài."
            ),
        )
    else:
        resolved_audit = pipeline_audit

    report = DailyQuantReportContract(
        report_date=report_iso,
        weekday_vn=weekday_vn,
        generated_at_ict=resolved_generated_at,
        data_pipeline_audit=resolved_audit,
        yesterday_settlement=yesterday_entry,
        yesterday_summary_vi=yesterday_summary_vi,
        verdict_tier=verdict_tier,
        should_play_today=should_play,
        primary_station=primary,
        secondary_station=secondary,
        skipped_stations=list(skipped),
        all_today_stations=list(ranked),
        capital_guidance=capital_guidance,
        executive_nlg_vi=executive_nlg,
    )
    from xsmn_alpha.live.telegram_bot import format_telegram_executive_briefing

    report.telegram_message_html = format_telegram_executive_briefing(report)
    return report


score_single_station_for_date = score_station_for_date
