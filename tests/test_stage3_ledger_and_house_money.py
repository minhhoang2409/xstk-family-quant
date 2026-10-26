"""Stage 3 TDD Suite (Task 4): Reference Benchmark Ledger (1M VND) & CPPI / House-Money Engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xsmn_alpha.constants import (
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_PAYOUT_PER_HIT_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    PRIZES_PER_DRAW,
    SAMPLE_CAPITAL_TIERS_VND,
)
from xsmn_alpha.exceptions import CapitalDisciplineError, DataIntegrityError
from xsmn_alpha.live.ledger import (
    DEFAULT_LEDGER_PATH,
    PRIZE_LABELS_18,
    build_capital_guidance,
    build_sample_capital_allocations,
    compute_house_money_multiplier,
    compute_ledger_sha256,
    compute_multiplier_for_verdict_tier,
    evaluate_18_prizes_hits,
    initialize_empty_ledger,
    load_benchmark_ledger,
    recalculate_ledger_state,
    record_pending_recommendation,
    save_benchmark_ledger,
    settle_entry_with_prizes,
    settle_ledger_for_date,
    verify_ledger_integrity,
)
from xsmn_alpha.live.multi_fetcher import save_station_raw_cache
from xsmn_alpha.schemas import BenchmarkLedgerEntry


def _sample_18_prizes_with_2_hits() -> list[str]:
    """Return 18 valid 2-digit prizes where '21' hits Giải Tám (0) and '28' hits Giải ĐB (17)."""
    return [
        "21",  # 0: Giải Tám (HIT #1)
        "19",  # 1: Giải Bảy
        "73",  # 2: Giải Sáu (1)
        "08",  # 3: Giải Sáu (2)
        "83",  # 4: Giải Sáu (3)
        "39",  # 5: Giải Năm
        "88",  # 6: Giải Tư (1)
        "14",  # 7: Giải Tư (2)
        "57",  # 8: Giải Tư (3)
        "81",  # 9: Giải Tư (4)
        "44",  # 10: Giải Tư (5)
        "90",  # 11: Giải Tư (6)
        "38",  # 12: Giải Tư (7)
        "84",  # 13: Giải Ba (1)
        "61",  # 14: Giải Ba (2)
        "03",  # 15: Giải Nhì
        "78",  # 16: Giải Nhất
        "28",  # 17: Giải Đặc Biệt (HIT #2)
    ]


def _sample_18_prizes_zero_hits() -> list[str]:
    """Return 18 valid 2-digit prizes with 0 hits for ['21', '22', '23', '28']."""
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
        "44",
        "90",
        "38",
        "84",
        "61",
        "03",
        "78",
        "83",
    ]


class TestHouseMoneyMultiplierAndCapitalGuidance:
    """Verify CPPI / House-Money sizing rules, Gate 5 bounds, and sample VND allocations."""

    def test_compute_house_money_multiplier_all_tiers_and_buffers(self) -> None:
        # 1. Fails selective alpha filter -> 0.0x, 0 VND even with huge surplus
        assert compute_house_money_multiplier(
            passes_selective_alpha=False,
            strong_convergence=True,
            current_bankroll_vnd=2_500_000,
        ) == (0.0, 0)

        # 2. Passes selective alpha, but house_money < 144,000 VND -> 1.0x (72,000 VND)
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=1_000_000,
        ) == (1.0, 72_000)
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=1_143_999,
        ) == (1.0, 72_000)

        # 3. Exactly at 2-day buffer (1,144,000 VND -> house_money = 144,000 VND):
        # Standard convergence -> 1.25x (90,000 VND, extra = 18,000 <= 72,000)
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=False,
            current_bankroll_vnd=1_144_000,
        ) == (1.25, 90_000)

        # Peak convergence -> 1.50x (108,000 VND, extra = 36,000 <= 72,000)
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=1_144_000,
        ) == (1.50, 108_000)

        # Gate 5 fallback to 1.0x when verdict_tier is passed directly
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=1_500_000,
            verdict_tier="PLAY_CAUTIOUS",
        ) == (1.0, 72_000)

        # Gate 5 fallback when current_bankroll_vnd - total_cost_vnd < initial_bankroll_vnd
        # (e.g. if HOUSE_MONEY_MIN_BUFFER_DAYS=1 or custom base cost where total_cost > surplus)
        assert compute_house_money_multiplier(
            passes_selective_alpha=True,
            strong_convergence=True,
            current_bankroll_vnd=1_100_000,
            initial_bankroll_vnd=1_000_000,
            base_daily_cost_vnd=45_000,  # buffer=90k <= 100k, 1.5x=67.5k -> 1_100k - 67.5k >= 1M
        ) == (1.50, 67_500)

    def test_compute_multiplier_for_verdict_tier(self) -> None:
        # SKIP_NO_EDGE -> always (0.0, 0)
        assert compute_multiplier_for_verdict_tier(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=2_000_000,
        ) == (0.0, 0)

        # PLAY_CAUTIOUS -> always (1.0, 72_000) even when house_money >= 144,000
        assert compute_multiplier_for_verdict_tier(
            "PLAY_CAUTIOUS",
            current_bankroll_vnd=1_000_000,
        ) == (1.0, 72_000)
        assert compute_multiplier_for_verdict_tier(
            "PLAY_CAUTIOUS",
            current_bankroll_vnd=2_500_000,
        ) == (1.0, 72_000)

        # PLAY_STANDARD -> (1.0, 72_000) when surplus < 144k, (1.25, 90_000) when >= 144k
        assert compute_multiplier_for_verdict_tier(
            "PLAY_STANDARD",
            current_bankroll_vnd=1_100_000,
        ) == (1.0, 72_000)
        assert compute_multiplier_for_verdict_tier(
            "PLAY_STANDARD",
            current_bankroll_vnd=1_200_000,
        ) == (1.25, 90_000)

        # PLAY_PEAK -> (1.0, 72_000) when surplus < 144k, (1.50, 108_000) when >= 144k
        assert compute_multiplier_for_verdict_tier(
            "PLAY_PEAK",
            current_bankroll_vnd=1_100_000,
        ) == (1.0, 72_000)
        assert compute_multiplier_for_verdict_tier(
            "PLAY_PEAK",
            current_bankroll_vnd=1_200_000,
        ) == (1.50, 108_000)

    def test_build_sample_capital_allocations_and_guidance(self) -> None:
        assert SAMPLE_CAPITAL_TIERS_VND == (500_000, 1_000_000, 2_000_000, 5_000_000)

        # 1.0x allocations
        rows_1x = build_sample_capital_allocations(1.0)
        assert len(rows_1x) == 4
        by_tier_1x = {r.capital_tier_vnd: r for r in rows_1x}

        assert by_tier_1x[500_000].stake_per_number_vnd == 9_000
        assert by_tier_1x[500_000].total_daily_cost_vnd == 36_000
        assert by_tier_1x[500_000].payout_per_hit_vnd == 43_750
        assert by_tier_1x[500_000].net_profit_1hit_vnd == 7_750
        assert by_tier_1x[500_000].net_profit_2hits_vnd == 51_500

        assert by_tier_1x[1_000_000].stake_per_number_vnd == BENCHMARK_STAKE_PER_NUMBER_VND
        assert by_tier_1x[1_000_000].total_daily_cost_vnd == BENCHMARK_BASE_DAILY_COST_4NUM_VND
        assert by_tier_1x[1_000_000].payout_per_hit_vnd == BENCHMARK_PAYOUT_PER_HIT_VND
        assert by_tier_1x[1_000_000].net_profit_1hit_vnd == 15_500
        assert by_tier_1x[1_000_000].net_profit_2hits_vnd == 103_000

        assert by_tier_1x[2_000_000].total_daily_cost_vnd == 144_000
        assert by_tier_1x[5_000_000].total_daily_cost_vnd == 360_000

        # 1.5x allocations via build_capital_guidance
        guidance_peak = build_capital_guidance(
            "PLAY_PEAK",
            current_bankroll_vnd=1_500_000,
        )
        assert guidance_peak.should_play_today is True
        assert guidance_peak.recommended_multiplier == pytest.approx(1.5)
        assert guidance_peak.benchmark_bet_vnd == 108_000
        assert guidance_peak.stake_per_number_vnd == 27_000
        assert guidance_peak.payout_per_hit_vnd == 131_250
        assert guidance_peak.house_money_surplus_vnd == 500_000
        assert len(guidance_peak.sizing_rationale_vi) > 10

        # 0.0x allocations via build_capital_guidance on SKIP_NO_EDGE
        guidance_skip = build_capital_guidance(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=1_500_000,
        )
        assert guidance_skip.should_play_today is False
        assert guidance_skip.recommended_multiplier == 0.0
        assert guidance_skip.benchmark_bet_vnd == 0
        assert all(r.total_daily_cost_vnd == 0 for r in guidance_skip.sample_allocations)
        assert all(r.stake_per_number_vnd == 0 for r in guidance_skip.sample_allocations)

        # PLAY_CAUTIOUS and PLAY_STANDARD (no buffer) rationales + custom tier labels
        guidance_cautious = build_capital_guidance("PLAY_CAUTIOUS", current_bankroll_vnd=1_500_000)
        assert guidance_cautious.recommended_multiplier == 1.0
        assert "PLAY_CAUTIOUS" in guidance_cautious.sizing_rationale_vi

        guidance_std_1x = build_capital_guidance("PLAY_STANDARD", current_bankroll_vnd=1_050_000)
        assert guidance_std_1x.recommended_multiplier == 1.0
        assert "CPPI" in guidance_std_1x.sizing_rationale_vi

        custom_rows = build_sample_capital_allocations(1.0, tiers_vnd=(300_000, 3_000_000, 750_500))
        assert [r.tier_label for r in custom_rows] == ["Vốn 300k", "Vốn 3 Triệu", "Vốn 750,500đ"]

    def test_negative_mutations_on_house_money_multiplier(self) -> None:
        # Negative or zero bankroll / base cost -> CapitalDisciplineError
        with pytest.raises(CapitalDisciplineError):
            compute_house_money_multiplier(
                passes_selective_alpha=True,
                strong_convergence=False,
                current_bankroll_vnd=0,
            )
        with pytest.raises(CapitalDisciplineError):
            compute_house_money_multiplier(
                passes_selective_alpha=True,
                strong_convergence=False,
                current_bankroll_vnd=-100_000,
            )
        with pytest.raises(CapitalDisciplineError):
            compute_house_money_multiplier(
                passes_selective_alpha=True,
                strong_convergence=False,
                current_bankroll_vnd=1_000_000,
                initial_bankroll_vnd=0,
            )
        with pytest.raises(CapitalDisciplineError):
            compute_house_money_multiplier(
                passes_selective_alpha=True,
                strong_convergence=False,
                current_bankroll_vnd=1_000_000,
                base_daily_cost_vnd=0,
            )
        with pytest.raises(CapitalDisciplineError):
            compute_multiplier_for_verdict_tier(
                "INVALID_TIER",  # type: ignore[arg-type]
                current_bankroll_vnd=1_000_000,
            )


class TestPrizeLabelsAndHitEvaluation:
    """Verify 18-prize labels mapping and hit evaluation across all 18 prizes."""

    def test_18_prize_labels_exact_order(self) -> None:
        assert len(PRIZE_LABELS_18) == PRIZES_PER_DRAW == 18
        assert PRIZE_LABELS_18[0] == "Giải Tám"
        assert PRIZE_LABELS_18[1] == "Giải Bảy"
        assert PRIZE_LABELS_18[2:5] == ("Giải Sáu (1)", "Giải Sáu (2)", "Giải Sáu (3)")
        assert PRIZE_LABELS_18[5] == "Giải Năm"
        assert PRIZE_LABELS_18[6:13] == (
            "Giải Tư (1)",
            "Giải Tư (2)",
            "Giải Tư (3)",
            "Giải Tư (4)",
            "Giải Tư (5)",
            "Giải Tư (6)",
            "Giải Tư (7)",
        )
        assert PRIZE_LABELS_18[13:15] == ("Giải Ba (1)", "Giải Ba (2)")
        assert PRIZE_LABELS_18[15] == "Giải Nhì"
        assert PRIZE_LABELS_18[16] == "Giải Nhất"
        assert PRIZE_LABELS_18[17] == "Giải Đặc Biệt"

    def test_evaluate_18_prizes_hits_pass_and_negative_mutations(self) -> None:
        prizes = _sample_18_prizes_with_2_hits()
        hit_k, details = evaluate_18_prizes_hits(["21", "22", "23", "28"], prizes)
        assert hit_k == 2
        assert len(details) == 2
        assert details[0].prize_index == 0
        assert details[0].prize_label == "Giải Tám"
        assert details[0].number == "21"
        assert details[1].prize_index == 17
        assert details[1].prize_label == "Giải Đặc Biệt"
        assert details[1].number == "28"

        # Multi-hit of the same number in 2 different prizes (e.g. '83' at index 4 and 17)
        prizes_zero = _sample_18_prizes_zero_hits()
        hit_k_dup, details_dup = evaluate_18_prizes_hits(["83", "01", "02", "04"], prizes_zero)
        assert hit_k_dup == 2
        assert [d.prize_index for d in details_dup] == [4, 17]
        assert [d.prize_label for d in details_dup] == ["Giải Sáu (3)", "Giải Đặc Biệt"]

        # Negative Mutations: fewer or more than 18 prizes -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            evaluate_18_prizes_hits(["21", "22", "23", "28"], prizes[:17])
        with pytest.raises(DataIntegrityError):
            evaluate_18_prizes_hits(["21", "22", "23", "28"], [*prizes, "99"])


class TestBenchmarkLedgerLifecycleAndIdempotency:
    """Verify ledger initialization, pending recording, settlement, idempotency, and SHA-256."""

    def test_ledger_init_pending_settle_and_idempotency(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "benchmark_ledger.json"
        assert DEFAULT_LEDGER_PATH == Path("data/live/benchmark_ledger.json")

        # 1. Initialize empty ledger with 1,000,000 VND
        state0 = initialize_empty_ledger(updated_at="2026-10-24T05:00:00+07:00")
        assert state0.starting_bankroll_vnd == 1_000_000
        assert state0.current_bankroll_vnd == 1_000_000
        assert state0.house_money_surplus_vnd == 0
        assert state0.total_tracked_days == 0
        assert len(state0.sha256) == 64

        save_benchmark_ledger(state0, ledger_file)
        loaded0 = load_benchmark_ledger(ledger_file)
        assert loaded0.sha256 == state0.sha256

        # 2. Record Day 1 (2026-10-24): PLAY_STANDARD (1.0x = 72,000 VND) as PENDING
        state1_pending = record_pending_recommendation(
            loaded0,
            draw_date="2026-10-24",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_station_name="TP. Hồ Chí Minh",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            updated_at="2026-10-24T05:05:00+07:00",
            ledger_path=ledger_file,
        )
        assert state1_pending.total_tracked_days == 1
        assert state1_pending.played_days == 1
        assert state1_pending.rest_days == 0
        assert state1_pending.current_bankroll_vnd == 1_000_000
        assert state1_pending.entries[0].settlement_status == "PENDING"
        assert state1_pending.entries[0].cost_vnd == 72_000
        assert state1_pending.entries[0].recommended_multiplier == 1.0

        # 3. Settle Day 1 with 2 hits -> revenue 175,000 VND, net +103,000 VND (Task 4 manual check)
        prizes_day1 = _sample_18_prizes_with_2_hits()
        state1_settled = settle_ledger_for_date(
            ledger_file,
            draw_date="2026-10-24",
            actual_prizes_last2=prizes_day1,
            updated_at="2026-10-24T16:40:00+07:00",
        )
        e1 = state1_settled.entries[0]
        assert e1.settlement_status == "SETTLED"
        assert e1.hit_count_k == 2
        assert e1.cost_vnd == 72_000
        assert e1.revenue_vnd == 175_000
        assert e1.net_profit_vnd == 103_000
        assert e1.bankroll_after_vnd == 1_103_000
        assert e1.house_money_after_vnd == 103_000

        assert state1_settled.current_bankroll_vnd == 1_103_000
        assert state1_settled.house_money_surplus_vnd == 103_000
        assert state1_settled.peak_bankroll_vnd == 1_103_000
        assert state1_settled.min_bankroll_vnd == 1_000_000
        assert state1_settled.max_drawdown_vnd == 0
        assert state1_settled.win_days == 1
        assert state1_settled.loss_days == 0
        assert state1_settled.total_cost_vnd == 72_000
        assert state1_settled.total_revenue_vnd == 175_000
        assert state1_settled.net_profit_vnd == 103_000

        # 4. IDEMPOTENCY: Calling settle_ledger_for_date a second time for 2026-10-24
        # with the same 18 prizes must not double-count revenue or cost!
        state1_repeat = settle_ledger_for_date(
            ledger_file,
            draw_date="2026-10-24",
            actual_prizes_last2=prizes_day1,
            updated_at="2026-10-24T18:00:00+07:00",
        )
        assert state1_repeat.current_bankroll_vnd == 1_103_000
        assert state1_repeat.total_cost_vnd == 72_000
        assert state1_repeat.total_revenue_vnd == 175_000
        assert state1_repeat.net_profit_vnd == 103_000
        assert state1_repeat.sha256 == state1_settled.sha256

        # 5. Record Day 2 (2026-10-25): SKIP_NO_EDGE -> immediate SETTLED with cost_vnd = 0
        state2 = record_pending_recommendation(
            state1_repeat,
            draw_date="2026-10-25",
            verdict_tier="SKIP_NO_EDGE",
            chosen_station_code="XSDL",
            chosen_station_name="Đà Lạt (Lâm Đồng)",
            chosen_region="Miền Nam",
            chosen_config_id="2x2",
            selected_numbers=["01", "02", "11", "12"],
            updated_at="2026-10-25T05:00:00+07:00",
            ledger_path=ledger_file,
        )
        assert state2.total_tracked_days == 2
        assert state2.played_days == 1
        assert state2.rest_days == 1
        assert state2.current_bankroll_vnd == 1_103_000
        assert state2.entries[1].settlement_status == "SETTLED"
        assert state2.entries[1].recommended_multiplier == 0.0
        assert state2.entries[1].cost_vnd == 0

        # 6. Record Day 3 (2026-10-26): PLAY_STANDARD (1.0x since surplus=103k < 144k)
        # Settle via raw_dir cache lookup with 0 hits -> loss -72,000 VND, drawdown 72,000 VND
        raw_dir = tmp_path / "raw_all"
        save_station_raw_cache(
            "XSHCM",
            [
                {
                    "station_code": "XSHCM",
                    "draw_date": "2026-10-26",
                    "prizes_last2": _sample_18_prizes_zero_hits(),
                }
            ],
            raw_dir=raw_dir,
        )
        state3_pending = record_pending_recommendation(
            state2,
            draw_date="2026-10-26",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_station_name="TP. Hồ Chí Minh",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            updated_at="2026-10-26T05:00:00+07:00",
            ledger_path=ledger_file,
        )
        state3_settled = settle_ledger_for_date(
            state3_pending,
            draw_date="2026-10-26",
            raw_dir=raw_dir,
            ledger_path=ledger_file,
            updated_at="2026-10-26T16:40:00+07:00",
        )
        assert state3_settled.current_bankroll_vnd == 1_031_000
        assert state3_settled.house_money_surplus_vnd == 31_000
        assert state3_settled.peak_bankroll_vnd == 1_103_000
        assert state3_settled.min_bankroll_vnd == 1_000_000
        assert state3_settled.max_drawdown_vnd == 72_000
        assert state3_settled.played_days == 2
        assert state3_settled.rest_days == 1
        assert state3_settled.win_days == 1
        assert state3_settled.loss_days == 1

    def test_negative_mutations_on_ledger_and_gate5(self, tmp_path: Path) -> None:
        ledger_file = tmp_path / "benchmark_ledger.json"
        state = initialize_empty_ledger(updated_at="2026-10-24T05:00:00+07:00")

        # Negative Mutation 1: Forcing multiplier=1.5 when house_money < 144,000
        with pytest.raises(CapitalDisciplineError):
            record_pending_recommendation(
                state,
                draw_date="2026-10-24",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSHCM",
                chosen_station_name="TP. Hồ Chí Minh",
                chosen_region="Miền Nam",
                chosen_config_id="1x4",
                selected_numbers=["21", "22", "23", "28"],
                recommended_multiplier=1.5,
                cost_vnd=108_000,
            )

        # Negative Mutation 2: Forcing multiplier=1.5 when bankroll=950,000
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-24",
                weekday_vn="Thứ 7",
                settlement_status="PENDING",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSHCM",
                chosen_station_name="TP. Hồ Chí Minh",
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

        # Create a valid settled state and save to disk
        state = record_pending_recommendation(
            state,
            draw_date="2026-10-24",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_station_name="TP. Hồ Chí Minh",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            updated_at="2026-10-24T05:00:00+07:00",
        )
        state = settle_ledger_for_date(
            state,
            draw_date="2026-10-24",
            actual_prizes_last2=_sample_18_prizes_with_2_hits(),
            ledger_path=ledger_file,
            updated_at="2026-10-24T16:40:00+07:00",
        )
        assert verify_ledger_integrity(state).current_bankroll_vnd == 1_103_000

        # Negative Mutation 3: Tampering with sha256 in benchmark_ledger.json -> DataIntegrityError
        raw_payload = json.loads(ledger_file.read_text(encoding="utf-8"))
        raw_payload["sha256"] = "0" * 64
        ledger_file.write_text(json.dumps(raw_payload), encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            load_benchmark_ledger(ledger_file)

        # Negative Mutation 4: Tampering with bankroll_after_vnd in JSON (even if sha256 recomputed)
        raw_payload["entries"][0]["bankroll_after_vnd"] = 9_999_999
        raw_payload["entries"][0]["house_money_after_vnd"] = 8_999_999
        raw_payload["sha256"] = compute_ledger_sha256(raw_payload)
        ledger_file.write_text(json.dumps(raw_payload), encoding="utf-8")
        with pytest.raises((CapitalDisciplineError, DataIntegrityError)):
            load_benchmark_ledger(ledger_file)

        # Negative Mutation 5: Conflicting 18 prizes on an already SETTLED date
        save_benchmark_ledger(state, ledger_file)
        with pytest.raises(DataIntegrityError):
            settle_ledger_for_date(
                ledger_file,
                draw_date="2026-10-24",
                actual_prizes_last2=_sample_18_prizes_zero_hits(),
            )

        # Negative Mutation 6: Broken bankroll_before_vnd chain across entries
        e_day1 = state.entries[0]
        e_day2_broken = BenchmarkLedgerEntry(
            draw_date="2026-10-25",
            weekday_vn="Chủ Nhật",
            settlement_status="PENDING",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSDL",
            chosen_station_name="Đà Lạt (Lâm Đồng)",
            chosen_region="Miền Nam",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            recommended_multiplier=1.0,
            bankroll_before_vnd=1_000_000,  # Should be 1_103_000!
            house_money_before_vnd=0,
            cost_vnd=72_000,
            bankroll_after_vnd=1_000_000,
            house_money_after_vnd=0,
        )
        with pytest.raises(CapitalDisciplineError):
            recalculate_ledger_state([e_day1, e_day2_broken], strict_chain=True)
        with pytest.raises(DataIntegrityError):
            settle_entry_with_prizes(e_day2_broken, _sample_18_prizes_with_2_hits()[:15])

        # Verify create_if_missing, re-recording on SETTLED vs PENDING, and SKIP_NO_EDGE settlement
        auto_file = tmp_path / "auto_created_ledger.json"
        auto_state = load_benchmark_ledger(auto_file, create_if_missing=True)
        assert auto_file.exists()
        assert auto_state.current_bankroll_vnd == 1_000_000

        # Re-recording on an already SETTLED date preserves the settled entry
        preserved = record_pending_recommendation(
            state,
            draw_date="2026-10-24",
            verdict_tier="PLAY_PEAK",
            chosen_station_code="XSHCM",
            chosen_config_id="1x4",
            selected_numbers=["01", "02", "03", "04"],
            ledger_path=ledger_file,
        )
        assert preserved.entries[0].settlement_status == "SETTLED"
        assert preserved.current_bankroll_vnd == 1_103_000

        # Recording SKIP_NO_EDGE and calling settle_ledger_for_date without prizes is idempotent
        state_with_skip = record_pending_recommendation(
            preserved,
            draw_date="2026-10-25",
            verdict_tier="SKIP_NO_EDGE",
            chosen_station_code="XSDL",
            chosen_config_id="2x2",
            selected_numbers=["11", "12", "21", "22"],
            ledger_path=ledger_file,
        )
        settled_skip = settle_ledger_for_date(state_with_skip, draw_date="2026-10-25")
        assert settled_skip.current_bankroll_vnd == 1_103_000
        settled_skip_with_prizes = settle_entry_with_prizes(
            state_with_skip.entries[1], _sample_18_prizes_zero_hits()
        )
        assert settled_skip_with_prizes.revenue_vnd == 0
        assert settled_skip_with_prizes.net_profit_vnd == 0

    def test_adversarial_b01_forged_hits_revenue_cost_schedule_and_weekday_rejected(
        self,
    ) -> None:
        state = initialize_empty_ledger(updated_at="2026-10-24T05:00:00+07:00")

        # 1. Station not scheduled on draw_date (XSHCM on Sunday 2026-10-25) -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            record_pending_recommendation(
                state,
                draw_date="2026-10-25",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSHCM",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
            )

        # 2. Wrong weekday_vn label for draw_date -> DataIntegrityError
        with pytest.raises(DataIntegrityError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",  # Sunday (Chủ Nhật)
                weekday_vn="Thứ 2",
                settlement_status="PENDING",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSDL",
                chosen_station_name="Đà Lạt",
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

        # 3. Forged hit_count_k / empty hit_details / decoupled revenue -> DataIntegrityError
        with pytest.raises((DataIntegrityError, CapitalDisciplineError)):
            BenchmarkLedgerEntry(
                draw_date="2026-10-25",
                weekday_vn="Chủ Nhật",
                settlement_status="SETTLED",
                verdict_tier="PLAY_STANDARD",
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
                hit_count_k=18,
                hit_details=[],
                revenue_vnd=1_575_000,
                net_profit_vnd=1_503_000,
                bankroll_after_vnd=2_503_000,
                house_money_after_vnd=1_503_000,
            )

    def test_adversarial_b02_principal_protection_at_1x_and_martingale_rejection(self) -> None:
        # 1. Principal protection even at 1.0x when current_bankroll_vnd < initial_bankroll_vnd
        with pytest.raises(CapitalDisciplineError):
            compute_house_money_multiplier(
                passes_selective_alpha=True,
                strong_convergence=True,
                current_bankroll_vnd=500_000,
                initial_bankroll_vnd=1_000_000,
            )
        with pytest.raises(CapitalDisciplineError):
            compute_multiplier_for_verdict_tier(
                "PLAY_CAUTIOUS",
                current_bankroll_vnd=950_000,
                initial_bankroll_vnd=1_000_000,
            )
        with pytest.raises(CapitalDisciplineError):
            build_capital_guidance(
                "PLAY_STANDARD",
                current_bankroll_vnd=500_000,
                initial_bankroll_vnd=1_000_000,
            )

        # 2. BenchmarkLedgerEntry rejects bankroll_before_vnd < initial principal even at 1.0x
        with pytest.raises(CapitalDisciplineError):
            BenchmarkLedgerEntry(
                draw_date="2026-10-24",
                weekday_vn="Thứ 7",
                settlement_status="PENDING",
                verdict_tier="PLAY_PEAK",
                chosen_station_code="XSHCM",
                chosen_station_name="TP. Hồ Chí Minh",
                chosen_region="Miền Nam",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=1.0,
                bankroll_before_vnd=500_000,
                house_money_before_vnd=0,
                cost_vnd=72_000,
                bankroll_after_vnd=500_000,
                house_money_after_vnd=0,
            )

        # 3. Martingale multipliers (4.0x, 10.0x) rejected everywhere
        with pytest.raises(CapitalDisciplineError):
            build_capital_guidance(
                "PLAY_STANDARD",
                current_bankroll_vnd=2_000_000,
                recommended_multiplier=4.0,
            )
        state = initialize_empty_ledger()
        with pytest.raises(CapitalDisciplineError):
            record_pending_recommendation(
                state,
                draw_date="2026-10-24",
                verdict_tier="PLAY_STANDARD",
                chosen_station_code="XSHCM",
                chosen_config_id="2x2",
                selected_numbers=["01", "02", "11", "12"],
                recommended_multiplier=10.0,
                cost_vnd=72_000,
            )

    def test_adversarial_b04_hybrid_core_satellite_settlement_and_custom_bankroll(self) -> None:
        # 1. Hybrid core_2x2_sat_3x3: 4 core numbers (1.0x = 87,500) + 5 sat numbers (0.5x = 43,750)
        state = initialize_empty_ledger()
        hybrid_nums = ["11", "12", "21", "22", "13", "23", "31", "32", "33"]
        state = record_pending_recommendation(
            state,
            draw_date="2026-10-24",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_config_id="core_2x2_sat_3x3",
            selected_numbers=hybrid_nums,
        )
        assert state.entries[0].cost_vnd == 117_000

        # 1 satellite hit ('33') -> revenue = 43,750 VND, net = -73,250 VND
        settled_sat = settle_entry_with_prizes(
            state.entries[0],
            ["33"] + ["99"] * 17,
        )
        assert settled_sat.hit_count_k == 1
        assert settled_sat.revenue_vnd == 43_750
        assert settled_sat.net_profit_vnd == 43_750 - 117_000

        # 1 core hit ('11') + 1 satellite hit ('33') -> revenue = 131,250 VND, net = +14,250 VND
        settled_both = settle_entry_with_prizes(
            state.entries[0],
            ["11", "33"] + ["99"] * 16,
        )
        assert settled_both.hit_count_k == 2
        assert settled_both.revenue_vnd == 131_250
        assert settled_both.net_profit_vnd == 14_250

        # 2. Custom starting_bankroll_vnd=2_000_000 works without crashing
        state_2m = initialize_empty_ledger(starting_bankroll_vnd=2_000_000)
        state_2m = record_pending_recommendation(
            state_2m,
            draw_date="2026-10-24",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSHCM",
            chosen_config_id="3x3",
            selected_numbers=["11", "12", "13", "21", "22", "23", "31", "32", "33"],
        )
        assert state_2m.entries[0].cost_vnd == 162_000
        state_2m = settle_ledger_for_date(
            state_2m,
            draw_date="2026-10-24",
            actual_prizes_last2=["11", "22"] + ["99"] * 16,
        )
        assert state_2m.entries[0].revenue_vnd == 175_000
        assert state_2m.entries[0].net_profit_vnd == 13_000
        assert state_2m.current_bankroll_vnd == 2_013_000
        assert state_2m.house_money_surplus_vnd == 13_000

    def test_adversarial_b05_skip_no_edge_prize_backfill_and_pre_draw_update(
        self, tmp_path: Path
    ) -> None:
        raw_dir = tmp_path / "raw_all"
        prizes_18 = _sample_18_prizes_with_2_hits()
        save_station_raw_cache(
            "XSDL",
            [
                {
                    "station_code": "XSDL",
                    "draw_date": "2026-10-25",
                    "prizes_last2": prizes_18,
                }
            ],
            raw_dir=raw_dir,
        )
        state = initialize_empty_ledger()
        state = record_pending_recommendation(
            state,
            draw_date="2026-10-25",
            verdict_tier="SKIP_NO_EDGE",
            chosen_station_code="XSDL",
            chosen_config_id="2x2",
            selected_numbers=["21", "22", "23", "28"],
        )
        assert state.entries[0].actual_prizes_last2 == []

        # Calling settle_ledger_for_date populates actual_prizes_last2 from raw_dir (cost/rev=0)
        settled_state = settle_ledger_for_date(
            state,
            draw_date="2026-10-25",
            raw_dir=raw_dir,
        )
        assert settled_state.entries[0].actual_prizes_last2 == prizes_18
        assert settled_state.entries[0].cost_vnd == 0
        assert settled_state.entries[0].revenue_vnd == 0
        assert settled_state.entries[0].net_profit_vnd == 0
        assert settled_state.current_bankroll_vnd == 1_000_000
