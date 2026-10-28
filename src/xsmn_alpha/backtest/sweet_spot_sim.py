"""Pillar 4B: Sweet-Spot Portfolio Simulator & 19-State Kelly Hit Distribution."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy.special import gammaln, logsumexp

from xsmn_alpha.backtest.alpha_decay import rank_balls_from_probabilities
from xsmn_alpha.constants import (
    BAO_LO_PAYOUT_PER_HIT,
    CAGE_NUM_BALLS,
    KELLY_NUM_STATES,
    PRIZES_PER_DRAW,
    REAL_PAYOUT_1D,
    ROLLING_WINDOW_DRAWS,
    STAGE3_TICKET_CONFIGS,
    STAGE4_SWEET_SPOT_CONFIGS,
    STAGE4_TICKET_CONFIGS,
    SWEET_SPOT_CONFIGS,
)
from xsmn_alpha.exceptions import CalibrationIntegrityError, DataIntegrityError
from xsmn_alpha.schemas import (
    CalibratedCagePrediction,
    CanonicalDrawRecord,
    Stage3CanonicalDrawRecord,
    SweetSpotPortfolioMetrics,
    validate_probability_simplex,
    validate_two_digit_ascii,
)


def _extract_probs(
    item: Sequence[float] | np.ndarray | CalibratedCagePrediction,
) -> list[float]:
    """Extract and validate a 10-ball probability vector from prediction or sequence."""
    if isinstance(item, CalibratedCagePrediction):
        probs = validate_probability_simplex(list(item.p_ai), expected_len=CAGE_NUM_BALLS)
        raw_ranks = item.ranked_balls
        if not isinstance(raw_ranks, Sequence) or isinstance(raw_ranks, (str, bytes)):
            raise CalibrationIntegrityError("Invalid ranked_balls in CalibratedCagePrediction.")
        ranks: list[int] = []
        for b in raw_ranks:
            if isinstance(b, bool) or not isinstance(b, (int, np.integer)):
                raise CalibrationIntegrityError(
                    f"Ball index in ranked_balls must be strict int, got {b!r}."
                )
            ranks.append(int(b))
        expected_ranks = rank_balls_from_probabilities(probs)
        if ranks != expected_ranks:
            raise CalibrationIntegrityError(
                f"CalibratedCagePrediction.ranked_balls {ranks} does not match "
                f"p_ai ordering {expected_ranks}."
            )
        if (
            isinstance(item.conviction_score, bool)
            or not isinstance(item.conviction_score, (int, float))
            or float(item.conviction_score) < 0.0
            or float(item.conviction_score) > 100.0 + 1e-6
        ):
            raise CalibrationIntegrityError(
                f"CalibratedCagePrediction.conviction_score out of [0, 100]: "
                f"{item.conviction_score!r}."
            )
        return probs
    if isinstance(item, np.ndarray):
        if item.dtype == np.bool_:
            raise CalibrationIntegrityError("Boolean ndarray is not a valid probability simplex.")
        return validate_probability_simplex(item.tolist(), expected_len=CAGE_NUM_BALLS)
    return validate_probability_simplex(item, expected_len=CAGE_NUM_BALLS)


_extract_prob_array = _extract_probs
rank_balls_by_probability = rank_balls_from_probabilities


def select_sweet_5_numbers(
    probs_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    probs_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
) -> tuple[list[str], list[str], list[str]]:
    """Select the 5-number 'sweet_5' portfolio (4 core '2x2' numbers + 1 top satellite number).

    Returns:
        (selected_5_sorted, core_4_sorted, satellite_1_list)
    """
    pt = _extract_probs(probs_tens)
    pu = _extract_probs(probs_units)
    ranks_t = rank_balls_from_probabilities(pt)
    ranks_u = rank_balls_from_probabilities(pu)

    core_set = {f"{a}{b}" for a in ranks_t[:2] for b in ranks_u[:2]}
    top3_box = {f"{a}{b}" for a in ranks_t[:3] for b in ranks_u[:3]} - core_set

    # Rank all remaining 96 two-digit numbers by:
    # 1) Joint probability P_tens(a) * P_units(b) descending (within 1e-12 tolerance)
    # 2) Membership in Top-3x3 box outside 2x2 (1 if in top3_box else 0) descending
    # 3) Lexicographical ASCII token "00".."99" ascending
    raw_candidates: list[tuple[float, int, str]] = []
    for a in range(CAGE_NUM_BALLS):
        for b in range(CAGE_NUM_BALLS):
            tok = f"{a}{b}"
            if tok in core_set:
                continue
            joint_p = float(pt[a]) * float(pu[b])
            in_top3 = 1 if tok in top3_box else 0
            raw_candidates.append((joint_p, in_top3, tok))

    max_p = max(c[0] for c in raw_candidates)
    top_tier = [c for c in raw_candidates if max_p - c[0] <= 1e-12]
    best_sat = min(top_tier, key=lambda c: (-c[1], c[2]))[2]
    core_sorted = sorted(core_set)
    selected_sorted = sorted([*core_sorted, best_sat])
    return (selected_sorted, core_sorted, [best_sat])


def select_sweet_spot_numbers(
    p_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    p_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    config_id: str,
) -> list[str]:
    """Select the sorted 2-digit number set S_{A x B} for a given Sweet-Spot configuration."""
    if config_id not in STAGE4_SWEET_SPOT_CONFIGS:
        raise DataIntegrityError(
            f"Unknown config_id {config_id!r}; must be in {sorted(STAGE4_SWEET_SPOT_CONFIGS)}."
        )
    probs_t = _extract_probs(p_tens)
    probs_u = _extract_probs(p_units)
    if config_id == "sweet_5":
        selected_5, _, _ = select_sweet_5_numbers(probs_t, probs_u)
        return selected_5

    ranks_t = rank_balls_from_probabilities(probs_t)
    ranks_u = rank_balls_from_probabilities(probs_u)

    if config_id == "core_2x2_sat_3x3":
        core_nums = sorted(f"{a}{b}" for a in ranks_t[:2] for b in ranks_u[:2])
        core_set = set(core_nums)
        sat_nums = sorted(
            f"{a}{b}" for a in ranks_t[:3] for b in ranks_u[:3] if f"{a}{b}" not in core_set
        )
        return core_nums + sat_nums

    cfg = STAGE4_SWEET_SPOT_CONFIGS[config_id]
    if config_id == "negative_filter_87":
        # Rank all 100 2-digit numbers by joint probability P_tens(a) * P_units(b) descending
        scored_pairs: list[tuple[float, str]] = []
        for a in range(CAGE_NUM_BALLS):
            for b in range(CAGE_NUM_BALLS):
                scored_pairs.append((probs_t[a] * probs_u[b], f"{a}{b}"))
        scored_pairs.sort(key=lambda pair: (-pair[0], pair[1]))
        top_n = int(cfg["num_numbers"])
        selected = [num for _, num in scored_pairs[:top_n]]
        return sorted(selected)

    top_a = int(cfg["tens_top_k"])
    top_b = int(cfg["units_top_k"])
    tens_balls = ranks_t[:top_a]
    units_balls = ranks_u[:top_b]
    selected = [f"{a}{b}" for a in tens_balls for b in units_balls]
    return sorted(selected)


def select_hybrid_core_satellite_sets(
    p_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    p_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
) -> tuple[set[str], set[str]]:
    """Return (S_Core_2x2, S_Sat_5) sets for 'core_2x2_sat_3x3' hybrid portfolio."""
    core_list = select_sweet_spot_numbers(p_tens, p_units, "2x2")
    full_3x3 = select_sweet_spot_numbers(p_tens, p_units, "3x3")
    core_set = set(core_list)
    sat_set = set(full_3x3) - core_set
    return core_set, sat_set


def compute_portfolio_set_probability(
    p_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    p_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    config_id: str = "2x2",
) -> float:
    """Compute single-prize hit probability p_S = sum_{(a,b) in S} P_tens(a) * P_units(b).

    For 'core_2x2_sat_3x3', returns the stake-weighted effective single-prize probability
    p_eff = 1.0 * p_core_2x2 + 0.5 * p_sat_only_5 so expected effective hits = 18 * p_eff.
    """
    if config_id not in STAGE4_SWEET_SPOT_CONFIGS:
        raise DataIntegrityError(f"Unknown config_id {config_id!r}.")
    probs_t = _extract_probs(p_tens)
    probs_u = _extract_probs(p_units)
    if config_id == "core_2x2_sat_3x3":
        core_set, sat_set = select_hybrid_core_satellite_sets(probs_t, probs_u)
        p_core = sum(
            probs_t[ord(tok[0]) - 48] * probs_u[ord(tok[1]) - 48] for tok in sorted(core_set)
        )
        p_sat = sum(
            probs_t[ord(tok[0]) - 48] * probs_u[ord(tok[1]) - 48] for tok in sorted(sat_set)
        )
        p_eff = 1.0 * p_core + 0.5 * p_sat
        return float(max(0.0, min(1.0, p_eff)))

    selected_nums = select_sweet_spot_numbers(probs_t, probs_u, config_id)
    p_sum = 0.0
    for token in selected_nums:
        a = ord(token[0]) - 48
        b = ord(token[1]) - 48
        p_sum += probs_t[a] * probs_u[b]
    return float(max(0.0, min(1.0, p_sum)))


def compute_19_state_hit_distribution(
    p_set: float,
    *,
    num_trials: int | None = None,
    num_prizes: int = PRIZES_PER_DRAW,
) -> list[float]:
    """Compute exact 19-state Binomial distribution P_AI(K = k | S) for k in 0..18.

    Supports num_trials=18 (for Bao Lô 18 prizes) and num_trials=1 (for Giải Đuôi ĐB 1 prize).
    """
    if (
        isinstance(p_set, bool)
        or not isinstance(p_set, (int, float))
        or not math.isfinite(p_set)
        or float(p_set) < -1e-9
        or float(p_set) > 1.0 + 1e-9
    ):
        raise CalibrationIntegrityError(
            f"Portfolio single-prize hit probability p_set must be in [0, 1], got {p_set!r}."
        )
    trials = num_prizes if num_trials is None else num_trials
    if (
        isinstance(trials, bool)
        or not isinstance(trials, int)
        or trials not in (1, PRIZES_PER_DRAW)
    ):
        raise DataIntegrityError(f"num_trials must be 1 or {PRIZES_PER_DRAW}, got {trials!r}.")

    p = float(max(0.0, min(1.0, float(p_set))))
    if trials == 1:
        dist = [0.0] * KELLY_NUM_STATES
        dist[0] = 1.0 - p
        dist[1] = p
        return validate_probability_simplex(dist, expected_len=KELLY_NUM_STATES)

    if p <= 1e-15:
        dist = [0.0] * KELLY_NUM_STATES
        dist[0] = 1.0
        return dist
    if p >= 1.0 - 1e-15:
        dist = [0.0] * KELLY_NUM_STATES
        dist[PRIZES_PER_DRAW] = 1.0
        return dist

    k_grid = np.arange(KELLY_NUM_STATES, dtype=np.float64)
    n_val = float(PRIZES_PER_DRAW)
    log_comb = gammaln(n_val + 1.0) - gammaln(k_grid + 1.0) - gammaln(n_val - k_grid + 1.0)
    log_probs = log_comb + k_grid * math.log(p) + (n_val - k_grid) * math.log(1.0 - p)
    log_probs -= float(logsumexp(log_probs))
    probs = np.exp(log_probs)
    probs = np.maximum(0.0, probs)
    probs /= float(np.sum(probs))
    return validate_probability_simplex(probs.tolist(), expected_len=KELLY_NUM_STATES)


def compute_all_portfolio_19_state_distributions(
    p_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    p_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
) -> dict[str, list[float]]:
    """Compute 19-state hit count distributions across all Sweet-Spot configurations."""
    distributions: dict[str, list[float]] = {}
    for cfg_id, cfg in SWEET_SPOT_CONFIGS.items():
        p_s = compute_portfolio_set_probability(p_tens, p_units, cfg_id)
        is_single_prize = (
            cfg.get("game_type") == "duoi_1_giai" or cfg.get("bet_type") == "duoi_1_giai"
        )
        trials = 1 if is_single_prize else PRIZES_PER_DRAW
        distributions[cfg_id] = compute_19_state_hit_distribution(p_s, num_trials=trials)
    return distributions


def score_single_draw_portfolio(
    p_tens: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    p_units: Sequence[float] | np.ndarray | CalibratedCagePrediction,
    actual_prizes_or_draw: Sequence[str] | CanonicalDrawRecord | Stage3CanonicalDrawRecord,
    config_id: str,
) -> dict[str, Any]:
    """Score a single draw for config_id per Stage 1 cash-flow rules (spec.md Section 5.3.D)."""
    if config_id not in STAGE4_SWEET_SPOT_CONFIGS:
        raise DataIntegrityError(f"Unknown config_id {config_id!r}.")

    if isinstance(actual_prizes_or_draw, (CanonicalDrawRecord, Stage3CanonicalDrawRecord)):
        if len(actual_prizes_or_draw.prizes_last2) != PRIZES_PER_DRAW:
            raise DataIntegrityError(
                f"Draw record must have {PRIZES_PER_DRAW} prizes, "
                f"got {len(actual_prizes_or_draw.prizes_last2)}."
            )
        prizes_last2 = [validate_two_digit_ascii(p) for p in actual_prizes_or_draw.prizes_last2]
        expected_tens = [0] * CAGE_NUM_BALLS
        expected_units = [0] * CAGE_NUM_BALLS
        for p in prizes_last2:
            expected_tens[ord(p[0]) - 48] += 1
            expected_units[ord(p[1]) - 48] += 1
        if (
            list(actual_prizes_or_draw.tens_counts) != expected_tens
            or list(actual_prizes_or_draw.units_counts) != expected_units
        ):
            raise DataIntegrityError("CanonicalDrawRecord counts do not match prizes_last2.")
    elif isinstance(actual_prizes_or_draw, Sequence) and not isinstance(
        actual_prizes_or_draw, (str, bytes)
    ):
        if len(actual_prizes_or_draw) != PRIZES_PER_DRAW:
            raise DataIntegrityError(
                f"actual_prizes_or_draw must have {PRIZES_PER_DRAW} prizes, "
                f"got {len(actual_prizes_or_draw)}."
            )
        prizes_last2 = [validate_two_digit_ascii(p) for p in actual_prizes_or_draw]
    else:
        raise DataIntegrityError("Invalid actual_prizes_or_draw input.")

    cfg = STAGE4_SWEET_SPOT_CONFIGS[config_id]
    game_type = str(cfg["game_type"])
    cost = float(cfg["cost_per_draw"])

    if game_type == "bao_lo_hybrid":
        core_set, sat_set = select_hybrid_core_satellite_sets(p_tens, p_units)
        core_hits = sum(1 for p in prizes_last2 if p in core_set)
        sat_hits = sum(1 for p in prizes_last2 if p in sat_set)
        raw_hits = core_hits + sat_hits
        equiv_hits = float(core_hits) + 0.5 * float(sat_hits)
        revenue = float(core_hits) * BAO_LO_PAYOUT_PER_HIT + float(sat_hits) * (
            0.5 * BAO_LO_PAYOUT_PER_HIT
        )
        net_profit = revenue - cost
        return {
            "config_id": config_id,
            "cost": cost,
            "revenue": revenue,
            "net_profit": net_profit,
            "raw_hits": raw_hits,
            "effective_hits": equiv_hits,
            "is_multi_hit_ge2": equiv_hits >= 2.0 - 1e-9,
            "core_hits": core_hits,
            "satellite_hits": sat_hits,
        }

    selected_set = set(select_sweet_spot_numbers(p_tens, p_units, config_id))
    if game_type == "duoi_1_giai":
        special_prize = prizes_last2[int(cfg["target_prize_index"])]
        hit = 1 if special_prize in selected_set else 0
        revenue = float(hit) * REAL_PAYOUT_1D
        net_profit = revenue - cost
        return {
            "config_id": config_id,
            "cost": cost,
            "revenue": revenue,
            "net_profit": net_profit,
            "raw_hits": hit,
            "effective_hits": float(hit),
            "is_multi_hit_ge2": False,
        }

    # Standard uniform 1.0đ/number Bao Lô 18 prizes
    hits = sum(1 for p in prizes_last2 if p in selected_set)
    revenue = float(hits) * BAO_LO_PAYOUT_PER_HIT
    net_profit = revenue - cost
    return {
        "config_id": config_id,
        "cost": cost,
        "revenue": revenue,
        "net_profit": net_profit,
        "raw_hits": hits,
        "effective_hits": float(hits),
        "is_multi_hit_ge2": float(hits) >= 2.0 - 1e-9,
    }


def evaluate_sweet_spot_portfolio(
    tens_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    units_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    evaluated_draws: Sequence[CanonicalDrawRecord | Stage3CanonicalDrawRecord | Sequence[str]],
    config_id: str,
) -> SweetSpotPortfolioMetrics:
    """Evaluate a Sweet-Spot configuration across an out-of-sample walk-forward sequence."""
    if config_id not in STAGE4_SWEET_SPOT_CONFIGS:
        raise DataIntegrityError(f"Unknown config_id {config_id!r}.")
    n_eval = len(evaluated_draws)
    if n_eval == 0 or len(tens_predictions) != n_eval or len(units_predictions) != n_eval:
        raise DataIntegrityError(
            "tens_predictions, units_predictions, and evaluated_draws must be non-empty "
            "sequences of identical length."
        )

    cfg = STAGE4_SWEET_SPOT_CONFIGS[config_id]
    cost_per_draw = float(cfg["cost_per_draw"])
    be_hits_30 = float(cfg["be_hits_30_draws"])

    total_cost = 0.0
    total_revenue = 0.0
    total_effective_hits = 0.0
    win_days = 0
    multi_hit_days = 0
    zero_hit_days = 0

    current_losing_streak = 0
    max_losing_streak = 0
    cum_profit = 0.0
    peak_profit = 0.0
    max_drawdown = 0.0

    for p_t, p_u, draw_item in zip(
        tens_predictions, units_predictions, evaluated_draws, strict=True
    ):
        step_res = score_single_draw_portfolio(p_t, p_u, draw_item, config_id)
        c_t = float(step_res["cost"])
        r_t = float(step_res["revenue"])
        net_t = float(step_res["net_profit"])
        raw_k = int(step_res["raw_hits"])
        eff_k = float(step_res["effective_hits"])

        total_cost += c_t
        total_revenue += r_t
        total_effective_hits += eff_k

        is_win_day = (
            raw_k >= int(cfg["min_hits_for_profit"])
            if (config_id == "sweet_5" and "min_hits_for_profit" in cfg)
            else net_t > 1e-9
        )
        if is_win_day:
            win_days += 1
            current_losing_streak = 0
        else:
            current_losing_streak += 1
            if current_losing_streak > max_losing_streak:
                max_losing_streak = current_losing_streak

        if eff_k >= 2.0 - 1e-9:
            multi_hit_days += 1
        if raw_k == 0:
            zero_hit_days += 1

        cum_profit += net_t
        if cum_profit > peak_profit:
            peak_profit = cum_profit
        dd = peak_profit - cum_profit
        if dd > max_drawdown:
            max_drawdown = dd

    net_profit = total_revenue - total_cost
    roi_pct = (net_profit / total_cost) * 100.0 if total_cost > 0.0 else 0.0
    hits_per_30 = (total_effective_hits / float(n_eval)) * float(ROLLING_WINDOW_DRAWS)

    return SweetSpotPortfolioMetrics(
        config_id=config_id,
        game_type=str(cfg["game_type"]),
        evaluated_draws=n_eval,
        cost_per_draw=cost_per_draw,
        total_cost=total_cost,
        total_revenue=total_revenue,
        net_profit=net_profit,
        roi_pct=roi_pct,
        total_hits=total_effective_hits,
        hits_per_30_draws=hits_per_30,
        break_even_hits_30_draws=be_hits_30,
        daily_win_rate=float(win_days) / float(n_eval),
        multi_hit_rate_ge2=float(multi_hit_days) / float(n_eval),
        zero_hit_rate_k0=float(zero_hit_days) / float(n_eval),
        max_losing_streak=max_losing_streak,
        max_drawdown=max_drawdown,
    )


def evaluate_all_sweet_spot_portfolios(
    tens_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    units_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    evaluated_draws: Sequence[CanonicalDrawRecord | Stage3CanonicalDrawRecord | Sequence[str]],
) -> dict[str, SweetSpotPortfolioMetrics]:
    """Evaluate all 8 Sweet-Spot configurations across the out-of-sample sequence."""
    return {
        cfg_id: evaluate_sweet_spot_portfolio(
            tens_predictions, units_predictions, evaluated_draws, cfg_id
        )
        for cfg_id in SWEET_SPOT_CONFIGS
    }


def evaluate_stage3_ticket_portfolios(
    tens_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    units_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    evaluated_draws: Sequence[CanonicalDrawRecord | Stage3CanonicalDrawRecord | Sequence[str]],
) -> dict[str, SweetSpotPortfolioMetrics]:
    """Evaluate all 5 Stage 3 ticket configurations (2x2, 1x4, 4x1, 3x3, core_2x2_sat_3x3)."""
    return {
        cfg_id: evaluate_sweet_spot_portfolio(
            tens_predictions, units_predictions, evaluated_draws, cfg_id
        )
        for cfg_id in STAGE3_TICKET_CONFIGS
    }


def evaluate_stage4_ticket_portfolios(
    tens_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    units_predictions: Sequence[Sequence[float] | np.ndarray | CalibratedCagePrediction],
    evaluated_draws: Sequence[CanonicalDrawRecord | Stage3CanonicalDrawRecord | Sequence[str]],
) -> dict[str, SweetSpotPortfolioMetrics]:
    """Evaluate all 6 Stage 4 ticket configurations (including 'sweet_5')."""
    return {
        cfg_id: evaluate_sweet_spot_portfolio(
            tens_predictions, units_predictions, evaluated_draws, cfg_id
        )
        for cfg_id in STAGE4_TICKET_CONFIGS
    }
