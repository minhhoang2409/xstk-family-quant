"""Pillar 1A: Automated Multi-Source XSMN Draw Fetcher, Fallback Verifier, and SHA-256 Cache."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

from xsmn_alpha.constants import (
    PRIZES_PER_DRAW,
    STATION_CONFIG,
    VALID_STATIONS,
)
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.ingest.canonicalizer import (
    canonicalize_draws,
    decompose_cage_counts,
    deduplicate_and_sort_raw_draws,
    extract_last2_from_prize_token,
    normalize_draw_date,
)
from xsmn_alpha.schemas import CanonicalDrawRecord, validate_iso_date

DEFAULT_MAX_CONCURRENCY: int = 6
DEFAULT_HTTP_TIMEOUT: float = 10.0
DEFAULT_HTTP_RETRIES: int = 3
DEFAULT_RAW_DIR: Path = Path("data/raw")

_PRIZE_CLASS_SPECS: tuple[tuple[str, int], ...] = (
    ("giai8", 1),
    ("giai7", 1),
    ("giai6", 3),
    ("giai5", 1),
    ("giai4", 7),
    ("giai3", 2),
    ("giai2", 1),
    ("giai1", 1),
    ("giaidb", 1),
)

_STATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "XSHCM": ("tp-hcm", "tp. hcm", "tp.hcm", "tp hcm", "hồ chí minh", "ho chi minh", "xshcm"),
    "XSVL": ("vinh-long", "vĩnh long", "vinh long", "xsvl"),
}

_OTHER_STATION_KEYWORDS: tuple[str, ...] = (
    "cần thơ",
    "can tho",
    "xsct",
    "đồng tháp",
    "dong thap",
    "xsdt",
    "cà mau",
    "ca mau",
    "xscm",
    "bến tre",
    "ben tre",
    "xsbt",
    "vũng tàu",
    "vung tau",
    "xsvt",
    "bạc liêu",
    "bac lieu",
    "xsbl",
    "đồng nai",
    "dong nai",
    "xsdn",
    "sóc trăng",
    "soc trang",
    "xsst",
    "tây ninh",
    "tay ninh",
    "xstn",
    "an giang",
    "xsag",
    "bình thuận",
    "binh thuan",
    "xsbth",
    "bình dương",
    "binh duong",
    "xsbd",
    "trà vinh",
    "tra vinh",
    "xstv",
    "long an",
    "xsla",
    "bình phước",
    "binh phuoc",
    "xsbp",
    "hậu giang",
    "hau giang",
    "xshg",
    "tiền giang",
    "tien giang",
    "xstg",
    "kiên giang",
    "kien giang",
    "xskg",
    "đà lạt",
    "da lat",
    "xsdl",
)

_DATE_IN_TEXT_RE = re.compile(
    r"\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})\b"
)
_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_BKQ_RE = re.compile(
    r"<table[^>]*class=[\"'][^\"']*bkqtinhmiennam[^\"']*[\"'][^>]*>(.*?)(?=</table>\s*(?:<table|<div|</body>|$))",
    re.IGNORECASE | re.DOTALL,
)
_RIGHTCL_TABLE_RE = re.compile(
    r"<table[^>]*class=[\"'][^\"']*rightcl[^\"']*[\"'][^>]*>(.*?)</table>",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TD_TH_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)

_ROW_LABEL_TO_CLASS: dict[str, str] = {
    "g8": "giai8",
    "g.8": "giai8",
    "giai8": "giai8",
    "giải8": "giai8",
    "giảitám": "giai8",
    "giaitam": "giai8",
    "8": "giai8",
    "g7": "giai7",
    "g.7": "giai7",
    "giai7": "giai7",
    "giải7": "giai7",
    "giảibảy": "giai7",
    "giaibay": "giai7",
    "7": "giai7",
    "g6": "giai6",
    "g.6": "giai6",
    "giai6": "giai6",
    "giải6": "giai6",
    "giảisáu": "giai6",
    "giaisau": "giai6",
    "6": "giai6",
    "g5": "giai5",
    "g.5": "giai5",
    "giai5": "giai5",
    "giải5": "giai5",
    "giảinăm": "giai5",
    "giainam": "giai5",
    "5": "giai5",
    "g4": "giai4",
    "g.4": "giai4",
    "giai4": "giai4",
    "giải4": "giai4",
    "giảitư": "giai4",
    "giaitu": "giai4",
    "giảibốn": "giai4",
    "4": "giai4",
    "g3": "giai3",
    "g.3": "giai3",
    "giai3": "giai3",
    "giải3": "giai3",
    "giảiba": "giai3",
    "giaiba": "giai3",
    "3": "giai3",
    "g2": "giai2",
    "g.2": "giai2",
    "giai2": "giai2",
    "giải2": "giai2",
    "giảinhì": "giai2",
    "giainhi": "giai2",
    "2": "giai2",
    "g1": "giai1",
    "g.1": "giai1",
    "giai1": "giai1",
    "giải1": "giai1",
    "giảinhất": "giai1",
    "giainhat": "giai1",
    "1": "giai1",
    "đb": "giaidb",
    "db": "giaidb",
    "g.đb": "giaidb",
    "g.db": "giaidb",
    "gđb": "giaidb",
    "gdb": "giaidb",
    "giaidb": "giaidb",
    "giảiđb": "giaidb",
    "giảiđặcbiệt": "giaidb",
    "giaidacbiet": "giaidb",
    "đặcbiệt": "giaidb",
    "dacbiet": "giaidb",
}


def format_date_dmy(iso_date: str) -> str:
    """Convert an ISO 'YYYY-MM-DD' date string into 'DD-MM-YYYY' for URL endpoints."""
    validated = validate_iso_date(iso_date)
    dt = datetime.date.fromisoformat(validated)
    return dt.strftime("%d-%m-%Y")


def build_minhngoc_url(station_code: str, iso_date: str) -> str:
    """Build primary batch endpoint URL for minhngoc.net.vn."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Unsupported station_code: {station_code!r}")
    slug = STATION_CONFIG[station_code]["minhngoc_slug"]
    dmy = format_date_dmy(iso_date)
    return f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-nam/{slug}/{dmy}.html"


def build_xskt_url(station_code: str, iso_date: str) -> str:
    """Build Fallback 1 endpoint URL for xskt.com.vn."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Unsupported station_code: {station_code!r}")
    slug = STATION_CONFIG[station_code]["xskt_slug"]
    dmy = format_date_dmy(iso_date)
    return f"https://xskt.com.vn/{slug}/ngay-{dmy}"


def build_xoso_url(station_code: str, iso_date: str) -> str:
    """Build Fallback 2 endpoint URL for xoso.com.vn."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Unsupported station_code: {station_code!r}")
    slug = STATION_CONFIG[station_code]["xoso_slug"]
    dmy = format_date_dmy(iso_date)
    return f"https://xoso.com.vn/{slug}-{dmy}.html"


def _strip_tags_to_tokens(fragment: str) -> list[str]:
    """Strip HTML tags and split prize content into tokens without stripping minus signs."""
    text = _TAG_RE.sub(" ", fragment)
    text = text.replace("&nbsp;", " ").replace("|", " ")
    text = re.sub(r"\s+-\s+", " ", text)
    return [tok.strip() for tok in text.split() if tok.strip()]


def _extract_last2_tokens_from_fragment(fragment: str, expected_count: int) -> list[str] | None:
    """Extract exact expected_count of 2-digit last2 strings from an HTML prize cell."""
    plain = _TAG_RE.sub(" ", fragment).replace("&nbsp;", " ")
    if re.search(r"(?<![0-9])-[0-9]", plain):
        return None
    raw_tokens = _strip_tags_to_tokens(fragment)
    if not raw_tokens:
        return None
    last2_list: list[str] = []
    for tok in raw_tokens:
        try:
            last2_list.append(extract_last2_from_prize_token(tok))
        except DataIntegrityError:
            return None
    if len(last2_list) != expected_count:
        return None
    return last2_list


def _extract_date_from_fragment(fragment: str, fallback_date: str | None = None) -> str | None:
    """Extract and normalize the first valid calendar date from an HTML fragment."""
    for match in _DATE_IN_TEXT_RE.finditer(_TAG_RE.sub(" ", fragment)):
        candidate = match.group(1)
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


def _extract_last_date_from_fragment(fragment: str) -> str | None:
    """Extract and normalize the last valid calendar date in an HTML heading/context fragment."""
    found: str | None = None
    for match in _DATE_IN_TEXT_RE.finditer(_TAG_RE.sub(" ", fragment)):
        candidate = match.group(1)
        try:
            found = normalize_draw_date(candidate)
        except DataIntegrityError:
            continue
    return found


def _fragment_conflicts_with_station(fragment_html: str, station_code: str) -> bool:
    """Return True if fragment explicitly names a different station without target station."""
    normalized = unicodedata.normalize("NFC", fragment_html).lower()
    plain = _TAG_RE.sub(" ", normalized)
    target_kws = _STATION_KEYWORDS.get(station_code, ())
    if any(kw in plain or kw in normalized for kw in target_kws):
        return False
    for other_code, other_kws in _STATION_KEYWORDS.items():
        if other_code != station_code and any(kw in plain or kw in normalized for kw in other_kws):
            return True
    return any(kw in plain for kw in _OTHER_STATION_KEYWORDS)


def _extract_9_classes_from_block(block_html: str) -> list[str] | None:
    """Extract 18 prizes in exact order (giai8 -> giaidb) from a block with class='giaiX'."""
    prizes_last2: list[str] = []
    for cls_name, expected_count in _PRIZE_CLASS_SPECS:
        td_pattern = re.compile(
            rf"<td[^>]*class=[\"'][^\"']*\b{cls_name}\b[^\"']*[\"'][^>]*>(.*?)</td>",
            re.IGNORECASE | re.DOTALL,
        )
        td_matches = td_pattern.findall(block_html)
        if len(td_matches) > 1:
            return None
        if len(td_matches) == 1:
            content = td_matches[0]
        else:
            div_pattern = re.compile(
                rf"<(?P<tag>tr|div|span)[^>]*class=[\"'][^\"']*\b{cls_name}\b[^\"']*[\"'][^>]*>(.*?)</(?P=tag)>",
                re.IGNORECASE | re.DOTALL,
            )
            div_matches = div_pattern.findall(block_html)
            if len(div_matches) != 1:
                return None
            content = div_matches[0][1]

        extracted = _extract_last2_tokens_from_fragment(content, expected_count)
        if extracted is None:
            return None
        prizes_last2.extend(extracted)

    if len(prizes_last2) != PRIZES_PER_DRAW:
        return None
    return prizes_last2


def _matches_station(block_html: str, station_code: str) -> bool:
    """Check whether a station sub-table matches the target station_code."""
    norm_block = unicodedata.normalize("NFC", block_html)
    tinh_match = re.search(
        r"<(?P<tag>td|div|th)[^>]*class=[\"'][^\"']*\btinh\b[^\"']*[\"'][^>]*>(.*?)</(?P=tag)>",
        norm_block,
        re.IGNORECASE | re.DOTALL,
    )
    if not tinh_match:
        return not _fragment_conflicts_with_station(norm_block, station_code)
    tinh_text = tinh_match.group(2).lower()
    keywords = _STATION_KEYWORDS.get(station_code, ())
    return any(kw in tinh_text for kw in keywords)


def parse_minhngoc_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse minhngoc.net.vn HTML (<table class='bkqtinhmiennam'>) into validated raw draw dicts."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    if not isinstance(html, str) or not html.strip():
        return []
    html = unicodedata.normalize("NFC", html)

    # Split by bkqtinhmiennam table openings to handle nested tables cleanly
    parts = re.split(
        r"(?=<table[^>]*class=[\"'][^\"']*bkqtinhmiennam[^\"']*[\"'][^>]*>)",
        html,
        flags=re.IGNORECASE,
    )
    results: list[dict[str, Any]] = []
    for part in parts:
        if "bkqtinhmiennam" not in part.lower():
            continue
        draw_date = _extract_date_from_fragment(part, fallback_date=fallback_date)
        if draw_date is None:
            continue

        rightcl_blocks = _RIGHTCL_TABLE_RE.findall(part)
        if rightcl_blocks:
            for sub_block in rightcl_blocks:
                if not _matches_station(sub_block, station_code):
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
            if _matches_station(part, station_code):
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
    return deduplicate_and_sort_raw_draws(results, station_code=station_code)


def _parse_labeled_table_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse fallback HTML tables (xskt.com.vn / xoso.com.vn) with row labels G8..ĐB or ĐB..G8."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    if not isinstance(html, str) or not html.strip():
        return []
    html = unicodedata.normalize("NFC", html)

    # First try minhngoc-style class extraction if present
    direct = parse_minhngoc_html(html, station_code=station_code, fallback_date=fallback_date)
    if direct:
        return direct

    results: list[dict[str, Any]] = []
    expected_map = dict(_PRIZE_CLASS_SPECS)
    table_matches = list(_GENERIC_TABLE_RE.finditer(html))

    for idx, table_match in enumerate(table_matches):
        table_html = table_match.group(1)
        prev_end = table_matches[idx - 1].end() if idx > 0 else 0
        context_before = html[prev_end : table_match.start()]

        if _fragment_conflicts_with_station(context_before + " " + table_html, station_code):
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
                draw_date = _extract_date_from_fragment(table_html)
                if draw_date is None:
                    draw_date = _extract_last_date_from_fragment(context_before)
                if draw_date is None and len(table_matches) == 1 and fallback_date is not None:
                    draw_date = _extract_date_from_fragment("", fallback_date=fallback_date)
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
    return deduplicate_and_sort_raw_draws(results, station_code=station_code)


def parse_xskt_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Fallback 1 (xskt.com.vn) HTML into validated 18-prize raw draw dicts."""
    if isinstance(html, str):
        html = unicodedata.normalize("NFC", html)
    return _parse_labeled_table_html(html, station_code=station_code, fallback_date=fallback_date)


def parse_xoso_html(
    html: str,
    station_code: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Fallback 2 (xoso.com.vn) HTML into validated 18-prize raw draw dicts."""
    if isinstance(html, str):
        html = unicodedata.normalize("NFC", html)
    return _parse_labeled_table_html(html, station_code=station_code, fallback_date=fallback_date)


async def _get_html_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = DEFAULT_HTTP_RETRIES,
    backoff_base: float = 0.05,
) -> str | None:
    """Perform an async HTTP GET with bounded retries and exponential backoff."""
    for attempt in range(retries):
        try:
            response = await client.get(url)
            if response.status_code == 200 and response.text:
                return response.text
        except httpx.HTTPError:
            pass
        if attempt + 1 < retries:
            await asyncio.sleep(backoff_base * (2**attempt))
    return None


async def fetch_draw_with_failover(
    client: httpx.AsyncClient,
    station_code: str,
    draw_date: str,
    *,
    retries: int = DEFAULT_HTTP_RETRIES,
    backoff_base: float = 0.05,
) -> dict[str, Any]:
    """Fetch a single draw for station_code on draw_date with automatic 3-tier failover."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    target_date = normalize_draw_date(draw_date)

    providers = (
        ("minhngoc.net.vn", build_minhngoc_url(station_code, target_date), parse_minhngoc_html),
        ("xskt.com.vn", build_xskt_url(station_code, target_date), parse_xskt_html),
        ("xoso.com.vn", build_xoso_url(station_code, target_date), parse_xoso_html),
    )

    for _provider_name, url, parser_fn in providers:
        html = await _get_html_with_retries(client, url, retries=retries, backoff_base=backoff_base)
        if not html:
            continue
        parsed_draws = parser_fn(html, station_code=station_code, fallback_date=target_date)
        for draw in parsed_draws:
            if draw["draw_date"] == target_date and len(draw["prizes_last2"]) == PRIZES_PER_DRAW:
                decompose_cage_counts(draw["prizes_last2"])
                return draw

    raise DataIntegrityError(
        f"All 3 sources (minhngoc, xskt, xoso) failed to provide a valid 18-prize draw "
        f"for {station_code} on {target_date}."
    )


def compute_draws_sha256(raw_draws: Sequence[Mapping[str, Any]]) -> str:
    """Compute a deterministic SHA-256 hex digest over normalized draw dictionaries."""
    if not isinstance(raw_draws, Sequence) or isinstance(raw_draws, (str, bytes)):
        raise DataIntegrityError("raw_draws must be a sequence of draw mappings.")
    canonical_payload: list[dict[str, Any]] = []
    for idx, d in enumerate(raw_draws):
        if not isinstance(d, Mapping):
            raise DataIntegrityError(
                f"Draw entry at index {idx} must be a mapping, got {type(d).__name__}."
            )
        try:
            prizes = d["prizes_last2"]
            if not isinstance(prizes, Sequence) or isinstance(prizes, (str, bytes)):
                raise TypeError("prizes_last2 must be a sequence of strings.")
            canonical_payload.append(
                {
                    "station_code": str(d["station_code"]),
                    "draw_date": str(d["draw_date"]),
                    "prizes_last2": [str(p) for p in prizes],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataIntegrityError(
                f"Malformed draw record at index {idx} in compute_draws_sha256: {exc}"
            ) from exc
    serialized = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def get_raw_cache_path(station_code: str, raw_dir: str | Path = DEFAULT_RAW_DIR) -> Path:
    """Return the path to data/raw/<STATION>_draws.json."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    return Path(raw_dir) / f"{station_code}_draws.json"


def save_raw_cache(
    station_code: str,
    raw_draws: Sequence[Mapping[str, Any]],
    raw_dir: str | Path = DEFAULT_RAW_DIR,
) -> Path:
    """Deduplicate, validate, compute SHA-256, and save raw draws to local cache."""
    cleaned = deduplicate_and_sort_raw_draws(raw_draws, station_code=station_code)
    canonicalize_draws(cleaned, station_code=station_code, require_sorted=True)
    digest = compute_draws_sha256(cleaned)

    cache_path = get_raw_cache_path(station_code, raw_dir=raw_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "station_code": station_code,
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


def load_raw_cache(
    station_code: str,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
) -> list[dict[str, Any]]:
    """Load raw draws from local cache and verify SHA-256 and metadata integrity."""
    cache_path = get_raw_cache_path(station_code, raw_dir=raw_dir)
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
    expected_sha = payload.get("sha256")
    if not isinstance(draws, list) or not draws or not isinstance(expected_sha, str):
        raise DataIntegrityError(f"Missing draws or sha256 in {cache_path}.")

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

    actual_sha = compute_draws_sha256(draws)
    if actual_sha != expected_sha:
        raise DataIntegrityError(
            f"SHA-256 integrity mismatch for {cache_path}: "
            f"expected {expected_sha}, computed {actual_sha}."
        )

    # Validate strict chronological order and non-duplicate dates BEFORE deduplicate_and_sort
    canonicalize_draws(draws, station_code=station_code, require_sorted=True)
    cleaned = deduplicate_and_sort_raw_draws(draws, station_code=station_code)

    if "last_draw_date" in payload:
        last_draw_date = payload.get("last_draw_date")
        if last_draw_date != cleaned[-1]["draw_date"]:
            raise DataIntegrityError(
                f"Cache last_draw_date mismatch in {cache_path}: "
                f"expected {cleaned[-1]['draw_date']!r}, got {last_draw_date!r}."
            )

    return cleaned


def generate_expected_draw_dates(
    station_code: str,
    num_draws: int,
    as_of_date: datetime.date | None = None,
) -> list[str]:
    """Generate expected draw dates (YYYY-MM-DD) backwards from as_of_date by station schedule."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")
    if num_draws <= 0:
        raise DataIntegrityError("num_draws must be positive.")

    cursor = as_of_date or datetime.date.today()
    allowed_weekdays = set(STATION_CONFIG[station_code]["draw_days_of_week"])
    dates: list[str] = []
    while len(dates) < num_draws:
        if cursor.weekday() in allowed_weekdays:
            dates.append(cursor.isoformat())
        cursor -= datetime.timedelta(days=1)
    dates.reverse()
    return dates


async def fetch_station_draws_async(
    station_code: str,
    *,
    years: int = 5,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    as_of_date: datetime.date | None = None,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[CanonicalDrawRecord]:
    """Fetch 5-year history for station_code using local SHA-256 cache + incremental delta sync."""
    if station_code not in VALID_STATIONS:
        raise DataIntegrityError(f"Invalid station_code {station_code!r}.")

    cfg = STATION_CONFIG[station_code]
    horizons_map = cfg["horizons"]
    assert isinstance(horizons_map, Mapping)
    target_draws = (
        int(horizons_map["5y"]) if years == 5 else int(cfg["draws_per_week"]) * 52 * years  # type: ignore[arg-type]
    )
    effective_as_of = as_of_date or datetime.date.today()
    as_of_iso = effective_as_of.isoformat()
    expected_dates = generate_expected_draw_dates(
        station_code, num_draws=target_draws, as_of_date=effective_as_of
    )
    latest_expected_date = expected_dates[-1]

    cache_path = get_raw_cache_path(station_code, raw_dir=raw_dir)
    all_cached_draws: list[dict[str, Any]] = []
    if cache_path.exists():
        all_cached_draws = load_raw_cache(station_code, raw_dir=raw_dir)

    # Strictly filter cached_draws and cached_by_date to <= as_of_iso to prevent future leakage
    cached_draws = [d for d in all_cached_draws if d["draw_date"] <= as_of_iso]
    cached_by_date: dict[str, dict[str, Any]] = {d["draw_date"]: d for d in cached_draws}

    # Fast-path: Cache already satisfies target_draws up to effective_as_of,
    # OR full 5Y cache is present and covers through latest_expected_date in offline historical mode
    if cached_draws and cached_draws[-1]["draw_date"] >= latest_expected_date:
        if len(cached_draws) >= target_draws or (
            as_of_date is not None and transport is None and len(all_cached_draws) >= target_draws
        ):
            return canonicalize_draws(
                cached_draws[-target_draws:], station_code=station_code, require_sorted=True
            )

    # Determine whether we only need incremental delta sync (dates after last_draw_date)
    if cached_draws:
        last_cached_date = cached_draws[-1]["draw_date"]
        delta_dates = [dt for dt in expected_dates if last_cached_date < dt <= as_of_iso]
    else:
        delta_dates = [dt for dt in expected_dates if dt <= as_of_iso]

    semaphore = asyncio.Semaphore(max_concurrency)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        transport=transport,
    ) as client:
        if cached_draws and len(cached_draws) + len(delta_dates) >= target_draws:
            # Incremental Delta Sync: only fetch dates newer than last_cached_date up to as_of_iso
            async def _fetch_single_delta(dt: str) -> dict[str, Any]:
                async with semaphore:
                    return await fetch_draw_with_failover(
                        client=client,
                        station_code=station_code,
                        draw_date=dt,
                        retries=retries,
                    )

            fetched_deltas = await asyncio.gather(*(_fetch_single_delta(dt) for dt in delta_dates))
            for d in fetched_deltas:
                if d["draw_date"] <= as_of_iso:
                    cached_by_date[d["draw_date"]] = d
        else:
            # Batch crawl from minhngoc.net.vn stepping backwards by minhngoc_step_days
            step_days = int(cfg["minhngoc_step_days"])  # type: ignore[arg-type]
            draws_per_page = int(cfg["minhngoc_draws_per_page"])  # type: ignore[arg-type]
            num_pages = (target_draws // draws_per_page) + 2
            anchor_dates = [
                (effective_as_of - datetime.timedelta(days=i * step_days)).isoformat()
                for i in range(num_pages)
            ]

            async def _fetch_batch_page(anchor_iso: str) -> list[dict[str, Any]]:
                async with semaphore:
                    url = build_minhngoc_url(station_code, anchor_iso)
                    html = await _get_html_with_retries(client, url, retries=retries)
                    if not html:
                        return []
                    return parse_minhngoc_html(
                        html, station_code=station_code, fallback_date=anchor_iso
                    )

            batch_lists = await asyncio.gather(*(_fetch_batch_page(dt) for dt in anchor_dates))
            for page_draws in batch_lists:
                for d in page_draws:
                    if d["draw_date"] <= as_of_iso:
                        cached_by_date[d["draw_date"]] = d

            # If historical pauses (e.g. 2021 Covid-19 hiatus) caused fewer than target_draws,
            # step further back in batch rounds from the earliest discovered draw date.
            extra_rounds = 0
            while (
                len(cached_by_date) > 0 and len(cached_by_date) < target_draws and extra_rounds < 4
            ):
                extra_rounds += 1
                earliest_dt = datetime.date.fromisoformat(min(cached_by_date.keys()))
                missing_count = target_draws - len(cached_by_date)
                extra_pages = (missing_count // draws_per_page) + 3
                older_anchors = [
                    (earliest_dt - datetime.timedelta(days=(i + 1) * step_days)).isoformat()
                    for i in range(extra_pages)
                ]
                older_lists = await asyncio.gather(*(_fetch_batch_page(dt) for dt in older_anchors))
                added_in_round = 0
                for page_draws in older_lists:
                    for d in page_draws:
                        if d["draw_date"] <= as_of_iso and d["draw_date"] not in cached_by_date:
                            cached_by_date[d["draw_date"]] = d
                            added_in_round += 1
                if added_in_round == 0:
                    break

            # If still fewer than target_draws, failover on missing expected_dates <= as_of_iso
            if len(cached_by_date) < target_draws:
                missing_dates = [
                    dt for dt in expected_dates if dt <= as_of_iso and dt not in cached_by_date
                ][: target_draws - len(cached_by_date)]

                async def _fetch_missing(dt: str) -> dict[str, Any]:
                    async with semaphore:
                        return await fetch_draw_with_failover(
                            client=client,
                            station_code=station_code,
                            draw_date=dt,
                            retries=retries,
                        )

                recovered = await asyncio.gather(*(_fetch_missing(dt) for dt in missing_dates))
                for d in recovered:
                    if d["draw_date"] <= as_of_iso:
                        cached_by_date[d["draw_date"]] = d

    eligible_raw = [d for d in cached_by_date.values() if d["draw_date"] <= as_of_iso]
    if not eligible_raw:
        raise DataIntegrityError(
            f"Fetched 0 valid draws for {station_code} as of {as_of_iso}, "
            f"require at least {target_draws}."
        )
    merged_raw = deduplicate_and_sort_raw_draws(eligible_raw, station_code=station_code)
    if len(merged_raw) < target_draws:
        raise DataIntegrityError(
            f"Fetched only {len(merged_raw)} valid draws for {station_code}, "
            f"require at least {target_draws}."
        )

    all_to_save = deduplicate_and_sort_raw_draws(
        [*all_cached_draws, *merged_raw], station_code=station_code
    )
    save_raw_cache(station_code=station_code, raw_draws=all_to_save, raw_dir=raw_dir)
    selected = [d for d in merged_raw if d["draw_date"] <= as_of_iso][-target_draws:]
    return canonicalize_draws(selected, station_code=station_code, require_sorted=True)


def fetch_station_draws(
    station_code: str,
    *,
    years: int = 5,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    as_of_date: datetime.date | None = None,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[CanonicalDrawRecord]:
    """Synchronous entry point for fetching and caching 5-year station draw history."""
    return asyncio.run(
        fetch_station_draws_async(
            station_code=station_code,
            years=years,
            raw_dir=raw_dir,
            as_of_date=as_of_date,
            max_concurrency=max_concurrency,
            timeout=timeout,
            retries=retries,
            transport=transport,
        )
    )
