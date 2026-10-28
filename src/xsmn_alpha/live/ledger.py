"""Stage 3 Pillar 2: Automated Reference Benchmark Ledger (1M VND) & CPPI / House-Money Engine."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from xsmn_alpha.constants import (
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    BENCHMARK_PAYOUT_PER_HIT_VND,
    BENCHMARK_STAKE_PER_NUMBER_VND,
    HOUSE_MONEY_MAX_SURPLUS_FRACTION,
    HOUSE_MONEY_MIN_BUFFER_DAYS,
    PRIZES_PER_DRAW,
    SAMPLE_CAPITAL_TIERS_VND,
    STAGE4_SWEET_SPOT_CONFIGS,
)
from xsmn_alpha.exceptions import CapitalDisciplineError, DataIntegrityError
from xsmn_alpha.live.multi_fetcher import DEFAULT_RAW_ALL_DIR, load_station_raw_cache
from xsmn_alpha.live.registry import (
    get_station_codes_for_weekday,
    get_station_meta,
    get_weekday_vn_label,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerEntry,
    BenchmarkLedgerState,
    CapitalGuidanceContract,
    DailyVerdictTier,
    HitDetailRecord,
    RegionName,
    SampleCapitalAllocationRow,
    Weekly52AndFlatStakeGate,
    validate_iso_date,
    validate_station_code_35,
    validate_two_digit_ascii,
)

DEFAULT_LEDGER_PATH: Final[Path] = Path("data/live/benchmark_ledger.json")

PRIZE_LABELS_18: Final[tuple[str, ...]] = (
    "Giải Tám",
    "Giải Bảy",
    "Giải Sáu (1)",
    "Giải Sáu (2)",
    "Giải Sáu (3)",
    "Giải Năm",
    "Giải Tư (1)",
    "Giải Tư (2)",
    "Giải Tư (3)",
    "Giải Tư (4)",
    "Giải Tư (5)",
    "Giải Tư (6)",
    "Giải Tư (7)",
    "Giải Ba (1)",
    "Giải Ba (2)",
    "Giải Nhì",
    "Giải Nhất",
    "Giải Đặc Biệt",
)

SAMPLE_TIER_LABELS: Final[Mapping[int, str]] = MappingProxyType(
    {
        500_000: "Vốn 500k",
        1_000_000: "Vốn 1 Triệu",
        2_000_000: "Vốn 2 Triệu",
        5_000_000: "Vốn 5 Triệu",
    }
)

_VALID_VERDICT_TIERS: Final[frozenset[str]] = frozenset(
    {
        "PLAY_PEAK",
        "PLAY_STANDARD",
        "PLAY_CAUTIOUS",
        "SKIP_NO_EDGE",
    }
)

_ICT_TZ = datetime.timezone(datetime.timedelta(hours=7))


def _now_ict_iso() -> str:
    """Return current timestamp formatted in ISO-8601 with +07:00 ICT offset."""
    return datetime.datetime.now(_ICT_TZ).replace(microsecond=0).isoformat()


def _format_tier_label(capital_tier_vnd: int) -> str:
    """Return human-readable Vietnamese label for a sample family capital tier."""
    if capital_tier_vnd in SAMPLE_TIER_LABELS:
        return SAMPLE_TIER_LABELS[capital_tier_vnd]
    if capital_tier_vnd >= 1_000_000 and capital_tier_vnd % 1_000_000 == 0:
        return f"Vốn {capital_tier_vnd // 1_000_000} Triệu"
    if capital_tier_vnd >= 1_000 and capital_tier_vnd % 1_000 == 0:
        return f"Vốn {capital_tier_vnd // 1_000}k"
    return f"Vốn {capital_tier_vnd:,}đ"


def _validate_positive_int_param(value: Any, name: str) -> int:
    """Ensure a financial parameter is a strictly positive integer (> 0, not bool)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CapitalDisciplineError(f"{name} must be a positive integer (> 0), got {value!r}.")
    return value


def is_station_scheduled_on_date(station_code: str, draw_date: str | datetime.date) -> bool:
    """Return True if station_code is scheduled to open on draw_date's weekday."""
    code = validate_station_code_35(station_code)
    if isinstance(draw_date, datetime.date) and not isinstance(draw_date, datetime.datetime):
        dt = draw_date
    else:
        dt = datetime.date.fromisoformat(validate_iso_date(str(draw_date)))
    return code in get_station_codes_for_weekday(dt.weekday())


def compute_house_money_multiplier(
    *,
    passes_selective_alpha: bool,
    strong_convergence: bool,
    current_bankroll_vnd: int,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_daily_cost_vnd: int = BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    verdict_tier: DailyVerdictTier | None = None,
    lock_flat_1x: bool = False,
) -> tuple[float, int]:
    """Compute fail-closed CPPI / House-Money capital multiplier and daily bet in VND (Gate 5)."""
    _validate_positive_int_param(current_bankroll_vnd, "current_bankroll_vnd")
    _validate_positive_int_param(initial_bankroll_vnd, "initial_bankroll_vnd")
    _validate_positive_int_param(base_daily_cost_vnd, "base_daily_cost_vnd")

    if verdict_tier is not None:
        return compute_multiplier_for_verdict_tier(
            verdict_tier,
            current_bankroll_vnd=current_bankroll_vnd,
            initial_bankroll_vnd=initial_bankroll_vnd,
            base_daily_cost_vnd=base_daily_cost_vnd,
            lock_flat_1x=lock_flat_1x,
        )

    if not passes_selective_alpha:
        return (0.0, 0)

    if current_bankroll_vnd < initial_bankroll_vnd:
        raise CapitalDisciplineError(
            f"Gate 5 Principal Protection violation: current_bankroll_vnd ({current_bankroll_vnd}) "
            f"< initial_bankroll_vnd ({initial_bankroll_vnd}); cannot place active bet."
        )
    if base_daily_cost_vnd > current_bankroll_vnd:
        raise CapitalDisciplineError(
            f"Gate 5 Capital Discipline violation: base_daily_cost_vnd ({base_daily_cost_vnd}) "
            f"> current_bankroll_vnd ({current_bankroll_vnd})."
        )

    if lock_flat_1x:
        return (1.0, base_daily_cost_vnd)

    house_money_vnd = max(0, current_bankroll_vnd - initial_bankroll_vnd)
    min_buffer_vnd = HOUSE_MONEY_MIN_BUFFER_DAYS * base_daily_cost_vnd

    if house_money_vnd < min_buffer_vnd:
        return (1.0, base_daily_cost_vnd)

    candidate_mult = 1.50 if strong_convergence else 1.25
    total_cost_vnd = int(round(base_daily_cost_vnd * candidate_mult))
    extra_cost_vnd = total_cost_vnd - base_daily_cost_vnd

    # Gate 5: Never risk more than 50% of House-Money surplus and never breach initial principal
    if (
        extra_cost_vnd > int(house_money_vnd * HOUSE_MONEY_MAX_SURPLUS_FRACTION)
        or (current_bankroll_vnd - total_cost_vnd) < initial_bankroll_vnd
    ):
        return (1.0, base_daily_cost_vnd)

    return (candidate_mult, total_cost_vnd)


def compute_multiplier_for_verdict_tier(
    verdict_tier: DailyVerdictTier,
    *,
    current_bankroll_vnd: int,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_daily_cost_vnd: int = BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    lock_flat_1x: bool = False,
) -> tuple[float, int]:
    """Compute CPPI / House-Money multiplier and daily bet for a specific DailyVerdictTier."""
    _validate_positive_int_param(current_bankroll_vnd, "current_bankroll_vnd")
    _validate_positive_int_param(initial_bankroll_vnd, "initial_bankroll_vnd")
    _validate_positive_int_param(base_daily_cost_vnd, "base_daily_cost_vnd")

    if not isinstance(verdict_tier, str) or verdict_tier not in _VALID_VERDICT_TIERS:
        raise CapitalDisciplineError(
            f"Invalid verdict_tier {verdict_tier!r}; must be one of {sorted(_VALID_VERDICT_TIERS)}."
        )

    if verdict_tier == "SKIP_NO_EDGE":
        return (0.0, 0)

    if current_bankroll_vnd < initial_bankroll_vnd:
        raise CapitalDisciplineError(
            f"Gate 5 Principal Protection violation: current_bankroll_vnd ({current_bankroll_vnd}) "
            f"< initial_bankroll_vnd ({initial_bankroll_vnd}); "
            f"cannot place active bet for {verdict_tier}."
        )
    if base_daily_cost_vnd > current_bankroll_vnd:
        raise CapitalDisciplineError(
            f"Gate 5 Capital Discipline violation: base_daily_cost_vnd ({base_daily_cost_vnd}) "
            f"> current_bankroll_vnd ({current_bankroll_vnd})."
        )

    if lock_flat_1x or verdict_tier == "PLAY_CAUTIOUS":
        return (1.0, base_daily_cost_vnd)

    strong_conv = verdict_tier == "PLAY_PEAK"
    return compute_house_money_multiplier(
        passes_selective_alpha=True,
        strong_convergence=strong_conv,
        current_bankroll_vnd=current_bankroll_vnd,
        initial_bankroll_vnd=initial_bankroll_vnd,
        base_daily_cost_vnd=base_daily_cost_vnd,
        lock_flat_1x=lock_flat_1x,
    )


def build_sample_capital_allocations(
    recommended_multiplier: float,
    *,
    tiers_vnd: Sequence[int] = SAMPLE_CAPITAL_TIERS_VND,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_stake_per_number_vnd: int = BENCHMARK_STAKE_PER_NUMBER_VND,
    base_payout_per_hit_vnd: int = BENCHMARK_PAYOUT_PER_HIT_VND,
    num_numbers: int = 4,
) -> list[SampleCapitalAllocationRow]:
    """Build proportional sample VND allocation rows for family capital tiers (500k, 1M, 2M, 5M)."""
    if (
        isinstance(recommended_multiplier, bool)
        or not isinstance(recommended_multiplier, (int, float))
        or not math.isfinite(float(recommended_multiplier))
        or float(recommended_multiplier) < 0.0
    ):
        raise CapitalDisciplineError(
            f"recommended_multiplier must be a non-negative finite float, "
            f"got {recommended_multiplier!r}."
        )
    _validate_positive_int_param(initial_bankroll_vnd, "initial_bankroll_vnd")
    _validate_positive_int_param(base_stake_per_number_vnd, "base_stake_per_number_vnd")
    _validate_positive_int_param(base_payout_per_hit_vnd, "base_payout_per_hit_vnd")
    _validate_positive_int_param(num_numbers, "num_numbers")

    if not isinstance(tiers_vnd, Sequence) or isinstance(tiers_vnd, (str, bytes)) or not tiers_vnd:
        raise DataIntegrityError("tiers_vnd must be a non-empty sequence of positive integers.")

    mult = float(recommended_multiplier)
    rows: list[SampleCapitalAllocationRow] = []
    for tier in tiers_vnd:
        _validate_positive_int_param(tier, "capital_tier_vnd")
        scale = float(tier) / float(initial_bankroll_vnd)
        if mult == 0.0:
            stake = 0
            total_cost = 0
            payout = 0
            net_1 = 0
            net_2 = 0
            net_3 = 0
        else:
            stake = int(round(base_stake_per_number_vnd * scale * mult))
            total_cost = num_numbers * stake
            payout = int(round(base_payout_per_hit_vnd * scale * mult))
            net_1 = payout - total_cost
            net_2 = 2 * payout - total_cost
            net_3 = 3 * payout - total_cost

        rows.append(
            SampleCapitalAllocationRow(
                capital_tier_vnd=tier,
                tier_label=_format_tier_label(tier),
                scale_factor=scale,
                recommended_multiplier=mult,
                stake_per_number_vnd=stake,
                num_numbers=num_numbers,
                total_daily_cost_vnd=total_cost,
                payout_per_hit_vnd=payout,
                net_profit_1hit_vnd=net_1,
                net_profit_2hits_vnd=net_2,
                net_profit_3hits_vnd=net_3,
            )
        )
    return rows


def build_capital_guidance(
    verdict_tier: DailyVerdictTier,
    *,
    current_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_daily_cost_vnd: int = BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    base_stake_per_number_vnd: int = BENCHMARK_STAKE_PER_NUMBER_VND,
    base_payout_per_hit_vnd: int = BENCHMARK_PAYOUT_PER_HIT_VND,
    recommended_multiplier: float | None = None,
    num_numbers: int = 4,
    sizing_rationale_vi: str = "",
    lock_flat_1x: bool = False,
) -> CapitalGuidanceContract:
    """Build a fail-closed CapitalGuidanceContract enforcing Gate 4, Gate 5, and Gate 6."""
    _validate_positive_int_param(num_numbers, "num_numbers")
    _validate_positive_int_param(base_stake_per_number_vnd, "base_stake_per_number_vnd")
    if num_numbers != 4 and base_daily_cost_vnd == BENCHMARK_BASE_DAILY_COST_4NUM_VND:
        base_daily_cost_vnd = num_numbers * base_stake_per_number_vnd
    elif num_numbers == 4 and base_daily_cost_vnd != BENCHMARK_BASE_DAILY_COST_4NUM_VND:
        if base_daily_cost_vnd > 0 and base_daily_cost_vnd % base_stake_per_number_vnd == 0:
            num_numbers = base_daily_cost_vnd // base_stake_per_number_vnd
    if base_daily_cost_vnd != num_numbers * base_stake_per_number_vnd:
        raise CapitalDisciplineError(
            f"base_daily_cost_vnd ({base_daily_cost_vnd}) != "
            f"num_numbers * base_stake_per_number_vnd ({num_numbers * base_stake_per_number_vnd})."
        )

    computed_mult, computed_bet = compute_multiplier_for_verdict_tier(
        verdict_tier,
        current_bankroll_vnd=current_bankroll_vnd,
        initial_bankroll_vnd=initial_bankroll_vnd,
        base_daily_cost_vnd=base_daily_cost_vnd,
        lock_flat_1x=lock_flat_1x,
    )
    mult = float(computed_mult if recommended_multiplier is None else recommended_multiplier)
    should_play = verdict_tier != "SKIP_NO_EDGE"

    if lock_flat_1x:
        if not should_play and abs(mult) > 1e-9:
            raise CapitalDisciplineError(
                f"Gate 6 (Weekly52AndFlatStakeGate) violation: SKIP_NO_EDGE with "
                f"lock_flat_1x=True requires recommended_multiplier == 0.0, got {mult}."
            )
        Weekly52AndFlatStakeGate.enforce_flat_stake(
            mult,
            should_play_today=should_play,
            lock_flat_1x=True,
        )

    house_money_vnd = max(0, current_bankroll_vnd - initial_bankroll_vnd)
    min_buffer_vnd = HOUSE_MONEY_MIN_BUFFER_DAYS * base_daily_cost_vnd

    if mult == 0.0:
        bet_vnd = 0
        stake_vnd = 0
        payout_vnd = 0
    else:
        stake_vnd = int(round(base_stake_per_number_vnd * mult))
        bet_vnd = (
            computed_bet
            if (recommended_multiplier is None and num_numbers == 4)
            else num_numbers * stake_vnd
        )
        payout_vnd = int(round(base_payout_per_hit_vnd * mult))

    allocations = build_sample_capital_allocations(
        mult,
        initial_bankroll_vnd=initial_bankroll_vnd,
        base_stake_per_number_vnd=base_stake_per_number_vnd,
        base_payout_per_hit_vnd=base_payout_per_hit_vnd,
        num_numbers=num_numbers,
    )

    if not sizing_rationale_vi:
        if verdict_tier == "SKIP_NO_EDGE":
            if lock_flat_1x:
                sizing_rationale_vi = (
                    f"Thực thi kỷ luật BÁO NGHỈ (0.00x — Nghỉ định kỳ Lịch Chơi 5/2 "
                    f"theo độ cân bằng lồng cầu hoặc đứng ngoài bảo toàn vốn). "
                    f"Khóa phanh tiền mặt 0.0x (cược 0 VNĐ) "
                    f"để bảo toàn 100% số dư {current_bankroll_vnd:,} VNĐ."
                )
            else:
                sizing_rationale_vi = (
                    f"Toàn bộ các đài mở thưởng hôm nay đều nằm trong vùng nhiễu trắng "
                    f"(chưa đạt ngưỡng lọc lợi thế chọn lọc). Khóa phanh tiền mặt 0.0x "
                    f"(cược 0 VNĐ) để bảo toàn 100% số dư {current_bankroll_vnd:,} VNĐ."
                )
        elif lock_flat_1x:
            sizing_rationale_vi = (
                f"Thực thi Kỷ Luật Tiền Chợ Đều Tay 1.00x ({bet_vnd:,} VNĐ/ngày cho "
                f"{num_numbers} số, tuyệt đối không gấp thếp). Quỹ Lãi Ròng hiện đạt "
                f"{house_money_vnd:,} VNĐ trên vốn gốc {initial_bankroll_vnd:,} VNĐ."
            )
        elif mult > 1.0:
            extra_vnd = bet_vnd - base_daily_cost_vnd
            sizing_rationale_vi = (
                f"Quỹ Lãi Ròng hiện đạt {house_money_vnd:,} VNĐ (>= ngưỡng đệm 2 ngày "
                f"{min_buffer_vnd:,} VNĐ). Kích hoạt hệ số House-Money {mult:.2f}x "
                f"({bet_vnd:,} VNĐ/ngày; phần tăng thêm {extra_vnd:,} VNĐ trích hoàn toàn từ lãi, "
                f"bảo toàn 100% vốn gốc {initial_bankroll_vnd:,} VNĐ)."
            )
        elif verdict_tier == "PLAY_CAUTIOUS":
            sizing_rationale_vi = (
                f"Tín hiệu đạt lợi thế dương nhẹ ({verdict_tier}). Giữ mức cược tiêu chuẩn "
                f"1.00x ({bet_vnd:,} VNĐ/ngày cho Quỹ Chuẩn {initial_bankroll_vnd:,} VNĐ), "
                f"không dùng bội số House-Money."
            )
        else:
            sizing_rationale_vi = (
                f"Quỹ Lãi Ròng hiện tại ({house_money_vnd:,} VNĐ) chưa vượt ngưỡng đệm 2 ngày "
                f"({min_buffer_vnd:,} VNĐ). Đi vốn chuẩn 1.00x ({bet_vnd:,} VNĐ/ngày) theo "
                f"kỷ luật CPPI."
            )

    return CapitalGuidanceContract(
        verdict_tier=verdict_tier,
        should_play_today=should_play,
        recommended_multiplier=mult,
        initial_bankroll_vnd=initial_bankroll_vnd,
        benchmark_bankroll_vnd=current_bankroll_vnd,
        house_money_surplus_vnd=house_money_vnd,
        base_daily_cost_vnd=base_daily_cost_vnd,
        benchmark_bet_vnd=bet_vnd,
        stake_per_number_vnd=stake_vnd,
        payout_per_hit_vnd=payout_vnd,
        sample_allocations=allocations,
        sizing_rationale_vi=sizing_rationale_vi,
    )


def evaluate_18_prizes_hits(
    selected_numbers: Sequence[str],
    actual_prizes_last2: Sequence[str],
) -> tuple[int, list[HitDetailRecord]]:
    """Evaluate 18 prizes (Giải Tám -> Giải Đặc Biệt) against selected 2-digit numbers.

    Returns (hit_count_k, hit_details) where each hit occurrence across the 18 prizes
    is recorded with its exact prize_index (0..17) and Vietnamese prize_label.
    """
    if not isinstance(selected_numbers, Sequence) or isinstance(selected_numbers, (str, bytes)):
        raise DataIntegrityError("selected_numbers must be a sequence of 2-digit ASCII strings.")

    cleaned_selected = [validate_two_digit_ascii(num) for num in selected_numbers]
    if len(set(cleaned_selected)) != len(cleaned_selected):
        raise DataIntegrityError("selected_numbers must not contain duplicate 2-digit numbers.")
    selected_set = set(cleaned_selected)

    if (
        not isinstance(actual_prizes_last2, Sequence)
        or isinstance(actual_prizes_last2, (str, bytes))
        or len(actual_prizes_last2) != PRIZES_PER_DRAW
    ):
        count = len(actual_prizes_last2) if isinstance(actual_prizes_last2, Sequence) else "invalid"
        raise DataIntegrityError(
            f"actual_prizes_last2 must contain exactly {PRIZES_PER_DRAW} prizes, got {count}."
        )

    cleaned_prizes = [validate_two_digit_ascii(p) for p in actual_prizes_last2]
    hit_details: list[HitDetailRecord] = []
    for idx, prize_num in enumerate(cleaned_prizes):
        if prize_num in selected_set:
            hit_details.append(
                HitDetailRecord(
                    prize_index=idx,
                    prize_label=PRIZE_LABELS_18[idx],
                    number=prize_num,
                )
            )
    return (len(hit_details), hit_details)


def compute_ledger_sha256(state_or_dict: BenchmarkLedgerState | Mapping[str, Any]) -> str:
    """Compute a deterministic SHA-256 hex digest over a BenchmarkLedgerState payload."""
    if isinstance(state_or_dict, BenchmarkLedgerState):
        payload = state_or_dict.model_dump()
    elif isinstance(state_or_dict, Mapping):
        payload = dict(state_or_dict)
    else:
        raise DataIntegrityError(
            f"Expected BenchmarkLedgerState or mapping, got {type(state_or_dict).__name__}."
        )

    payload_without_sha = {k: v for k, v in payload.items() if k != "sha256"}
    serialized = json.dumps(
        payload_without_sha,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def recalculate_ledger_state(
    entries: Sequence[BenchmarkLedgerEntry | Mapping[str, Any]],
    *,
    starting_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_stake_per_number_vnd: int = BENCHMARK_STAKE_PER_NUMBER_VND,
    payout_per_hit_vnd: int = BENCHMARK_PAYOUT_PER_HIT_VND,
    updated_at: str | None = None,
    strict_chain: bool = False,
) -> BenchmarkLedgerState:
    """Recalculate and sign aggregate BenchmarkLedgerState from an ordered sequence of entries."""
    _validate_positive_int_param(starting_bankroll_vnd, "starting_bankroll_vnd")
    _validate_positive_int_param(base_stake_per_number_vnd, "base_stake_per_number_vnd")
    _validate_positive_int_param(payout_per_hit_vnd, "payout_per_hit_vnd")

    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise DataIntegrityError("entries must be a sequence of BenchmarkLedgerEntry items.")

    validated_entries: list[BenchmarkLedgerEntry] = [
        item
        if isinstance(item, BenchmarkLedgerEntry)
        else BenchmarkLedgerEntry.model_validate(item)
        for item in entries
    ]

    seen_dates: set[str] = set()
    prev_date: str | None = None
    for entry in validated_entries:
        if entry.draw_date in seen_dates:
            raise DataIntegrityError(f"Duplicate draw_date {entry.draw_date!r} in ledger entries.")
        if prev_date is not None and entry.draw_date < prev_date:
            raise DataIntegrityError(
                f"Ledger entries out of chronological order: {entry.draw_date} < {prev_date}."
            )
        seen_dates.add(entry.draw_date)
        prev_date = entry.draw_date

    running_bankroll = starting_bankroll_vnd
    peak_bankroll = starting_bankroll_vnd
    min_bankroll = starting_bankroll_vnd
    max_drawdown = 0
    played_days = 0
    rest_days = 0
    win_days = 0
    loss_days = 0
    total_cost_vnd = 0
    total_revenue_vnd = 0
    normalized_entries: list[BenchmarkLedgerEntry] = []

    for entry in validated_entries:
        if strict_chain:
            if entry.bankroll_before_vnd != running_bankroll:
                raise CapitalDisciplineError(
                    f"Broken bankroll chain on {entry.draw_date}: "
                    f"bankroll_before_vnd ({entry.bankroll_before_vnd}) != "
                    f"previous bankroll_after_vnd ({running_bankroll})."
                )
            cur_entry = entry
        else:
            hm_before = max(0, running_bankroll - starting_bankroll_vnd)
            if entry.settlement_status == "PENDING":
                after_bankroll = running_bankroll
            else:
                after_bankroll = running_bankroll + entry.revenue_vnd - entry.cost_vnd
            hm_after = max(0, after_bankroll - starting_bankroll_vnd)
            if (
                entry.bankroll_before_vnd == running_bankroll
                and entry.house_money_before_vnd == hm_before
                and entry.bankroll_after_vnd == after_bankroll
                and entry.house_money_after_vnd == hm_after
            ):
                cur_entry = entry
            else:
                dumped = entry.model_dump()
                dumped["bankroll_before_vnd"] = running_bankroll
                dumped["house_money_before_vnd"] = hm_before
                dumped["bankroll_after_vnd"] = after_bankroll
                dumped["house_money_after_vnd"] = hm_after
                cur_entry = BenchmarkLedgerEntry.model_validate(dumped)

        if cur_entry.verdict_tier == "SKIP_NO_EDGE":
            rest_days += 1
        else:
            played_days += 1
            if cur_entry.settlement_status == "SETTLED":
                total_cost_vnd += cur_entry.cost_vnd
                total_revenue_vnd += cur_entry.revenue_vnd
                if cur_entry.net_profit_vnd > 0:
                    win_days += 1
                else:
                    loss_days += 1

        running_bankroll = cur_entry.bankroll_after_vnd
        peak_bankroll = max(peak_bankroll, running_bankroll)
        min_bankroll = min(min_bankroll, running_bankroll)
        drawdown = peak_bankroll - running_bankroll
        max_drawdown = max(max_drawdown, drawdown)
        normalized_entries.append(cur_entry)

    net_profit_vnd = total_revenue_vnd - total_cost_vnd
    current_bankroll_vnd = starting_bankroll_vnd + net_profit_vnd
    if current_bankroll_vnd != running_bankroll:
        raise CapitalDisciplineError(
            f"Ledger bankroll mismatch: running_bankroll ({running_bankroll}) != "
            f"starting_bankroll + net_profit ({current_bankroll_vnd})."
        )
    house_money_surplus_vnd = max(0, current_bankroll_vnd - starting_bankroll_vnd)
    ts = updated_at if updated_at else _now_ict_iso()

    state = BenchmarkLedgerState(
        schema_version="3.0.0",
        starting_bankroll_vnd=starting_bankroll_vnd,
        base_stake_per_number_vnd=base_stake_per_number_vnd,
        payout_per_hit_vnd=payout_per_hit_vnd,
        current_bankroll_vnd=current_bankroll_vnd,
        house_money_surplus_vnd=house_money_surplus_vnd,
        peak_bankroll_vnd=peak_bankroll,
        min_bankroll_vnd=min_bankroll,
        max_drawdown_vnd=max_drawdown,
        total_tracked_days=len(normalized_entries),
        played_days=played_days,
        rest_days=rest_days,
        win_days=win_days,
        loss_days=loss_days,
        total_cost_vnd=total_cost_vnd,
        total_revenue_vnd=total_revenue_vnd,
        net_profit_vnd=net_profit_vnd,
        updated_at=ts,
        sha256="",
        entries=normalized_entries,
    )
    state.sha256 = compute_ledger_sha256(state)
    return state


def verify_ledger_integrity(
    state: BenchmarkLedgerState,
    *,
    verify_sha256: bool = True,
) -> BenchmarkLedgerState:
    """Enforce Gate 5 (HouseMoneyAndLedgerIntegrityGate) across the entire BenchmarkLedgerState."""
    if not isinstance(state, BenchmarkLedgerState):
        raise DataIntegrityError(f"Expected BenchmarkLedgerState, got {type(state).__name__}.")

    BenchmarkLedgerState.model_validate(state.model_dump())

    recomputed = recalculate_ledger_state(
        state.entries,
        starting_bankroll_vnd=state.starting_bankroll_vnd,
        base_stake_per_number_vnd=state.base_stake_per_number_vnd,
        payout_per_hit_vnd=state.payout_per_hit_vnd,
        updated_at=state.updated_at,
        strict_chain=True,
    )

    for field_name in (
        "current_bankroll_vnd",
        "house_money_surplus_vnd",
        "peak_bankroll_vnd",
        "min_bankroll_vnd",
        "max_drawdown_vnd",
        "total_tracked_days",
        "played_days",
        "rest_days",
        "win_days",
        "loss_days",
        "total_cost_vnd",
        "total_revenue_vnd",
        "net_profit_vnd",
    ):
        actual_val = getattr(state, field_name)
        expected_val = getattr(recomputed, field_name)
        if actual_val != expected_val:
            raise CapitalDisciplineError(
                f"Ledger state aggregate mismatch for {field_name}: "
                f"stored={actual_val}, recomputed={expected_val}."
            )

    if verify_sha256:
        if not state.sha256:
            raise DataIntegrityError("Missing sha256 signature on BenchmarkLedgerState.")
        expected_sha = compute_ledger_sha256(state)
        if state.sha256 != expected_sha:
            raise DataIntegrityError(
                f"BenchmarkLedgerState SHA-256 mismatch: "
                f"stored={state.sha256}, computed={expected_sha}."
            )

    return state


def initialize_empty_ledger(
    *,
    starting_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_stake_per_number_vnd: int = BENCHMARK_STAKE_PER_NUMBER_VND,
    payout_per_hit_vnd: int = BENCHMARK_PAYOUT_PER_HIT_VND,
    updated_at: str | None = None,
) -> BenchmarkLedgerState:
    """Create a fresh, SHA-256 signed BenchmarkLedgerState starting at 1,000,000 VND."""
    return recalculate_ledger_state(
        [],
        starting_bankroll_vnd=starting_bankroll_vnd,
        base_stake_per_number_vnd=base_stake_per_number_vnd,
        payout_per_hit_vnd=payout_per_hit_vnd,
        updated_at=updated_at,
        strict_chain=True,
    )


def save_benchmark_ledger(
    state: BenchmarkLedgerState,
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
) -> Path:
    """Verify Gate 5 integrity, update SHA-256 signature, and write benchmark_ledger.json."""
    verify_ledger_integrity(state, verify_sha256=False)
    state.sha256 = compute_ledger_sha256(state)
    verify_ledger_integrity(state, verify_sha256=True)

    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_benchmark_ledger(
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    *,
    verify_sha256: bool = True,
    create_if_missing: bool = False,
) -> BenchmarkLedgerState:
    """Load and verify benchmark_ledger.json from disk (Gate 5 & SHA-256 check)."""
    path = Path(ledger_path)
    if not path.exists():
        if create_if_missing:
            state = initialize_empty_ledger()
            save_benchmark_ledger(state, path)
            return state
        raise DataIntegrityError(f"Benchmark ledger file does not exist: {path}")

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DataIntegrityError(f"Corrupted JSON in benchmark ledger {path}: {exc}") from exc

    if not isinstance(raw_payload, Mapping):
        raise DataIntegrityError(f"Invalid JSON root in {path}; expected object mapping.")

    if verify_sha256:
        stored_sha = raw_payload.get("sha256")
        if not isinstance(stored_sha, str) or not stored_sha:
            raise DataIntegrityError(f"Missing or empty sha256 field in {path}.")
        computed_sha = compute_ledger_sha256(raw_payload)
        if stored_sha != computed_sha:
            raise DataIntegrityError(
                f"SHA-256 integrity mismatch in {path}: "
                f"stored={stored_sha}, computed={computed_sha}."
            )

    state = BenchmarkLedgerState.model_validate(raw_payload)
    return verify_ledger_integrity(state, verify_sha256=verify_sha256)


def record_pending_recommendation(
    state: BenchmarkLedgerState,
    *,
    draw_date: str,
    verdict_tier: DailyVerdictTier,
    chosen_station_code: str,
    chosen_station_name: str | None = None,
    chosen_region: RegionName | None = None,
    chosen_config_id: str,
    selected_numbers: Sequence[str],
    recommended_multiplier: float | None = None,
    cost_vnd: int | None = None,
    weekday_vn: str | None = None,
    updated_at: str | None = None,
    ledger_path: str | Path | None = None,
    lock_flat_1x: bool = False,
) -> BenchmarkLedgerState:
    """Record a pre-draw recommendation in the ledger (PENDING, or SETTLED if SKIP_NO_EDGE)."""
    validate_iso_date(draw_date)
    validate_station_code_35(chosen_station_code)
    meta = get_station_meta(chosen_station_code)
    st_name = chosen_station_name if chosen_station_name else str(meta["name"])
    st_region: RegionName = (
        chosen_region if chosen_region is not None else str(meta["region"])  # type: ignore[assignment]
    )
    if not is_station_scheduled_on_date(chosen_station_code, draw_date):
        raise DataIntegrityError(
            f"Station {chosen_station_code} ({st_name}) is not scheduled to open on "
            f"{draw_date} ({get_weekday_vn_label(draw_date)})."
        )
    expected_wd = get_weekday_vn_label(draw_date)
    if weekday_vn is not None and weekday_vn.strip() != expected_wd:
        raise DataIntegrityError(
            f"weekday_vn mismatch for {draw_date}: got {weekday_vn!r}, expected {expected_wd!r}."
        )
    wd_label = expected_wd

    # Check if an entry for draw_date already exists
    existing_idx: int | None = None
    for idx, entry in enumerate(state.entries):
        if entry.draw_date == draw_date:
            existing_idx = idx
            break

    # Determine bankroll_before_vnd from preceding entries
    entries_before = (
        state.entries[:existing_idx]
        if existing_idx is not None
        else [e for e in state.entries if e.draw_date < draw_date]
    )
    bankroll_before = (
        entries_before[-1].bankroll_after_vnd if entries_before else state.starting_bankroll_vnd
    )
    hm_before = max(0, bankroll_before - state.starting_bankroll_vnd)

    cfg_meta = STAGE4_SWEET_SPOT_CONFIGS.get(chosen_config_id)
    if cfg_meta is None:
        raise DataIntegrityError(f"Unknown chosen_config_id {chosen_config_id!r}.")
    if not isinstance(selected_numbers, Sequence) or isinstance(selected_numbers, (str, bytes)):
        raise DataIntegrityError("selected_numbers must be a sequence of 2-digit ASCII strings.")
    cleaned_selected = [validate_two_digit_ascii(num) for num in selected_numbers]
    if len(set(cleaned_selected)) != len(cleaned_selected):
        raise DataIntegrityError("selected_numbers must not contain duplicates.")
    expected_num_numbers = int(cfg_meta["num_numbers"])
    if cleaned_selected and len(cleaned_selected) != expected_num_numbers:
        raise DataIntegrityError(
            f"len(selected_numbers) ({len(cleaned_selected)}) != "
            f"expected num_numbers ({expected_num_numbers}) for {chosen_config_id!r}."
        )
    if chosen_config_id == "sweet_5" and cleaned_selected:
        Weekly52AndFlatStakeGate.enforce_sweet_5(cleaned_selected)

    base_cost_for_cfg = int(
        round(float(cfg_meta["cost_per_draw"]) * state.base_stake_per_number_vnd)
    )

    auto_mult, auto_cost = compute_multiplier_for_verdict_tier(
        verdict_tier,
        current_bankroll_vnd=bankroll_before,
        initial_bankroll_vnd=state.starting_bankroll_vnd,
        base_daily_cost_vnd=base_cost_for_cfg,
        lock_flat_1x=lock_flat_1x,
    )
    eff_mult = float(auto_mult if recommended_multiplier is None else recommended_multiplier)
    if lock_flat_1x:
        if verdict_tier == "SKIP_NO_EDGE" and abs(eff_mult) > 1e-9:
            raise CapitalDisciplineError(
                f"Gate 6 (Weekly52AndFlatStakeGate) violation: SKIP_NO_EDGE with "
                f"lock_flat_1x=True requires recommended_multiplier == 0.0, got {eff_mult}."
            )
        Weekly52AndFlatStakeGate.enforce_flat_stake(
            eff_mult,
            should_play_today=(verdict_tier != "SKIP_NO_EDGE"),
            lock_flat_1x=True,
        )

    if (
        existing_idx is not None
        and state.entries[existing_idx].settlement_status == "SETTLED"
        and (
            state.entries[existing_idx].verdict_tier != "SKIP_NO_EDGE"
            or bool(state.entries[existing_idx].actual_prizes_last2)
        )
    ):
        # Preserve already-settled historical entry (idempotent)
        if ledger_path is not None:
            save_benchmark_ledger(state, ledger_path)
        return state
    if cost_vnd is not None:
        eff_cost = int(cost_vnd)
    elif eff_mult == 0.0:
        eff_cost = 0
    else:
        eff_cost = int(round(base_cost_for_cfg * eff_mult))

    is_skip = verdict_tier == "SKIP_NO_EDGE"
    status = "SETTLED" if is_skip else "PENDING"

    new_entry = BenchmarkLedgerEntry(
        draw_date=draw_date,
        weekday_vn=wd_label,
        settlement_status=status,  # type: ignore[arg-type]
        verdict_tier=verdict_tier,
        chosen_station_code=chosen_station_code,
        chosen_station_name=st_name,
        chosen_region=st_region,
        chosen_config_id=chosen_config_id,
        selected_numbers=list(selected_numbers),
        recommended_multiplier=eff_mult,
        bankroll_before_vnd=bankroll_before,
        house_money_before_vnd=hm_before,
        cost_vnd=eff_cost,
        actual_prizes_last2=[],
        hit_count_k=0 if is_skip else None,
        hit_details=[],
        revenue_vnd=0,
        net_profit_vnd=0,
        bankroll_after_vnd=bankroll_before,
        house_money_after_vnd=hm_before,
    )

    if existing_idx is not None:
        updated_entries = list(state.entries)
        updated_entries[existing_idx] = new_entry
    else:
        updated_entries = sorted(
            [*state.entries, new_entry],
            key=lambda e: e.draw_date,
        )

    new_state = recalculate_ledger_state(
        updated_entries,
        starting_bankroll_vnd=state.starting_bankroll_vnd,
        base_stake_per_number_vnd=state.base_stake_per_number_vnd,
        payout_per_hit_vnd=state.payout_per_hit_vnd,
        updated_at=updated_at,
        strict_chain=False,
    )
    if ledger_path is not None:
        save_benchmark_ledger(new_state, ledger_path)
    return new_state


def settle_entry_with_prizes(
    entry: BenchmarkLedgerEntry,
    actual_prizes_last2: Sequence[str],
    *,
    payout_per_hit_vnd: int = BENCHMARK_PAYOUT_PER_HIT_VND,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
) -> BenchmarkLedgerEntry:
    """Settle a single BenchmarkLedgerEntry against 18 actual prizes (idempotent)."""
    _validate_positive_int_param(payout_per_hit_vnd, "payout_per_hit_vnd")
    _validate_positive_int_param(initial_bankroll_vnd, "initial_bankroll_vnd")

    hit_count_k, hit_details = evaluate_18_prizes_hits(entry.selected_numbers, actual_prizes_last2)
    cleaned_prizes = [validate_two_digit_ascii(p) for p in actual_prizes_last2]

    if entry.settlement_status == "SETTLED":
        if entry.actual_prizes_last2 and entry.actual_prizes_last2 != cleaned_prizes:
            raise DataIntegrityError(
                f"Conflicting 18 prizes for already-SETTLED draw on {entry.draw_date} "
                f"({entry.chosen_station_code})."
            )
        if entry.actual_prizes_last2 == cleaned_prizes:
            return entry.model_copy(deep=True)

    if entry.verdict_tier == "SKIP_NO_EDGE":
        revenue_vnd = 0
        net_profit_vnd = 0
        bankroll_after_vnd = entry.bankroll_before_vnd
        house_money_after_vnd = entry.house_money_before_vnd
    else:
        if entry.chosen_config_id == "core_2x2_sat_3x3":
            core_set = set(entry.selected_numbers[:4])
            core_hits = sum(1 for hd in hit_details if hd.number in core_set)
            sat_hits = len(hit_details) - core_hits
            revenue_vnd = int(
                round(
                    (float(core_hits) + 0.5 * float(sat_hits))
                    * payout_per_hit_vnd
                    * entry.recommended_multiplier
                )
            )
        else:
            revenue_vnd = int(
                round(hit_count_k * payout_per_hit_vnd * entry.recommended_multiplier)
            )
        net_profit_vnd = revenue_vnd - entry.cost_vnd
        bankroll_after_vnd = entry.bankroll_before_vnd + net_profit_vnd
        house_money_after_vnd = max(0, bankroll_after_vnd - initial_bankroll_vnd)

    return BenchmarkLedgerEntry(
        draw_date=entry.draw_date,
        weekday_vn=entry.weekday_vn,
        settlement_status="SETTLED",
        verdict_tier=entry.verdict_tier,
        chosen_station_code=entry.chosen_station_code,
        chosen_station_name=entry.chosen_station_name,
        chosen_region=entry.chosen_region,
        chosen_config_id=entry.chosen_config_id,
        selected_numbers=list(entry.selected_numbers),
        recommended_multiplier=entry.recommended_multiplier,
        bankroll_before_vnd=entry.bankroll_before_vnd,
        house_money_before_vnd=entry.house_money_before_vnd,
        cost_vnd=entry.cost_vnd,
        actual_prizes_last2=cleaned_prizes,
        hit_count_k=hit_count_k,
        hit_details=hit_details,
        revenue_vnd=revenue_vnd,
        net_profit_vnd=net_profit_vnd,
        bankroll_after_vnd=bankroll_after_vnd,
        house_money_after_vnd=house_money_after_vnd,
    )


def _lookup_prizes_from_raw_cache(
    station_code: str,
    draw_date: str,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
) -> list[str]:
    """Load 18 prizes for station_code on draw_date from <raw_dir>/<CODE>_draws.json."""
    draws = load_station_raw_cache(
        station_code,
        raw_dir=raw_dir,
        verify_sha256=True,
        allow_unhashed_legacy=True,
    )
    for draw in draws:
        if draw["draw_date"] == draw_date:
            return [validate_two_digit_ascii(p) for p in draw["prizes_last2"]]
    raise DataIntegrityError(
        f"No 18-prize draw found for station {station_code} on {draw_date} in {raw_dir}."
    )


def settle_ledger_for_date(
    state_or_path: BenchmarkLedgerState | str | Path,
    draw_date: str,
    actual_prizes_last2: Sequence[str] | None = None,
    *,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    ledger_path: str | Path | None = None,
    updated_at: str | None = None,
) -> BenchmarkLedgerState:
    """Settle the ledger entry for draw_date and recalculate cumulative state (idempotent)."""
    validate_iso_date(draw_date)

    path_to_save: Path | None = Path(ledger_path) if ledger_path is not None else None
    if isinstance(state_or_path, (str, Path)):
        resolved_path = Path(state_or_path)
        state = load_benchmark_ledger(resolved_path, verify_sha256=True)
        if path_to_save is None:
            path_to_save = resolved_path
    elif isinstance(state_or_path, BenchmarkLedgerState):
        state = verify_ledger_integrity(state_or_path, verify_sha256=False)
    else:
        raise DataIntegrityError(
            f"state_or_path must be a BenchmarkLedgerState or Path, "
            f"got {type(state_or_path).__name__}."
        )

    target_idx: int | None = None
    for idx, entry in enumerate(state.entries):
        if entry.draw_date == draw_date:
            target_idx = idx
            break

    if target_idx is None:
        raise DataIntegrityError(f"No ledger entry found for draw_date {draw_date!r}.")

    target_entry = state.entries[target_idx]

    # Resolve 18 prizes if not explicitly provided
    prizes_to_use: Sequence[str] | None = actual_prizes_last2
    if prizes_to_use is None:
        if (
            target_entry.verdict_tier == "SKIP_NO_EDGE"
            and target_entry.settlement_status == "SETTLED"
        ):
            if target_entry.actual_prizes_last2:
                if path_to_save is not None:
                    save_benchmark_ledger(state, path_to_save)
                return state
            try:
                prizes_to_use = _lookup_prizes_from_raw_cache(
                    target_entry.chosen_station_code,
                    draw_date,
                    raw_dir=raw_dir,
                )
            except DataIntegrityError:
                if path_to_save is not None:
                    save_benchmark_ledger(state, path_to_save)
                return state
        else:
            prizes_to_use = _lookup_prizes_from_raw_cache(
                target_entry.chosen_station_code,
                draw_date,
                raw_dir=raw_dir,
            )

    cleaned_prizes = [validate_two_digit_ascii(p) for p in prizes_to_use]
    if len(cleaned_prizes) != PRIZES_PER_DRAW:
        raise DataIntegrityError(
            f"actual_prizes_last2 must contain {PRIZES_PER_DRAW} prizes, got {len(cleaned_prizes)}."
        )

    # Idempotency check: if already SETTLED with the exact same 18 prizes, return state unchanged!
    if (
        target_entry.settlement_status == "SETTLED"
        and target_entry.actual_prizes_last2 == cleaned_prizes
    ):
        if path_to_save is not None:
            save_benchmark_ledger(state, path_to_save)
        return state

    settled_entry = settle_entry_with_prizes(
        target_entry,
        cleaned_prizes,
        payout_per_hit_vnd=state.payout_per_hit_vnd,
        initial_bankroll_vnd=state.starting_bankroll_vnd,
    )

    updated_entries = list(state.entries)
    updated_entries[target_idx] = settled_entry

    new_state = recalculate_ledger_state(
        updated_entries,
        starting_bankroll_vnd=state.starting_bankroll_vnd,
        base_stake_per_number_vnd=state.base_stake_per_number_vnd,
        payout_per_hit_vnd=state.payout_per_hit_vnd,
        updated_at=updated_at,
        strict_chain=False,
    )

    if path_to_save is not None:
        save_benchmark_ledger(new_state, path_to_save)
    return new_state


record_morning_recommendation = record_pending_recommendation
