"""Tier 2 TDD Suite: Pillar 1A Ingest/Canonicalizer/Fetcher and Pillar 1B Pre-Draw Features."""

from __future__ import annotations

import datetime
import json
import math
import unicodedata
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from xsmn_alpha.constants import (
    DEFICIT_10_STD,
    GAP_MEAN_MU,
    GAP_STD_SIGMA,
    REGIME_WINDOWS,
)
from xsmn_alpha.exceptions import (
    DataIntegrityError,
    InsufficientSampleSizeError,
    TemporalLeakageError,
)
from xsmn_alpha.features.extractor import (
    PreDrawCutoffGate,
    enforce_pre_draw_cutoff,
    extract_cage_features,
    extract_features,
)
from xsmn_alpha.ingest.canonicalizer import (
    canonicalize_draws,
    decompose_cage_counts,
    deduplicate_and_sort_raw_draws,
    load_canonical_draws,
    normalize_draw_date,
    save_canonical_draws,
    slice_horizon,
)
from xsmn_alpha.ingest.fetcher import (
    compute_draws_sha256,
    fetch_draw_with_failover,
    fetch_station_draws,
    load_raw_cache,
    parse_minhngoc_html,
    parse_xoso_html,
    parse_xskt_html,
    save_raw_cache,
)
from xsmn_alpha.schemas import CanonicalDrawRecord


def _generate_synthetic_raw_draws(
    station_code: str,
    num_draws: int,
    start_date: datetime.date = datetime.date(2021, 1, 1),
    step_days: int = 3,
) -> list[dict[str, Any]]:
    """Generate deterministic valid raw draw dictionaries in chronological order."""
    draws: list[dict[str, Any]] = []
    for idx in range(num_draws):
        draw_dt = start_date + datetime.timedelta(days=idx * step_days)
        prizes = [f"{(idx + g * 7) % 100:02d}" for g in range(18)]
        draws.append(
            {
                "station_code": station_code,
                "draw_date": draw_dt.isoformat(),
                "prizes_last2": prizes,
            }
        )
    return draws


def _build_minhngoc_table_html(
    draw_date_dmy: str,
    full_prizes_18: list[str],
    station_label: str = "TP. HCM",
    station_slug: str = "tp-hcm",
) -> str:
    """Build a realistic minhngoc.net.vn <table class='bkqtinhmiennam'> HTML snippet."""
    assert len(full_prizes_18) == 18
    g8 = full_prizes_18[0]
    g7 = full_prizes_18[1]
    g6 = "".join(f"<div>{p}</div>" for p in full_prizes_18[2:5])
    g5 = full_prizes_18[5]
    g4 = "".join(f"<div>{p}</div>" for p in full_prizes_18[6:13])
    g3 = "".join(f"<div>{p}</div>" for p in full_prizes_18[13:15])
    g2 = full_prizes_18[15]
    g1 = full_prizes_18[16]
    gdb = full_prizes_18[17]
    return f"""
    <table class="bkqtinhmiennam">
      <tr>
        <td class="ngay">Thứ Bảy - Ngày: {draw_date_dmy}</td>
      </tr>
      <tr>
        <td>
          <table class="rightcl">
            <tr><td class="tinh">
              <a href="/ket-qua-xo-so/mien-nam/{station_slug}.html">{station_label}</a>
            </td></tr>
            <tr><td class="giai8"><div>{g8}</div></td></tr>
            <tr><td class="giai7"><div>{g7}</div></td></tr>
            <tr><td class="giai6">{g6}</td></tr>
            <tr><td class="giai5"><div>{g5}</div></td></tr>
            <tr><td class="giai4">{g4}</td></tr>
            <tr><td class="giai3">{g3}</td></tr>
            <tr><td class="giai2"><div>{g2}</div></td></tr>
            <tr><td class="giai1"><div>{g1}</div></td></tr>
            <tr><td class="giaidb"><div>{gdb}</div></td></tr>
          </table>
        </td>
      </tr>
    </table>
    """


class TestCanonicalizerAndHorizonSlicing:
    """Task 3 unit and negative mutation tests for canonicalizer.py (matches -k 'canonical')."""

    def test_canonical_decompose_18_prizes_and_canonicalize_pass(
        self,
        sample_valid_prizes_18: list[str],
        sample_valid_tens_counts: list[int],
        sample_valid_units_counts: list[int],
    ) -> None:
        tens, units = decompose_cage_counts(sample_valid_prizes_18)
        assert tens == sample_valid_tens_counts
        assert units == sample_valid_units_counts
        assert sum(tens) == 18
        assert sum(units) == 18

        raw_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-19",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": list(reversed(sample_valid_prizes_18)),
            },
        ]
        records = canonicalize_draws(raw_draws, station_code="XSHCM")
        assert len(records) == 2
        assert records[0].draw_index == 0
        assert records[0].draw_date == "2026-10-19"
        assert records[0].prizes_last2[0] == "42"  # Giải Tám at index 0
        assert records[0].prizes_last2[17] == "83"  # Giải ĐB at index 17
        assert records[0].tens_counts == sample_valid_tens_counts
        assert records[0].units_counts == sample_valid_units_counts

        assert records[1].draw_index == 1
        assert records[1].draw_date == "2026-10-24"
        assert records[1].prizes_last2[0] == "83"
        assert records[1].prizes_last2[17] == "42"
        assert sum(records[1].tens_counts) == 18
        assert sum(records[1].units_counts) == 18

    def test_canonical_normalize_date_and_deduplicate_helper(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        assert normalize_draw_date("24/10/2026") == "2026-10-24"
        assert normalize_draw_date("24-10-2026") == "2026-10-24"
        assert normalize_draw_date("2026-10-24") == "2026-10-24"

        with pytest.raises(DataIntegrityError):
            normalize_draw_date("2026/99/99")

        # Multi-page batch helper sorts ascending and deduplicates identical overlapping draws
        raw_unsorted = [
            {
                "station_code": "XSVL",
                "draw_date": "2026-10-23",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSVL",
                "draw_date": "2026-10-16",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSVL",
                "draw_date": "2026-10-23",
                "prizes_last2": sample_valid_prizes_18,
            },
        ]
        deduped = deduplicate_and_sort_raw_draws(raw_unsorted, station_code="XSVL")
        assert [d["draw_date"] for d in deduped] == ["2026-10-16", "2026-10-23"]

        # Conflicting prizes on the same date must raise DataIntegrityError
        conflicting = [
            {
                "station_code": "XSVL",
                "draw_date": "2026-10-23",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSVL",
                "draw_date": "2026-10-23",
                "prizes_last2": ["99", *sample_valid_prizes_18[1:]],
            },
        ]
        with pytest.raises(DataIntegrityError):
            deduplicate_and_sort_raw_draws(conflicting, station_code="XSVL")

    def test_canonical_negative_mutations_duplicate_and_out_of_order_dates_fail(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        # Duplicate draw_date must fail
        dup_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": sample_valid_prizes_18,
            },
        ]
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(dup_draws, station_code="XSHCM")

        # Out-of-order / reversed chronological draw_date must fail
        reversed_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": sample_valid_prizes_18,
            },
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-19",
                "prizes_last2": sample_valid_prizes_18,
            },
        ]
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(reversed_draws, station_code="XSHCM")

        # Missing prize (17 prizes) must fail
        missing_prize_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": sample_valid_prizes_18[:17],
            }
        ]
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(missing_prize_draws, station_code="XSHCM")

        # Full-width Unicode or invalid ASCII prize must fail
        bad_prize_draws = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": ["０８", *sample_valid_prizes_18[1:]],
            }
        ]
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(bad_prize_draws, station_code="XSHCM")

        # Empty input or invalid station_code must fail
        with pytest.raises(DataIntegrityError):
            canonicalize_draws([], station_code="XSHCM")

        with pytest.raises(DataIntegrityError):
            canonicalize_draws(
                [
                    {
                        "station_code": "XSHCM",
                        "draw_date": "2026-10-24",
                        "prizes_last2": sample_valid_prizes_18,
                    }
                ],
                station_code="XSTG",
            )

        # Mismatched station_code in record must fail
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(
                [
                    {
                        "station_code": "XSVL",
                        "draw_date": "2026-10-24",
                        "prizes_last2": sample_valid_prizes_18,
                    }
                ],
                station_code="XSHCM",
            )

    def test_canonical_slice_horizon_5y_and_3y_for_xshcm_and_xsvl(self) -> None:
        raw_hcm = _generate_synthetic_raw_draws("XSHCM", 520, step_days=3)
        draws_hcm = canonicalize_draws(raw_hcm, station_code="XSHCM")
        assert len(draws_hcm) == 520
        assert draws_hcm[0].draw_index == 0
        assert draws_hcm[-1].draw_index == 519

        hcm_5y = slice_horizon(draws_hcm, "XSHCM", "5y")
        assert len(hcm_5y) == 520
        assert [d.draw_index for d in hcm_5y] == list(range(520))
        assert hcm_5y[0].draw_date == draws_hcm[0].draw_date
        assert hcm_5y[-1].draw_date == draws_hcm[-1].draw_date

        hcm_3y = slice_horizon(draws_hcm, "XSHCM", "3y")
        assert len(hcm_3y) == 312
        assert [d.draw_index for d in hcm_3y] == list(range(312))
        assert hcm_3y[0].draw_date == draws_hcm[520 - 312].draw_date
        assert hcm_3y[-1].draw_date == draws_hcm[-1].draw_date
        assert hcm_3y[0].prizes_last2 == draws_hcm[520 - 312].prizes_last2
        # Ensure original list was not mutated
        assert draws_hcm[520 - 312].draw_index == 208
        assert draws_hcm[-1].draw_index == 519

        raw_vl = _generate_synthetic_raw_draws("XSVL", 260, step_days=7)
        draws_vl = canonicalize_draws(raw_vl, station_code="XSVL")
        vl_5y = slice_horizon(draws_vl, "XSVL", "5y")
        vl_3y = slice_horizon(draws_vl, "XSVL", "3y")
        assert len(vl_5y) == 260
        assert [d.draw_index for d in vl_5y] == list(range(260))
        assert len(vl_3y) == 156
        assert [d.draw_index for d in vl_3y] == list(range(156))
        assert vl_3y[0].draw_date == draws_vl[260 - 156].draw_date
        assert draws_vl[260 - 156].draw_index == 104

    def test_canonical_slice_horizon_negative_mutations(self) -> None:
        raw_short = _generate_synthetic_raw_draws("XSHCM", 200, step_days=3)
        draws_short = canonicalize_draws(raw_short, station_code="XSHCM")

        with pytest.raises(InsufficientSampleSizeError):
            slice_horizon(draws_short, "XSHCM", "3y")

        with pytest.raises(InsufficientSampleSizeError):
            slice_horizon(draws_short, "XSHCM", "5y")

        with pytest.raises(DataIntegrityError):
            slice_horizon(draws_short, "XSHCM", "10y")

        with pytest.raises(DataIntegrityError):
            slice_horizon(draws_short, "XSTG", "3y")

        with pytest.raises(DataIntegrityError):
            slice_horizon(draws_short, "XSVL", "3y")

    def test_canonical_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        raw_vl = _generate_synthetic_raw_draws("XSVL", 65, step_days=7)
        draws_vl = canonicalize_draws(raw_vl, station_code="XSVL")
        out_file = tmp_path / "canonical" / "XSVL_canonical.json"

        saved_path = save_canonical_draws(draws_vl, out_file)
        assert saved_path == out_file
        assert out_file.exists()

        loaded = load_canonical_draws(out_file, station_code="XSVL")
        assert loaded == draws_vl

        # Also test station inference when station_code=None
        loaded_inferred = load_canonical_draws(out_file, station_code=None)
        assert loaded_inferred == draws_vl

        # Station mismatch on load must raise DataIntegrityError
        with pytest.raises(DataIntegrityError):
            load_canonical_draws(out_file, station_code="XSHCM")

        # Empty save or missing/corrupted load must raise DataIntegrityError
        with pytest.raises(DataIntegrityError):
            save_canonical_draws([], out_file)

        with pytest.raises(DataIntegrityError):
            load_canonical_draws(tmp_path / "does_not_exist.json")

        bad_json_file = tmp_path / "bad.json"
        bad_json_file.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            load_canonical_draws(bad_json_file)

    def test_canonical_additional_edge_branches(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        # Non-ASCII or invalid calendar date in normalize_draw_date
        with pytest.raises(DataIntegrityError):
            normalize_draw_date("2026-10-２４")
        with pytest.raises(DataIntegrityError):
            normalize_draw_date("31/02/2026")

        # decompose_cage_counts with invalid length
        with pytest.raises(DataIntegrityError):
            decompose_cage_counts(["42"])

        # extract_last2_from_full_prizes=True and require_sorted=False on canonicalize_draws
        full_18 = [f"12{p}" for p in sample_valid_prizes_18]
        raw_full_unsorted = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "prizes_last2": full_18,
            },
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-19",
                "prizes_last2": full_18,
            },
        ]
        dedup = deduplicate_and_sort_raw_draws(
            raw_full_unsorted,
            station_code="XSHCM",
            extract_last2_from_full_prizes=True,
        )
        assert len(dedup) == 2
        assert dedup[0]["prizes_last2"] == sample_valid_prizes_18

        recs = canonicalize_draws(
            raw_full_unsorted,
            station_code="XSHCM",
            require_sorted=False,
            extract_last2_from_full_prizes=True,
        )
        assert [r.draw_date for r in recs] == ["2026-10-19", "2026-10-24"]
        assert [r.draw_index for r in recs] == [0, 1]

        # Canonicalize existing CanonicalDrawRecord instances
        recs_again = canonicalize_draws(recs, station_code="XSHCM")
        assert recs_again == recs

        with pytest.raises(DataIntegrityError):
            canonicalize_draws(recs, station_code="XSVL")

        with pytest.raises(DataIntegrityError):
            canonicalize_draws([123], station_code="XSHCM")  # type: ignore[list-item]

        with pytest.raises(DataIntegrityError):
            slice_horizon([], "XSHCM", "3y")

    def test_canonical_corrupted_counts_and_non_contiguous_slice_rejected(
        self,
        tmp_path: Path,
        sample_valid_prizes_18: list[str],
    ) -> None:
        # SA-03: load_canonical_draws and canonicalize_draws must reject corrupted tens_counts,
        # units_counts, negative draw_index, or unexpected extra fields in canonical JSON
        bad_canonical_file = tmp_path / "corrupted_canonical.json"
        corrupted_payload = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "draw_index": -999,
                "prizes_last2": sample_valid_prizes_18,
                "tens_counts": [999, -50, 0, 0, 0, 0, 0, 0, 0, 0],
                "units_counts": ["not_an_int"],
                "malicious_extra_field": "bypassed_extra_forbid",
            }
        ]
        bad_canonical_file.write_text(json.dumps(corrupted_payload), encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            load_canonical_draws(bad_canonical_file, station_code="XSHCM")

        # Also test non-contiguous draw_index in canonicalize_draws
        t_counts, u_counts = decompose_cage_counts(sample_valid_prizes_18)
        gapped_dicts = [
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-19",
                "draw_index": 0,
                "prizes_last2": sample_valid_prizes_18,
                "tens_counts": t_counts,
                "units_counts": u_counts,
            },
            {
                "station_code": "XSHCM",
                "draw_date": "2026-10-24",
                "draw_index": 5,
                "prizes_last2": sample_valid_prizes_18,
                "tens_counts": t_counts,
                "units_counts": u_counts,
            },
        ]
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(gapped_dicts, station_code="XSHCM")

        # In-place mutated CanonicalDrawRecord passed to canonicalize_draws or slice_horizon fails
        raw_vl = _generate_synthetic_raw_draws("XSVL", 160, step_days=7)
        draws_vl = canonicalize_draws(raw_vl, station_code="XSVL")
        draws_vl[10].prizes_last2[0] = "99" if draws_vl[10].prizes_last2[0] != "99" else "00"
        with pytest.raises(DataIntegrityError):
            canonicalize_draws(draws_vl, station_code="XSVL")
        with pytest.raises(DataIntegrityError):
            slice_horizon(draws_vl, "XSVL", "3y")

        # SA-12: Non-contiguous draw_index passed to slice_horizon must raise DataIntegrityError
        draws_vl_clean = canonicalize_draws(raw_vl, station_code="XSVL")
        gapped_vl = [*draws_vl_clean[:50], *draws_vl_clean[51:]]
        assert len(gapped_vl) == 159
        with pytest.raises(DataIntegrityError):
            slice_horizon(gapped_vl, "XSVL", "3y")


class TestMultiSourceFetcherAndCache:
    """Task 4 unit and negative mutation tests for fetcher.py (matches -k 'fetcher')."""

    def test_fetcher_parse_minhngoc_html_multi_draw_and_station_filtering(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        full_prizes_1 = [
            "42",
            "518",
            "1273",
            "4908",
            "6083",
            "9139",
            "12388",
            "45114",
            "67257",
            "89081",
            "34123",
            "56290",
            "78338",
            "90184",
            "11261",
            "22303",
            "33478",
            "999483",
        ]
        full_prizes_2 = [
            f"{1000 + i:04d}{p}" for i, p in enumerate(reversed(sample_valid_prizes_18))
        ]

        html_batch = (
            "<html><body>"
            + _build_minhngoc_table_html("24/10/2026", full_prizes_1, "TP. HCM", "tp-hcm")
            + _build_minhngoc_table_html("19/10/2026", full_prizes_2, "TP. HCM", "tp-hcm")
            + "</body></html>"
        )

        parsed = parse_minhngoc_html(html_batch, station_code="XSHCM")
        assert len(parsed) == 2
        by_date = {d["draw_date"]: d for d in parsed}
        assert set(by_date.keys()) == {"2026-10-19", "2026-10-24"}
        assert by_date["2026-10-24"]["prizes_last2"] == sample_valid_prizes_18
        assert by_date["2026-10-24"]["prizes_last2"][0] == "42"  # Giải 8
        assert by_date["2026-10-24"]["prizes_last2"][17] == "83"  # Giải ĐB
        assert by_date["2026-10-19"]["prizes_last2"] == list(reversed(sample_valid_prizes_18))

    def test_fetcher_parse_xskt_and_xoso_fallback_html_formats(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        # xskt.com.vn style table where Giải ĐB is at the bottom or top with G8..ĐB row labels
        p = sample_valid_prizes_18
        g4_dash = " - ".join(f"10{i + 1}{p[6 + i]}" for i in range(7))
        xskt_html = f"""
        <html><body>
        <div class="box-ketqua">
          <h2>Kết quả XSVL ngày 23-10-2026</h2>
          <table>
            <tr><td>G8</td><td>{p[0]}</td></tr>
            <tr><td>G7</td><td>7{p[1]}</td></tr>
            <tr><td>G6</td><td>12{p[2]} - 34{p[3]} - 56{p[4]}</td></tr>
            <tr><td>G5</td><td>88{p[5]}</td></tr>
            <tr><td>G4</td><td>{g4_dash}</td></tr>
            <tr><td>G3</td><td>201{p[13]} - 202{p[14]}</td></tr>
            <tr><td>G2</td><td>301{p[15]}</td></tr>
            <tr><td>G1</td><td>401{p[16]}</td></tr>
            <tr><td>ĐB</td><td>9999{p[17]}</td></tr>
          </table>
        </div>
        </body></html>
        """
        xskt_draws = parse_xskt_html(xskt_html, station_code="XSVL", fallback_date="2026-10-23")
        assert len(xskt_draws) == 1
        assert xskt_draws[0]["draw_date"] == "2026-10-23"
        assert xskt_draws[0]["prizes_last2"] == sample_valid_prizes_18

        # xoso.com.vn style table where Giải ĐB appears FIRST at top of table and Giải 8 at bottom
        xoso_html = f"""
        <html><body>
        <table class="table-result">
          <tr><th>ĐB</th><td><span class="special-prize">8888{p[17]}</span></td></tr>
          <tr><th>G.1</th><td><span>444{p[16]}</span></td></tr>
          <tr><th>G.2</th><td><span>333{p[15]}</span></td></tr>
          <tr><th>G.3</th><td><span>222{p[13]}</span><span>222{p[14]}</span></td></tr>
          <tr><th>G.4</th><td>
            <span>111{p[6]}</span><span>111{p[7]}</span><span>111{p[8]}</span>
            <span>111{p[9]}</span><span>111{p[10]}</span><span>111{p[11]}</span><span>111{p[12]}</span>
          </td></tr>
          <tr><th>G.5</th><td><span>55{p[5]}</span></td></tr>
          <tr><th>G.6</th><td><span>66{p[2]}</span><span>66{p[3]}</span><span>66{p[4]}</span></td></tr>
          <tr><th>G.7</th><td><span>7{p[1]}</span></td></tr>
          <tr><th>G.8</th><td><span>{p[0]}</span></td></tr>
        </table>
        </body></html>
        """
        xoso_draws = parse_xoso_html(xoso_html, station_code="XSVL", fallback_date="2026-10-23")
        assert len(xoso_draws) == 1
        assert xoso_draws[0]["draw_date"] == "2026-10-23"
        assert xoso_draws[0]["prizes_last2"] == sample_valid_prizes_18
        assert xoso_draws[0]["prizes_last2"][0] == p[0]  # Giải 8 at index 0
        assert xoso_draws[0]["prizes_last2"][17] == p[17]  # Giải ĐB at index 17

    @pytest.mark.anyio
    async def test_fetcher_failover_primary_to_xskt_and_xoso_and_total_failure_gate(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        p = sample_valid_prizes_18
        g4_space = " ".join(f"111{p[6 + i]}" for i in range(7))
        valid_xskt_html = f"""
        <table>
          <tr><td>G8</td><td>{p[0]}</td></tr>
          <tr><td>G7</td><td>1{p[1]}</td></tr>
          <tr><td>G6</td><td>11{p[2]} 11{p[3]} 11{p[4]}</td></tr>
          <tr><td>G5</td><td>11{p[5]}</td></tr>
          <tr><td>G4</td><td>{g4_space}</td></tr>
          <tr><td>G3</td><td>111{p[13]} 111{p[14]}</td></tr>
          <tr><td>G2</td><td>111{p[15]}</td></tr>
          <tr><td>G1</td><td>111{p[16]}</td></tr>
          <tr><td>ĐB</td><td>1111{p[17]}</td></tr>
        </table>
        """
        incomplete_minhngoc_html = """
        <table class="bkqtinhmiennam">
          <tr><td class="ngay">24/10/2026</td></tr>
          <tr><td class="giai8">42</td></tr>
        </table>
        """

        # Case 1: Primary returns incomplete draw (<18 prizes) -> Fallback 1 (xskt) succeeds
        def handler_fallback1(request: httpx.Request) -> httpx.Response:
            host = request.url.host or ""
            if "minhngoc" in host:
                return httpx.Response(200, text=incomplete_minhngoc_html)
            if "xskt.com.vn" in host:
                return httpx.Response(200, text=valid_xskt_html)
            return httpx.Response(500, text="error")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler_fallback1)) as client:
            draw = await fetch_draw_with_failover(
                client=client,
                station_code="XSHCM",
                draw_date="2026-10-24",
            )
            assert draw["draw_date"] == "2026-10-24"
            assert draw["prizes_last2"] == sample_valid_prizes_18

        # Case 2: Primary HTTP 503 + Fallback 1 incomplete -> Fallback 2 (xoso) succeeds
        def handler_fallback2(request: httpx.Request) -> httpx.Response:
            host = request.url.host or ""
            if "minhngoc" in host:
                return httpx.Response(503, text="Service Unavailable")
            if "xskt.com.vn" in host:
                return httpx.Response(200, text="<html><body>Updating...</body></html>")
            if "xoso.com.vn" in host:
                return httpx.Response(200, text=valid_xskt_html)
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler_fallback2)) as client:
            draw2 = await fetch_draw_with_failover(
                client=client,
                station_code="XSVL",
                draw_date="2026-10-23",
            )
            assert draw2["draw_date"] == "2026-10-23"
            assert draw2["prizes_last2"] == sample_valid_prizes_18

        # Case 3 (Negative Mutation): All 3 sources fail or return < 18 prizes -> DataIntegrityError
        def handler_all_fail(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=incomplete_minhngoc_html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler_all_fail)) as client:
            with pytest.raises(DataIntegrityError):
                await fetch_draw_with_failover(
                    client=client,
                    station_code="XSHCM",
                    draw_date="2026-10-24",
                )

    def test_fetcher_local_cache_sha256_and_incremental_delta_sync(
        self,
        tmp_path: Path,
        sample_valid_prizes_18: list[str],
    ) -> None:
        # Prepare 259 historical Friday draws for XSVL ending on 2026-10-16
        end_dt = datetime.date(2026, 10, 23)
        start_dt = end_dt - datetime.timedelta(days=259 * 7)
        raw_259 = _generate_synthetic_raw_draws("XSVL", 259, start_date=start_dt, step_days=7)
        assert raw_259[-1]["draw_date"] == "2026-10-16"

        cache_path = save_raw_cache(
            station_code="XSVL",
            raw_draws=raw_259,
            raw_dir=tmp_path,
        )
        assert cache_path.exists()

        # Verify load_raw_cache validates SHA-256
        loaded_259 = load_raw_cache("XSVL", raw_dir=tmp_path)
        assert len(loaded_259) == 259
        assert loaded_259[-1]["draw_date"] == "2026-10-16"

        # Incremental Delta Sync: fetching up to 2026-10-23 should ONLY request the new draw
        requested_urls: list[str] = []
        delta_html = _build_minhngoc_table_html(
            "23/10/2026",
            [f"12{p}" for p in sample_valid_prizes_18],
            station_label="Vĩnh Long",
            station_slug="vinh-long",
        )

        def delta_handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(200, text=delta_html)

        records_260 = fetch_station_draws(
            station_code="XSVL",
            years=5,
            raw_dir=tmp_path,
            as_of_date=end_dt,
            transport=httpx.MockTransport(delta_handler),
        )
        assert len(records_260) == 260
        assert isinstance(records_260[-1], CanonicalDrawRecord)
        assert records_260[-1].draw_date == "2026-10-23"
        assert records_260[-1].draw_index == 259
        assert records_260[-1].prizes_last2 == sample_valid_prizes_18
        assert len(requested_urls) == 1  # Only 1 delta request made, not 38 pages!

        # Second call with same as_of_date should make ZERO network requests (0s wait)
        requested_urls.clear()
        records_cached = fetch_station_draws(
            station_code="XSVL",
            years=5,
            raw_dir=tmp_path,
            as_of_date=end_dt,
            transport=httpx.MockTransport(delta_handler),
        )
        assert len(records_cached) == 260
        assert len(requested_urls) == 0

        # Negative Mutation: Tampering with cache prizes without updating sha256 must fail
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["draws"][0]["prizes_last2"][0] = (
            "99" if payload["draws"][0]["prizes_last2"][0] != "99" else "00"
        )
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=tmp_path)

    def test_fetcher_batch_crawl_from_empty_cache_and_edge_cases(
        self,
        tmp_path: Path,
        sample_valid_prizes_18: list[str],
    ) -> None:
        from xsmn_alpha.ingest.fetcher import (
            build_minhngoc_url,
            build_xoso_url,
            build_xskt_url,
            generate_expected_draw_dates,
        )

        with pytest.raises(DataIntegrityError):
            build_minhngoc_url("XSTG", "2026-10-24")
        with pytest.raises(DataIntegrityError):
            build_xskt_url("XSTG", "2026-10-24")
        with pytest.raises(DataIntegrityError):
            build_xoso_url("XSTG", "2026-10-24")
        with pytest.raises(DataIntegrityError):
            generate_expected_draw_dates("XSVL", 0)
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=tmp_path / "missing_dir")

        # Single-station bkqtinhmiennam table without inner rightcl table
        p = sample_valid_prizes_18
        g4_single = " - ".join(f"111{p[6 + i]}" for i in range(7))
        single_table_html = f"""
        <table class="bkqtinhmiennam">
          <tr><td class="ngay">23/10/2026</td></tr>
          <tr><td class="giai8">{p[0]}</td></tr>
          <tr><td class="giai7">1{p[1]}</td></tr>
          <tr><td class="giai6">11{p[2]} - 11{p[3]} - 11{p[4]}</td></tr>
          <tr><td class="giai5">11{p[5]}</td></tr>
          <tr><td class="giai4">{g4_single}</td></tr>
          <tr><td class="giai3">111{p[13]} - 111{p[14]}</td></tr>
          <tr><td class="giai2">111{p[15]}</td></tr>
          <tr><td class="giai1">111{p[16]}</td></tr>
          <tr><td class="giaidb">1111{p[17]}</td></tr>
        </table>
        """
        parsed_single = parse_minhngoc_html(single_table_html, station_code="XSVL")
        assert len(parsed_single) == 1
        assert parsed_single[0]["prizes_last2"] == sample_valid_prizes_18

        # Full batch crawl for years=1 (52 draws for XSVL) starting from empty cache
        # Omit the last draw from batch pages so missing-date failover (xskt) recovers it
        end_dt = datetime.date(2026, 10, 23)
        expected_52 = generate_expected_draw_dates("XSVL", 52, as_of_date=end_dt)
        batch_51_html = (
            "<html><body>"
            + "".join(
                _build_minhngoc_table_html(
                    datetime.date.fromisoformat(dt).strftime("%d/%m/%Y"),
                    [f"12{x}" for x in sample_valid_prizes_18],
                    station_label="Vĩnh Long",
                    station_slug="vinh-long",
                )
                for dt in expected_52[:-1]
            )
            + "</body></html>"
        )

        missing_last_html = _build_minhngoc_table_html(
            datetime.date.fromisoformat(expected_52[-1]).strftime("%d/%m/%Y"),
            [f"12{x}" for x in sample_valid_prizes_18],
            station_label="Vĩnh Long",
            station_slug="vinh-long",
        )

        attempts = 0

        def batch_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("Transient connection glitch")
            host = request.url.host or ""
            if "xskt.com.vn" in host:
                return httpx.Response(200, text=missing_last_html)
            return httpx.Response(200, text=batch_51_html)

        records_52 = fetch_station_draws(
            station_code="XSVL",
            years=1,
            raw_dir=tmp_path / "batch_raw",
            as_of_date=end_dt,
            transport=httpx.MockTransport(batch_handler),
        )
        assert len(records_52) == 52
        assert records_52[0].draw_index == 0
        assert records_52[-1].draw_index == 51
        assert (tmp_path / "batch_raw" / "XSVL_draws.json").exists()

        # Also test cache station mismatch and invalid JSON
        bad_cache_dir = tmp_path / "bad_cache"
        bad_cache_dir.mkdir(parents=True, exist_ok=True)
        (bad_cache_dir / "XSVL_draws.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=bad_cache_dir)

        (bad_cache_dir / "XSVL_draws.json").write_text(
            json.dumps({"station_code": "XSHCM", "draws": [], "sha256": "abc"}),
            encoding="utf-8",
        )
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=bad_cache_dir)

    def test_fetcher_nfd_unicode_negative_prizes_wrong_station_and_multitable(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        p = sample_valid_prizes_18
        # SA-06: Unicode NFD normalized Vietnamese HTML must parse identically to NFC
        minhngoc_nfc = _build_minhngoc_table_html(
            "23/10/2026",
            [f"12{x}" for x in p],
            station_label="Vĩnh Long",
            station_slug="vinh-long",
        )
        minhngoc_nfd = unicodedata.normalize("NFD", minhngoc_nfc)
        assert parse_minhngoc_html(minhngoc_nfd, station_code="XSVL") == parse_minhngoc_html(
            minhngoc_nfc, station_code="XSVL"
        )

        g4_dash = " - ".join(f"10{i + 1}{p[6 + i]}" for i in range(7))
        xskt_nfc = f"""
        <div class="box-ketqua">
          <h2>Kết quả Xổ Số Vĩnh Long ngày 23-10-2026</h2>
          <table>
            <tr><td>Giải tám</td><td>{p[0]}</td></tr>
            <tr><td>Giải bảy</td><td>7{p[1]}</td></tr>
            <tr><td>Giải sáu</td><td>12{p[2]} - 34{p[3]} - 56{p[4]}</td></tr>
            <tr><td>Giải năm</td><td>88{p[5]}</td></tr>
            <tr><td>Giải tư</td><td>{g4_dash}</td></tr>
            <tr><td>Giải ba</td><td>201{p[13]} - 202{p[14]}</td></tr>
            <tr><td>Giải nhì</td><td>301{p[15]}</td></tr>
            <tr><td>Giải nhất</td><td>401{p[16]}</td></tr>
            <tr><td>Đặc biệt</td><td>9999{p[17]}</td></tr>
          </table>
        </div>
        """
        xskt_nfd = unicodedata.normalize("NFD", xskt_nfc)
        assert parse_xskt_html(xskt_nfd, station_code="XSVL") == parse_xskt_html(
            xskt_nfc, station_code="XSVL"
        )

        # SA-05: Reject negative prizes ("-42"), duplicate rows (19 prizes), and wrong station
        wrong_station_html = xskt_nfc.replace("Xổ Số Vĩnh Long", "Xổ Số Cần Thơ (XSCT)")
        assert parse_xskt_html(wrong_station_html, station_code="XSVL") == []

        negative_prize_html = xskt_nfc.replace(f"<td>{p[0]}</td>", f"<td>-{p[0]}</td>")
        assert parse_xskt_html(negative_prize_html, station_code="XSVL") == []

        dup_row_html = xskt_nfc.replace(
            f"<tr><td>Giải tám</td><td>{p[0]}</td></tr>",
            f"<tr><td>Giải tám</td><td>{p[0]}</td></tr><tr><td>Giải tám</td><td>99</td></tr>",
        )
        assert parse_xskt_html(dup_row_html, station_code="XSVL") == []

        # SA-10: Multi-table HTML must extract per-table dates rather than first page-global date
        p_rev = list(reversed(p))
        g4_rev = " - ".join(f"10{i + 1}{p_rev[6 + i]}" for i in range(7))
        multi_xskt_html = (
            xskt_nfc
            + f"""
            <div class="box-ketqua">
              <h2>Kết quả Xổ Số Vĩnh Long ngày 16-10-2026</h2>
              <table>
                <tr><td>G8</td><td>{p_rev[0]}</td></tr>
                <tr><td>G7</td><td>7{p_rev[1]}</td></tr>
                <tr><td>G6</td><td>12{p_rev[2]} - 34{p_rev[3]} - 56{p_rev[4]}</td></tr>
                <tr><td>G5</td><td>88{p_rev[5]}</td></tr>
                <tr><td>G4</td><td>{g4_rev}</td></tr>
                <tr><td>G3</td><td>201{p_rev[13]} - 202{p_rev[14]}</td></tr>
                <tr><td>G2</td><td>301{p_rev[15]}</td></tr>
                <tr><td>G1</td><td>401{p_rev[16]}</td></tr>
                <tr><td>ĐB</td><td>9999{p_rev[17]}</td></tr>
              </table>
            </div>
            """
        )
        multi_parsed = parse_xskt_html(multi_xskt_html, station_code="XSVL")
        assert [d["draw_date"] for d in multi_parsed] == ["2026-10-16", "2026-10-23"]

    def test_fetcher_cache_corruption_and_historical_as_of_date_cutoff(
        self,
        tmp_path: Path,
    ) -> None:
        # SA-09: compute_draws_sha256 and load_raw_cache must raise DataIntegrityError on
        # malformed records, tampered draw_count/last_draw_date, or unsorted/duplicate draws
        with pytest.raises(DataIntegrityError):
            compute_draws_sha256([{"station_code": "XSVL"}])

        corrupt_dir = tmp_path / "corrupt_raw"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        cache_file = corrupt_dir / "XSVL_draws.json"

        # 1. Missing 'draw_date' key in draw dict
        cache_file.write_text(
            json.dumps(
                {
                    "station_code": "XSVL",
                    "draw_count": 1,
                    "last_draw_date": "2026-10-23",
                    "sha256": "0" * 64,
                    "draws": [{"station_code": "XSVL"}],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=corrupt_dir)

        # 2. Duplicate/unsorted draws with matching SHA-256 or tampered metadata
        raw_2 = _generate_synthetic_raw_draws("XSVL", 2, step_days=7)
        dup_draws = [raw_2[1], raw_2[0], raw_2[1]]
        cache_file.write_text(
            json.dumps(
                {
                    "station_code": "XSVL",
                    "draw_count": 3,
                    "last_draw_date": raw_2[1]["draw_date"],
                    "sha256": compute_draws_sha256(dup_draws),
                    "draws": dup_draws,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=corrupt_dir)

        # 3. Tampered draw_count metadata with valid draws and SHA-256
        cache_file.write_text(
            json.dumps(
                {
                    "station_code": "XSVL",
                    "draw_count": 999,
                    "last_draw_date": raw_2[-1]["draw_date"],
                    "sha256": compute_draws_sha256(raw_2),
                    "draws": raw_2,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(DataIntegrityError):
            load_raw_cache("XSVL", raw_dir=corrupt_dir)

        # SA-01: Historical as_of_date must filter out future draws cached on disk
        end_dt = datetime.date(2026, 10, 23)
        start_dt = end_dt - datetime.timedelta(days=59 * 7)
        raw_60 = _generate_synthetic_raw_draws("XSVL", 60, start_date=start_dt, step_days=7)
        hist_dir = tmp_path / "hist_cache"
        save_raw_cache("XSVL", raw_60, raw_dir=hist_dir)

        historical_cutoff = end_dt - datetime.timedelta(days=5 * 7)
        hist_records = fetch_station_draws(
            station_code="XSVL",
            years=1,
            raw_dir=hist_dir,
            as_of_date=historical_cutoff,
        )
        assert len(hist_records) == 52
        assert hist_records[-1].draw_date <= historical_cutoff.isoformat()
        assert all(r.draw_date <= historical_cutoff.isoformat() for r in hist_records)


class TestPreDrawCutoffAndFeatureExtractor:
    """Task 5 unit, analytical invariant, and negative mutation tests for extractor.py."""

    def test_features_pre_draw_cutoff_gate_negative_mutations_fail(self) -> None:
        raw_draws = _generate_synthetic_raw_draws("XSHCM", 25, step_days=3)
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        target_t = 15
        target_draw = draws[target_t]

        # Valid slice draws[:t] passes PreDrawCutoffGate
        enforce_pre_draw_cutoff(draws[:target_t], target_draw)
        PreDrawCutoffGate.enforce(draws[:target_t], target_draw)

        # 1. Empty history must raise TemporalLeakageError
        with pytest.raises(TemporalLeakageError):
            extract_features([], target_draw)

        # 2. Look-ahead leakage: history includes target_draw itself (draws[:t+1])
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[: target_t + 1], target_draw)

        # 3. Future leakage: history includes draws after target_draw (draws[:t+3])
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[: target_t + 3], target_draw)

        # 4. Non-contiguous history: missing t-1 (draws[:t-1])
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[: target_t - 1], target_draw)

        # 5. Non-contiguous history: not starting at draw_index 0 (draws[1:t])
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[1:target_t], target_draw)

        # 6. Non-contiguous history: interior gap
        gapped_history = [*draws[:5], *draws[6:target_t]]
        with pytest.raises(TemporalLeakageError):
            extract_features(gapped_history, target_draw)

        # 7. Chronological date violation: history[-1].draw_date >= target_draw.draw_date
        bad_target = CanonicalDrawRecord.from_prizes(
            station_code="XSHCM",
            draw_date=draws[target_t - 1].draw_date,
            draw_index=target_t,
            prizes_last2=target_draw.prizes_last2,
        )
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[:target_t], bad_target)

        # 8. Non-increasing draw_date inside history
        mutated_history = list(draws[:target_t])
        mutated_history[4] = CanonicalDrawRecord.from_prizes(
            station_code="XSHCM",
            draw_date=mutated_history[3].draw_date,
            draw_index=4,
            prizes_last2=mutated_history[4].prizes_last2,
        )
        with pytest.raises(TemporalLeakageError):
            extract_features(mutated_history, target_draw)

        # 9. Station mismatch between history and target_draw
        vl_target = CanonicalDrawRecord.from_prizes(
            station_code="XSVL",
            draw_date=target_draw.draw_date,
            draw_index=target_t,
            prizes_last2=target_draw.prizes_last2,
        )
        with pytest.raises(TemporalLeakageError):
            extract_features(draws[:target_t], vl_target)

    def test_features_future_invariance_under_future_mutation_and_shuffling(self) -> None:
        raw_draws = _generate_synthetic_raw_draws("XSHCM", 80, step_days=3)
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        t = 45

        baseline_bundle = extract_features(draws[:t], draws[t])

        # Mutate target_draw's prizes (intra-draw data) and completely alter/shuffle draws[t:]
        mutated_draws = list(draws)
        mutated_draws[t] = CanonicalDrawRecord.from_prizes(
            station_code="XSHCM",
            draw_date=draws[t].draw_date,
            draw_index=t,
            prizes_last2=["99"] * 18,
        )
        for fut_idx in range(t + 1, len(mutated_draws)):
            mutated_draws[fut_idx] = CanonicalDrawRecord.from_prizes(
                station_code="XSHCM",
                draw_date=draws[fut_idx].draw_date,
                draw_index=fut_idx,
                prizes_last2=[f"{(99 - g * 3 - fut_idx) % 100:02d}" for g in range(18)],
            )

        mutated_bundle = extract_features(mutated_draws[:t], mutated_draws[t])
        assert baseline_bundle == mutated_bundle
        assert baseline_bundle.tens_cage == mutated_bundle.tens_cage
        assert baseline_bundle.units_cage == mutated_bundle.units_cage
        assert baseline_bundle["tens_cage"] == mutated_bundle["tens"]
        assert baseline_bundle["units_cage"] == mutated_bundle["units"]

    def test_features_group1_group2_group3_exact_analytical_formulas(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        raw_draws = _generate_synthetic_raw_draws("XSHCM", 65, step_days=3)
        # Force draw 11 (t-1 when t=12) to have >= 3 hits on tens ball 8 via sample_valid_prizes_18
        raw_draws[11]["prizes_last2"] = list(sample_valid_prizes_18)
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")

        t = 12
        bundle = extract_features(draws[:t], draws[t])
        tens_feat = bundle.tens_cage
        units_feat = bundle.units_cage

        assert tens_feat.station_code == "XSHCM"
        assert tens_feat.cage_name == "tens_cage"
        assert tens_feat.target_draw_index == t
        assert tens_feat.history_length == t
        assert units_feat.cage_name == "units_cage"

        # Single-cage call via extract_features(..., cage=...) matches bundle
        assert extract_features(draws[:t], draws[t], cage="tens_cage") == tens_feat
        assert extract_features(draws[:t], draws[t], cage="units") == units_feat

        counts_mat = np.array([d.tens_counts for d in draws[:t]], dtype=np.int64)

        # Group 1: Regime counts and frequencies for windows (5, 10, 15, 30, 60)
        for w in REGIME_WINDOWS:
            eff_w = min(t, w)
            expected_counts = counts_mat[-eff_w:].sum(axis=0).tolist()
            expected_freqs = [c / (18.0 * eff_w) for c in expected_counts]
            assert tens_feat.regime_counts[w] == expected_counts
            assert np.allclose(tens_feat.regime_freqs[w], expected_freqs, atol=1e-12)
            assert math.isclose(sum(tens_feat.regime_freqs[w]), 1.0, abs_tol=1e-9)

        # Group 2: Zero-hit gaps, gap Z-scores, deficit_10 Z-scores, burst rebound
        for i in range(10):
            expected_gap = 0
            for tau in range(t - 1, -1, -1):
                if counts_mat[tau, i] == 0:
                    expected_gap += 1
                else:
                    break
            assert tens_feat.zero_hit_gaps[i] == expected_gap
            expected_z_gap = (expected_gap - GAP_MEAN_MU) / GAP_STD_SIGMA
            assert math.isclose(tens_feat.gap_z_scores[i], expected_z_gap, abs_tol=1e-12)

            expected_def10 = (18.0 - tens_feat.regime_counts[10][i]) / DEFICIT_10_STD
            assert math.isclose(tens_feat.deficit_10_z_scores[i], expected_def10, abs_tol=1e-12)
            assert math.isclose(tens_feat.deficit_z_scores[i], expected_def10, abs_tol=1e-12)

            expected_burst = 1 if counts_mat[t - 1, i] >= 3 else 0
            assert tens_feat.burst_rebound_indicators[i] == expected_burst
            assert tens_feat.burst_indicators_t_minus_1[i] == expected_burst
            assert 0.0 < tens_feat.burst_rebound_rates[i] < 1.0

        # In sample_valid_prizes_18, tens ball 8 has 5 hits (>= 3)
        assert tens_feat.burst_rebound_indicators[8] == 1

        # Group 3: Smoothed First-Order Markov Transition Matrix (10x10) & Session Split
        active_prev = (counts_mat[:-1] >= 2).astype(np.float64)  # tau = 0 .. t-2
        next_counts = counts_mat[1:].astype(np.float64)  # tau = 1 .. t-1
        trans_num = 1.0 + active_prev.T @ next_counts
        trans_den = 10.0 + 18.0 * active_prev.sum(axis=0, keepdims=True).T
        expected_markov = trans_num / trans_den

        markov_arr = np.array(tens_feat.markov_transition_matrix, dtype=np.float64)
        assert markov_arr.shape == (10, 10)
        assert np.allclose(markov_arr, expected_markov, atol=1e-12)
        for row_idx in range(10):
            row_sum = float(sum(tens_feat.markov_transition_matrix[row_idx]))
            assert abs(row_sum - 1.0) <= 1e-9

        # Session split at draw t-1 (sample_valid_prizes_18):
        # First 9 prizes: "42", "18", "73", "08", "83", "39", "88", "14", "57"
        # Tens ball 8 hits in first 9: "83", "88" (2 hits); total hits = 5 -> ratio = 2/5 = 0.4
        assert math.isclose(tens_feat.session_early_ratios[8], 2.0 / 5.0, abs_tol=1e-12)
        assert math.isclose(tens_feat.session_late_ratios[8], 3.0 / 5.0, abs_tol=1e-12)
        # Units ball 5 has 0 hits in sample_valid_prizes_18 -> neutral ratio = 0.5
        assert math.isclose(units_feat.session_early_ratios[5], 0.5, abs_tol=1e-12)

    def test_features_single_draw_history_t1_and_validation_edges(self) -> None:
        raw_draws = _generate_synthetic_raw_draws("XSVL", 5, step_days=7)
        draws = canonicalize_draws(raw_draws, station_code="XSVL")

        # t = 1: only 1 draw in history (no tau-1 -> tau transitions yet)
        bundle_t1 = extract_features(draws[:1], draws[1])
        assert list(bundle_t1.keys()) == ["tens_cage", "units_cage"]
        assert len(bundle_t1.values()) == 2
        assert len(bundle_t1.items()) == 2
        assert "tens_cage" in bundle_t1
        assert list(bundle_t1) == ["tens_cage", "units_cage"]
        # With 0 transitions, Laplace-smoothed Markov matrix has uniform rows [0.10, ..., 0.10]
        for row in bundle_t1.tens_cage.markov_transition_matrix:
            assert np.allclose(row, [0.10] * 10, atol=1e-12)
            assert abs(sum(row) - 1.0) <= 1e-9

        # Direct extract_cage_features without prizes_last2_history defaults early ratios to 0.5
        counts_only = [d.tens_counts for d in draws[:3]]
        cage_feat = extract_cage_features(counts_only, windows=(5, 15))
        assert cage_feat.history_length == 3
        assert cage_feat.session_early_ratios == [0.5] * 10
        assert cage_feat["zero_hit_gaps"] == cage_feat.zero_hit_gaps
        assert cage_feat.burst_rebound == cage_feat.burst_rebound_rates
        assert cage_feat.markov_matrix == cage_feat.markov_transition_matrix

        gate = PreDrawCutoffGate()
        gate.validate(draws[:2], draws[2])
        gate(draws[:2], draws[2])

        with pytest.raises(KeyError):
            _ = cage_feat["non_existent_key"]
        with pytest.raises(KeyError):
            _ = bundle_t1["non_existent_key"]

        # Invalid inputs to extract_cage_features and PreDrawCutoffGate
        with pytest.raises(TemporalLeakageError):
            enforce_pre_draw_cutoff(draws[:1], "not_a_draw")  # type: ignore[arg-type]

        with pytest.raises(TemporalLeakageError):
            enforce_pre_draw_cutoff(["not_a_draw"], draws[1])  # type: ignore[list-item]

        with pytest.raises(TemporalLeakageError):
            enforce_pre_draw_cutoff(draws[:1], draws[0])

        with pytest.raises(TemporalLeakageError):
            extract_cage_features([])

        with pytest.raises(DataIntegrityError):
            extract_cage_features("not_an_array")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            extract_cage_features([[1, 2, 3]])  # wrong shape (not 10 balls)

        with pytest.raises(DataIntegrityError):
            extract_cage_features([[1] * 10])  # row sum 10 != 18

        with pytest.raises(DataIntegrityError):
            extract_cage_features([[float("nan")] * 10])

        with pytest.raises(DataIntegrityError):
            extract_cage_features([[1.5, 2.5, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 1.0, 1.0]])

        with pytest.raises(DataIntegrityError):
            extract_cage_features([[-1, 19, 0, 0, 0, 0, 0, 0, 0, 0]])

        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_only, prizes_last2_history=[["42"]])

        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_only, cage_name="bad_cage")  # type: ignore[arg-type]

        with pytest.raises(DataIntegrityError):
            extract_features(draws[:2], draws[2], cage="invalid_cage")

    def test_features_direct_cage_cutoff_and_session_validation_and_last_counts(
        self,
        sample_valid_prizes_18: list[str],
    ) -> None:
        raw_draws = _generate_synthetic_raw_draws("XSHCM", 15, step_days=3)
        draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        counts_10 = [d.tens_counts for d in draws[:10]]
        prizes_10 = [d.prizes_last2 for d in draws[:10]]

        # SB-03: last_draw_counts is populated on CageFeatureVector and matches counts_history[-1]
        vec = extract_cage_features(counts_10, prizes_10)
        assert vec.last_draw_counts == draws[9].tens_counts
        bundle = extract_features(draws[:10], draws[10])
        assert bundle.tens_cage.last_draw_counts == draws[9].tens_counts
        assert bundle.units_cage.last_draw_counts == draws[9].units_counts

        # SA-02: target_draw_index < t or bool must raise TemporalLeakageError
        with pytest.raises(TemporalLeakageError):
            extract_cage_features(counts_10, target_draw_index=9)
        with pytest.raises(TemporalLeakageError):
            extract_cage_features(counts_10, target_draw_index=-1)
        with pytest.raises(TemporalLeakageError):
            extract_cage_features(counts_10, target_draw_index=True)

        # SA-02: invalid windows (empty, <= 0, bool) must raise DataIntegrityError
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, windows=())
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, windows=(0, 5))
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, windows=(-5, 10))
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, windows=(True, 5))  # type: ignore[arg-type]

        # SA-02: prizes_last2_history length or digit count mismatch raises DataIntegrityError
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, prizes_last2_history=prizes_10[:5])

        mismatched_prizes = [*prizes_10[:-1], ["99"] * 18]
        with pytest.raises(DataIntegrityError):
            extract_cage_features(counts_10, prizes_last2_history=mismatched_prizes)

        # In-place mutation of an earlier draw in history must be rejected by extract_features
        corrupted_draws = canonicalize_draws(raw_draws, station_code="XSHCM")
        corrupted_draws[0].prizes_last2[0] = (
            "99" if corrupted_draws[0].prizes_last2[0] != "99" else "00"
        )
        with pytest.raises(DataIntegrityError):
            extract_features(corrupted_draws[:10], corrupted_draws[10])
