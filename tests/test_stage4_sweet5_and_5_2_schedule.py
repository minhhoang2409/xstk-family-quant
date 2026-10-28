"""Stage 4 TDD Suite: Sweet-5 Portfolio, Weekly 5/2 Cage-Balance Schedule & Anomaly Sentinel."""

from __future__ import annotations

from pathlib import Path

import pytest

from xsmn_alpha.backtest.sweet_spot_sim import (
    compute_portfolio_set_probability,
    evaluate_all_sweet_spot_portfolios,
    evaluate_stage3_ticket_portfolios,
    evaluate_stage4_ticket_portfolios,
    evaluate_sweet_spot_portfolio,
    score_single_draw_portfolio,
    select_sweet_5_numbers,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_BASE_DAILY_COST_5NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    BENCHMARK_PAYOUT_PER_HIT_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    CAGE_ANOMALY_BF10_THRESHOLD,
    CAGE_COLD_BALL_FREQ_MAX_PCT,
    CAGE_HOT_BALL_FREQ_MIN_PCT,
    EXTENDED_SWEET_SPOT_CONFIGS,
    SAMPLE_CAPITAL_TIERS_VND,
    STAGE3_TICKET_CONFIGS,
    STAGE4_MAX_STAKE_MULTIPLIER,
    STAGE4_SWEET_SPOT_CONFIGS,
    STAGE4_TICKET_CONFIGS,
    SWEET_4_NET_PROFIT_1HIT_VND,
    SWEET_4_NET_PROFIT_2HITS_VND,
    SWEET_5_NET_PROFIT_1HIT_VND,
    SWEET_5_NET_PROFIT_2HITS_VND,
    SWEET_SPOT_CONFIGS,
    THEORETICAL_MULTI_HIT_4NUM_PCT,
    THEORETICAL_MULTI_HIT_5NUM_PCT,
    THEORETICAL_WIN_RATE_4NUM_PCT,
    THEORETICAL_WIN_RATE_5NUM_PCT,
    WEEKLY_SCHEDULE_PLAY_DAYS,
    WEEKLY_SCHEDULE_REST_DAYS,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    CapitalDisciplineError,
    DataIntegrityError,
)
from xsmn_alpha.live.ledger import (
    DEFAULT_LEDGER_PATH,
    build_capital_guidance,
    compute_house_money_multiplier,
    compute_multiplier_for_verdict_tier,
    initialize_empty_ledger,
    load_benchmark_ledger,
    record_pending_recommendation,
    settle_entry_with_prizes,
    settle_ledger_for_date,
    verify_ledger_integrity,
)
from xsmn_alpha.live.registry import (
    STATION_REGISTRY_35,
    WEEKDAY_VN_LABELS,
    get_station_codes_for_weekday,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerEntry,
    CapitalGuidanceContract,
    DailyQuantReportContract,
    DataPipelineAuditRecord,
    ExecutiveNLGContract,
    HitDetailRecord,
    SampleCapitalAllocationRow,
    StationDailyScorecard,
    TicketConfigRecommendation,
    WeekdayCageBalanceSummary,
    Weekly52AndFlatStakeGate,
    WeeklySchedule52Analysis,
)


def _valid_18_prizes() -> list[str]:
    return [
        "41",
        "19",
        "73",
        "08",
        "83",
        "39",
        "88",
        "14",
        "57",
        "81",
        "23",
        "90",
        "38",
        "84",
        "61",
        "03",
        "78",
        "83",
    ]


# ===========================================================================
# Layer 1 (Task 1): Stage 4 Constants & Sweet-5 Portfolio Selection/Scoring
# ===========================================================================


class TestStage4ConstantsAndSweet5Portfolio:
    """Verify Stage 4 constants and 'sweet_5' (4 core 2x2 + 1 top satellite) simulator."""

    def test_stage4_constants_and_backward_compatibility(self) -> None:
        assert BENCHMARK_BASE_DAILY_COST_4NUM_VND == 72_000
        assert BENCHMARK_BASE_DAILY_COST_5NUM_VND == 90_000
        assert SWEET_5_NET_PROFIT_1HIT_VND == 9_500
        assert SWEET_5_NET_PROFIT_2HITS_VND == 109_000
        assert SWEET_4_NET_PROFIT_1HIT_VND == 27_500
        assert SWEET_4_NET_PROFIT_2HITS_VND == 127_000
        assert THEORETICAL_WIN_RATE_4NUM_PCT == pytest.approx(52.04)
        assert THEORETICAL_WIN_RATE_5NUM_PCT == pytest.approx(60.28)
        assert THEORETICAL_MULTI_HIT_4NUM_PCT == pytest.approx(16.13)
        assert THEORETICAL_MULTI_HIT_5NUM_PCT == pytest.approx(22.65)
        assert STAGE4_MAX_STAKE_MULTIPLIER == pytest.approx(1.0)
        assert WEEKLY_SCHEDULE_PLAY_DAYS == 5
        assert WEEKLY_SCHEDULE_REST_DAYS == 2
        assert CAGE_ANOMALY_BF10_THRESHOLD == pytest.approx(10.0)
        assert CAGE_COLD_BALL_FREQ_MAX_PCT == pytest.approx(6.5)
        assert CAGE_HOT_BALL_FREQ_MIN_PCT == pytest.approx(14.0)

        # Stage 2 & Stage 3 constant sets must remain strictly untouched
        assert len(SWEET_SPOT_CONFIGS) == 8
        assert "sweet_5" not in SWEET_SPOT_CONFIGS
        assert len(EXTENDED_SWEET_SPOT_CONFIGS) == 9
        assert "sweet_5" not in EXTENDED_SWEET_SPOT_CONFIGS
        assert STAGE3_TICKET_CONFIGS == ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3")

        # Stage 4 ticket configs & sweet spot configs
        assert STAGE4_TICKET_CONFIGS == (
            "2x2",
            "sweet_5",
            "1x4",
            "4x1",
            "3x3",
            "core_2x2_sat_3x3",
        )
        assert len(STAGE4_SWEET_SPOT_CONFIGS) == 10
        assert "sweet_5" in STAGE4_SWEET_SPOT_CONFIGS
        for cid in STAGE4_TICKET_CONFIGS:
            assert cid in STAGE4_SWEET_SPOT_CONFIGS

        cfg_s5 = STAGE4_SWEET_SPOT_CONFIGS["sweet_5"]
        assert cfg_s5["config_id"] == "sweet_5"
        assert cfg_s5["game_type"] == "bao_lo"
        assert cfg_s5["tens_top_k"] == 2
        assert cfg_s5["units_top_k"] == 2
        assert cfg_s5["num_numbers"] == 5
        assert cfg_s5["cost_per_draw"] == pytest.approx(5.0)
        assert cfg_s5["payout_per_hit"] == pytest.approx(BAO_LO_PAYOUT_PER_HIT, rel=1e-12)
        assert cfg_s5["min_hits_for_profit"] == 1
        assert cfg_s5["be_hits_30_draws"] == pytest.approx(
            (30.0 * 5.0) / BAO_LO_PAYOUT_PER_HIT, rel=1e-12
        )
        assert cfg_s5["target_hits_30_draws"] == 31

        # MappingProxyType immutability check
        with pytest.raises(TypeError):
            STAGE4_SWEET_SPOT_CONFIGS["sweet_5"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            STAGE4_SWEET_SPOT_CONFIGS["sweet_5"]["cost_per_draw"] = 4.0  # type: ignore[index]

    def test_sweet_5_bc01_uniform_tie_break_selection(self) -> None:
        p_uniform = [0.10] * 10
        selected_5, core_4, sat_1 = select_sweet_5_numbers(p_uniform, p_uniform)
        assert core_4 == ["00", "01", "10", "11"]
        assert sat_1 == ["02"]
        assert selected_5 == ["00", "01", "02", "10", "11"]
        assert select_sweet_spot_numbers(p_uniform, p_uniform, "sweet_5") == [
            "00",
            "01",
            "02",
            "10",
            "11",
        ]

    def test_sweet_5_bc02_non_uniform_satellite_selection_and_probability(self) -> None:
        # Case A: Satellite in Top-3x3 box outside 2x2
        # Top tens: ball 3 (0.18), ball 1 (0.16), ball 7 (0.14)
        # Top units: ball 8 (0.26), ball 2 (0.12), ball 1 (0.10)
        # 2x2 core = {12, 18, 32, 38}
        # Best outside 2x2 is ball 7 (0.14) x ball 8 (0.26) = 0.0364 -> "78"
        p_tens = [0.08, 0.16, 0.06, 0.18, 0.08, 0.08, 0.06, 0.14, 0.08, 0.08]
        p_units = [0.06, 0.10, 0.12, 0.07, 0.07, 0.07, 0.07, 0.06, 0.26, 0.12]
        # In p_units, ball 2 (0.12) ties with ball 9 (0.12) -> ball 2 is rank 2, ball 9 is rank 3
        selected_5, core_4, sat_1 = select_sweet_5_numbers(p_tens, p_units)
        assert core_4 == ["12", "18", "32", "38"]
        assert sat_1 == ["78"]
        assert selected_5 == ["12", "18", "32", "38", "78"]
        assert select_sweet_spot_numbers(p_tens, p_units, "sweet_5") == [
            "12",
            "18",
            "32",
            "38",
            "78",
        ]

        p_set_2x2 = compute_portfolio_set_probability(p_tens, p_units, "2x2")
        p_set_s5 = compute_portfolio_set_probability(p_tens, p_units, "sweet_5")
        expected_s5 = p_set_2x2 + (0.14 * 0.26)
        assert p_set_s5 == pytest.approx(expected_s5, rel=1e-12)

        # Case B: Exact tie in joint probability between a Top-3x3 candidate and an outside-3x3
        # candidate -> must prefer Top-3x3 candidate ("02" over "03")
        p_tens_tie = [0.20, 0.16, 0.12, 0.08, 0.08, 0.08, 0.07, 0.07, 0.07, 0.07]
        p_units_tie = [0.20, 0.15, 0.10, 0.10, 0.08, 0.08, 0.08, 0.07, 0.07, 0.07]
        sel_tie, core_tie, sat_tie = select_sweet_5_numbers(p_tens_tie, p_units_tie)
        assert core_tie == ["00", "01", "10", "11"]
        assert sat_tie == ["20"]
        assert sel_tie == ["00", "01", "10", "11", "20"]

    def test_sweet_5_scoring_and_walk_forward_evaluation(self) -> None:
        # Use probabilities from above where sweet_5 = ["12", "18", "32", "38", "78"]
        p_tens = [0.08, 0.16, 0.06, 0.18, 0.08, 0.08, 0.06, 0.14, 0.08, 0.08]
        p_units = [0.06, 0.10, 0.12, 0.07, 0.07, 0.07, 0.07, 0.06, 0.26, 0.12]
        # In _valid_18_prizes(), "38" and "78" each appear once -> 2 hits for sweet_5
        prizes = _valid_18_prizes()

        res_s5 = score_single_draw_portfolio(p_tens, p_units, prizes, "sweet_5")
        assert res_s5["config_id"] == "sweet_5"
        assert res_s5["cost"] == pytest.approx(5.0)
        assert res_s5["raw_hits"] == 2
        assert res_s5["effective_hits"] == pytest.approx(2.0)
        assert res_s5["revenue"] == pytest.approx(2.0 * BAO_LO_PAYOUT_PER_HIT)
        assert res_s5["net_profit"] == pytest.approx(2.0 * BAO_LO_PAYOUT_PER_HIT - 5.0)
        assert res_s5["is_multi_hit_ge2"] is True

        # 0-hit draw check
        zero_prizes = ["00"] * 18
        res_zero = score_single_draw_portfolio(p_tens, p_units, zero_prizes, "sweet_5")
        assert res_zero["raw_hits"] == 0
        assert res_zero["cost"] == pytest.approx(5.0)
        assert res_zero["revenue"] == pytest.approx(0.0)
        assert res_zero["net_profit"] == pytest.approx(-5.0)
        assert res_zero["is_multi_hit_ge2"] is False

        # Walk-forward evaluation for sweet_5
        metrics = evaluate_sweet_spot_portfolio(
            [p_tens, p_tens],
            [p_units, p_units],
            [prizes, zero_prizes],
            "sweet_5",
        )
        assert metrics.config_id == "sweet_5"
        assert metrics.evaluated_draws == 2
        assert metrics.cost_per_draw == pytest.approx(5.0)
        assert metrics.total_cost == pytest.approx(10.0)
        assert metrics.total_hits == pytest.approx(2.0)
        assert metrics.daily_win_rate == pytest.approx(0.5)
        assert metrics.multi_hit_rate_ge2 == pytest.approx(0.5)
        assert metrics.zero_hit_rate_k0 == pytest.approx(0.5)

        # Stage 4 vs Stage 3 vs Stage 2 batch evaluators
        s4_all = evaluate_stage4_ticket_portfolios([p_tens], [p_units], [prizes])
        assert tuple(s4_all.keys()) == STAGE4_TICKET_CONFIGS
        assert "sweet_5" in s4_all

        s3_all = evaluate_stage3_ticket_portfolios([p_tens], [p_units], [prizes])
        assert tuple(s3_all.keys()) == STAGE3_TICKET_CONFIGS
        assert "sweet_5" not in s3_all

        s2_all = evaluate_all_sweet_spot_portfolios([p_tens], [p_units], [prizes])
        assert set(s2_all.keys()) == set(SWEET_SPOT_CONFIGS.keys())
        assert "sweet_5" not in s2_all

    def test_sweet_5_negative_mutations_invalid_simplex_and_unknown_config(self) -> None:
        valid_p = [0.10] * 10
        bad_p_sum = [0.05] * 10  # sums to 0.50 != 1.0
        bad_p_neg = [-0.10, 0.20, *[0.1125] * 8]

        with pytest.raises(CalibrationIntegrityError):
            select_sweet_5_numbers(bad_p_sum, valid_p)
        with pytest.raises(CalibrationIntegrityError):
            select_sweet_5_numbers(valid_p, bad_p_neg)
        with pytest.raises(CalibrationIntegrityError):
            select_sweet_spot_numbers(bad_p_sum, valid_p, "sweet_5")
        with pytest.raises(CalibrationIntegrityError):
            compute_portfolio_set_probability(bad_p_sum, valid_p, "sweet_5")

        with pytest.raises(DataIntegrityError):
            select_sweet_spot_numbers(valid_p, valid_p, "sweet_6_invalid")
        with pytest.raises(DataIntegrityError):
            compute_portfolio_set_probability(valid_p, valid_p, "sweet_6_invalid")
        with pytest.raises(DataIntegrityError):
            score_single_draw_portfolio(valid_p, valid_p, _valid_18_prizes(), "sweet_6_invalid")
        with pytest.raises(DataIntegrityError):
            evaluate_sweet_spot_portfolio(
                [valid_p], [valid_p], [_valid_18_prizes()], "sweet_6_invalid"
            )


# ===========================================================================
# Layer 2 (Task 2): Stage 4 Pydantic v2 Contracts & Gate 6 Hardening
# ===========================================================================


def _make_sweet_5_ticket_rec(
    core_nums: list[str] | None = None,
    sat_nums: list[str] | None = None,
) -> TicketConfigRecommendation:
    core = core_nums if core_nums is not None else ["21", "22", "31", "32"]
    sat = sat_nums if sat_nums is not None else ["23"]
    selected = sorted([*core, *sat])
    cfg = STAGE4_SWEET_SPOT_CONFIGS["sweet_5"]
    return TicketConfigRecommendation(
        config_id="sweet_5",
        label=str(cfg["label"]),
        num_numbers=5,
        selected_numbers=selected,
        core_numbers=core,
        satellite_numbers=sat,
        unit_cost_per_draw=5.0,
        benchmark_1x_cost_vnd=90_000,
        single_prize_hit_prob=0.056,
        hit_at_least_1_in_18_prob=1.0 - (0.944**18),
        oos_roi_3y_pct=6.12,
        oos_win_rate_3y_pct=60.5,
        oos_hits_per_30_draws=float(cfg["be_hits_30_draws"]) + 1.8,
        be_hits_30_draws=float(cfg["be_hits_30_draws"]),
        is_recommended_primary=False,
    )


def _make_stage3_ticket_configs(primary_cfg: str = "2x2") -> dict[str, TicketConfigRecommendation]:
    configs: dict[str, TicketConfigRecommendation] = {}
    sample_nums: dict[str, list[str]] = {
        "2x2": ["21", "22", "31", "32"],
        "1x4": ["21", "22", "23", "28"],
        "4x1": ["01", "11", "21", "31"],
        "3x3": ["21", "22", "23", "31", "32", "33", "41", "42", "43"],
        "core_2x2_sat_3x3": ["21", "22", "23", "31", "32", "33", "41", "42", "43"],
    }
    for cid in STAGE3_TICKET_CONFIGS:
        cfg_meta = STAGE4_SWEET_SPOT_CONFIGS[cid]
        nums = sample_nums[cid]
        unit_cost = float(cfg_meta["cost_per_draw"])
        p_s = 0.045 if len(nums) == 4 else 0.095
        configs[cid] = TicketConfigRecommendation(
            config_id=cid,
            label=str(cfg_meta["label"]),
            num_numbers=int(cfg_meta["num_numbers"]),
            selected_numbers=nums,
            core_numbers=["21", "22", "31", "32"] if cid == "core_2x2_sat_3x3" else nums,
            satellite_numbers=["23", "33", "41", "42", "43"] if cid == "core_2x2_sat_3x3" else [],
            unit_cost_per_draw=unit_cost,
            benchmark_1x_cost_vnd=int(round(unit_cost * BENCHMARK_STAKE_PER_NUMBER_VND)),
            single_prize_hit_prob=p_s,
            hit_at_least_1_in_18_prob=1.0 - ((1.0 - p_s) ** 18),
            oos_roi_3y_pct=8.50 if cid == primary_cfg else 3.20,
            oos_win_rate_3y_pct=55.0,
            oos_hits_per_30_draws=float(cfg_meta["be_hits_30_draws"]) + 1.5,
            be_hits_30_draws=float(cfg_meta["be_hits_30_draws"]),
            is_recommended_primary=(cid == primary_cfg),
        )
    return configs


def _make_stage4_scorecard(
    station_code: str = "XSBT",
    station_name: str = "Bến Tre",
    region: str = "Miền Nam",
    draw_time_ict: str = "16:15",
    last_draw_date: str = "2026-10-20",
    *,
    passes_alpha: bool = False,
    passes_weekly_5_2_play: bool = True,
    cage_anomaly_detected: bool = True,
    sweet_5_numbers: list[str] | None = None,
) -> StationDailyScorecard:
    s5_nums = sweet_5_numbers if sweet_5_numbers is not None else ["21", "22", "23", "31", "32"]
    return StationDailyScorecard(
        station_code=station_code,
        station_name=station_name,
        region=region,  # type: ignore[arg-type]
        draw_time_ict=draw_time_ict,  # type: ignore[arg-type]
        sample_draws_3y=156,
        evaluated_oos_draws=111,
        last_draw_date_before_d=last_draw_date,
        chi2_15_tens=24.5,
        chi2_30_tens=38.2,
        chi2_60_tens=50.35,
        chi2_15_units=14.1,
        chi2_30_units=19.8,
        chi2_60_units=22.0,
        chi2_max_tens=50.35,
        chi2_max_units=22.0,
        chi2_max_overall=50.35,
        null_chi2_p90=18.5,
        null_chi2_p95=21.2,
        bf10_max_tens=1.82e7,
        bf10_max_units=2.45,
        bf10_max_overall=1.82e7,
        normalized_entropy_tens=0.971,
        normalized_entropy_units=0.988,
        bocd_map_run_length_tens=42,
        bocd_map_run_length_units=25,
        bocd_map_run_length=25,
        bocd_changepoint_warning=False,
        p_ai_tens=[0.10] * 10,
        p_bocd_tens=[0.10] * 10,
        p_seq_tens=[0.10] * 10,
        ranked_balls_tens=[2, 3, 0, 1, 5, 6, 7, 8, 9, 4],
        p_ai_units=[0.10] * 10,
        p_bocd_units=[0.10] * 10,
        p_seq_units=[0.10] * 10,
        ranked_balls_units=[1, 2, 3, 8, 0, 4, 5, 7, 9, 6],
        joint_100_matrix=[[0.01] * 10 for _ in range(10)],
        oos_rank1_freq_tens_pct=11.2 if passes_alpha else 10.4,
        oos_rank1_freq_units_pct=10.8 if passes_alpha else 10.2,
        joint_r1_pct=1.166 if passes_alpha else 1.061,
        recommended_config_id="2x2",
        recommended_numbers=["21", "22", "31", "32"],
        best_oos_roi_pct=8.50 if passes_alpha else -1.20,
        ticket_configs=_make_stage3_ticket_configs("2x2"),
        station_alpha_score=25.4 if passes_alpha else 12.8,
        passes_selective_alpha=passes_alpha,
        strong_convergence=False,
        rank_in_day=1,
        role_label_vi="Đài Chủ Lực Điểm Ngọt Lịch 5/2",
        rationale_vi="Phát hiện lồng cầu lệch mạnh tại Bến Tre (Chi2_max = 50.35).",
        sweet_5_numbers=s5_nums,
        sweet_5_config=_make_sweet_5_ticket_rec(),
        cage_anomaly_detected=cage_anomaly_detected,
        cage_anomaly_summary_vi=(
            "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH: Đài Bến Tre (XSBT) vượt ngưỡng P95."
            if cage_anomaly_detected
            else ""
        ),
        cold_balls_tens=[4] if cage_anomaly_detected else [],
        cold_balls_units=[6] if cage_anomaly_detected else [],
        passes_weekly_5_2_play=passes_weekly_5_2_play,
    )


def _make_sample_allocations(multiplier: float = 1.0) -> list[SampleCapitalAllocationRow]:
    rows: list[SampleCapitalAllocationRow] = []
    labels = {
        500_000: "Vốn 500k",
        1_000_000: "Vốn 1 Triệu",
        2_000_000: "Vốn 2 Triệu",
        5_000_000: "Vốn 5 Triệu",
    }
    for tier in SAMPLE_CAPITAL_TIERS_VND:
        scale = tier / float(BENCHMARK_INITIAL_BANKROLL_VND)
        stake = int(round(BENCHMARK_STAKE_PER_NUMBER_VND * scale * multiplier))
        cost = 4 * stake
        payout = int(round(BENCHMARK_PAYOUT_PER_HIT_VND * scale * multiplier))
        rows.append(
            SampleCapitalAllocationRow(
                capital_tier_vnd=tier,
                tier_label=labels[tier],
                scale_factor=scale,
                recommended_multiplier=multiplier,
                stake_per_number_vnd=stake,
                num_numbers=4,
                total_daily_cost_vnd=cost,
                payout_per_hit_vnd=payout,
                net_profit_1hit_vnd=(payout - cost) if multiplier > 0.0 else 0,
                net_profit_2hits_vnd=(2 * payout - cost) if multiplier > 0.0 else 0,
                net_profit_3hits_vnd=(3 * payout - cost) if multiplier > 0.0 else 0,
            )
        )
    return rows


def _make_valid_weekly_52_schedule(
    as_of_date: str = "2026-10-27",
    target_weekday: int = 1,
) -> WeeklySchedule52Analysis:
    # Ordered by balance_rank 1..7 (non-decreasing max_chi2_overall):
    # Rank 1: Wed (2, 13.22), Rank 2: Mon (0, 15.07) -> REST DAYS
    # Rank 3: Thu (3, 18.40), Rank 4: Fri (4, 21.10), Rank 5: Sat (5, 23.50),
    # Rank 6: Sun (6, 26.80), Rank 7: Tue (1, 50.35) -> PLAY DAYS
    spec_order = [
        (2, 13.22, 11.10, 0.35, 0.9945, True),
        (0, 15.07, 12.40, 0.52, 0.9938, True),
        (3, 18.40, 14.20, 1.15, 0.9910, False),
        (4, 21.10, 15.80, 2.30, 0.9890, False),
        (5, 23.50, 16.90, 4.10, 0.9860, False),
        (6, 26.80, 17.50, 8.50, 0.9830, False),
        (1, 50.35, 22.10, 1.82e7, 0.9710, False),
    ]
    rankings: list[WeekdayCageBalanceSummary] = []
    today_rank = 1
    is_rest = False
    for rank_idx, (wd, max_c2, mean_c2, max_bf, min_ent, rest_flag) in enumerate(
        spec_order, start=1
    ):
        codes = list(get_station_codes_for_weekday(wd))
        lead_code = codes[0]
        lead_name = str(STATION_REGISTRY_35[lead_code]["name"])
        if wd == target_weekday:
            today_rank = rank_idx
            is_rest = rest_flag
        rankings.append(
            WeekdayCageBalanceSummary(
                weekday=wd,
                weekday_vn=WEEKDAY_VN_LABELS[wd],
                balance_rank=rank_idx,
                num_stations=len(codes),
                station_codes=codes,
                lead_station_code=lead_code,
                lead_station_name=lead_name,
                max_chi2_overall=max_c2,
                mean_chi2_overall=mean_c2,
                max_bf10_overall=max_bf,
                min_entropy_overall=min_ent,
                is_rest_day=rest_flag,
            )
        )
    rest_wds = (rankings[0].weekday, rankings[1].weekday)
    rest_vns = (rankings[0].weekday_vn, rankings[1].weekday_vn)
    play_wds = tuple(r.weekday for r in rankings[2:])
    play_vns = tuple(r.weekday_vn for r in rankings[2:])
    return WeeklySchedule52Analysis(
        as_of_date=as_of_date,
        target_weekday=target_weekday,
        target_weekday_vn=WEEKDAY_VN_LABELS[target_weekday],
        today_balance_rank=today_rank,
        is_today_scheduled_rest_day=is_rest,
        rest_weekdays=rest_wds,  # type: ignore[arg-type]
        rest_weekdays_vn=rest_vns,  # type: ignore[arg-type]
        play_weekdays=play_wds,  # type: ignore[arg-type]
        play_weekdays_vn=play_vns,  # type: ignore[arg-type]
        weekday_rankings=rankings,
    )


class TestStage4SchemasAndGate6:
    """Verify Task 2 Stage 4 Pydantic v2 contracts and Gate 6 (Weekly52AndFlatStakeGate)."""

    def test_gate6_weekly_schedule_52_analysis_pass_and_negative_mutations(self) -> None:
        sched = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        assert sched.rest_weekdays == (2, 0)
        assert sched.rest_weekdays_vn == ("Thứ 4", "Thứ 2")
        assert len(sched.play_weekdays) == WEEKLY_SCHEDULE_PLAY_DAYS
        assert sched.today_balance_rank == 7
        assert sched.is_today_scheduled_rest_day is False
        assert Weekly52AndFlatStakeGate.enforce_schedule(sched) is sched

        # Rest day target (Monday = 0 -> rank 2, is_today_scheduled_rest_day = True)
        sched_mon = _make_valid_weekly_52_schedule("2026-10-26", target_weekday=0)
        assert sched_mon.today_balance_rank == 2
        assert sched_mon.is_today_scheduled_rest_day is True

        # Negative Mutation 1: 3 rest days in weekday_rankings -> DataIntegrityError
        bad_3_rest = sched.model_dump()
        bad_3_rest["weekday_rankings"][2]["is_rest_day"] = True
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_3_rest)

        # Negative Mutation 2: rest_weekdays has 3 elements instead of 2 -> DataIntegrityError
        bad_tuple_len = sched.model_dump()
        bad_tuple_len["rest_weekdays"] = (2, 0, 3)
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_tuple_len)

        # Negative Mutation 3: max_chi2_overall decreases with balance_rank -> DataIntegrityError
        bad_chi2_order = sched.model_dump()
        bad_chi2_order["weekday_rankings"][0]["max_chi2_overall"] = 30.0  # > rank 2 (15.07)
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_chi2_order)

        # Negative Mutation 4: duplicate weekday in weekday_rankings -> DataIntegrityError
        bad_dup_wd = sched.model_dump()
        bad_dup_wd["weekday_rankings"][6]["weekday"] = 0
        bad_dup_wd["weekday_rankings"][6]["weekday_vn"] = "Thứ 2"
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_dup_wd)

        # Negative Mutation 5: non-sequential balance_rank -> DataIntegrityError
        bad_ranks = sched.model_dump()
        bad_ranks["weekday_rankings"][0]["balance_rank"] = 2
        bad_ranks["weekday_rankings"][1]["balance_rank"] = 1
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_ranks)

        # Negative Mutation 6: is_today_scheduled_rest_day conflicts with rest_weekdays
        bad_today_flag = sched.model_dump()
        bad_today_flag["is_today_scheduled_rest_day"] = True  # Tue (1) is a play day!
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_today_flag)

    def test_gate6_ticket_config_and_scorecard_sweet_5_validation(self) -> None:
        rec_s5 = _make_sweet_5_ticket_rec()
        assert rec_s5.config_id == "sweet_5"
        assert rec_s5.num_numbers == 5
        assert len(rec_s5.core_numbers) == 4
        assert len(rec_s5.satellite_numbers) == 1

        # Negative Mutation on TicketConfigRecommendation for sweet_5:
        # wrong core/satellite split (3 core + 2 sat) -> DataIntegrityError
        bad_rec = rec_s5.model_dump()
        bad_rec["core_numbers"] = ["21", "22", "31"]
        bad_rec["satellite_numbers"] = ["23", "32"]
        with pytest.raises(DataIntegrityError):
            TicketConfigRecommendation.model_validate(bad_rec)

        # StationDailyScorecard with valid Stage 4 fields
        sc = _make_stage4_scorecard()
        assert sc.sweet_5_numbers == ["21", "22", "23", "31", "32"]
        assert sc.sweet_5_config is not None
        assert sc.cage_anomaly_detected is True
        assert sc.cold_balls_tens == [4]
        assert sc.cold_balls_units == [6]
        assert sc.passes_weekly_5_2_play is True

        # Negative Mutation 1 (Todo Task 2 Manual Check):
        # sweet_5_numbers has only 4 numbers -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            _make_stage4_scorecard(sweet_5_numbers=["21", "22", "31", "32"])

        # Negative Mutation 2: sweet_5_numbers has duplicate numbers -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            _make_stage4_scorecard(sweet_5_numbers=["21", "22", "31", "32", "32"])

        # Negative Mutation 3 (Todo Task 2 Manual Check):
        # sweet_5_numbers has 5 unique numbers but is missing "32" from 2x2 -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            _make_stage4_scorecard(sweet_5_numbers=["21", "22", "23", "24", "31"])

        # Negative Mutation 4: invalid cold_balls_tens element (out of 0..9) -> DataIntegrityError
        bad_cold = sc.model_dump()
        bad_cold["cold_balls_tens"] = [10]
        with pytest.raises(DataIntegrityError):
            StationDailyScorecard.model_validate(bad_cold)

    def test_gate6_benchmark_ledger_entry_supports_sweet_5_and_flat_stake_gate(self) -> None:
        # Pending & Settled BenchmarkLedgerEntry with chosen_config_id="sweet_5" (5 numbers, 90k)
        prizes_1hit = _valid_18_prizes()  # "23" hits once at index 10
        entry_s5 = BenchmarkLedgerEntry(
            draw_date="2026-10-27",
            weekday_vn="Thứ 3",
            settlement_status="SETTLED",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSBT",
            chosen_station_name="Bến Tre",
            chosen_region="Miền Nam",
            chosen_config_id="sweet_5",
            selected_numbers=["21", "22", "23", "31", "32"],
            recommended_multiplier=1.0,
            bankroll_before_vnd=1_000_000,
            house_money_before_vnd=0,
            cost_vnd=90_000,
            actual_prizes_last2=prizes_1hit,
            hit_count_k=1,
            hit_details=[HitDetailRecord(prize_index=10, prize_label="Giải Tư (5)", number="23")],
            revenue_vnd=99_500,
            net_profit_vnd=9_500,
            bankroll_after_vnd=1_009_500,
            house_money_after_vnd=9_500,
        )
        assert entry_s5.cost_vnd == BENCHMARK_BASE_DAILY_COST_5NUM_VND
        assert entry_s5.net_profit_vnd == SWEET_5_NET_PROFIT_1HIT_VND

        # Negative Mutation: sweet_5 entry with only 4 selected_numbers -> DataIntegrityError
        bad_s5 = entry_s5.model_dump()
        bad_s5["selected_numbers"] = ["21", "22", "31", "32"]
        with pytest.raises(DataIntegrityError):
            BenchmarkLedgerEntry.model_validate(bad_s5)

        # Gate 6 Flat Stake helper check
        assert Weekly52AndFlatStakeGate.enforce_flat_stake(
            1.0, should_play_today=True, lock_flat_1x=True
        ) == pytest.approx(1.0)
        assert Weekly52AndFlatStakeGate.enforce_flat_stake(
            0.0, should_play_today=False, lock_flat_1x=True
        ) == pytest.approx(0.0)
        with pytest.raises(CapitalDisciplineError):
            Weekly52AndFlatStakeGate.enforce_flat_stake(
                1.25, should_play_today=True, lock_flat_1x=True
            )
        with pytest.raises(CapitalDisciplineError):
            Weekly52AndFlatStakeGate.enforce_flat_stake(
                1.50, should_play_today=True, lock_flat_1x=True
            )

    def test_daily_quant_report_contract_with_weekly_52_schedule_and_passes_play(self) -> None:
        sched = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        # Primary station has passes_selective_alpha=False, passes_weekly_5_2_play=True
        sc_primary = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=True,
        )
        cap_1x = CapitalGuidanceContract(
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            recommended_multiplier=1.0,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=72_000,
            stake_per_number_vnd=18_000,
            payout_per_hit_vnd=99_500,
            sample_allocations=_make_sample_allocations(1.0),
            sizing_rationale_vi="Khóa cứng 1.0x theo Kỷ Luật Tiền Chợ Đều Tay Lịch 5/2.",
        )
        nlg = ExecutiveNLGContract(
            yesterday_settlement_summary_vi="Hôm qua nghỉ định kỳ Thứ 2 (0.0x).",
            q1_should_play_and_why="CHƠI ĐỀU TAY 1.0x — Thứ 3 thuộc 5 ngày chơi Điểm Ngọt.",
            q2_which_station_and_region="Đài Chủ Lực: Bến Tre (Miền Nam - 16:15).",
            q3_which_numbers_and_config="Bộ 5 số Điểm Ngọt: 21, 22, 23, 31, 32.",
            q4_how_to_allocate_capital="Khóa trần 1.0x đều tay (72k cho 4 số / 90k cho 5 số).",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-27",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-26",
        )
        report = DailyQuantReportContract(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            generated_at_ict="2026-10-27T05:00:00+07:00",
            data_pipeline_audit=audit,
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            primary_station=sc_primary,
            secondary_station=None,
            skipped_stations=[],
            all_today_stations=[sc_primary],
            capital_guidance=cap_1x,
            executive_nlg_vi=nlg,
            weekly_5_2_schedule=sched,
        )
        assert report.weekly_5_2_schedule is not None
        assert report.primary_station.passes_weekly_5_2_play is True
        assert report.primary_station.passes_selective_alpha is False

        # Negative Mutation 1: Both passes_selective_alpha and passes_weekly_5_2_play are False
        # when verdict_tier != "SKIP_NO_EDGE" -> DataIntegrityError
        sc_neither = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=False,
        )
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-27",
                weekday_vn="Thứ 3",
                generated_at_ict="2026-10-27T05:00:00+07:00",
                data_pipeline_audit=audit,
                verdict_tier="PLAY_STANDARD",
                should_play_today=True,
                primary_station=sc_neither,
                all_today_stations=[sc_neither],
                capital_guidance=cap_1x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=sched,
            )

        # Negative Mutation 2: weekly_5_2_schedule present with multiplier > 1.0 (1.25x)
        # -> CapitalDisciplineError
        cap_125x = CapitalGuidanceContract(
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            recommended_multiplier=1.25,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=90_000,
            stake_per_number_vnd=22_500,
            payout_per_hit_vnd=124_375,
            sample_allocations=_make_sample_allocations(1.25),
            sizing_rationale_vi="Mutated 1.25x.",
        )
        with pytest.raises(CapitalDisciplineError):
            DailyQuantReportContract(
                report_date="2026-10-27",
                weekday_vn="Thứ 3",
                generated_at_ict="2026-10-27T05:00:00+07:00",
                data_pipeline_audit=audit,
                verdict_tier="PLAY_STANDARD",
                should_play_today=True,
                primary_station=sc_primary,
                all_today_stations=[sc_primary],
                capital_guidance=cap_125x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=sched,
            )


# ===========================================================================
# Layer 3 (Task 3): Benchmark Ledger Sweet-5 Settlement & Flat 1.0x Brake
# ===========================================================================


class TestStage4LedgerSweet5AndFlat1xCapitalBrake:
    """Verify Task 3 flat 1.0x capital brake (BC-07, EARS-R02), sweet_5 settlement, and BC-08."""

    def test_bc07_flat_1x_capital_brake_on_multiplier_and_guidance(self) -> None:
        # Even when house_money_surplus_vnd is 4,911,500 VND (current_bankroll = 5,911,500 VND),
        # lock_flat_1x=True must lock recommended_multiplier == 1.0 on play days and 0.0 on skip.
        huge_bankroll = 5_911_500

        assert compute_multiplier_for_verdict_tier(
            "PLAY_STANDARD",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        ) == (1.0, BENCHMARK_BASE_DAILY_COST_4NUM_VND)

        assert compute_multiplier_for_verdict_tier(
            "PLAY_PEAK",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        ) == (1.0, BENCHMARK_BASE_DAILY_COST_4NUM_VND)

        assert compute_multiplier_for_verdict_tier(
            "PLAY_CAUTIOUS",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        ) == (1.0, BENCHMARK_BASE_DAILY_COST_4NUM_VND)

        assert compute_multiplier_for_verdict_tier(
            "PLAY_STANDARD",
            current_bankroll_vnd=huge_bankroll,
            base_daily_cost_vnd=BENCHMARK_BASE_DAILY_COST_5NUM_VND,
            lock_flat_1x=True,
        ) == (1.0, BENCHMARK_BASE_DAILY_COST_5NUM_VND)

        assert compute_multiplier_for_verdict_tier(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        ) == (0.0, 0)

        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        ) == (1.0, BENCHMARK_BASE_DAILY_COST_4NUM_VND)

        # 4-number 2x2 guidance with lock_flat_1x=True
        g_4num = build_capital_guidance(
            "PLAY_STANDARD",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        )
        assert g_4num.should_play_today is True
        assert g_4num.recommended_multiplier == pytest.approx(1.0)
        assert g_4num.house_money_surplus_vnd == 4_911_500
        assert g_4num.benchmark_bet_vnd == 72_000
        assert g_4num.stake_per_number_vnd == 18_000
        assert g_4num.payout_per_hit_vnd == 99_500

        # 5-number sweet_5 guidance with lock_flat_1x=True
        g_5num = build_capital_guidance(
            "PLAY_STANDARD",
            current_bankroll_vnd=huge_bankroll,
            base_daily_cost_vnd=BENCHMARK_BASE_DAILY_COST_5NUM_VND,
            num_numbers=5,
            lock_flat_1x=True,
        )
        assert g_5num.should_play_today is True
        assert g_5num.recommended_multiplier == pytest.approx(1.0)
        assert g_5num.benchmark_bet_vnd == 90_000
        by_tier_5 = {r.capital_tier_vnd: r for r in g_5num.sample_allocations}
        assert by_tier_5[1_000_000].total_daily_cost_vnd == 90_000
        assert by_tier_5[1_000_000].net_profit_1hit_vnd == SWEET_5_NET_PROFIT_1HIT_VND
        assert by_tier_5[1_000_000].net_profit_2hits_vnd == SWEET_5_NET_PROFIT_2HITS_VND
        assert by_tier_5[2_000_000].total_daily_cost_vnd == 180_000
        assert by_tier_5[2_000_000].net_profit_2hits_vnd == 218_000

        # Skip guidance with lock_flat_1x=True
        g_skip = build_capital_guidance(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=huge_bankroll,
            lock_flat_1x=True,
        )
        assert g_skip.should_play_today is False
        assert g_skip.recommended_multiplier == 0.0
        assert g_skip.benchmark_bet_vnd == 0

    def test_ears_r02_negative_mutations_on_flat_1x_capital_brake(self) -> None:
        huge_bankroll = 5_911_500

        # Forcing multiplier=1.25 or 1.5 under lock_flat_1x=True -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            build_capital_guidance(
                "PLAY_STANDARD",
                current_bankroll_vnd=huge_bankroll,
                recommended_multiplier=1.25,
                lock_flat_1x=True,
            )
        with pytest.raises(CapitalDisciplineError):
            build_capital_guidance(
                "PLAY_PEAK",
                current_bankroll_vnd=huge_bankroll,
                recommended_multiplier=1.50,
                lock_flat_1x=True,
            )
        with pytest.raises(CapitalDisciplineError):
            build_capital_guidance(
                "SKIP_NO_EDGE",
                current_bankroll_vnd=huge_bankroll,
                recommended_multiplier=1.0,
                lock_flat_1x=True,
            )

        state = initialize_empty_ledger()
        with pytest.raises(CapitalDisciplineError):
            record_pending_recommendation(
                state,
                draw_date="2026-10-27",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSBT",
                chosen_config_id="sweet_5",
                selected_numbers=["21", "22", "23", "31", "32"],
                recommended_multiplier=1.25,
                lock_flat_1x=True,
            )

    def test_sweet_5_ledger_record_and_settle_0_1_2_hits_and_idempotency(
        self, tmp_path: Path
    ) -> None:
        ledger_file = tmp_path / "stage4_sweet5_ledger.json"
        state0 = initialize_empty_ledger(updated_at="2026-10-20T05:00:00+07:00")
        sweet5_nums = ["21", "22", "23", "31", "32"]

        # 1. Day 1 (2026-10-20, Tue, XSBT): Record PENDING sweet_5 at 1.0x (cost = 90,000 VND)
        state1_pending = record_pending_recommendation(
            state0,
            draw_date="2026-10-20",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSBT",
            chosen_config_id="sweet_5",
            selected_numbers=sweet5_nums,
            lock_flat_1x=True,
            updated_at="2026-10-20T05:05:00+07:00",
            ledger_path=ledger_file,
        )
        assert state1_pending.entries[0].chosen_config_id == "sweet_5"
        assert state1_pending.entries[0].recommended_multiplier == pytest.approx(1.0)
        assert state1_pending.entries[0].cost_vnd == 90_000
        assert state1_pending.entries[0].settlement_status == "PENDING"

        # Settle Day 1 with 1 hit ("23" at prize_index 10 in _valid_18_prizes())
        # -> gross = 99,500 VND, net = +9,500 VND, bankroll = 1,009,500 VND
        prizes_1hit = _valid_18_prizes()
        state1_settled = settle_ledger_for_date(
            ledger_file,
            draw_date="2026-10-20",
            actual_prizes_last2=prizes_1hit,
            updated_at="2026-10-20T16:40:00+07:00",
        )
        e1 = state1_settled.entries[0]
        assert e1.settlement_status == "SETTLED"
        assert e1.hit_count_k == 1
        assert e1.cost_vnd == 90_000
        assert e1.revenue_vnd == 99_500
        assert e1.net_profit_vnd == 9_500
        assert state1_settled.current_bankroll_vnd == 1_009_500
        assert state1_settled.house_money_surplus_vnd == 9_500

        # Idempotent re-settlement check
        state1_repeat = settle_ledger_for_date(
            ledger_file,
            draw_date="2026-10-20",
            actual_prizes_last2=prizes_1hit,
            updated_at="2026-10-20T17:00:00+07:00",
        )
        assert state1_repeat.current_bankroll_vnd == 1_009_500
        assert state1_repeat.sha256 == state1_settled.sha256

        # 2. Day 2 (2026-10-27, Tue, XSBT): Record & settle sweet_5 with 2 hits
        # -> gross = 199,000 VND, net = +109,000 VND, bankroll = 1,118,500 VND
        state2_pending = record_pending_recommendation(
            state1_repeat,
            draw_date="2026-10-27",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSBT",
            chosen_config_id="sweet_5",
            selected_numbers=sweet5_nums,
            lock_flat_1x=True,
            updated_at="2026-10-27T05:00:00+07:00",
            ledger_path=ledger_file,
        )
        prizes_2hits = ["21", "32", *(["99"] * 16)]
        state2_settled = settle_ledger_for_date(
            state2_pending,
            draw_date="2026-10-27",
            actual_prizes_last2=prizes_2hits,
            ledger_path=ledger_file,
            updated_at="2026-10-27T16:40:00+07:00",
        )
        e2 = state2_settled.entries[1]
        assert e2.hit_count_k == 2
        assert e2.cost_vnd == 90_000
        assert e2.revenue_vnd == 199_000
        assert e2.net_profit_vnd == 109_000
        assert state2_settled.current_bankroll_vnd == 1_118_500
        assert state2_settled.house_money_surplus_vnd == 118_500

        # 3. Day 3 (2026-11-03, Tue, XSBT): Record & settle sweet_5 with 0 hits
        # -> gross = 0 VND, net = -90,000 VND, bankroll = 1,028,500 VND
        state3_pending = record_pending_recommendation(
            state2_settled,
            draw_date="2026-11-03",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSBT",
            chosen_config_id="sweet_5",
            selected_numbers=sweet5_nums,
            lock_flat_1x=True,
            updated_at="2026-11-03T05:00:00+07:00",
            ledger_path=ledger_file,
        )
        prizes_0hits = ["99"] * 18
        e3_direct = settle_entry_with_prizes(state3_pending.entries[2], prizes_0hits)
        assert e3_direct.hit_count_k == 0
        assert e3_direct.revenue_vnd == 0
        assert e3_direct.net_profit_vnd == -90_000

        state3_settled = settle_ledger_for_date(
            state3_pending,
            draw_date="2026-11-03",
            actual_prizes_last2=prizes_0hits,
            ledger_path=ledger_file,
            updated_at="2026-11-03T16:40:00+07:00",
        )
        assert state3_settled.current_bankroll_vnd == 1_028_500
        assert state3_settled.house_money_surplus_vnd == 28_500
        assert state3_settled.win_days == 2
        assert state3_settled.loss_days == 1
        assert state3_settled.total_cost_vnd == 270_000
        assert state3_settled.total_revenue_vnd == 298_500
        assert state3_settled.net_profit_vnd == 28_500

        reloaded = load_benchmark_ledger(ledger_file)
        assert verify_ledger_integrity(reloaded).sha256 == state3_settled.sha256

    def test_bc08_load_historical_benchmark_ledger_compatibility(self) -> None:
        state = load_benchmark_ledger(DEFAULT_LEDGER_PATH)
        assert state.total_tracked_days >= 300
        assert state.starting_bankroll_vnd == 1_000_000
        assert state.current_bankroll_vnd == 5_911_500
        assert state.house_money_surplus_vnd == 4_911_500
        assert len(state.sha256) == 64
        assert all(e.settlement_status == "SETTLED" for e in state.entries)


# ===========================================================================
# Layer 4 (Task 4): Weekly 5/2 Cage-Balance Filter & Cage Anomaly Sentinel
# ===========================================================================


class TestStage4Weekly52FilterAndCageAnomalySentinel:
    """Verify Task 4: detect_cage_anomaly, compute_weekly_balance_rest_days, XSBT #1 & 5/2."""

    def test_detect_cage_anomaly_sentinel_and_bc05_boundaries(self) -> None:
        from xsmn_alpha.live.daily_analyst import detect_cage_anomaly

        # Create a 30-draw counts matrix where Tens ball 4 is cold (10 hits / 540 = 1.85% <= 6.5%)
        # and Units ball 6 is cold (15 hits / 540 = 2.78% <= 6.5%)
        tens_row = [2, 2, 2, 2, 0, 2, 2, 2, 2, 2]  # sum = 18, ball 4 has 0 hits
        units_row = [2, 2, 2, 2, 2, 2, 0, 2, 2, 2]  # sum = 18, ball 6 has 0 hits
        tens_mat = [tens_row for _ in range(30)]
        units_mat = [units_row for _ in range(30)]
        ranked_t = [7, 0, 2, 9, 1, 6, 5, 3, 8, 4]
        ranked_u = [5, 4, 3, 8, 7, 9, 0, 1, 2, 6]

        detected, cold_t, cold_u, summary_vi = detect_cage_anomaly(
            station_code="XSBT",
            station_name="Bến Tre",
            chi2_max_overall=50.35,
            null_chi2_p95=19.34,
            bf10_max_overall=1.82e7,
            tens_counts=tens_mat,
            units_counts=units_mat,
            ranked_balls_tens=ranked_t,
            ranked_balls_units=ranked_u,
        )
        assert detected is True
        assert cold_t == [4]
        assert cold_u == [6]
        assert "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in summary_vi
        assert "Bến Tre (XSBT)" in summary_vi
        assert "50.35" in summary_vi
        assert "19.34" in summary_vi
        assert "[4]" in summary_vi
        assert "[6]" in summary_vi
        assert "7, 0" in summary_vi
        assert "5, 4" in summary_vi

        # BC-05 Boundary 1: chi2_max_overall == null_chi2_p95 -> False
        det_b1, ct_b1, cu_b1, sum_b1 = detect_cage_anomaly(
            station_code="XSBT",
            station_name="Bến Tre",
            chi2_max_overall=19.34,
            null_chi2_p95=19.34,
            bf10_max_overall=25.0,
            tens_counts=tens_mat,
            units_counts=units_mat,
        )
        assert det_b1 is False
        assert ct_b1 == []
        assert cu_b1 == []
        assert sum_b1 == ""

        # BC-05 Boundary 2: bf10_max_overall == 9.999 < 10.0 -> False
        det_b2, ct_b2, cu_b2, sum_b2 = detect_cage_anomaly(
            station_code="XSBT",
            station_name="Bến Tre",
            chi2_max_overall=35.0,
            null_chi2_p95=19.34,
            bf10_max_overall=9.999,
            tens_counts=tens_mat,
            units_counts=units_mat,
        )
        assert det_b2 is False
        assert ct_b2 == []
        assert cu_b2 == []
        assert sum_b2 == ""

    def test_compute_weekly_balance_rest_days_real_data_and_pre_draw_cutoff_gate(self) -> None:
        from xsmn_alpha.exceptions import TemporalLeakageError
        from xsmn_alpha.live.daily_analyst import compute_weekly_balance_rest_days
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR, load_station_raw_cache

        # 1. At 2026-10-19 (start of week Oct 19..25):
        # Wednesday (weekday=2, Max Chi2 = 13.22) is Rank #1 and Monday (0, Max Chi2 = 15.07)
        # is Rank #2 -> rest_weekdays == (2, 0), Tuesday (1, Max Chi2 = 50.35, XSBT) is Rank #7
        sched_oct19 = compute_weekly_balance_rest_days("2026-10-19", raw_dir=DEFAULT_RAW_ALL_DIR)
        assert sched_oct19.rest_weekdays == (2, 0)
        assert sched_oct19.rest_weekdays_vn == ("Thứ 4", "Thứ 2")
        assert sched_oct19.weekday_rankings[0].weekday == 2
        assert sched_oct19.weekday_rankings[0].max_chi2_overall == pytest.approx(13.22, abs=0.01)
        assert sched_oct19.weekday_rankings[1].weekday == 0
        assert sched_oct19.weekday_rankings[1].max_chi2_overall == pytest.approx(15.07, abs=0.01)
        assert sched_oct19.weekday_rankings[6].weekday == 1
        assert sched_oct19.weekday_rankings[6].lead_station_code == "XSBT"
        assert sched_oct19.weekday_rankings[6].max_chi2_overall == pytest.approx(50.35, abs=0.01)
        assert sched_oct19.is_today_scheduled_rest_day is True

        # 2. At 2026-10-26 (Monday): rest_weekdays == (2, 0), is_today_scheduled_rest_day is True
        sched_oct26 = compute_weekly_balance_rest_days("2026-10-26", raw_dir=DEFAULT_RAW_ALL_DIR)
        assert sched_oct26.rest_weekdays == (2, 0)
        assert sched_oct26.is_today_scheduled_rest_day is True
        assert sched_oct26.today_balance_rank == 2

        # 3. At 2026-10-27 (Tuesday) and 2026-10-28 (Wednesday):
        # Monday (0) and Wednesday (2) are the 2 rest days; Tuesday (1) is Rank #7 play day (XSBT)
        sched_oct27 = compute_weekly_balance_rest_days("2026-10-27", raw_dir=DEFAULT_RAW_ALL_DIR)
        assert set(sched_oct27.rest_weekdays) == {0, 2}
        assert set(sched_oct27.play_weekdays) == {1, 3, 4, 5, 6}
        assert sched_oct27.target_weekday == 1
        assert sched_oct27.today_balance_rank == 7
        assert sched_oct27.is_today_scheduled_rest_day is False
        assert sched_oct27.weekday_rankings[6].weekday == 1
        assert sched_oct27.weekday_rankings[6].lead_station_code == "XSBT"

        sched_oct28 = compute_weekly_balance_rest_days("2026-10-28", raw_dir=DEFAULT_RAW_ALL_DIR)
        assert set(sched_oct28.rest_weekdays) == {0, 2}
        assert sched_oct28.target_weekday == 2
        assert sched_oct28.is_today_scheduled_rest_day is True

        # 4. Negative Mutation (Gate 2 PreDrawCutoffGate):
        # Injecting draw_date >= target_date into ANY station raises TemporalLeakageError!
        raw_xsbt = load_station_raw_cache("XSBT", raw_dir=DEFAULT_RAW_ALL_DIR)
        leaked_xsbt = [
            *raw_xsbt,
            {
                "station_code": "XSBT",
                "draw_date": "2026-10-27",
                "prizes_last2": raw_xsbt[-1]["prizes_last2"],
            },
        ]
        with pytest.raises(TemporalLeakageError):
            compute_weekly_balance_rest_days(
                "2026-10-27",
                raw_dir=DEFAULT_RAW_ALL_DIR,
                station_histories={"XSBT": leaked_xsbt},
            )

    def test_tuesday_xsbt_ranked_number_1_excludes_cold_4x_and_locks_1x(self) -> None:
        from xsmn_alpha.live.daily_analyst import (
            generate_daily_quant_report,
            rank_stations_for_day,
            score_station_for_date,
        )
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR

        # Check XSBT at both 2026-10-20 (chi2_max = 50.35) and 2026-10-27 (chi2_max = 51.20)
        sc_oct20 = score_station_for_date(
            "XSBT", target_date="2026-10-20", raw_dir=DEFAULT_RAW_ALL_DIR, null_sims=200
        )
        assert sc_oct20.chi2_max_overall == pytest.approx(50.35, abs=0.01)
        assert sc_oct20.cage_anomaly_detected is True
        assert 4 in sc_oct20.cold_balls_tens
        assert all(
            not num.startswith("4") for num in sc_oct20.ticket_configs["2x2"].selected_numbers
        )
        assert all(not num.startswith("4") for num in sc_oct20.sweet_5_numbers)

        # Full Tuesday 2026-10-27 evaluation across all 5 Tuesday stations
        tuesday_codes = get_station_codes_for_weekday(1)
        tue_cards = [
            score_station_for_date(
                c, target_date="2026-10-27", raw_dir=DEFAULT_RAW_ALL_DIR, null_sims=200
            )
            for c in tuesday_codes
        ]
        ranked, primary, _sec, _skip, tier = rank_stations_for_day(
            tue_cards, is_weekly_rest_day=False
        )
        assert primary.station_code == "XSBT"
        assert ranked[0].station_code == "XSBT"
        assert primary.cage_anomaly_detected is True
        assert primary.chi2_max_overall > primary.null_chi2_p95
        assert primary.bf10_max_overall >= CAGE_ANOMALY_BF10_THRESHOLD
        assert 4 in primary.cold_balls_tens
        assert len(primary.sweet_5_numbers) == 5
        assert primary.sweet_5_config is not None
        assert set(primary.ticket_configs["2x2"].selected_numbers).issubset(
            set(primary.sweet_5_numbers)
        )
        assert all(
            not num.startswith("4") for num in primary.ticket_configs["2x2"].selected_numbers
        )
        assert all(not num.startswith("4") for num in primary.sweet_5_numbers)
        assert tier == "PLAY_STANDARD"

        # Full DailyQuantReportContract on Tuesday 2026-10-27
        report_tue = generate_daily_quant_report(
            "2026-10-27",
            raw_dir=DEFAULT_RAW_ALL_DIR,
            null_sims=200,
        )
        assert report_tue.verdict_tier == "PLAY_STANDARD"
        assert report_tue.should_play_today is True
        assert report_tue.primary_station.station_code == "XSBT"
        assert report_tue.primary_station.cage_anomaly_detected is True
        assert report_tue.primary_station.passes_weekly_5_2_play is True
        assert 4 in report_tue.primary_station.cold_balls_tens
        assert all(not n.startswith("4") for n in report_tue.primary_station.sweet_5_numbers)
        assert report_tue.capital_guidance.recommended_multiplier == pytest.approx(1.0)
        assert report_tue.weekly_5_2_schedule is not None
        assert report_tue.weekly_5_2_schedule.is_today_scheduled_rest_day is False
        assert "PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in report_tue.executive_nlg_vi.q1_should_play_and_why
        assert "sweet_5" in report_tue.executive_nlg_vi.q3_which_numbers_and_config

    def test_monday_and_wednesday_scheduled_rest_days_lock_skip_0x(self) -> None:
        from xsmn_alpha.live.daily_analyst import generate_daily_quant_report
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR

        for rest_date in ("2026-10-26", "2026-10-28"):
            rep = generate_daily_quant_report(
                rest_date,
                raw_dir=DEFAULT_RAW_ALL_DIR,
                null_sims=200,
            )
            assert rep.verdict_tier == "SKIP_NO_EDGE"
            assert rep.should_play_today is False
            assert rep.capital_guidance.recommended_multiplier == pytest.approx(0.0)
            assert rep.capital_guidance.benchmark_bet_vnd == 0
            assert rep.weekly_5_2_schedule is not None
            assert rep.weekly_5_2_schedule.is_today_scheduled_rest_day is True
            assert "5/2" in rep.executive_nlg_vi.q1_should_play_and_why

    def test_bc03_auto_weekly_52_mode_fallback_on_partial_tmp_path(self, tmp_path: Path) -> None:
        import datetime

        from xsmn_alpha.live.daily_analyst import generate_daily_quant_report
        from xsmn_alpha.live.multi_fetcher import save_station_raw_cache

        base_dt = datetime.date(2026, 10, 24)
        raw_dir = tmp_path / "partial_raw_5"
        for code in get_station_codes_for_weekday(0):
            draws = []
            for idx in range(65):
                draw_dt = base_dt - datetime.timedelta(days=(64 - idx) * 7)
                prizes = (
                    ["28"] * 6
                    + ["29", "38"]
                    + [f"{(idx + k) % 10}{(idx * 3 + k * 7) % 10}" for k in range(10)]
                )
                draws.append(
                    {
                        "station_code": code,
                        "draw_date": draw_dt.isoformat(),
                        "prizes_last2": prizes,
                    }
                )
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        # In auto mode with only 5 stations (< 35), falls back to single-day evaluation
        rep = generate_daily_quant_report("2026-10-26", raw_dir=raw_dir, null_sims=50)
        assert rep.weekly_5_2_schedule is None
        assert rep.should_play_today is True


# ===========================================================================
# Layer 5 (Task 5): 05:00 AM Telegram Briefing — Dual Sweet-Spot, 5/2 & 1.0x
# ===========================================================================


class TestStage4TelegramMorningBriefingTask5:
    """Verify Task 5 Telegram 05:00 AM briefing: 5/2 status, Dual Sweet-Spot & 1.0x frame."""

    def test_telegram_play_day_displays_5_2_schedule_dual_sweet_spot_1x_frame_and_anomaly(
        self,
    ) -> None:
        from xsmn_alpha.live.daily_analyst import generate_daily_quant_report
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR
        from xsmn_alpha.live.telegram_bot import (
            TELEGRAM_MAX_MESSAGE_LENGTH,
            format_telegram_executive_briefing,
            format_telegram_morning_briefing,
        )

        report_play = generate_daily_quant_report(
            "2026-10-27",
            raw_dir=DEFAULT_RAW_ALL_DIR,
            null_sims=100,
        )
        msg = format_telegram_morning_briefing(
            report_play,
            public_report_base_url="https://xstk-family.pages.dev",
        )
        assert msg == format_telegram_executive_briefing(
            report_play,
            public_report_base_url="https://xstk-family.pages.dev",
        )
        assert report_play.telegram_message_html == msg

        # BC-09: UTF-8 byte length <= 4096
        assert len(msg) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert len(msg.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH

        # 1. Lịch Chơi 5/2 status on play day
        assert "Lịch Chơi 5/2" in msg
        assert "1.0x" in msg
        assert "Thứ 3" in msg
        assert "Thứ 4" in msg and "Thứ 2" in msg

        # 2. Cage Anomaly Sentinel alert when cage_anomaly_detected == True
        assert report_play.primary_station.cage_anomaly_detected is True
        assert "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in msg
        assert "XSBT" in msg
        assert "Bến Tre" in msg

        # 3. Dual Sweet-Spot configs: sweet_5 (5 nums, 60.28%, 90k) & 2x2 (4 nums, 52.04%, 72k)
        assert "sweet_5" in msg
        assert "60.28%" in msg
        assert "90k" in msg
        assert "+9.5k" in msg
        assert "+109k" in msg
        for n5 in report_play.primary_station.sweet_5_numbers:
            assert n5 in msg

        assert "2x2" in msg
        assert "52.04%" in msg
        assert "72k" in msg
        assert "+27.5k" in msg
        assert "+127k" in msg
        for n4 in report_play.primary_station.ticket_configs["2x2"].selected_numbers:
            assert n4 in msg

        # 4. Reminder frame: 🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x (Tuyệt đối không gấp thếp)
        assert "🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x" in msg
        assert "không gấp thếp" in msg.lower()

        # 5. Web Report URL link at the bottom
        expected_url = "https://xstk-family.pages.dev/daily/2026-10-27.html"
        assert f'<a href="{expected_url}">' in msg
        assert msg.rfind(expected_url) > msg.find("🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x")

        # Also verify extended audit mode stays <= 4096 UTF-8 bytes
        msg_ext = format_telegram_executive_briefing(
            report_play,
            public_report_base_url="https://xstk-family.pages.dev",
            include_extended_audit=True,
        )
        assert len(msg_ext.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH

    def test_telegram_scheduled_rest_day_explains_balanced_cage_rest_reason_and_bc09(
        self,
    ) -> None:
        from xsmn_alpha.live.daily_analyst import generate_daily_quant_report
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR
        from xsmn_alpha.live.telegram_bot import (
            TELEGRAM_MAX_MESSAGE_LENGTH,
            format_telegram_executive_briefing,
        )

        report_rest = generate_daily_quant_report(
            "2026-10-26",
            raw_dir=DEFAULT_RAW_ALL_DIR,
            null_sims=100,
        )
        assert report_rest.verdict_tier == "SKIP_NO_EDGE"
        assert report_rest.should_play_today is False
        assert report_rest.capital_guidance.recommended_multiplier == pytest.approx(0.0)
        assert report_rest.weekly_5_2_schedule is not None
        assert report_rest.weekly_5_2_schedule.is_today_scheduled_rest_day is True

        msg_rest = format_telegram_executive_briefing(
            report_rest,
            public_report_base_url="https://xstk-family.pages.dev",
        )
        assert len(msg_rest) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert len(msg_rest.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH

        # Must clearly explain the scheduled rest reason (2 most balanced cage weekdays in the week)
        assert "SKIP_NO_EDGE" in msg_rest
        assert "0.0x" in msg_rest
        assert "Lịch Chơi 5/2" in msg_rest
        assert "2 ngày" in msg_rest.lower()
        assert "cân bằng nhất tuần" in msg_rest.lower()
        assert "bảo toàn" in msg_rest.lower()
        assert "🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x" in msg_rest
        assert "https://xstk-family.pages.dev/daily/2026-10-26.html" in msg_rest

    def test_telegram_bc10_xss_injection_in_anomaly_and_executive_summary_escaped(
        self,
    ) -> None:
        from xsmn_alpha.live.telegram_bot import format_telegram_executive_briefing

        sched = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        sc_primary = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=True,
            cage_anomaly_detected=True,
        )
        xss_payload = '<script>alert(1)</script><img src=x onerror="alert(2)">'
        sc_mutated = sc_primary.model_copy(
            update={
                "cage_anomaly_summary_vi": f"⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH: {xss_payload}",
            }
        )
        cap_1x = CapitalGuidanceContract(
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            recommended_multiplier=1.0,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=72_000,
            stake_per_number_vnd=18_000,
            payout_per_hit_vnd=99_500,
            sample_allocations=_make_sample_allocations(1.0),
            sizing_rationale_vi=f"Khóa 1.0x {xss_payload}",
        )
        nlg_mutated = ExecutiveNLGContract(
            yesterday_settlement_summary_vi=f"Yesterday {xss_payload}",
            q1_should_play_and_why=f"Q1 {xss_payload}",
            q2_which_station_and_region=f"Q2 {xss_payload}",
            q3_which_numbers_and_config=f"Q3 {xss_payload}",
            q4_how_to_allocate_capital=f"Q4 {xss_payload}",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-27",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-26",
        )
        report_xss = DailyQuantReportContract(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            generated_at_ict="2026-10-27T05:00:00+07:00",
            data_pipeline_audit=audit,
            yesterday_summary_vi=f"Summary {xss_payload}",
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            primary_station=sc_mutated,
            secondary_station=None,
            skipped_stations=[],
            all_today_stations=[sc_mutated],
            capital_guidance=cap_1x,
            executive_nlg_vi=nlg_mutated,
            weekly_5_2_schedule=sched,
        )

        for ext_flag in (False, True):
            rendered = format_telegram_executive_briefing(
                report_xss,
                include_extended_audit=ext_flag,
            )
            assert "<script>" not in rendered
            assert "<script>alert(1)</script>" not in rendered
            assert '<img src=x onerror="alert(2)">' not in rendered
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


# ===========================================================================
# Layer 6 (Task 6): Stage 4 Static Web Audit Report & E2E CLI daily-report
# ===========================================================================


class TestStage4WebPublisherAndCliEndToEndTask6:
    """Verify Task 6 Web Audit Report (5/2 table, Anomaly Sentinel, sweet_5, 1.0x table) & CLI."""

    def test_web_render_daily_report_html_stage4_sections_and_anomaly_toggle(self) -> None:
        from xsmn_alpha.live.web_publisher import render_daily_report_html

        sched = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        sc_primary = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=True,
            cage_anomaly_detected=True,
            sweet_5_numbers=["21", "22", "23", "31", "32"],
        )
        cap_1x = CapitalGuidanceContract(
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            recommended_multiplier=1.0,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=72_000,
            stake_per_number_vnd=18_000,
            payout_per_hit_vnd=99_500,
            sample_allocations=_make_sample_allocations(1.0),
            sizing_rationale_vi="Khóa cứng 1.0x theo Kỷ Luật Tiền Chợ Đều Tay Lịch 5/2.",
        )
        nlg = ExecutiveNLGContract(
            yesterday_settlement_summary_vi="Hôm qua nghỉ định kỳ Thứ 2 (0.0x).",
            q1_should_play_and_why="CHƠI ĐỀU TAY 1.0x — Thứ 3 thuộc 5 ngày chơi Điểm Ngọt.",
            q2_which_station_and_region="Đài Chủ Lực: Bến Tre (Miền Nam - 16:15).",
            q3_which_numbers_and_config="Bộ 5 số Điểm Ngọt: 21, 22, 23, 31, 32.",
            q4_how_to_allocate_capital="Khóa trần 1.0x đều tay (72k cho 4 số / 90k cho 5 số).",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-27",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-26",
        )
        report = DailyQuantReportContract(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            generated_at_ict="2026-10-27T05:00:00+07:00",
            data_pipeline_audit=audit,
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            primary_station=sc_primary,
            secondary_station=None,
            skipped_stations=[],
            all_today_stations=[sc_primary],
            capital_guidance=cap_1x,
            executive_nlg_vi=nlg,
            weekly_5_2_schedule=sched,
        )

        html_doc = render_daily_report_html(report)

        # 1. Cage Anomaly Sentinel alert box when cage_anomaly_detected == True
        assert 'id="cage-anomaly-sentinel-alert"' in html_doc
        assert "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in html_doc
        assert "Cage Anomaly Sentinel" in html_doc
        assert "[4]" in html_doc and "[6]" in html_doc

        # 2. 7-weekday Weekly 5/2 Cage-Balance Ranking Table
        assert 'id="weekly-5-2-schedule-table"' in html_doc
        assert "Bảng Xếp Hạng Độ Cân Bằng 7 Thứ Trong Tuần" in html_doc
        for wd_row in sched.weekday_rankings:
            assert wd_row.weekday_vn in html_doc
            assert wd_row.lead_station_code in html_doc
            assert f"{wd_row.max_chi2_overall:.2f}" in html_doc
        assert "NGHỈ ĐỊNH KỲ 5/2" in html_doc
        assert "CHƠI ĐIỂM NGỌT 5/2" in html_doc

        # 3. Section 3: sweet_5 row in ticket comparison table & highlight on probability heatmap
        assert "sweet_5" in html_doc
        assert "Bộ 5 số Điểm Ngọt Bà Cô" in html_doc
        assert "60.28%" in html_doc
        assert "90.000" in html_doc
        assert "90,000" in html_doc
        assert "heatmap-sweet5" in html_doc
        # Satellite number "23" (in sweet_5 but not in 2x2) is highlighted on the heatmap
        assert 'heatmap-sweet5-satellite"><div><strong>23' in html_doc

        # 4. Section 4: "Kỷ Luật Tiền Chợ Đều Tay 1.0x" comparison table
        # (2x2 vs sweet_5 at 1.0x & 2.0x)
        assert 'id="flat-1x-grocery-comparison-table"' in html_doc
        assert "Kỷ Luật Tiền Chợ Đều Tay 1.0x" in html_doc
        assert "Tuyệt đối không gấp thếp" in html_doc
        assert "52.04%" in html_doc and "60.28%" in html_doc
        assert "72.000" in html_doc and "90.000" in html_doc
        assert "+27.500" in html_doc and "+9.500" in html_doc
        assert "+127.000" in html_doc and "+109.000" in html_doc
        assert "144.000" in html_doc and "180.000" in html_doc
        assert "+254.000" in html_doc and "+218.000" in html_doc

        # Verify that when cage_anomaly_detected is False and cage_anomaly_summary_vi is empty,
        # the Cage Anomaly Sentinel alert box is NOT rendered
        sc_no_anomaly = sc_primary.model_copy(
            update={
                "cage_anomaly_detected": False,
                "cage_anomaly_summary_vi": "",
                "cold_balls_tens": [],
                "cold_balls_units": [],
            }
        )
        report_no_anomaly = report.model_copy(
            update={
                "primary_station": sc_no_anomaly,
                "all_today_stations": [sc_no_anomaly],
            }
        )
        html_no_anomaly = render_daily_report_html(report_no_anomaly)
        assert 'id="cage-anomaly-sentinel-alert"' not in html_no_anomaly

    def test_web_bc10_xss_injection_in_anomaly_and_weekly_52_schedule_escaped(self) -> None:
        from xsmn_alpha.live.web_publisher import render_daily_report_html

        xss_payload = '<script>alert(1)</script><img src=x onerror="alert(2)">'
        sched_base = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        mut_rankings = list(sched_base.weekday_rankings)
        mut_rankings[6] = mut_rankings[6].model_copy(
            update={"lead_station_name": f"Bến Tre {xss_payload}"}
        )
        sched_xss = sched_base.model_copy(
            update={
                "schedule_summary_vi": f"Lịch 5/2 {xss_payload}",
                "weekday_rankings": mut_rankings,
            }
        )
        sc_xss = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=True,
            cage_anomaly_detected=True,
        ).model_copy(
            update={
                "cage_anomaly_summary_vi": f"⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH: {xss_payload}",
            }
        )
        cap_1x = CapitalGuidanceContract(
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            recommended_multiplier=1.0,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=72_000,
            stake_per_number_vnd=18_000,
            payout_per_hit_vnd=99_500,
            sample_allocations=_make_sample_allocations(1.0),
            sizing_rationale_vi="Khóa 1.0x.",
        )
        nlg = ExecutiveNLGContract(
            yesterday_settlement_summary_vi="Hôm qua nghỉ.",
            q1_should_play_and_why="Chơi 1.0x.",
            q2_which_station_and_region="Bến Tre.",
            q3_which_numbers_and_config="Bộ 5 số.",
            q4_how_to_allocate_capital="Đều tay 1.0x.",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-27",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-26",
        )
        report_xss = DailyQuantReportContract(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            generated_at_ict="2026-10-27T05:00:00+07:00",
            data_pipeline_audit=audit,
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            primary_station=sc_xss,
            secondary_station=None,
            skipped_stations=[],
            all_today_stations=[sc_xss],
            capital_guidance=cap_1x,
            executive_nlg_vi=nlg,
            weekly_5_2_schedule=sched_xss,
        )

        html_doc = render_daily_report_html(report_xss)
        assert "<script>alert(1)</script>" not in html_doc
        assert '<img src=x onerror="alert(2)">' not in html_doc
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_doc
        assert "Lịch 5/2 &lt;script&gt;alert(1)&lt;/script&gt;" in html_doc

    def test_cli_daily_report_dry_run_rest_day_and_anomaly_play_day_e2e(
        self, tmp_path: Path
    ) -> None:
        import shutil

        from xsmn_alpha.cli import main
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR

        ledger_copy = tmp_path / "benchmark_ledger.json"
        shutil.copy2(DEFAULT_LEDGER_PATH, ledger_copy)
        public_dir = tmp_path / "public"
        preview_26 = tmp_path / "preview_2026_10_26.txt"
        preview_27 = tmp_path / "preview_2026_10_27.txt"

        # 1. Run CLI daily-report --dry-run for scheduled rest day 2026-10-26 (Monday -> 0.0x)
        rc_26 = main(
            [
                "daily-report",
                "--date",
                "2026-10-26",
                "--raw-dir",
                str(DEFAULT_RAW_ALL_DIR),
                "--ledger",
                str(ledger_copy),
                "--public-dir",
                str(public_dir),
                "--preview-path",
                str(preview_26),
                "--null-sims",
                "100",
                "--send-telegram",
                "--dry-run",
            ]
        )
        assert rc_26 == 0
        html_26_path = public_dir / "daily" / "2026-10-26.html"
        json_26_path = public_dir / "daily" / "2026-10-26.json"
        assert html_26_path.exists()
        assert json_26_path.exists()
        assert preview_26.exists()

        rep_26 = DailyQuantReportContract.model_validate_json(
            json_26_path.read_text(encoding="utf-8")
        )
        assert rep_26.verdict_tier == "SKIP_NO_EDGE"
        assert rep_26.should_play_today is False
        assert rep_26.capital_guidance.recommended_multiplier == pytest.approx(0.0)
        assert rep_26.weekly_5_2_schedule is not None
        assert rep_26.weekly_5_2_schedule.is_today_scheduled_rest_day is True
        html_26 = html_26_path.read_text(encoding="utf-8")
        assert 'id="weekly-5-2-schedule-table"' in html_26
        assert "NGHỈ ĐỊNH KỲ 5/2" in html_26
        assert "sweet_5" in html_26
        assert "Kỷ Luật Tiền Chợ Đều Tay 1.0x" in html_26

        # 2. Run CLI daily-report --dry-run for anomaly play day 2026-10-27 (Tuesday -> XSBT 1.0x)
        rc_27 = main(
            [
                "daily-report",
                "--date",
                "2026-10-27",
                "--raw-dir",
                str(DEFAULT_RAW_ALL_DIR),
                "--ledger",
                str(ledger_copy),
                "--public-dir",
                str(public_dir),
                "--preview-path",
                str(preview_27),
                "--null-sims",
                "100",
                "--send-telegram",
                "--dry-run",
            ]
        )
        assert rc_27 == 0
        html_27_path = public_dir / "daily" / "2026-10-27.html"
        json_27_path = public_dir / "daily" / "2026-10-27.json"
        index_path = public_dir / "index.html"
        assert html_27_path.exists()
        assert json_27_path.exists()
        assert index_path.exists()
        assert preview_27.exists()

        rep_27 = DailyQuantReportContract.model_validate_json(
            json_27_path.read_text(encoding="utf-8")
        )
        assert rep_27.verdict_tier == "PLAY_STANDARD"
        assert rep_27.should_play_today is True
        assert rep_27.primary_station.station_code == "XSBT"
        assert rep_27.primary_station.cage_anomaly_detected is True
        assert rep_27.capital_guidance.recommended_multiplier == pytest.approx(1.0)
        assert rep_27.weekly_5_2_schedule is not None
        assert rep_27.weekly_5_2_schedule.is_today_scheduled_rest_day is False

        html_27 = html_27_path.read_text(encoding="utf-8")
        assert 'id="cage-anomaly-sentinel-alert"' in html_27
        assert "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in html_27
        assert 'id="weekly-5-2-schedule-table"' in html_27
        assert "Bộ 5 số Điểm Ngọt Bà Cô" in html_27
        assert "60.28%" in html_27
        assert "90.000" in html_27
        assert 'id="flat-1x-grocery-comparison-table"' in html_27
        assert "Kỷ Luật Tiền Chợ Đều Tay 1.0x" in html_27

        tg_preview_27 = preview_27.read_text(encoding="utf-8")
        assert len(tg_preview_27.encode("utf-8")) <= 4096
        assert "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH" in tg_preview_27
        assert "sweet_5" in tg_preview_27
        assert "🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x" in tg_preview_27


# ===========================================================================
# Layer 7 (Step 4 Reconcile): Doubt-Driven Adversarial Probe Regression Suite
# ===========================================================================


class TestStage4AdversarialReconcileSuite:
    """Regression suite for Doubt-Driven findings F-01..F-04, F-08..F-10, F-13 (P-01..P-15)."""

    def test_f01_daily_report_weekly_52_rest_and_play_contradictions_rejected(self) -> None:
        # P-01: Scheduled rest day (Monday=0) with PLAY_STANDARD / 1.0x -> DataIntegrityError
        sched_mon_rest = _make_valid_weekly_52_schedule("2026-10-26", target_weekday=0)
        sc_mon = _make_stage4_scorecard(
            "XSHCM",
            "TP. Hồ Chí Minh",
            last_draw_date="2026-10-24",
            passes_alpha=True,
            passes_weekly_5_2_play=False,
        )
        cap_1x = build_capital_guidance(
            "PLAY_STANDARD", current_bankroll_vnd=1_200_000, lock_flat_1x=True
        )
        nlg = ExecutiveNLGContract(
            yesterday_settlement_summary_vi="Ok",
            q1_should_play_and_why="Ok",
            q2_which_station_and_region="Ok",
            q3_which_numbers_and_config="Ok",
            q4_how_to_allocate_capital="Ok",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-26",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-25",
        )
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-26",
                weekday_vn="Thứ 2",
                generated_at_ict="2026-10-26T05:00:00+07:00",
                data_pipeline_audit=audit,
                verdict_tier="PLAY_STANDARD",
                should_play_today=True,
                primary_station=sc_mon,
                all_today_stations=[sc_mon],
                capital_guidance=cap_1x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=sched_mon_rest,
            )

        # P-02: Play day (Tuesday=1) with SKIP_NO_EDGE / 0.0x under 5/2 -> DataIntegrityError
        sched_tue_play = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        sc_tue = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=True,
        )
        cap_0x = build_capital_guidance(
            "SKIP_NO_EDGE", current_bankroll_vnd=1_200_000, lock_flat_1x=True
        )
        audit_tue = audit.model_copy(update={"target_date": "2026-10-27"})
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-27",
                weekday_vn="Thứ 3",
                generated_at_ict="2026-10-27T05:00:00+07:00",
                data_pipeline_audit=audit_tue,
                verdict_tier="SKIP_NO_EDGE",
                should_play_today=False,
                primary_station=sc_tue,
                all_today_stations=[sc_tue],
                capital_guidance=cap_0x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=sched_tue_play,
            )

        # P-03: Report date vs weekly_5_2_schedule.as_of_date mismatch -> DataIntegrityError
        sched_wrong_date = _make_valid_weekly_52_schedule("2026-10-20", target_weekday=1)
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-27",
                weekday_vn="Thứ 3",
                generated_at_ict="2026-10-27T05:00:00+07:00",
                data_pipeline_audit=audit_tue,
                verdict_tier="PLAY_STANDARD",
                should_play_today=True,
                primary_station=sc_tue,
                all_today_stations=[sc_tue],
                capital_guidance=cap_1x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=sched_wrong_date,
            )

        # B-03 & B-04: passes_weekly_5_2_play=True when schedule is None -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-27",
                weekday_vn="Thứ 3",
                generated_at_ict="2026-10-27T05:00:00+07:00",
                data_pipeline_audit=audit_tue,
                verdict_tier="PLAY_STANDARD",
                should_play_today=True,
                primary_station=sc_tue,
                all_today_stations=[sc_tue],
                capital_guidance=cap_1x,
                executive_nlg_vi=nlg,
                weekly_5_2_schedule=None,
            )

    def test_f02_weekly_52_schedule_tie_break_and_date_weekday_invariants(self) -> None:
        # P-04: as_of_date ("2026-10-26" Mon=0) mismatched with target_weekday=1 -> Error
        sched = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        bad_date_wd = sched.model_dump()
        bad_date_wd["as_of_date"] = "2026-10-26"
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_date_wd)

        # P-05: Tie on max_chi2_overall where rank 1 has higher max_bf10_overall than rank 2
        bad_tie_bf10 = sched.model_dump()
        bad_tie_bf10["weekday_rankings"][0]["max_chi2_overall"] = 15.00
        bad_tie_bf10["weekday_rankings"][0]["max_bf10_overall"] = 0.90
        bad_tie_bf10["weekday_rankings"][1]["max_chi2_overall"] = 15.00
        bad_tie_bf10["weekday_rankings"][1]["max_bf10_overall"] = 0.40
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_tie_bf10)

        # B-10: mean_chi2_overall > max_chi2_overall -> DataIntegrityError
        bad_mean_gt_max = sched.model_dump()
        bad_mean_gt_max["weekday_rankings"][0]["mean_chi2_overall"] = 19.0
        with pytest.raises(DataIntegrityError):
            WeeklySchedule52Analysis.model_validate(bad_mean_gt_max)

    def test_f03_f04_f13_sweet_spot_sim_precision_core_order_and_win_rate(self) -> None:
        # P-13 (F-03): Satellite probability difference 2e-13 <= 1e-12 triggers Top-3x3 tie-break
        pt = [0.20, 0.16, 0.100000000003, 0.09, 0.08, 0.08, 0.08, 0.07, 0.07, 0.069999999997]
        pu = [0.20, 0.15, 0.100000000002, 0.09, 0.08, 0.08, 0.08, 0.08, 0.07, 0.069999999998]
        sel, core, sat = select_sweet_5_numbers(pt, pu)
        assert core == ["00", "01", "10", "11"]
        assert sat == ["02"]  # Top-3x3 "02" ties with "20" within 1e-12 -> lexicographic "02"

        # P-14 (F-04): select_sweet_spot_numbers("core_2x2_sat_3x3") places 4 core numbers first
        pt_c = [0.05, 0.05, 0.14, 0.20, 0.18, 0.08, 0.08, 0.08, 0.07, 0.07]
        pu_c = [0.05, 0.13, 0.22, 0.17, 0.08, 0.08, 0.07, 0.07, 0.07, 0.06]
        nums_9 = select_sweet_spot_numbers(pt_c, pu_c, "core_2x2_sat_3x3")
        nums_2x2 = select_sweet_spot_numbers(pt_c, pu_c, "2x2")
        assert nums_9[:4] == nums_2x2

        # F-13 (C-03): evaluate_sweet_spot_portfolio("sweet_5") counts 1-hit draws as wins
        p_u = [0.10] * 10  # sweet_5 = ["00", "01", "02", "10", "11"]
        prizes_1hit = ["02", *(["99"] * 17)]
        metrics_1hit = evaluate_sweet_spot_portfolio([p_u], [p_u], [prizes_1hit], "sweet_5")
        assert metrics_1hit.daily_win_rate == pytest.approx(1.0)
        assert metrics_1hit.multi_hit_rate_ge2 == pytest.approx(0.0)
        assert metrics_1hit.zero_hit_rate_k0 == pytest.approx(0.0)

    def test_f08_f09_f10_gate6_sweet_5_and_ledger_hardening(self) -> None:
        # P-06: enforce_sweet_5 with non-2x2 core (3 distinct tens digits) -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            Weekly52AndFlatStakeGate.enforce_sweet_5(
                ["00", "10", "20", "30", "40"],
                ["00", "10", "20", "30"],
            )

        # P-07: TicketConfigRecommendation("sweet_5") with non-2x2 core -> DataIntegrityError
        bad_rec = _make_sweet_5_ticket_rec().model_dump()
        bad_rec["core_numbers"] = ["00", "10", "20", "30"]
        bad_rec["satellite_numbers"] = ["40"]
        bad_rec["selected_numbers"] = ["00", "10", "20", "30", "40"]
        with pytest.raises(DataIntegrityError):
            TicketConfigRecommendation.model_validate(bad_rec)

        # P-08: StationDailyScorecard where sweet_5_config disagrees with sweet_5_numbers -> Error
        sc = _make_stage4_scorecard()
        bad_sc = sc.model_dump()
        bad_sc["sweet_5_numbers"] = ["21", "22", "28", "31", "32"]
        with pytest.raises(DataIntegrityError):
            StationDailyScorecard.model_validate(bad_sc)

        # P-09 & P-10: BenchmarkLedgerEntry("sweet_5") without 2x2 subset -> DataIntegrityError
        state0 = initialize_empty_ledger()
        with pytest.raises(DataIntegrityError):
            record_pending_recommendation(
                state0,
                draw_date="2026-10-27",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSBT",
                chosen_config_id="sweet_5",
                selected_numbers=["00", "11", "22", "33", "44"],
                lock_flat_1x=True,
            )

        # P-11: build_capital_guidance with 90k base_daily_cost_vnd infers 5 numbers automatically
        cap_90k = build_capital_guidance(
            "PLAY_STANDARD",
            current_bankroll_vnd=1_000_000,
            base_daily_cost_vnd=BENCHMARK_BASE_DAILY_COST_5NUM_VND,
            lock_flat_1x=True,
        )
        row_1m = next(r for r in cap_90k.sample_allocations if r.capital_tier_vnd == 1_000_000)
        assert row_1m.num_numbers == 5
        assert row_1m.total_daily_cost_vnd == 90_000
        assert row_1m.net_profit_1hit_vnd == SWEET_5_NET_PROFIT_1HIT_VND

        # P-12: SETTLED SKIP_NO_EDGE entry with partial (non-0, non-18) prizes -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-26",
                weekday_vn="Thứ 2",
                settlement_status="SETTLED",
                verdict_tier="SKIP_NO_EDGE",
                chosen_station_code="XSHCM",
                chosen_station_name="TP. Hồ Chí Minh",
                chosen_region="Miền Nam",
                chosen_config_id="sweet_5",
                selected_numbers=["21", "22", "23", "31", "32"],
                recommended_multiplier=0.0,
                bankroll_before_vnd=1_000_000,
                house_money_before_vnd=0,
                cost_vnd=0,
                actual_prizes_last2=["21"],
                hit_count_k=0,
                hit_details=[],
                revenue_vnd=0,
                net_profit_vnd=0,
                bankroll_after_vnd=1_000_000,
                house_money_after_vnd=0,
            )

        # P-15: record_pending_recommendation validates config_id even on already-SETTLED date
        state_settled = settle_ledger_for_date(
            record_pending_recommendation(
                state0,
                draw_date="2026-10-27",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSBT",
                chosen_config_id="sweet_5",
                selected_numbers=["21", "22", "23", "31", "32"],
                lock_flat_1x=True,
            ),
            draw_date="2026-10-27",
            actual_prizes_last2=_valid_18_prizes(),
        )
        with pytest.raises(DataIntegrityError):
            record_pending_recommendation(
                state_settled,
                draw_date="2026-10-27",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSBT",
                chosen_config_id="invalid_cfg",
                selected_numbers=["21", "22", "23", "31", "32"],
                lock_flat_1x=True,
            )

    def test_f05_f06_f07_f11_f12_f14_analyst_web_telegram_and_cli_reconcile(
        self, tmp_path: Path
    ) -> None:
        import unicodedata

        import numpy as np

        from xsmn_alpha.cli import build_parser
        from xsmn_alpha.live.daily_analyst import (
            build_executive_nlg_vi,
            detect_cage_anomaly,
            generate_daily_quant_report,
            rank_stations_for_day,
        )
        from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR, load_station_raw_cache
        from xsmn_alpha.live.telegram_bot import (
            dispatch_telegram_briefing,
            format_telegram_executive_briefing,
        )
        from xsmn_alpha.live.web_publisher import render_daily_report_html

        # 1. F-12 (B-07): detect_cage_anomaly rejects empty, NaN/Inf, negative, or zero-row arrays
        valid_counts = np.full((30, 10), 2.0)
        for bad_arr in (
            np.empty((0, 10)),
            np.ones((30, 9)),
            np.full((30, 10), -1.0),
            np.full((30, 10), np.nan),
            np.zeros((30, 10)),
        ):
            with pytest.raises(DataIntegrityError):
                detect_cage_anomaly(
                    station_code="XSBT",
                    station_name="Bến Tre",
                    chi2_max_overall=40.0,
                    null_chi2_p95=20.0,
                    bf10_max_overall=50.0,
                    tens_counts_window=bad_arr,
                    units_counts_window=valid_counts,
                )

        # 2. F-06 & F-12 (B-02, B-06): rank_stations_for_day locks PLAY_STANDARD on 5/2 play day
        # and ranks physical cage anomaly station #1 ahead of non-anomaly Selective Alpha station
        sc_alpha_no_anom = _make_stage4_scorecard(
            "XSDLK",
            "Đắk Lắk",
            last_draw_date="2026-10-20",
            passes_alpha=True,
            passes_weekly_5_2_play=False,
            cage_anomaly_detected=True,
        ).model_copy(
            update={
                "chi2_w15_max": 12.0,
                "chi2_w30_max": 13.0,
                "chi2_w60_max": 14.0,
                "chi2_max_overall": 14.0,
                "null_chi2_p95": 20.0,
                "bf10_max_overall": 0.5,
                "cage_anomaly_detected": False,
                "cage_anomaly_summary_vi": "",
                "cold_balls_tens": [],
                "cold_balls_units": [],
                "strong_convergence": True,
                "station_alpha_score": 15.0,
            }
        )
        sc_anom = _make_stage4_scorecard(
            "XSBT",
            "Bến Tre",
            last_draw_date="2026-10-20",
            passes_alpha=False,
            passes_weekly_5_2_play=False,
            cage_anomaly_detected=True,
        )
        ranked, prim, _, _, v_tier = rank_stations_for_day(
            [sc_alpha_no_anom, sc_anom],
            is_weekly_rest_day=False,
        )
        assert v_tier == "PLAY_STANDARD"
        assert prim.station_code == "XSBT"
        assert prim.passes_weekly_5_2_play is True
        assert "BÁO NGHỈ / BỎ QUA" not in prim.rationale_vi

        # 3. F-05 & F-11: build_executive_nlg_vi avoids false inequalities & includes sweet_5 & 2x2
        sched_tue = _make_valid_weekly_52_schedule("2026-10-27", target_weekday=1)
        cap_1x = build_capital_guidance(
            "PLAY_STANDARD", current_bankroll_vnd=1_500_000, lock_flat_1x=True
        )
        nlg_tue = build_executive_nlg_vi(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            verdict_tier="PLAY_STANDARD",
            primary_station=prim,
            secondary_station=ranked[1],
            skipped_stations=[],
            all_today_stations=ranked,
            capital_guidance=cap_1x,
            yesterday_settlement=None,
            weekly_5_2_schedule=sched_tue,
        )
        assert "(>= ngưỡng lọc" not in nlg_tue.q1_should_play_and_why
        assert "(> 0%)" not in nlg_tue.q1_should_play_and_why
        assert "sweet_5" in nlg_tue.q3_which_numbers_and_config
        assert "2x2" in nlg_tue.q3_which_numbers_and_config
        assert "90,000" in nlg_tue.q3_which_numbers_and_config

        # 4. F-12 (B-09): Partial in-memory station_histories (<35) with weekly_5_2_mode='auto'
        # must NOT mix disk stations or fabricate a 35-station schedule
        partial_hist = {
            code: [
                d
                for d in load_station_raw_cache(code, raw_dir=DEFAULT_RAW_ALL_DIR)
                if d["draw_date"] < "2026-10-26"
            ]
            for code in ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY")
        }
        rep_partial = generate_daily_quant_report(
            "2026-10-26",
            station_histories=partial_hist,
            null_sims=20,
            weekly_5_2_mode="auto",
        )
        assert rep_partial.weekly_5_2_schedule is None

        # 5. F-07 & F-14: Web HTML filters future ledger entries, avoids duplicate anomaly header,
        # and Telegram sanitizer blocks entity/attribute XSS & normalizes NFC <= 4096 bytes
        audit_tue = DataPipelineAuditRecord(
            target_date="2026-10-27",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-26",
        )
        rep_tue = DailyQuantReportContract(
            report_date="2026-10-27",
            weekday_vn="Thứ 3",
            generated_at_ict="2026-10-27T05:00:00+07:00",
            data_pipeline_audit=audit_tue,
            verdict_tier="PLAY_STANDARD",
            should_play_today=True,
            primary_station=prim,
            secondary_station=ranked[1],
            skipped_stations=[],
            all_today_stations=ranked,
            capital_guidance=cap_1x,
            executive_nlg_vi=nlg_tue,
            weekly_5_2_schedule=sched_tue,
        )
        future_ledger = record_pending_recommendation(
            initialize_empty_ledger(),
            draw_date="2026-10-28",
            verdict_tier="SKIP_NO_EDGE",
            chosen_station_code="XSDN",
            chosen_config_id="2x2",
            selected_numbers=["00", "01", "10", "11"],
            lock_flat_1x=True,
        )
        html_tue = render_daily_report_html(rep_tue, future_ledger)
        assert "2026-10-28" not in html_tue
        assert "1.25x – 1.50x" not in html_tue
        assert html_tue.count("PHÁT HIỆN LỒNG CẦU LỆCH MẠNH (Cage Anomaly Sentinel):") == 1

        nfd_anom = unicodedata.normalize(
            "NFD",
            "⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH: " + ("Phân tích cầu lệch hàng chục " * 25),
        )
        prim_nfd = prim.model_copy(update={"cage_anomaly_summary_vi": nfd_anom})
        rep_nfd = rep_tue.model_copy(
            update={"primary_station": prim_nfd, "all_today_stations": [prim_nfd, ranked[1]]}
        )
        tg_msg = format_telegram_executive_briefing(rep_nfd)
        assert unicodedata.is_normalized("NFC", tg_msg)
        assert len(tg_msg.encode("utf-8")) <= 4096

        tg_ext_play = format_telegram_executive_briefing(rep_nfd, include_extended_audit=True)
        assert unicodedata.is_normalized("NFC", tg_ext_play)
        assert len(tg_ext_play.encode("utf-8")) <= 4096

        sched_mon = _make_valid_weekly_52_schedule("2026-10-26", target_weekday=0)
        cap_0x = build_capital_guidance(
            "SKIP_NO_EDGE", current_bankroll_vnd=1_500_000, lock_flat_1x=True
        )
        prim_rest = prim.model_copy(
            update={"passes_weekly_5_2_play": False, "passes_selective_alpha": False}
        )
        sec_rest = ranked[1].model_copy(
            update={"passes_weekly_5_2_play": False, "passes_selective_alpha": False}
        )
        rep_rest = rep_tue.model_copy(
            update={
                "report_date": "2026-10-26",
                "weekday_vn": "Thứ 2",
                "verdict_tier": "SKIP_NO_EDGE",
                "should_play_today": False,
                "primary_station": prim_rest,
                "secondary_station": None,
                "skipped_stations": [prim_rest, sec_rest],
                "all_today_stations": [prim_rest, sec_rest],
                "capital_guidance": cap_0x,
                "weekly_5_2_schedule": sched_mon,
                "yesterday_summary_vi": "Đối soát kỳ hôm qua: " + ("Chuỗi giải trình dài " * 15),
            }
        )
        tg_ext_rest = format_telegram_executive_briefing(rep_rest, include_extended_audit=True)
        assert len(tg_ext_rest.encode("utf-8")) <= 4096

        for xss_html in (
            '<b>Alert</b> <a href="&#106;avascript:alert(1)">Click</a>',
            '<b>Alert</b> <a href="  javascript:alert(1)">Click</a>',
            '<b>Alert</b> <b onmouseover="alert(1)">Hover</b>',
            '<b>Alert</b> <a href="data:text/html,<script>alert(1)</script>">Click</a>',
        ):
            with pytest.raises(DataIntegrityError):
                dispatch_telegram_briefing(
                    xss_html, dry_run=True, preview_path=tmp_path / "xss.txt"
                )

        # 6. F-11 (C-07): CLI parser exposes --weekly-5-2-mode and --ticket-config / --ledger-config
        parser = build_parser()
        parsed_cli = parser.parse_args(
            [
                "daily-report",
                "--date",
                "2026-10-27",
                "--weekly-5-2-mode",
                "enforce",
                "--ticket-config",
                "sweet_5",
            ]
        )
        assert parsed_cli.weekly_5_2_mode == "enforce"
        assert parsed_cli.ticket_config == "sweet_5"
