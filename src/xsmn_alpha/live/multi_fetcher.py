"""Stage 3 Pillar 1: 35-Station Incremental Multi-Source Fetcher, Failover & SHA-256 Cache."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import re
import unicodedata
from collections.abc import Coroutine, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

import httpx

from xsmn_alpha.constants import PRIZES_PER_DRAW
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.ingest.canonicalizer import (
    decompose_cage_counts,
    extract_last2_from_prize_token,
    normalize_draw_date,
)
from xsmn_alpha.ingest.fetcher import (
    _DATE_IN_TEXT_RE,
    _GENERIC_TABLE_RE,
    _PRIZE_CLASS_SPECS,
    _RIGHTCL_TABLE_RE,
    _ROW_LABEL_TO_CLASS,
    _TAG_RE,
    _TD_TH_RE,
    _TR_RE,
    _extract_9_classes_from_block,
    _extract_date_from_fragment,
    _extract_last2_tokens_from_fragment,
    _get_html_with_retries,
    format_date_dmy,
)
from xsmn_alpha.live.registry import (
    STATION_REGISTRY_35,
    VALID_35_STATION_CODES,
    get_station_meta,
)
from xsmn_alpha.schemas import (
    DataPipelineAuditRecord,
    Stage3CanonicalDrawRecord,
    validate_iso_date,
    validate_station_code_35,
    validate_two_digit_ascii,
)

DEFAULT_RAW_ALL_DIR: Path = Path("data/raw_all")
DEFAULT_FALLBACK_RAW_DIR: Path = Path("data/raw")
DEFAULT_MAX_CONCURRENCY: int = 6
DEFAULT_HTTP_TIMEOUT: float = 10.0
DEFAULT_HTTP_RETRIES: int = 3

_T = TypeVar("_T")

_BKQ_TABLE_SPLIT_RE = re.compile(
    r"(?=<table[^>]*class=[\"'][^\"']*bkqtinhmien(?:nam|trung)[^\"']*[\"'][^>]*>)",
    re.IGNORECASE,
)
_BKQ_TABLE_MARKER_RE = re.compile(r"bkqtinhmien(?:nam|trung)", re.IGNORECASE)
_VIETNAMESE_WORD_DATE_RE = re.compile(
    r"ngày\s+([0-9]{1,2})\s+tháng\s+([0-9]{1,2})\s+năm\s+(20[0-9]{2})",
    re.IGNORECASE,
)
_NAV_NOISE_BLOCK_RE = re.compile(
    r"<(?P<tag>nav|header|footer|aside|script|style|ul|ol)\b[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_ANCHOR_NOISE_RE = re.compile(
    r"<a\b[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
_DOMAIN_NOISE_RE = re.compile(
    r"(?:https?://\S+|\b(?:www\.)?(?:xskt\.com\.vn|minhngoc\.net\.vn|xoso\.com\.vn)\b)",
    re.IGNORECASE,
)


def _keyword_in_text(text: str, keyword: str) -> bool:
    """Match station keyword on strict word boundaries so 'xsdn' never matches 'xsdno'/'xsdng'."""
    pattern = rf"(?<!\w){re.escape(keyword.lower())}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _strip_navigation_and_domain_noise(
    fragment_html: str,
    *,
    strip_anchors: bool = True,
) -> str:
    """Remove navigation/chrome blocks, standalone anchor links, and provider domain names."""
    cleaned = unicodedata.normalize("NFC", fragment_html)
    cleaned = _NAV_NOISE_BLOCK_RE.sub(" ", cleaned)
    if strip_anchors:
        cleaned = _ANCHOR_NOISE_RE.sub(" ", cleaned)
    cleaned = _DOMAIN_NOISE_RE.sub(" ", cleaned)
    return cleaned


def _extract_date_from_fragment_35(
    fragment: str,
    fallback_date: str | None = None,
) -> str | None:
    """Extract and normalize the first valid numeric or Vietnamese word date from HTML."""
    plain = _TAG_RE.sub(" ", unicodedata.normalize("NFC", fragment))
    direct = _extract_date_from_fragment(plain, fallback_date=None)
    if direct is not None:
        return direct
    for match in _VIETNAMESE_WORD_DATE_RE.finditer(plain):
        day_s, month_s, year_s = match.group(1), match.group(2), match.group(3)
        candidate = f"{int(day_s):02d}-{int(month_s):02d}-{int(year_s):04d}"
        try:
            return normalize_draw_date(candidate)
        except DataIntegrityError:
            continue
    if fallback_date is not None:
        try:
            return normalize_draw_date(fallback_date)
        except DataIntegrityError:
            return None
    return None


def _extract_last_date_from_fragment_35(fragment: str) -> str | None:
    """Extract and normalize the last valid numeric or Vietnamese word date in an HTML fragment."""
    plain = _TAG_RE.sub(" ", unicodedata.normalize("NFC", fragment))
    candidates: list[tuple[int, str]] = []
    for match in _DATE_IN_TEXT_RE.finditer(plain):
        try:
            candidates.append((match.start(), normalize_draw_date(match.group(1))))
        except DataIntegrityError:
            continue
    for match in _VIETNAMESE_WORD_DATE_RE.finditer(plain):
        day_s, month_s, year_s = match.group(1), match.group(2), match.group(3)
        candidate = f"{int(day_s):02d}-{int(month_s):02d}-{int(year_s):04d}"
        try:
            candidates.append((match.start(), normalize_draw_date(candidate)))
        except DataIntegrityError:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _run_coroutine_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Execute an async coroutine synchronously, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _coerce_target_date(target_date: str | datetime.date | None = None) -> datetime.date:
    """Validate and convert target_date (str | date | None) to datetime.date."""
    if target_date is None:
        return datetime.date.today()
    if isinstance(target_date, datetime.date) and not isinstance(target_date, datetime.datetime):
        return target_date
    if isinstance(target_date, str):
        iso_str = validate_iso_date(target_date)
        return datetime.date.fromisoformat(iso_str)
    raise DataIntegrityError(
        f"target_date must be an ISO 'YYYY-MM-DD' string or datetime.date, got {target_date!r}."
    )


def build_station_minhngoc_url(station_code: str, iso_date: str) -> str:
    """Build Tier-1 primary endpoint URL for minhngoc.net.vn across all 35 stations."""
    meta = get_station_meta(station_code)
    region_slug = str(meta["region_slug"])
    slug = str(meta["minhngoc_slug"])
    dmy = format_date_dmy(iso_date)
    return f"https://www.minhngoc.net.vn/ket-qua-xo-so/{region_slug}/{slug}/{dmy}.html"


def build_station_xskt_url(station_code: str, iso_date: str) -> str:
    """Build Tier-2 Fallback 1 endpoint URL for xskt.com.vn across all 35 stations."""
    meta = get_station_meta(station_code)
    slug = str(meta["xskt_slug"])
    dmy = format_date_dmy(iso_date)
    return f"https://xskt.com.vn/{slug}/ngay-{dmy}"


def build_station_xoso_url(station_code: str, iso_date: str) -> str:
    """Build Tier-3 Fallback 2 endpoint URL for xoso.com.vn across all 35 stations."""
    meta = get_station_meta(station_code)
    slug = str(meta["xoso_slug"])
    dmy = format_date_dmy(iso_date)
    return f"https://xoso.com.vn/{slug}-{dmy}.html"


def _fragment_conflicts_with_station_35(fragment_html: str, station_code: str) -> bool:
    """Return True if fragment explicitly names a different station without target station."""
    meta = get_station_meta(station_code)
    cleaned_html = _strip_navigation_and_domain_noise(fragment_html, strip_anchors=True)
    normalized = cleaned_html.lower()
    plain = _TAG_RE.sub(" ", normalized)
    target_kws: tuple[str, ...] = tuple(meta["keywords"])

    has_other_station = False
    for other_code, other_meta in STATION_REGISTRY_35.items():
        if other_code == station_code:
            continue
        for kw in other_meta["keywords"]:
            if kw in ("xskt", "xoso"):
                continue
            if _keyword_in_text(plain, kw) or _keyword_in_text(normalized, kw):
                has_other_station = True
                break
        if has_other_station:
            break

    # For XSKT (Kon Tum), generic 'xskt' ("xổ số kiến thiết") must not override an explicit
    # other station name unless 'kon tum' / 'kon-tum' / 'kontum' is explicitly present.
    effective_target_kws = (
        tuple(kw for kw in target_kws if kw != "xskt")
        if (station_code == "XSKT" and has_other_station)
        else target_kws
    )
    if any(
        _keyword_in_text(plain, kw) or _keyword_in_text(normalized, kw)
        for kw in effective_target_kws
    ):
        return False

    return has_other_station


def _matches_station_35(block_html: str, station_code: str) -> bool:
    """Check whether a station sub-table matches the target station_code among 35 stations."""
    meta = get_station_meta(station_code)
    norm_block = unicodedata.normalize("NFC", block_html)
    tinh_match = re.search(
        r"<(?P<tag>td|div|th)[^>]*class=[\"'][^\"']*\btinh\b[^\"']*[\"'][^>]*>(.*?)</(?P=tag)>",
        norm_block,
        re.IGNORECASE | re.DOTALL,
    )
    if not tinh_match:
        return not _fragment_conflicts_with_station_35(norm_block, station_code)
    tinh_cleaned = _strip_navigation_and_domain_noise(tinh_match.group(2), strip_anchors=False)
    tinh_text = _TAG_RE.sub(" ", tinh_cleaned).lower()
    keywords: tuple[str, ...] = tuple(meta["keywords"])
    if station_code == "XSKT":
        for other_code, other_meta in STATION_REGISTRY_35.items():
            if other_code == "XSKT":
                continue
            other_kws = (kw for kw in other_meta["keywords"] if kw not in ("xskt", "xoso"))
            if any(_keyword_in_text(tinh_text, kw) for kw in other_kws):
                keywords = tuple(kw for kw in keywords if kw != "xskt")
                break
    return any(_keyword_in_text(tinh_text, kw) for kw in keywords)


def deduplicate_and_sort_station_draws(
    raw_draws: Sequence[Mapping[str, Any] | Stage3CanonicalDrawRecord],
    station_code: str,
    *,
    extract_last2_from_full_prizes: bool = False,
) -> list[dict[str, Any]]:
    """Deduplicate overlapping batch draws (failing on conflicting prizes) and sort by draw_date."""
    validate_station_code_35(station_code)
    if not isinstance(raw_draws, Sequence) or isinstance(raw_draws, (str, bytes)) or not raw_draws:
        raise DataIntegrityError("raw_draws must be a non-empty sequence of draw mappings.")

    by_date: dict[str, dict[str, Any]] = {}
    for item in raw_draws:
        if isinstance(item, Stage3CanonicalDrawRecord):
            rec_dict: Mapping[str, Any] = item.model_dump()
        elif isinstance(item, Mapping):
            rec_dict = item
        else:
            raise DataIntegrityError(f"Expected mapping in raw_draws, got {type(item).__name__}.")

        rec_station = rec_dict.get("station_code", station_code)
        if rec_station != station_code:
            raise DataIntegrityError(
                f"Station mismatch in raw draw: expected {station_code!r}, got {rec_station!r}."
            )
        iso_date = normalize_draw_date(rec_dict.get("draw_date"))
        raw_prizes = rec_dict.get("prizes_last2")
        if (
            not isinstance(raw_prizes, Sequence)
            or isinstance(raw_prizes, (str, bytes))
            or len(raw_prizes) != PRIZES_PER_DRAW
        ):
            raise DataIntegrityError(
                f"Draw on {iso_date} for {station_code} must have {PRIZES_PER_DRAW} prizes, "
                f"got {raw_prizes!r}."
            )
        if extract_last2_from_full_prizes:
            prizes_last2 = [extract_last2_from_prize_token(p) for p in raw_prizes]
        else:
            prizes_last2 = [validate_two_digit_ascii(p) for p in raw_prizes]

        decompose_cage_counts(prizes_last2)
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


def canonicalize_station_draws(
    raw_draws: Sequence[Mapping[str, Any] | Stage3CanonicalDrawRecord],
    station_code: str,
    *,
    require_sorted: bool = True,
    extract_last2_from_full_prizes: bool = False,
) -> list[Stage3CanonicalDrawRecord]:
    """Validate and convert raw draws into sorted Stage3CanonicalDrawRecord instances (Gate 1)."""
    validate_station_code_35(station_code)
    if (
        not isinstance(raw_draws, Sequence)
        or isinstance(raw_draws, (str, bytes))
        or len(raw_draws) == 0
    ):
        raise DataIntegrityError("raw_draws cannot be empty.")

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
        if isinstance(item, Stage3CanonicalDrawRecord):
            if item.station_code != station_code:
                raise DataIntegrityError(
                    f"Station code mismatch: expected {station_code!r}, got {item.station_code!r}."
                )
            draw_date = validate_iso_date(item.draw_date)
            prizes_last2 = [validate_two_digit_ascii(p) for p in item.prizes_last2]
            exp_tens, exp_units = decompose_cage_counts(prizes_last2)
            if item.tens_counts != exp_tens or item.units_counts != exp_units:
                raise DataIntegrityError(
                    f"Corrupted Stage3CanonicalDrawRecord on {draw_date}: cage counts mismatch."
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
            draw_date = normalize_draw_date(item.get("draw_date"))
            raw_prizes = item.get("prizes_last2")
            if (
                not isinstance(raw_prizes, Sequence)
                or isinstance(raw_prizes, (str, bytes))
                or len(raw_prizes) != PRIZES_PER_DRAW
            ):
                raise DataIntegrityError(
                    f"Draw {draw_date} for {station_code} must contain {PRIZES_PER_DRAW} prizes."
                )
            if extract_last2_from_full_prizes:
                prizes_last2 = [extract_last2_from_prize_token(p) for p in raw_prizes]
            else:
                prizes_last2 = [validate_two_digit_ascii(p) for p in raw_prizes]

            exp_tens, exp_units = decompose_cage_counts(prizes_last2)
            if "tens_counts" in item and item["tens_counts"] is not None:
                if list(item["tens_counts"]) != exp_tens:
                    raise DataIntegrityError(f"tens_counts mismatch on {draw_date}.")
            if "units_counts" in item and item["units_counts"] is not None:
                if list(item["units_counts"]) != exp_units:
                    raise DataIntegrityError(f"units_counts mismatch on {draw_date}.")
            if "draw_index" in item and item["draw_index"] is not None:
                raw_idx = item["draw_index"]
                if isinstance(raw_idx, bool) or not isinstance(raw_idx, int) or raw_idx < 0:
                    raise DataIntegrityError(f"Invalid draw_index {raw_idx!r}.")
                if require_sorted and raw_idx != pos:
                    raise DataIntegrityError(
                        f"Non-contiguous draw_index at position {pos}: "
                        f"expected {pos}, got {raw_idx}."
                    )
        else:
            raise DataIntegrityError(f"Unsupported draw record type: {type(item).__name__}.")

        parsed_items.append((draw_date, prizes_last2))

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

    return [
        Stage3CanonicalDrawRecord.from_prizes(
            station_code=station_code,
            draw_date=draw_date,
            draw_index=idx,
            prizes_last2=prizes_last2,
        )
        for idx, (draw_date, prizes_last2) in enumerate(parsed_items)
    ]


def parse_station_minhngoc_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse minhngoc.net.vn HTML tables for any of the 35 XSMN/XSMT stations."""
    validate_station_code_35(station_code)
    if not isinstance(html, str) or not html.strip():
        return []
    html = unicodedata.normalize("NFC", html)

    parts = _BKQ_TABLE_SPLIT_RE.split(html)
    results: list[dict[str, Any]] = []
    for part in parts:
        if not _BKQ_TABLE_MARKER_RE.search(part):
            continue
        draw_date = _extract_date_from_fragment_35(part, fallback_date=fallback_date)
        if draw_date is None:
            continue

        rightcl_blocks = _RIGHTCL_TABLE_RE.findall(part)
        if rightcl_blocks:
            for sub_block in rightcl_blocks:
                if not _matches_station_35(sub_block, station_code):
                    continue
                prizes = _extract_9_classes_from_block(sub_block)
                if prizes is not None:
                    decompose_cage_counts(prizes)
                    results.append(
                        {
                            "station_code": station_code,
                            "draw_date": draw_date,
                            "prizes_last2": prizes,
                        }
                    )
        else:
            if _matches_station_35(part, station_code):
                prizes = _extract_9_classes_from_block(part)
                if prizes is not None:
                    decompose_cage_counts(prizes)
                    results.append(
                        {
                            "station_code": station_code,
                            "draw_date": draw_date,
                            "prizes_last2": prizes,
                        }
                    )

    if not results:
        return []
    return deduplicate_and_sort_station_draws(results, station_code=station_code)


def _parse_station_labeled_table_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse fallback HTML tables (xskt.com.vn / xoso.com.vn) for any of the 35 stations."""
    validate_station_code_35(station_code)
    if not isinstance(html, str) or not html.strip():
        return []
    html = unicodedata.normalize("NFC", html)

    direct = parse_station_minhngoc_html(
        html, station_code=station_code, fallback_date=fallback_date
    )
    if direct:
        return direct

    results: list[dict[str, Any]] = []
    expected_map = dict(_PRIZE_CLASS_SPECS)
    table_matches = list(_GENERIC_TABLE_RE.finditer(html))

    for idx, table_match in enumerate(table_matches):
        table_html = table_match.group(1)
        prev_end = table_matches[idx - 1].end() if idx > 0 else 0
        context_before = html[prev_end : table_match.start()]

        if _fragment_conflicts_with_station_35(context_before + " " + table_html, station_code):
            continue

        class_to_prizes: dict[str, list[str]] = {}
        table_invalid = False

        for tr_match in _TR_RE.finditer(table_html):
            cells = _TD_TH_RE.findall(tr_match.group(1))
            if len(cells) < 2:
                continue
            raw_label = _TAG_RE.sub("", cells[0]).strip().lower()
            normalized_label = re.sub(r"[\s:_-]+", "", raw_label)
            cls_name = _ROW_LABEL_TO_CLASS.get(normalized_label)
            if cls_name is None:
                continue
            if cls_name in class_to_prizes:
                table_invalid = True
                break
            expected_count = expected_map[cls_name]
            extracted = _extract_last2_tokens_from_fragment(cells[1], expected_count)
            if extracted is None:
                table_invalid = True
                break
            class_to_prizes[cls_name] = extracted

        if not table_invalid and len(class_to_prizes) == len(_PRIZE_CLASS_SPECS):
            ordered_prizes: list[str] = []
            for cls_name, _ in _PRIZE_CLASS_SPECS:
                ordered_prizes.extend(class_to_prizes[cls_name])
            if len(ordered_prizes) == PRIZES_PER_DRAW:
                draw_date = _extract_date_from_fragment_35(table_html)
                if draw_date is None:
                    draw_date = _extract_last_date_from_fragment_35(context_before)
                if draw_date is None and len(table_matches) == 1 and fallback_date is not None:
                    draw_date = _extract_date_from_fragment_35("", fallback_date=fallback_date)
                if draw_date is not None:
                    decompose_cage_counts(ordered_prizes)
                    results.append(
                        {
                            "station_code": station_code,
                            "draw_date": draw_date,
                            "prizes_last2": ordered_prizes,
                        }
                    )

    if not results:
        return []
    return deduplicate_and_sort_station_draws(results, station_code=station_code)


def parse_station_xskt_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Tier-2 Fallback 1 (xskt.com.vn) HTML into validated 18-prize raw draw dicts."""
    return _parse_station_labeled_table_html(
        html, station_code=station_code, fallback_date=fallback_date
    )


def parse_station_xoso_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Tier-3 Fallback 2 (xoso.com.vn) HTML into validated 18-prize raw draw dicts."""
    return _parse_station_labeled_table_html(
        html, station_code=station_code, fallback_date=fallback_date
    )


async def fetch_station_draw_with_failover(
    client: httpx.AsyncClient,
    station_code: str,
    draw_date: str,
    *,
    retries: int = DEFAULT_HTTP_RETRIES,
    backoff_base: float = 0.05,
) -> tuple[dict[str, Any], bool, str]:
    """Fetch a single 18-prize draw for station_code on draw_date with 3-tier automatic failover.

    Returns (draw_dict, fallback_used, provider_name).
    Raises DataIntegrityError if all 3 sources fail or return incomplete (<18 prize) draws.
    """
    validate_station_code_35(station_code)
    target_date = normalize_draw_date(draw_date)

    providers = (
        (
            "minhngoc.net.vn",
            build_station_minhngoc_url(station_code, target_date),
            parse_station_minhngoc_html,
            False,
        ),
        (
            "xskt.com.vn",
            build_station_xskt_url(station_code, target_date),
            parse_station_xskt_html,
            True,
        ),
        (
            "xoso.com.vn",
            build_station_xoso_url(station_code, target_date),
            parse_station_xoso_html,
            True,
        ),
    )

    for provider_name, url, parser_fn, is_fallback in providers:
        html = await _get_html_with_retries(client, url, retries=retries, backoff_base=backoff_base)
        if not html:
            continue
        try:
            parsed_draws = parser_fn(html, station_code=station_code, fallback_date=None)
        except DataIntegrityError:
            continue
        for draw in parsed_draws:
            if draw["draw_date"] == target_date and len(draw["prizes_last2"]) == PRIZES_PER_DRAW:
                decompose_cage_counts(draw["prizes_last2"])
                return (draw, is_fallback, provider_name)

    raise DataIntegrityError(
        f"All 3 sources (minhngoc, xskt, xoso) failed to provide a valid 18-prize draw "
        f"for {station_code} on {target_date}."
    )


def compute_station_draws_sha256(
    raw_draws: Sequence[Mapping[str, Any] | Stage3CanonicalDrawRecord],
    station_code: str | None = None,
) -> str:
    """Compute a deterministic SHA-256 hex digest over normalized draw dictionaries."""
    if not isinstance(raw_draws, Sequence) or isinstance(raw_draws, (str, bytes)):
        raise DataIntegrityError("raw_draws must be a sequence of draw mappings.")
    if station_code is not None:
        validate_station_code_35(station_code)

    canonical_payload: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_draws):
        if isinstance(item, Stage3CanonicalDrawRecord):
            d: Mapping[str, Any] = item.model_dump()
        elif isinstance(item, Mapping):
            d = item
        else:
            raise DataIntegrityError(
                f"Draw entry at index {idx} must be a mapping, got {type(item).__name__}."
            )
        try:
            rec_station = d.get("station_code") or station_code
            if not rec_station:
                raise KeyError("station_code")
            prizes = d["prizes_last2"]
            if not isinstance(prizes, Sequence) or isinstance(prizes, (str, bytes)):
                raise TypeError("prizes_last2 must be a sequence of strings.")
            canonical_payload.append(
                {
                    "station_code": str(rec_station),
                    "draw_date": str(d["draw_date"]),
                    "prizes_last2": [str(p) for p in prizes],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataIntegrityError(
                f"Malformed draw record at index {idx} in compute_station_draws_sha256: {exc}"
            ) from exc

    serialized = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def get_station_raw_cache_path(
    station_code: str,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
) -> Path:
    """Return the path to <raw_dir>/<STATION_CODE>_draws.json for any of the 35 stations."""
    validate_station_code_35(station_code)
    return Path(raw_dir) / f"{station_code}_draws.json"


def save_station_raw_cache(
    station_code: str,
    raw_draws: Sequence[Mapping[str, Any] | Stage3CanonicalDrawRecord],
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
) -> Path:
    """Deduplicate, validate via Gate 1, compute SHA-256, and save draws to <CODE>_draws.json."""
    meta = get_station_meta(station_code)
    cleaned = deduplicate_and_sort_station_draws(raw_draws, station_code=station_code)
    canonicalize_station_draws(cleaned, station_code=station_code, require_sorted=True)
    digest = compute_station_draws_sha256(cleaned, station_code=station_code)

    cache_path = get_station_raw_cache_path(station_code, raw_dir=raw_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "station_code": station_code,
        "station_name": str(meta["name"]),
        "region": str(meta["region"]),
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "draw_count": len(cleaned),
        "last_draw_date": cleaned[-1]["draw_date"],
        "sha256": digest,
        "draws": cleaned,
    }
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cache_path


def load_station_raw_cache(
    station_code: str,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    *,
    verify_sha256: bool = True,
    allow_unhashed_legacy: bool = False,
) -> list[dict[str, Any]]:
    """Load raw draws from local cache and verify SHA-256 and Gate 1 schema integrity."""
    cache_path = get_station_raw_cache_path(station_code, raw_dir=raw_dir)
    if not cache_path.exists():
        raise DataIntegrityError(f"Raw cache file does not exist: {cache_path}")
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DataIntegrityError(f"Corrupted JSON in raw cache {cache_path}: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise DataIntegrityError(f"Invalid cache structure in {cache_path}.")
    if payload.get("station_code") != station_code:
        raise DataIntegrityError(
            f"Cache station_code mismatch in {cache_path}: {payload.get('station_code')!r}."
        )
    draws = payload.get("draws")
    if not isinstance(draws, list) or not draws:
        raise DataIntegrityError(f"Missing or empty draws list in {cache_path}.")

    if "draw_count" in payload:
        draw_count = payload.get("draw_count")
        if (
            isinstance(draw_count, bool)
            or not isinstance(draw_count, int)
            or draw_count != len(draws)
        ):
            raise DataIntegrityError(
                f"Cache draw_count mismatch in {cache_path}: "
                f"expected {len(draws)}, got {draw_count!r}."
            )

    has_sha_key = "sha256" in payload
    expected_sha = payload.get("sha256")
    if has_sha_key:
        if not isinstance(expected_sha, str) or not expected_sha:
            raise DataIntegrityError(f"Invalid sha256 field in {cache_path}.")
        actual_sha = compute_station_draws_sha256(draws, station_code=station_code)
        if actual_sha != expected_sha:
            raise DataIntegrityError(
                f"SHA-256 integrity mismatch for {cache_path}: "
                f"expected {expected_sha}, computed {actual_sha}."
            )
    elif verify_sha256 and not allow_unhashed_legacy:
        raise DataIntegrityError(f"Missing sha256 signature in {cache_path}.")

    canonicalize_station_draws(draws, station_code=station_code, require_sorted=True)
    cleaned = deduplicate_and_sort_station_draws(draws, station_code=station_code)

    if "last_draw_date" in payload:
        last_draw_date = payload.get("last_draw_date")
        if last_draw_date != cleaned[-1]["draw_date"]:
            raise DataIntegrityError(
                f"Cache last_draw_date mismatch in {cache_path}: "
                f"expected {cleaned[-1]['draw_date']!r}, got {last_draw_date!r}."
            )

    return cleaned


load_station_cache_file = load_station_raw_cache


def generate_station_expected_draw_dates(
    station_code: str,
    num_draws: int,
    as_of_date: str | datetime.date | None = None,
) -> list[str]:
    """Generate expected draw dates (YYYY-MM-DD) backwards from as_of_date by station schedule."""
    meta = get_station_meta(station_code)
    if isinstance(num_draws, bool) or not isinstance(num_draws, int) or num_draws <= 0:
        raise DataIntegrityError("num_draws must be a positive integer.")

    cursor = _coerce_target_date(as_of_date)
    allowed_weekdays = set(meta["draw_days_of_week"])
    dates: list[str] = []
    while len(dates) < num_draws:
        if cursor.weekday() in allowed_weekdays:
            dates.append(cursor.isoformat())
        cursor -= datetime.timedelta(days=1)
    dates.reverse()
    return dates


async def sync_station_draws_async(
    station_code: str,
    *,
    target_date: str | datetime.date | None = None,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    offline: bool = False,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[Stage3CanonicalDrawRecord], int]:
    """Incrementally sync 18-prize draws for station_code up to target_date with 3-tier failover.

    Returns (canonical_draws_up_to_target_date, fallback_used_count).
    """
    meta = get_station_meta(station_code)
    target_dt = _coerce_target_date(target_date)
    target_iso = target_dt.isoformat()
    target_3y = int(meta["target_3y"])

    raw_dir_path = Path(raw_dir)
    cache_path = get_station_raw_cache_path(station_code, raw_dir=raw_dir_path)

    all_cached_draws: list[dict[str, Any]] = []

    if cache_path.exists():
        all_cached_draws = load_station_raw_cache(
            station_code,
            raw_dir=raw_dir_path,
            verify_sha256=True,
            allow_unhashed_legacy=False,
        )
    elif raw_dir_path.resolve() == DEFAULT_RAW_ALL_DIR.resolve():
        fallback_path = DEFAULT_FALLBACK_RAW_DIR / f"{station_code}_draws.json"
        if fallback_path.exists():
            all_cached_draws = load_station_raw_cache(
                station_code,
                raw_dir=DEFAULT_FALLBACK_RAW_DIR,
                verify_sha256=True,
                allow_unhashed_legacy=False,
            )
            save_station_raw_cache(station_code, all_cached_draws, raw_dir=raw_dir_path)

    cached_up_to_target = [d for d in all_cached_draws if d["draw_date"] <= target_iso]

    if offline:
        if not cached_up_to_target:
            raise DataIntegrityError(
                f"Offline sync requested for {station_code}, but no cached draws <= {target_iso} "
                f"exist in {raw_dir_path}."
            )
        return (
            canonicalize_station_draws(
                cached_up_to_target, station_code=station_code, require_sorted=True
            ),
            0,
        )

    expected_dates = generate_station_expected_draw_dates(
        station_code,
        num_draws=target_3y,
        as_of_date=target_dt,
    )
    existing_dates = {d["draw_date"] for d in cached_up_to_target}
    pre_target_dates = [d["draw_date"] for d in cached_up_to_target if d["draw_date"] < target_iso]
    if pre_target_dates:
        first_cached_date = pre_target_dates[0]
        delta_dates = [
            dt
            for dt in expected_dates
            if first_cached_date <= dt <= target_iso and dt not in existing_dates
        ]
    else:
        delta_dates = [dt for dt in expected_dates if dt <= target_iso and dt not in existing_dates]

    if not delta_dates:
        return (
            canonicalize_station_draws(
                cached_up_to_target, station_code=station_code, require_sorted=True
            ),
            0,
        )

    semaphore = asyncio.Semaphore(max_concurrency)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    fallback_used_count = 0
    by_date: dict[str, dict[str, Any]] = {d["draw_date"]: d for d in all_cached_draws}

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        transport=transport,
    ) as client:

        async def _fetch_delta(dt: str) -> tuple[dict[str, Any] | None, bool]:
            async with semaphore:
                try:
                    draw_dict, used_fb, _provider = await fetch_station_draw_with_failover(
                        client=client,
                        station_code=station_code,
                        draw_date=dt,
                        retries=retries,
                    )
                    return (draw_dict, used_fb)
                except DataIntegrityError:
                    # Only allow skipping today's not-yet-drawn target_iso in live mode
                    # when full 3Y pre-draw history (< target_iso) is already verified in cache.
                    if (
                        transport is None
                        and dt == target_iso
                        and len(cached_up_to_target) >= target_3y
                        and all(d < target_iso for d in delta_dates if d != target_iso)
                    ):
                        return (None, False)
                    raise

        delta_results = await asyncio.gather(*(_fetch_delta(dt) for dt in delta_dates))

    added_any = False
    for draw_dict, used_fb in delta_results:
        if used_fb:
            fallback_used_count += 1
        if draw_dict is not None:
            by_date[draw_dict["draw_date"]] = draw_dict
            added_any = True

    merged_list = [by_date[dt] for dt in sorted(by_date.keys())]
    if not merged_list:
        raise DataIntegrityError(f"No draws available for {station_code} up to {target_iso}.")

    if added_any or not cache_path.exists():
        save_station_raw_cache(station_code, merged_list, raw_dir=raw_dir_path)

    final_up_to_target = [d for d in merged_list if d["draw_date"] <= target_iso]
    return (
        canonicalize_station_draws(
            final_up_to_target, station_code=station_code, require_sorted=True
        ),
        fallback_used_count,
    )


def sync_station_draws(
    station_code: str,
    *,
    target_date: str | datetime.date | None = None,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    offline: bool = False,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[Stage3CanonicalDrawRecord], int]:
    """Synchronous wrapper for sync_station_draws_async."""
    return _run_coroutine_sync(
        sync_station_draws_async(
            station_code=station_code,
            target_date=target_date,
            raw_dir=raw_dir,
            offline=offline,
            max_concurrency=max_concurrency,
            timeout=timeout,
            retries=retries,
            transport=transport,
        )
    )


async def sync_all_35_stations_async(
    *,
    target_date: str | datetime.date | None = None,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    station_codes: Sequence[str] | None = None,
    offline: bool = False,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[dict[str, list[Stage3CanonicalDrawRecord]], DataPipelineAuditRecord]:
    """Sync all 35 stations (or a specified subset) and return draws + DataPipelineAuditRecord."""
    target_dt = _coerce_target_date(target_date)
    target_iso = target_dt.isoformat()

    codes_to_sync = (
        tuple(STATION_REGISTRY_35.keys()) if station_codes is None else tuple(station_codes)
    )
    if not codes_to_sync:
        raise DataIntegrityError("station_codes cannot be empty.")
    for code in codes_to_sync:
        validate_station_code_35(code)

    draws_by_station: dict[str, list[Stage3CanonicalDrawRecord]] = {}
    total_fallback_used = 0
    latest_date_seen = ""

    for code in codes_to_sync:
        records, fb_count = await sync_station_draws_async(
            station_code=code,
            target_date=target_dt,
            raw_dir=raw_dir,
            offline=offline,
            max_concurrency=max_concurrency,
            timeout=timeout,
            retries=retries,
            transport=transport,
        )
        draws_by_station[code] = records
        total_fallback_used += fb_count
        if records and records[-1].draw_date > latest_date_seen:
            latest_date_seen = records[-1].draw_date

    ict_tz = datetime.timezone(datetime.timedelta(hours=7))
    now_ict = datetime.datetime.now(ict_tz).isoformat(timespec="seconds")

    audit = DataPipelineAuditRecord(
        audit_timestamp_ict=now_ict,
        target_date=target_iso,
        total_stations_35=len(VALID_35_STATION_CODES),
        stations_synced_ok=len(draws_by_station),
        fallback_used_count=total_fallback_used,
        schema_gate_passed=True,
        latest_settled_date=latest_date_seen,
        notes_vi=(
            f"Đã xác thực DataSchemaGate & SHA-256 cho {len(draws_by_station)}/"
            f"{len(VALID_35_STATION_CODES)} đài (Failover={total_fallback_used}, "
            f"kỳ mới nhất={latest_date_seen})."
        ),
    )
    return (draws_by_station, audit)


def sync_all_35_stations(
    *,
    target_date: str | datetime.date | None = None,
    raw_dir: str | Path = DEFAULT_RAW_ALL_DIR,
    station_codes: Sequence[str] | None = None,
    offline: bool = False,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[dict[str, list[Stage3CanonicalDrawRecord]], DataPipelineAuditRecord]:
    """Synchronous wrapper for sync_all_35_stations_async."""
    return _run_coroutine_sync(
        sync_all_35_stations_async(
            target_date=target_date,
            raw_dir=raw_dir,
            station_codes=station_codes,
            offline=offline,
            max_concurrency=max_concurrency,
            timeout=timeout,
            retries=retries,
            transport=transport,
        )
    )
