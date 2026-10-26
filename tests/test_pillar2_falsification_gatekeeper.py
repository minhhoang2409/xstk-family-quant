"""Tier 3 TDD Suite: Pillar 2 Multi-Window Statistical Tests & Falsification Gatekeeper."""

from __future__ import annotations

import datetime
import math

import numpy as np
import pytest
from scipy.special import gammaln
from scipy.stats import chi2

from xsmn_alpha.constants import (
    DIRICHLET_PRIOR_ALPHA0,
    FALSIFICATION_WINDOWS,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.falsification.stats_tests import (
    dirichlet_multinomial_bf10,
    markov_transition_chi_square_test,
    multinomial_chi_square_test,
    normalized_shannon_entropy,
    run_multi_window_tests,
    run_station_multi_window_tests,
    run_window_tests,
    validate_counts_matrix,
    wald_wolfowitz_runs_test,
)
from xsmn_alpha.ingest.canonicalizer import canonicalize_draws
from xsmn_alpha.schemas import CageWindowTestResult


def _build_balanced_60_draws_matrix() -> np.ndarray:
    """Construct a 60x10 count matrix where every 5-draw block sums to 9 per ball (flat)."""
    block_5 = np.array(
        [
            [2, 2, 2, 2, 2, 2, 2, 2, 1, 1],
            [2, 2, 2, 2, 2, 2, 1, 1, 2, 2],
            [2, 2, 2, 2, 1, 1, 2, 2, 2, 2],
            [2, 2, 1, 1, 2, 2, 2, 2, 2, 2],
            [1, 1, 2, 2, 2, 2, 2, 2, 2, 2],
        ],
        dtype=np.int64,
    )
    assert np.all(block_5.sum(axis=1) == 18)
    assert np.all(block_5.sum(axis=0) == 9)
    return np.tile(block_5, (12, 1))


class TestMultiWindowStatisticalTests:
    """Task 6 unit, log-space analytical, and negative mutation tests (matches -k 'stats')."""

    def test_stats_flat_counts_w30_invariants(self) -> None:
        # Manual verification case: flat counts O_i = 54 for W = 30 (M_W = 540)
        flat_o = [54] * 10
        chi2_val, p_val = multinomial_chi_square_test(flat_o, window_draws=30)
        bf10_val = dirichlet_multinomial_bf10(flat_o, alpha0=DIRICHLET_PRIOR_ALPHA0)
        h_norm_val = normalized_shannon_entropy(flat_o)

        assert chi2_val == 0.0
        assert p_val == 1.0
        assert math.isclose(h_norm_val, 1.0, abs_tol=1e-12)
        assert 0.0 < bf10_val < 1.0

        # Also verify via run_window_tests on 1D observed_counts and 2D balanced matrix
        res_1d = run_window_tests(flat_o, window_draws=30)
        assert isinstance(res_1d, CageWindowTestResult)
        assert res_1d.window_draws == 30
        assert res_1d.total_trials == 540
        assert res_1d.observed_counts == flat_o
        assert res_1d.chi2_stat == 0.0
        assert res_1d.chi2_p_value == 1.0
        assert math.isclose(res_1d.normalized_entropy, 1.0, abs_tol=1e-12)
        assert res_1d.bf10_dirichlet < 1.0
        assert res_1d.bf10 == res_1d.bf10_dirichlet
        assert res_1d.h_norm == res_1d.normalized_entropy
        assert res_1d.window == 30

        balanced_mat = _build_balanced_60_draws_matrix()
        multi_res = run_multi_window_tests(balanced_mat)
        assert [r.window_draws for r in multi_res] == list(FALSIFICATION_WINDOWS)
        for r in multi_res:
            w = r.window_draws
            expected_o = int(round(1.8 * w))
            assert r.observed_counts == [expected_o] * 10
            assert r.chi2_stat == 0.0
            assert r.chi2_p_value == 1.0
            assert math.isclose(r.normalized_entropy, 1.0, abs_tol=1e-12)
            assert r.bf10_dirichlet < 1.0

    def test_stats_biased_regime_bf10_chi2_and_entropy_analytical_formulas(self) -> None:
        # Construct a 60-draw matrix with strong physical bias on balls 0 and 1
        # Every draw has 4 hits on ball 0, 4 hits on ball 1, and 10 hits spread across balls 2..9
        biased_row = [4, 4, 2, 2, 1, 1, 1, 1, 1, 1]
        assert sum(biased_row) == 18
        biased_mat = np.tile(np.array(biased_row, dtype=np.int64), (60, 1))

        results = run_multi_window_tests(biased_mat)
        assert len(results) == 3

        for res in results:
            w = res.window_draws
            m_w = 18 * w
            obs = np.array(res.observed_counts, dtype=np.float64)
            exp_e = 0.10 * m_w

            # 1. Exact Chi-Square and p-value check
            expected_chi2 = float(np.sum((obs - exp_e) ** 2 / exp_e))
            expected_p = float(chi2.sf(expected_chi2, df=9))
            assert math.isclose(res.chi2_stat, expected_chi2, rel_tol=1e-12)
            assert math.isclose(res.chi2_p_value, expected_p, abs_tol=1e-12)

            # 2. Exact log-space Dirichlet-Multinomial BF10 check
            a0 = DIRICHLET_PRIOR_ALPHA0
            ln_p_h1 = float(gammaln(10.0 * a0) - gammaln(10.0 * a0 + m_w)) + float(
                np.sum(gammaln(a0 + obs) - gammaln(a0))
            )
            ln_p_h0 = float(m_w * math.log(0.10))
            expected_bf10 = float(math.exp(np.clip(ln_p_h1 - ln_p_h0, -700.0, 700.0)))
            assert math.isclose(res.bf10_dirichlet, expected_bf10, rel_tol=1e-12)
            assert res.bf10_dirichlet > 3.0  # Strong physical bias easily exceeds 3.0

            # 3. Exact Normalized Shannon Entropy check
            p_hat = obs / m_w
            expected_h = float(-np.sum(p_hat * np.log(p_hat)) / math.log(10.0))
            assert math.isclose(res.normalized_entropy, expected_h, rel_tol=1e-12)
            assert 0.0 < res.normalized_entropy < 1.0

        # Extreme concentration case: all hits on ball 0 -> H_norm == 0.0 and BF10 clipped cleanly
        extreme_obs = [1080, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        assert normalized_shannon_entropy(extreme_obs) == 0.0
        bf10_extreme = dirichlet_multinomial_bf10(extreme_obs)
        assert math.isfinite(bf10_extreme)
        assert bf10_extreme > 1e100

    def test_stats_wald_wolfowitz_runs_and_markov_transition_tests(self) -> None:
        # Build a 60-draw matrix where ball 0 alternates cleanly vs clusters in 2 long blocks
        # Clustered: first 30 draws ball 0 has 3 hits (active), next 30 draws ball 0 has 0 hits
        row_active = [3, 3, 2, 2, 2, 2, 1, 1, 1, 1]
        row_inactive = [0, 0, 3, 3, 2, 2, 2, 2, 2, 2]
        assert sum(row_active) == 18
        assert sum(row_inactive) == 18
        clustered_mat = np.vstack(
            [
                np.tile(row_active, (30, 1)),
                np.tile(row_inactive, (30, 1)),
            ]
        )

        # In clustered_mat (W=60), ball 0 has only 2 runs over 60 draws (30 ones then 30 zeros)
        min_p, max_z = wald_wolfowitz_runs_test(clustered_mat)
        assert max_z > 5.0
        assert min_p < 1e-6

        # Also test 1D binary sequence input to wald_wolfowitz_runs_test
        p_1d, z_1d = wald_wolfowitz_runs_test([1] * 15 + [0] * 15)
        assert z_1d > 4.0
        assert p_1d < 1e-4

        # Constant sequence (no transitions) returns (1.0, 0.0)
        p_const, z_const = wald_wolfowitz_runs_test([1] * 20)
        assert p_const == 1.0
        assert z_const == 0.0

        # Markov Transition Chi-Square on biased transition matrix
        m_chi2, m_p = markov_transition_chi_square_test(clustered_mat)
        assert m_chi2 > 20.0
        assert 0.0 <= m_p < 0.05

        # Station-level helper on CanonicalDrawRecord sequence
        start_dt = datetime.date(2024, 1, 1)
        raw_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": (start_dt + datetime.timedelta(days=i * 3)).isoformat(),
                "prizes_last2": [f"{(i + g * 7) % 100:02d}" for g in range(18)],
            }
            for i in range(60)
        ]
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        station_res = run_station_multi_window_tests(draws)
        assert set(station_res.keys()) == {"tens_cage", "units_cage"}
        assert len(station_res["tens_cage"]) == 3
        assert len(station_res["units_cage"]) == 3
        assert station_res["tens_cage"][0].runs_p_value == (
            station_res["tens_cage"][0].runs_test_min_p_value
        )
        assert station_res["tens_cage"][0].markov_p_value == (
            station_res["tens_cage"][0].markov_chi2_p_value
        )

    def test_stats_negative_mutations_sample_size_nan_inf_and_shape_fail(self) -> None:
        balanced_60 = _build_balanced_60_draws_matrix()

        # 1. Sample size T < 60 must raise InsufficientSampleSizeError immediately
        with pytest.raises(InsufficientSampleSizeError):
            run_multi_window_tests(balanced_60[:59])

        with pytest.raises(InsufficientSampleSizeError):
            validate_counts_matrix(balanced_60[:45])

        with pytest.raises(InsufficientSampleSizeError):
            run_window_tests(balanced_60[:10], window_draws=15)

        # 2. NaN or Inf in counts matrix must raise DataIntegrityError
        nan_mat = balanced_60.astype(np.float64).copy()
        nan_mat[10, 3] = float("nan")
        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(nan_mat)

        inf_mat = balanced_60.astype(np.float64).copy()
        inf_mat[5, 0] = float("inf")
        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(inf_mat)

        # 3. Negative values or row sum != 18 must raise DataIntegrityError
        neg_mat = balanced_60.copy()
        neg_mat[0, 0] = -1
        neg_mat[0, 1] = 3
        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(neg_mat)

        bad_sum_mat = balanced_60.copy()
        bad_sum_mat[20, 0] = 5
        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(bad_sum_mat)

        # 4. Wrong shape (!= (T, 10)) must raise DataIntegrityError
        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(balanced_60[:, :9])

        with pytest.raises(DataIntegrityError):
            validate_counts_matrix("invalid")  # type: ignore[arg-type]

        # 5. Invalid direct inputs to individual test functions
        res_alias = run_window_tests([54] * 10, window_draws=30)
        assert res_alias.entropy_norm == res_alias.normalized_entropy
        assert res_alias.runs_z_stat == res_alias.runs_test_max_abs_z

        # 1D count sequence (>= 2 threshold) in wald_wolfowitz_runs_test
        p_cnt, z_cnt = wald_wolfowitz_runs_test([3, 3, 3, 0, 0, 0])
        assert 0.0 <= p_cnt <= 1.0
        assert z_cnt >= 0.0

        with pytest.raises(DataIntegrityError):
            validate_counts_matrix([[1.5, 2.5, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 1.0, 1.0]] * 60)

        with pytest.raises(DataIntegrityError):
            validate_counts_matrix([["a"] * 10] * 60)  # type: ignore[list-item]

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test("invalid")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([54] * 9)

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([float("nan")] * 10)

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([54.5] + [54.0] * 9)

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([-1, 55, 54, 54, 54, 54, 54, 54, 54, 54])

        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([54] * 10, window_draws=15)

        with pytest.raises(DataIntegrityError):
            dirichlet_multinomial_bf10([54] * 10, alpha0=0.0)

        with pytest.raises(DataIntegrityError):
            normalized_shannon_entropy([0] * 10)

        with pytest.raises(DataIntegrityError):
            wald_wolfowitz_runs_test("invalid")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            wald_wolfowitz_runs_test([float("nan"), 1.0, 0.0])

        with pytest.raises(DataIntegrityError):
            markov_transition_chi_square_test(balanced_60[:1])

        with pytest.raises(DataIntegrityError):
            run_window_tests(balanced_60, window_draws=1)

        with pytest.raises(DataIntegrityError):
            run_multi_window_tests(balanced_60, windows=())

        with pytest.raises(DataIntegrityError):
            run_station_multi_window_tests("invalid")  # type: ignore[arg-type]

        with pytest.raises(InsufficientSampleSizeError):
            run_station_multi_window_tests([])

        with pytest.raises(DataIntegrityError):
            run_station_multi_window_tests([123] * 60)  # type: ignore[list-item]


class TestMonteCarloNullAndFalsificationGatekeeper:
    """Task 7 TDD suite: 1,000 Monte Carlo Null Benchmark (PCG64 seed=42) & Gatekeeper."""

    def test_monte_carlo_null_determinism_speed_and_percentiles(self) -> None:
        import time

        from xsmn_alpha.falsification.monte_carlo import (
            compute_empirical_mc_p_value,
            simulate_monte_carlo_null,
        )

        t0 = time.perf_counter()
        mc_run1 = simulate_monte_carlo_null(sample_size_draws=520, null_sims=1000, seed=42)
        elapsed = time.perf_counter() - t0
        mc_run2 = simulate_monte_carlo_null(sample_size_draws=520, null_sims=1000, seed=42)

        # Must complete 1,000 simulations in < 2.0 seconds via vectorized numpy
        assert elapsed < 2.0

        # 100% deterministic reproduction to 12+ decimal places across runs
        assert math.isclose(
            mc_run1.null_p90_chi2_max, mc_run2.null_p90_chi2_max, rel_tol=0.0, abs_tol=1e-12
        )
        assert math.isclose(
            mc_run1.null_p95_chi2_max, mc_run2.null_p95_chi2_max, rel_tol=0.0, abs_tol=1e-12
        )
        assert mc_run1.null_chi2_max_values == mc_run2.null_chi2_max_values
        assert mc_run1.p90 == mc_run1.null_p90_chi2_max
        assert mc_run1.p95 == mc_run1.null_p95_chi2_max
        assert mc_run1.null_chi2_max_p90 == mc_run1.null_p90_chi2_max
        assert mc_run1.null_chi2_max_p95 == mc_run1.null_p95_chi2_max

        # Multi-window max chi2 percentiles must exceed single-window chi2(df=9) percentiles
        single_w_p90 = float(chi2.ppf(0.90, df=9))
        single_w_p95 = float(chi2.ppf(0.95, df=9))
        assert mc_run1.null_p90_chi2_max > single_w_p90
        assert mc_run1.null_p95_chi2_max > single_w_p95
        assert mc_run1.null_p95_chi2_max > mc_run1.null_p90_chi2_max

        # Verify across all 4 station-horizon sample sizes (520, 312, 260, 156)
        for horizon_t in (520, 312, 260, 156):
            mc_h = simulate_monte_carlo_null(sample_size_draws=horizon_t, null_sims=1000, seed=42)
            assert mc_h.sample_size_draws == horizon_t
            assert mc_h.null_simulations == 1000
            assert len(mc_h.null_chi2_max_values) == 1000
            assert mc_h.null_p95_chi2_max > mc_h.null_p90_chi2_max > 14.0

        # Empirical p-value boundary checks
        assert math.isclose(mc_run1.empirical_p_value(0.0), 1.0, abs_tol=1e-12)
        assert mc_run1.empirical_p_value(mc_run1.null_p95_chi2_max) <= 0.06
        assert math.isclose(
            compute_empirical_mc_p_value(1e6, mc_run1.null_chi2_max_values),
            1.0 / 1001.0,
            abs_tol=1e-12,
        )

    def test_gatekeeper_synthetic_white_noise_immunity_cash_brake(self) -> None:
        from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
        from xsmn_alpha.falsification.monte_carlo import generate_synthetic_cage_history

        gatekeeper = FalsificationGatekeeper(null_sims=1000, seed=42)

        # 1. Balanced uniform 60-draw matrix -> strict FAIL_WHITE_NOISE_CASH_BRAKE
        balanced_60 = _build_balanced_60_draws_matrix()
        cage_res = gatekeeper.evaluate_cage(balanced_60, cage_name="tens_cage")
        assert cage_res.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert cage_res.recommended_capital_multiplier == 0.0
        assert cage_res.observed_chi2_max == 0.0
        assert cage_res.observed_bf10_max < 1.0
        assert cage_res.mc_p_value > 0.10

        # 2. Stochastic uniform white noise (p_i = 0.10) over 156 draws (XSVL 3Y)
        white_noise_tens = generate_synthetic_cage_history(
            sample_size_draws=156,
            ball_probs=[0.10] * 10,
            seed=42,
        )
        white_noise_units = generate_synthetic_cage_history(
            sample_size_draws=156,
            ball_probs=[0.10] * 10,
            seed=44,
        )
        report = gatekeeper.evaluate_station(
            white_noise_tens,
            white_noise_units,
            station_code="XSVL",
            horizon="3y",
        )
        assert report.station_code == "XSVL"
        assert report.horizon == "3y"
        assert report.sample_size_draws == 156
        assert report.tens_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert report.units_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert report.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert report.recommended_capital_multiplier == 0.0
        assert report.tens_cage.recommended_capital_multiplier == 0.0
        assert report.units_cage.recommended_capital_multiplier == 0.0

    def test_gatekeeper_synthetic_true_regime_bias_detection_pass_alpha(self) -> None:
        from xsmn_alpha.constants import BE_LIFT_SINGLE_BALL, BE_PROB_SINGLE_BALL
        from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
        from xsmn_alpha.falsification.monte_carlo import generate_synthetic_cage_history

        gatekeeper = FalsificationGatekeeper(null_sims=1000, seed=42)

        # Synthetic physical regime bias where top 2 balls achieve >= +9.0% calibrated lift
        # Raw probabilities: balls 0 & 1 biased upward, cold balls 8 & 9 suppressed
        biased_probs = [0.135, 0.130, 0.105, 0.100, 0.100, 0.095, 0.095, 0.090, 0.080, 0.070]
        biased_tens = generate_synthetic_cage_history(
            sample_size_draws=156,
            ball_probs=biased_probs,
            seed=42,
        )
        biased_units = generate_synthetic_cage_history(
            sample_size_draws=156,
            ball_probs=biased_probs,
            seed=43,
        )

        report = gatekeeper.evaluate_station(
            biased_tens,
            biased_units,
            station_code="XSVL",
            horizon="3y",
        )
        for cage in (report.tens_cage, report.units_cage):
            assert cage.gate_status == "PASS_ALPHA"
            assert cage.observed_chi2_max >= cage.null_chi2_max_p95
            assert cage.observed_bf10_max >= 3.0
            assert cage.mc_p_value <= 0.05
            assert cage.top2_calibrated_prob_mean >= BE_PROB_SINGLE_BALL
            assert cage.top2_calibrated_lift >= BE_LIFT_SINGLE_BALL
            assert cage.recommended_capital_multiplier == 1.0

        assert report.overall_status == "PASS_ALPHA"
        assert report.recommended_capital_multiplier == 1.0

    def test_gatekeeper_warn_weak_signal_and_canonical_draws_input(self) -> None:
        from xsmn_alpha.constants import BE_PROB_SINGLE_BALL
        from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper

        gatekeeper = FalsificationGatekeeper(null_sims=1000, seed=42)

        # Case A: Strong statistical deviation (ball 9 suppressed to 45 hits, balls 0..8 at 115 hits
        # over 60 draws -> chi2_60 = 40.83 > p95 and BF10 > 100 >= 3.0),
        # BUT top-2 Dirichlet-shrunk prob = (18 + 115) / 1260 = 0.10556 < BE_PROB_SINGLE_BALL
        rows_60: list[list[int]] = []
        rot_idx = 0
        for t in range(60):
            if t % 4 == 0:
                rows_60.append([2, 2, 2, 2, 2, 2, 2, 2, 2, 0])
            else:
                row = [2, 2, 2, 2, 2, 2, 2, 2, 2, 1]
                row[rot_idx % 9] = 1
                rot_idx += 1
                rows_60.append(row)
        one_cold_mat = np.array(rows_60, dtype=np.int64)
        res_dead = gatekeeper.evaluate_cage(one_cold_mat, cage_name="tens_cage")
        assert res_dead.observed_chi2_max > res_dead.null_chi2_max_p95
        assert res_dead.observed_bf10_max >= 3.0
        assert res_dead.top2_calibrated_prob_mean < BE_PROB_SINGLE_BALL
        assert res_dead.gate_status == "WARN_WEAK_SIGNAL"
        assert 0.0 < res_dead.recommended_capital_multiplier < 1.0

        # Case B: Explicit calibrated_probs passed with weak lift (< +6.9045%) on biased counts
        biased_row = [4, 4, 2, 2, 1, 1, 1, 1, 1, 1]
        biased_mat = np.tile(np.array(biased_row, dtype=np.int64), (60, 1))
        weak_cal_probs = [0.105, 0.104, 0.101, 0.100, 0.100, 0.100, 0.100, 0.100, 0.095, 0.095]
        res_weak_cal = gatekeeper.evaluate_cage(
            biased_mat,
            cage_name="units_cage",
            calibrated_probs=weak_cal_probs,
        )
        assert res_weak_cal.gate_status == "WARN_WEAK_SIGNAL"

        # Case C: Evaluate directly on a sequence of CanonicalDrawRecord
        start_dt = datetime.date(2024, 1, 1)
        raw_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": (start_dt + datetime.timedelta(days=i * 3)).isoformat(),
                "prizes_last2": ["00", "00", "01", "11"]
                + [f"{(g + 2) * 11:02d}" for g in range(8)]
                + ["23", "34", "45", "56", "67", "78"],
            }
            for i in range(60)
        ]
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        station_report = gatekeeper.falsify(draws, station_code="XSHCM", horizon="5y")
        assert station_report.station_code == "XSHCM"
        assert station_report.horizon == "5y"
        assert station_report.sample_size_draws == 60

    def test_gatekeeper_negative_mutations_sample_size_and_corrupted_inputs(self) -> None:
        from xsmn_alpha.exceptions import CalibrationIntegrityError
        from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
        from xsmn_alpha.falsification.monte_carlo import (
            compute_empirical_mc_p_value,
            generate_synthetic_cage_history,
            simulate_monte_carlo_null,
        )

        gatekeeper = FalsificationGatekeeper(null_sims=100, seed=42)
        balanced_60 = _build_balanced_60_draws_matrix()

        # 1. Sample size T < 60 must raise InsufficientSampleSizeError
        with pytest.raises(InsufficientSampleSizeError):
            simulate_monte_carlo_null(sample_size_draws=59, null_sims=100, seed=42)

        with pytest.raises(InsufficientSampleSizeError):
            generate_synthetic_cage_history(sample_size_draws=45)

        with pytest.raises(InsufficientSampleSizeError):
            gatekeeper.evaluate_cage(balanced_60[:59], cage_name="tens_cage")

        with pytest.raises(InsufficientSampleSizeError):
            gatekeeper.evaluate_station(balanced_60[:59], balanced_60[:59])

        # 2. NaN / Inf in counts or parameters must raise DataIntegrityError
        nan_mat = balanced_60.astype(np.float64).copy()
        nan_mat[0, 0] = float("nan")
        with pytest.raises(DataIntegrityError):
            gatekeeper.evaluate_cage(nan_mat, cage_name="tens_cage")

        inf_mat = balanced_60.astype(np.float64).copy()
        inf_mat[0, 0] = float("inf")
        with pytest.raises(DataIntegrityError):
            gatekeeper.evaluate_cage(inf_mat, cage_name="units_cage")

        with pytest.raises(DataIntegrityError):
            compute_empirical_mc_p_value(float("nan"), [10.0, 12.0])

        with pytest.raises(DataIntegrityError):
            compute_empirical_mc_p_value(10.0, [])

        with pytest.raises(DataIntegrityError):
            simulate_monte_carlo_null(sample_size_draws=60, null_sims=0, seed=42)

        # 3. Invalid calibrated_probs must raise CalibrationIntegrityError
        with pytest.raises(CalibrationIntegrityError):
            gatekeeper.evaluate_cage(
                balanced_60,
                cage_name="tens_cage",
                calibrated_probs=[0.20] * 10,
            )

        # 4. Additional boundary and negative mutation checks on MonteCarloNullResult & Gatekeeper
        from xsmn_alpha.falsification.gatekeeper import (
            estimate_dirichlet_calibrated_probs,
            evaluate_cage_falsification,
            evaluate_station_falsification,
        )
        from xsmn_alpha.falsification.monte_carlo import MonteCarloNullResult

        with pytest.raises(InsufficientSampleSizeError):
            MonteCarloNullResult(
                sample_size_draws=30,
                null_simulations=2,
                seed=42,
                windows=(15,),
                null_chi2_max_values=[10.0, 12.0],
                null_p90_chi2_max=11.0,
                null_p95_chi2_max=11.5,
            )

        with pytest.raises(DataIntegrityError):
            MonteCarloNullResult(
                sample_size_draws=60,
                null_simulations=3,
                seed=42,
                windows=(15,),
                null_chi2_max_values=[10.0, 12.0],
                null_p90_chi2_max=11.0,
                null_p95_chi2_max=11.5,
            )

        with pytest.raises(DataIntegrityError):
            MonteCarloNullResult(
                sample_size_draws=60,
                null_simulations=2,
                seed=42,
                windows=(15,),
                null_chi2_max_values=[10.0, 12.0],
                null_p90_chi2_max=15.0,
                null_p95_chi2_max=11.5,
            )

        with pytest.raises(DataIntegrityError):
            compute_empirical_mc_p_value(10.0, "invalid")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            compute_empirical_mc_p_value(10.0, [float("nan"), 12.0])

        with pytest.raises(DataIntegrityError):
            simulate_monte_carlo_null(sample_size_draws=True)  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            simulate_monte_carlo_null(sample_size_draws=60, null_sims=10, seed=True)  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            simulate_monte_carlo_null(sample_size_draws=60, null_sims=10, windows=())

        with pytest.raises(DataIntegrityError):
            simulate_monte_carlo_null(sample_size_draws=60, null_sims=10, windows=(1,))

        with pytest.raises(InsufficientSampleSizeError):
            simulate_monte_carlo_null(sample_size_draws=60, null_sims=10, windows=(15, 90))

        with pytest.raises(DataIntegrityError):
            generate_synthetic_cage_history(sample_size_draws="60")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            generate_synthetic_cage_history(sample_size_draws=60, seed=False)  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            estimate_dirichlet_calibrated_probs([])

        with pytest.raises(DataIntegrityError):
            estimate_dirichlet_calibrated_probs(run_multi_window_tests(balanced_60), alpha0=-1.0)

        with pytest.raises(DataIntegrityError):
            evaluate_cage_falsification(balanced_60, cage_name="bad_cage")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            evaluate_cage_falsification(balanced_60, windows=())

        # Standalone evaluate_cage_falsification & evaluate_station_falsification without mc_null
        standalone_cage = evaluate_cage_falsification(balanced_60, null_sims=50, seed=42)
        assert standalone_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"

        standalone_station = evaluate_station_falsification(
            balanced_60, balanced_60, null_sims=50, seed=42
        )
        assert standalone_station.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE"

        # Mixed station status: 1 cage PASS_ALPHA (modest lift) + 1 cage FAIL -> WARN_WEAK_SIGNAL
        biased_row = [4, 4, 2, 2, 1, 1, 1, 1, 1, 1]
        biased_60 = np.tile(np.array(biased_row, dtype=np.int64), (60, 1))
        mixed_report = gatekeeper.evaluate_station(
            biased_60,
            balanced_60,
            tens_calibrated_probs=[
                0.108,
                0.107,
                0.100,
                0.100,
                0.100,
                0.100,
                0.100,
                0.095,
                0.095,
                0.095,
            ],
            units_calibrated_probs=[0.10] * 10,
        )
        assert mixed_report.tens_cage.gate_status == "PASS_ALPHA"
        assert mixed_report.units_cage.gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
        assert mixed_report.overall_status == "WARN_WEAK_SIGNAL"
        assert mixed_report.recommended_capital_multiplier == 0.25

        with pytest.raises(DataIntegrityError):
            evaluate_station_falsification(balanced_60, balanced_60, station_code="BAD")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            evaluate_station_falsification(balanced_60, balanced_60, horizon="10y")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            evaluate_station_falsification("invalid")  # type: ignore[arg-type]

        with pytest.raises(InsufficientSampleSizeError):
            evaluate_station_falsification([])

        with pytest.raises(DataIntegrityError):
            evaluate_station_falsification([123] * 60)  # type: ignore[list-item]

        with pytest.raises(DataIntegrityError):
            evaluate_station_falsification(balanced_60, np.vstack([balanced_60, balanced_60[:5]]))

        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(null_sims=0)

        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(seed=True)  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(windows=())

        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(alpha0=0.0)

        with pytest.raises(DataIntegrityError):
            gatekeeper.evaluate_station("invalid")  # type: ignore[arg-type]

        with pytest.raises(InsufficientSampleSizeError):
            gatekeeper.evaluate_station([])

    def test_slice_b_adversarial_mutations_and_gatekeeper_pooler_parity(self) -> None:
        """Verify SB-04, SB-06, SB-07 fixes across stats_tests, monte_carlo, and gatekeeper."""
        from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler
        from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
        from xsmn_alpha.falsification.monte_carlo import MonteCarloNullResult

        # 1. SB-04: Gatekeeper with calibrated_probs=None matches pooled P_AI exactly
        balanced_block = np.array(
            [
                [2, 2, 2, 2, 2, 2, 2, 2, 1, 1],
                [2, 2, 2, 2, 2, 2, 1, 1, 2, 2],
                [2, 2, 2, 2, 1, 1, 2, 2, 2, 2],
                [2, 2, 1, 1, 2, 2, 2, 2, 2, 2],
                [1, 1, 2, 2, 2, 2, 2, 2, 2, 2],
            ],
            dtype=np.int64,
        )
        first_45 = np.tile([4, 4, 2, 1, 1, 1, 1, 1, 2, 1], (45, 1))
        last_15 = np.tile(balanced_block, (3, 1))
        recent_bias_60 = np.vstack([first_45, last_15])

        gk = FalsificationGatekeeper(null_sims=200, seed=42)
        rep_auto = gk.evaluate_station(
            recent_bias_60, recent_bias_60, station_code="XSVL", horizon="3y"
        )
        pooler = CalibratedProbabilityPooler(alpha0=gk.alpha0)
        p_tens = pooler.predict_cage(recent_bias_60, cage_name="tens_cage").p_ai
        p_units = pooler.predict_cage(recent_bias_60, cage_name="units_cage").p_ai
        rep_explicit = gk.evaluate_station(
            recent_bias_60,
            recent_bias_60,
            station_code="XSVL",
            horizon="3y",
            tens_calibrated_probs=p_tens,
            units_calibrated_probs=p_units,
        )
        assert rep_auto.overall_status == rep_explicit.overall_status
        assert (
            rep_auto.recommended_capital_multiplier == rep_explicit.recommended_capital_multiplier
        )
        assert (
            abs(
                rep_auto.tens_cage.top2_calibrated_prob_mean
                - rep_explicit.tens_cage.top2_calibrated_prob_mean
            )
            <= 1e-12
        )

        # 2. SB-06: Markov transition Chi-square normalizes by 1 / |A_{tau-1}| (no 9x inflation)
        w2 = np.array(
            [
                [2, 2, 2, 2, 2, 2, 2, 2, 2, 0],
                [4, 4, 2, 2, 1, 1, 1, 1, 1, 1],
            ],
            dtype=np.int64,
        )
        single_chi2, _ = multinomial_chi_square_test(w2[1], window_draws=1)
        m_chi2, _ = markov_transition_chi_square_test(w2)
        assert abs(m_chi2 - single_chi2) <= 1e-9

        # 3. SB-07: 1D count slice with {0, 1} never >= 2 returns (1.0, 0.0), and invalid types fail
        rows_01 = [
            [1, 3, 2, 2, 2, 2, 2, 2, 1, 1] if t % 2 == 0 else [0, 3, 3, 2, 2, 2, 2, 2, 1, 1]
            for t in range(30)
        ]
        mat_01 = np.array(rows_01, dtype=np.int64)
        p_slice, z_slice = wald_wolfowitz_runs_test(mat_01[:, 0])
        assert p_slice == 1.0 and z_slice == 0.0

        for bad_seq in (
            [-999.5, -12.3, 500.2, 9999.0, -1.0, 42.0],
            ["0", "1", "0", "1"],
            [True, False, True, False],
            [-1, 0, 1, 0],
            [19, 0, 1, 0],
        ):
            with pytest.raises(DataIntegrityError):
                wald_wolfowitz_runs_test(bad_seq)  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            wald_wolfowitz_runs_test(mat_01, active_threshold=True)  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            multinomial_chi_square_test([2, 2, 2, 2, 2, 2, 2, 2, 1, 1], window_draws=True)  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            dirichlet_multinomial_bf10([54] * 10, alpha0=True)  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(alpha0=True)  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            FalsificationGatekeeper(windows=(True, 30, 60))  # type: ignore[arg-type]
        with pytest.raises(DataIntegrityError):
            MonteCarloNullResult(
                sample_size_draws=60,
                null_simulations=2,
                seed=42,
                windows=(True, 30),  # type: ignore[arg-type]
                null_chi2_max_values=[10.0, 12.0],
                null_p90_chi2_max=11.8,
                null_p95_chi2_max=11.9,
            )
