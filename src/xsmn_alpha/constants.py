"""Immutable Stage 1 financial constants, station configurations, and Sweet-Spot parameters."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

# ---------------------------------------------------------------------------
# 1. Stage 1 Cash-Flow & Break-Even Constants (Single Source of Truth)
# ---------------------------------------------------------------------------
REAL_PAYOUT_1D: Final[float] = 70.0 / 0.8  # 87.5 đồng per 1.0 đồng real capital
PRIZES_PER_DRAW: Final[int] = 18  # 18 prizes (Giải 8 -> Giải ĐB) per XSMN draw
CAGE_NUM_BALLS: Final[int] = 10  # Balls 0..9 in each cage (tens_cage, units_cage)
UNIFORM_BALL_PROB: Final[float] = 1.0 / CAGE_NUM_BALLS  # 0.10 (10.0%)
UNIFORM_2D_PROB: Final[float] = 0.01  # 1.0% for any 2-digit number 00..99

BAO_LO_PAYOUT_PER_HIT: Final[float] = REAL_PAYOUT_1D / PRIZES_PER_DRAW  # 87.5 / 18 = 175 / 36
BE_PROB_2D_NUMBER: Final[float] = 1.0 / REAL_PAYOUT_1D  # 1 / 87.5 ≈ 0.011428571428571429
BE_LIFT_2D_NUMBER: Final[float] = (BE_PROB_2D_NUMBER / UNIFORM_2D_PROB) - 1.0  # +14.2857%

BE_PROB_SINGLE_BALL: Final[float] = math.sqrt(100.0 / REAL_PAYOUT_1D) / 10.0  # 0.10690449676496976
BE_LIFT_SINGLE_BALL: Final[float] = (BE_PROB_SINGLE_BALL / UNIFORM_BALL_PROB) - 1.0  # +6.9045%

ROLLING_WINDOW_DRAWS: Final[int] = 30  # 30 draws = 540 prizes standard business cycle
ROLLING_WINDOW_PRIZES: Final[int] = ROLLING_WINDOW_DRAWS * PRIZES_PER_DRAW  # 540 prizes

# ---------------------------------------------------------------------------
# 2. Target Station Configurations (XSHCM: 2 draws/wk, XSVL: 1 draw/wk)
# ---------------------------------------------------------------------------
VALID_STATIONS: Final[frozenset[str]] = frozenset({"XSHCM", "XSVL"})
VALID_HORIZONS: Final[tuple[str, ...]] = ("5y", "3y")

StationConfigValue = int | str | tuple[int, ...] | Mapping[str, int]
SweetSpotConfigValue = int | float | str

STATION_CONFIG: Final[Mapping[str, Mapping[str, StationConfigValue]]] = MappingProxyType(
    {
        "XSHCM": MappingProxyType(
            {
                "station_code": "XSHCM",
                "name": "TP. Hồ Chí Minh",
                "draws_per_week": 2,
                "draw_days_of_week": (0, 5),  # Monday (0) and Saturday (5)
                "slug": "tp-hcm",
                "minhngoc_slug": "tp-hcm",
                "minhngoc_draws_per_page": 6,
                "minhngoc_step_days": 21,
                "xskt_slug": "xshcm-xstp",
                "xoso_slug": "xshcm",
                "horizons": MappingProxyType(
                    {
                        "5y": 520,
                        "3y": 312,
                    }
                ),
                "5y": 520,
                "3y": 312,
            }
        ),
        "XSVL": MappingProxyType(
            {
                "station_code": "XSVL",
                "name": "Vĩnh Long",
                "draws_per_week": 1,
                "draw_days_of_week": (4,),  # Friday (4)
                "slug": "vinh-long",
                "minhngoc_slug": "vinh-long",
                "minhngoc_draws_per_page": 7,
                "minhngoc_step_days": 49,
                "xskt_slug": "xsvl",
                "xoso_slug": "xsvl",
                "horizons": MappingProxyType(
                    {
                        "5y": 260,
                        "3y": 156,
                    }
                ),
                "5y": 260,
                "3y": 156,
            }
        ),
    }
)

# ---------------------------------------------------------------------------
# 3. Sweet-Spot Portfolio Configurations (Pillar 4)
# ---------------------------------------------------------------------------
SWEET_SPOT_CONFIGS: Final[Mapping[str, Mapping[str, SweetSpotConfigValue]]] = MappingProxyType(
    {
        "2x2": MappingProxyType(
            {
                "config_id": "2x2",
                "label": "Bộ 2x2 = 4 số (1.0đ/số)",
                "game_type": "bao_lo",
                "tens_top_k": 2,
                "units_top_k": 2,
                "num_numbers": 4,
                "cost_per_draw": 4.0,
                "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 1,
                "be_hits_30_draws": (30.0 * 4.0) / BAO_LO_PAYOUT_PER_HIT,  # 24.685714...
                "target_hits_30_draws": 25,
            }
        ),
        "3x3": MappingProxyType(
            {
                "config_id": "3x3",
                "label": "Bộ 3x3 = 9 số (1.0đ/số)",
                "game_type": "bao_lo",
                "tens_top_k": 3,
                "units_top_k": 3,
                "num_numbers": 9,
                "cost_per_draw": 9.0,
                "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 2,
                "be_hits_30_draws": (30.0 * 9.0) / BAO_LO_PAYOUT_PER_HIT,  # 55.542857...
                "target_hits_30_draws": 56,
            }
        ),
        "core_2x2_sat_3x3": MappingProxyType(
            {
                "config_id": "core_2x2_sat_3x3",
                "label": "Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ)",
                "game_type": "bao_lo_hybrid",
                "tens_top_k": 3,
                "units_top_k": 3,
                "core_tens_top_k": 2,
                "core_units_top_k": 2,
                "core_numbers": 4,
                "satellite_numbers": 5,
                "num_numbers": 9,
                "core_stake": 1.0,
                "satellite_stake": 0.5,
                "cost_per_draw": 6.5,
                "core_payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "satellite_payout_per_hit": 0.5 * BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 2,
                "be_hits_30_draws": (30.0 * 6.5) / BAO_LO_PAYOUT_PER_HIT,  # 40.114285...
                "target_hits_30_draws": 41,
            }
        ),
        "1x4": MappingProxyType(
            {
                "config_id": "1x4",
                "label": "Bộ 1x4 = 4 số (1.0đ/số)",
                "game_type": "bao_lo",
                "tens_top_k": 1,
                "units_top_k": 4,
                "num_numbers": 4,
                "cost_per_draw": 4.0,
                "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 1,
                "be_hits_30_draws": (30.0 * 4.0) / BAO_LO_PAYOUT_PER_HIT,
                "target_hits_30_draws": 25,
            }
        ),
        "2x7": MappingProxyType(
            {
                "config_id": "2x7",
                "label": "Bộ 2x7 = 14 số (1.0đ/số)",
                "game_type": "bao_lo",
                "tens_top_k": 2,
                "units_top_k": 7,
                "num_numbers": 14,
                "cost_per_draw": 14.0,
                "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 3,
                "be_hits_30_draws": (30.0 * 14.0) / BAO_LO_PAYOUT_PER_HIT,  # 86.4
                "target_hits_30_draws": 87,
            }
        ),
        "3x6": MappingProxyType(
            {
                "config_id": "3x6",
                "label": "Bộ 3x6 = 18 số (1.0đ/số)",
                "game_type": "bao_lo",
                "tens_top_k": 3,
                "units_top_k": 6,
                "num_numbers": 18,
                "cost_per_draw": 18.0,
                "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                "min_hits_for_profit": 4,
                "be_hits_30_draws": (30.0 * 18.0) / BAO_LO_PAYOUT_PER_HIT,  # 111.085714...
                "target_hits_30_draws": 112,
            }
        ),
        "negative_filter_81": MappingProxyType(
            {
                "config_id": "negative_filter_81",
                "label": "Negative Filter 9x9 = 81 số (Giải Đuôi ĐB)",
                "game_type": "duoi_1_giai",
                "target_prize_index": 17,
                "tens_top_k": 9,
                "units_top_k": 9,
                "num_numbers": 81,
                "excluded_numbers": 19,
                "cost_per_draw": 81.0,
                "payout_per_hit": REAL_PAYOUT_1D,
                "min_hits_for_profit": 1,
                "be_win_rate": 81.0 / REAL_PAYOUT_1D,
                "be_hits_30_draws": (30.0 * 81.0) / REAL_PAYOUT_1D,  # 27.771428...
                "target_hits_30_draws": 28,
            }
        ),
        "negative_filter_87": MappingProxyType(
            {
                "config_id": "negative_filter_87",
                "label": "Negative Filter Top 87 số (Loại 13 số thấp nhất - Giải Đuôi ĐB)",
                "game_type": "duoi_1_giai",
                "target_prize_index": 17,
                "tens_top_k": 10,
                "units_top_k": 10,
                "num_numbers": 87,
                "excluded_numbers": 13,
                "cost_per_draw": 87.0,
                "payout_per_hit": REAL_PAYOUT_1D,
                "min_hits_for_profit": 1,
                "be_win_rate": 87.0 / REAL_PAYOUT_1D,
                "be_hits_30_draws": (30.0 * 87.0) / REAL_PAYOUT_1D,  # 29.828571...
                "target_hits_30_draws": 30,
            }
        ),
    }
)

# ---------------------------------------------------------------------------
# 4. Feature Engineering, Falsification Gatekeeper & Engine Constants
# ---------------------------------------------------------------------------
REGIME_WINDOWS: Final[tuple[int, ...]] = (5, 10, 15, 30, 60)
ZERO_HIT_PROB_Q0: Final[float] = 0.9**PRIZES_PER_DRAW  # (0.9)^18 ≈ 0.15009463529699912
GAP_MEAN_MU: Final[float] = ZERO_HIT_PROB_Q0 / (1.0 - ZERO_HIT_PROB_Q0)  # ≈ 0.17660159
GAP_STD_SIGMA: Final[float] = math.sqrt(ZERO_HIT_PROB_Q0) / (1.0 - ZERO_HIT_PROB_Q0)  # ≈ 0.4559835
DEFICIT_10_EXPECTED: Final[float] = 18.0
DEFICIT_10_STD: Final[float] = math.sqrt(180.0 * 0.10 * 0.90)  # sqrt(16.2) ≈ 4.024922359
BURST_THRESHOLD_HITS: Final[int] = 3
MARKOV_ACTIVE_THRESHOLD_HITS: Final[int] = 2
LAPLACE_SMOOTHING_ALPHA: Final[float] = 1.0

FALSIFICATION_WINDOWS: Final[tuple[int, ...]] = (15, 30, 60)
MIN_SAMPLE_SIZE_DRAWS: Final[int] = 60
DIRICHLET_PRIOR_ALPHA0: Final[float] = 18.0
DEFAULT_MONTE_CARLO_SIMS: Final[int] = 1000
DEFAULT_RANDOM_SEED: Final[int] = 42
BF10_ALPHA_THRESHOLD: Final[float] = 3.0
BF10_WEAK_THRESHOLD: Final[float] = 1.0

BOCD_MAX_RUN_LENGTH: Final[int] = 60
BOCD_REGIME_LAMBDA: Final[float] = 25.0
BOCD_HAZARD_RATE: Final[float] = 1.0 / BOCD_REGIME_LAMBDA  # 0.04
CANDIDATE_PAST_WINDOWS: Final[tuple[int, ...]] = (15, 20, 25, 30, 40, 50, 60)
LAG1_EXHAUSTION_PENALTY: Final[float] = 0.35
MARKOV_GAP_L2_PENALTY: Final[float] = 10.0
POOLING_VAL_WINDOW: Final[int] = 30
SIMPLEX_TOLERANCE: Final[float] = 1e-6

DEFAULT_WARMUP_DRAWS: Final[int] = 45
KELLY_NUM_STATES: Final[int] = 19  # Discrete hit counts K in {0, 1, ..., 18}

# ---------------------------------------------------------------------------
# 5. Stage 3 Reference Benchmark Fund, House-Money & Extended Sweet-Spot
# ---------------------------------------------------------------------------
SELECTIVE_ALPHA_JOINT_R1_MIN_PCT: Final[float] = 1.105
PEAK_CONVICTION_JOINT_R1_PCT: Final[float] = 1.150

BENCHMARK_INITIAL_BANKROLL_VND: Final[int] = 1_000_000
BENCHMARK_STAKE_PER_NUMBER_VND: Final[int] = 18_000
BENCHMARK_BASE_DAILY_COST_4NUM_VND: Final[int] = 72_000
BENCHMARK_PAYOUT_PER_HIT_VND: Final[int] = 99_500

HOUSE_MONEY_MIN_BUFFER_DAYS: Final[int] = 2
HOUSE_MONEY_MAX_SURPLUS_FRACTION: Final[float] = 0.50

SAMPLE_CAPITAL_TIERS_VND: Final[tuple[int, ...]] = (
    500_000,
    1_000_000,
    2_000_000,
    5_000_000,
)

STAGE3_TICKET_CONFIGS: Final[tuple[str, ...]] = (
    "2x2",
    "1x4",
    "4x1",
    "3x3",
    "core_2x2_sat_3x3",
)

EXTENDED_SWEET_SPOT_CONFIGS: Final[Mapping[str, Mapping[str, SweetSpotConfigValue]]] = (
    MappingProxyType(
        {
            **SWEET_SPOT_CONFIGS,
            "4x1": MappingProxyType(
                {
                    "config_id": "4x1",
                    "label": "Bộ 4x1 = 4 số (1.0đ/số)",
                    "game_type": "bao_lo",
                    "tens_top_k": 4,
                    "units_top_k": 1,
                    "num_numbers": 4,
                    "cost_per_draw": 4.0,
                    "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                    "min_hits_for_profit": 1,
                    "be_hits_30_draws": (30.0 * 4.0) / BAO_LO_PAYOUT_PER_HIT,
                    "target_hits_30_draws": 25,
                }
            ),
        }
    )
)

# ---------------------------------------------------------------------------
# 6. Stage 4 Family Sweet-Spot (sweet_5), Weekly 5/2 Schedule & Anomaly Sentinel
# ---------------------------------------------------------------------------
BENCHMARK_BASE_DAILY_COST_5NUM_VND: Final[int] = 90_000
SWEET_5_NET_PROFIT_1HIT_VND: Final[int] = 9_500
SWEET_5_NET_PROFIT_2HITS_VND: Final[int] = 109_000
SWEET_4_NET_PROFIT_1HIT_VND: Final[int] = 27_500
SWEET_4_NET_PROFIT_2HITS_VND: Final[int] = 127_000

THEORETICAL_WIN_RATE_4NUM_PCT: Final[float] = 52.04
THEORETICAL_WIN_RATE_5NUM_PCT: Final[float] = 60.28
THEORETICAL_MULTI_HIT_4NUM_PCT: Final[float] = 16.13
THEORETICAL_MULTI_HIT_5NUM_PCT: Final[float] = 22.65

STAGE4_MAX_STAKE_MULTIPLIER: Final[float] = 1.0
WEEKLY_SCHEDULE_PLAY_DAYS: Final[int] = 5
WEEKLY_SCHEDULE_REST_DAYS: Final[int] = 2

CAGE_ANOMALY_BF10_THRESHOLD: Final[float] = 10.0
CAGE_COLD_BALL_FREQ_MAX_PCT: Final[float] = 6.5
CAGE_HOT_BALL_FREQ_MIN_PCT: Final[float] = 14.0

STAGE4_TICKET_CONFIGS: Final[tuple[str, ...]] = (
    "2x2",
    "sweet_5",
    "1x4",
    "4x1",
    "3x3",
    "core_2x2_sat_3x3",
)

STAGE4_SWEET_SPOT_CONFIGS: Final[Mapping[str, Mapping[str, SweetSpotConfigValue]]] = (
    MappingProxyType(
        {
            **EXTENDED_SWEET_SPOT_CONFIGS,
            "sweet_5": MappingProxyType(
                {
                    "config_id": "sweet_5",
                    "label": (
                        "Bộ 5 số Điểm Ngọt Bà Cô (4 số 2x2 + 1 số Vệ tinh đỉnh = 5 số, 1.0đ/số)"
                    ),
                    "game_type": "bao_lo",
                    "tens_top_k": 2,
                    "units_top_k": 2,
                    "num_numbers": 5,
                    "cost_per_draw": 5.0,
                    "payout_per_hit": BAO_LO_PAYOUT_PER_HIT,
                    "min_hits_for_profit": 1,
                    "be_hits_30_draws": (30.0 * 5.0) / BAO_LO_PAYOUT_PER_HIT,
                    "target_hits_30_draws": 31,
                }
            ),
        }
    )
)


def compute_theoretical_noise_std(window_draws: int | float) -> float:
    """Compute exact theoretical binomial standard error for 1 ball over W draws (18*W prizes).

    Formula derived directly from XSMN problem parameters (10 balls, p0 = 0.10, 18 prizes/draw):
        sigma_nhieu(W) = sqrt(p0 * (1 - p0) / (18 * W)) = sqrt(0.09 / (18 * W)) = 1 / sqrt(200 * W)
    """
    if (
        isinstance(window_draws, bool)
        or not isinstance(window_draws, (int, float))
        or not math.isfinite(window_draws)
        or float(window_draws) <= 0.0
    ):
        raise ValueError(f"window_draws must be a finite positive number, got {window_draws!r}.")
    return 1.0 / math.sqrt(200.0 * float(window_draws))
