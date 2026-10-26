"""Pillar 4C: Strict Step-by-Step Walk-Forward Backtest Runner & Stage 3 Handoff Builder."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import cast

import numpy as np

from xsmn_alpha.backtest.alpha_decay import compute_rank_ordered_alpha_decay
from xsmn_alpha.backtest.sweet_spot_sim import (
    compute_19_state_hit_distribution,
    compute_all_portfolio_19_state_distributions,
    compute_portfolio_set_probability,
    evaluate_all_sweet_spot_portfolios,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    DEFAULT_MONTE_CARLO_SIMS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_WARMUP_DRAWS,
    MIN_SAMPLE_SIZE_DRAWS,
    POOLING_VAL_WINDOW,
    PRIZES_PER_DRAW,
    REAL_PAYOUT_1D,
    STATION_CONFIG,
    SWEET_SPOT_CONFIGS,
    VALID_HORIZONS,
    VALID_STATIONS,
)
from xsmn_alpha.engine.calibration_pooler import (
    CalibratedProbabilityPooler,
    _compute_naive_rolling_predictions,
    compute_multiclass_brier_score,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
from xsmn_alpha.ingest.canonicalizer import slice_horizon
from xsmn_alpha.schemas import (
    CanonicalDrawRecord,
    DualHorizonStationReport,
    GatekeeperStatus,
    HorizonBacktestReport,
    HorizonCode,
    Stage3HandoffContract,
    StationCode,
)

_AS_OF_DRAW_DATE_REGISTRY: dict[tuple[str, str, int, str], str] = {}


def _compute_next_expected_draw_date(last_draw_date: str, station_code: str) -> str:
    """Compute the next scheduled draw date strictly after last_draw_date for station_code."""
    dt = datetime.date.fromisoformat(last_draw_date)
    cfg = STATION_CONFIG.get(station_code, {})
    weekdays = tuple(cfg.get("draw_days_of_week") or cfg.get("draw_weekdays") or ())
    if not weekdays:
        return (dt + datetime.timedelta(days=7)).isoformat()
    for step in range(1, 8):
        cand = dt + datetime.timedelta(days=step)
        if cand.weekday() in weekdays:
            return cand.isoformat()
    return (dt + datetime.timedelta(days=7)).isoformat()


def _compute_previous_expected_draw_date(target_draw_date: str, station_code: str) -> str:
    """Compute the previous scheduled draw date strictly before target_draw_date."""
    dt = datetime.date.fromisoformat(target_draw_date)
    cfg = STATION_CONFIG.get(station_code, {})
    weekdays = tuple(cfg.get("draw_days_of_week") or cfg.get("draw_weekdays") or ())
    if not weekdays:
        return (dt - datetime.timedelta(days=7)).isoformat()
    for step in range(1, 8):
        cand = dt - datetime.timedelta(days=step)
        if cand.weekday() in weekdays:
            return cand.isoformat()
    return (dt - datetime.timedelta(days=7)).isoformat()


class WalkForwardRunner:
    """Orchestrates strict step-by-step walk-forward evaluation across stations and horizons."""

    def __init__(
        self,
        *,
        warmup_draws: int = DEFAULT_WARMUP_DRAWS,
        val_window: int = POOLING_VAL_WINDOW,
        null_sims: int = DEFAULT_MONTE_CARLO_SIMS,
        seed: int = DEFAULT_RANDOM_SEED,
    ) -> None:
        if isinstance(warmup_draws, bool) or not isinstance(warmup_draws, int) or warmup_draws < 10:
            raise DataIntegrityError(
                f"warmup_draws must be an integer >= 10, got {warmup_draws!r}."
            )
        if isinstance(null_sims, bool) or not isinstance(null_sims, int) or null_sims < 10:
            raise DataIntegrityError(f"null_sims must be an integer >= 10, got {null_sims!r}.")
        self.warmup_draws: int = int(warmup_draws)
        self.val_window: int = int(val_window)
        self.null_sims: int = int(null_sims)
        self.seed: int = int(seed)
        self.pooler = CalibratedProbabilityPooler(val_window=self.val_window)
        self.gatekeeper = FalsificationGatekeeper(
            null_sims=self.null_sims,
            seed=self.seed,
        )

    def evaluate_horizon(
        self,
        draws: Sequence[CanonicalDrawRecord],
        *,
        station_code: str,
        horizon: str,
    ) -> HorizonBacktestReport:
        """Run complete walk-forward evaluation for a single station and horizon ('5y' or '3y')."""
        if station_code not in VALID_STATIONS:
            raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
        if horizon not in VALID_HORIZONS:
            raise DataIntegrityError(f"Invalid horizon {horizon!r}.")
        if not isinstance(draws, Sequence) or isinstance(draws, (str, bytes)):
            raise DataIntegrityError("draws must be a sequence of CanonicalDrawRecord.")

        total_draws = len(draws)
        if total_draws < MIN_SAMPLE_SIZE_DRAWS:
            raise InsufficientSampleSizeError(
                f"Sample size {total_draws} draws is below minimum {MIN_SAMPLE_SIZE_DRAWS}."
            )
        if total_draws <= self.warmup_draws:
            raise InsufficientSampleSizeError(
                f"Total draws ({total_draws}) must exceed warmup_draws ({self.warmup_draws})."
            )

        station_typed = cast(StationCode, station_code)
        horizon_typed = cast(HorizonCode, horizon)

        # 1. Step-by-step out-of-sample walk-forward predictions for t in warmup_draws .. T-1
        tens_wf_preds = self.pooler.walk_forward_cage_predictions(
            draws, warmup_draws=self.warmup_draws, cage_name="tens_cage"
        )
        units_wf_preds = self.pooler.walk_forward_cage_predictions(
            draws, warmup_draws=self.warmup_draws, cage_name="units_cage"
        )
        eval_draws = list(draws[self.warmup_draws :])

        # 2. Out-of-sample Rank-Ordered Alpha Decay (Rank 1 .. Rank 10)
        tens_decay = compute_rank_ordered_alpha_decay(
            tens_wf_preds, eval_draws, cage_name="tens_cage"
        )
        units_decay = compute_rank_ordered_alpha_decay(
            units_wf_preds, eval_draws, cage_name="units_cage"
        )

        # 3. Out-of-sample Multi-class Brier scores vs Naive Rolling Frequency
        tens_counts_all = np.array([d.tens_counts for d in draws], dtype=np.int64)
        units_counts_all = np.array([d.units_counts for d in draws], dtype=np.int64)

        tens_ai_mat = np.array([p.p_ai for p in tens_wf_preds], dtype=np.float64)
        units_ai_mat = np.array([p.p_ai for p in units_wf_preds], dtype=np.float64)
        tens_naive_mat = _compute_naive_rolling_predictions(tens_counts_all)[self.warmup_draws :]
        units_naive_mat = _compute_naive_rolling_predictions(units_counts_all)[self.warmup_draws :]

        tens_eval_counts = tens_counts_all[self.warmup_draws :]
        units_eval_counts = units_counts_all[self.warmup_draws :]

        tens_oos_brier = compute_multiclass_brier_score(tens_ai_mat, tens_eval_counts)
        tens_naive_brier = compute_multiclass_brier_score(tens_naive_mat, tens_eval_counts)
        units_oos_brier = compute_multiclass_brier_score(units_ai_mat, units_eval_counts)
        units_naive_brier = compute_multiclass_brier_score(units_naive_mat, units_eval_counts)

        # 4. Latest calibrated prediction at the end of the horizon (using all T draws)
        last_draw = draws[-1]
        next_draw_date = _compute_next_expected_draw_date(last_draw.draw_date, station_code)
        _AS_OF_DRAW_DATE_REGISTRY[
            (station_code, horizon, last_draw.draw_index + 1, next_draw_date)
        ] = last_draw.draw_date
        latest_tens_pred = self.pooler.predict_cage(
            tens_counts_all,
            cage_name="tens_cage",
            target_draw_index=last_draw.draw_index + 1,
            target_draw_date=next_draw_date,
        )
        latest_units_pred = self.pooler.predict_cage(
            units_counts_all,
            cage_name="units_cage",
            target_draw_index=last_draw.draw_index + 1,
            target_draw_date=next_draw_date,
        )

        # 5. Pillar 2 Statistical Falsification Gatekeeper on full horizon
        falsification_rep = self.gatekeeper.evaluate_station(
            draws,
            station_code=station_typed,
            horizon=horizon_typed,
            tens_calibrated_probs=latest_tens_pred.p_ai,
            units_calibrated_probs=latest_units_pred.p_ai,
        )

        # 6. Pillar 4 Sweet-Spot Portfolio Evaluation across all 8 configurations
        portfolio_metrics = evaluate_all_sweet_spot_portfolios(
            tens_wf_preds, units_wf_preds, eval_draws
        )

        return HorizonBacktestReport(
            station_code=station_typed,
            horizon=horizon_typed,
            total_draws=total_draws,
            warmup_draws=self.warmup_draws,
            evaluated_draws=len(eval_draws),
            falsification_report=falsification_rep,
            latest_tens_prediction=latest_tens_pred,
            latest_units_prediction=latest_units_pred,
            tens_rank_alpha_decay=tens_decay,
            units_rank_alpha_decay=units_decay,
            tens_oos_brier_score=tens_oos_brier,
            tens_naive_brier_score=tens_naive_brier,
            units_oos_brier_score=units_oos_brier,
            units_naive_brier_score=units_naive_brier,
            portfolio_metrics=portfolio_metrics,
        )

    def evaluate_station_dual_horizons(
        self,
        draws: Sequence[CanonicalDrawRecord],
        *,
        station_code: str,
        horizons: Sequence[str] = VALID_HORIZONS,
    ) -> DualHorizonStationReport:
        """Slice 5y and 3y horizons for station_code and run walk-forward evaluation on both."""
        if station_code not in VALID_STATIONS:
            raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
        if (
            not isinstance(horizons, Sequence)
            or isinstance(horizons, (str, bytes))
            or len(horizons) == 0
            or any(h not in VALID_HORIZONS for h in horizons)
        ):
            raise DataIntegrityError(
                f"horizons must be a non-empty subset of {VALID_HORIZONS}, got {horizons!r}."
            )

        draws_5y = slice_horizon(draws, station_code=station_code, horizon="5y")
        draws_3y = slice_horizon(draws, station_code=station_code, horizon="3y")

        rep_5y = self.evaluate_horizon(draws_5y, station_code=station_code, horizon="5y")
        rep_3y = self.evaluate_horizon(draws_3y, station_code=station_code, horizon="3y")

        cfg = STATION_CONFIG[station_code]
        return DualHorizonStationReport(
            station_code=cast(StationCode, station_code),
            station_name=str(cfg["name"]),
            draws_per_week=int(cfg["draws_per_week"]),
            horizon_5y=rep_5y,
            horizon_3y=rep_3y,
        )


def build_stage3_handoff_contract(
    station_report: DualHorizonStationReport,
    *,
    recommended_config: str = "2x2",
    horizons: Sequence[str] = VALID_HORIZONS,
) -> Stage3HandoffContract:
    """Build a validated Stage3HandoffContract from a DualHorizonStationReport.

    Uses the 3Y horizon (reflecting the current generation of cage/ball set) as the primary
    live probability source while embedding both 5Y and 3Y summaries for Stage 3 Kelly sizing.
    Reconciles 3Y and 5Y gatekeeper verdicts conservatively: if the active 3Y horizon hits
    'FAIL_WHITE_NOISE_CASH_BRAKE', capital multiplier is locked at 0.0; if 3Y is 'PASS_ALPHA'
    while 5Y is 'FAIL_WHITE_NOISE_CASH_BRAKE', status is conservatively scaled to
    'WARN_WEAK_SIGNAL' (0.25x); if 3Y is 'WARN_WEAK_SIGNAL', preserves 'WARN_WEAK_SIGNAL' (0.25x).
    """
    if recommended_config not in SWEET_SPOT_CONFIGS:
        raise DataIntegrityError(f"Unknown recommended_config {recommended_config!r}.")
    if (
        not isinstance(horizons, Sequence)
        or isinstance(horizons, (str, bytes))
        or len(horizons) == 0
        or any(h not in VALID_HORIZONS for h in horizons)
    ):
        raise DataIntegrityError(
            f"horizons must be a non-empty subset of {VALID_HORIZONS}, got {horizons!r}."
        )

    rep_3y = station_report.horizon_3y
    rep_5y = station_report.horizon_5y
    primary_rep = rep_5y if ("3y" not in horizons and "5y" in horizons) else rep_3y

    # Use active horizon's latest calibrated prediction for next draw
    p_tens = list(primary_rep.latest_tens_prediction.p_ai)
    p_units = list(primary_rep.latest_units_prediction.p_ai)
    conviction = 0.5 * (
        primary_rep.latest_tens_prediction.conviction_score
        + primary_rep.latest_units_prediction.conviction_score
    )

    status_3y = rep_3y.falsification_report.overall_status
    mult_3y = rep_3y.falsification_report.recommended_capital_multiplier
    status_5y = rep_5y.falsification_report.overall_status
    mult_5y = rep_5y.falsification_report.recommended_capital_multiplier

    gate_status: GatekeeperStatus
    if "3y" not in horizons and "5y" in horizons:
        gate_status = status_5y
        cap_mult = 0.0 if gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE" else mult_5y
    elif status_3y == "FAIL_WHITE_NOISE_CASH_BRAKE":
        gate_status = "FAIL_WHITE_NOISE_CASH_BRAKE"
        cap_mult = 0.0
    elif (
        status_3y == "PASS_ALPHA"
        and status_5y == "FAIL_WHITE_NOISE_CASH_BRAKE"
        and "5y" in horizons
    ):
        gate_status = "WARN_WEAK_SIGNAL"
        cap_mult = 0.25
    else:
        gate_status = status_3y
        cap_mult = 0.0 if gate_status == "FAIL_WHITE_NOISE_CASH_BRAKE" else mult_3y

    cfg_meta = SWEET_SPOT_CONFIGS[recommended_config]
    rec_trials = (
        1
        if (cfg_meta.get("game_type") == "duoi_1_giai" or cfg_meta.get("bet_type") == "duoi_1_giai")
        else PRIZES_PER_DRAW
    )
    selected_2d = select_sweet_spot_numbers(p_tens, p_units, recommended_config)
    p_set_rec = compute_portfolio_set_probability(p_tens, p_units, recommended_config)
    dist_19_rec = compute_19_state_hit_distribution(p_set_rec, num_trials=rec_trials)
    all_dists_19 = compute_all_portfolio_19_state_distributions(p_tens, p_units)

    reg_key = (
        station_report.station_code,
        primary_rep.horizon,
        primary_rep.latest_tens_prediction.target_draw_index,
        primary_rep.latest_tens_prediction.target_draw_date,
    )
    as_of_date = _AS_OF_DRAW_DATE_REGISTRY.get(reg_key)
    if as_of_date is None:
        as_of_date = _compute_previous_expected_draw_date(
            primary_rep.latest_tens_prediction.target_draw_date,
            station_report.station_code,
        )

    return Stage3HandoffContract(
        contract_version="stage2-to-stage3-v1",
        station_code=station_report.station_code,
        as_of_draw_date=as_of_date,
        as_of_draw_index=rep_5y.total_draws - 1,
        gatekeeper_status=gate_status,
        recommended_capital_multiplier=cap_mult,
        p_ai_tens=p_tens,
        p_ai_units=p_units,
        conviction_score=conviction,
        recommended_portfolio_config=recommended_config,
        selected_numbers_2d=selected_2d,
        hit_count_distribution_19=dist_19_rec,
        portfolio_hit_distributions_19=all_dists_19,
        horizon_5y_summary=rep_5y,
        horizon_3y_summary=rep_3y,
        real_payout_1d=REAL_PAYOUT_1D,
        bao_lo_payout_per_hit=BAO_LO_PAYOUT_PER_HIT,
    )
