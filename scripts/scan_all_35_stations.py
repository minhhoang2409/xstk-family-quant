"""Multi-Station Alpha Radar: Crawl & Evaluate All 35 Stations (21 Miền Nam + 14 Miền Trung).

Fetches 3-year historical 18-prize draws (312 draws for 2-draw/week stations, 156 draws for
1-draw/week stations) from minhngoc.net.vn, runs Pillar 2 Statistical Falsification Gatekeeper
(against 1,000 Monte Carlo Nulls) + Pillar 3 Causal Calibrated Engine (W*_{t-1} + Lag-1 Filter
+ BOCD + Markov-Gap) + Pillar 4 Walk-Forward Backtest (2x2, 1x4, 3x3), and generates an
interactive HTML Radar Report ranking all 35 stations.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from xsmn_alpha.backtest.alpha_decay import (
    compute_rank_ordered_alpha_decay,
    rank_balls_from_probabilities,
)
from xsmn_alpha.backtest.sweet_spot_sim import (
    evaluate_all_sweet_spot_portfolios,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import (
    BE_PROB_SINGLE_BALL,
    PRIZES_PER_DRAW,
)
from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler
from xsmn_alpha.falsification.monte_carlo import simulate_monte_carlo_null
from xsmn_alpha.falsification.stats_tests import run_multi_window_tests
from xsmn_alpha.ingest.canonicalizer import (
    decompose_cage_counts,
    extract_last2_from_prize_token,
    normalize_draw_date,
)
from xsmn_alpha.schemas import CanonicalDrawRecord

ALL_35_STATIONS: tuple[dict[str, Any], ...] = (
    # --- 21 ĐÀI MIỀN NAM (XSMN) ---
    {
        "code": "XSHCM",
        "name": "TP. Hồ Chí Minh",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "tp-hcm",
        "keywords": ("tp-hcm", "tp. hcm", "tp.hcm", "hồ chí minh", "ho chi minh"),
        "draws_per_week": 2,
        "days_label": "Thứ 2, Thứ 7",
        "target_3y": 312,
    },
    {
        "code": "XSDT",
        "name": "Đồng Tháp",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "dong-thap",
        "keywords": ("đồng tháp", "dong thap", "dong-thap"),
        "draws_per_week": 1,
        "days_label": "Thứ 2",
        "target_3y": 156,
    },
    {
        "code": "XSCM",
        "name": "Cà Mau",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "ca-mau",
        "keywords": ("cà mau", "ca mau", "ca-mau"),
        "draws_per_week": 1,
        "days_label": "Thứ 2",
        "target_3y": 156,
    },
    {
        "code": "XSBT",
        "name": "Bến Tre",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "ben-tre",
        "keywords": ("bến tre", "ben tre", "ben-tre"),
        "draws_per_week": 1,
        "days_label": "Thứ 3",
        "target_3y": 156,
    },
    {
        "code": "XSVT",
        "name": "Vũng Tàu",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "vung-tau",
        "keywords": ("vũng tàu", "vung tau", "vung-tau"),
        "draws_per_week": 1,
        "days_label": "Thứ 3",
        "target_3y": 156,
    },
    {
        "code": "XSBL",
        "name": "Bạc Liêu",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "bac-lieu",
        "keywords": ("bạc liêu", "bac lieu", "bac-lieu"),
        "draws_per_week": 1,
        "days_label": "Thứ 3",
        "target_3y": 156,
    },
    {
        "code": "XSDN",
        "name": "Đồng Nai",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "dong-nai",
        "keywords": ("đồng nai", "dong nai", "dong-nai"),
        "draws_per_week": 1,
        "days_label": "Thứ 4",
        "target_3y": 156,
    },
    {
        "code": "XSCT",
        "name": "Cần Thơ",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "can-tho",
        "keywords": ("cần thơ", "can tho", "can-tho"),
        "draws_per_week": 1,
        "days_label": "Thứ 4",
        "target_3y": 156,
    },
    {
        "code": "XSST",
        "name": "Sóc Trăng",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "soc-trang",
        "keywords": ("sóc trăng", "soc trang", "soc-trang"),
        "draws_per_week": 1,
        "days_label": "Thứ 4",
        "target_3y": 156,
    },
    {
        "code": "XSTN",
        "name": "Tây Ninh",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "tay-ninh",
        "keywords": ("tây ninh", "tay ninh", "tay-ninh"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSAG",
        "name": "An Giang",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "an-giang",
        "keywords": ("an giang", "an-giang"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSBTH",
        "name": "Bình Thuận",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "binh-thuan",
        "keywords": ("bình thuận", "binh thuan", "binh-thuan"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSVL",
        "name": "Vĩnh Long",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "vinh-long",
        "keywords": ("vĩnh long", "vinh long", "vinh-long"),
        "draws_per_week": 1,
        "days_label": "Thứ 6",
        "target_3y": 156,
    },
    {
        "code": "XSBD",
        "name": "Bình Dương",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "binh-duong",
        "keywords": ("bình dương", "binh duong", "binh-duong"),
        "draws_per_week": 1,
        "days_label": "Thứ 6",
        "target_3y": 156,
    },
    {
        "code": "XSTV",
        "name": "Trà Vinh",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "tra-vinh",
        "keywords": ("trà vinh", "tra vinh", "tra-vinh"),
        "draws_per_week": 1,
        "days_label": "Thứ 6",
        "target_3y": 156,
    },
    {
        "code": "XSLA",
        "name": "Long An",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "long-an",
        "keywords": ("long an", "long-an"),
        "draws_per_week": 1,
        "days_label": "Thứ 7",
        "target_3y": 156,
    },
    {
        "code": "XSBP",
        "name": "Bình Phước",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "binh-phuoc",
        "keywords": ("bình phước", "binh phuoc", "binh-phuoc"),
        "draws_per_week": 1,
        "days_label": "Thứ 7",
        "target_3y": 156,
    },
    {
        "code": "XSHG",
        "name": "Hậu Giang",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "hau-giang",
        "keywords": ("hậu giang", "hau giang", "hau-giang"),
        "draws_per_week": 1,
        "days_label": "Thứ 7",
        "target_3y": 156,
    },
    {
        "code": "XSTG",
        "name": "Tiền Giang",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "tien-giang",
        "keywords": ("tiền giang", "tien giang", "tien-giang"),
        "draws_per_week": 1,
        "days_label": "Chủ Nhật",
        "target_3y": 156,
    },
    {
        "code": "XSKG",
        "name": "Kiên Giang",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "kien-giang",
        "keywords": ("kiên giang", "kien giang", "kien-giang"),
        "draws_per_week": 1,
        "days_label": "Chủ Nhật",
        "target_3y": 156,
    },
    {
        "code": "XSDL",
        "name": "Đà Lạt (Lâm Đồng)",
        "region": "Miền Nam",
        "region_slug": "mien-nam",
        "slug": "da-lat",
        "keywords": ("đà lạt", "da lat", "da-lat", "lâm đồng"),
        "draws_per_week": 1,
        "days_label": "Chủ Nhật",
        "target_3y": 156,
    },
    # --- 14 ĐÀI MIỀN TRUNG (XSMT) ---
    {
        "code": "XSTTH",
        "name": "Thừa Thiên Huế",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "thua-thien-hue",
        "keywords": ("thừa thiên huế", "thua thien hue", "thua-thien-hue", "huế"),
        "draws_per_week": 2,
        "days_label": "Thứ 2, Chủ Nhật",
        "target_3y": 312,
    },
    {
        "code": "XSPY",
        "name": "Phú Yên",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "phu-yen",
        "keywords": ("phú yên", "phu yen", "phu-yen"),
        "draws_per_week": 1,
        "days_label": "Thứ 2",
        "target_3y": 156,
    },
    {
        "code": "XSDLK",
        "name": "Đắk Lắk",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "dak-lak",
        "keywords": ("đắk lắk", "dak lak", "dak-lak", "đắc lắc"),
        "draws_per_week": 1,
        "days_label": "Thứ 3",
        "target_3y": 156,
    },
    {
        "code": "XSQNM",
        "name": "Quảng Nam",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "quang-nam",
        "keywords": ("quảng nam", "quang nam", "quang-nam"),
        "draws_per_week": 1,
        "days_label": "Thứ 3",
        "target_3y": 156,
    },
    {
        "code": "XSDNG",
        "name": "Đà Nẵng",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "da-nang",
        "keywords": ("đà nẵng", "da nang", "da-nang"),
        "draws_per_week": 2,
        "days_label": "Thứ 4, Thứ 7",
        "target_3y": 312,
    },
    {
        "code": "XSKH",
        "name": "Khánh Hòa",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "khanh-hoa",
        "keywords": ("khánh hòa", "khanh hoa", "khanh-hoa"),
        "draws_per_week": 2,
        "days_label": "Thứ 4, Chủ Nhật",
        "target_3y": 312,
    },
    {
        "code": "XSBDI",
        "name": "Bình Định",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "binh-dinh",
        "keywords": ("bình định", "binh dinh", "binh-dinh"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSQT",
        "name": "Quảng Trị",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "quang-tri",
        "keywords": ("quảng trị", "quang tri", "quang-tri"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSQB",
        "name": "Quảng Bình",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "quang-binh",
        "keywords": ("quảng bình", "quang binh", "quang-binh"),
        "draws_per_week": 1,
        "days_label": "Thứ 5",
        "target_3y": 156,
    },
    {
        "code": "XSGL",
        "name": "Gia Lai",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "gia-lai",
        "keywords": ("gia lai", "gia-lai"),
        "draws_per_week": 1,
        "days_label": "Thứ 6",
        "target_3y": 156,
    },
    {
        "code": "XSNT",
        "name": "Ninh Thuận",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "ninh-thuan",
        "keywords": ("ninh thuận", "ninh thuan", "ninh-thuan"),
        "draws_per_week": 1,
        "days_label": "Thứ 6",
        "target_3y": 156,
    },
    {
        "code": "XSQNG",
        "name": "Quảng Ngãi",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "quang-ngai",
        "keywords": ("quảng ngãi", "quang ngai", "quang-ngai"),
        "draws_per_week": 1,
        "days_label": "Thứ 7",
        "target_3y": 156,
    },
    {
        "code": "XSDNO",
        "name": "Đắk Nông",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "dak-nong",
        "keywords": ("đắk nông", "dak nong", "dak-nong", "đắc nông"),
        "draws_per_week": 1,
        "days_label": "Thứ 7",
        "target_3y": 156,
    },
    {
        "code": "XSKT",
        "name": "Kon Tum",
        "region": "Miền Trung",
        "region_slug": "mien-trung",
        "slug": "kon-tum",
        "keywords": ("kon tum", "kon-tum"),
        "draws_per_week": 1,
        "days_label": "Chủ Nhật",
        "target_3y": 156,
    },
)

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
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_IN_TEXT_RE = re.compile(
    r"\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})\b"
)


def _extract_last2_tokens(fragment: str, expected_count: int) -> list[str] | None:
    text = _TAG_RE.sub(" ", fragment).replace("&nbsp;", " ").replace("|", " ")
    text = re.sub(r"\s+-\s+", " ", text)
    tokens = [tok.strip() for tok in text.split() if tok.strip()]
    if len(tokens) != expected_count:
        return None
    out: list[str] = []
    for tok in tokens:
        try:
            out.append(extract_last2_from_prize_token(tok))
        except Exception:
            return None
    return out


def _extract_9_classes(block_html: str) -> list[str] | None:
    prizes: list[str] = []
    for cls_name, expected_count in _PRIZE_CLASS_SPECS:
        td_pat = re.compile(
            rf"<td[^>]*class=[\"'][^\"']*\b{cls_name}\b[^\"']*[\"'][^>]*>(.*?)</td>",
            re.IGNORECASE | re.DOTALL,
        )
        matches = td_pat.findall(block_html)
        if len(matches) != 1:
            return None
        extracted = _extract_last2_tokens(matches[0], expected_count)
        if extracted is None:
            return None
        prizes.extend(extracted)
    return prizes if len(prizes) == PRIZES_PER_DRAW else None


def _parse_single_station_minhngoc_page(html: str) -> list[dict[str, Any]]:
    html = unicodedata.normalize("NFC", html)
    parts = re.split(
        r"(?=<table[^>]*class=[\"'][^\"']*bkqtinhmiennam[^\"']*[\"'][^>]*>)",
        html,
        flags=re.IGNORECASE,
    )
    draws: list[dict[str, Any]] = []
    for part in parts:
        if "bkqtinhmiennam" not in part.lower():
            continue
        dt_str: str | None = None
        for m in _DATE_IN_TEXT_RE.finditer(_TAG_RE.sub(" ", part)):
            try:
                dt_str = normalize_draw_date(m.group(1))
                break
            except Exception:
                continue
        if dt_str is None:
            continue
        prizes = _extract_9_classes(part)
        if prizes is not None:
            draws.append({"draw_date": dt_str, "prizes_last2": prizes})
    return draws


async def fetch_station_3y_draws(
    st_meta: dict[str, Any],
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    raw_dir: Path,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    code = st_meta["code"]
    target_n = int(st_meta["target_3y"])

    # 1. Check existing cache in data/raw/ or data/raw_all/ unless force_refresh is True
    if not force_refresh:
        for candidate_path in (
            Path("data/raw") / f"{code}_draws.json",
            raw_dir / f"{code}_draws.json",
        ):
            if candidate_path.exists():
                try:
                    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
                    cached_list = payload.get("draws", [])
                    if len(cached_list) >= target_n:
                        return cached_list[-target_n:]
                except Exception:
                    pass

    region_slug = st_meta["region_slug"]
    slug = st_meta["slug"]
    draws_per_week = int(st_meta["draws_per_week"])
    step_days = 21 if draws_per_week == 2 else 42
    num_pages = (target_n // 5) + 4
    anchor_base = datetime.date(2026, 10, 25)

    by_date: dict[str, dict[str, Any]] = {}

    async def _fetch_page(anchor_dt: datetime.date) -> list[dict[str, Any]]:
        dmy = anchor_dt.strftime("%d-%m-%Y")
        url = f"https://www.minhngoc.net.vn/ket-qua-xo-so/{region_slug}/{slug}/{dmy}.html"
        async with sem:
            for attempt in range(3):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200 and "bkqtinhmiennam" in resp.text:
                        return _parse_single_station_minhngoc_page(resp.text)
                except Exception:
                    await asyncio.sleep(0.3 * (attempt + 1))
        return []

    anchors = [anchor_base - datetime.timedelta(days=i * step_days) for i in range(num_pages)]
    pages = await asyncio.gather(*(_fetch_page(dt) for dt in anchors))
    for page_draws in pages:
        for d in page_draws:
            by_date[d["draw_date"]] = d

    extra_round = 0
    while len(by_date) > 0 and len(by_date) < target_n and extra_round < 3:
        extra_round += 1
        earliest = datetime.date.fromisoformat(min(by_date.keys()))
        needed = target_n - len(by_date)
        more_pages = (needed // 5) + 3
        older_anchors = [
            earliest - datetime.timedelta(days=(i + 1) * step_days) for i in range(more_pages)
        ]
        older_pages = await asyncio.gather(*(_fetch_page(dt) for dt in older_anchors))
        added = 0
        for page_draws in older_pages:
            for d in page_draws:
                if d["draw_date"] not in by_date:
                    by_date[d["draw_date"]] = d
                    added += 1
        if added == 0:
            break

    sorted_draws = [by_date[k] for k in sorted(by_date.keys())]
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_file = raw_dir / f"{code}_draws.json"
    out_file.write_text(
        json.dumps(
            {
                "station_code": code,
                "station_name": st_meta["name"],
                "region": st_meta["region"],
                "draw_count": len(sorted_draws),
                "last_draw_date": sorted_draws[-1]["draw_date"] if sorted_draws else "",
                "draws": sorted_draws,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return sorted_draws[-target_n:]


def _build_canonical_records_for_station(
    raw_draws: list[dict[str, Any]],
) -> list[CanonicalDrawRecord]:
    records: list[CanonicalDrawRecord] = []
    for idx, d in enumerate(raw_draws):
        prizes = d["prizes_last2"]
        t_counts, u_counts = decompose_cage_counts(prizes)
        records.append(
            CanonicalDrawRecord(
                station_code="XSHCM",  # Schema proxy for any 18-prize station
                draw_date=d["draw_date"],
                draw_index=idx,
                prizes_last2=prizes,
                tens_counts=t_counts,
                units_counts=u_counts,
            )
        )
    return records


def evaluate_single_station_3y(
    st_meta: dict[str, Any],
    raw_draws: list[dict[str, Any]],
    null_thresholds_cache: dict[int, Any],
) -> dict[str, Any]:
    records = _build_canonical_records_for_station(raw_draws)
    n_draws = len(records)
    if n_draws not in null_thresholds_cache:
        null_thresholds_cache[n_draws] = simulate_monte_carlo_null(
            sample_size_draws=n_draws,
            null_sims=1000,
            seed=42,
        )
    null_res = null_thresholds_cache[n_draws]

    tens_mat = np.array([r.tens_counts for r in records], dtype=np.int64)
    units_mat = np.array([r.units_counts for r in records], dtype=np.int64)

    pooler = CalibratedProbabilityPooler()
    tens_wf_preds = pooler.walk_forward_cage_predictions(
        records, warmup_draws=45, cage_name="tens_cage"
    )
    units_wf_preds = pooler.walk_forward_cage_predictions(
        records, warmup_draws=45, cage_name="units_cage"
    )
    eval_draws = records[45:]

    tens_decay = compute_rank_ordered_alpha_decay(
        tens_wf_preds, eval_draws, cage_name="tens_cage"
    )
    units_decay = compute_rank_ordered_alpha_decay(
        units_wf_preds, eval_draws, cage_name="units_cage"
    )

    latest_tens = pooler.predict_cage(
        tens_mat,
        cage_name="tens_cage",
        target_draw_index=n_draws,
        target_draw_date=records[-1].draw_date,
    )
    latest_units = pooler.predict_cage(
        units_mat,
        cage_name="units_cage",
        target_draw_index=n_draws,
        target_draw_date=records[-1].draw_date,
    )

    # Multi-window statistical tests on last 15, 30, 60 draws
    t_win = run_multi_window_tests(tens_mat)
    u_win = run_multi_window_tests(units_mat)
    t_chi2_max = max(r.chi2_stat for r in t_win)
    u_chi2_max = max(r.chi2_stat for r in u_win)
    t_bf10_max = max(r.bf10 for r in t_win)
    u_bf10_max = max(r.bf10 for r in u_win)

    # Also compute rolling historical peak chi2_30 across the 3-year series
    csum_t = np.vstack([np.zeros((1, 10)), np.cumsum(tens_mat, axis=0)])
    csum_u = np.vstack([np.zeros((1, 10)), np.cumsum(units_mat, axis=0)])
    win30_t = csum_t[30:] - csum_t[:-30]
    win30_u = csum_u[30:] - csum_u[:-30]
    hist_chi2_30_t = float(np.max(np.sum((win30_t - 54.0) ** 2 / 54.0, axis=1)))
    hist_chi2_30_u = float(np.max(np.sum((win30_u - 54.0) ** 2 / 54.0, axis=1)))

    # Determine status using both current window chi2 and out-of-sample Rank-1 persistence
    t_r1 = float(tens_decay[0])
    t_r2 = float(tens_decay[1])
    u_r1 = float(units_decay[0])
    u_r2 = float(units_decay[1])

    portfolios = evaluate_all_sweet_spot_portfolios(
        tens_wf_preds, units_wf_preds, eval_draws
    )
    m2x2 = portfolios["2x2"]
    m1x4 = portfolios["1x4"]
    m3x3 = portfolios["3x3"]
    m_hyb = portfolios["core_2x2_sat_3x3"]

    best_roi = max(m2x2.roi_pct, m1x4.roi_pct)
    best_cfg = "2x2" if m2x2.roi_pct >= m1x4.roi_pct else "1x4"

    # Classify station physical anomaly tier & long-run exploitability
    max_chi2_now = max(t_chi2_max, u_chi2_max)
    max_bf10_now = max(t_bf10_max, u_bf10_max)
    if (
        best_roi >= 5.0
        and max(t_r1, u_r1) >= BE_PROB_SINGLE_BALL
        and (max_chi2_now >= null_res.p90 or max(hist_chi2_30_t, hist_chi2_30_u) >= 20.0)
    ):
        tier = "PASS_ALPHA"
        cap_mult = 1.0 if best_roi >= 8.0 else 0.5
    elif (
        best_roi > 0.0
        or max_chi2_now >= null_res.p90
        or max_bf10_now >= 1.5
    ):
        tier = "WARN_WEAK_SIGNAL"
        cap_mult = 0.25 if best_roi > 0.0 else 0.0
    else:
        tier = "FAIL_WHITE_NOISE_CASH_BRAKE"
        cap_mult = 0.0

    next_2x2 = select_sweet_spot_numbers(latest_tens.p_ai, latest_units.p_ai, "2x2")
    next_1x4 = select_sweet_spot_numbers(latest_tens.p_ai, latest_units.p_ai, "1x4")

    return {
        "code": st_meta["code"],
        "name": st_meta["name"],
        "region": st_meta["region"],
        "days_label": st_meta["days_label"],
        "draws_per_week": st_meta["draws_per_week"],
        "sample_draws": n_draws,
        "evaluated_draws": len(eval_draws),
        "last_draw_date": records[-1].draw_date,
        "tier": tier,
        "recommended_capital_multiplier": cap_mult,
        "best_config": best_cfg,
        "best_roi_pct": round(best_roi, 2),
        "tens_chi2_max": round(t_chi2_max, 2),
        "units_chi2_max": round(u_chi2_max, 2),
        "null_p90": round(null_res.p90, 2),
        "null_p95": round(null_res.p95, 2),
        "tens_bf10_max": round(t_bf10_max, 3),
        "units_bf10_max": round(u_bf10_max, 3),
        "hist_peak_chi2_30_tens": round(hist_chi2_30_t, 2),
        "hist_peak_chi2_30_units": round(hist_chi2_30_u, 2),
        "tens_oos_rank1_freq_pct": round(t_r1 * 100.0, 2),
        "tens_oos_rank2_freq_pct": round(t_r2 * 100.0, 2),
        "units_oos_rank1_freq_pct": round(u_r1 * 100.0, 2),
        "units_oos_rank2_freq_pct": round(u_r2 * 100.0, 2),
        "roi_2x2_pct": round(m2x2.roi_pct, 2),
        "net_profit_2x2": round(m2x2.net_profit, 2),
        "hits_30d_2x2": round(m2x2.hits_per_30_draws, 2),
        "win_rate_2x2_pct": round(m2x2.daily_win_rate * 100.0, 2),
        "roi_1x4_pct": round(m1x4.roi_pct, 2),
        "net_profit_1x4": round(m1x4.net_profit, 2),
        "hits_30d_1x4": round(m1x4.hits_per_30_draws, 2),
        "roi_3x3_pct": round(m3x3.roi_pct, 2),
        "roi_hybrid_pct": round(m_hyb.roi_pct, 2),
        "tens_top3_balls": latest_tens.ranked_balls[:3],
        "units_top4_balls": latest_units.ranked_balls[:4],
        "next_draw_2x2_numbers": next_2x2,
        "next_draw_1x4_numbers": next_1x4,
    }


def generate_html_radar_report(results: list[dict[str, Any]], out_path: Path) -> None:
    pass_count = sum(1 for r in results if r["tier"] == "PASS_ALPHA")
    warn_count = sum(1 for r in results if r["tier"] == "WARN_WEAK_SIGNAL")
    brake_count = sum(1 for r in results if r["tier"] == "FAIL_WHITE_NOISE_CASH_BRAKE")
    pos_roi_count = sum(1 for r in results if r["best_roi_pct"] > 0.0)

    rows_html = []
    for rank_idx, r in enumerate(results, 1):
        if r["tier"] == "PASS_ALPHA":
            badge = '<span class="badge pass">🟢 PASS_ALPHA (Đánh chuẩn)</span>'
            row_cls = "row-pass"
        elif r["tier"] == "WARN_WEAK_SIGNAL":
            badge = '<span class="badge warn">🟡 WARN_SIGNAL (Thăm dò 0.25x)</span>'
            row_cls = "row-warn"
        else:
            badge = '<span class="badge fail">🔴 CASH_BRAKE (Đứng ngoài 0x)</span>'
            row_cls = ""

        r2x2_cls = "pos" if r["roi_2x2_pct"] > 0 else "neg"
        r1x4_cls = "pos" if r["roi_1x4_pct"] > 0 else "neg"
        t_r1_cls = "pos" if r["tens_oos_rank1_freq_pct"] >= 10.69 else ""
        u_r1_cls = "pos" if r["units_oos_rank1_freq_pct"] >= 10.69 else ""

        nums_2x2 = ", ".join(f"<b>{n}</b>" for n in r["next_draw_2x2_numbers"])
        nums_1x4 = ", ".join(f"<b>{n}</b>" for n in r["next_draw_1x4_numbers"])

        rows_html.append(
            f"""
        <tr class="{row_cls}">
          <td>{rank_idx}</td>
          <td class="left"><b>{r['name']}</b> <small>({r['code']})</small></td>
          <td>{r['region']}</td>
          <td>{r['days_label']}<br><small>({r['sample_draws']} kỳ)</small></td>
          <td>{badge}</td>
          <td><b>{r['tens_chi2_max']:.2f}</b> / <b>{r['units_chi2_max']:.2f}</b><br><small>P95={r['null_p95']:.1f} | Đỉnh 3Y: {r['hist_peak_chi2_30_tens']:.1f}/{r['hist_peak_chi2_30_units']:.1f}</small></td>
          <td class="{t_r1_cls}"><b>{r['tens_oos_rank1_freq_pct']:.2f}%</b><br><small>(Hạng 2: {r['tens_oos_rank2_freq_pct']:.2f}%)</small></td>
          <td class="{u_r1_cls}"><b>{r['units_oos_rank1_freq_pct']:.2f}%</b><br><small>(Hạng 2: {r['units_oos_rank2_freq_pct']:.2f}%)</small></td>
          <td class="{r2x2_cls}"><b>{r['roi_2x2_pct']:+.2f}%</b><br><small>({r['net_profit_2x2']:+.1f}đ | {r['hits_30d_2x2']:.1f} lô/30kỳ)</small></td>
          <td class="{r1x4_cls}"><b>{r['roi_1x4_pct']:+.2f}%</b><br><small>({r['net_profit_1x4']:+.1f}đ | {r['hits_30d_1x4']:.1f} lô/30kỳ)</small></td>
          <td class="left">
            <small>Đầu: {r['tens_top3_balls']} | Đuôi: {r['units_top4_balls']}</small><br>
            2x2: {nums_2x2}<br>
            1x4: {nums_1x4}
          </td>
        </tr>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>Bảng Radar Tầm Soát 35 Đài Xổ Số Miền Nam (21 Đài) & Miền Trung (14 Đài)</title>
  <style>
    body {{
      margin: 0; padding: 24px;
      font-family: "Segoe UI", Roboto, Arial, sans-serif;
      background: #0f172a; color: #f1f5f9;
      line-height: 1.5;
    }}
    .container {{ max-width: 1480px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px; font-size: 1.75rem; color: #fff; }}
    .sub {{ color: #94a3b8; margin-bottom: 20px; }}
    .kpi-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px;
    }}
    .kpi {{
      background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px 18px;
    }}
    .kpi .val {{ font-size: 1.65rem; font-weight: 800; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; background: #1e293b; }}
    th, td {{ border: 1px solid #334155; padding: 8px 9px; text-align: center; }}
    th {{ background: #0b1324; color: #cbd5e1; position: sticky; top: 0; }}
    td.left, th.left {{ text-align: left; }}
    tr.row-pass {{ background: rgba(34, 197, 94, 0.13); }}
    tr.row-warn {{ background: rgba(245, 158, 11, 0.08); }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-weight: 700; font-size: 0.76rem; }}
    .badge.pass {{ background: rgba(34, 197, 94, 0.25); color: #4ade80; border: 1px solid #22c55e; }}
    .badge.warn {{ background: rgba(245, 158, 11, 0.22); color: #fbbf24; border: 1px solid #f59e0b; }}
    .badge.fail {{ background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid #ef4444; }}
    .pos {{ color: #4ade80; font-weight: 700; }}
    .neg {{ color: #f87171; }}
  </style>
</head>
<body>
<div class="container">
  <h1>📡 Bảng Radar Tầm Soát 35 Đài Xổ Số Miền Nam (21 Đài) &amp; Miền Trung (14 Đài) — Khung 3 Năm Hiện Hành</h1>
  <div class="sub">
    Kiểm định thực nghiệm cuốn chiếu (Walk-Forward Backtest) trên toàn bộ 35 đài có cùng cơ cấu 18 giải/kỳ và lồng cầu 0–9. Sắp xếp từ Đài có Độ Lệch Vật Lý &amp; Lợi Nhuận Thực Nghiệm cao nhất xuống thấp nhất. (Ngưỡng hòa vốn bóng đơn: <b>10.69%</b> | Ngưỡng hòa vốn Bộ 4 số: <b>24.69 lô / 30 kỳ</b>).
  </div>
  <div class="kpi-grid">
    <div class="kpi">
      <div>Tổng số đài đã quét (XSMN + XSMT)</div>
      <div class="val" style="color:#38bdf8;">{len(results)} Đài</div>
    </div>
    <div class="kpi">
      <div>🟢 Đạt chuẩn PASS_ALPHA (Lệch Mạnh)</div>
      <div class="val" style="color:#4ade80;">{pass_count} Đài</div>
    </div>
    <div class="kpi">
      <div>🟡 Tín hiệu WARN_WEAK_SIGNAL (Có Lợi Thế)</div>
      <div class="val" style="color:#fbbf24;">{warn_count} Đài</div>
    </div>
    <div class="kpi">
      <div>💰 Số đài đạt ROI Dương (Bộ 2x2 hoặc 1x4)</div>
      <div class="val" style="color:#c084fc;">{pos_roi_count} / {len(results)} Đài</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Hạng</th>
        <th class="left">Tên Đài (Mã)</th>
        <th>Miền</th>
        <th>Lịch Quay</th>
        <th>Phán Quyết Gatekeeper</th>
        <th>Độ Lệch χ² Hiện Tại<br><small>(Chục / Đơn Vị)</small></th>
        <th>OOS Hạng 1 Lồng Chục<br><small>(Mốc BE: 10.69%)</small></th>
        <th>OOS Hạng 1 Lồng Đơn Vị<br><small>(Mốc BE: 10.69%)</small></th>
        <th>Lợi Nhuận Bộ `2x2` (4 số)<br><small>(ROI % | Lãi | Lô/30kỳ)</small></th>
        <th>Lợi Nhuận Bộ `1x4` (4 số)<br><small>(ROI % | Lãi | Lô/30kỳ)</small></th>
        <th class="left">Bộ Số Dự Báo Kỳ Tới<br><small>(Từ Dữ Liệu Mới Nhất)</small></th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</div>
</body>
</html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


async def main_async() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description="Quét và kiểm định thực nghiệm 35 đài XSMN (21 đài) & XSMT (14 đài)."
    )
    parser.add_argument(
        "--station",
        nargs="*",
        help="Mã đài cần chạy riêng (ví dụ: --station XSBP XSVL XSQB). Bỏ trống để chạy đủ 35 đài.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Tải lại dữ liệu mới nhất trực tiếp từ minhngoc.net.vn (bỏ qua cache).",
    )
    args = parser.parse_args()

    selected_stations = list(ALL_35_STATIONS)
    if args.station:
        wanted = {s.upper().strip() for s in args.station}
        selected_stations = [st for st in ALL_35_STATIONS if st["code"] in wanted]
        if not selected_stations:
            valid_codes = ", ".join(st["code"] for st in ALL_35_STATIONS)
            print(f"[LỖI] Không tìm thấy mã đài {wanted}. Các mã hợp lệ: {valid_codes}")
            sys.exit(1)

    t0 = time.perf_counter()
    raw_dir = Path("data/raw_all")
    sem = asyncio.Semaphore(16)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    print(
        f"[1/2] Đang chuẩn bị lịch sử 3 năm cho {len(selected_stations)} đài "
        f"(refresh={args.refresh})..."
    )
    async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
        tasks = [
            fetch_station_3y_draws(st, client, sem, raw_dir, force_refresh=args.refresh)
            for st in selected_stations
        ]
        all_raw_lists = await asyncio.gather(*tasks)

    t_fetch = time.perf_counter() - t0
    print(
        f"  -> Hoàn tất dữ liệu trong {t_fetch:.1f}s. "
        f"Bắt đầu chạy kiểm định & Walk-Forward Backtest..."
    )

    null_cache: dict[int, Any] = {}
    results: list[dict[str, Any]] = []
    for st_meta, raw_draws in zip(selected_stations, all_raw_lists, strict=True):
        if len(raw_draws) < 60:
            print(f"  [WARN] Đài {st_meta['code']} chỉ có {len(raw_draws)} kỳ, bỏ qua.")
            continue
        res = evaluate_single_station_3y(st_meta, raw_draws, null_cache)
        results.append(res)
        print(
            f"  [{res['code']:6s} - {res['name']:18s}] {res['tier']:27s} | "
            f"Chục R1={res['tens_oos_rank1_freq_pct']:5.2f}%, ĐV R1={res['units_oos_rank1_freq_pct']:5.2f}% | "
            f"2x2 ROI={res['roi_2x2_pct']:+6.2f}% | 1x4 ROI={res['roi_1x4_pct']:+6.2f}% | "
            f"Số kỳ tới (2x2): {res['next_draw_2x2_numbers']} | (1x4): {res['next_draw_1x4_numbers']}"
        )

    # Sort by tier priority and best_roi_pct descending
    tier_order = {"PASS_ALPHA": 0, "WARN_WEAK_SIGNAL": 1, "FAIL_WHITE_NOISE_CASH_BRAKE": 2}
    results.sort(key=lambda r: (tier_order.get(r["tier"], 9), -r["best_roi_pct"]))

    if not args.station:
        json_out = Path("reports/all_35_stations_radar.json")
        html_out = Path("reports/all_35_stations_radar_report.html")
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        generate_html_radar_report(results, html_out)
        print(
            f"\n[HOÀN TẤT] Đã xuất bảng xếp hạng 35 đài tại:\n"
            f"  - HTML: {html_out}\n  - JSON: {json_out}"
        )


if __name__ == "__main__":
    asyncio.run(main_async())
