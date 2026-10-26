"""Tier 1 TDD Suite: Stage 1 Constants, Fail-Closed Exceptions, and Pydantic v2 Schemas."""

from __future__ import annotations

import math
import types

import pytest
from pydantic import ValidationError

from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    BE_LIFT_2D_NUMBER,
    BE_LIFT_SINGLE_BALL,
    BE_PROB_2D_NUMBER,
    BE_PROB_SINGLE_BALL,
    CAGE_NUM_BALLS,
    PRIZES_PER_DRAW,
    REAL_PAYOUT_1D,
    STATION_CONFIG,
    SWEET_SPOT_CONFIGS,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    DataIntegrityError,
    InsufficientSampleSizeError,
    TemporalLeakageError,
    XSMNAlphaError,
)
from xsmn_alpha.schemas import (
    CageFalsificationResult,
    CageWindowTestResult,
    CalibratedCagePrediction,
    CanonicalDrawRecord,
    DualHorizonStationReport,
    FalsificationReport,
    HorizonBacktestReport,
    PreDrawFeatureVector,
    Stage3HandoffContract,
    SweetSpotPortfolioMetrics,
    validate_pooling_weights,
    validate_probability_simplex,
)


def _make_uniform_10() -> list[float]:
    return [0.10] * 10


def _make_valid_19_state_dist() -> list[float]:
    p = 0.04
    dist = [math.comb(18, k) * (p**k) * ((1.0 - p) ** (18 - k)) for k in range(19)]
    total = sum(dist)
    return [x / total for x in dist]


def _make_sample_window_result(window_draws: int = 30) -> CageWindowTestResult:
    m_w = 18 * window_draws
    per_ball = m_w // 10
    return CageWindowTestResult(
        window_draws=window_draws,
        total_trials=m_w,
        observed_counts=[per_ball] * 10,
        chi2_stat=0.0,
        chi2_p_value=1.0,
        bf10_dirichlet=0.15,
        normalized_entropy=1.0,
        runs_test_min_p_value=0.50,
        runs_test_max_abs_z=0.67,
        markov_chi2_stat=81.0,
        markov_chi2_p_value=0.74,
    )


def _make_sample_cage_falsification(
    cage_name: str = "tens_cage",
    sample_size_draws: int = 520,
    gate_status: str = "FAIL_WHITE_NOISE_CASH_BRAKE",
    multiplier: float = 0.0,
) -> CageFalsificationResult:
    return CageFalsificationResult(
        cage_name=cage_name,  # type: ignore[arg-type]
        sample_size_draws=sample_size_draws,
        window_results=[
            _make_sample_window_result(15),
            _make_sample_window_result(30),
            _make_sample_window_result(60),
        ],
        observed_chi2_max=11.2,
        observed_bf10_max=0.42,
        null_chi2_max_p90=18.5,
        null_chi2_max_p95=21.3,
        mc_p_value=0.52,
        top2_calibrated_prob_mean=0.102,
        top2_calibrated_lift=0.02,
        gate_status=gate_status,  # type: ignore[arg-type]
        recommended_capital_multiplier=multiplier,
    )


def _make_sample_falsification_report(
    station_code: str = "XSHCM",
    horizon: str = "5y",
    sample_size_draws: int = 520,
) -> FalsificationReport:
    return FalsificationReport(
        station_code=station_code,  # type: ignore[arg-type]
        horizon=horizon,  # type: ignore[arg-type]
        sample_size_draws=sample_size_draws,
        null_simulations=1000,
        seed=42,
        tens_cage=_make_sample_cage_falsification("tens_cage", sample_size_draws),
        units_cage=_make_sample_cage_falsification("units_cage", sample_size_draws),
        overall_status="FAIL_WHITE_NOISE_CASH_BRAKE",
        recommended_capital_multiplier=0.0,
    )


def _make_sample_cage_prediction(cage_name: str = "tens_cage") -> CalibratedCagePrediction:
    return CalibratedCagePrediction(
        cage_name=cage_name,  # type: ignore[arg-type]
        target_draw_index=519,
        target_draw_date="2026-10-24",
        p_bocd=_make_uniform_10(),
        p_seq=_make_uniform_10(),
        p_ai=_make_uniform_10(),
        weights=(0.2, 0.1),
        uniform_weight=0.7,
        ranked_balls=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        top2_mean_prob=0.10,
        top2_lift_vs_uniform=0.0,
        exceeds_break_even_ball_threshold=False,
        conviction_score=0.0,
        oos_brier_score=0.09,
        naive_brier_score=0.092,
        map_run_length=15,
    )


def _make_sample_portfolio_metrics(config_id: str = "2x2") -> SweetSpotPortfolioMetrics:
    cfg = SWEET_SPOT_CONFIGS[config_id]
    return SweetSpotPortfolioMetrics(
        config_id=config_id,
        game_type=str(cfg["game_type"]),
        evaluated_draws=300,
        cost_per_draw=float(cfg["cost_per_draw"]),
        total_cost=float(cfg["cost_per_draw"]) * 300,
        total_revenue=float(cfg["cost_per_draw"]) * 300 * 0.95,
        net_profit=-float(cfg["cost_per_draw"]) * 300 * 0.05,
        roi_pct=-5.0,
        total_hits=220.0,
        hits_per_30_draws=22.0,
        break_even_hits_30_draws=float(cfg["be_hits_30_draws"]),
        daily_win_rate=0.52,
        multi_hit_rate_ge2=0.15,
        zero_hit_rate_k0=0.48,
        max_losing_streak=6,
        max_drawdown=42.0,
    )


def _make_sample_horizon_report(
    station_code: str = "XSHCM",
    horizon: str = "5y",
    total_draws: int = 520,
) -> HorizonBacktestReport:
    return HorizonBacktestReport(
        station_code=station_code,  # type: ignore[arg-type]
        horizon=horizon,  # type: ignore[arg-type]
        total_draws=total_draws,
        warmup_draws=45,
        evaluated_draws=total_draws - 45,
        falsification_report=_make_sample_falsification_report(station_code, horizon, total_draws),
        latest_tens_prediction=_make_sample_cage_prediction("tens_cage"),
        latest_units_prediction=_make_sample_cage_prediction("units_cage"),
        tens_rank_alpha_decay=_make_uniform_10(),
        units_rank_alpha_decay=_make_uniform_10(),
        tens_oos_brier_score=0.09,
        tens_naive_brier_score=0.092,
        units_oos_brier_score=0.09,
        units_naive_brier_score=0.091,
        portfolio_metrics={cid: _make_sample_portfolio_metrics(cid) for cid in SWEET_SPOT_CONFIGS},
    )


class TestStage1ConstantsAndExceptions:
    """Verify Stage 1 mathematical constants, station configs, and fail-closed exceptions."""

    def test_stage1_financial_constants_exact(self) -> None:
        assert REAL_PAYOUT_1D == 87.5
        assert PRIZES_PER_DRAW == 18
        assert CAGE_NUM_BALLS == 10
        assert BAO_LO_PAYOUT_PER_HIT == pytest.approx(87.5 / 18.0, rel=1e-15)
        assert BAO_LO_PAYOUT_PER_HIT == pytest.approx(175.0 / 36.0, rel=1e-15)
        assert BE_PROB_2D_NUMBER == pytest.approx(1.0 / 87.5, rel=1e-15)
        assert BE_LIFT_2D_NUMBER == pytest.approx((100.0 / 87.5) - 1.0, rel=1e-15)
        assert BE_PROB_SINGLE_BALL == pytest.approx(0.1 * math.sqrt(100.0 / 87.5), rel=1e-15)
        assert BE_LIFT_SINGLE_BALL == pytest.approx(math.sqrt(100.0 / 87.5) - 1.0, rel=1e-15)

    def test_station_config_xshcm_and_xsvl(self) -> None:
        assert set(STATION_CONFIG.keys()) == {"XSHCM", "XSVL"}

        hcm = STATION_CONFIG["XSHCM"]
        assert hcm["slug"] == "tp-hcm"
        assert hcm["xskt_slug"] == "xshcm-xstp"
        assert hcm["xoso_slug"] == "xshcm"
        assert hcm["draws_per_week"] == 2
        assert hcm["horizons"]["5y"] == 520
        assert hcm["horizons"]["3y"] == 312

        vl = STATION_CONFIG["XSVL"]
        assert vl["slug"] == "vinh-long"
        assert vl["xskt_slug"] == "xsvl"
        assert vl["xoso_slug"] == "xsvl"
        assert vl["draws_per_week"] == 1
        assert vl["horizons"]["5y"] == 260
        assert vl["horizons"]["3y"] == 156

    def test_sweet_spot_configs_all_eight_present(self) -> None:
        expected_ids = {
            "2x2",
            "3x3",
            "core_2x2_sat_3x3",
            "1x4",
            "2x7",
            "3x6",
            "negative_filter_81",
            "negative_filter_87",
        }
        assert set(SWEET_SPOT_CONFIGS.keys()) == expected_ids

        assert SWEET_SPOT_CONFIGS["2x2"]["cost_per_draw"] == 4.0
        assert SWEET_SPOT_CONFIGS["2x2"]["be_hits_30_draws"] == pytest.approx(
            120.0 / BAO_LO_PAYOUT_PER_HIT, rel=1e-12
        )
        assert SWEET_SPOT_CONFIGS["3x3"]["cost_per_draw"] == 9.0
        assert SWEET_SPOT_CONFIGS["3x3"]["be_hits_30_draws"] == pytest.approx(
            270.0 / BAO_LO_PAYOUT_PER_HIT, rel=1e-12
        )
        assert SWEET_SPOT_CONFIGS["core_2x2_sat_3x3"]["cost_per_draw"] == 6.5
        assert SWEET_SPOT_CONFIGS["core_2x2_sat_3x3"]["be_hits_30_draws"] == pytest.approx(
            195.0 / BAO_LO_PAYOUT_PER_HIT, rel=1e-12
        )
        assert SWEET_SPOT_CONFIGS["1x4"]["cost_per_draw"] == 4.0
        assert SWEET_SPOT_CONFIGS["2x7"]["cost_per_draw"] == 14.0
        assert SWEET_SPOT_CONFIGS["3x6"]["cost_per_draw"] == 18.0
        assert SWEET_SPOT_CONFIGS["negative_filter_81"]["cost_per_draw"] == 81.0
        assert SWEET_SPOT_CONFIGS["negative_filter_87"]["cost_per_draw"] == 87.0

    def test_exception_hierarchy(self) -> None:
        assert issubclass(XSMNAlphaError, Exception)
        assert not issubclass(XSMNAlphaError, ValueError)
        assert issubclass(DataIntegrityError, XSMNAlphaError)
        assert issubclass(TemporalLeakageError, XSMNAlphaError)
        assert issubclass(CalibrationIntegrityError, XSMNAlphaError)
        assert issubclass(InsufficientSampleSizeError, XSMNAlphaError)
        assert not issubclass(CalibrationIntegrityError, DataIntegrityError)
        assert not issubclass(InsufficientSampleSizeError, DataIntegrityError)

    def test_constants_mapping_proxy_immutability(self) -> None:
        with pytest.raises(TypeError):
            STATION_CONFIG["XSHCM"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            STATION_CONFIG["XSHCM"]["draws_per_week"] = 999  # type: ignore[index]
        with pytest.raises(TypeError):
            STATION_CONFIG["XSHCM"]["horizons"]["5y"] = 10  # type: ignore[index]
        with pytest.raises(TypeError):
            SWEET_SPOT_CONFIGS["2x2"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            SWEET_SPOT_CONFIGS["2x2"]["cost_per_draw"] = 0.0  # type: ignore[index]


class TestCanonicalDrawRecordAndDataSchemaGate:
    """Verify CanonicalDrawRecord PASS flows and DataSchemaGate Negative Mutation FAILs."""

    def test_canonical_draw_record_pass(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        record = CanonicalDrawRecord(
            station_code="XSHCM",
            draw_date="2026-10-24",
            draw_index=519,
            prizes_last2=sample_valid_prizes_18,
            tens_counts=sample_valid_tens_counts,
            units_counts=sample_valid_units_counts,
        )
        assert record.station_code == "XSHCM"
        assert len(record.prizes_last2) == 18
        assert sum(record.tens_counts) == 18
        assert sum(record.units_counts) == 18

        from_helper = CanonicalDrawRecord.from_prizes(
            station_code="XSVL",
            draw_date="2026-10-23",
            draw_index=259,
            prizes_last2=sample_valid_prizes_18,
        )
        assert from_helper.tens_counts == sample_valid_tens_counts
        assert from_helper.units_counts == sample_valid_units_counts

    def test_negative_mutation_17_or_19_prizes_fails(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=0,
                prizes_last2=sample_valid_prizes_18[:17],
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=0,
                prizes_last2=[*sample_valid_prizes_18, "99"],
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

    @pytest.mark.parametrize("bad_token", ["０８", "9A", "", "8", "083", "ab", " 8", "-1"])
    def test_negative_mutation_non_ascii_or_invalid_prize_token_fails(
        self,
        bad_token: str,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        mutated = list(sample_valid_prizes_18)
        mutated[3] = bad_token
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=10,
                prizes_last2=mutated,
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

    def test_negative_mutation_cage_counts_sum_or_mismatch_fails(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        # Sum != 18
        bad_sum_tens = list(sample_valid_tens_counts)
        bad_sum_tens[0] += 1
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=10,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=bad_sum_tens,
                units_counts=sample_valid_units_counts,
            )

        # Sum == 18 but does not match prizes_last2
        swapped_tens = list(reversed(sample_valid_tens_counts))
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=10,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=swapped_tens,
                units_counts=sample_valid_units_counts,
            )

        # Wrong vector length (9 instead of 10)
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=10,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=sample_valid_tens_counts[:9],
                units_counts=sample_valid_units_counts,
            )

    def test_negative_mutation_invalid_station_or_date_or_extra_field_fails(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSTG",  # type: ignore[arg-type]
                draw_date="2026-10-24",
                draw_index=0,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="24/10/2026",
                draw_index=0,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=-5,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
            )

        with pytest.raises((DataIntegrityError, ValidationError)):
            CanonicalDrawRecord(
                station_code="XSHCM",
                draw_date="2026-10-24",
                draw_index=0,
                prizes_last2=sample_valid_prizes_18,
                tens_counts=sample_valid_tens_counts,
                units_counts=sample_valid_units_counts,
                unexpected_extra_field=123,  # type: ignore[call-arg]
            )


class TestCalibrationSimplexAndStage3HandoffSchemas:
    """Verify CalibratedCagePrediction, FalsificationReport, and Stage3HandoffContract."""

    def test_simplex_and_pooling_validators_pass_and_fail(self) -> None:
        valid_p = validate_probability_simplex([0.1] * 10, expected_len=10)
        assert len(valid_p) == 10
        assert sum(valid_p) == pytest.approx(1.0)

        w1, w2 = validate_pooling_weights(0.4, 0.3)
        assert (w1, w2) == (0.4, 0.3)

        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex([0.0995] * 10, expected_len=10)

        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex([-0.1, 0.2, *[0.1125] * 8], expected_len=10)

        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex([float("nan"), *[0.1] * 9], expected_len=10)

        with pytest.raises(CalibrationIntegrityError):
            validate_pooling_weights(0.7, 0.5)

        with pytest.raises(CalibrationIntegrityError):
            validate_pooling_weights(-0.1, 0.5)

    def test_calibrated_cage_prediction_negative_mutations(self) -> None:
        pred = _make_sample_cage_prediction("tens_cage")
        assert sum(pred.p_ai) == pytest.approx(1.0)

        # Sum 0.995 violates simplex
        bad_probs = [0.0995] * 10
        with pytest.raises(CalibrationIntegrityError):
            CalibratedCagePrediction(
                cage_name="tens_cage",
                target_draw_index=519,
                target_draw_date="2026-10-24",
                p_bocd=_make_uniform_10(),
                p_seq=_make_uniform_10(),
                p_ai=bad_probs,
                weights=(0.2, 0.1),
                uniform_weight=0.7,
                ranked_balls=list(range(10)),
                top2_mean_prob=0.10,
                top2_lift_vs_uniform=0.0,
                exceeds_break_even_ball_threshold=False,
                conviction_score=0.0,
            )

        # Weights sum > 1.0
        with pytest.raises(CalibrationIntegrityError):
            CalibratedCagePrediction(
                cage_name="tens_cage",
                target_draw_index=519,
                target_draw_date="2026-10-24",
                p_bocd=_make_uniform_10(),
                p_seq=_make_uniform_10(),
                p_ai=_make_uniform_10(),
                weights=(0.7, 0.5),
                uniform_weight=-0.2,
                ranked_balls=list(range(10)),
                top2_mean_prob=0.10,
                top2_lift_vs_uniform=0.0,
                exceeds_break_even_ball_threshold=False,
                conviction_score=0.0,
            )

    def test_falsification_report_and_insufficient_sample_size_gate(self) -> None:
        report = _make_sample_falsification_report("XSHCM", "5y", 520)
        assert report.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert report.recommended_capital_multiplier == 0.0

        # Sample size < 60 must raise InsufficientSampleSizeError
        with pytest.raises(InsufficientSampleSizeError):
            _make_sample_cage_falsification("tens_cage", sample_size_draws=45)

        # FAIL_WHITE_NOISE_CASH_BRAKE with non-zero capital multiplier must fail
        with pytest.raises(DataIntegrityError):
            _make_sample_cage_falsification(
                "tens_cage",
                sample_size_draws=156,
                gate_status="FAIL_WHITE_NOISE_CASH_BRAKE",
                multiplier=1.0,
            )

    def test_dual_horizon_and_stage3_handoff_contract_pass_and_fail(self) -> None:
        h5y = _make_sample_horizon_report("XSHCM", "5y", 520)
        h3y = _make_sample_horizon_report("XSHCM", "3y", 312)

        dual = DualHorizonStationReport(
            station_code="XSHCM",
            station_name="TP. Hồ Chí Minh",
            draws_per_week=2,
            horizon_5y=h5y,
            horizon_3y=h3y,
        )
        assert dual.horizon_5y.total_draws == 520
        assert dual.horizon_3y.total_draws == 312

        dist_19 = _make_valid_19_state_dist()
        handoff = Stage3HandoffContract(
            station_code="XSHCM",
            as_of_draw_date="2026-10-24",
            as_of_draw_index=519,
            gatekeeper_status="FAIL_WHITE_NOISE_CASH_BRAKE",
            recommended_capital_multiplier=0.0,
            p_ai_tens=_make_uniform_10(),
            p_ai_units=_make_uniform_10(),
            conviction_score=0.0,
            recommended_portfolio_config="2x2",
            selected_numbers_2d=["00", "01", "10", "11"],
            hit_count_distribution_19=dist_19,
            portfolio_hit_distributions_19={"2x2": dist_19},
            horizon_5y_summary=h5y,
            horizon_3y_summary=h3y,
        )
        dumped = handoff.model_dump_json()
        restored = Stage3HandoffContract.model_validate_json(dumped)
        assert restored.station_code == "XSHCM"
        assert sum(restored.hit_count_distribution_19) == pytest.approx(1.0)

        # Negative mutation: 19-state distribution with wrong length (18 states instead of 19)
        with pytest.raises(CalibrationIntegrityError):
            Stage3HandoffContract(
                station_code="XSHCM",
                as_of_draw_date="2026-10-24",
                as_of_draw_index=519,
                gatekeeper_status="FAIL_WHITE_NOISE_CASH_BRAKE",
                recommended_capital_multiplier=0.0,
                p_ai_tens=_make_uniform_10(),
                p_ai_units=_make_uniform_10(),
                conviction_score=0.0,
                recommended_portfolio_config="2x2",
                selected_numbers_2d=["00", "01", "10", "11"],
                hit_count_distribution_19=dist_19[:18],
                horizon_5y_summary=h5y,
                horizon_3y_summary=h3y,
            )

        # Negative mutation: 10-ball probability sum == 0.995
        with pytest.raises(CalibrationIntegrityError):
            Stage3HandoffContract(
                station_code="XSHCM",
                as_of_draw_date="2026-10-24",
                as_of_draw_index=519,
                gatekeeper_status="FAIL_WHITE_NOISE_CASH_BRAKE",
                recommended_capital_multiplier=0.0,
                p_ai_tens=[0.0995] * 10,
                p_ai_units=_make_uniform_10(),
                conviction_score=0.0,
                recommended_portfolio_config="2x2",
                selected_numbers_2d=["00", "01", "10", "11"],
                hit_count_distribution_19=dist_19,
                horizon_5y_summary=h5y,
                horizon_3y_summary=h3y,
            )

        # Negative mutation: FAIL_WHITE_NOISE_CASH_BRAKE with non-zero capital multiplier
        with pytest.raises(DataIntegrityError):
            Stage3HandoffContract(
                station_code="XSHCM",
                as_of_draw_date="2026-10-24",
                as_of_draw_index=519,
                gatekeeper_status="FAIL_WHITE_NOISE_CASH_BRAKE",
                recommended_capital_multiplier=0.5,
                p_ai_tens=_make_uniform_10(),
                p_ai_units=_make_uniform_10(),
                conviction_score=0.0,
                recommended_portfolio_config="2x2",
                selected_numbers_2d=["00", "01", "10", "11"],
                hit_count_distribution_19=dist_19,
                horizon_5y_summary=h5y,
                horizon_3y_summary=h3y,
            )

    def test_predraw_feature_vector_and_edge_branches(self) -> None:
        feat = PreDrawFeatureVector(
            station_code="XSHCM",
            cage_name="tens_cage",
            target_draw_index=10,
            target_draw_date="2026-10-24",
            history_length=10,
            regime_counts={5: [9] * 10, 10: [18] * 10},
            regime_freqs={5: [0.1] * 10, 10: [0.1] * 10},
            zero_hit_gaps=[0] * 10,
            gap_z_scores=[0.0] * 10,
            deficit_10_z_scores=[0.0] * 10,
            burst_rebound_indicators=[0] * 10,
            burst_rebound_rates=[0.1] * 10,
            markov_transition_matrix=[_make_uniform_10() for _ in range(10)],
            session_early_ratios=[0.5] * 10,
        )
        assert feat.cage_name == "tens_cage"

        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(
                station_code="XSHCM",
                cage_name="tens_cage",
                target_draw_index=10,
                target_draw_date="2026-10-24",
                history_length=10,
                regime_counts={5: [9] * 10},
                regime_freqs={5: [0.1] * 10},
                zero_hit_gaps=[0] * 9,
                gap_z_scores=[0.0] * 10,
                deficit_10_z_scores=[0.0] * 10,
                burst_rebound_indicators=[0] * 10,
                burst_rebound_rates=[0.1] * 10,
                markov_transition_matrix=[_make_uniform_10() for _ in range(10)],
                session_early_ratios=[0.5] * 10,
            )

        with pytest.raises(DataIntegrityError):
            CageWindowTestResult(
                window_draws=15,
                total_trials=100,
                observed_counts=[27] * 10,
                chi2_stat=0.0,
                chi2_p_value=1.0,
                bf10_dirichlet=0.2,
                normalized_entropy=1.0,
                runs_test_min_p_value=0.5,
                markov_chi2_stat=10.0,
                markov_chi2_p_value=0.5,
            )

    def test_mapping_proxy_validation_and_caller_dict_non_mutation(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        # SA-04: Non-dict Mapping (MappingProxyType) must still go through Gate 1 validation
        bad_proxy = types.MappingProxyType(
            {
                "station_code": "XSHCM",
                "draw_date": "NOT-A-VALID-ISO-DATE",
                "draw_index": -999,
                "prizes_last2": [f"{p}999_GARBAGE" for p in sample_valid_prizes_18],
                "tens_counts": sample_valid_tens_counts,
                "units_counts": sample_valid_units_counts,
            }
        )
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord.model_validate(bad_proxy)

        valid_proxy = types.MappingProxyType(
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "draw_index": 0,
                "prizes_last2": sample_valid_prizes_18,
                "tens_counts": sample_valid_tens_counts,
                "units_counts": sample_valid_units_counts,
            }
        )
        rec = CanonicalDrawRecord.model_validate(valid_proxy)
        assert rec.station_code == "XSHCM"
        assert rec.draw_index == 0

        # SA-11: Pre-validators must not mutate caller dictionaries in-place
        caller_feat_dict = {
            "station_code": "XSHCM",
            "cage_name": "tens_cage",
            "target_draw_index": 10,
            "target_draw_date": "2026-10-24",
            "history_length": 10,
            "regime_counts": {"5": [9] * 10},
            "regime_freqs": {"5": [0.1] * 10},
            "zero_hit_gaps": [0] * 10,
            "gap_z_scores": [0.0] * 10,
            "deficit_10_z_scores": [0.0] * 10,
            "burst_rebound_indicators": [0] * 10,
            "burst_rebound_rates": [0.1] * 10,
            "markov_transition_matrix": [_make_uniform_10() for _ in range(10)],
            "session_early_ratios": [0.5] * 10,
            "last_draw_counts": sample_valid_tens_counts,
        }
        feat = PreDrawFeatureVector.model_validate(caller_feat_dict)
        assert feat.last_draw_counts == sample_valid_tens_counts
        assert list(caller_feat_dict["regime_counts"].keys()) == ["5"]  # type: ignore[attr-defined]
        assert list(caller_feat_dict["regime_freqs"].keys()) == ["5"]  # type: ignore[attr-defined]

        caller_pred_dict = {
            "cage_name": "tens_cage",
            "target_draw_index": 519,
            "target_draw_date": "2026-10-24",
            "p_bocd": _make_uniform_10(),
            "p_seq": _make_uniform_10(),
            "p_ai": _make_uniform_10(),
            "weights": [0.2, 0.1],
            "uniform_weight": 0.7,
            "ranked_balls": list(range(10)),
            "top2_mean_prob": 0.10,
            "top2_lift_vs_uniform": 0.0,
            "exceeds_break_even_ball_threshold": False,
            "conviction_score": 0.0,
        }
        _ = CalibratedCagePrediction.model_validate(caller_pred_dict)
        assert isinstance(caller_pred_dict["weights"], list)

    def test_predraw_feature_vector_and_portfolio_metrics_value_constraints(
        self,
        sample_valid_tens_counts: list[int],
    ) -> None:
        base_kwargs = {
            "station_code": "XSHCM",
            "cage_name": "tens_cage",
            "target_draw_index": 10,
            "target_draw_date": "2026-10-24",
            "history_length": 10,
            "regime_counts": {5: [9] * 10},
            "regime_freqs": {5: [0.1] * 10},
            "zero_hit_gaps": [0] * 10,
            "gap_z_scores": [0.0] * 10,
            "deficit_10_z_scores": [0.0] * 10,
            "burst_rebound_indicators": [0] * 10,
            "burst_rebound_rates": [0.1] * 10,
            "markov_transition_matrix": [_make_uniform_10() for _ in range(10)],
            "session_early_ratios": [0.5] * 10,
            "last_draw_counts": sample_valid_tens_counts,
        }

        # Invalid regime_counts sum != 18 * min(w, history_length)
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "regime_counts": {5: [10] * 10}})  # type: ignore[arg-type]

        # Invalid regime_freqs sum != 1.0 or mismatched keys
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "regime_freqs": {5: [0.2] * 10}})  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "regime_freqs": {10: [0.1] * 10}})  # type: ignore[arg-type]

        # Invalid zero_hit_gaps (> history_length or < 0)
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "zero_hit_gaps": [11, *[0] * 9]})  # type: ignore[arg-type]

        # Invalid burst_rebound_indicators (not in {0, 1})
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "burst_rebound_indicators": [2, *[0] * 9]})  # type: ignore[arg-type]

        # Invalid burst_rebound_rates (> 1.0)
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "burst_rebound_rates": [1.5, *[0.1] * 9]})  # type: ignore[arg-type]

        # Invalid session_early_ratios (< 0.0 or > 1.0)
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "session_early_ratios": [-0.1, *[0.5] * 9]})  # type: ignore[arg-type]

        # Invalid last_draw_counts (sum != 18 or wrong length)
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "last_draw_counts": [1] * 10})  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            PreDrawFeatureVector(**{**base_kwargs, "last_draw_counts": [2] * 9})  # type: ignore[arg-type]

        # SweetSpotPortfolioMetrics rate bounds
        valid_pm = _make_sample_portfolio_metrics("2x2").model_dump()
        with pytest.raises(DataIntegrityError):
            SweetSpotPortfolioMetrics(
                **{**valid_pm, "daily_win_rate": 0.8, "zero_hit_rate_k0": 0.8}
            )
        with pytest.raises(DataIntegrityError):
            SweetSpotPortfolioMetrics(**{**valid_pm, "multi_hit_rate_ge2": 0.9})

    def test_simplex_tolerance_and_calibration_and_gatekeeper_cross_checks(self) -> None:
        # SB-08: validate_probability_simplex normalizes within tol=1e-5 and clamps tiny negative
        drifted = [0.1 + 5e-7] * 10
        normed = validate_probability_simplex(drifted, expected_len=10)
        assert abs(sum(normed) - 1.0) <= 1e-12

        tiny_neg = [-1e-12, 0.2, *[0.1] * 8]
        clamped = validate_probability_simplex(tiny_neg, expected_len=10)
        assert clamped[0] == 0.0
        assert abs(sum(clamped) - 1.0) <= 1e-12

        with pytest.raises(CalibrationIntegrityError):
            validate_probability_simplex([-1e-6, 0.1 + 1e-6, *[0.1] * 8], expected_len=10)

        w1, w2 = validate_pooling_weights(0.6, 0.4 + 5e-7)
        assert w1 + w2 <= 1.0
        assert math.isclose(w1 + w2, 1.0, abs_tol=1e-12)

        # SA-07: CalibratedCagePrediction convex combination and ranked_balls order check
        p_bocd = [0.19, 0.01, *[0.10] * 8]
        p_seq = [0.10] * 10
        # With w1=0.5, w2=0.2, uniform=0.3 -> p_ai[0] = 0.095 + 0.02 + 0.03 = 0.145
        p_ai_valid = [0.5 * b + 0.2 * s + 0.3 * 0.10 for b, s in zip(p_bocd, p_seq, strict=True)]
        ranked_valid = sorted(range(10), key=lambda b: (-p_ai_valid[b], b))
        pred = CalibratedCagePrediction(
            cage_name="tens_cage",
            target_draw_index=519,
            target_draw_date="2026-10-24",
            p_bocd=p_bocd,
            p_seq=p_seq,
            p_ai=p_ai_valid,
            weights=(0.5, 0.2),
            uniform_weight=0.3,
            ranked_balls=ranked_valid,
            top2_mean_prob=(p_ai_valid[ranked_valid[0]] + p_ai_valid[ranked_valid[1]]) / 2.0,
            top2_lift_vs_uniform=((p_ai_valid[ranked_valid[0]] + p_ai_valid[ranked_valid[1]]) / 0.2)
            - 1.0,
            exceeds_break_even_ball_threshold=True,
            conviction_score=50.0,
        )
        assert pred.ranked_balls[0] == 0

        # Mismatched p_ai vs convex combination must raise CalibrationIntegrityError
        with pytest.raises(CalibrationIntegrityError):
            CalibratedCagePrediction(
                cage_name="tens_cage",
                target_draw_index=519,
                target_draw_date="2026-10-24",
                p_bocd=p_bocd,
                p_seq=p_seq,
                p_ai=_make_uniform_10(),
                weights=(0.5, 0.2),
                uniform_weight=0.3,
                ranked_balls=list(range(10)),
                top2_mean_prob=0.10,
                top2_lift_vs_uniform=0.0,
                exceeds_break_even_ball_threshold=False,
                conviction_score=0.0,
            )

        # Misordered ranked_balls must raise CalibrationIntegrityError
        with pytest.raises(CalibrationIntegrityError):
            CalibratedCagePrediction(
                cage_name="tens_cage",
                target_draw_index=519,
                target_draw_date="2026-10-24",
                p_bocd=p_bocd,
                p_seq=p_seq,
                p_ai=p_ai_valid,
                weights=(0.5, 0.2),
                uniform_weight=0.3,
                ranked_balls=list(reversed(ranked_valid)),
                top2_mean_prob=(p_ai_valid[ranked_valid[0]] + p_ai_valid[ranked_valid[1]]) / 2.0,
                top2_lift_vs_uniform=(
                    (p_ai_valid[ranked_valid[0]] + p_ai_valid[ranked_valid[1]]) / 0.2
                )
                - 1.0,
                exceeds_break_even_ball_threshold=True,
                conviction_score=50.0,
            )

        # SA-08: CageFalsificationResult PASS_ALPHA requires p <= 0.05, BF10 >= 3.0, top2 >= BE
        with pytest.raises(DataIntegrityError):
            _make_sample_cage_falsification(
                "tens_cage",
                sample_size_draws=520,
                gate_status="PASS_ALPHA",
                multiplier=1.0,
            )

        # FalsificationReport overall_status must be consistent with tens_cage & units_cage
        with pytest.raises(DataIntegrityError):
            FalsificationReport(
                station_code="XSHCM",
                horizon="5y",
                sample_size_draws=520,
                null_simulations=1000,
                seed=42,
                tens_cage=_make_sample_cage_falsification("tens_cage", 520),
                units_cage=_make_sample_cage_falsification("units_cage", 520),
                overall_status="WARN_WEAK_SIGNAL",
                recommended_capital_multiplier=0.5,
            )

        # Stage3HandoffContract duplicate selected_numbers_2d or mismatched status must fail
        h5y = _make_sample_horizon_report("XSHCM", "5y", 520)
        h3y = _make_sample_horizon_report("XSHCM", "3y", 312)
        dist_19 = _make_valid_19_state_dist()
        with pytest.raises(DataIntegrityError):
            Stage3HandoffContract(
                station_code="XSHCM",
                as_of_draw_date="2026-10-24",
                as_of_draw_index=519,
                gatekeeper_status="FAIL_WHITE_NOISE_CASH_BRAKE",
                recommended_capital_multiplier=0.0,
                p_ai_tens=_make_uniform_10(),
                p_ai_units=_make_uniform_10(),
                conviction_score=0.0,
                recommended_portfolio_config="2x2",
                selected_numbers_2d=["00", "00", "10", "11"],
                hit_count_distribution_19=dist_19,
                horizon_5y_summary=h5y,
                horizon_3y_summary=h3y,
            )
        with pytest.raises(DataIntegrityError):
            Stage3HandoffContract(
                station_code="XSHCM",
                as_of_draw_date="2026-10-24",
                as_of_draw_index=519,
                gatekeeper_status="PASS_ALPHA",
                recommended_capital_multiplier=1.0,
                p_ai_tens=_make_uniform_10(),
                p_ai_units=_make_uniform_10(),
                conviction_score=0.0,
                recommended_portfolio_config="2x2",
                selected_numbers_2d=["00", "01", "10", "11"],
                hit_count_distribution_19=dist_19,
                horizon_5y_summary=h5y,
                horizon_3y_summary=h3y,
            )
