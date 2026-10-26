"""Tier 4 TDD Suite: Pillar 3 Dual-Branch Calibrated Probability Engine & SimplexCalibrationGate."""

from __future__ import annotations

import datetime
import math

import numpy as np
import pytest
from numpy.random import PCG64, Generator

from xsmn_alpha.constants import (
    BE_PROB_SINGLE_BALL,
    BOCD_MAX_RUN_LENGTH,
    BOCD_REGIME_LAMBDA,
    CAGE_NUM_BALLS,
    CANDIDATE_PAST_WINDOWS,
    DIRICHLET_PRIOR_ALPHA0,
    LAG1_EXHAUSTION_PENALTY,
    MARKOV_GAP_L2_PENALTY,
    POOLING_VAL_WINDOW,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
    compute_theoretical_noise_std,
)
from xsmn_alpha.engine.bocd_dirichlet import (
    BayesianDirichletBOCD,
    CausalPastWindowOptimizer,
    optimize_causal_past_window,
    predict_bocd_probabilities,
)
from xsmn_alpha.engine.calibration_pooler import (
    CalibratedProbabilityPooler,
    SimplexCalibrationGate,
    combine_convex_probabilities,
    compute_conviction_score,
    compute_multiclass_brier_score,
    validate_convex_weights,
    validate_simplex_probabilities,
)
from xsmn_alpha.engine.markov_gap_model import (
    RegularizedMarkovGapModel,
    predict_markov_gap_probabilities,
)
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    DataIntegrityError,
    TemporalLeakageError,
)
from xsmn_alpha.schemas import CanonicalDrawRecord


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
    assert len(tens_digits) == PRIZES_PER_DRAW
    assert len(units_digits) == PRIZES_PER_DRAW
    return [f"{t}{u}" for t, u in zip(tens_digits, units_digits, strict=True)]


def _build_canonical_draws_from_counts(
    tens_matrix: np.ndarray | list[list[int]],
    units_matrix: np.ndarray | list[list[int]] | None = None,
    station_code: str = "XSHCM",
) -> list[CanonicalDrawRecord]:
    """Construct contiguous CanonicalDrawRecord sequence from cage count matrices."""
    t_arr = np.asarray(tens_matrix, dtype=np.int64)
    u_arr = t_arr if units_matrix is None else np.asarray(units_matrix, dtype=np.int64)
    base_date = datetime.date(2024, 1, 1)
    records: list[CanonicalDrawRecord] = []
    for idx in range(t_arr.shape[0]):
        draw_date = (base_date + datetime.timedelta(days=idx * 3)).isoformat()
        prizes = _counts_to_prizes_last2(
            t_arr[idx].tolist(),
            u_arr[idx].tolist(),
        )
        records.append(
            CanonicalDrawRecord.from_prizes(
                station_code=station_code,  # type: ignore[arg-type]
                draw_date=draw_date,
                draw_index=idx,
                prizes_last2=prizes,
            )
        )
    return records


# ===========================================================================
# 1. Task 8 — Branch 1: BayesianDirichletBOCD Tests (-k "bocd")
# ===========================================================================


def test_bocd_dirichlet_run_length_and_predictive_simplex_invariants() -> None:
    """PASS: BOCD preserves sum(P(r_t)) == 1.0 and sum(P_BOCD(i)) == 1.0 +/- 1e-9 at every step."""
    rng = Generator(PCG64(seed=42))
    probs = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)
    counts_seq = rng.multinomial(PRIZES_PER_DRAW, probs, size=80)

    bocd = BayesianDirichletBOCD(
        max_run_length=BOCD_MAX_RUN_LENGTH,
        regime_lambda=BOCD_REGIME_LAMBDA,
        alpha0=DIRICHLET_PRIOR_ALPHA0,
    )

    # Initial state t=0 before any draws
    init_r_post = bocd.run_length_posterior
    init_pred = bocd.predict_proba()
    assert init_r_post.shape == (BOCD_MAX_RUN_LENGTH + 1,)
    assert abs(float(init_r_post.sum()) - 1.0) <= 1e-9
    assert abs(float(init_r_post[0]) - 1.0) <= 1e-12
    assert len(init_pred) == CAGE_NUM_BALLS
    assert abs(math.fsum(init_pred) - 1.0) <= 1e-9
    assert all(abs(p - UNIFORM_BALL_PROB) <= 1e-12 for p in init_pred)

    # Step through 80 draws and verify exact analytical conditional and marginal identities
    for t_step in range(counts_seq.shape[0]):
        draw_c = counts_seq[t_step]
        p_bocd = bocd.update(draw_c)
        r_post = bocd.run_length_posterior
        cond_mat = bocd.conditional_predictive_matrix()

        assert r_post.shape == (BOCD_MAX_RUN_LENGTH + 1,)
        assert np.all(np.isfinite(r_post))
        assert np.all(r_post >= 0.0)
        assert abs(float(r_post.sum()) - 1.0) <= 1e-9

        assert cond_mat.shape == (BOCD_MAX_RUN_LENGTH + 1, CAGE_NUM_BALLS)
        max_active_r = min(t_step + 1, BOCD_MAX_RUN_LENGTH)
        for r in range(max_active_r + 1):
            if r == 0:
                expected_cond = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB)
            else:
                win_sum = counts_seq[t_step + 1 - r : t_step + 1].sum(axis=0)
                expected_cond = (DIRICHLET_PRIOR_ALPHA0 + win_sum) / (
                    10.0 * DIRICHLET_PRIOR_ALPHA0 + 18.0 * float(r)
                )
            np.testing.assert_allclose(cond_mat[r], expected_cond, atol=1e-12)

        expected_marginal = r_post @ cond_mat
        np.testing.assert_allclose(bocd._predict_proba_array(), expected_marginal, atol=1e-12)
        np.testing.assert_allclose(p_bocd, bocd.predict_lag1_adjusted_proba(), atol=1e-12)
        np.testing.assert_allclose(p_bocd, bocd.predict_proba(), atol=1e-12)
        assert abs(math.fsum(p_bocd) - 1.0) <= 1e-9


@pytest.mark.parametrize(
    "post_changepoint_draw",
    [
        # Scenario A: Hot balls reverse from (0, 1) to (8, 9); old hot balls get normal ~1-2 hits
        [2, 1, 1, 1, 1, 1, 1, 1, 5, 4],
        # Scenario B: Hot balls reverse from (0, 1) to (8, 9); old hot balls get 1 hit each
        [1, 1, 1, 1, 1, 1, 1, 1, 5, 5],
        # Scenario C: Hot balls reverse from (0, 1) to (8, 9); old hot balls get 0 hits each
        [0, 0, 1, 1, 1, 1, 2, 2, 5, 5],
    ],
)
def test_bocd_dirichlet_changepoint_adaptation_within_4_draws(
    post_changepoint_draw: list[int],
) -> None:
    """PASS (Task 8 AC2): At t=100 regime reversal, BOCD pulls old hot balls to 10% +/- 0.8%."""
    bocd = BayesianDirichletBOCD(
        max_run_length=BOCD_MAX_RUN_LENGTH,
        regime_lambda=BOCD_REGIME_LAMBDA,
        alpha0=DIRICHLET_PRIOR_ALPHA0,
    )

    # Regime 1 (draws 0..99): Balls 0 and 1 are strongly hot (4 hits each per draw = 22.2%)
    regime1_draw = [4, 4, 1, 1, 1, 1, 2, 2, 1, 1]
    for _ in range(100):
        bocd.update(regime1_draw)

    pre_shift_probs = bocd.predict_proba()
    assert pre_shift_probs[0] > 0.17
    assert pre_shift_probs[1] > 0.17
    assert bocd.map_run_length >= 15

    # Regime 2 (draws 100..103): Station replaces ball set (reversing hot balls to 8 and 9)
    post_shift_probs_trace: list[list[float]] = []
    for _ in range(4):
        p_t = bocd.update(post_changepoint_draw)
        post_shift_probs_trace.append(list(p_t))

    final_probs = post_shift_probs_trace[-1]
    # Posterior must shift weight to short run lengths (r <= 4)
    assert bocd.short_run_mass(max_r=4) > 0.85
    assert bocd.map_run_length <= 4

    # Old hot balls (0 and 1) must be pulled back to 10.0% baseline within < 0.8% error (0.008)
    assert abs(final_probs[0] - UNIFORM_BALL_PROB) < 0.008, (
        f"Old hot ball 0 prob {final_probs[0]:.5f} not within 0.008 of 0.10"
    )
    assert abs(final_probs[1] - UNIFORM_BALL_PROB) < 0.008, (
        f"Old hot ball 1 prob {final_probs[1]:.5f} not within 0.008 of 0.10"
    )
    assert abs(math.fsum(final_probs) - 1.0) <= 1e-9


def test_bocd_dirichlet_negative_mutations_and_cutoff_gate() -> None:
    """FAIL (Negative Mutation): BOCD rejects invalid counts, bad params, and temporal leakage."""
    with pytest.raises(DataIntegrityError):
        BayesianDirichletBOCD(max_run_length=0)
    with pytest.raises(DataIntegrityError):
        BayesianDirichletBOCD(regime_lambda=0.5)  # hazard_rate > 1
    with pytest.raises(DataIntegrityError):
        BayesianDirichletBOCD(alpha0=-1.0)
    with pytest.raises(DataIntegrityError):
        BayesianDirichletBOCD(hazard_rate=float("nan"))

    bocd = BayesianDirichletBOCD()
    with pytest.raises(DataIntegrityError, match="sum"):
        bocd.update([2, 2, 2, 2, 2, 2, 2, 2, 2, 2])  # sum == 20 != 18
    with pytest.raises(DataIntegrityError):
        bocd.update([2, 2, 2, 2, 2, 2, 2, 2, 2])  # length == 9 != 10
    with pytest.raises(DataIntegrityError):
        bocd.update([-1, 3, 2, 2, 2, 2, 2, 2, 2, 2])  # negative count

    # Temporal leakage check via CanonicalDrawRecord interface
    counts = np.tile([2, 2, 2, 2, 2, 2, 2, 2, 1, 1], (20, 1))
    draws = _build_canonical_draws_from_counts(counts)
    valid_probs = predict_bocd_probabilities(draws[:15], target_draw=draws[15])
    assert abs(math.fsum(valid_probs) - 1.0) <= 1e-9

    with pytest.raises(TemporalLeakageError):
        predict_bocd_probabilities(draws[:16], target_draw=draws[15])


# ===========================================================================
# 2. Task 8 — Branch 2: RegularizedMarkovGapModel Tests (-k "markov")
# ===========================================================================


def test_markov_gap_model_simplex_and_l2_shrinkage_invariants() -> None:
    """PASS: RegularizedMarkovGapModel outputs valid P_Seq and shrinks under L2 / temperature."""
    counts_list: list[list[int]] = []
    for t in range(40):
        if t % 2 == 0:
            counts_list.append([4, 2, 2, 2, 2, 1, 1, 1, 2, 1])
        else:
            counts_list.append([1, 1, 2, 2, 2, 6, 1, 1, 1, 1])

    draws = _build_canonical_draws_from_counts(counts_list)
    model_default = RegularizedMarkovGapModel(
        l2_penalty=MARKOV_GAP_L2_PENALTY,
        temperature=1.0,
    )
    p_seq = model_default.fit_predict(draws[:39], draws[39], cage_name="tens_cage")

    assert len(p_seq) == CAGE_NUM_BALLS
    assert all(math.isfinite(p) and p > 0.0 for p in p_seq)
    assert abs(math.fsum(p_seq) - 1.0) <= 1e-9
    assert p_seq[5] > UNIFORM_BALL_PROB
    assert int(np.argmax(p_seq)) == 5

    # Increasing L2 penalty or Softmax temperature must shrink P_Seq closer to uniform 0.10
    model_heavy_l2 = RegularizedMarkovGapModel(l2_penalty=500.0, temperature=2.5)
    p_seq_shrunk = model_heavy_l2.fit_predict(draws[:39], draws[39], cage_name="tens_cage")
    assert abs(math.fsum(p_seq_shrunk) - 1.0) <= 1e-9
    dev_default = max(abs(p - UNIFORM_BALL_PROB) for p in p_seq)
    dev_shrunk = max(abs(p - UNIFORM_BALL_PROB) for p in p_seq_shrunk)
    assert dev_shrunk < dev_default


def test_markov_gap_model_future_invariance_and_cutoff_gate() -> None:
    """PASS & FAIL: RegularizedMarkovGapModel enforces PreDrawCutoffGate and future invariance."""
    rng = Generator(PCG64(seed=123))
    probs = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB)
    counts_a = rng.multinomial(PRIZES_PER_DRAW, probs, size=35)
    counts_b = counts_a.copy()
    counts_b[25:] = np.tile([9, 9, 0, 0, 0, 0, 0, 0, 0, 0], (10, 1))

    draws_a = _build_canonical_draws_from_counts(counts_a)
    draws_b = _build_canonical_draws_from_counts(counts_b)

    p_seq_a = predict_markov_gap_probabilities(draws_a[:25], draws_a[25], cage_name="tens_cage")
    p_seq_b = predict_markov_gap_probabilities(draws_b[:25], draws_b[25], cage_name="tens_cage")
    np.testing.assert_allclose(p_seq_a, p_seq_b, atol=1e-12)

    with pytest.raises(TemporalLeakageError):
        predict_markov_gap_probabilities(draws_a[:26], draws_a[25], cage_name="tens_cage")

    with pytest.raises(CalibrationIntegrityError):
        RegularizedMarkovGapModel(l2_penalty=0.0)
    with pytest.raises(CalibrationIntegrityError):
        RegularizedMarkovGapModel(temperature=0.5)
    with pytest.raises(CalibrationIntegrityError):
        RegularizedMarkovGapModel(temperature=float("nan"))


# ===========================================================================
# 3. Task 9 — SimplexCalibrationGate & CalibratedProbabilityPooler Tests
# ===========================================================================


def test_simplex_calibration_gate_rejects_invalid_weights_and_probabilities() -> None:
    """FAIL (Negative Mutation — Task 9 AC2): SimplexCalibrationGate blocks invalid inputs."""
    # Manual check case from Task 9: w1 = 0.7, w2 = 0.5 -> w1 + w2 = 1.2 > 1.0
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(0.7, 0.5)
    with pytest.raises(CalibrationIntegrityError):
        SimplexCalibrationGate.validate_weights(0.7, 0.5)
    with pytest.raises(CalibrationIntegrityError):
        combine_convex_probabilities([0.1] * 10, [0.1] * 10, (0.7, 0.5))

    # Negative weights and non-finite weights
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(-0.05, 0.5)
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(0.3, -0.01)
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(float("nan"), 0.2)
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(True, 0.2)  # type: ignore[arg-type]

    # Probability simplex violations: negative element, sum != 1.0, NaN/Inf, wrong length
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([-0.05, 0.15, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([0.0995] * 10)  # sum = 0.995 != 1.0
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([0.105] * 10)  # sum = 1.05 != 1.0
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([float("nan")] + [0.1] * 9)
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([float("inf")] + [0.1] * 9)
    with pytest.raises(CalibrationIntegrityError):
        validate_simplex_probabilities([0.1] * 9)


def test_calibration_pooler_white_noise_shrinks_weights_and_beats_naive_brier() -> None:
    """PASS (Task 9 AC1 & AC3): On white noise, SLSQP shrinks weights near 0 and beats Naive."""
    rng = Generator(PCG64(seed=42))
    uniform_probs = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)
    white_noise_counts = rng.multinomial(PRIZES_PER_DRAW, uniform_probs, size=145)
    draws = _build_canonical_draws_from_counts(white_noise_counts)

    pooler = CalibratedProbabilityPooler(val_window=POOLING_VAL_WINDOW)

    # Verify across 100 consecutive sliding steps (t = 45 .. 144)
    ai_brier_list: list[float] = []
    naive_brier_list: list[float] = []
    for t in range(45, 145):
        pred = pooler.predict_draw(draws[:t], draws[t], cage_name="tens_cage")
        assert abs(math.fsum(pred.p_ai) - 1.0) <= 1e-9
        w1, w2 = pred.weights
        assert w1 >= 0.0 and w2 >= 0.0 and (w1 + w2) <= 1.0 + 1e-9

        actual_freq = np.asarray(draws[t].tens_counts, dtype=np.float64) / float(PRIZES_PER_DRAW)
        naive_freq = white_noise_counts[t - 15 : t].sum(axis=0) / float(15 * PRIZES_PER_DRAW)
        ai_brier_list.append(compute_multiclass_brier_score(pred.p_ai, actual_freq))
        naive_brier_list.append(compute_multiclass_brier_score(naive_freq, actual_freq))

    # On the final step of pure white noise, weights must shrink near 0 and P_AI near 10.0%
    last_pred = pooler.predict_draw(draws[:144], draws[144], cage_name="tens_cage")
    assert sum(last_pred.weights) < 0.20
    assert max(abs(p - UNIFORM_BALL_PROB) for p in last_pred.p_ai) < 0.008
    assert last_pred.oos_brier_score <= last_pred.naive_brier_score + 1e-9

    # Out-of-sample Multi-class Brier score across 100 steps <= Naive Rolling Frequency
    mean_oos_ai_brier = float(np.mean(ai_brier_list))
    mean_oos_naive_brier = float(np.mean(naive_brier_list))
    assert mean_oos_ai_brier <= mean_oos_naive_brier


def test_calibration_pooler_biased_regime_conviction_and_temporal_leakage() -> None:
    """PASS & FAIL: On biased data, pooler detects break-even lift (+6.9045%) and blocks leakage."""
    rng = Generator(PCG64(seed=99))
    biased_probs = np.array(
        [0.19, 0.19, 0.0775, 0.0775, 0.0775, 0.0775, 0.0775, 0.0775, 0.0775, 0.0775]
    )
    biased_counts = rng.multinomial(PRIZES_PER_DRAW, biased_probs, size=90)
    draws = _build_canonical_draws_from_counts(biased_counts)

    pooler = CalibratedProbabilityPooler(val_window=POOLING_VAL_WINDOW)
    pred = pooler.predict_draw(draws[:89], draws[89], cage_name="tens_cage")

    assert abs(math.fsum(pred.p_ai) - 1.0) <= 1e-9
    assert set(pred.ranked_balls[:2]) == {0, 1}
    assert pred.top2_mean_prob >= BE_PROB_SINGLE_BALL
    assert pred.exceeds_break_even_ball_threshold is True
    assert pred.conviction_score >= 50.0
    assert pred.oos_brier_score <= pred.naive_brier_score + 1e-9

    # Direct conviction_score boundary test and SimplexCalibrationGate.validate/enforce
    assert compute_conviction_score([0.10] * 10) == 0.0
    assert len(SimplexCalibrationGate.validate([0.10] * 10, weights=(0.3, 0.2))) == 10
    with pytest.raises(CalibrationIntegrityError):
        SimplexCalibrationGate.enforce([0.10] * 10, weights=(0.8, 0.5))

    # Exercise predict_from_features and fit_predict without target_draw
    from xsmn_alpha.features.extractor import extract_features

    feat_vec = extract_features(draws[:89], draws[89], cage="tens_cage")
    seq_model = RegularizedMarkovGapModel()
    probs_from_feat = seq_model.predict_from_features(feat_vec)
    assert abs(math.fsum(probs_from_feat) - 1.0) <= 1e-9
    assert len(seq_model.coefficients) == 4
    assert abs(math.fsum(predict_bocd_probabilities(draws[:20])) - 1.0) <= 1e-9
    assert abs(math.fsum(predict_markov_gap_probabilities(draws[:20])) - 1.0) <= 1e-9

    # Dual cages and walk-forward batch helper
    tens_pred, units_pred = pooler.predict_dual_cages(draws[:89], draws[89])
    assert tens_pred.cage_name == "tens_cage"
    assert units_pred.cage_name == "units_cage"
    assert abs(math.fsum(units_pred.p_ai) - 1.0) <= 1e-9

    wf_preds = pooler.walk_forward_cage_predictions(draws[:60], warmup_draws=45)
    assert len(wf_preds) == 15
    assert all(abs(math.fsum(p.p_ai) - 1.0) <= 1e-9 for p in wf_preds)

    # Temporal leakage check: passing draws[:80] for draws[79] must raise TemporalLeakageError
    with pytest.raises(TemporalLeakageError):
        pooler.predict_draw(draws[:80], draws[79], cage_name="tens_cage")


# ===========================================================================
# 4. Task 13 — Causal Past-Window Optimizer W*_{t-1} & Theoretical Noise Variance
# ===========================================================================


def test_theoretical_noise_std_exact_binomial_formula_and_validation() -> None:
    """PASS & FAIL (Task 13 & 14): compute_theoretical_noise_std(W) == 1 / sqrt(200 * W)."""
    expected_windows = (15, 20, 25, 30, 40, 50, 60)
    assert expected_windows == CANDIDATE_PAST_WINDOWS
    assert abs(LAG1_EXHAUSTION_PENALTY - 0.35) <= 1e-12

    for w in CANDIDATE_PAST_WINDOWS:
        sigma = compute_theoretical_noise_std(w)
        expected_sigma = math.sqrt((0.10 * 0.90) / (18.0 * float(w)))
        assert abs(sigma - (1.0 / math.sqrt(200.0 * float(w)))) <= 1e-15
        assert abs(sigma - expected_sigma) <= 1e-15

    # Specific check for W = 12 -> 1 / sqrt(2400) approx 0.0204124145
    assert abs(compute_theoretical_noise_std(12) - (1.0 / math.sqrt(2400.0))) <= 1e-12

    for bad_w in (0, -5, True, False, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            compute_theoretical_noise_std(bad_w)  # type: ignore[arg-type]


def test_lag1_burst_exhaustion_filter_prevents_rank1_inversion() -> None:
    """PASS (Task 14): Lag-1 Burst Exhaustion Filter demotes single-draw burst spikes at t-1."""
    optimizer = CausalPastWindowOptimizer()
    assert abs(optimizer.lag1_penalty - 0.35) <= 1e-12

    # Build a 20-draw history where Ball 0 and Ball 1 both lead with 44 total hits over W=20 draws,
    # EXCEPT Ball 0 got 6 hits in the very last draw (t-1 burst), whereas Ball 1 had steady hits.
    history = np.full((20, CAGE_NUM_BALLS), 2, dtype=np.int64)
    history[:, 8] = 1
    history[:, 9] = 1
    # Give Ball 1 steady 3 hits in draws 0..3 (total = 4*3 + 16*2 = 44 hits)
    for d_idx in range(4):
        history[d_idx, 1] = 3
        history[d_idx, d_idx + 2] = 1
    # On the final draw t-1 (index 19), Ball 0 explodes with 6 hits (total = 19*2 + 6 = 44 hits),
    # while Ball 1 has 2 hits.
    history[19] = np.array([6, 2, 1, 1, 1, 1, 2, 2, 1, 1], dtype=np.int64)
    assert int(history[:, 0].sum()) == 44
    assert int(history[:, 1].sum()) == 44

    p_adj = optimizer.compute_lag1_adjusted_window_proba(history, w_star=20)
    assert abs(float(np.sum(p_adj)) - 1.0) <= 1e-12
    # Steady leader Ball 1 must strictly outrank yesterday's burst spike Ball 0!
    assert p_adj[1] > p_adj[0]
    assert int(np.argmax(p_adj)) == 1

    # Negative burst prior weight in Branch 2 (RegularizedMarkovGapModel)
    seq_model = RegularizedMarkovGapModel()
    assert seq_model.coefficients[3] < 0.0

    with pytest.raises(DataIntegrityError):
        CausalPastWindowOptimizer(lag1_penalty=-0.1)


def test_causal_past_window_optimizer_future_invariance_and_no_noise_floor() -> None:
    """PASS (Task 13 AC1-AC4): CausalPastWindowOptimizer is invariant to draws[t:] & no floor."""
    rng = Generator(PCG64(seed=2026))
    # Construct history where balls 7 and 8 lead in tens_cage, and 3 and 4 lead in units_cage
    tens_probs = np.array([0.08, 0.08, 0.09, 0.09, 0.10, 0.10, 0.10, 0.13, 0.13, 0.10])
    units_probs = np.array([0.09, 0.09, 0.09, 0.135, 0.135, 0.09, 0.09, 0.09, 0.09, 0.10])
    t_counts_a = rng.multinomial(PRIZES_PER_DRAW, tens_probs, size=85)
    u_counts_a = rng.multinomial(PRIZES_PER_DRAW, units_probs, size=85)

    # Mutate draws[t:] (from index t=65 onwards) completely in copy B
    t_counts_b = t_counts_a.copy()
    u_counts_b = u_counts_a.copy()
    t_counts_b[65:] = np.tile([9, 9, 0, 0, 0, 0, 0, 0, 0, 0], (20, 1))
    u_counts_b[65:] = np.tile([0, 0, 0, 0, 0, 0, 0, 0, 9, 9], (20, 1))

    draws_a = _build_canonical_draws_from_counts(t_counts_a, u_counts_a)
    draws_b = _build_canonical_draws_from_counts(t_counts_b, u_counts_b)

    t_idx = 65
    w_tens_a, p_tens_a = optimize_causal_past_window(draws_a[:t_idx], draws_a[t_idx], "tens_cage")
    w_tens_b, p_tens_b = optimize_causal_past_window(draws_b[:t_idx], draws_b[t_idx], "tens_cage")
    assert w_tens_a in CANDIDATE_PAST_WINDOWS
    assert w_tens_a == w_tens_b
    np.testing.assert_allclose(p_tens_a, p_tens_b, atol=1e-15)

    w_units_a, p_units_a = optimize_causal_past_window(
        draws_a[:t_idx], draws_a[t_idx], "units_cage"
    )
    w_units_b, p_units_b = optimize_causal_past_window(
        draws_b[:t_idx], draws_b[t_idx], "units_cage"
    )
    assert w_units_a in CANDIDATE_PAST_WINDOWS
    assert w_units_a == w_units_b
    np.testing.assert_allclose(p_units_a, p_units_b, atol=1e-15)

    # Verify CalibratedProbabilityPooler is invariant to draws[t:] and never degenerates to 0..9
    pooler = CalibratedProbabilityPooler(val_window=POOLING_VAL_WINDOW)
    pred_tens_a = pooler.predict_draw(draws_a[:t_idx], draws_a[t_idx], cage_name="tens_cage")
    pred_tens_b = pooler.predict_draw(draws_b[:t_idx], draws_b[t_idx], cage_name="tens_cage")
    np.testing.assert_allclose(pred_tens_a.p_ai, pred_tens_b.p_ai, atol=1e-15)
    assert pred_tens_a.ranked_balls == pred_tens_b.ranked_balls
    assert pred_tens_a.ranked_balls != list(range(10))

    # Inspect source of calibration_pooler to guarantee noise_floor = 3.5e-4 is completely gone
    import inspect

    import xsmn_alpha.engine.calibration_pooler as cp_mod

    cp_src = inspect.getsource(cp_mod)
    assert "3.5e-4" not in cp_src
    assert "noise_floor" not in cp_src

    # Verify CausalPastWindowOptimizer validation errors
    with pytest.raises(DataIntegrityError):
        CausalPastWindowOptimizer(candidate_windows=())
    with pytest.raises(DataIntegrityError):
        CausalPastWindowOptimizer(candidate_windows=(-3, 5))
    with pytest.raises(DataIntegrityError):
        CausalPastWindowOptimizer(alpha0=0.0)
    with pytest.raises(DataIntegrityError):
        CausalPastWindowOptimizer(eval_lookback=0)


def test_slice_b_bocd_post_changepoint_regime_growth_and_online_batch_parity() -> None:
    """Verify SB-01 & SB-02: post-changepoint run-length growth and online/batch parity."""
    # 1. SB-01: After changepoint at draw 100, MAP run length is never locked at r=0 and grows
    bocd = BayesianDirichletBOCD()
    regime1 = [4, 4, 1, 1, 1, 1, 2, 2, 1, 1]
    regime2 = [0, 0, 1, 1, 1, 1, 2, 2, 5, 5]
    for _ in range(100):
        bocd.update(regime1)

    map_r_trace: list[int] = []
    p8_trace: list[float] = []
    for _ in range(45):
        p = bocd.update(regime2)
        map_r_trace.append(bocd.map_run_length)
        p8_trace.append(p[8])

    assert sum(1 for r in map_r_trace if r == 0) == 0
    assert map_r_trace[3] >= 4
    assert map_r_trace[19] >= 15
    assert p8_trace[19] > 0.20

    # 2. SB-02: Online update()/predict_proba() matches batch fit_predict() and preserves short_mass
    history = np.full((25, CAGE_NUM_BALLS), 2, dtype=np.int64)
    history[:, 8] = 1
    history[:, 9] = 1
    history[0, 0] = 3
    history[0, 7] = 1
    for d_idx in range(10, 14):
        history[d_idx, 1] = 3
        history[d_idx, d_idx - 8] = 1
    history[24] = np.array([6, 2, 1, 1, 1, 1, 2, 2, 1, 1], dtype=np.int64)

    bocd_online = BayesianDirichletBOCD()
    p_online: list[float] = []
    for row in history:
        p_online = bocd_online.update(row)

    bocd_batch = BayesianDirichletBOCD()
    p_fit = bocd_batch.fit_predict(history)

    np.testing.assert_allclose(p_online, p_fit, atol=1e-12)
    np.testing.assert_allclose(bocd_online.predict_proba(), p_fit, atol=1e-12)
    assert int(np.argmax(p_online)) == 1
    assert int(np.argmax(p_fit)) == 1

    bocd_dc = BayesianDirichletBOCD()
    for row in history[:20]:
        bocd_dc._update_unchecked(row.astype(np.float64))
    short_before = bocd_dc.short_run_mass(max_r=5)
    bocd_dc._apply_causal_window_posterior_concentration(15)
    short_after = bocd_dc.short_run_mass(max_r=5)
    assert abs(short_before - short_after) <= 1e-12

    b1 = BayesianDirichletBOCD()
    for row in history[:5]:
        b1.update(row)
    b2 = BayesianDirichletBOCD()
    b2.predict_rolling_history(history[:5])
    assert b1.optimal_past_window == b2.optimal_past_window == 5

    # 3. SB-08: compute_lag1_adjusted_window_proba rejects NaN, bad shape, bool w_star
    opt = CausalPastWindowOptimizer()
    with pytest.raises(DataIntegrityError):
        opt.compute_lag1_adjusted_window_proba(np.full((10, 10), np.nan), w_star=15)
    with pytest.raises(DataIntegrityError):
        opt.compute_lag1_adjusted_window_proba(np.ones((5, 3)), w_star=15)
    with pytest.raises(DataIntegrityError):
        opt.compute_lag1_adjusted_window_proba(history, w_star=True)  # type: ignore[arg-type]
    with pytest.raises(DataIntegrityError):
        opt.compute_lag1_adjusted_window_proba(history, w_star=0)


def test_slice_b_markov_gap_feature_parity_and_pooler_brier_invariants() -> None:
    """Verify SB-03, SB-05, SB-07, SB-08 in RegularizedMarkovGapModel and calibration_pooler."""
    from xsmn_alpha.features.extractor import extract_features
    from xsmn_alpha.schemas import validate_pooling_weights

    # 1. SB-03: predict_from_features matches fit_predict when balls have 1 hit at t-1
    rows = []
    for t in range(30):
        row = [0] * 10
        row[(3 * t) % 10] = 4
        row[(3 * t + 1) % 10] = 4
        row[(3 * t + 2) % 10] = 3
        for k in range(3, 10):
            row[(3 * t + k) % 10] = 1
        rows.append(row)
    rows[-1] = [4, 1, 1, 4, 1, 1, 3, 1, 1, 1]
    tens_mat = np.array(rows, dtype=np.int64)
    draws = _build_canonical_draws_from_counts(tens_mat, tens_mat)

    model = RegularizedMarkovGapModel()
    p_fit = model.fit_predict(draws[:-1], draws[-1], cage_name="tens_cage")
    feat_vec = extract_features(draws[:-1], draws[-1], cage="tens_cage")
    p_feat = model.predict_from_features(feat_vec)
    np.testing.assert_allclose(p_fit, p_feat, atol=1e-12)

    # Burst rebound sequence must not flip coef[3] (w_burst) positive
    burst_rebound_rows = [
        [3, 2, 2, 2, 2, 2, 2, 1, 1, 1]
        if t % 3 == 0
        else ([18, 0, 0, 0, 0, 0, 0, 0, 0, 0] if t % 3 == 1 else [2, 2, 2, 2, 2, 2, 2, 2, 1, 1])
        for t in range(60)
    ]
    model_pos = RegularizedMarkovGapModel()
    model_pos.fit_predict_counts(np.array(burst_rebound_rows, dtype=np.int64))
    assert model_pos.coefficients[3] < 0.0

    # 2. SB-05: Regime-shift validation window guarantees oos_brier <= naive_brier
    regime_a = np.tile([4, 4, 1, 1, 1, 1, 2, 2, 1, 1], (60, 1))
    regime_b = np.tile([1, 1, 1, 1, 1, 1, 2, 2, 4, 4], (30, 1))
    shift_counts = np.vstack([regime_a, regime_b])
    pooler = CalibratedProbabilityPooler()
    pred_shift = pooler.predict_cage(shift_counts, cage_name="tens_cage")
    assert pred_shift.oos_brier_score <= pred_shift.naive_brier_score

    # 3. SB-07 & SB-08: Brier NaN/shape validation and weight tolerance parity
    with pytest.raises(DataIntegrityError):
        compute_multiclass_brier_score([float("nan")] * 10, [0.1] * 10)
    with pytest.raises(DataIntegrityError):
        compute_multiclass_brier_score([0.3, 0.3, 0.4], [1.0, 2.0, 3.0])

    assert validate_convex_weights(-5e-7, 0.5) == validate_pooling_weights(-5e-7, 0.5) == (0.0, 0.5)
    w_rescaled = validate_convex_weights(0.6, 0.4 + 9e-7)
    assert sum(w_rescaled) <= 1.0 + 1e-15
