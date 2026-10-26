"""Pillar 1A: Canonicalizer for 18-prize XSMN draws and Dual-Horizon (5Y / 3Y) Slicing."""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from xsmn_alpha.constants import (
    CAGE_NUM_BALLS,
    PRIZES_PER_DRAW,
    STATION_CONFIG,
    VALID_HORIZONS,
    VALID_STATIONS,
)
from xsmn_alpha.exceptions import DataIntegrityError, InsufficientSampleSizeError
from xsmn_alpha.schemas import (
    CanonicalDrawRecord,
    StationCode,
    validate_iso_date,
    validate_two_digit_ascii,
)

_ASCII_FULL_PRIZE_RE = re.compile(r"^[0-9]{2,6}$", re.ASCII)
_DMY_DATE_RE = re.compile(r"^([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})$", re.ASCII)


def normalize_draw_date(date_str: Any) -> str:
    """Normalize a strict ASCII date ('YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY') to ISO format."""
    if not isinstance(date_str, str) or not date_str.isascii():
        raise DataIntegrityError(f"Invalid draw_date {date_str!r}; must be an ASCII string.")
    cleaned = date_str.strip()
    m_dmy = _DMY_DATE_RE.fullmatch(cleaned)
    if m_dmy:
        day, month, year = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            dt = datetime.date(year, month, day)
        except ValueError as exc:
            raise DataIntegrityError(f"Invalid calendar date {date_str!r}: {exc}") from exc
        return dt.isoformat()
    return validate_iso_date(cleaned)


def extract_last2_from_prize_token(raw_token: Any) -> str:
    """Extract and validate the last 2 ASCII digits ('00'..'99') from a full prize string."""
    if (
        not isinstance(raw_token, str)
        or not raw_token.isascii()
        or not _ASCII_FULL_PRIZE_RE.fullmatch(raw_token)
    ):
        raise DataIntegrityError(
            f"Invalid prize token {raw_token!r}; must be 2 to 6 strict ASCII digits."
        )
    return validate_two_digit_ascii(raw_token[-2:])


def decompose_cage_counts(prizes_last2: Sequence[str]) -> tuple[list[int], list[int]]:
    """Decompose 18 2-digit prizes (Giải 8 -> Giải ĐB) into 10-ball tens & units count vectors."""
    if (
        not isinstance(prizes_last2, Sequence)
        or isinstance(prizes_last2, (str, bytes))
        or len(prizes_last2) != PRIZES_PER_DRAW
    ):
        count = len(prizes_last2) if isinstance(prizes_last2, Sequence) else "non-sequence"
        raise DataIntegrityError(
            f"prizes_last2 must contain exactly {PRIZES_PER_DRAW} prizes, got {count}."
        )

    tens_counts = [0] * CAGE_NUM_BALLS
    units_counts = [0] * CAGE_NUM_BALLS
    for token in prizes_last2:
        cleaned = validate_two_digit_ascii(token)
        tens_counts[ord(cleaned[0]) - 48] += 1
        units_counts[ord(cleaned[1]) - 48] += 1

    if sum(tens_counts) != PRIZES_PER_DRAW or sum(units_counts) != PRIZES_PER_DRAW:
        raise DataIntegrityError("Cage count decomposition invariant sum == 18 violated.")
    return tens_counts, units_counts


def deduplicate_and_sort_raw_draws(
    raw_draws: Sequence[Mapping[str, Any]],
    station_code: str,
    *,
    extract_last2_from_full_prizes: bool = False,
) -> list[dict[str, Any]]:
    """Deduplicate overlapping batch draws (failing on conflicting prizes) and sort by draw_date."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(
            f"Invalid station_code {station_code!r}; must be in {sorted(VALID_STATIONS)}."
        )
    if not isinstance(raw_draws, Sequence) or isinstance(raw_draws, (str, bytes)) or not raw_draws:
        raise DataIntegrityError("raw_draws must be a non-empty sequence of draw mappings.")

    by_date: dict[str, dict[str, Any]] = {}
    for item in raw_draws:
        if not isinstance(item, Mapping):
            raise DataIntegrityError(f"Expected mapping in raw_draws, got {type(item).__name__}.")
        rec_station = item.get("station_code", station_code)
        if rec_station != station_code:
            raise DataIntegrityError(
                f"Station mismatch in raw draw: expected {station_code!r}, got {rec_station!r}."
            )
        iso_date = normalize_draw_date(item.get("draw_date"))
        raw_prizes = item.get("prizes_last2")
        if (
            not isinstance(raw_prizes, Sequence)
            or isinstance(raw_prizes, (str, bytes))
            or len(raw_prizes) != PRIZES_PER_DRAW
        ):
            raise DataIntegrityError(
                f"Draw on {iso_date} must have {PRIZES_PER_DRAW} prizes, got {raw_prizes!r}."
            )
        if extract_last2_from_full_prizes:
            prizes_last2 = [extract_last2_from_prize_token(p) for p in raw_prizes]
        else:
            prizes_last2 = [validate_two_digit_ascii(p) for p in raw_prizes]

        normalized_entry = {
            "station_code": station_code,
            "draw_date": iso_date,
            "prizes_last2": prizes_last2,
        }
        if iso_date in by_date:
            if by_date[iso_date]["prizes_last2"] != prizes_last2:
                raise DataIntegrityError(
                    f"Conflicting prizes_last2 for duplicate draw_date {iso_date} "
                    f"in {station_code}."
                )
        else:
            by_date[iso_date] = normalized_entry

    return [by_date[dt] for dt in sorted(by_date.keys())]


def canonicalize_draws(
    raw_draws: Sequence[Mapping[str, Any] | CanonicalDrawRecord],
    station_code: str,
    *,
    require_sorted: bool = True,
    extract_last2_from_full_prizes: bool = False,
) -> list[CanonicalDrawRecord]:
    """Convert raw draw dicts into a strictly sorted ascending sequence of CanonicalDrawRecord."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(
            f"Invalid station_code {station_code!r}; must be in {sorted(VALID_STATIONS)}."
        )
    if (
        not isinstance(raw_draws, Sequence)
        or isinstance(raw_draws, (str, bytes))
        or len(raw_draws) == 0
    ):
        raise DataIntegrityError("raw_draws cannot be empty.")

    station_typed = cast(StationCode, station_code)
    parsed_items: list[tuple[str, list[str]]] = []
    allowed_keys = {
        "station_code",
        "draw_date",
        "draw_index",
        "prizes_last2",
        "tens_counts",
        "units_counts",
    }

    for pos, item in enumerate(raw_draws):
        if isinstance(item, CanonicalDrawRecord):
            if item.station_code != station_code:
                raise DataIntegrityError(
                    f"Station code mismatch: expected {station_code!r}, got {item.station_code!r}."
                )
            if (
                isinstance(item.draw_index, bool)
                or not isinstance(item.draw_index, int)
                or item.draw_index < 0
            ):
                raise DataIntegrityError(
                    f"Invalid draw_index {item.draw_index!r} in CanonicalDrawRecord."
                )
            if require_sorted and item.draw_index != pos:
                raise DataIntegrityError(
                    f"Non-contiguous draw_index at position {pos}: "
                    f"expected {pos}, got {item.draw_index}."
                )
            draw_date = validate_iso_date(item.draw_date)
            prizes_last2 = [validate_two_digit_ascii(p) for p in item.prizes_last2]
            exp_tens, exp_units = decompose_cage_counts(prizes_last2)
            if item.tens_counts != exp_tens or item.units_counts != exp_units:
                raise DataIntegrityError(
                    f"Corrupted CanonicalDrawRecord on {draw_date}: "
                    f"cage counts do not match prizes_last2."
                )
        elif isinstance(item, Mapping):
            extra_keys = set(item.keys()) - allowed_keys
            if extra_keys:
                raise DataIntegrityError(
                    f"Unexpected extra fields in draw record: {sorted(extra_keys)}"
                )
            rec_station = item.get("station_code", station_code)
            if rec_station != station_code:
                raise DataIntegrityError(
                    f"Station code mismatch: expected {station_code!r}, got {rec_station!r}."
                )
            draw_date = validate_iso_date(item.get("draw_date"))
            raw_prizes = item.get("prizes_last2")
            if (
                not isinstance(raw_prizes, Sequence)
                or isinstance(raw_prizes, (str, bytes))
                or len(raw_prizes) != PRIZES_PER_DRAW
            ):
                raise DataIntegrityError(
                    f"Draw {draw_date} must contain {PRIZES_PER_DRAW} prizes in prizes_last2."
                )
            if extract_last2_from_full_prizes:
                prizes_last2 = [extract_last2_from_prize_token(p) for p in raw_prizes]
            else:
                prizes_last2 = [validate_two_digit_ascii(p) for p in raw_prizes]

            exp_tens, exp_units = decompose_cage_counts(prizes_last2)
            if "draw_index" in item or "tens_counts" in item or "units_counts" in item:
                raw_idx = item.get("draw_index", pos)
                if isinstance(raw_idx, bool) or not isinstance(raw_idx, int) or raw_idx < 0:
                    raise DataIntegrityError(
                        f"Invalid draw_index {raw_idx!r}; must be a non-negative integer."
                    )
                if require_sorted and "draw_index" in item and raw_idx != pos:
                    raise DataIntegrityError(
                        f"Non-contiguous draw_index at position {pos}: "
                        f"expected {pos}, got {raw_idx}."
                    )
                CanonicalDrawRecord.model_validate(
                    {
                        "station_code": station_typed,
                        "draw_date": draw_date,
                        "draw_index": raw_idx,
                        "prizes_last2": prizes_last2,
                        "tens_counts": item.get("tens_counts", exp_tens),
                        "units_counts": item.get("units_counts", exp_units),
                    }
                )
        else:
            raise DataIntegrityError(f"Unsupported draw record type: {type(item).__name__}.")

        parsed_items.append((draw_date, prizes_last2))

    # Enforce strict chronological order and reject duplicate dates (Gate 1: DataSchemaGate)
    seen_dates: set[str] = set()
    prev_date: str | None = None
    for draw_date, _ in parsed_items:
        if draw_date in seen_dates:
            raise DataIntegrityError(
                f"Duplicate draw_date {draw_date!r} detected for station {station_code}."
            )
        if require_sorted and prev_date is not None and draw_date < prev_date:
            raise DataIntegrityError(
                f"Chronological order violation for {station_code}: "
                f"{draw_date!r} appears after {prev_date!r}."
            )
        seen_dates.add(draw_date)
        prev_date = draw_date

    if not require_sorted:
        parsed_items.sort(key=lambda pair: pair[0])

    canonical_records: list[CanonicalDrawRecord] = []
    for draw_idx, (draw_date, prizes_last2) in enumerate(parsed_items):
        tens_counts, units_counts = decompose_cage_counts(prizes_last2)
        record = CanonicalDrawRecord(
            station_code=station_typed,
            draw_date=draw_date,
            draw_index=draw_idx,
            prizes_last2=prizes_last2,
            tens_counts=tens_counts,
            units_counts=units_counts,
        )
        canonical_records.append(record)

    return canonical_records


def slice_horizon(
    draws: Sequence[CanonicalDrawRecord],
    station_code: str,
    horizon: str,
) -> list[CanonicalDrawRecord]:
    """Slice a canonical draw sequence into '5y' or '3y' horizon and re-index 0..T-1."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(
            f"Invalid station_code {station_code!r}; must be in {sorted(VALID_STATIONS)}."
        )
    if not isinstance(horizon, str) or horizon.lower() not in VALID_HORIZONS:
        raise DataIntegrityError(f"Invalid horizon {horizon!r}; must be one of {VALID_HORIZONS}.")
    if not isinstance(draws, Sequence) or isinstance(draws, (str, bytes)) or len(draws) == 0:
        raise DataIntegrityError("draws sequence cannot be empty.")

    h_key = horizon.lower()
    required_draws = int(STATION_CONFIG[station_code]["horizons"][h_key])

    prev_date: str | None = None
    prev_idx: int | None = None
    for rec in draws:
        if not isinstance(rec, CanonicalDrawRecord):
            raise DataIntegrityError("All elements in draws must be CanonicalDrawRecord instances.")
        if rec.station_code != station_code:
            raise DataIntegrityError(
                f"Record station_code {rec.station_code!r} does not match {station_code!r}."
            )
        if (
            isinstance(rec.draw_index, bool)
            or not isinstance(rec.draw_index, int)
            or rec.draw_index < 0
        ):
            raise DataIntegrityError(f"Invalid draw_index {rec.draw_index!r} in slice_horizon.")
        if prev_idx is not None and rec.draw_index != prev_idx + 1:
            raise DataIntegrityError(
                f"Non-contiguous draw_index in slice_horizon: "
                f"expected {prev_idx + 1}, got {rec.draw_index}."
            )
        exp_tens, exp_units = decompose_cage_counts(rec.prizes_last2)
        if rec.tens_counts != exp_tens or rec.units_counts != exp_units:
            raise DataIntegrityError(
                f"Corrupted CanonicalDrawRecord on {rec.draw_date}: "
                f"cage counts do not match prizes_last2."
            )
        if prev_date is not None and rec.draw_date <= prev_date:
            raise DataIntegrityError(
                f"Chronological or duplicate date violation in slice_horizon: "
                f"{rec.draw_date!r} after {prev_date!r}."
            )
        prev_date = rec.draw_date
        prev_idx = rec.draw_index

    if len(draws) < required_draws:
        raise InsufficientSampleSizeError(
            f"Station {station_code} horizon {h_key!r} requires at least {required_draws} draws, "
            f"got {len(draws)}."
        )

    sliced = draws[-required_draws:]
    reindexed: list[CanonicalDrawRecord] = []
    for new_idx, rec in enumerate(sliced):
        reindexed.append(
            CanonicalDrawRecord(
                station_code=rec.station_code,
                draw_date=rec.draw_date,
                draw_index=new_idx,
                prizes_last2=list(rec.prizes_last2),
                tens_counts=list(rec.tens_counts),
                units_counts=list(rec.units_counts),
            )
        )
    return reindexed


def save_canonical_draws(
    draws: Sequence[CanonicalDrawRecord],
    file_path: str | Path,
) -> Path:
    """Validate and save a sequence of CanonicalDrawRecord to a UTF-8 JSON file."""
    if not draws:
        raise DataIntegrityError("Cannot save an empty sequence of CanonicalDrawRecord.")
    station_code = draws[0].station_code
    validated = canonicalize_draws(draws, station_code=station_code, require_sorted=True)
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [rec.model_dump() for rec in validated]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_canonical_draws(
    file_path: str | Path,
    station_code: str | None = None,
) -> list[CanonicalDrawRecord]:
    """Load and validate a sequence of CanonicalDrawRecord from a UTF-8 JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise DataIntegrityError(f"Canonical draw file not found: {path}")
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DataIntegrityError(f"Failed to parse JSON from {path}: {exc}") from exc

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise DataIntegrityError(f"Canonical draw JSON at {path} must be a non-empty list.")

    inferred_station = station_code
    if inferred_station is None:
        first_item = raw_data[0]
        if not isinstance(first_item, Mapping) or "station_code" not in first_item:
            raise DataIntegrityError(f"Missing station_code in {path}.")
        inferred_station = str(first_item["station_code"])

    return canonicalize_draws(raw_data, station_code=inferred_station, require_sorted=True)
