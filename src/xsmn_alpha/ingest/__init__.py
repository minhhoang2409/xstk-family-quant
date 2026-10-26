"""Pillar 1A: Automated Multi-Source Ingestion and Canonical 5Y/3Y Data Preparation."""

from __future__ import annotations

from xsmn_alpha.ingest.canonicalizer import (
    canonicalize_draws,
    decompose_cage_counts,
    deduplicate_and_sort_raw_draws,
    extract_last2_from_prize_token,
    load_canonical_draws,
    normalize_draw_date,
    save_canonical_draws,
    slice_horizon,
)
from xsmn_alpha.ingest.fetcher import (
    build_minhngoc_url,
    build_xoso_url,
    build_xskt_url,
    compute_draws_sha256,
    fetch_draw_with_failover,
    fetch_station_draws,
    fetch_station_draws_async,
    format_date_dmy,
    generate_expected_draw_dates,
    get_raw_cache_path,
    load_raw_cache,
    parse_minhngoc_html,
    parse_xoso_html,
    parse_xskt_html,
    save_raw_cache,
)

__all__ = [
    "build_minhngoc_url",
    "build_xoso_url",
    "build_xskt_url",
    "canonicalize_draws",
    "compute_draws_sha256",
    "decompose_cage_counts",
    "deduplicate_and_sort_raw_draws",
    "extract_last2_from_prize_token",
    "fetch_draw_with_failover",
    "fetch_station_draws",
    "fetch_station_draws_async",
    "format_date_dmy",
    "generate_expected_draw_dates",
    "get_raw_cache_path",
    "load_canonical_draws",
    "load_raw_cache",
    "normalize_draw_date",
    "parse_minhngoc_html",
    "parse_xoso_html",
    "parse_xskt_html",
    "save_canonical_draws",
    "save_raw_cache",
    "slice_horizon",
]
