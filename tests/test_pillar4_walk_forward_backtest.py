"""Tier 5 TDD Suite: Pillar 4 Walk-Forward Sweet-Spot Portfolio Backtester & Stage 3 Handoff."""

from __future__ import annotations

import datetime
import math

import numpy as np
import pytest
from numpy.random import PCG64, Generator

from xsmn_alpha.backtest.alpha_decay import (
    compute_rank_ordered_alpha_decay,
)
from xsmn_alpha.backtest.sweet_spot_sim import (
    compute_19_state_hit_distribution,
    compute_all_portfolio_19_state_distributions,
    compute_portfolio_set_probability,
    evaluate_all_sweet_spot_portfolios,
    evaluate_sweet_spot_portfolio,
    score_single_draw_portfolio,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    CAGE_NUM_BALLS,
    KELLY_NUM_STATES,
    PRIZES_PER_DRAW,
    REAL_PAYOUT_1D,
    SWEET_SPOT_CONFIGS,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    DataIntegrityError,
    InsufficientSampleSizeError,
)
from xsmn_alpha.schemas import CanonicalDrawRecord, Stage3HandoffContract


def _counts_to_prizes_last2(
    tens_counts: list[int],
    units_counts: list[int],
) -> list[str]:
    """Deterministically pack 10-ball tens and units count vectors into 18 2-digit ASCII prizes."""
    tens_digits: list[int] = []
    units_digits: list[int] = []
    for digit, cnt in enumerate(tens_counts):
        tens_digits.extend([digit] * int(cnt))
    for digit, cnt in enumerate(units_counts):
        units_digits.extend([digit] * int(cnt))
    return [f"{t}{u}" for t, u in zip(tens_digits, units_digits, strict=True)]


def _build_synthetic_draws(
    num_draws: int = 75,
    station_code: str = "XSVL",
    seed: int = 42,
) -> list[CanonicalDrawRecord]:
    """Generate deterministic CanonicalDrawRecord sequence for backtest verification."""
    rng = Generator(PCG64(seed=seed))
    probs_tens = np.array([0.16, 0.14, 0.10, 0.10, 0.09, 0.09, 0.08, 0.08, 0.08, 0.08])
    probs_units = np.array([0.15, 0.15, 0.10, 0.10, 0.09, 0.09, 0.08, 0.08, 0.08, 0.08])
    t_mat = rng.multinomial(PRIZES_PER_DRAW, probs_tens, size=num_draws)
    u_mat = rng.multinomial(PRIZES_PER_DRAW, probs_units, size=num_draws)
    base_date = datetime.date(2023, 1, 6)
    records: list[CanonicalDrawRecord] = []
    for idx in range(num_draws):
        dt = (base_date + datetime.timedelta(days=idx * 7)).isoformat()
        prizes = _counts_to_prizes_last2(t_mat[idx].tolist(), u_mat[idx].tolist())
        records.append(
            CanonicalDrawRecord.from_prizes(
                station_code=station_code,  # type: ignore[arg-type]
                draw_date=dt,
                draw_index=idx,
                prizes_last2=prizes,
            )
        )
    return records


# ===========================================================================
# 1. Task 10 — Rank-Ordered Alpha Decay Tests (-k "decay")
# ===========================================================================


def test_alpha_decay_curve_simplex_and_monotonic_bias() -> None:
    """PASS: compute_rank_ordered_alpha_decay sums to 1.0 and reflects Rank 1 > Rank 10."""
    # Suppose predicted rankings always rank balls 0..9 in order [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    # and realized counts have [4, 3, 2, 2, 2, 1, 1, 1, 1, 1] (sum = 18) across 20 draws
    ranked_lists = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9] for _ in range(20)]
    actual_counts = [[4, 3, 2, 2, 2, 1, 1, 1, 1, 1] for _ in range(20)]

    decay = compute_rank_ordered_alpha_decay(ranked_lists, actual_counts)
    assert len(decay) == CAGE_NUM_BALLS
    assert abs(math.fsum(decay) - 1.0) <= 1e-9
    assert abs(decay[0] - (4.0 / 18.0)) <= 1e-12
    assert abs(decay[1] - (3.0 / 18.0)) <= 1e-12
    assert abs(decay[9] - (1.0 / 18.0)) <= 1e-12
    assert decay[0] > decay[1] > decay[9]

    # Negative Mutation: mismatched lengths or invalid permutation raises DataIntegrityError
    with pytest.raises(DataIntegrityError):
        compute_rank_ordered_alpha_decay([], [])
    with pytest.raises(DataIntegrityError):
        compute_rank_ordered_alpha_decay([[0, 0, 2, 3, 4, 5, 6, 7, 8, 9]], actual_counts[:1])


# ===========================================================================
# 2. Task 10 — Sweet-Spot Portfolio & 19-State Kelly Distribution (-k "sweet_spot")
# ===========================================================================


def test_sweet_spot_cash_flow_formulas_and_hybrid_manual_check() -> None:
    """PASS (Task 10 AC1): Verify cash-flow rules for 2x2, 3x3, Core+Sat, Negative Filter."""
    p_tens = [0.18, 0.16, 0.12, 0.10, 0.08, 0.08, 0.07, 0.07, 0.07, 0.07]
    p_units = [0.17, 0.15, 0.13, 0.10, 0.08, 0.08, 0.08, 0.07, 0.07, 0.07]

    # Top-2 tens = {0, 1}, Top-2 units = {0, 1} -> Core 2x2 = {"00", "01", "10", "11"}
    # Top-3 tens = {0, 1, 2}, Top-3 units = {0, 1, 2} -> Sat = {"02", "12", "20", "21", "22"}
    nums_2x2 = select_sweet_spot_numbers(p_tens, p_units, "2x2")
    assert set(nums_2x2) == {"00", "01", "10", "11"}

    nums_3x3 = select_sweet_spot_numbers(p_tens, p_units, "3x3")
    assert len(nums_3x3) == 9

    nums_81 = select_sweet_spot_numbers(p_tens, p_units, "negative_filter_81")
    assert len(nums_81) == 81
    assert "99" not in nums_81

    nums_87 = select_sweet_spot_numbers(p_tens, p_units, "negative_filter_87")
    assert len(nums_87) == 87
    assert "99" not in nums_87

    # Exact Task 10 manual check: 1 Core hit + 1 Satellite hit
    sample_prizes_1core_1sat = [
        "00",  # 1 Core hit
        "22",  # 1 Satellite hit
        "55",
        "56",
        "57",
        "58",
        "59",
        "65",
        "66",
        "67",
        "68",
        "69",
        "75",
        "76",
        "77",
        "78",
        "79",
        "55",  # Giải ĐB is "55" (in 81/87 filter, not in 3x3)
    ]

    # 1. Manual Check: Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ) with 1 Core hit + 1 Satellite hit
    res_hybrid = score_single_draw_portfolio(
        p_tens, p_units, sample_prizes_1core_1sat, "core_2x2_sat_3x3"
    )
    expected_rev = BAO_LO_PAYOUT_PER_HIT + 0.5 * BAO_LO_PAYOUT_PER_HIT
    expected_net = expected_rev - 6.5
    assert abs(res_hybrid["cost"] - 6.5) <= 1e-12
    assert abs(res_hybrid["revenue"] - expected_rev) <= 1e-9
    assert abs(res_hybrid["net_profit"] - expected_net) <= 1e-9
    assert abs(res_hybrid["revenue"] - 7.291666666666667) <= 1e-6
    assert abs(res_hybrid["net_profit"] - 0.7916666666666667) <= 1e-6

    # 2. Check 2x2 (cost 4.0đ, 1 hit -> rev 4.861111, net +0.861111)
    res_2x2 = score_single_draw_portfolio(p_tens, p_units, sample_prizes_1core_1sat, "2x2")
    assert abs(res_2x2["cost"] - 4.0) <= 1e-12
    assert abs(res_2x2["revenue"] - BAO_LO_PAYOUT_PER_HIT) <= 1e-9
    assert abs(res_2x2["net_profit"] - (BAO_LO_PAYOUT_PER_HIT - 4.0)) <= 1e-9

    # 3. Check 3x3 (cost 9.0đ, 2 hits -> rev 9.722222, net +0.722222)
    res_3x3 = score_single_draw_portfolio(p_tens, p_units, sample_prizes_1core_1sat, "3x3")
    assert abs(res_3x3["cost"] - 9.0) <= 1e-12
    assert abs(res_3x3["revenue"] - 2.0 * BAO_LO_PAYOUT_PER_HIT) <= 1e-9
    assert abs(res_3x3["net_profit"] - (2.0 * BAO_LO_PAYOUT_PER_HIT - 9.0)) <= 1e-9

    # 4. Check Negative Filter 81 and 87 on Giải ĐB (index 17 == "55" is included -> rev 87.5đ)
    res_nf81 = score_single_draw_portfolio(
        p_tens, p_units, sample_prizes_1core_1sat, "negative_filter_81"
    )
    assert abs(res_nf81["cost"] - 81.0) <= 1e-12
    assert abs(res_nf81["revenue"] - REAL_PAYOUT_1D) <= 1e-9
    assert abs(res_nf81["net_profit"] - 6.5) <= 1e-9

    res_nf87 = score_single_draw_portfolio(
        p_tens, p_units, sample_prizes_1core_1sat, "negative_filter_87"
    )
    assert abs(res_nf87["cost"] - 87.0) <= 1e-12
    assert abs(res_nf87["revenue"] - REAL_PAYOUT_1D) <= 1e-9
    assert abs(res_nf87["net_profit"] - 0.5) <= 1e-9

    # Multi-draw portfolio aggregation across all 8 SWEET_SPOT_CONFIGS
    draws = _build_synthetic_draws(num_draws=40)
    preds_tens = [p_tens for _ in range(30)]
    preds_units = [p_units for _ in range(30)]
    eval_draws = draws[10:]
    all_metrics = evaluate_all_sweet_spot_portfolios(preds_tens, preds_units, eval_draws)
    assert set(all_metrics.keys()) == set(SWEET_SPOT_CONFIGS.keys())
    for cfg_id, m in all_metrics.items():
        assert m.evaluated_draws == 30
        assert abs(m.cost_per_draw - float(SWEET_SPOT_CONFIGS[cfg_id]["cost_per_draw"])) <= 1e-9
        assert abs(m.net_profit - (m.total_revenue - m.total_cost)) <= 1e-6
        if int(SWEET_SPOT_CONFIGS[cfg_id]["min_hits_for_profit"]) <= 2:
            assert m.multi_hit_rate_ge2 <= m.daily_win_rate + 1e-12

    # C-05: 0 Core + 2 Satellite hits (effective_hits = 1.0, net_profit = -1.6389đ)
    # must NOT be counted as a multi-hit day (multi_hit_rate_ge2 == 0.0 <= daily_win_rate)
    prizes_0core_2sat = ["22", "21"] + ["55"] * 16
    res_0c_2s = score_single_draw_portfolio(p_tens, p_units, prizes_0core_2sat, "core_2x2_sat_3x3")
    assert res_0c_2s["raw_hits"] == 2
    assert abs(res_0c_2s["effective_hits"] - 1.0) <= 1e-12
    assert res_0c_2s["net_profit"] < 0.0
    assert res_0c_2s["is_multi_hit_ge2"] is False
    metrics_0c_2s = evaluate_sweet_spot_portfolio(
        [p_tens], [p_units], [prizes_0core_2sat], "core_2x2_sat_3x3"
    )
    assert metrics_0c_2s.daily_win_rate == 0.0
    assert metrics_0c_2s.multi_hit_rate_ge2 == 0.0


def test_sweet_spot_19_state_hit_distribution_invariants() -> None:
    """PASS & FAIL (Task 10 AC3 & C-01/C-08): 19-state distribution across all 8 configs."""
    p_tens = [0.16, 0.14, 0.12, 0.10, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08]
    p_units = [0.15, 0.15, 0.11, 0.10, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08]

    all_dists = compute_all_portfolio_19_state_distributions(p_tens, p_units)
    assert set(all_dists.keys()) == set(SWEET_SPOT_CONFIGS.keys())

    for cfg_id, cfg in SWEET_SPOT_CONFIGS.items():
        p_set = compute_portfolio_set_probability(p_tens, p_units, cfg_id)
        dist_19 = all_dists[cfg_id]
        assert len(dist_19) == KELLY_NUM_STATES
        assert all(p >= 0.0 and math.isfinite(p) for p in dist_19)
        assert abs(math.fsum(dist_19) - 1.0) <= 1e-9

        expected_k = sum(k * dist_19[k] for k in range(KELLY_NUM_STATES))
        if cfg["game_type"] == "duoi_1_giai":
            assert abs(expected_k - 1.0 * p_set) <= 1e-9
            assert abs(dist_19[0] - (1.0 - p_set)) <= 1e-9
            assert abs(dist_19[1] - p_set) <= 1e-9
            assert abs(sum(dist_19[2:])) <= 1e-12
        else:
            assert abs(expected_k - float(PRIZES_PER_DRAW) * p_set) <= 1e-9

    # C-01: core_2x2_sat_3x3 must have stake-weighted effective p_eff < p_3x3
    p_2x2 = compute_portfolio_set_probability(p_tens, p_units, "2x2")
    p_3x3 = compute_portfolio_set_probability(p_tens, p_units, "3x3")
    p_hybrid = compute_portfolio_set_probability(p_tens, p_units, "core_2x2_sat_3x3")
    assert abs(p_hybrid - (p_2x2 + 0.5 * (p_3x3 - p_2x2))) <= 1e-12
    assert p_2x2 < p_hybrid < p_3x3
    assert all_dists["core_2x2_sat_3x3"] != all_dists["3x3"]

    # Boundary probabilities p_S = 0.0 and p_S = 1.0
    dist_zero = compute_19_state_hit_distribution(0.0)
    assert abs(dist_zero[0] - 1.0) <= 1e-12
    assert abs(math.fsum(dist_zero) - 1.0) <= 1e-12

    dist_one = compute_19_state_hit_distribution(1.0)
    assert abs(dist_one[18] - 1.0) <= 1e-12
    assert abs(math.fsum(dist_one) - 1.0) <= 1e-12

    dist_one_single = compute_19_state_hit_distribution(1.0, num_trials=1)
    assert abs(dist_one_single[1] - 1.0) <= 1e-12
    assert abs(sum(dist_one_single[2:])) <= 1e-12

    # Invalid p_S outside [0, 1] must raise CalibrationIntegrityError
    with pytest.raises(CalibrationIntegrityError):
        compute_19_state_hit_distribution(-0.01)
    with pytest.raises(CalibrationIntegrityError):
        compute_19_state_hit_distribution(1.05)
    with pytest.raises(CalibrationIntegrityError):
        compute_19_state_hit_distribution(float("nan"))
    with pytest.raises(DataIntegrityError):
        compute_19_state_hit_distribution(0.5, num_trials=5)


# ===========================================================================
# 3. Task 11 — WalkForwardRunner, HTML/JSON Reporting & CLI Tests
# ===========================================================================


def test_walk_forward_runner_and_stage3_handoff_export(tmp_path) -> None:
    """PASS & FAIL (Task 11 AC1, AC2, AC3): WalkForwardRunner, HTML/JSON reports, and CLI."""
    import json

    from xsmn_alpha.backtest.runner import (
        WalkForwardRunner,
        build_stage3_handoff_contract,
    )
    from xsmn_alpha.cli import main as cli_main
    from xsmn_alpha.reporting.html_report import (
        export_dual_station_reports,
        save_stage3_handoff_contract,
    )

    draws_hcm = _build_synthetic_draws(num_draws=520, station_code="XSHCM", seed=42)
    draws_vl = _build_synthetic_draws(num_draws=260, station_code="XSVL", seed=77)

    runner = WalkForwardRunner(warmup_draws=45, null_sims=50, seed=42)
    station_rep_vl = runner.evaluate_station_dual_horizons(draws_vl, station_code="XSVL")
    assert station_rep_vl.station_code == "XSVL"
    assert station_rep_vl.horizon_5y.total_draws == 260
    assert station_rep_vl.horizon_5y.evaluated_draws == 215
    assert station_rep_vl.horizon_3y.total_draws == 156
    assert station_rep_vl.horizon_3y.evaluated_draws == 111

    station_rep_hcm = runner.evaluate_station_dual_horizons(draws_hcm, station_code="XSHCM")
    assert station_rep_hcm.station_code == "XSHCM"
    assert station_rep_hcm.horizon_5y.total_draws == 520
    assert station_rep_hcm.horizon_3y.total_draws == 312

    handoff_vl = build_stage3_handoff_contract(station_rep_vl)
    handoff_hcm = build_stage3_handoff_contract(station_rep_hcm)
    assert isinstance(handoff_vl, Stage3HandoffContract)
    assert isinstance(handoff_hcm, Stage3HandoffContract)
    assert handoff_vl.as_of_draw_date == draws_vl[-1].draw_date
    assert handoff_hcm.as_of_draw_date == draws_hcm[-1].draw_date
    assert (
        station_rep_vl.horizon_3y.latest_tens_prediction.target_draw_date
        > handoff_vl.as_of_draw_date
    )
    assert (
        station_rep_hcm.horizon_3y.latest_tens_prediction.target_draw_date
        > handoff_hcm.as_of_draw_date
    )

    out_dir = tmp_path / "outputs"
    reports_dir = tmp_path / "reports"
    vl_json_path = save_stage3_handoff_contract(handoff_vl, out_dir=out_dir)
    hcm_json_path = save_stage3_handoff_contract(handoff_hcm, out_dir=out_dir)
    assert vl_json_path.exists()
    assert hcm_json_path.exists()

    # Re-validate from disk using Stage3HandoffContract
    loaded_vl = Stage3HandoffContract.model_validate(
        json.loads(vl_json_path.read_text(encoding="utf-8"))
    )
    assert loaded_vl.station_code == "XSVL"

    comp_json, comp_html = export_dual_station_reports(
        {"XSHCM": station_rep_hcm, "XSVL": station_rep_vl},
        {"XSHCM": handoff_hcm, "XSVL": handoff_vl},
        reports_dir=reports_dir,
    )
    assert comp_json.exists()
    assert comp_html.exists()
    html_text = comp_html.read_text(encoding="utf-8")
    assert "XSHCM" in html_text and "XSVL" in html_text

    # Negative Mutation: Sample size < 60 must raise InsufficientSampleSizeError
    with pytest.raises(InsufficientSampleSizeError):
        runner.evaluate_horizon(draws_vl[:50], station_code="XSVL", horizon="3y")

    # Verify CLI help exits cleanly with 0
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])
    assert exc_info.value.code == 0
