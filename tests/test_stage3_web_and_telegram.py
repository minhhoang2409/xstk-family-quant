"""Stage 3 TDD Suite (Tasks 7 & 8): 5-Section Static Web Audit Publisher & 05:00 AM Telegram Bot."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from xsmn_alpha.constants import STAGE3_TICKET_CONFIGS
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.live.daily_analyst import (
    generate_daily_quant_report,
    rank_stations_for_day,
    score_station_for_date,
)
from xsmn_alpha.live.ledger import (
    build_capital_guidance,
    initialize_empty_ledger,
    record_pending_recommendation,
    settle_ledger_for_date,
)
from xsmn_alpha.live.telegram_bot import (
    TELEGRAM_MAX_MESSAGE_LENGTH,
    build_daily_report_url,
    dispatch_telegram_briefing,
    format_telegram_executive_briefing,
)
from xsmn_alpha.live.web_publisher import (
    publish_daily_web_report,
    render_daily_report_html,
    render_equity_curve_svg,
    render_index_dashboard_html,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerState,
    DailyQuantReportContract,
    DataPipelineAuditRecord,
)


def _build_synthetic_draws(
    station_code: str,
    num_draws: int = 68,
    end_date_before: str = "2026-10-24",
    *,
    tens_hot_ball: int = 2,
    units_hot_ball: int = 8,
    hot_count_per_draw: int = 6,
) -> list[dict[str, Any]]:
    """Build deterministic 18-prize draw history strictly before report_date (< D)."""
    base_dt = datetime.date.fromisoformat(end_date_before)
    draws: list[dict[str, Any]] = []
    for idx in range(num_draws):
        draw_dt = base_dt - datetime.timedelta(days=(num_draws - 1 - idx) * 7)
        hot_pair = f"{tens_hot_ball}{units_hot_ball}"
        alt_1 = f"{tens_hot_ball}{(units_hot_ball + 1) % 10}"
        alt_2 = f"{(tens_hot_ball + 1) % 10}{units_hot_ball}"
        prizes = [hot_pair] * hot_count_per_draw + [alt_1, alt_2]
        remaining = 18 - len(prizes)
        for k in range(remaining):
            d_tens = (idx + k) % 10
            d_units = (idx * 3 + k * 7) % 10
            prizes.append(f"{d_tens}{d_units}")
        draws.append(
            {
                "station_code": station_code,
                "draw_date": draw_dt.isoformat(),
                "prizes_last2": prizes,
            }
        )
    return draws


@pytest.fixture(scope="module")
def sample_report_and_ledger() -> tuple[DailyQuantReportContract, BenchmarkLedgerState]:
    """Create a realistic deterministic DailyQuantReportContract and BenchmarkLedgerState."""
    report_date = "2026-10-26"
    draws_hcm = _build_synthetic_draws(
        "XSHCM",
        num_draws=68,
        end_date_before="2026-10-24",
        tens_hot_ball=2,
        units_hot_ball=8,
        hot_count_per_draw=6,
    )
    sc_hcm = score_station_for_date(
        "XSHCM",
        target_date=report_date,
        history_draws=draws_hcm,
        null_sims=100,
        seed=42,
    )
    sc_dt = sc_hcm.model_copy(
        update={
            "station_code": "XSDT",
            "station_name": "Đồng Tháp",
            "region": "Miền Nam",
            "draw_time_ict": "16:15",
            "station_alpha_score": round(sc_hcm.station_alpha_score - 3.0, 2),
            "passes_selective_alpha": True,
            "strong_convergence": False,
        }
    )
    sc_cm = sc_hcm.model_copy(
        update={
            "station_code": "XSCM",
            "station_name": "Cà Mau",
            "region": "Miền Nam",
            "draw_time_ict": "16:15",
            "joint_r1_pct": 0.985,
            "best_oos_roi_pct": -4.20,
            "station_alpha_score": -2.55,
            "passes_selective_alpha": False,
            "strong_convergence": False,
        }
    )
    sc_tth = sc_hcm.model_copy(
        update={
            "station_code": "XSTTH",
            "station_name": "Thừa Thiên Huế",
            "region": "Miền Trung",
            "draw_time_ict": "17:15",
            "joint_r1_pct": 1.010,
            "best_oos_roi_pct": -1.80,
            "station_alpha_score": 0.55,
            "passes_selective_alpha": False,
            "strong_convergence": False,
        }
    )
    sc_py = sc_hcm.model_copy(
        update={
            "station_code": "XSPY",
            "station_name": "Phú Yên",
            "region": "Miền Trung",
            "draw_time_ict": "17:15",
            "joint_r1_pct": 0.960,
            "best_oos_roi_pct": -7.50,
            "station_alpha_score": -5.88,
            "passes_selective_alpha": False,
            "strong_convergence": False,
        }
    )

    # Build a settled ledger with 2 historical days so equity curve and yesterday settlement exist
    ledger = initialize_empty_ledger(updated_at="2026-10-24T05:00:00+07:00")
    ledger = record_pending_recommendation(
        ledger,
        draw_date="2026-10-24",
        verdict_tier="PLAY_STANDARD",
        chosen_station_code="XSHCM",
        chosen_config_id="2x2",
        selected_numbers=["28", "29", "38", "39"],
        updated_at="2026-10-24T05:00:00+07:00",
    )
    ledger = settle_ledger_for_date(
        ledger,
        draw_date="2026-10-24",
        actual_prizes_last2=["28", "38"] + ["00"] * 16,
        updated_at="2026-10-24T16:45:00+07:00",
    )
    ledger = record_pending_recommendation(
        ledger,
        draw_date="2026-10-25",
        verdict_tier="PLAY_PEAK",
        chosen_station_code="XSDL",
        chosen_config_id="1x4",
        selected_numbers=["21", "22", "23", "28"],
        updated_at="2026-10-25T05:00:00+07:00",
    )
    ledger = settle_ledger_for_date(
        ledger,
        draw_date="2026-10-25",
        actual_prizes_last2=["23", "28"] + ["11"] * 16,
        updated_at="2026-10-25T16:45:00+07:00",
    )

    ranked, primary, secondary, skipped, verdict_tier = rank_stations_for_day(
        [sc_hcm, sc_dt, sc_cm, sc_tth, sc_py]
    )
    cap_guidance = build_capital_guidance(
        verdict_tier,
        current_bankroll_vnd=ledger.current_bankroll_vnd,
        initial_bankroll_vnd=ledger.starting_bankroll_vnd,
    )
    from xsmn_alpha.live.daily_analyst import (
        build_executive_nlg_vi,
        build_yesterday_settlement_summary_vi,
    )

    yesterday_entry = ledger.entries[-1]
    yesterday_summary = build_yesterday_settlement_summary_vi(
        yesterday_entry,
        report_date=report_date,
    )
    nlg = build_executive_nlg_vi(
        report_date=report_date,
        weekday_vn="Thứ 2",
        verdict_tier=verdict_tier,
        primary_station=primary,
        secondary_station=secondary,
        skipped_stations=skipped,
        all_today_stations=ranked,
        capital_guidance=cap_guidance,
        yesterday_settlement=yesterday_entry,
    )
    audit = DataPipelineAuditRecord(
        audit_timestamp_ict="2026-10-26T05:00:00+07:00",
        target_date=report_date,
        total_stations_35=35,
        stations_synced_ok=35,
        fallback_used_count=1,
        schema_gate_passed=True,
        latest_settled_date="2026-10-25",
        notes_vi="Đã đồng bộ 35 đài chuẩn xác (1 đài dùng nguồn dự phòng xskt.com.vn).",
    )
    report = DailyQuantReportContract(
        report_date=report_date,
        weekday_vn="Thứ 2",
        generated_at_ict="2026-10-26T05:00:00+07:00",
        data_pipeline_audit=audit,
        yesterday_settlement=yesterday_entry,
        yesterday_summary_vi=yesterday_summary,
        verdict_tier=verdict_tier,
        should_play_today=(verdict_tier != "SKIP_NO_EDGE"),
        primary_station=primary,
        secondary_station=secondary,
        skipped_stations=skipped,
        all_today_stations=ranked,
        capital_guidance=cap_guidance,
        executive_nlg_vi=nlg,
    )
    return (report, ledger)


# ===========================================================================
# 1. Task 7 Tests: 5-Section Static Web Audit Publisher & Index Dashboard
# ===========================================================================


class TestTask7WebPublisherFiveSectionsAndDashboard:
    """Task 7 tests (`-k "web"`): 5-section daily HTML, JSON audit, index dashboard & XSS guard."""

    def test_web_render_daily_report_html_contains_all_5_mandatory_sections(
        self,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger
        html_doc = render_daily_report_html(
            report,
            ledger,
            public_report_base_url="https://xstk-family.pages.dev",
        )

        # Must be a complete self-contained Dark-Mode HTML5 document
        assert html_doc.startswith("<!DOCTYPE html>")
        assert '<html lang="vi">' in html_doc
        assert "<style>" in html_doc
        assert "@media" in html_doc

        # Section 1: Executive Verdict & 4 Core Questions + Yesterday's settlement
        assert 'id="section-1-executive-verdict"' in html_doc
        assert "Khu vực 1" in html_doc
        assert report.report_date in html_doc
        assert "2026-10-25" in html_doc
        assert "Câu hỏi 1" in html_doc
        assert "Câu hỏi 2" in html_doc
        assert "Câu hỏi 3" in html_doc
        assert "Câu hỏi 4" in html_doc

        # Section 2: Multi-Station Comparison Table (all 5 opening stations)
        assert 'id="section-2-station-comparison"' in html_doc
        assert "Khu vực 2" in html_doc
        for st in report.all_today_stations:
            assert st.station_code in html_doc
            assert st.station_name in html_doc
            assert st.region in html_doc
            assert st.draw_time_ict in html_doc
            assert f"{st.joint_r1_pct:.3f}%" in html_doc
            assert f"{st.station_alpha_score:+.2f}" in html_doc

        # Section 3: 10-Ball Probabilities (0-9), 10x10 Heatmap (00-99) & All 5 Ticket Configs
        assert 'id="section-3-probabilities-and-configs"' in html_doc
        assert "Khu vực 3" in html_doc
        assert "Lồng Hàng Chục" in html_doc
        assert "Lồng Hàng Đơn Vị" in html_doc
        # Verify 100 two-digit cells 00..99 exist in the 10x10 heatmap
        for num_int in range(100):
            assert f"{num_int:02d}" in html_doc
        assert "heatmap-recommended" in html_doc
        # Verify all 5 ticket configs are compared
        for cfg_id in STAGE3_TICKET_CONFIGS:
            assert cfg_id in html_doc

        # Section 4: CPPI / House-Money Capital Guidance & Sample VND Conversion Table
        assert 'id="section-4-capital-guidance"' in html_doc
        assert "Khu vực 4" in html_doc
        assert "500,000" in html_doc or "500.000" in html_doc
        assert "1,000,000" in html_doc or "1.000.000" in html_doc
        assert "2,000,000" in html_doc or "2.000.000" in html_doc
        assert "5,000,000" in html_doc or "5.000.000" in html_doc
        assert "Vốn 500k" in html_doc
        assert "Vốn 1 Triệu" in html_doc
        assert "Vốn 2 Triệu" in html_doc
        assert "Vốn 5 Triệu" in html_doc

        # Section 5: Data Pipeline Audit, SVG Equity Curve & Benchmark Ledger Statement
        assert 'id="section-5-pipeline-audit-and-ledger"' in html_doc
        assert "Khu vực 5" in html_doc
        assert "<svg" in html_doc and "</svg>" in html_doc
        assert ledger.sha256[:16] in html_doc
        assert "XSDL" in html_doc

    def test_web_publish_daily_web_report_writes_json_daily_html_and_index_dashboard(
        self,
        tmp_path: Path,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger
        public_dir = tmp_path / "public"

        paths = publish_daily_web_report(
            report,
            public_dir=public_dir,
            ledger_state_or_path=ledger,
            public_report_base_url="https://xstk-family.pages.dev",
        )

        assert paths["daily_json"] == public_dir / "daily" / "2026-10-26.json"
        assert paths["daily_html"] == public_dir / "daily" / "2026-10-26.html"
        assert paths["index_html"] == public_dir / "index.html"

        assert paths["daily_json"].exists()
        assert paths["daily_html"].exists()
        assert paths["index_html"].exists()

        # Validate written JSON matches DailyQuantReportContract
        loaded_json = json.loads(paths["daily_json"].read_text(encoding="utf-8"))
        validated_contract = DailyQuantReportContract.model_validate(loaded_json)
        assert validated_contract.report_date == "2026-10-26"
        assert validated_contract.telegram_message_html != ""

        # Validate index.html contains Benchmark Fund 1,000,000 VND KPIs, SVG curve, and daily links
        index_html = paths["index_html"].read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in index_html
        assert "<svg" in index_html and "</svg>" in index_html
        assert "daily/2026-10-26.html" in index_html
        assert "daily/2026-10-26.json" in index_html
        assert f"{ledger.current_bankroll_vnd:,}" in index_html

        # Also test standalone render_equity_curve_svg on empty ledger
        empty_svg = render_equity_curve_svg(initialize_empty_ledger())
        assert empty_svg.startswith("<svg") and empty_svg.endswith("</svg>")

    def test_web_negative_mutation_xss_injection_is_strictly_html_escaped(
        self,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger
        malicious_payload = '<script>alert(1)</script><img src=x onerror="alert(2)">'

        mutated_primary = report.primary_station.model_copy(
            update={
                "station_name": f"TP.HCM {malicious_payload}",
                "role_label_vi": f"Role {malicious_payload}",
                "rationale_vi": f"Rationale {malicious_payload}",
            }
        )
        mutated_nlg = report.executive_nlg_vi.model_copy(
            update={
                "yesterday_settlement_summary_vi": f"Yesterday {malicious_payload}",
                "q1_should_play_and_why": f"Q1 {malicious_payload}",
                "q2_which_station_and_region": f"Q2 {malicious_payload}",
                "q3_which_numbers_and_config": f"Q3 {malicious_payload}",
                "q4_how_to_allocate_capital": f"Q4 {malicious_payload}",
            }
        )
        mutated_audit = report.data_pipeline_audit.model_copy(
            update={"notes_vi": f"Audit {malicious_payload}"}
        )
        mutated_report = report.model_copy(
            update={
                "weekday_vn": f"Thứ 2 {malicious_payload}",
                "yesterday_summary_vi": f"Summary {malicious_payload}",
                "primary_station": mutated_primary,
                "all_today_stations": [mutated_primary, *report.all_today_stations[1:]],
                "executive_nlg_vi": mutated_nlg,
                "data_pipeline_audit": mutated_audit,
            }
        )

        daily_html = render_daily_report_html(mutated_report, ledger)
        index_html = render_index_dashboard_html([mutated_report], ledger)

        # Raw <script>alert(1)</script> must NEVER appear in rendered HTML
        assert "<script>alert(1)</script>" not in daily_html
        assert '<img src=x onerror="alert(2)">' not in daily_html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in daily_html

        assert "<script>alert(1)</script>" not in index_html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in index_html


# ===========================================================================
# 2. Task 8 Tests: 05:00 AM Telegram Executive Briefing & Bot Dispatcher
# ===========================================================================


class TestTask8TelegramExecutiveBriefingAndDispatcher:
    """Task 8 tests: Telegram HTML formatter (4 questions + link), dry-run & MockTransport."""

    def test_telegram_format_executive_briefing_contains_all_required_sections_and_link(
        self,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger
        base_url = "https://xstk-family.pages.dev"
        msg_html = format_telegram_executive_briefing(
            report,
            public_report_base_url=base_url,
        )

        # Length strictly <= 4096 UTF-8 chars and bytes
        assert len(msg_html) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert len(msg_html.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH

        # 1. Header
        assert "05:00 SÁNG" in msg_html
        assert "26/10/2026" in msg_html

        # 2. Câu hỏi 1 — Hôm nay có nên đánh không?
        assert "1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?" in msg_html
        assert "🟢" in msg_html
        assert "CÓ — HÔM NAY NÊN ĐÁNH" in msg_html

        # 3. Câu hỏi 2 — Nên đánh đài gì & Tổ hợp số?
        assert "2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?" in msg_html
        assert "Nên Đánh:" in msg_html
        assert report.primary_station.station_name in msg_html
        assert report.primary_station.station_code in msg_html
        assert report.primary_station.region in msg_html
        assert report.primary_station.draw_time_ict in msg_html
        assert "Bộ số nên đánh nhất" in msg_html
        assert report.primary_station.recommended_config_id in msg_html
        rec_nums_joined = ", ".join(report.primary_station.recommended_numbers)
        assert f"<b>{rec_nums_joined}</b>" in msg_html
        assert "Các bộ số tham khảo" in msg_html
        assert "3x3" in msg_html

        if report.secondary_station is not None:
            assert "Nên đánh thứ nhì là:" in msg_html
            assert report.secondary_station.station_name in msg_html
            assert report.secondary_station.station_code in msg_html
        for sk in report.skipped_stations:
            assert sk.station_code in msg_html

        # 4. Footer link <a href="{PUBLIC_REPORT_BASE_URL}/daily/{YYYY-MM-DD}.html">
        expected_url = build_daily_report_url(report.report_date, base_url=base_url)
        assert expected_url == "https://xstk-family.pages.dev/daily/2026-10-26.html"
        assert f'<a href="{expected_url}">' in msg_html

    def test_telegram_dispatch_dry_run_writes_preview_without_requiring_tokens(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, _ = sample_report_and_ledger
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        preview_file = tmp_path / "live" / "latest_telegram_preview.txt"
        result = dispatch_telegram_briefing(
            report,
            dry_run=True,
            preview_path=preview_file,
            public_report_base_url="https://xstk-family.pages.dev",
        )

        assert result["ok"] is True
        assert result["dry_run"] is True
        assert preview_file.exists()
        preview_content = preview_file.read_text(encoding="utf-8")
        assert preview_content == result["message_html"]
        assert "https://xstk-family.pages.dev/daily/2026-10-26.html" in preview_content

    def test_telegram_dispatch_live_sends_http_post_via_mock_transport(
        self,
        tmp_path: Path,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, _ = sample_report_and_ledger
        captured_requests: list[httpx.Request] = []

        def _mock_handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200,
                json={"ok": True, "result": {"message_id": 101}},
            )

        mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))
        preview_file = tmp_path / "live" / "latest_telegram_preview.txt"

        result = dispatch_telegram_briefing(
            report,
            dry_run=False,
            bot_token="123456:TEST_TOKEN",
            chat_id="-100987654321",
            preview_path=preview_file,
            public_report_base_url="https://xstk-family.pages.dev",
            client=mock_client,
        )

        assert result["ok"] is True
        assert result["dry_run"] is False
        assert len(captured_requests) == 1
        req = captured_requests[0]
        assert req.method == "POST"
        assert str(req.url) == "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"
        payload = json.loads(req.content.decode("utf-8"))
        assert payload["chat_id"] == "-100987654321"
        assert payload["parse_mode"] == "HTML"
        assert "https://xstk-family.pages.dev/daily/2026-10-26.html" in payload["text"]

    def test_telegram_negative_mutations_missing_token_api_failure_and_xss_escape(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, _ = sample_report_and_ledger
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        # Negative Mutation 1: Missing token/chat_id when dry_run=False raises DataIntegrityError
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                report,
                dry_run=False,
                bot_token="",
                chat_id="",
                preview_path=tmp_path / "preview.txt",
            )

        # Negative Mutation 2: Telegram API HTTP 400 or {"ok": False} raises DataIntegrityError
        fail_client_400 = httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    400,
                    json={"ok": False, "description": "Bad Request: can't parse entities"},
                )
            )
        )
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                report,
                dry_run=False,
                bot_token="123456:TEST_TOKEN",
                chat_id="-100987654321",
                preview_path=tmp_path / "preview.txt",
                client=fail_client_400,
            )

        fail_client_ok_false = httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={"ok": False, "description": "Bot was blocked"},
                )
            )
        )
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                report,
                dry_run=False,
                bot_token="123456:TEST_TOKEN",
                chat_id="-100987654321",
                preview_path=tmp_path / "preview.txt",
                client=fail_client_ok_false,
            )

        # Negative Mutation 3: Dynamic strings with <script>alert(1)</script> are HTML-escaped
        malicious_station = report.primary_station.model_copy(
            update={"station_name": "Vĩnh Long <script>alert(1)</script>"}
        )
        malicious_report = report.model_copy(
            update={
                "primary_station": malicious_station,
                "all_today_stations": [malicious_station, *report.all_today_stations[1:]],
            }
        )
        escaped_msg = format_telegram_executive_briefing(malicious_report)
        assert "<script>alert(1)</script>" not in escaped_msg
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in escaped_msg

        # Negative Mutation 4: Invalid non-http(s) base_url scheme rejected by DataIntegrityError
        with pytest.raises(DataIntegrityError):
            build_daily_report_url("2026-10-26", base_url="javascript:alert(1)")

        with pytest.raises(DataIntegrityError):
            build_daily_report_url("2026-10-26", base_url="https://bad<url>.example")

        # Negative Mutation 5: Raw string input to dispatch_telegram_briefing with <script> or empty
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing("", dry_run=True, preview_path=tmp_path / "preview.txt")
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                "<b>Hello</b><script>alert(1)</script>",
                dry_run=True,
                preview_path=tmp_path / "preview.txt",
            )
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                "A" * 5000,
                dry_run=True,
                preview_path=tmp_path / "preview.txt",
            )

        # Negative Mutation 6: Network error and non-JSON response raise DataIntegrityError
        net_err_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda req: (_ for _ in ()).throw(httpx.ConnectError("Network down"))
            )
        )
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                "<b>Valid Message</b>",
                dry_run=False,
                bot_token="123:TOK",
                chat_id="999",
                preview_path=tmp_path / "preview.txt",
                client=net_err_client,
            )

        bad_json_client = httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"not-json"))
        )
        with pytest.raises(DataIntegrityError):
            dispatch_telegram_briefing(
                "<b>Valid Message</b>",
                dry_run=False,
                bot_token="123:TOK",
                chat_id="999",
                preview_path=tmp_path / "preview.txt",
                client=bad_json_client,
            )

    def test_web_and_telegram_skip_no_edge_and_ledger_path_resolution(
        self,
        tmp_path: Path,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger
        from xsmn_alpha.live.ledger import save_benchmark_ledger

        ledger_file = tmp_path / "benchmark_ledger.json"
        save_benchmark_ledger(ledger, ledger_file)

        # Build a SKIP_NO_EDGE report with no secondary station and a SKIP yesterday entry
        skip_primary = report.primary_station.model_copy(
            update={
                "joint_r1_pct": 0.990,
                "best_oos_roi_pct": -3.50,
                "passes_selective_alpha": False,
                "strong_convergence": False,
                "bocd_changepoint_warning": True,
                "bocd_map_run_length": 2,
                "role_label_vi": "Đứng Ngoài / Nhiễu Trắng (0x)",
            }
        )
        skip_cap = build_capital_guidance(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=ledger.current_bankroll_vnd,
            initial_bankroll_vnd=ledger.starting_bankroll_vnd,
        )
        skip_report = report.model_copy(
            update={
                "verdict_tier": "SKIP_NO_EDGE",
                "should_play_today": False,
                "primary_station": skip_primary,
                "secondary_station": None,
                "skipped_stations": [skip_primary, *report.skipped_stations],
                "all_today_stations": [skip_primary, *report.skipped_stations],
                "capital_guidance": skip_cap,
                "yesterday_settlement": None,
                "telegram_message_html": "",
            }
        )

        tg_skip_html = format_telegram_executive_briefing(skip_report)
        assert "🔴" in tg_skip_html
        assert "SKIP_NO_EDGE" in tg_skip_html
        assert "Không đánh đài nào" in tg_skip_html
        assert "CHỈ QUAN SÁT" in tg_skip_html

        out_paths = publish_daily_web_report(
            skip_report,
            public_dir=tmp_path / "public_skip",
            ledger_state_or_path=ledger_file,
        )
        assert out_paths["daily_html"].exists()
        assert out_paths["index_html"].exists()

    def test_daily_analyst_populates_telegram_message_html_matching_formatter(
        self,
        tmp_path: Path,
    ) -> None:
        raw_dir = tmp_path / "raw_all"
        for code in ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY"):
            draws = _build_synthetic_draws(code, num_draws=65, end_date_before="2026-10-24")
            from xsmn_alpha.live.multi_fetcher import save_station_raw_cache

            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        generated = generate_daily_quant_report(
            "2026-10-26",
            raw_dir=raw_dir,
            null_sims=50,
        )
        assert generated.telegram_message_html != ""
        assert generated.telegram_message_html == format_telegram_executive_briefing(generated)


# ===========================================================================
# 3. Task 9 Tests: Unified Stage 2/3 CLI Commands & GitHub Actions Workflow
# ===========================================================================


class TestTask9Stage3CliAndGitOpsWorkflow:
    """Task 9 tests: CLI subcommands (sync-35, settle-ledger, daily-report) & GitOps workflow."""

    def test_cli_sync_35_settle_ledger_and_daily_report_end_to_end(
        self,
        tmp_path: Path,
    ) -> None:
        from xsmn_alpha.cli import build_parser, main
        from xsmn_alpha.live.multi_fetcher import save_station_raw_cache

        parser = build_parser()
        # Verify all 6 subcommands are registered in the unified CLI parser
        for subcmd in (
            ["ingest"],
            ["falsify"],
            ["run-pipeline"],
            ["sync-35", "--date", "2026-10-26"],
            ["settle-ledger", "--date", "2026-10-25"],
            ["daily-report", "--date", "2026-10-26", "--dry-run"],
        ):
            parsed = parser.parse_args(subcmd)
            assert parsed.command == subcmd[0]

        raw_dir = tmp_path / "raw_all"
        # Prepare Monday 2026-10-26 opening stations + Sunday 2026-10-25 station XSDL
        for code in ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY"):
            draws = _build_synthetic_draws(code, num_draws=65, end_date_before="2026-10-24")
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        draws_dl = _build_synthetic_draws("XSDL", num_draws=65, end_date_before="2026-10-18")
        draws_dl.append(
            {
                "station_code": "XSDL",
                "draw_date": "2026-10-25",
                "prizes_last2": ["21", "23"] + ["00"] * 16,
            }
        )
        save_station_raw_cache("XSDL", draws_dl, raw_dir=raw_dir)

        # 1. Test sync-35 CLI subcommand (--offline on prepared station subset)
        rc_sync = main(
            [
                "sync-35",
                "--date",
                "2026-10-26",
                "--raw-dir",
                str(raw_dir),
                "--stations",
                "XSHCM",
                "XSDT",
                "XSCM",
                "XSTTH",
                "XSPY",
                "XSDL",
                "--offline",
            ]
        )
        assert rc_sync == 0

        # 2. Seed a PENDING entry for 2026-10-25 and test settle-ledger CLI subcommand
        ledger_path = tmp_path / "live" / "benchmark_ledger.json"
        init_state = initialize_empty_ledger(updated_at="2026-10-25T05:00:00+07:00")
        pending_state = record_pending_recommendation(
            init_state,
            draw_date="2026-10-25",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSDL",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            ledger_path=ledger_path,
            updated_at="2026-10-25T05:00:00+07:00",
        )
        assert pending_state.entries[-1].settlement_status == "PENDING"

        rc_settle = main(
            [
                "settle-ledger",
                "--date",
                "2026-10-25",
                "--ledger",
                str(ledger_path),
                "--raw-dir",
                str(raw_dir),
            ]
        )
        assert rc_settle == 0

        from xsmn_alpha.live.ledger import load_benchmark_ledger

        settled_state = load_benchmark_ledger(ledger_path)
        assert settled_state.entries[-1].settlement_status == "SETTLED"
        assert settled_state.entries[-1].hit_count_k == 2

        # 3. Test daily-report CLI subcommand (--send-telegram --dry-run)
        public_dir = tmp_path / "public"
        preview_path = tmp_path / "live" / "latest_telegram_preview.txt"
        rc_report = main(
            [
                "daily-report",
                "--date",
                "2026-10-26",
                "--raw-dir",
                str(raw_dir),
                "--ledger",
                str(ledger_path),
                "--public-dir",
                str(public_dir),
                "--preview-path",
                str(preview_path),
                "--null-sims",
                "50",
                "--send-telegram",
                "--dry-run",
            ]
        )
        assert rc_report == 0
        assert (public_dir / "index.html").exists()
        assert (public_dir / "daily" / "2026-10-26.html").exists()
        assert (public_dir / "daily" / "2026-10-26.json").exists()
        assert preview_path.exists()

    def test_github_actions_workflow_yaml_configured_for_0500_ict(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "daily_quant_report.yml"
        )
        assert workflow_path.exists()
        content = workflow_path.read_text(encoding="utf-8")
        assert "47 20 * * *" in content
        assert "TELEGRAM_BOT_TOKEN" in content
        assert "TELEGRAM_CHAT_ID" in content
        assert "sync-35" in content
        assert "settle-ledger" in content
        assert "daily-report" in content
        assert "public" in content

    def test_cli_and_live_helpers_additional_edge_branches(
        self,
        tmp_path: Path,
    ) -> None:
        from xsmn_alpha.cli import main
        from xsmn_alpha.live.multi_fetcher import (
            canonicalize_station_draws,
            deduplicate_and_sort_station_draws,
            generate_station_expected_draw_dates,
            load_station_raw_cache,
            save_station_raw_cache,
            sync_station_draws,
        )
        from xsmn_alpha.live.registry import get_stations_for_date, get_weekday_vn_label

        # Registry edge branches
        assert len(get_stations_for_date(datetime.date(2026, 10, 26))) == 5
        assert len(get_stations_for_date("2026-10-26")) == 5
        with pytest.raises(DataIntegrityError):
            get_stations_for_date(12345)  # type: ignore[arg-type]
        assert get_weekday_vn_label(0) == "Thứ 2"
        assert get_weekday_vn_label(datetime.date(2026, 10, 26)) == "Thứ 2"
        assert get_weekday_vn_label("2026-10-26") == "Thứ 2"
        with pytest.raises(DataIntegrityError):
            get_weekday_vn_label(True)
        with pytest.raises(DataIntegrityError):
            get_weekday_vn_label(9)
        with pytest.raises(DataIntegrityError):
            get_weekday_vn_label(None)  # type: ignore[arg-type]

        # Multi-fetcher edge branches
        with pytest.raises(DataIntegrityError):
            deduplicate_and_sort_station_draws([], "XSHCM")
        with pytest.raises(DataIntegrityError):
            canonicalize_station_draws([], "XSHCM")
        with pytest.raises(DataIntegrityError):
            generate_station_expected_draw_dates("XSHCM", 0)
        with pytest.raises(DataIntegrityError):
            load_station_raw_cache("XSHCM", raw_dir=tmp_path / "missing_dir")

        raw_dir = tmp_path / "raw_edge"
        for code in ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY"):
            draws = _build_synthetic_draws(code, num_draws=65, end_date_before="2026-10-24")
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        canon_recs = canonicalize_station_draws(
            load_station_raw_cache("XSHCM", raw_dir=raw_dir),
            "XSHCM",
        )
        deduped = deduplicate_and_sort_station_draws(canon_recs, "XSHCM")
        assert len(deduped) == 65
        recs_again = canonicalize_station_draws(canon_recs, "XSHCM")
        assert len(recs_again) == 65

        synced_recs, fb = sync_station_draws(
            "XSHCM",
            target_date="2026-10-24",
            raw_dir=raw_dir,
            offline=True,
        )
        assert len(synced_recs) == 65 and fb == 0

        # CLI daily-report when ledger file does not exist yet + re-run when already settled
        fresh_ledger = tmp_path / "live_fresh" / "benchmark_ledger.json"
        public_dir = tmp_path / "public_fresh"
        rc1 = main(
            [
                "daily-report",
                "--date",
                "2026-10-26",
                "--raw-dir",
                str(raw_dir),
                "--ledger",
                str(fresh_ledger),
                "--public-dir",
                str(public_dir),
                "--base-url",
                "https://xstk-family.pages.dev",
                "--null-sims",
                "40",
            ]
        )
        assert rc1 == 0
        assert fresh_ledger.exists()


class TestSliceCAdversarialMutationsAndReconciliation:
    """Adversarial regression & mutation tests for Slice C findings (C-01 through C-07)."""

    def test_c01_telegram_briefing_contains_all_spec_5_5_a_quantitative_blocks(
        self,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, _ = sample_report_and_ledger
        tg_clean = format_telegram_executive_briefing(report)
        assert len(tg_clean.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH
        assert "1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?" in tg_clean
        assert "2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?" in tg_clean

        tg_html = format_telegram_executive_briefing(report, include_extended_audit=True)
        assert len(tg_html.encode("utf-8")) <= TELEGRAM_MAX_MESSAGE_LENGTH

        # D-1 Settlement summary + bankroll W & house money C
        assert "Đối soát Hôm qua (D-1)" in tg_html
        assert "2026-10-25" in tg_html
        assert f"{report.capital_guidance.benchmark_bankroll_vnd:,}" in tg_html
        assert f"{report.capital_guidance.house_money_surplus_vnd:,}" in tg_html

        # Section 1 quantitative proof metrics
        assert "1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?" in tg_html
        assert "1.105%" in tg_html
        assert "10.69%" in tg_html
        assert "Chi2_max" in tg_html
        assert "BF10" in tg_html
        assert "BOCD r*" in tg_html
        assert "OOS ROI" in tg_html

        # Section 2 AlphaScore, Top 2 cage balls, and all reference configs including Hybrid
        assert "2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?" in tg_html
        assert "AlphaScore" in tg_html
        assert "Lồng Chục Top 2" in tg_html
        assert "Lồng Đơn Vị Top 2" in tg_html
        assert "3x3" in tg_html
        assert "core_2x2_sat_3x3" in tg_html
        assert "Hybrid" in tg_html

        # Section 3 capital sizing multiplier & 4-tier Sample VND Conversion table
        assert "3. ĐI VỐN NHƯ THẾ NÀO (QUỸ CHUẨN 1 TRIỆU)?" in tg_html
        assert f"{report.capital_guidance.recommended_multiplier:.2f}x" in tg_html
        for tier_lbl in ("Vốn 500k", "Vốn 1 Triệu", "Vốn 2 Triệu", "Vốn 5 Triệu"):
            assert tier_lbl in tg_html

    def test_c02_c05_github_actions_workflow_schedule_separation_and_input_hardening(
        self,
    ) -> None:
        import re

        wf_path = (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "daily_quant_report.yml"
        )
        wf_text = wf_path.read_text(encoding="utf-8")

        # Must bind inputs via env: and never interpolate ${{ github.event.inputs.* }} in run:
        assert "INPUT_REPORT_DATE: ${{ github.event.inputs.report_date }}" in wf_text
        assert "INPUT_DRY_RUN: ${{ github.event.inputs.dry_run }}" in wf_text
        assert "EVENT_SCHEDULE: ${{ github.event.schedule }}" in wf_text
        assert "grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'" in wf_text

        run_blocks = wf_text.split("run: |")[1:]
        for block in run_blocks:
            step_body = block.split("\n      - name:")[0]
            assert not re.findall(r"\$\{\{\s*github\.event\.inputs\.[^}]+\}\}", step_body)

        # Must never swallow settle-ledger errors with || true
        assert "|| true" not in wf_text

        # Must distinguish 35 10 * * * (17:35 ICT) vs morning run
        assert "github.event.schedule != '35 10 * * *'" in wf_text
        assert "github.event.schedule == '35 10 * * *'" in wf_text

    def test_c03_c07_web_roi_attribution_and_ui_visual_polish(
        self,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger

        # 1. Mutate primary station so recommended config ROI differs from best_oos_roi_pct
        tc_2x2 = report.primary_station.ticket_configs["2x2"].model_copy(
            update={"oos_roi_3y_pct": 1.25}
        )
        tc_1x4 = report.primary_station.ticket_configs["1x4"].model_copy(
            update={"oos_roi_3y_pct": 6.80}
        )
        mut_configs = dict(report.primary_station.ticket_configs)
        mut_configs["2x2"] = tc_2x2
        mut_configs["1x4"] = tc_1x4
        mut_primary = report.primary_station.model_copy(
            update={
                "recommended_config_id": "2x2",
                "recommended_numbers": list(tc_2x2.selected_numbers),
                "best_oos_roi_pct": 6.80,
                "ticket_configs": mut_configs,
            }
        )
        # Also test yesterday 0 hits banner ("Không trúng giải nào") and failed DataSchemaGate
        zero_hit_yesterday = report.yesterday_settlement.model_copy(
            update={
                "actual_prizes_last2": ["99"] * 18,
                "hit_count_k": 0,
                "hit_details": [],
                "revenue_vnd": 0,
                "net_profit_vnd": -report.yesterday_settlement.cost_vnd,
                "bankroll_after_vnd": (
                    report.yesterday_settlement.bankroll_before_vnd
                    - report.yesterday_settlement.cost_vnd
                ),
                "house_money_after_vnd": max(
                    0,
                    report.yesterday_settlement.bankroll_before_vnd
                    - report.yesterday_settlement.cost_vnd
                    - 1_000_000,
                ),
            }
        )
        failed_audit = report.data_pipeline_audit.model_copy(
            update={"stations_synced_ok": 5, "schema_gate_passed": False}
        )
        mut_report = report.model_copy(
            update={
                "primary_station": mut_primary,
                "all_today_stations": [mut_primary, *report.all_today_stations[1:]],
                "yesterday_settlement": zero_hit_yesterday,
                "data_pipeline_audit": failed_audit,
            }
        )
        html_doc = render_daily_report_html(mut_report, ledger)
        assert "ROI (2x2): +1.25%" in html_doc
        assert "Best 5-cfg: +6.80%" in html_doc
        assert "<strong>0 nháy</strong> (Không trúng giải nào)" in html_doc
        assert "<strong>0 nháy</strong> (0 nháy)" not in html_doc
        assert 'style="color: var(--red);">FAIL (5/35 Đài)' in html_doc

        # 2. On SKIP_NO_EDGE, KPI Box 3 must use muted style & "Bộ số quan sát (Không cược"
        skip_primary = mut_primary.model_copy(
            update={
                "joint_r1_pct": 0.980,
                "best_oos_roi_pct": -2.50,
                "passes_selective_alpha": False,
                "strong_convergence": False,
            }
        )
        skip_cap = build_capital_guidance(
            "SKIP_NO_EDGE",
            current_bankroll_vnd=ledger.current_bankroll_vnd,
            initial_bankroll_vnd=ledger.starting_bankroll_vnd,
        )
        skip_report = mut_report.model_copy(
            update={
                "verdict_tier": "SKIP_NO_EDGE",
                "should_play_today": False,
                "primary_station": skip_primary,
                "secondary_station": None,
                "skipped_stations": [skip_primary, *report.skipped_stations],
                "all_today_stations": [skip_primary, *report.skipped_stations],
                "capital_guidance": skip_cap,
            }
        )
        skip_html = render_daily_report_html(skip_report, ledger)
        assert "Bộ số quan sát (Không cược" in skip_html
        assert "Bộ Số Tối Ưu" not in skip_html

    def test_c04_cli_verifies_raw_dir_station_count_and_propagates_capital_discipline_error(
        self,
        tmp_path: Path,
    ) -> None:
        import argparse
        from unittest.mock import patch

        from xsmn_alpha.cli import run_daily_report_cmd
        from xsmn_alpha.exceptions import CapitalDisciplineError
        from xsmn_alpha.live.ledger import save_benchmark_ledger
        from xsmn_alpha.live.multi_fetcher import save_station_raw_cache

        raw_dir = tmp_path / "raw_5_only"
        for code in ("XSHCM", "XSDT", "XSCM", "XSTTH", "XSPY"):
            draws = _build_synthetic_draws(code, num_draws=65, end_date_before="2026-10-24")
            save_station_raw_cache(code, draws, raw_dir=raw_dir)

        ledger = initialize_empty_ledger(updated_at="2026-10-25T05:00:00+07:00")
        ledger = record_pending_recommendation(
            ledger,
            draw_date="2026-10-25",
            verdict_tier="PLAY_STANDARD",
            chosen_station_code="XSDL",
            chosen_config_id="1x4",
            selected_numbers=["21", "22", "23", "28"],
            updated_at="2026-10-25T05:00:00+07:00",
        )
        ledger_path = tmp_path / "benchmark_ledger.json"
        save_benchmark_ledger(ledger, ledger_path)

        args = argparse.Namespace(
            date="2026-10-26",
            raw_dir=str(raw_dir),
            ledger=str(ledger_path),
            public_dir=str(tmp_path / "public"),
            preview_path=str(tmp_path / "preview.txt"),
            base_url=None,
            null_sims=20,
            seed=42,
            dry_run=True,
            send_telegram=False,
        )

        # 1. CapitalDisciplineError during auto-settle must NEVER be swallowed
        with (
            patch(
                "xsmn_alpha.cli.settle_ledger_for_date",
                side_effect=CapitalDisciplineError("Gate 5 breach"),
            ),
            pytest.raises(CapitalDisciplineError, match="Gate 5 breach"),
        ):
            run_daily_report_cmd(args)

        # 2. With only 5/35 station files in raw_dir, audit reports 5/35 (not fabricated 35)
        rc = run_daily_report_cmd(args)
        assert rc == 0
        gen_report = DailyQuantReportContract.model_validate_json(
            (tmp_path / "public" / "daily" / "2026-10-26.json").read_text(encoding="utf-8")
        )
        assert gen_report.data_pipeline_audit.stations_synced_ok == 5
        assert gen_report.data_pipeline_audit.total_stations_35 == 35
        assert gen_report.data_pipeline_audit.schema_gate_passed is True

        # 3. Any corrupted station cache file in raw_dir fails closed with DataIntegrityError
        (raw_dir / "XSAG_draws.json").write_text('{"corrupt": true}', encoding="utf-8")
        with pytest.raises(DataIntegrityError):
            run_daily_report_cmd(args)

    def test_c06_web_publisher_and_telegram_reject_corrupt_json_and_unsafe_html_tags(
        self,
        tmp_path: Path,
        sample_report_and_ledger: tuple[DailyQuantReportContract, BenchmarkLedgerState],
    ) -> None:
        report, ledger = sample_report_and_ledger

        # 1. dispatch_telegram_briefing rejects <img onerror=...>, <svg onload=...>, javascript:
        for unsafe_str in (
            '<b>Alert</b> <img src=x onerror="alert(1)">',
            "<b>Alert</b> <svg onload=alert(1)>",
            '<b>Alert</b> <a href="javascript:alert(1)">Click</a>',
            "<b>Alert</b> <iframe src='https://evil.example'></iframe>",
        ):
            with pytest.raises(DataIntegrityError):
                dispatch_telegram_briefing(
                    unsafe_str,
                    dry_run=True,
                    preview_path=tmp_path / "unsafe_preview.txt",
                )

        # 2. render_index_dashboard_html rejects path traversal report_date or invalid verdict_tier
        with pytest.raises(DataIntegrityError):
            render_index_dashboard_html(
                [{"report_date": "../evil", "verdict_tier": "SKIP_NO_EDGE"}],
                ledger,
            )
        with pytest.raises(DataIntegrityError):
            render_index_dashboard_html(
                [{"report_date": "2026-10-26", "verdict_tier": "FAKE_TIER"}],
                ledger,
            )

        # 3. publish_daily_web_report raises DataIntegrityError on unvalidated/corrupt daily/*.json
        bad_public_dir = tmp_path / "bad_public"
        bad_daily_dir = bad_public_dir / "daily"
        bad_daily_dir.mkdir(parents=True)
        (bad_daily_dir / "2026-10-20.json").write_text(
            json.dumps({"report_date": "../evil", "verdict_tier": "FAKE"}),
            encoding="utf-8",
        )
        with pytest.raises(DataIntegrityError):
            publish_daily_web_report(report, public_dir=bad_public_dir, ledger_state_or_path=ledger)
