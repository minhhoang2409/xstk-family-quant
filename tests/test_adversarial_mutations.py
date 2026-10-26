"""Adversarial Negative Mutation Suite: Direct Attacks on All 4 Fail-Closed Gates & CLI."""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.random import PCG64, Generator

from xsmn_alpha.cli import main as cli_main
from xsmn_alpha.constants import (
    CAGE_NUM_BALLS,
    PRIZES_PER_DRAW,
    UNIFORM_BALL_PROB,
)
from xsmn_alpha.engine.bocd_dirichlet import (
    BayesianDirichletBOCD,
    CausalPastWindowOptimizer,
    optimize_causal_past_window,
)
from xsmn_alpha.engine.calibration_pooler import (
    CalibratedProbabilityPooler,
    SimplexCalibrationGate,
    combine_convex_probabilities,
    validate_convex_weights,
    validate_simplex_probabilities,
)
from xsmn_alpha.engine.markov_gap_model import RegularizedMarkovGapModel
from xsmn_alpha.exceptions import (
    CalibrationIntegrityError,
    DataIntegrityError,
    InsufficientSampleSizeError,
    TemporalLeakageError,
)
from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
from xsmn_alpha.features.extractor import PreDrawCutoffGate, extract_features
from xsmn_alpha.ingest.canonicalizer import canonicalize_draws, save_canonical_draws
from xsmn_alpha.schemas import (
    CageFalsificationResult,
    CalibratedCagePrediction,
    CanonicalDrawRecord,
    Stage3HandoffContract,
)


def _valid_18_prizes() -> list[str]:
    return [
        "42",
        "18",
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


def _make_canonical_sequence(
    num_draws: int,
    station_code: str = "XSVL",
    seed: int = 42,
) -> list[CanonicalDrawRecord]:
    rng = Generator(PCG64(seed=seed))
    probs = np.full(CAGE_NUM_BALLS, UNIFORM_BALL_PROB, dtype=np.float64)
    t_mat = rng.multinomial(PRIZES_PER_DRAW, probs, size=num_draws)
    u_mat = rng.multinomial(PRIZES_PER_DRAW, probs, size=num_draws)
    base_date = datetime.date(2021, 1, 1)
    records: list[CanonicalDrawRecord] = []
    for idx in range(num_draws):
        dt = (base_date + datetime.timedelta(days=idx * 3)).isoformat()
        tens_digits: list[int] = []
        units_digits: list[int] = []
        for d, c in enumerate(t_mat[idx].tolist()):
            tens_digits.extend([d] * int(c))
        for d, c in enumerate(u_mat[idx].tolist()):
            units_digits.extend([d] * int(c))
        prizes = [f"{t}{u}" for t, u in zip(tens_digits, units_digits, strict=True)]
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
# Gate 1: DataSchemaGate Adversarial Mutations
# ===========================================================================


def test_gate1_data_schema_blocks_corrupted_draws_and_unicode_digits() -> None:
    """Gate 1 (DataSchemaGate) must reject <18 or >18 prizes, full-width Unicode, and bad counts."""
    prizes = _valid_18_prizes()

    # 1. Missing prize (17 prizes) or extra prize (19 prizes)
    with pytest.raises(DataIntegrityError):
        CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-24", 0, prizes[:17])
    with pytest.raises(DataIntegrityError):
        CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-24", 0, [*prizes, "99"])

    # 2. Full-width Unicode digits ("０８") or alphanumeric ("9A") or empty string ("")
    for bad_token in ("０８", "9A", "", "8", "123", "-1"):
        mutated = list(prizes)
        mutated[0] = bad_token
        with pytest.raises(DataIntegrityError):
            CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-24", 0, mutated)

    # 3. Duplicate draw_date or reversed chronological order in canonicalize_draws
    rec0 = CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-20", 0, prizes)
    rec1_dup = CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-20", 1, prizes)
    rec1_rev = CanonicalDrawRecord.from_prizes("XSHCM", "2026-10-18", 1, prizes)
    with pytest.raises(DataIntegrityError, match="Duplicate"):
        canonicalize_draws([rec0, rec1_dup], station_code="XSHCM")
    with pytest.raises(DataIntegrityError, match="Chronological"):
        canonicalize_draws([rec0, rec1_rev], station_code="XSHCM", require_sorted=True)

    # 4. Tampered tens_counts whose sum != 18 or mismatched with prizes_last2
    with pytest.raises(DataIntegrityError):
        CanonicalDrawRecord(
            station_code="XSHCM",
            draw_date="2026-10-24",
            draw_index=0,
            prizes_last2=prizes,
            tens_counts=[2, 2, 1, 2, 1, 1, 1, 2, 5, 0],  # sum == 17 != 18
            units_counts=rec0.units_counts,
        )
    with pytest.raises(DataIntegrityError):
        CanonicalDrawRecord(
            station_code="XSHCM",
            draw_date="2026-10-24",
            draw_index=0,
            prizes_last2=prizes,
            tens_counts=[3, 1, 1, 2, 1, 1, 1, 2, 5, 1],  # sum == 18, but doesn't match prizes
            units_counts=rec0.units_counts,
        )


# ===========================================================================
# Gate 2: PreDrawCutoffGate Adversarial Mutations
# ===========================================================================


def test_gate2_pre_draw_cutoff_blocks_lookahead_and_intradraw_leakage() -> None:
    """Gate 2 (PreDrawCutoffGate) must block any history containing draw_index >= target_draw."""
    draws = _make_canonical_sequence(25, station_code="XSHCM")
    target = draws[15]

    # 1. Passing target_draw itself in history (intra-draw / same-day leakage)
    with pytest.raises(TemporalLeakageError):
        PreDrawCutoffGate.enforce(draws[:16], target)
    with pytest.raises(TemporalLeakageError):
        extract_features(draws[:16], target)

    # 2. Passing future draws (t+1 .. t+5) in history (look-ahead leakage)
    with pytest.raises(TemporalLeakageError):
        extract_features(draws[:20], target)

    # 3. Non-contiguous history (missing draw 14 right before target 15)
    with pytest.raises(TemporalLeakageError):
        extract_features(draws[:14], target)

    # 4. Empty history or target_draw at index 0
    with pytest.raises(TemporalLeakageError):
        extract_features([], target)
    with pytest.raises(TemporalLeakageError):
        extract_features([draws[0]], draws[0])

    # 5. Cross-station contamination in history
    wrong_station_draw = CanonicalDrawRecord.from_prizes(
        "XSVL", draws[14].draw_date, 14, draws[14].prizes_last2
    )
    contaminated_history = [*draws[:14], wrong_station_draw]
    with pytest.raises(TemporalLeakageError):
        extract_features(contaminated_history, target)

    # 6. Engine branches, CausalPastWindowOptimizer, and pooler also enforce Gate 2
    bocd = BayesianDirichletBOCD()
    win_opt = CausalPastWindowOptimizer()
    seq_model = RegularizedMarkovGapModel()
    pooler = CalibratedProbabilityPooler()
    with pytest.raises(TemporalLeakageError):
        bocd.fit_predict(draws[:16], target_draw=target)
    with pytest.raises(TemporalLeakageError):
        win_opt.select_optimal_window(draws[:16], target_draw=target)
    with pytest.raises(TemporalLeakageError):
        optimize_causal_past_window(draws[:16], target_draw=target)
    with pytest.raises(TemporalLeakageError):
        seq_model.fit_predict(draws[:16], target_draw=target)
    with pytest.raises(TemporalLeakageError):
        pooler.predict_draw(draws[:16], target_draw=target)


# ===========================================================================
# Gate 3: SimplexCalibrationGate Adversarial Mutations
# ===========================================================================


def test_gate3_simplex_calibration_blocks_unnormalized_probs_and_nonconvex_weights() -> None:
    """Gate 3 (SimplexCalibrationGate) must reject non-simplex probabilities and invalid weights."""
    # 1. Convex weight sum > 1.0 (e.g., w1=0.7, w2=0.5 -> 1.2) or negative weights
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(0.7, 0.5)
    with pytest.raises(CalibrationIntegrityError):
        validate_convex_weights(-0.01, 0.4)
    with pytest.raises(CalibrationIntegrityError):
        combine_convex_probabilities([0.1] * 10, [0.1] * 10, (0.6, 0.6))

    # 2. Probability vectors with negative entries, NaN, Inf, or sum != 1.0
    for bad_probs in (
        [-0.01, 0.11, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
        [0.099] * 10,  # sum = 0.990
        [0.101] * 10,  # sum = 1.010
        [float("nan"), *([0.1] * 9)],
        [float("inf"), *([0.1] * 9)],
        [0.1] * 9,
    ):
        with pytest.raises(CalibrationIntegrityError):
            validate_simplex_probabilities(bad_probs)
        with pytest.raises(CalibrationIntegrityError):
            SimplexCalibrationGate.enforce(bad_probs)

    # 3. CalibratedCagePrediction schema rejects mismatched uniform_weight or invalid ranked_balls
    with pytest.raises(CalibrationIntegrityError):
        CalibratedCagePrediction(
            cage_name="tens_cage",
            target_draw_index=10,
            target_draw_date="2026-10-24",
            p_bocd=[0.1] * 10,
            p_seq=[0.1] * 10,
            p_ai=[0.1] * 10,
            weights=(0.3, 0.3),
            uniform_weight=0.9,  # != 1 - 0.3 - 0.3 = 0.4
            ranked_balls=list(range(10)),
            top2_mean_prob=0.1,
            top2_lift_vs_uniform=0.0,
            exceeds_break_even_ball_threshold=False,
            conviction_score=0.0,
        )


# ===========================================================================
# Gate 4: FalsificationGatekeeper Adversarial Mutations
# ===========================================================================


def test_gate4_falsification_gatekeeper_blocks_short_samples_and_white_noise() -> None:
    """Gate 4 (FalsificationGatekeeper) rejects T < 60 and locks multiplier = 0.0 on white noise."""
    draws_short = _make_canonical_sequence(59, station_code="XSVL", seed=42)
    gatekeeper = FalsificationGatekeeper(null_sims=100, seed=42)

    # 1. Sample size < 60 must raise InsufficientSampleSizeError
    with pytest.raises(InsufficientSampleSizeError):
        gatekeeper.evaluate_station(draws_short, station_code="XSVL", horizon="3y")

    # 2. Pure white noise (T = 156 draws, p_i = 0.10) must be locked at FAIL_WHITE_NOISE_CASH_BRAKE
    draws_wn = _make_canonical_sequence(156, station_code="XSVL", seed=42)
    rep_wn = gatekeeper.evaluate_station(draws_wn, station_code="XSVL", horizon="3y")
    assert rep_wn.overall_status == "FAIL_WHITE_NOISE_CASH_BRAKE"
    assert rep_wn.recommended_capital_multiplier == 0.0

    # 3. Constructing CageFalsificationResult with FAIL status and non-zero multiplier fails
    with pytest.raises(DataIntegrityError):
        CageFalsificationResult(
            cage_name="tens_cage",
            sample_size_draws=156,
            window_results=rep_wn.tens_cage.window_results,
            observed_chi2_max=rep_wn.tens_cage.observed_chi2_max,
            observed_bf10_max=rep_wn.tens_cage.observed_bf10_max,
            null_chi2_max_p90=rep_wn.tens_cage.null_chi2_max_p90,
            null_chi2_max_p95=rep_wn.tens_cage.null_chi2_max_p95,
            mc_p_value=rep_wn.tens_cage.mc_p_value,
            top2_calibrated_prob_mean=0.10,
            top2_calibrated_lift=0.0,
            gate_status="FAIL_WHITE_NOISE_CASH_BRAKE",
            recommended_capital_multiplier=0.5,  # illegal! must be 0.0
        )


def test_cli_falsify_and_run_pipeline_end_to_end_with_canonical_files(tmp_path: Path) -> None:
    """PASS: CLI falsify and run-pipeline execute end-to-end on canonical files."""
    canonical_dir = tmp_path / "canonical"
    reports_dir = tmp_path / "reports"
    handoff_dir = tmp_path / "outputs"

    draws_hcm = _make_canonical_sequence(520, station_code="XSHCM", seed=42)
    draws_vl = _make_canonical_sequence(260, station_code="XSVL", seed=99)
    save_canonical_draws(draws_hcm, canonical_dir / "XSHCM_canonical.json")
    save_canonical_draws(draws_vl, canonical_dir / "XSVL_canonical.json")

    rc_falsify = cli_main(
        [
            "falsify",
            "--stations",
            "XSHCM",
            "XSVL",
            "--horizons",
            "5y",
            "3y",
            "--null-sims",
            "30",
            "--seed",
            "42",
            "--canonical-dir",
            str(canonical_dir),
        ]
    )
    assert rc_falsify == 0

    rc_pipe = cli_main(
        [
            "run-pipeline",
            "--stations",
            "XSHCM",
            "XSVL",
            "--horizons",
            "5y",
            "3y",
            "--warmup",
            "45",
            "--null-sims",
            "30",
            "--seed",
            "42",
            "--canonical-dir",
            str(canonical_dir),
            "--out-dir",
            str(reports_dir),
            "--handoff-dir",
            str(handoff_dir),
        ]
    )
    assert rc_pipe == 0
    assert (handoff_dir / "stage3_handoff_XSHCM.json").exists()
    assert (handoff_dir / "stage3_handoff_XSVL.json").exists()
    assert (reports_dir / "stage2_dual_station_comparison.json").exists()
    assert (reports_dir / "stage2_dual_station_report.html").exists()

    import json

    for st in ("XSHCM", "XSVL"):
        raw = json.loads((handoff_dir / f"stage3_handoff_{st}.json").read_text(encoding="utf-8"))
        validated = Stage3HandoffContract.model_validate(raw)
        assert validated.station_code == st


def test_slice_c_adversarial_mutations_alpha_decay_and_sweet_spot() -> None:
    """Block Slice C mutations: bool/float/Unicode coercion, draw mutation, rank mismatch."""
    from xsmn_alpha.backtest.alpha_decay import compute_rank_ordered_alpha_decay
    from xsmn_alpha.backtest.sweet_spot_sim import (
        score_single_draw_portfolio,
        select_sweet_spot_numbers,
    )

    valid_counts = [[2, 2, 2, 2, 2, 2, 2, 2, 1, 1]]
    valid_ranks = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]]

    # 1. Reject booleans, floats, and full-width Unicode digits in ranked_balls & actual_counts
    for bad_ranks in (
        [[False, True, 2, 3, 4, 5, 6, 7, 8, 9]],
        [[0, 1, 2.9, 3, 4, 5, 6, 7, 8, 9]],
        [[0, 1, 2, "３", 4, 5, 6, 7, 8, 9]],
    ):
        with pytest.raises(DataIntegrityError):
            compute_rank_ordered_alpha_decay(bad_ranks, valid_counts)  # type: ignore[arg-type]

    for bad_counts in (
        [[True, True, 2, 2, 2, 2, 2, 2, 2, 2]],
        [[2, 2, 2.9, 2, 2, 2, 2, 2, 1, 1]],
        [[2, 2, "２", 2, 2, 2, 2, 2, 1, 1]],
    ):
        with pytest.raises(DataIntegrityError):
            compute_rank_ordered_alpha_decay(valid_ranks, bad_counts)  # type: ignore[arg-type]

    # 2. Reject in-place mutated CanonicalDrawRecord in score_single_draw_portfolio & alpha_decay
    rec = CanonicalDrawRecord.from_prizes("XSVL", "2026-10-23", 0, _valid_18_prizes())
    rec.prizes_last2[0] = "０８"
    with pytest.raises(DataIntegrityError):
        score_single_draw_portfolio([0.1] * 10, [0.1] * 10, rec, "2x2")
    with pytest.raises(DataIntegrityError):
        compute_rank_ordered_alpha_decay(valid_ranks, [rec])

    rec2 = CanonicalDrawRecord.from_prizes("XSVL", "2026-10-23", 0, _valid_18_prizes())
    rec2.tens_counts[0] = 18
    for idx in range(1, 10):
        rec2.tens_counts[idx] = 0
    with pytest.raises(DataIntegrityError):
        score_single_draw_portfolio([0.1] * 10, [0.1] * 10, rec2, "2x2")
    with pytest.raises(DataIntegrityError):
        compute_rank_ordered_alpha_decay(valid_ranks, [rec2])

    # 3. Reject CalibratedCagePrediction with inconsistent ranked_balls vs p_ai
    p_ai = [0.28, 0.17, 0.09, 0.08, 0.07, 0.07, 0.06, 0.06, 0.06, 0.06]
    pred_ok = CalibratedCagePrediction(
        cage_name="tens_cage",
        target_draw_index=10,
        target_draw_date="2026-10-24",
        p_bocd=p_ai,
        p_seq=p_ai,
        p_ai=p_ai,
        weights=(1.0, 0.0),
        uniform_weight=0.0,
        ranked_balls=list(range(10)),
        top2_mean_prob=0.225,
        top2_lift_vs_uniform=1.25,
        exceeds_break_even_ball_threshold=True,
        conviction_score=50.0,
    )
    pred_ok.ranked_balls.reverse()
    with pytest.raises(CalibrationIntegrityError):
        compute_rank_ordered_alpha_decay([pred_ok], valid_counts)
    with pytest.raises(CalibrationIntegrityError):
        select_sweet_spot_numbers(pred_ok, pred_ok, "2x2")
