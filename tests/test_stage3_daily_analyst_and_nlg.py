"""Stage 3 TDD Suite (Tasks 5 & 6): Pre-Draw (< D) Daily Station Analyst & Deterministic NLG."""

from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import Any

import pytest

from xsmn_alpha.constants import (
    BE_PROB_SINGLE_BALL,
    SELECTIVE_ALPHA_JOINT_R1_MIN_PCT,
    STAGE3_TICKET_CONFIGS,
)
from xsmn_alpha.exceptions import (
    InsufficientSampleSizeError,
    TemporalLeakageError,
)
from xsmn_alpha.live.daily_analyst import (
    PreDrawCutoffGate,
    build_executive_nlg_vi,
    classify_daily_verdict_tier,
    enforce_pre_draw_date_cutoff,
    generate_daily_quant_report,
    rank_stations_for_day,
    score_station_for_date,
    select_optimal_ticket_config,
)
from xsmn_alpha.live.ledger import (
    build_capital_guidance,
    initialize_empty_ledger,
    record_pending_recommendation,
    settle_ledger_for_date,
)
from xsmn_alpha.live.multi_fetcher import save_station_raw_cache
from xsmn_alpha.live.registry import get_station_codes_for_weekday
from xsmn_alpha.schemas import (
    DailyQuantReportContract,
    ExecutiveNLGContract,
    StationDailyScorecard,
)


def _generate_biased_draws(
    station_code: str,
    num_draws: int = 80,
    end_date_before: str = "2026-10-24",
    *,
    tens_hot_ball: int = 2,
    units_hot_ball: int = 8,
    hot_count_per_draw: int = 5,
    trigger_recent_changepoint: bool = False,
) -> list[dict[str, Any]]:
    """Build deterministic synthetic 18-prize draw history strictly before target_date."""
    base_dt = datetime.date.fromisoformat(end_date_before)
    draws: list[dict[str, Any]] = []
    for idx in range(num_draws):
        draw_dt = base_dt - datetime.timedelta(days=(num_draws - 1 - idx) * 7)
        if trigger_recent_changepoint and idx >= num_draws - 3:
            # Sharp regime shift in the last 3 draws -> concentrates on ball 99
            prizes = ["99"] * 14 + ["00", "11", "22", "33"]
        else:
            hot_pair = f"{tens_hot_ball}{units_hot_ball}"
            alt_pair_1 = f"{tens_hot_ball}{(units_hot_ball + 1) % 10}"
            alt_pair_2 = f"{(tens_hot_ball + 1) % 10}{units_hot_ball}"
            prizes = [hot_pair] * hot_count_per_draw + [alt_pair_1, alt_pair_2]
            remaining = 18 - len(prizes)
            for k in range(remaining):
                d_tens = (idx + k) % 10
                d_units = (idx * 3 + k * 7) % 10
                prizes.append(f"{d_tens}{d_units}")
        draws.append(
            {
                "station_code": station_code,
                "draw_date": draw_dt.isoformat(),
                "prizes_last2": prizes,
            }
        )
    return draws


def _generate_uniform_white_noise_draws(
    station_code: str,
    num_draws: int = 80,
    end_date_before: str = "2026-10-24",
    *,
    seed: int = 7,
) -> list[dict[str, Any]]:
    """Build deterministic i.i.d. uniform white-noise draw history strictly before target_date."""
    import numpy as np

    rng = np.random.default_rng(seed)
    base_dt = datetime.date.fromisoformat(end_date_before)
    draws: list[dict[str, Any]] = []
    for idx in range(num_draws):
        draw_dt = base_dt - datetime.timedelta(days=(num_draws - 1 - idx) * 7)
        prizes = [f"{int(rng.integers(0, 10))}{int(rng.integers(0, 10))}" for _ in range(18)]
        draws.append(
            {
                "station_code": station_code,
                "draw_date": draw_dt.isoformat(),
                "prizes_last2": prizes,
            }
        )
    return draws


# ===========================================================================
# 1. Task 5: PreDrawCutoffGate (< D), Station Scoring & Verdict Tier
# ===========================================================================


class TestTask5PreDrawCutoffStationScoreAndVerdict:
    """Task 5 tests: PreDrawCutoffGate (< D), score_station_for_date, and verdict_tier."""

    def test_pre_draw_cutoff_gate_blocks_same_day_and_future_draws(self) -> None:
        target_date = "2026-10-26"
        valid_draws = _generate_biased_draws("XSHCM", num_draws=65, end_date_before="2026-10-24")

        # Valid history strictly < target_date passes PreDrawCutoffGate
        validated = enforce_pre_draw_date_cutoff(
            valid_draws, target_date=target_date, station_code="XSHCM"
        )
        assert len(validated) == 65
        assert all(r.draw_date < target_date for r in validated)
        PreDrawCutoffGate.enforce(valid_draws, target_date=target_date, station_code="XSHCM")
        PreDrawCutoffGate.validate(valid_draws, target_date=target_date, station_code="XSHCM")

        # Negative Mutation 1 (Manual check in todo.md Task 5):
        # Passing draw_date == target_date raises TemporalLeakageError immediately!
        same_day_draws = [
            *valid_draws,
            {
                "station_code": "XSHCM",
                "draw_date": target_date,
                "prizes_last2": valid_draws[-1]["prizes_last2"],
            },
        ]
        with pytest.raises(TemporalLeakageError):
            enforce_pre_draw_date_cutoff(
                same_day_draws, target_date=target_date, station_code="XSHCM"
            )
        with pytest.raises(TemporalLeakageError):
            PreDrawCutoffGate.enforce(same_day_draws, target_date=target_date, station_code="XSHCM")
        with pytest.raises(TemporalLeakageError):
            score_station_for_date(
                "XSHCM",
                target_date=target_date,
                history_draws=same_day_draws,
            )

        # Negative Mutation 2: Passing draw_date > target_date raises TemporalLeakageError!
        future_draws = [
            *valid_draws,
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-27",
                "prizes_last2": valid_draws[-1]["prizes_last2"],
            },
        ]
        with pytest.raises(TemporalLeakageError):
            PreDrawCutoffGate.enforce(future_draws, target_date=target_date, station_code="XSHCM")
        with pytest.raises(TemporalLeakageError):
            score_station_for_date(
                "XSHCM",
                target_date=target_date,
                history_draws=future_draws,
            )
        with pytest.raises(TemporalLeakageError):
            generate_daily_quant_report(
                target_date,
                station_histories={
                    "XSHCM": future_draws,
                    "XSDT": valid_draws,
                    "XSCM": valid_draws,
                    "XSTTH": valid_draws,
                    "XSPY": valid_draws,
                },
            )

        # Negative Mutation 3: Empty history or out-of-order dates -> TemporalLeakageError
        with pytest.raises(TemporalLeakageError):
            PreDrawCutoffGate.enforce([], target_date=target_date, station_code="XSHCM")

        reversed_draws = list(reversed(valid_draws))
        with pytest.raises(TemporalLeakageError):
            PreDrawCutoffGate.enforce(reversed_draws, target_date=target_date, station_code="XSHCM")

        # Negative Mutation 4: Insufficient sample size (< 60 draws) -> InsufficientSampleSizeError
        with pytest.raises(InsufficientSampleSizeError):
            score_station_for_date(
                "XSHCM",
                target_date=target_date,
                history_draws=valid_draws[:50],
            )

    def test_score_station_for_date_multi_window_calibrated_simplex_and_5_configs(self) -> None:
        target_date = "2026-10-26"
        history = _generate_biased_draws(
            "XSHCM",
            num_draws=75,
            end_date_before="2026-10-24",
            tens_hot_ball=2,
            units_hot_ball=8,
            hot_count_per_draw=6,
        )

        sc = score_station_for_date(
            "XSHCM",
            target_date=target_date,
            history_draws=history,
            null_sims=200,
            seed=42,
        )
        assert isinstance(sc, StationDailyScorecard)
        assert sc.station_code == "XSHCM"
        assert sc.station_name == "TP. Hồ Chí Minh"
        assert sc.region == "Miền Nam"
        assert sc.draw_time_ict == "16:15"
        assert sc.sample_draws_3y == 75
        assert sc.evaluated_oos_draws == 75 - 45
        assert sc.last_draw_date_before_d == "2026-10-24"
        assert sc.last_draw_date_before_d < target_date

        # Multi-window statistics W in {15, 30, 60}
        assert sc.chi2_15_tens >= 0.0
        assert sc.chi2_30_tens >= 0.0
        assert sc.chi2_60_tens >= 0.0
        assert sc.chi2_15_units >= 0.0
        assert sc.chi2_30_units >= 0.0
        assert sc.chi2_60_units >= 0.0
        assert sc.chi2_max_tens == pytest.approx(
            max(sc.chi2_15_tens, sc.chi2_30_tens, sc.chi2_60_tens), abs=1e-4
        )
        assert sc.chi2_max_units == pytest.approx(
            max(sc.chi2_15_units, sc.chi2_30_units, sc.chi2_60_units), abs=1e-4
        )
        assert sc.chi2_max_overall == pytest.approx(
            max(sc.chi2_max_tens, sc.chi2_max_units), abs=1e-4
        )
        assert 0.0 < sc.null_chi2_p90 <= sc.null_chi2_p95
        assert sc.bf10_max_tens > 0.0
        assert sc.bf10_max_units > 0.0
        assert sc.bf10_max_overall == pytest.approx(
            max(sc.bf10_max_tens, sc.bf10_max_units), abs=1e-4
        )
        assert 0.0 <= sc.normalized_entropy_tens <= 1.0
        assert 0.0 <= sc.normalized_entropy_units <= 1.0

        # BOCD run-length and changepoint warning
        assert sc.bocd_map_run_length == min(
            sc.bocd_map_run_length_tens, sc.bocd_map_run_length_units
        )
        assert sc.bocd_changepoint_warning is (sc.bocd_map_run_length <= 4)

        # 10-ball calibrated distributions summing to 1.0
        for dist_attr in (
            "p_ai_tens",
            "p_bocd_tens",
            "p_seq_tens",
            "p_ai_units",
            "p_bocd_units",
            "p_seq_units",
        ):
            dist = getattr(sc, dist_attr)
            assert len(dist) == 10
            assert math.isclose(sum(dist), 1.0, abs_tol=1e-6)
        assert set(sc.ranked_balls_tens) == set(range(10))
        assert set(sc.ranked_balls_units) == set(range(10))
        assert sc.ranked_balls_tens[0] == 2
        assert sc.ranked_balls_units[0] == 8

        # 10x10 joint_100_matrix summing to 1.0
        assert len(sc.joint_100_matrix) == 10
        assert all(len(row) == 10 for row in sc.joint_100_matrix)
        assert math.isclose(sum(sum(row) for row in sc.joint_100_matrix), 1.0, abs_tol=1e-6)
        for a in range(10):
            for b in range(10):
                assert sc.joint_100_matrix[a][b] == pytest.approx(
                    sc.p_ai_tens[a] * sc.p_ai_units[b], abs=1e-6
                )

        # OOS Rank-1 hit rates & JointR1%
        assert sc.oos_rank1_freq_tens_pct > 15.0
        assert sc.oos_rank1_freq_units_pct > 15.0
        expected_joint_r1 = (sc.oos_rank1_freq_tens_pct * sc.oos_rank1_freq_units_pct) / 100.0
        assert sc.joint_r1_pct == pytest.approx(expected_joint_r1, abs=1e-2)

        # All 5 Stage 3 ticket configs evaluated
        assert set(sc.ticket_configs.keys()) == set(STAGE3_TICKET_CONFIGS)
        for cfg_id in STAGE3_TICKET_CONFIGS:
            rec_cfg = sc.ticket_configs[cfg_id]
            assert rec_cfg.config_id == cfg_id
            assert len(rec_cfg.selected_numbers) == rec_cfg.num_numbers
            assert 0.0 < rec_cfg.single_prize_hit_prob < 1.0
            assert rec_cfg.hit_at_least_1_in_18_prob == pytest.approx(
                1.0 - (1.0 - rec_cfg.single_prize_hit_prob) ** 18, abs=1e-6
            )
            assert rec_cfg.is_recommended_primary is (cfg_id == sc.recommended_config_id)

        # Both cages strongly exceed 10.6904% -> selects "2x2"
        assert sc.recommended_config_id == "2x2"
        assert sc.recommended_numbers == sc.ticket_configs["2x2"].selected_numbers
        assert "28" in sc.recommended_numbers

        # Station Alpha Score formula check
        best_4cfg_roi = max(
            sc.ticket_configs[cid].oos_roi_3y_pct for cid in ("2x2", "1x4", "4x1", "3x3")
        )
        assert sc.best_oos_roi_pct == pytest.approx(best_4cfg_roi, abs=1e-2)
        expected_alpha_score = (sc.joint_r1_pct - 1.0) * 100.0 + 0.25 * sc.best_oos_roi_pct
        assert sc.station_alpha_score == pytest.approx(expected_alpha_score, abs=1e-2)
        assert sc.passes_selective_alpha is True
        assert sc.strong_convergence is True

    def test_score_optimal_ticket_config_selection_rules_2x2_1x4_4x1(self) -> None:
        be_pct = BE_PROB_SINGLE_BALL * 100.0  # ~10.6904%

        # Rule 1: Both tens and units Rank-1 >= 10.6904% -> "2x2"
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=be_pct + 0.1,
                units_r1_pct=be_pct + 0.2,
                roi_2x2=4.0,
                roi_1x4=9.0,
                roi_4x1=8.0,
            )
            == "2x2"
        )

        # Rule 2: tens < 10.6904%, units >= 10.50%, and roi_1x4 > max(roi_2x2, roi_4x1) -> "1x4"
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.30,
                units_r1_pct=10.80,
                roi_2x2=3.5,
                roi_1x4=7.2,
                roi_4x1=5.0,
            )
            == "1x4"
        )

        # Rule 3: units >= 10.6904% and roi_4x1 > max(roi_2x2, roi_1x4) + 1.5 -> "4x1"
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.40,
                units_r1_pct=11.10,
                roi_2x2=4.0,
                roi_1x4=5.0,
                roi_4x1=7.0,  # > 5.0 + 1.5
            )
            == "4x1"
        )

        # Rule 4: Fallback -> highest ROI between "2x2" and "1x4"
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.20,
                units_r1_pct=10.30,
                roi_2x2=5.5,
                roi_1x4=3.2,
                roi_4x1=6.0,
            )
            == "2x2"
        )
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.20,
                units_r1_pct=10.30,
                roi_2x2=1.5,
                roi_1x4=4.2,
                roi_4x1=6.0,
            )
            == "1x4"
        )

    def test_verdict_tier_classification_and_multi_station_ranking_score(self) -> None:
        # 1. SKIP_NO_EDGE when joint_r1_pct < 1.105 or best_roi_pct <= 0.0
        assert classify_daily_verdict_tier(1.095, 12.0) == "SKIP_NO_EDGE"
        assert classify_daily_verdict_tier(1.180, 0.0) == "SKIP_NO_EDGE"
        assert classify_daily_verdict_tier(1.180, -2.5) == "SKIP_NO_EDGE"

        # 2. PLAY_PEAK when passes_selective_alpha and (joint_r1 >= 1.150 or best_roi >= 8.0)
        assert classify_daily_verdict_tier(1.150, 2.0) == "PLAY_PEAK"
        assert classify_daily_verdict_tier(1.110, 8.0) == "PLAY_PEAK"
        assert classify_daily_verdict_tier(1.185, 11.4) == "PLAY_PEAK"

        # 3. PLAY_STANDARD when passes_selective_alpha and (best_roi >= 3.0 or joint_r1 >= 1.125)
        assert classify_daily_verdict_tier(1.110, 3.0) == "PLAY_STANDARD"
        assert classify_daily_verdict_tier(1.125, 1.2) == "PLAY_STANDARD"
        assert classify_daily_verdict_tier(1.140, 6.5) == "PLAY_STANDARD"

        # 4. PLAY_CAUTIOUS when 0.0 < best_roi < 3.0 and 1.105 <= joint_r1 < 1.125
        assert classify_daily_verdict_tier(1.105, 0.5) == "PLAY_CAUTIOUS"
        assert classify_daily_verdict_tier(1.120, 2.9) == "PLAY_CAUTIOUS"

        # 5. Multi-station deterministic ranking with tie-break by station_code ascending
        base_draws = _generate_biased_draws("XSHCM", num_draws=65, end_date_before="2026-10-24")
        sc_base = score_station_for_date(
            "XSHCM", target_date="2026-10-26", history_draws=base_draws, null_sims=100
        )

        sc_dt = sc_base.model_copy(
            update={
                "station_code": "XSDT",
                "station_name": "Đồng Tháp",
                "station_alpha_score": 15.0,
                "joint_r1_pct": 1.160,
                "best_oos_roi_pct": 9.2,
                "passes_selective_alpha": True,
                "strong_convergence": True,
            }
        )
        sc_cm = sc_base.model_copy(
            update={
                "station_code": "XSCM",
                "station_name": "Cà Mau",
                "station_alpha_score": 15.0,  # Exact tie with XSDT -> XSCM wins tie-break!
                "joint_r1_pct": 1.155,
                "best_oos_roi_pct": 8.5,
                "passes_selective_alpha": True,
                "strong_convergence": True,
            }
        )
        sc_py = sc_base.model_copy(
            update={
                "station_code": "XSPY",
                "station_name": "Phú Yên",
                "region": "Miền Trung",
                "draw_time_ict": "17:15",
                "station_alpha_score": -3.5,
                "joint_r1_pct": 0.980,
                "best_oos_roi_pct": -6.0,
                "passes_selective_alpha": False,
                "strong_convergence": False,
            }
        )

        ranked, primary, secondary, skipped, tier = rank_stations_for_day([sc_dt, sc_py, sc_cm])
        assert [s.station_code for s in ranked] == ["XSCM", "XSDT", "XSPY"]
        assert [s.rank_in_day for s in ranked] == [1, 2, 3]
        assert primary.station_code == "XSCM"
        assert secondary is not None and secondary.station_code == "XSDT"
        assert [s.station_code for s in skipped] == ["XSPY"]
        assert tier == "PLAY_PEAK"


# ===========================================================================
# 2. Task 6: Deterministic Quantitative NLG & Reproducibility
# ===========================================================================


class TestTask6DeterministicQuantitativeNLGAndReproducibility:
    """Task 6 tests: Pure deterministic Vietnamese NLG answering all 4 core questions."""

    def test_deterministic_nlg_four_core_questions_and_1to1_metric_citations(self) -> None:
        target_date = "2026-10-26"
        draws_hcm = _generate_biased_draws(
            "XSHCM", num_draws=70, end_date_before="2026-10-24", tens_hot_ball=2, units_hot_ball=8
        )
        draws_dt = _generate_biased_draws(
            "XSDT",
            num_draws=70,
            end_date_before="2026-10-19",
            tens_hot_ball=1,
            units_hot_ball=3,
            hot_count_per_draw=4,
        )
        draws_noise = _generate_uniform_white_noise_draws(
            "XSCM", num_draws=70, end_date_before="2026-10-19"
        )

        sc_hcm = score_station_for_date(
            "XSHCM", target_date=target_date, history_draws=draws_hcm, null_sims=100
        )
        sc_dt = score_station_for_date(
            "XSDT", target_date=target_date, history_draws=draws_dt, null_sims=100
        )
        sc_cm = score_station_for_date(
            "XSCM", target_date=target_date, history_draws=draws_noise, null_sims=100
        )

        ranked, primary, secondary, skipped, verdict_tier = rank_stations_for_day(
            [sc_hcm, sc_dt, sc_cm]
        )
        assert verdict_tier in ("PLAY_PEAK", "PLAY_STANDARD")

        cap_guidance = build_capital_guidance(
            verdict_tier,
            current_bankroll_vnd=1_500_000,
        )
        nlg = build_executive_nlg_vi(
            report_date=target_date,
            weekday_vn="Thứ 2",
            verdict_tier=verdict_tier,
            primary_station=primary,
            secondary_station=secondary,
            skipped_stations=skipped,
            all_today_stations=ranked,
            capital_guidance=cap_guidance,
            yesterday_settlement=None,
        )
        assert isinstance(nlg, ExecutiveNLGContract)

        # Verify Q1 cites exact scorecard metrics 1:1
        q1 = nlg.q1_should_play_and_why
        assert f"{primary.joint_r1_pct:.3f}%" in q1
        assert f"{SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%" in q1
        assert f"{primary.oos_rank1_freq_tens_pct:.2f}%" in q1
        assert f"{primary.oos_rank1_freq_units_pct:.2f}%" in q1
        assert "10.69%" in q1
        assert f"{primary.chi2_max_overall:.2f}" in q1
        assert f"{primary.null_chi2_p90:.2f}" in q1
        assert f"{primary.null_chi2_p95:.2f}" in q1
        assert f"{primary.bf10_max_overall:.2f}" in q1 or f"{primary.bf10_max_overall:.3f}" in q1
        assert str(primary.bocd_map_run_length) in q1
        assert f"{primary.best_oos_roi_pct:+.2f}%" in q1

        # Verify Q2 cites primary station, region, draw_time_ict, alpha score & skipped stations
        q2 = nlg.q2_which_station_and_region
        assert primary.station_name in q2
        assert primary.station_code in q2
        assert primary.region in q2
        assert primary.draw_time_ict in q2
        assert f"{primary.station_alpha_score:+.2f}" in q2
        if secondary is not None:
            assert secondary.station_code in q2
        for sk in skipped:
            assert sk.station_code in q2

        # Verify Q3 cites recommended_config_id, recommended_numbers, and top cage balls
        q3 = nlg.q3_which_numbers_and_config
        assert primary.recommended_config_id in q3
        for num in primary.recommended_numbers:
            assert num in q3
        assert str(primary.ranked_balls_tens[0]) in q3
        assert str(primary.ranked_balls_units[0]) in q3

        # Verify Q4 cites House-Money multiplier and VND amounts
        q4 = nlg.q4_how_to_allocate_capital
        assert f"{cap_guidance.recommended_multiplier:.2f}x" in q4
        assert f"{cap_guidance.benchmark_bet_vnd:,}" in q4
        assert f"{cap_guidance.benchmark_bankroll_vnd:,}" in q4
        assert f"{cap_guidance.house_money_surplus_vnd:,}" in q4
        assert "500k" in q4
        assert "1 Triệu" in q4
        assert "2 Triệu" in q4
        assert "5 Triệu" in q4

    def test_bocd_changepoint_warning_explicitly_mentioned_in_nlg_and_scorecard(self) -> None:
        target_date = "2026-10-26"
        cp_draws = _generate_biased_draws(
            "XSHCM",
            num_draws=70,
            end_date_before="2026-10-24",
            tens_hot_ball=2,
            units_hot_ball=8,
            hot_count_per_draw=6,
            trigger_recent_changepoint=True,
        )
        sc_cp = score_station_for_date(
            "XSHCM",
            target_date=target_date,
            history_draws=cp_draws,
            null_sims=100,
        )
        assert sc_cp.bocd_map_run_length <= 4
        assert sc_cp.bocd_changepoint_warning is True
        assert "BOCD" in sc_cp.rationale_vi
        assert str(sc_cp.bocd_map_run_length) in sc_cp.rationale_vi

        ranked, primary, secondary, skipped, verdict_tier = rank_stations_for_day([sc_cp])
        cap_guidance = build_capital_guidance(verdict_tier, current_bankroll_vnd=1_200_000)
        nlg = build_executive_nlg_vi(
            report_date=target_date,
            weekday_vn="Thứ 2",
            verdict_tier=verdict_tier,
            primary_station=primary,
            secondary_station=secondary,
            skipped_stations=skipped,
            all_today_stations=ranked,
            capital_guidance=cap_guidance,
        )
        assert "BOCD" in nlg.q1_should_play_and_why
        assert (
            "thay bóng" in nlg.q1_should_play_and_why.lower()
            or "đổi chế độ" in nlg.q1_should_play_and_why.lower()
        )

    def test_skip_no_edge_day_nlg_explains_white_noise_and_0x_preservation(
        self, tmp_path: Path
    ) -> None:
        target_date = "2026-10-26"  # Monday: XSHCM, XSDT, XSCM, XSTTH, XSPY
        raw_dir = tmp_path / "raw_all"
        monday_codes = get_station_codes_for_weekday(0)
        for code in monday_codes:
            noise_draws = _generate_uniform_white_noise_draws(
                code, num_draws=65, end_date_before="2026-10-24"
            )
            save_station_raw_cache(code, noise_draws, raw_dir=raw_dir)

        report = generate_daily_quant_report(
            target_date,
            raw_dir=raw_dir,
            null_sims=100,
        )
        assert isinstance(report, DailyQuantReportContract)
        assert report.verdict_tier == "SKIP_NO_EDGE"
        assert report.should_play_today is False
        assert report.secondary_station is None
        assert len(report.all_today_stations) == 5
        assert len(report.skipped_stations) == 5
        assert report.capital_guidance.recommended_multiplier == 0.0
        assert report.capital_guidance.benchmark_bet_vnd == 0
        assert all(r.total_daily_cost_vnd == 0 for r in report.capital_guidance.sample_allocations)

        q1 = report.executive_nlg_vi.q1_should_play_and_why
        q4 = report.executive_nlg_vi.q4_how_to_allocate_capital
        assert "NGHỈ" in q1.upper()
        assert "nhiễu trắng" in q1.lower() or "chưa đạt" in q1.lower()
        assert "1.105%" in q1
        assert "0.00x" in q4 or "0.0x" in q4
        assert "0 VNĐ" in q4

    def test_deterministic_reproducibility_of_generate_daily_quant_report(
        self, tmp_path: Path
    ) -> None:
        target_date = "2026-10-26"
        raw_dir = tmp_path / "raw_all"
        ledger_path = tmp_path / "benchmark_ledger.json"

        monday_codes = get_station_codes_for_weekday(0)
        for idx, code in enumerate(monday_codes):
            if idx == 0:
                draws = _generate_biased_draws(
                    code, num_draws=68, end_date_before="2026-10-24", hot_count_per_draw=6
                )
            else:
                draws = _generate_uniform_white_noise_draws(
                    code, num_draws=68, end_date_before="2026-10-19"
                )
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        # Initialize ledger with a settled entry on 2026-10-25 (yesterday)
        state = initialize_empty_ledger(updated_at="2026-10-25T05:00:00+07:00")
        state = record_pending_recommendation(
            state,
            draw_date="2026-10-25",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSDL",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            updated_at="2026-10-25T05:00:00+07:00",
        )
        prizes_18 = ["21"] + ["99"] * 17
        state = settle_ledger_for_date(
            state,
            draw_date="2026-10-25",
            actual_prizes_last2=prizes_18,
            ledger_path=ledger_path,
            updated_at="2026-10-25T16:45:00+07:00",
        )

        # Run generate_daily_quant_report twice on identical inputs
        report_run_1 = generate_daily_quant_report(
            target_date,
            raw_dir=raw_dir,
            ledger_state_or_path=ledger_path,
            null_sims=100,
        )
        report_run_2 = generate_daily_quant_report(
            target_date,
            raw_dir=raw_dir,
            ledger_state_or_path=ledger_path,
            null_sims=100,
        )

        assert report_run_1.model_dump() == report_run_2.model_dump()
        assert report_run_1.executive_nlg_vi == report_run_2.executive_nlg_vi
        assert (
            report_run_1.executive_nlg_vi.q1_should_play_and_why
            == report_run_2.executive_nlg_vi.q1_should_play_and_why
        )
        assert (
            report_run_1.executive_nlg_vi.q2_which_station_and_region
            == report_run_2.executive_nlg_vi.q2_which_station_and_region
        )
        assert (
            report_run_1.executive_nlg_vi.q3_which_numbers_and_config
            == report_run_2.executive_nlg_vi.q3_which_numbers_and_config
        )
        assert (
            report_run_1.executive_nlg_vi.q4_how_to_allocate_capital
            == report_run_2.executive_nlg_vi.q4_how_to_allocate_capital
        )
        assert report_run_1.yesterday_settlement is not None
        assert report_run_1.yesterday_settlement.draw_date == "2026-10-25"
        assert "2026-10-25" in report_run_1.yesterday_summary_vi

    def test_adversarial_b03_select_optimal_ticket_config_rejects_negative_roi_2x2_and_checks_4x1(
        self,
    ) -> None:
        be_pct = BE_PROB_SINGLE_BALL * 100.0  # ~10.6904%

        # B-03a: Both cages >= 10.6904%, but 2x2 has negative OOS ROI (-6.94%) while 1x4 has +1.82%
        # (Exact live XSPY on 2026-10-26 scenario) -> must pick "1x4", NOT negative-ROI "2x2"!
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.76,
                units_r1_pct=11.26,
                roi_2x2=-6.94,
                roi_1x4=+1.82,
                roi_4x1=-12.69,
            )
            == "1x4"
        )

        # B-03b: Both cages >= 10.6904%, 2x2/1x4 negative ROI, 4x1 positive ROI -> "4x1"
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=be_pct + 0.1,
                units_r1_pct=be_pct + 0.2,
                roi_2x2=-4.0,
                roi_1x4=-2.0,
                roi_4x1=+6.5,
            )
            == "4x1"
        )

        # B-03c: Fallback with units >= 10.50% (below 10.6904%) where 4x1 strongly dominates
        assert (
            select_optimal_ticket_config(
                tens_r1_pct=10.40,
                units_r1_pct=10.60,
                roi_2x2=-8.0,
                roi_1x4=-5.0,
                roi_4x1=+12.0,
            )
            == "4x1"
        )

    def test_adversarial_b06_b07_stale_settlement_label_no_von_von_weighted_hybrid_and_audit(
        self, tmp_path: Path
    ) -> None:
        from xsmn_alpha.exceptions import CalibrationIntegrityError, DataIntegrityError

        target_date = "2026-10-26"
        raw_dir = tmp_path / "raw_all"
        monday_codes = get_station_codes_for_weekday(0)
        for idx, code in enumerate(monday_codes):
            draws = (
                _generate_biased_draws(
                    code, num_draws=68, end_date_before="2026-10-24", hot_count_per_draw=6
                )
                if idx == 0
                else _generate_uniform_white_noise_draws(
                    code, num_draws=68, end_date_before="2026-10-19"
                )
            )
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        # Seed ledger with only a stale entry on 2026-01-01 (not yesterday 2026-10-25!)
        state = initialize_empty_ledger(updated_at="2026-01-01T05:00:00+07:00")
        state = record_pending_recommendation(
            state,
            draw_date="2026-01-01",
            verdict_tier="SKIP_NO_EDGE",
            chosen_station_code="XSQB",
            chosen_config_id="2x2",
            selected_numbers=["01", "02", "11", "12"],
        )

        rep = generate_daily_quant_report(
            target_date,
            raw_dir=raw_dir,
            ledger_state_or_path=state,
            null_sims=50,
        )

        # B-06: Stale entry from 2026-01-01 must be labeled "kỳ gần nhất", NOT "kỳ hôm qua"
        assert "2026-01-01" in rep.yesterday_summary_vi
        assert "kỳ gần nhất" in rep.yesterday_summary_vi
        assert "kỳ hôm qua" not in rep.yesterday_summary_vi

        # B-07: Q4 NLG must never duplicate "Vốn Vốn" and must mention 1-hit payout
        q4 = rep.executive_nlg_vi.q4_how_to_allocate_capital
        assert "Vốn Vốn" not in q4
        assert "Vốn 500k" in q4
        assert "trúng 1 nháy thu" in q4

        # B-07: Weighted single_prize_hit_prob for core_2x2_sat_3x3 < unweighted 3x3
        p_sc = rep.primary_station
        prob_2x2 = p_sc.ticket_configs["2x2"].single_prize_hit_prob
        prob_3x3 = p_sc.ticket_configs["3x3"].single_prize_hit_prob
        prob_hybrid = p_sc.ticket_configs["core_2x2_sat_3x3"].single_prize_hit_prob
        expected_hybrid = round(prob_2x2 + 0.5 * (prob_3x3 - prob_2x2), 6)
        assert prob_hybrid == pytest.approx(expected_hybrid, abs=1e-5)
        assert prob_2x2 < prob_hybrid < prob_3x3

        # B-07: Default pipeline_audit counts actual synced files in raw_dir (5, not fabricated 35)
        assert rep.data_pipeline_audit.total_stations_35 == 35
        assert rep.data_pipeline_audit.stations_synced_ok == 5

        # B-06: Schema contract gates block forged PLAY_PEAK with passes_selective_alpha=False
        failed_primary = p_sc.model_copy(
            update={
                "passes_selective_alpha": False,
                "strong_convergence": False,
                "joint_r1_pct": 0.850,
                "best_oos_roi_pct": -15.0,
            }
        )
        with pytest.raises(DataIntegrityError):
            DailyQuantReportContract(
                report_date=rep.report_date,
                weekday_vn=rep.weekday_vn,
                generated_at_ict=rep.generated_at_ict,
                data_pipeline_audit=rep.data_pipeline_audit,
                yesterday_settlement=rep.yesterday_settlement,
                yesterday_summary_vi=rep.yesterday_summary_vi,
                verdict_tier="PLAY_PEAK",
                should_play_today=True,
                primary_station=failed_primary,
                secondary_station=None,
                skipped_stations=[failed_primary],
                all_today_stations=[failed_primary],
                capital_guidance=rep.capital_guidance,
                executive_nlg_vi=rep.executive_nlg_vi,
                telegram_message_html=rep.telegram_message_html,
            )

        # B-06: StationDailyScorecard blocks inverted ranked_balls_tens and mismatched numbers
        with pytest.raises(CalibrationIntegrityError):
            StationDailyScorecard.model_validate(
                {
                    **p_sc.model_dump(),
                    "ranked_balls_tens": list(reversed(p_sc.ranked_balls_tens)),
                }
            )
        with pytest.raises(DataIntegrityError):
            StationDailyScorecard.model_validate(
                {
                    **p_sc.model_dump(),
                    "recommended_numbers": ["99", "98", "97", "96"],
                }
            )
