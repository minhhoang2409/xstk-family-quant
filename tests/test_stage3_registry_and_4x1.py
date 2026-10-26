"""Stage 3 TDD Suite (Tasks 1, 2 & 3): 35-Station Registry, 4x1 Config, Schemas & Multi-Fetcher."""

from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from xsmn_alpha.backtest.sweet_spot_sim import (
    compute_portfolio_set_probability,
    evaluate_all_sweet_spot_portfolios,
    evaluate_sweet_spot_portfolio,
    score_single_draw_portfolio,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    BENCHMARK_PAYOUT_PER_HIT_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    EXTENDED_SWEET_SPOT_CONFIGS,
    HOUSE_MONEY_MAX_SURPLUS_FRACTION,
    HOUSE_MONEY_MIN_BUFFER_DAYS,
    PEAK_CONVICTION_JOINT_R1_PCT,
    SAMPLE_CAPITAL_TIERS_VND,
    SELECTIVE_ALPHA_JOINT_R1_MIN_PCT,
    STAGE3_TICKET_CONFIGS,
    SWEET_SPOT_CONFIGS,
    VALID_STATIONS,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    CapitalDisciplineError,
    DataIntegrityError,
    TemporalLeakageError,
    XSMNAlphaError,
)
from xsmn_alpha.live.registry import (
    STATION_REGISTRY_35,
    VALID_35_STATION_CODES,
    WEEKDAY_VN_LABELS,
    get_station_codes_for_weekday,
    get_station_meta,
    get_stations_for_date,
    get_stations_for_weekday,
    get_weekday_vn_label,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerEntry,
    BenchmarkLedgerState,
    CapitalGuidanceContract,
    DailyQuantReportContract,
    DataPipelineAuditRecord,
    ExecutiveNLGContract,
    HitDetailRecord,
    RawDrawRecord,
    SampleCapitalAllocationRow,
    Stage3CanonicalDrawRecord,
    StationDailyScorecard,
    TicketConfigRecommendation,
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


def _make_uniform_10() -> list[float]:
    return [0.10] * 10


def _make_uniform_10x10() -> list[list[float]]:
    return [[0.01] * 10 for _ in range(10)]


def _make_sample_ticket_configs(primary_cfg: str = "1x4") -> dict[str, TicketConfigRecommendation]:
    configs: dict[str, TicketConfigRecommendation] = {}
    sample_nums: dict[str, list[str]] = {
        "2x2": ["21", "22", "31", "32"],
        "1x4": ["21", "22", "23", "28"],
        "4x1": ["01", "11", "21", "31"],
        "3x3": ["21", "22", "23", "31", "32", "33", "41", "42", "43"],
        "core_2x2_sat_3x3": ["21", "22", "23", "31", "32", "33", "41", "42", "43"],
    }
    for cid in STAGE3_TICKET_CONFIGS:
        cfg_meta = EXTENDED_SWEET_SPOT_CONFIGS[cid]
        nums = sample_nums[cid]
        unit_cost = float(cfg_meta["cost_per_draw"])
        p_s = 0.045 if len(nums) == 4 else 0.095
        p_18 = 1.0 - ((1.0 - p_s) ** 18)
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
            hit_at_least_1_in_18_prob=p_18,
            oos_roi_3y_pct=9.45 if cid == primary_cfg else 4.20,
            oos_win_rate_3y_pct=58.5,
            oos_hits_per_30_draws=float(cfg_meta["be_hits_30_draws"]) + 2.1,
            be_hits_30_draws=float(cfg_meta["be_hits_30_draws"]),
            is_recommended_primary=(cid == primary_cfg),
        )
    return configs


def _make_sample_scorecard(
    station_code: str = "XSHCM",
    station_name: str = "TP. Hồ Chí Minh",
    region: str = "Miền Nam",
    draw_time_ict: str = "16:15",
    last_draw_date: str = "2026-10-24",
    passes_alpha: bool = True,
) -> StationDailyScorecard:
    return StationDailyScorecard(
        station_code=station_code,
        station_name=station_name,
        region=region,  # type: ignore[arg-type]
        draw_time_ict=draw_time_ict,  # type: ignore[arg-type]
        sample_draws_3y=312 if station_code == "XSHCM" else 156,
        evaluated_oos_draws=267 if station_code == "XSHCM" else 111,
        last_draw_date_before_d=last_draw_date,
        chi2_15_tens=14.2,
        chi2_30_tens=19.8,
        chi2_60_tens=16.5,
        chi2_15_units=15.1,
        chi2_30_units=22.4,
        chi2_60_units=18.0,
        chi2_max_tens=19.8,
        chi2_max_units=22.4,
        chi2_max_overall=22.4,
        null_chi2_p90=18.5,
        null_chi2_p95=21.2,
        bf10_max_tens=3.45,
        bf10_max_units=5.12,
        bf10_max_overall=5.12,
        normalized_entropy_tens=0.985,
        normalized_entropy_units=0.979,
        bocd_map_run_length_tens=24,
        bocd_map_run_length_units=19,
        bocd_map_run_length=19,
        bocd_changepoint_warning=False,
        p_ai_tens=_make_uniform_10(),
        p_bocd_tens=_make_uniform_10(),
        p_seq_tens=_make_uniform_10(),
        ranked_balls_tens=[2, 3, 0, 1, 4, 5, 6, 7, 8, 9],
        p_ai_units=_make_uniform_10(),
        p_bocd_units=_make_uniform_10(),
        p_seq_units=_make_uniform_10(),
        ranked_balls_units=[1, 2, 3, 8, 0, 4, 5, 6, 7, 9],
        joint_100_matrix=_make_uniform_10x10(),
        oos_rank1_freq_tens_pct=10.85 if passes_alpha else 9.80,
        oos_rank1_freq_units_pct=10.75 if passes_alpha else 9.90,
        joint_r1_pct=1.166 if passes_alpha else 0.970,
        recommended_config_id="1x4",
        recommended_numbers=["21", "22", "23", "28"],
        best_oos_roi_pct=9.45 if passes_alpha else -4.50,
        ticket_configs=_make_sample_ticket_configs("1x4"),
        station_alpha_score=18.96 if passes_alpha else -4.12,
        passes_selective_alpha=passes_alpha,
        strong_convergence=passes_alpha,
        rank_in_day=1,
        role_label_vi="Đài Ưu Tiên Số 1" if passes_alpha else "Đứng Ngoài (Nhiễu Trắng)",
        rationale_vi="Lồng cầu đạt hội tụ đỉnh vượt ngưỡng P95.",
    )


def _make_sample_allocations(multiplier: float = 1.5) -> list[SampleCapitalAllocationRow]:
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


# ===========================================================================
# 1. Task 1: Stage 3 Constants, CapitalDisciplineError & 35-Station Registry
# ===========================================================================


class TestStage3ConstantsAndRegistry:
    """Verify Stage 3 constants, CapitalDisciplineError, and 35-station schedule registry."""

    def test_stage3_financial_and_house_money_constants(self) -> None:
        assert BENCHMARK_INITIAL_BANKROLL_VND == 1_000_000
        assert BENCHMARK_STAKE_PER_NUMBER_VND == 18_000
        assert BENCHMARK_BASE_DAILY_COST_4NUM_VND == 72_000
        assert BENCHMARK_PAYOUT_PER_HIT_VND == 87_500
        assert HOUSE_MONEY_MIN_BUFFER_DAYS == 2
        assert HOUSE_MONEY_MAX_SURPLUS_FRACTION == pytest.approx(0.50)
        assert SELECTIVE_ALPHA_JOINT_R1_MIN_PCT == pytest.approx(1.105)
        assert PEAK_CONVICTION_JOINT_R1_PCT == pytest.approx(1.150)
        assert SAMPLE_CAPITAL_TIERS_VND == (500_000, 1_000_000, 2_000_000, 5_000_000)
        assert STAGE3_TICKET_CONFIGS == ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3")

        # Backward compatibility with Stage 2 constants
        assert VALID_STATIONS == frozenset({"XSHCM", "XSVL"})
        assert len(SWEET_SPOT_CONFIGS) == 8
        assert "4x1" not in SWEET_SPOT_CONFIGS
        assert "4x1" in EXTENDED_SWEET_SPOT_CONFIGS
        assert len(EXTENDED_SWEET_SPOT_CONFIGS) == 9
        for cfg_id in STAGE3_TICKET_CONFIGS:
            assert cfg_id in EXTENDED_SWEET_SPOT_CONFIGS

        assert issubclass(CapitalDisciplineError, XSMNAlphaError)

    def test_station_registry_35_completeness_and_schedule(self) -> None:
        assert len(STATION_REGISTRY_35) == 35
        assert len(VALID_35_STATION_CODES) == 35
        assert set(STATION_REGISTRY_35.keys()) == VALID_35_STATION_CODES

        mn_stations = [s for s in STATION_REGISTRY_35.values() if s["region"] == "Miền Nam"]
        mt_stations = [s for s in STATION_REGISTRY_35.values() if s["region"] == "Miền Trung"]
        assert len(mn_stations) == 21
        assert len(mt_stations) == 14
        assert all(s["draw_time_ict"] == "16:15" for s in mn_stations)
        assert all(s["region_slug"] == "mien-nam" for s in mn_stations)
        assert all(s["draw_time_ict"] == "17:15" for s in mt_stations)
        assert all(s["region_slug"] == "mien-trung" for s in mt_stations)

        two_draws = {code for code, s in STATION_REGISTRY_35.items() if s["draws_per_week"] == 2}
        one_draw = {code for code, s in STATION_REGISTRY_35.items() if s["draws_per_week"] == 1}
        assert two_draws == {"XSHCM", "XSTTH", "XSDNG", "XSKH"}
        assert len(one_draw) == 31
        for code in two_draws:
            assert STATION_REGISTRY_35[code]["target_3y"] == 312
        for code in one_draw:
            assert STATION_REGISTRY_35[code]["target_3y"] == 156

        # Verify exact weekday schedules matching Table 5.2 of spec.md
        expected_by_weekday: dict[int, tuple[str, ...]] = {
            0: ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY"),
            1: ("XSBT", "XSVT", "XSBL", "XSDLK", "XSQNM"),
            2: ("XSDN", "XSCT", "XSST", "XSDNG", "XSKH"),
            3: ("XSTN", "XSAG", "XSBTH", "XSBDI", "XSQT", "XSQB"),
            4: ("XSVL", "XSBD", "XSTV", "XSGL", "XSNT"),
            5: ("XSHCM", "XSLA", "XSBP", "XSHG", "XSDNG", "XSQNG", "XSDNO"),
            6: ("XSTG", "XSKG", "XSDL", "XSTTH", "XSKH", "XSKT"),
        }
        for wd, expected_codes in expected_by_weekday.items():
            assert get_station_codes_for_weekday(wd) == expected_codes
            stations_list = get_stations_for_weekday(wd)
            assert tuple(s["station_code"] for s in stations_list) == expected_codes
            assert 5 <= len(stations_list) <= 7

        # Date lookup check: 2026-10-26 is Monday (0), 2026-10-25 is Sunday (6)
        mon_stations = get_stations_for_date("2026-10-26")
        assert tuple(s["station_code"] for s in mon_stations) == expected_by_weekday[0]
        sun_stations = get_stations_for_date(datetime.date(2026, 10, 25))
        assert tuple(s["station_code"] for s in sun_stations) == expected_by_weekday[6]
        assert get_weekday_vn_label("2026-10-26") == "Thứ 2"
        assert get_weekday_vn_label(6) == "Chủ Nhật"
        assert len(WEEKDAY_VN_LABELS) == 7

    def test_registry_negative_mutations_and_immutability(self) -> None:
        with pytest.raises(TypeError):
            STATION_REGISTRY_35["XSHCM"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            STATION_REGISTRY_35["XSHCM"]["target_3y"] = 10  # type: ignore[index]
        with pytest.raises(TypeError):
            EXTENDED_SWEET_SPOT_CONFIGS["4x1"] = {}  # type: ignore[index]

        with pytest.raises(DataIntegrityError):
            get_station_meta("XSHN")
        with pytest.raises(DataIntegrityError):
            get_stations_for_weekday(-1)
        with pytest.raises(DataIntegrityError):
            get_stations_for_weekday(7)
        with pytest.raises(DataIntegrityError):
            get_stations_for_weekday(True)  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            get_stations_for_date("26/10/2026")


# ===========================================================================
# 2. Task 1: Symmetric "4x1" Sweet-Spot Configuration Tests
# ===========================================================================


class TestSymmetric4x1SweetSpotConfig:
    """Verify symmetric '4x1' (Top 4 Tens x Top 1 Units = 4 numbers) in sweet_spot_sim.py."""

    def test_4x1_number_selection_probability_and_scoring(self) -> None:
        # Top 4 tens = [3, 1, 7, 0], Top 1 units = [8] -> {"08", "18", "38", "78"}
        p_tens = [0.12, 0.16, 0.06, 0.18, 0.08, 0.08, 0.06, 0.14, 0.06, 0.06]
        p_units = [0.08, 0.09, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08, 0.26, 0.08]

        cfg_4x1 = EXTENDED_SWEET_SPOT_CONFIGS["4x1"]
        assert cfg_4x1["tens_top_k"] == 4
        assert cfg_4x1["units_top_k"] == 1
        assert cfg_4x1["num_numbers"] == 4
        assert cfg_4x1["cost_per_draw"] == 4.0
        assert cfg_4x1["be_hits_30_draws"] == pytest.approx(
            (30.0 * 4.0) / BAO_LO_PAYOUT_PER_HIT, rel=1e-12
        )

        nums_4x1 = select_sweet_spot_numbers(p_tens, p_units, "4x1")
        assert nums_4x1 == ["08", "18", "38", "78"]

        p_set = compute_portfolio_set_probability(p_tens, p_units, "4x1")
        expected_p = (0.18 + 0.16 + 0.14 + 0.12) * 0.26
        assert p_set == pytest.approx(expected_p, rel=1e-12)

        # In _valid_18_prizes(), "08", "38", "78" each appear once -> 3 hits!
        prizes = _valid_18_prizes()
        res = score_single_draw_portfolio(p_tens, p_units, prizes, "4x1")
        assert res["config_id"] == "4x1"
        assert res["cost"] == pytest.approx(4.0)
        assert res["raw_hits"] == 3
        assert res["revenue"] == pytest.approx(3.0 * BAO_LO_PAYOUT_PER_HIT)
        assert res["net_profit"] == pytest.approx(3.0 * BAO_LO_PAYOUT_PER_HIT - 4.0)
        assert res["is_multi_hit_ge2"] is True

        # Walk-forward portfolio metrics for "4x1"
        metrics = evaluate_sweet_spot_portfolio([p_tens] * 5, [p_units] * 5, [prizes] * 5, "4x1")
        assert metrics.config_id == "4x1"
        assert metrics.evaluated_draws == 5
        assert metrics.cost_per_draw == pytest.approx(4.0)
        assert metrics.total_cost == pytest.approx(20.0)
        assert metrics.total_hits == pytest.approx(15.0)
        assert metrics.daily_win_rate == pytest.approx(1.0)

        # Ensure Stage 2 evaluate_all_sweet_spot_portfolios still returns the 8 original configs
        all_8 = evaluate_all_sweet_spot_portfolios([p_tens] * 2, [p_units] * 2, [prizes] * 2)
        assert set(all_8.keys()) == set(SWEET_SPOT_CONFIGS.keys())


# ===========================================================================
# 3. Task 2: Stage 3 Schemas & Adversarial Gates (Gates 1, 2, 3, 4, 5)
# ===========================================================================


class TestStage3SchemasAndAdversarialGates:
    """Verify Stage 3 Pydantic v2 contracts and fail-closed Gates 1, 2, 3, 4, and 5."""

    def test_gate1_35_station_draw_validation_pass_and_negative_mutations(self) -> None:
        prizes = _valid_18_prizes()
        # Any of the 35 stations (including XSDNG or XSDL) passes Stage3CanonicalDrawRecord
        rec_dl = Stage3CanonicalDrawRecord.from_prizes("XSDL", "2026-10-25", 0, prizes)
        assert rec_dl.station_code == "XSDL"
        assert sum(rec_dl.tens_counts) == 18
        assert sum(rec_dl.units_counts) == 18

        raw_dng = RawDrawRecord(
            station_code="XSDNG",
            draw_date="2026-10-24",
            prizes_last2=prizes,
        )
        assert raw_dng.station_code == "XSDNG"
        assert sum(raw_dng.tens_counts) == 18

        proxy = rec_dl.to_stage2_canonical()
        assert proxy.station_code in VALID_STATIONS

        # Negative Mutation 1: Unknown station outside 35 registry ("XSHN") -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            Stage3CanonicalDrawRecord.from_prizes("XSHN", "2026-10-25", 0, prizes)
        with pytest.raises(DataIntegrityError):
            RawDrawRecord(station_code="XSHN", draw_date="2026-10-25", prizes_last2=prizes)

        # Negative Mutation 2: 17 prizes (incomplete draw) -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            Stage3CanonicalDrawRecord.from_prizes("XSDL", "2026-10-25", 0, prizes[:17])

        # Negative Mutation 3: Full-width Unicode digits ("０８") -> DataIntegrityError
        bad_prizes = list(prizes)
        bad_prizes[3] = "０８"
        with pytest.raises(DataIntegrityError):
            Stage3CanonicalDrawRecord.from_prizes("XSDL", "2026-10-25", 0, bad_prizes)

    def test_gate3_simplex_calibration_on_scorecard_and_10x10_matrix(self) -> None:
        sc = _make_sample_scorecard()
        assert sc.station_code == "XSHCM"
        assert math.isclose(sum(sum(row) for row in sc.joint_100_matrix), 1.0, abs_tol=1e-6)

        # Negative Mutation: 10-ball distribution does not sum to 1.0 -> CalibrationIntegrityError
        dumped = sc.model_dump()
        dumped["p_ai_tens"] = [0.09] * 10
        with pytest.raises(CalibrationIntegrityError):
            StationDailyScorecard.model_validate(dumped)

        # Negative Mutation: 10x10 joint_100_matrix sums to 0.90 -> CalibrationIntegrityError
        dumped_mat = sc.model_dump()
        dumped_mat["joint_100_matrix"] = [[0.009] * 10 for _ in range(10)]
        with pytest.raises(CalibrationIntegrityError):
            StationDailyScorecard.model_validate(dumped_mat)

        # Negative Mutation: 10x10 matrix has wrong row count -> CalibrationIntegrityError
        dumped_shape = sc.model_dump()
        dumped_shape["joint_100_matrix"] = [[0.01] * 10 for _ in range(9)]
        with pytest.raises(CalibrationIntegrityError):
            StationDailyScorecard.model_validate(dumped_shape)

    def test_gate4_falsification_cash_brake_gate_pass_and_fail(self) -> None:
        # PASS when SKIP_NO_EDGE has multiplier=0.0, bet=0, all sample allocations cost=0
        zero_allocs = _make_sample_allocations(multiplier=0.0)
        cap_skip = CapitalGuidanceContract(
            verdict_tier="SKIP_NO_EDGE",
            should_play_today=False,
            recommended_multiplier=0.0,
            benchmark_bankroll_vnd=1_200_000,
            house_money_surplus_vnd=200_000,
            benchmark_bet_vnd=0,
            sample_allocations=zero_allocs,
            sizing_rationale_vi="Cầu nhiễu trắng — nghỉ 100% bảo toàn vốn.",
        )
        assert cap_skip.should_play_today is False
        assert cap_skip.benchmark_bet_vnd == 0

        # Negative Mutation 1: SKIP_NO_EDGE with should_play_today=True -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            CapitalGuidanceContract(
                verdict_tier="SKIP_NO_EDGE",
                should_play_today=True,
                recommended_multiplier=0.0,
                benchmark_bankroll_vnd=1_200_000,
                house_money_surplus_vnd=200_000,
                benchmark_bet_vnd=0,
                sample_allocations=zero_allocs,
            )

        # Negative Mutation 2: SKIP_NO_EDGE with recommended_multiplier > 0 -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            CapitalGuidanceContract(
                verdict_tier="SKIP_NO_EDGE",
                should_play_today=False,
                recommended_multiplier=1.0,
                benchmark_bankroll_vnd=1_200_000,
                house_money_surplus_vnd=200_000,
                benchmark_bet_vnd=0,
                sample_allocations=zero_allocs,
            )

        # Negative Mutation 3: SKIP_NO_EDGE with non-zero sample allocation -> DataIntegrityError
        non_zero_allocs = _make_sample_allocations(multiplier=1.0)
        with pytest.raises(DataIntegrityError):
            CapitalGuidanceContract(
                verdict_tier="SKIP_NO_EDGE",
                should_play_today=False,
                recommended_multiplier=0.0,
                benchmark_bankroll_vnd=1_200_000,
                house_money_surplus_vnd=200_000,
                benchmark_bet_vnd=0,
                sample_allocations=non_zero_allocs,
            )

    def test_gate5_house_money_and_ledger_integrity_pass_and_fail(self) -> None:
        # PASS: Valid settled entry matching spec.md Section 5.4.1
        entry = BenchmarkLedgerEntry(
            draw_date="2026-10-25",
            weekday_vn="Chủ Nhật",
            settlement_status="SETTLED",
            verdict_tier="PLAY_PEAK",
            chosen_station_code="XSDL",
            chosen_station_name="Đà Lạt (Lâm Đồng)",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            recommended_multiplier=1.5,
            bankroll_before_vnd=2_959_625,
            house_money_before_vnd=1_959_625,
            cost_vnd=108_000,
            actual_prizes_last2=_valid_18_prizes(),
            hit_count_k=1,
            hit_details=[HitDetailRecord(prize_index=10, prize_label="Giải Tư (5)", number="23")],
            revenue_vnd=131_250,
            net_profit_vnd=23_250,
            bankroll_after_vnd=2_982_875,
            house_money_after_vnd=1_982_875,
        )
        assert entry.net_profit_vnd == 23_250

        # Negative Mutation 1 (Todo Task 2 Manual Check):
        # multiplier=1.5 when house_money_before_vnd=50_000 (< 144_000) -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="PENDING",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt (Lâm Đồng)",
                chosen_region="Miền Nam",
                chosen_config_id="1x4",
                selected_numbers=["21", "22", "23", "28"],
                recommended_multiplier=1.5,
                bankroll_before_vnd=1_050_000,
                house_money_before_vnd=50_000,
                cost_vnd=108_000,
                bankroll_after_vnd=1_050_000,
                house_money_after_vnd=50_000,
            )

        # Negative Mutation 2: multiplier > 1.0 when bankroll < 1,000,000 -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="PENDING",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt (Lâm Đồng)",
                chosen_region="Miền Nam",
                chosen_config_id="1x4",
                selected_numbers=["21", "22", "23", "28"],
                recommended_multiplier=1.5,
                bankroll_before_vnd=950_000,
                house_money_before_vnd=0,
                cost_vnd=108_000,
                bankroll_after_vnd=950_000,
                house_money_after_vnd=0,
            )

        # Negative Mutation 3: Tampered bankroll_after_vnd -> CapitalDisciplineError
        bad_entry_data: dict[str, Any] = entry.model_dump()
        bad_entry_data["bankroll_after_vnd"] = 3_999_999
        bad_entry_data["house_money_after_vnd"] = 2_999_999
        with pytest.raises((CapitalDisciplineError, DataIntegrityError)):
            BenchmarkLedgerEntry.model_validate(bad_entry_data)

        # PASS & FAIL on BenchmarkLedgerState
        state = BenchmarkLedgerState(
            current_bankroll_vnd=1_023_250,
            house_money_surplus_vnd=23_250,
            peak_bankroll_vnd=1_023_250,
            min_bankroll_vnd=1_000_000,
            max_drawdown_vnd=0,
            total_tracked_days=1,
            played_days=1,
            rest_days=0,
            win_days=1,
            loss_days=0,
            total_cost_vnd=108_000,
            total_revenue_vnd=131_250,
            net_profit_vnd=23_250,
            updated_at="2026-10-26T05:00:00+07:00",
            sha256="abc123",
            entries=[],
        )
        assert state.current_bankroll_vnd == 1_023_250

        bad_state = state.model_dump()
        bad_state["current_bankroll_vnd"] = 1_500_000
        with pytest.raises((CapitalDisciplineError, DataIntegrityError)):
            BenchmarkLedgerState.model_validate(bad_state)

    def test_daily_quant_report_contract_and_gate2_cutoff_check(self) -> None:
        primary_sc = _make_sample_scorecard("XSHCM", last_draw_date="2026-10-24", passes_alpha=True)
        skip_sc = _make_sample_scorecard(
            "XSDT", "Đồng Tháp", "Miền Nam", "16:15", "2026-10-19", passes_alpha=False
        )
        cap_guide = CapitalGuidanceContract(
            verdict_tier="PLAY_PEAK",
            should_play_today=True,
            recommended_multiplier=1.5,
            benchmark_bankroll_vnd=1_500_000,
            house_money_surplus_vnd=500_000,
            benchmark_bet_vnd=108_000,
            stake_per_number_vnd=27_000,
            payout_per_hit_vnd=131_250,
            sample_allocations=_make_sample_allocations(1.5),
            sizing_rationale_vi="Đủ đệm lãi ròng >= 144.000đ, kích hoạt 1.5x.",
        )
        nlg = ExecutiveNLGContract(
            yesterday_settlement_summary_vi="Hôm qua nổ 1 nháy số 23, lãi +23.250đ.",
            q1_should_play_and_why="NÊN ĐÁNH — Đài TP.HCM đạt JointR1 = 1.166% >= 1.105%.",
            q2_which_station_and_region="Đài Ưu Tiên Số 1: TP. Hồ Chí Minh (Miền Nam - 16:15).",
            q3_which_numbers_and_config="Cấu hình 1x4 gồm 4 số: 21, 22, 23, 28.",
            q4_how_to_allocate_capital="Hệ số vốn 1.5x (108.000đ/ngày cho Quỹ Chuẩn 1 Triệu).",
        )
        audit = DataPipelineAuditRecord(
            target_date="2026-10-26",
            total_stations_35=35,
            stations_synced_ok=35,
            fallback_used_count=0,
            schema_gate_passed=True,
            latest_settled_date="2026-10-25",
        )
        report = DailyQuantReportContract(
            report_date="2026-10-26",
            weekday_vn="Thứ 2",
            generated_at_ict="2026-10-26T05:00:00+07:00",
            data_pipeline_audit=audit,
            verdict_tier="PLAY_PEAK",
            should_play_today=True,
            primary_station=primary_sc,
            secondary_station=None,
            skipped_stations=[skip_sc],
            all_today_stations=[primary_sc, skip_sc],
            capital_guidance=cap_guide,
            executive_nlg_vi=nlg,
            telegram_message_html="<b>Bản tin 05:00 sáng</b>",
        )
        assert report.should_play_today is True

        # Gate 2 Negative Mutation: scorecard has last_draw_date_before_d >= report_date
        leaked_sc = _make_sample_scorecard("XSHCM", last_draw_date="2026-10-26", passes_alpha=True)
        with pytest.raises(TemporalLeakageError):
            DailyQuantReportContract(
                report_date="2026-10-26",
                weekday_vn="Thứ 2",
                generated_at_ict="2026-10-26T05:00:00+07:00",
                data_pipeline_audit=audit,
                verdict_tier="PLAY_PEAK",
                should_play_today=True,
                primary_station=leaked_sc,
                all_today_stations=[leaked_sc],
                capital_guidance=cap_guide,
                executive_nlg_vi=nlg,
            )

        # Extra field forbidden on StrictBaseModel
        with pytest.raises((DataIntegrityError, ValidationError)):
            ExecutiveNLGContract(
                q1_should_play_and_why="A",
                q2_which_station_and_region="B",
                q3_which_numbers_and_config="C",
                q4_how_to_allocate_capital="D",
                unexpected_extra="forbidden",  # type: ignore[call-arg]
            )


# ===========================================================================
# 4. Task 3: 35-Station Incremental Multi-Source Fetcher, 3-Tier Failover & SHA-256
# ===========================================================================


def _make_minhngoc_html(
    station_name: str,
    dmy_date: str,
    prizes_18: list[str],
    *,
    table_class: str = "bkqtinhmiennam",
    include_giaidb: bool = True,
) -> str:
    """Build synthetic MinhNgoc HTML table (18 prizes or 17 prizes if include_giaidb=False)."""
    g8 = prizes_18[0]
    g7 = prizes_18[1]
    g6 = " - ".join(prizes_18[2:5])
    g5 = prizes_18[5]
    g4 = " - ".join(prizes_18[6:13])
    g3 = " - ".join(prizes_18[13:15])
    g2 = prizes_18[15]
    g1 = prizes_18[16]
    gdb = prizes_18[17] if include_giaidb else ""
    return f"""
    <html><body>
    <table class="{table_class}">
      <tr><td class="tinh">{station_name}</td><td class="ngay">{dmy_date}</td></tr>
      <tr><td class="giai8">{g8}</td></tr>
      <tr><td class="giai7">1{g7}</td></tr>
      <tr><td class="giai6">{g6}</td></tr>
      <tr><td class="giai5">23{g5}</td></tr>
      <tr><td class="giai4">{g4}</td></tr>
      <tr><td class="giai3">{g3}</td></tr>
      <tr><td class="giai2">456{g2}</td></tr>
      <tr><td class="giai1">789{g1}</td></tr>
      <tr><td class="giaidb">{gdb}</td></tr>
    </table>
    </body></html>
    """


def _make_labeled_fallback_html(
    station_name: str,
    dmy_date: str,
    prizes_18: list[str],
    *,
    include_giaidb: bool = True,
) -> str:
    """Build synthetic xskt.com.vn / xoso.com.vn row-labeled HTML table."""
    g8 = prizes_18[0]
    g7 = prizes_18[1]
    g6 = " - ".join(prizes_18[2:5])
    g5 = prizes_18[5]
    g4 = " - ".join(prizes_18[6:13])
    g3 = " - ".join(prizes_18[13:15])
    g2 = prizes_18[15]
    g1 = prizes_18[16]
    gdb_row = f"<tr><td>ĐB</td><td>9999{prizes_18[17]}</td></tr>" if include_giaidb else ""
    return f"""
    <html><body>
    <h2>Kết quả xổ số {station_name} ngày {dmy_date}</h2>
    <table>
      <tr><td>G8</td><td>{g8}</td></tr>
      <tr><td>G7</td><td>1{g7}</td></tr>
      <tr><td>G6</td><td>{g6}</td></tr>
      <tr><td>G5</td><td>23{g5}</td></tr>
      <tr><td>G4</td><td>{g4}</td></tr>
      <tr><td>G3</td><td>{g3}</td></tr>
      <tr><td>G2</td><td>456{g2}</td></tr>
      <tr><td>G1</td><td>789{g1}</td></tr>
      {gdb_row}
    </table>
    </body></html>
    """


class TestStage3MultiStationFetcherAndFailover:
    """Verify multi_fetcher.py: 35-station cache SHA-256, delta sync & 3-tier failover."""

    def test_url_builders_and_parsers_for_mien_nam_and_mien_trung(self) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            build_station_minhngoc_url,
            build_station_xoso_url,
            build_station_xskt_url,
            parse_station_minhngoc_html,
            parse_station_xoso_html,
            parse_station_xskt_html,
        )

        # Miền Nam station: XSDL (Đà Lạt)
        assert (
            build_station_minhngoc_url("XSDL", "2026-10-25")
            == "https://www.minhngoc.net.vn/ket-qua-xo-so/mien-nam/da-lat/25-10-2026.html"
        )
        assert (
            build_station_xskt_url("XSDL", "2026-10-25")
            == "https://xskt.com.vn/xsdl/ngay-25-10-2026"
        )
        assert (
            build_station_xoso_url("XSDL", "2026-10-25")
            == "https://xoso.com.vn/xsdl-25-10-2026.html"
        )

        # Miền Trung station: XSDNG (Đà Nẵng)
        assert (
            build_station_minhngoc_url("XSDNG", "2026-10-24")
            == "https://www.minhngoc.net.vn/ket-qua-xo-so/mien-trung/da-nang/24-10-2026.html"
        )
        assert (
            build_station_xskt_url("XSDNG", "2026-10-24")
            == "https://xskt.com.vn/xsdng/ngay-24-10-2026"
        )
        assert (
            build_station_xoso_url("XSDNG", "2026-10-24")
            == "https://xoso.com.vn/xsdng-24-10-2026.html"
        )

        prizes = _valid_18_prizes()
        html_mn = _make_minhngoc_html(
            "Đà Nẵng",
            "24/10/2026",
            prizes,
            table_class="bkqtinhmientrung",
        )
        parsed_mn = parse_station_minhngoc_html(html_mn, "XSDNG")
        assert len(parsed_mn) == 1
        assert parsed_mn[0]["station_code"] == "XSDNG"
        assert parsed_mn[0]["draw_date"] == "2026-10-24"
        assert parsed_mn[0]["prizes_last2"] == prizes

        html_fb = _make_labeled_fallback_html("Đà Lạt", "25-10-2026", prizes)
        parsed_xskt = parse_station_xskt_html(html_fb, "XSDL")
        parsed_xoso = parse_station_xoso_html(html_fb, "XSDL")
        assert len(parsed_xskt) == 1
        assert parsed_xskt[0]["prizes_last2"] == prizes
        assert parsed_xoso == parsed_xskt

    def test_sha256_cache_save_load_and_incremental_delta_sync(self, tmp_path: Path) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            compute_station_draws_sha256,
            load_station_raw_cache,
            save_station_raw_cache,
            sync_all_35_stations,
            sync_station_draws,
        )

        prizes_1 = _valid_18_prizes()
        prizes_2 = list(reversed(_valid_18_prizes()))
        # XSDT (Đồng Tháp) opens on Mondays (weekday 0): 2026-10-12, 2026-10-19, 2026-10-26
        initial_draws = [
            {"station_code": "XSDT", "draw_date": "2026-10-12", "prizes_last2": prizes_1},
            {"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes_2},
        ]
        cache_file = save_station_raw_cache("XSDT", initial_draws, raw_dir=tmp_path)
        assert cache_file.exists()

        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        assert payload["station_code"] == "XSDT"
        assert payload["draw_count"] == 2
        assert payload["last_draw_date"] == "2026-10-19"
        assert payload["sha256"] == compute_station_draws_sha256(initial_draws, station_code="XSDT")

        loaded = load_station_raw_cache("XSDT", raw_dir=tmp_path)
        assert len(loaded) == 2
        assert loaded[-1]["draw_date"] == "2026-10-19"

        # Now test incremental delta sync up to Monday 2026-10-26 via MockTransport:
        # Only 2026-10-26 should be fetched and appended to the existing 2 cached draws!
        requested_urls: list[str] = []

        def _mock_handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            if "minhngoc.net.vn" in str(request.url) and "26-10-2026" in str(request.url):
                return httpx.Response(
                    200,
                    text=_make_minhngoc_html("Đồng Tháp", "26/10/2026", prizes_1),
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(_mock_handler)
        synced_records, fb_count = sync_station_draws(
            "XSDT",
            target_date="2026-10-26",
            raw_dir=tmp_path,
            transport=transport,
        )
        assert fb_count == 0
        assert len(synced_records) == 3
        assert [r.draw_date for r in synced_records] == [
            "2026-10-12",
            "2026-10-19",
            "2026-10-26",
        ]
        assert len(requested_urls) == 1
        assert "26-10-2026" in requested_urls[0]

        # Re-running sync on the same target_date hits cache fast-path with 0 HTTP requests
        requested_urls.clear()
        draws_by_st, audit = sync_all_35_stations(
            target_date="2026-10-26",
            raw_dir=tmp_path,
            station_codes=["XSDT"],
            transport=transport,
        )
        assert len(requested_urls) == 0
        assert len(draws_by_st["XSDT"]) == 3
        assert audit.schema_gate_passed is True
        assert audit.stations_synced_ok == 1
        assert audit.fallback_used_count == 0
        assert audit.latest_settled_date == "2026-10-26"

    def test_3_tier_automatic_failover_on_incomplete_draw_and_http_error(
        self, tmp_path: Path
    ) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            save_station_raw_cache,
            sync_all_35_stations,
        )

        prizes = _valid_18_prizes()
        # Seed XSCM (Monday) and XSPY (Monday) up to 2026-10-19
        save_station_raw_cache(
            "XSCM",
            [{"station_code": "XSCM", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            raw_dir=tmp_path,
        )
        save_station_raw_cache(
            "XSPY",
            [{"station_code": "XSPY", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            raw_dir=tmp_path,
        )

        # Scenario:
        # - For XSCM on 2026-10-26: minhngoc returns an INCOMPLETE 17-prize table (missing Giải ĐB),
        #   so Gate 1 rejects it and multi_fetcher fails over to Tier 2 (xskt.com.vn, 18 prizes).
        # - For XSPY on 2026-10-26: minhngoc returns HTTP 503 AND xskt returns HTTP 500,
        #   so multi_fetcher fails over to Tier 3 (xoso.com.vn, 18 prizes).
        def _failover_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "ca-mau" in url and "minhngoc.net.vn" in url:
                return httpx.Response(
                    200,
                    text=_make_minhngoc_html("Cà Mau", "26/10/2026", prizes, include_giaidb=False),
                )
            if "xscm" in url and "xskt.com.vn" in url:
                return httpx.Response(
                    200,
                    text=_make_labeled_fallback_html("Cà Mau", "26-10-2026", prizes),
                )
            if "phu-yen" in url and "minhngoc.net.vn" in url:
                return httpx.Response(503, text="Service Unavailable")
            if "xspy" in url and "xskt.com.vn" in url:
                return httpx.Response(500, text="Internal Server Error")
            if "xspy" in url and "xoso.com.vn" in url:
                return httpx.Response(
                    200,
                    text=_make_labeled_fallback_html("Phú Yên", "26-10-2026", prizes),
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(_failover_handler)
        draws_map, audit = sync_all_35_stations(
            target_date="2026-10-26",
            raw_dir=tmp_path,
            station_codes=["XSCM", "XSPY"],
            retries=1,
            transport=transport,
        )
        assert len(draws_map["XSCM"]) == 2
        assert draws_map["XSCM"][-1].draw_date == "2026-10-26"
        assert len(draws_map["XSPY"]) == 2
        assert draws_map["XSPY"][-1].draw_date == "2026-10-26"
        assert audit.stations_synced_ok == 2
        assert audit.fallback_used_count == 2
        assert audit.schema_gate_passed is True

    def test_multi_fetcher_negative_mutations_fail_closed(self, tmp_path: Path) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            build_station_minhngoc_url,
            canonicalize_station_draws,
            load_station_raw_cache,
            save_station_raw_cache,
            sync_station_draws,
        )

        prizes = _valid_18_prizes()

        # Negative Mutation 1: Unknown station code "XSHN" -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            build_station_minhngoc_url("XSHN", "2026-10-25")
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws(
                [{"station_code": "XSHN", "draw_date": "2026-10-25", "prizes_last2": prizes}],
                station_code="XSHN",
            )
        with pytest.raises(DataIntegrityError):
            sync_station_draws("XSHN", target_date="2026-10-25", raw_dir=tmp_path)

        # Negative Mutation 2: 17-prize incomplete draw rejected by DataSchemaGate
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws(
                [{"station_code": "XSDL", "draw_date": "2026-10-25", "prizes_last2": prizes[:17]}],
                station_code="XSDL",
            )

        # Also when all 3 web sources return 17 prizes (in-progress draw), failover must reject
        # and raise DataIntegrityError without writing incomplete draw to cache
        save_station_raw_cache(
            "XSDT",
            [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            raw_dir=tmp_path,
        )

        def _all_incomplete_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=_make_minhngoc_html("Đồng Tháp", "26/10/2026", prizes, include_giaidb=False),
            )

        with pytest.raises(DataIntegrityError):
            sync_station_draws(
                "XSDT",
                target_date="2026-10-26",
                raw_dir=tmp_path,
                retries=1,
                transport=httpx.MockTransport(_all_incomplete_handler),
            )
        # Verify cache was NOT polluted with the 17-prize draw
        cached_after_fail = load_station_raw_cache("XSDT", raw_dir=tmp_path)
        assert len(cached_after_fail) == 1
        assert cached_after_fail[-1]["draw_date"] == "2026-10-19"

        # Negative Mutation 3: Full-width Unicode digits ("０８") -> DataIntegrityError
        fw_prizes = list(prizes)
        fw_prizes[0] = "０８"
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws(
                [{"station_code": "XSDL", "draw_date": "2026-10-25", "prizes_last2": fw_prizes}],
                station_code="XSDL",
            )

        # Negative Mutation 4: Duplicate draw_date -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws(
                [
                    {"station_code": "XSDL", "draw_date": "2026-10-25", "prizes_last2": prizes},
                    {"station_code": "XSDL", "draw_date": "2026-10-25", "prizes_last2": prizes},
                ],
                station_code="XSDL",
            )

        # Negative Mutation 5: Corrupted sha256 checksum in cache file -> DataIntegrityError
        cache_path = save_station_raw_cache(
            "XSDL",
            [{"station_code": "XSDL", "draw_date": "2026-10-25", "prizes_last2": prizes}],
            raw_dir=tmp_path,
        )
        tampered = json.loads(cache_path.read_text(encoding="utf-8"))
        tampered["sha256"] = "0" * 64
        cache_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            load_station_raw_cache("XSDL", raw_dir=tmp_path)
        with pytest.raises(DataIntegrityError):
            sync_station_draws("XSDL", target_date="2026-10-25", raw_dir=tmp_path, offline=True)

    def test_real_35_stations_cache_audit_and_sha256_integrity(self) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            load_station_raw_cache,
            sync_all_35_stations,
        )

        raw_all_dir = Path("data/raw_all")
        draws_by_st, audit = sync_all_35_stations(
            target_date="2026-10-25",
            raw_dir=raw_all_dir,
            offline=True,
        )
        assert audit.schema_gate_passed is True
        assert audit.total_stations_35 == 35
        assert audit.stations_synced_ok == 35
        assert audit.latest_settled_date == "2026-10-25"
        assert len(draws_by_st) == 35

        for code in VALID_35_STATION_CODES:
            loaded = load_station_raw_cache(
                code,
                raw_dir=raw_all_dir,
                verify_sha256=True,
                allow_unhashed_legacy=False,
            )
            assert len(loaded) >= STATION_REGISTRY_35[code]["target_3y"]

    def test_f01_f02_f08_station_collision_date_poisoning_and_cache_hardening(
        self, tmp_path: Path
    ) -> None:
        from xsmn_alpha.live.multi_fetcher import (
            fetch_station_draw_with_failover,
            parse_station_minhngoc_html,
            parse_station_xskt_html,
            save_station_raw_cache,
            sync_all_35_stations,
            sync_station_draws,
        )

        prizes = _valid_18_prizes()

        # F-01(a): Substring collisions must NOT cross-contaminate stations
        for wrong_header, target_code in [
            ("XSDNG", "XSDN"),
            ("XSDNO", "XSDN"),
            ("XSDLK", "XSDL"),
            ("XSBDI", "XSBD"),
            ("XSBTH", "XSBT"),
        ]:
            html_wrong = _make_minhngoc_html(wrong_header, "25/10/2026", prizes)
            assert parse_station_minhngoc_html(html_wrong, target_code) == []

        # F-01(b): Domain token 'xskt.com.vn' on Tiền Giang page must NOT match XSKT (Kon Tum)
        html_xskt_domain = f"""
        <html><body>
        <div>Nguồn: xskt.com.vn - Kết quả xổ số Tiền Giang ngày 25-10-2026</div>
        {_make_labeled_fallback_html("Tiền Giang", "25-10-2026", prizes)}
        </body></html>
        """
        assert parse_station_xskt_html(html_xskt_domain, "XSKT") == []

        # F-01(c): Navigation links (<nav><a ...>) before a Cà Mau table must NOT match XSDT
        html_nav_noise = f"""
        <html><body>
        <nav><a href="/xsdt">Xổ số Đồng Tháp (XSDT)</a> | <a href="/xshcm">XSHCM</a></nav>
        {_make_labeled_fallback_html("Cà Mau", "26-10-2026", prizes)}
        </body></html>
        """
        assert parse_station_xskt_html(html_nav_noise, "XSDT") == []
        parsed_cm = parse_station_xskt_html(html_nav_noise, "XSCM")
        assert len(parsed_cm) == 1
        assert parsed_cm[0]["station_code"] == "XSCM"

        # F-02(a): Vietnamese word-formatted date ("Ngày 19 tháng 10 năm 2026") is parsed accurately
        # and rejected by fetch_station_draw_with_failover when target_date is 2026-10-26
        stale_vn_word_html = _make_labeled_fallback_html("Đồng Tháp", "19-10-2026", prizes).replace(
            "ngày 19-10-2026", "Ngày 19 tháng 10 năm 2026"
        )
        parsed_vn_word = parse_station_xskt_html(stale_vn_word_html, "XSDT")
        assert len(parsed_vn_word) == 1
        assert parsed_vn_word[0]["draw_date"] == "2026-10-19"

        # F-02(b): Undated table must NOT be silently stamped with target_date during failover
        undated_html = _make_labeled_fallback_html("Đồng Tháp", "26-10-2026", prizes).replace(
            "ngày 26-10-2026", ""
        )

        async def _check_failover_rejects(body: str) -> None:
            transport = httpx.MockTransport(lambda _req: httpx.Response(200, text=body))
            async with httpx.AsyncClient(transport=transport) as client:
                with pytest.raises(DataIntegrityError):
                    await fetch_station_draw_with_failover(client, "XSDT", "2026-10-26", retries=1)

        import asyncio

        asyncio.run(_check_failover_rejects(stale_vn_word_html))
        asyncio.run(_check_failover_rejects(undated_html))

        # F-08(a): Unhashed cache file must be rejected by sync_station_draws (no auto-rehash)
        unhashed_dir = tmp_path / "unhashed"
        cache_file = save_station_raw_cache(
            "XSDT",
            [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            raw_dir=unhashed_dir,
        )
        raw_obj = json.loads(cache_file.read_text(encoding="utf-8"))
        del raw_obj["sha256"]
        raw_obj["draws"][0]["prizes_last2"] = ["99"] * 18
        cache_file.write_text(json.dumps(raw_obj), encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            sync_station_draws("XSDT", target_date="2026-10-19", raw_dir=unhashed_dir)

        # F-08(b): Truncated/corrupted JSON raises DataIntegrityError (never raw JSONDecodeError)
        corrupt_dir = tmp_path / "corrupt"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "XSDT_draws.json").write_text("{corrupted_json", encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            sync_station_draws("XSDT", target_date="2026-10-19", raw_dir=corrupt_dir)

        # F-08(c): Single-draw cache on target_date (0 pre-target history draws) triggers backfill
        partial_dir = tmp_path / "partial"
        save_station_raw_cache(
            "XSHCM",
            [{"station_code": "XSHCM", "draw_date": "2026-10-26", "prizes_last2": prizes}],
            raw_dir=partial_dir,
        )
        with pytest.raises(DataIntegrityError):
            sync_all_35_stations(
                target_date="2026-10-26",
                raw_dir=partial_dir,
                station_codes=["XSHCM"],
                retries=1,
                transport=httpx.MockTransport(lambda _req: httpx.Response(404)),
            )


class TestStage3ReconcileNegativeMutationsBatch1:
    """Verify negative mutations for F-03, F-04, F-05, A-09, A-10, A-11, and A-12."""

    def test_a12_capital_discipline_error_is_distinct_from_data_integrity_error(self) -> None:
        assert issubclass(CapitalDisciplineError, XSMNAlphaError)
        assert not issubclass(CapitalDisciplineError, DataIntegrityError)

    def test_a09_a10_a11_schema_contracts_and_stage2_proxy(self) -> None:
        from xsmn_alpha.schemas import validate_probability_simplex

        # A-09: Explicit tol=1e-6 strictly enforces 1e-6 (rejects 5e-6 deviation)
        bad_simplex = [0.10] * 9 + [0.100005]
        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex(bad_simplex, tol=1e-6)
        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex([0.10] * 9 + [0.10002])

        # A-11: Stage3CanonicalDrawRecord.to_stage2_canonical proxy cadence & allow_stage2_proxy
        prizes = _valid_18_prizes()
        rec_1w = Stage3CanonicalDrawRecord.from_prizes("XSDL", "2026-10-25", 0, prizes)
        rec_2w = Stage3CanonicalDrawRecord.from_prizes("XSDNG", "2026-10-24", 0, prizes)
        assert rec_1w.to_stage2_canonical().station_code == "XSVL"
        assert rec_2w.to_stage2_canonical().station_code == "XSHCM"
        with pytest.raises(DataIntegrityError):
            rec_1w.to_stage2_canonical(allow_stage2_proxy=False)

        # A-10: TicketConfigRecommendation rejects malformed core/satellite numbers
        base_cfg = _make_sample_ticket_configs("1x4")["core_2x2_sat_3x3"].model_dump()
        bad_cfg = dict(base_cfg)
        bad_cfg["core_numbers"] = ["21", "22", "31"]  # Only 3 core numbers instead of 4
        with pytest.raises(DataIntegrityError):
            TicketConfigRecommendation.model_validate(bad_cfg)

        # A-10: SampleCapitalAllocationRow rejects wrong net_profit_3hits_vnd
        row_dump = _make_sample_allocations(1.0)[0].model_dump()
        row_dump["net_profit_3hits_vnd"] = 999_999
        with pytest.raises(DataIntegrityError):
            SampleCapitalAllocationRow.model_validate(row_dump)

    def test_f03_f04_f05_gate_bypass_mutations_blocked(self) -> None:
        prizes = _valid_18_prizes()

        # F-03(a): Arbitrary 10.0x multiplier or PLAY_CAUTIOUS > 1.0x -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="PENDING",
                verdict_tier="PLAY_CAUTIOUS",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt",
                chosen_region="Miền Nam",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=1.5,
                bankroll_before_vnd=2_000_000,
                house_money_before_vnd=1_000_000,
                cost_vnd=108_000,
                bankroll_after_vnd=2_000_000,
                house_money_after_vnd=1_000_000,
            )

        # F-03(b): 1.0x multiplier with inflated cost_vnd=500,000 -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="PENDING",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt",
                chosen_region="Miền Nam",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=1.0,
                bankroll_before_vnd=1_050_000,
                house_money_before_vnd=50_000,
                cost_vnd=500_000,
                bankroll_after_vnd=1_050_000,
                house_money_after_vnd=50_000,
            )

        # F-03(c): Station not scheduled on Sunday (XSHCM on 2026-10-25) -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="PENDING",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSHCM",
                chosen_station_name="TP.HCM",
                chosen_region="Miền Nam",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=1.0,
                bankroll_before_vnd=1_000_000,
                house_money_before_vnd=0,
                cost_vnd=72_000,
                bankroll_after_vnd=1_000_000,
                house_money_after_vnd=0,
            )

        # F-03(d): Forged hit_count_k / revenue_vnd on SETTLED entry -> DataIntegrityError
        with pytest.raises((DataIntegrityError, CapitalDisciplineError)):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="SETTLED",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt",
                chosen_region="Miền Nam",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=1.0,
                bankroll_before_vnd=1_000_000,
                house_money_before_vnd=0,
                cost_vnd=72_000,
                actual_prizes_last2=["99"] * 18,
                hit_count_k=2,
                hit_details=[],
                revenue_vnd=175_000,
                net_profit_vnd=103_000,
                bankroll_after_vnd=1_103_000,
                house_money_after_vnd=103_000,
            )

        # F-04: BenchmarkLedgerState with broken entry chain or peak < current
        e1 = BenchmarkLedgerEntry(
            draw_date="2026-10-24",
            weekday_vn="Thứ 7",
            settlement_status="SETTLED",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_station_name="TP.HCM",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            recommended_multiplier=1.0,
            bankroll_before_vnd=1_000_000,
            house_money_before_vnd=0,
            cost_vnd=72_000,
            actual_prizes_last2=prizes,
            hit_count_k=1,
            hit_details=[HitDetailRecord(prize_index=10, prize_label="Giải Tư (5)", number="23")],
            revenue_vnd=87_500,
            net_profit_vnd=15_500,
            bankroll_after_vnd=1_015_500,
            house_money_after_vnd=15_500,
        )
        with pytest.raises((CapitalDisciplineError, DataIntegrityError)):
            BenchmarkLedgerState(
                current_bankroll_vnd=2_000_000,
                house_money_surplus_vnd=1_000_000,
                peak_bankroll_vnd=2_000_000,
                min_bankroll_vnd=1_000_000,
                max_drawdown_vnd=0,
                total_tracked_days=1,
                played_days=1,
                rest_days=0,
                win_days=1,
                loss_days=0,
                total_cost_vnd=72_000,
                total_revenue_vnd=1_072_000,
                net_profit_vnd=1_000_000,
                updated_at="2026-10-25T05:00:00+07:00",
                entries=[e1],
            )

        # F-05(a): StationDailyScorecard with inverted ranked_balls or false passes_selective_alpha
        sc_dump = _make_sample_scorecard("XSHCM", passes_alpha=True).model_dump()
        sc_dump["p_ai_tens"] = [0.28, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08]
        # Ball 1 (0.08) ranked ahead of Ball 0 (0.28)
        sc_dump["ranked_balls_tens"] = [1, 0, 2, 3, 4, 5, 6, 7, 8, 9]
        with pytest.raises(CalibrationIntegrityError):
            StationDailyScorecard.model_validate(sc_dump)

        sc_alpha_dump = _make_sample_scorecard("XSHCM", passes_alpha=False).model_dump()
        # False positive on joint_r1=0.970, roi=-4.50
        sc_alpha_dump["passes_selective_alpha"] = True
        with pytest.raises(DataIntegrityError):
            StationDailyScorecard.model_validate(sc_alpha_dump)

        # F-05(b): DailyQuantReportContract with primary_station.passes_selective_alpha=False
        # on PLAY_PEAK or leaked skipped_stations date -> DataIntegrityError / TemporalLeakageError
        no_edge_sc = _make_sample_scorecard(
            "XSHCM", last_draw_date="2026-10-24", passes_alpha=False
        )
        cap_guide = CapitalGuidanceContract(
            verdict_tier="PLAY_PEAK",
            should_play_today=True,
            recommended_multiplier=1.5,
            benchmark_bankroll_vnd=1_500_000,
            house_money_surplus_vnd=500_000,
            benchmark_bet_vnd=108_000,
            stake_per_number_vnd=27_000,
            payout_per_hit_vnd=131_250,
            sample_allocations=_make_sample_allocations(1.5),
        )
        nlg = ExecutiveNLGContract(
            q1_should_play_and_why="A",
            q2_which_station_and_region="B",
            q3_which_numbers_and_config="C",
            q4_how_to_allocate_capital="D",
        )
        audit_ok = DataPipelineAuditRecord(
            target_date="2026-10-26",
            total_stations_35=35,
            stations_synced_ok=35,
            schema_gate_passed=True,
            latest_settled_date="2026-10-25",
        )
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date="2026-10-26",
                weekday_vn="Thứ 2",
                generated_at_ict="2026-10-26T05:00:00+07:00",
                data_pipeline_audit=audit_ok,
                verdict_tier="PLAY_PEAK",
                should_play_today=True,
                primary_station=no_edge_sc,
                all_today_stations=[no_edge_sc],
                capital_guidance=cap_guide,
                executive_nlg_vi=nlg,
            )

        leaked_skip_sc = _make_sample_scorecard(
            "XSDT", "Đồng Tháp", "Miền Nam", "16:15", "2026-10-27", passes_alpha=False
        )
        valid_primary_sc = _make_sample_scorecard(
            "XSHCM", last_draw_date="2026-10-24", passes_alpha=True
        )
        with pytest.raises(TemporalLeakageError):
            DailyQuantReportContract(
                report_date="2026-10-26",
                weekday_vn="Thứ 2",
                generated_at_ict="2026-10-26T05:00:00+07:00",
                data_pipeline_audit=audit_ok,
                verdict_tier="PLAY_PEAK",
                should_play_today=True,
                primary_station=valid_primary_sc,
                skipped_stations=[leaked_skip_sc],
                all_today_stations=[valid_primary_sc],
                capital_guidance=cap_guide,
                executive_nlg_vi=nlg,
            )

    def test_multi_fetcher_and_canonicalize_defensive_branches(self) -> None:
        """Exercise defensive validation branches in multi_fetcher.py for >=90% coverage."""
        import datetime

        from xsmn_alpha.live.multi_fetcher import (
            _coerce_target_date,
            _extract_date_from_fragment_35,
            _extract_last_date_from_fragment_35,
            canonicalize_station_draws,
            deduplicate_and_sort_station_draws,
        )

        # _coerce_target_date branches
        assert isinstance(_coerce_target_date(None), datetime.date)
        assert _coerce_target_date(datetime.date(2026, 10, 26)) == datetime.date(2026, 10, 26)
        with pytest.raises(DataIntegrityError):
            _coerce_target_date(12345)  # type: ignore[arg-type]

        # _extract_date_from_fragment_35 & _extract_last_date_from_fragment_35 word dates
        assert _extract_date_from_fragment_35("Mở thưởng ngày 19 tháng 10 năm 2026") == "2026-10-19"
        assert _extract_date_from_fragment_35("Ngày 99 tháng 99 năm 2026") is None
        assert _extract_date_from_fragment_35("No date", fallback_date="bad-date") is None
        assert (
            _extract_last_date_from_fragment_35(
                "Kỳ 12/10/2026 và ngày 19 tháng 10 năm 2026 "
                "(lỗi 99/99/2026, ngày 99 tháng 99 năm 2026)"
            )
            == "2026-10-19"
        )
        assert _extract_last_date_from_fragment_35("Không có ngày") is None

        prizes = _valid_18_prizes()
        rec0 = canonicalize_station_draws(
            [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            "XSDT",
        )[0]
        # deduplicate_and_sort_station_draws with Stage3CanonicalDrawRecord & extract_last2
        deduped = deduplicate_and_sort_station_draws(
            [rec0, {"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            "XSDT",
            extract_last2_from_full_prizes=True,
        )
        assert len(deduped) == 1

        for bad_arg in ([], "not-a-seq", [123]):
            with pytest.raises(DataIntegrityError):
                deduplicate_and_sort_station_draws(bad_arg, "XSDT")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            deduplicate_and_sort_station_draws(
                [{"station_code": "XSHCM", "draw_date": "2026-10-19", "prizes_last2": prizes}],
                "XSDT",
            )
        with pytest.raises(DataIntegrityError):
            deduplicate_and_sort_station_draws(
                [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": ["01"]}],
                "XSDT",
            )
        with pytest.raises(DataIntegrityError):
            deduplicate_and_sort_station_draws(
                [
                    {"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes},
                    {
                        "station_code": "XSDT",
                        "draw_date": "2026-10-19",
                        "prizes_last2": list(reversed(prizes)),
                    },
                ],
                "XSDT",
            )

        # canonicalize_station_draws defensive checks
        assert len(canonicalize_station_draws([rec0], "XSDT")) == 1
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws([rec0], "XSHCM")
        for bad_raw in (
            [],
            [123],
            [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": prizes, "x": 1}],
            [{"station_code": "XSHCM", "draw_date": "2026-10-19", "prizes_last2": prizes}],
            [{"station_code": "XSDT", "draw_date": "2026-10-19", "prizes_last2": ["01"]}],
            [
                {
                    "station_code": "XSDT",
                    "draw_date": "2026-10-19",
                    "prizes_last2": prizes,
                    "tens_counts": [0] * 10,
                }
            ],
            [
                {
                    "station_code": "XSDT",
                    "draw_date": "2026-10-19",
                    "prizes_last2": prizes,
                    "units_counts": [0] * 10,
                }
            ],
            [
                {
                    "station_code": "XSDT",
                    "draw_date": "2026-10-19",
                    "prizes_last2": prizes,
                    "draw_index": -1,
                }
            ],
            [
                {
                    "station_code": "XSDT",
                    "draw_date": "2026-10-19",
                    "prizes_last2": prizes,
                    "draw_index": 5,
                }
            ],
        ):
            with pytest.raises(DataIntegrityError):
                canonicalize_station_draws(bad_raw, "XSDT")  # type: ignore[arg-type]
