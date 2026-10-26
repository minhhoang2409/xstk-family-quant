"""Stage 3 Pillar 5: 05:00 AM Telegram Executive Briefing Formatter & Bot API Dispatcher."""

from __future__ import annotations

import datetime
import html
import os
from pathlib import Path
from typing import Any, Final

import httpx

from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.schemas import (
    DailyQuantReportContract,
    DailyVerdictTier,
    StationDailyScorecard,
    validate_iso_date,
)

DEFAULT_PUBLIC_REPORT_BASE_URL: Final[str] = "https://xstk-family.pages.dev"
DEFAULT_TELEGRAM_PREVIEW_PATH: Final[Path] = Path("data/live/latest_telegram_preview.txt")
TELEGRAM_MAX_MESSAGE_LENGTH: Final[int] = 4096
TELEGRAM_API_BASE_URL: Final[str] = "https://api.telegram.org"


def _esc(value: Any) -> str:
    """Safely escape any dynamic value for HTML / Telegram HTML output."""
    return html.escape(str(value), quote=True)


def _format_dd_mm_yyyy(iso_date: str) -> str:
    """Convert YYYY-MM-DD into DD/MM/YYYY."""
    cleaned = validate_iso_date(iso_date)
    dt = datetime.date.fromisoformat(cleaned)
    return dt.strftime("%d/%m/%Y")


def resolve_public_report_base_url(base_url: str | None = None) -> str:
    """Resolve and validate the base URL for published static Web daily reports."""
    raw = (
        base_url
        if base_url is not None
        else os.environ.get("PUBLIC_REPORT_BASE_URL", DEFAULT_PUBLIC_REPORT_BASE_URL)
    )
    cleaned = str(raw).strip().rstrip("/")
    if not cleaned:
        cleaned = DEFAULT_PUBLIC_REPORT_BASE_URL
    if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
        raise DataIntegrityError(
            f"Invalid public_report_base_url {cleaned!r}; must start with 'https://' or 'http://'."
        )
    if any(ch in cleaned for ch in ('"', "'", "<", ">")) or any(ch.isspace() for ch in cleaned):
        raise DataIntegrityError(
            f"Invalid unsafe characters in public_report_base_url {cleaned!r}."
        )
    return cleaned


def build_daily_report_url(
    report_date: str,
    *,
    base_url: str | None = None,
) -> str:
    """Construct the full canonical URL to the daily static HTML report."""
    iso_date = validate_iso_date(report_date)
    resolved_base = resolve_public_report_base_url(base_url)
    return f"{resolved_base}/daily/{iso_date}.html"


def _format_verdict_banner(verdict_tier: DailyVerdictTier) -> str:
    """Return the concise yes/no Telegram HTML banner for a DailyVerdictTier."""
    banners: dict[DailyVerdictTier, str] = {
        "PLAY_PEAK": "🟢 <b>CÓ — HÔM NAY NÊN ĐÁNH (Tín hiệu rất đẹp / PLAY_PEAK)</b>",
        "PLAY_STANDARD": "🟢 <b>CÓ — HÔM NAY NÊN ĐÁNH (Đạt chuẩn / PLAY_STANDARD)</b>",
        "PLAY_CAUTIOUS": "🟡 <b>CÓ — HÔM NAY ĐÁNH NHẸ THẬN TRỌNG (PLAY_CAUTIOUS)</b>",
        "SKIP_NO_EDGE": "🔴 <b>KHÔNG NÊN ĐÁNH — HÔM NAY NGHỈ (SKIP_NO_EDGE)</b>",
    }
    return banners[verdict_tier]


def _format_station_pick_block(
    st: StationDailyScorecard,
    *,
    heading_prefix: str,
    compact_refs: bool = False,
    include_extended_audit: bool = False,
) -> str:
    """Format a station pick block with its best number set and reference sets."""
    rec_id = st.recommended_config_id
    rec_cfg = st.ticket_configs[rec_id]
    rec_nums_str = ", ".join(_esc(n) for n in st.recommended_numbers)

    if not include_extended_audit:
        ref_lines_clean: list[str] = []
        for alt_id in ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3"):
            if alt_id == rec_id or alt_id not in st.ticket_configs:
                continue
            alt_cfg = st.ticket_configs[alt_id]
            alt_nums = ", ".join(_esc(n) for n in alt_cfg.selected_numbers)
            ref_lines_clean.append(
                f"  • Bộ <code>{_esc(alt_id)}</code> ({alt_cfg.num_numbers} số, "
                f"ROI {alt_cfg.oos_roi_3y_pct:+.2f}%): <code>{alt_nums}</code>"
            )
        refs_joined = "\n".join(ref_lines_clean)
        return (
            f"{heading_prefix} <b>{_esc(st.station_name)} - {_esc(st.region)}</b> "
            f"({_esc(st.station_code)} — Quay {_esc(st.draw_time_ict)}) với:\n"
            f"+ <b>Bộ số nên đánh nhất ({_esc(rec_id)} - {rec_cfg.num_numbers} số, "
            f"ROI {rec_cfg.oos_roi_3y_pct:+.2f}%):</b> "
            f"<b>{rec_nums_str}</b>\n"
            f"+ <b>Các bộ số tham khảo:</b>\n"
            f"{refs_joined}"
        )

    t_top2 = ", ".join(
        f"bóng {b} ({st.p_ai_tens[b] * 100.0:.2f}%)" for b in st.ranked_balls_tens[:2]
    )
    u_top2 = ", ".join(
        f"bóng {b} ({st.p_ai_units[b] * 100.0:.2f}%)" for b in st.ranked_balls_units[:2]
    )

    if compact_refs:
        compact_parts: list[str] = []
        for alt_id in ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3"):
            if alt_id == rec_id or alt_id not in st.ticket_configs:
                continue
            alt_cfg = st.ticket_configs[alt_id]
            alt_nums = ", ".join(_esc(n) for n in alt_cfg.selected_numbers)
            lbl = f"{alt_id} (Hybrid)" if alt_id == "core_2x2_sat_3x3" else alt_id
            compact_parts.append(f"<code>{_esc(lbl)}</code>: {alt_nums}")
        refs_section = f"+ <b>Các bộ số tham khảo:</b> {' | '.join(compact_parts)}"
    else:
        ref_lines: list[str] = []
        for alt_id in ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3"):
            if alt_id == rec_id or alt_id not in st.ticket_configs:
                continue
            alt_cfg = st.ticket_configs[alt_id]
            alt_nums = ", ".join(_esc(n) for n in alt_cfg.selected_numbers)
            if alt_id == "core_2x2_sat_3x3":
                ref_lines.append(
                    f"  • Bộ <code>{_esc(alt_id)}</code> (Hybrid {alt_cfg.num_numbers} số, "
                    f"ROI {alt_cfg.oos_roi_3y_pct:+.2f}%): <code>{alt_nums}</code>"
                )
            else:
                ref_lines.append(
                    f"  • Bộ <code>{_esc(alt_id)}</code> ({alt_cfg.num_numbers} số, "
                    f"ROI {alt_cfg.oos_roi_3y_pct:+.2f}%): <code>{alt_nums}</code>"
                )
        refs_section = "+ <b>Các bộ số tham khảo:</b>\n" + "\n".join(ref_lines)

    return (
        f"{heading_prefix} <b>{_esc(st.station_name)} - {_esc(st.region)}</b> "
        f"({_esc(st.station_code)} — Quay {_esc(st.draw_time_ict)}, "
        f"AlphaScore = <b>{st.station_alpha_score:+.2f}</b>) với:\n"
        f"+ <b>Cầu bóng dẫn đầu:</b> Lồng Chục Top 2: {t_top2} | Lồng Đơn Vị Top 2: {u_top2}\n"
        f"+ <b>Bộ số nên đánh nhất ({_esc(rec_id)} - {rec_cfg.num_numbers} số, "
        f"ROI {rec_cfg.oos_roi_3y_pct:+.2f}%):</b> "
        f"<b>{rec_nums_str}</b>\n"
        f"{refs_section}"
    )


def format_telegram_executive_briefing(
    report: DailyQuantReportContract,
    *,
    public_report_base_url: str | None = None,
    include_extended_audit: bool = False,
) -> str:
    """Format the focused 05:00 AM Telegram HTML briefing for the family (<= 4096 UTF-8 chars).

    By default (`include_extended_audit=False`), formats the concise 3-part family layout:
      1. Hôm nay có nên đánh không? (Có / Không nên; bằng chứng chi tiết xem trên Web)
      2. Nên đánh đài gì & Tổ hợp số? (Đài số 1 + Bộ số nên đánh nhất + Bộ tham khảo;
         Đài thứ nhì nếu có; các đài còn lại nghỉ)
      3. Link mở Trang Web Báo Cáo Giải Trình Chi Tiết (bằng chứng, nguyên nhân & bảng vốn)
    """
    if not isinstance(report, DailyQuantReportContract):
        raise DataIntegrityError(f"Expected DailyQuantReportContract, got {type(report).__name__}.")

    dd_mm_yyyy = _format_dd_mm_yyyy(report.report_date)
    report_url = build_daily_report_url(report.report_date, base_url=public_report_base_url)
    p = report.primary_station
    cg = report.capital_guidance
    rec_cfg = p.ticket_configs[p.recommended_config_id]

    skipped_str = (
        ", ".join(
            f"{_esc(sk.station_name)} ({_esc(sk.station_code)})" for sk in report.skipped_stations
        )
        if report.skipped_stations
        else "Không có"
    )

    if not include_extended_audit:
        header_block = (
            f"<b>📡 BẢN TIN 05:00 SÁNG — {_esc(report.weekday_vn.upper())} "
            f"({dd_mm_yyyy})</b>\n"
            f"────────────"
        )
        q1_block = (
            f"<b>1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?</b>\n"
            f"👉 {_format_verdict_banner(report.verdict_tier)}\n"
            f"<i>(Bằng chứng toán học &amp; lý do chi tiết xem trên trang Web bên dưới)</i>"
        )
        if report.should_play_today:
            primary_block = _format_station_pick_block(
                p,
                heading_prefix="🏆 <b>Nên Đánh:</b>",
                include_extended_audit=False,
            )
            sec = report.secondary_station
            if sec is not None:
                secondary_block = "\n\n" + _format_station_pick_block(
                    sec,
                    heading_prefix="🥈 <b>Nên đánh thứ nhì là:</b>",
                    include_extended_audit=False,
                )
            else:
                secondary_block = "\n\n• <b>Đài thứ nhì:</b> Không có đài thứ 2 đạt chuẩn hôm nay."
            q2_block = (
                f"<b>2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?</b>\n"
                f"{primary_block}"
                f"{secondary_block}\n"
                f"• <i>Các đài còn lại không đánh: {skipped_str}.</i>"
            )
        else:
            rec_nums_str = ", ".join(_esc(n) for n in p.recommended_numbers)
            q2_block = (
                f"<b>2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?</b>\n"
                f"• <b>Không đánh đài nào hôm nay (CHỈ QUAN SÁT).</b>\n"
                f"• <i>Đài quan sát tham khảo ({_esc(p.station_name)} - {_esc(p.region)}, "
                f"{_esc(p.station_code)}):</i> Bộ <code>{_esc(p.recommended_config_id)}</code>: "
                f"<b>{rec_nums_str}</b>\n"
                f"• <i>Các đài nghỉ hôm nay: {skipped_str}.</i>"
            )
        footer_block = (
            f"────────────\n"
            f"💡 <i>Bằng chứng giải trình nguyên nhân, kết quả đối soát và bảng đi vốn "
            f"xem tại trang Web:</i>\n"
            f'🔗 <a href="{_esc(report_url)}">Xem Trang Web Giải Trình Chi Tiết '
            f"Ngày {dd_mm_yyyy} ({_esc(report.report_date)})</a>"
        )
        full_message = "\n\n".join([header_block, q1_block, q2_block, footer_block])
        if len(full_message.encode("utf-8")) > TELEGRAM_MAX_MESSAGE_LENGTH:
            raise DataIntegrityError(
                f"Formatted Telegram message exceeds {TELEGRAM_MAX_MESSAGE_LENGTH} UTF-8 bytes."
            )
        return full_message

    ys = report.yesterday_settlement
    if ys is not None and ys.settlement_status == "SETTLED":
        ys_brief = (
            f"Ngày {_esc(ys.draw_date)} ({_esc(ys.chosen_station_code)}, "
            f"{_esc(ys.chosen_config_id)}): K={ys.hit_count_k} nháy, "
            f"Lãi/Lỗ <b>{ys.net_profit_vnd:+,}đ</b>"
        )
    else:
        ys_brief = _esc(report.yesterday_summary_vi)

    header_block = (
        f"<b>📡 BẢN TIN 05:00 SÁNG — {_esc(report.weekday_vn.upper())} "
        f"({dd_mm_yyyy})</b>\n"
        f"📌 <b>Đối soát Hôm qua (D-1):</b> {ys_brief} "
        f"(Quỹ <code>W_D-1</code>: <b>{cg.benchmark_bankroll_vnd:,}đ</b> | "
        f"Lãi <code>C_D-1</code>: <b>{cg.house_money_surplus_vnd:,}đ</b>)\n"
        f"────────────"
    )

    # 1. Hôm nay có nên đánh không?
    bocd_warn_txt = " ⚠️(Đổi chế độ)" if p.bocd_changepoint_warning else ""
    null_bounds = f"P90=<code>{p.null_chi2_p90:.2f}</code>/P95=<code>{p.null_chi2_p95:.2f}</code>"
    q1_block = (
        f"<b>1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?</b>\n"
        f"👉 {_format_verdict_banner(report.verdict_tier)}\n"
        f"• <b>Bằng chứng định lượng (&lt; {_esc(report.report_date)}):</b> "
        f"JointR1 = <b>{p.joint_r1_pct:.3f}%</b> (vs chuẩn <code>1.105%</code>) | "
        f"Lồng Chục R1 = <b>{p.oos_rank1_freq_tens_pct:.2f}%</b> &amp; "
        f"Đơn Vị R1 = <b>{p.oos_rank1_freq_units_pct:.2f}%</b> (vs hòa vốn <code>10.69%</code>)\n"
        f"• <b>Kiểm định &amp; OOS 3Y:</b> "
        f"Chi2_max = <b>{p.chi2_max_overall:.2f}</b> (vs Null {null_bounds}) | "
        f"BF10 = <b>{p.bf10_max_overall:.2f}</b> | "
        f"BOCD r* = <b>{p.bocd_map_run_length} kỳ</b>{bocd_warn_txt} | "
        f"OOS ROI (<code>{_esc(p.recommended_config_id)}</code>) = "
        f"<b>{rec_cfg.oos_roi_3y_pct:+.2f}%</b> (Best = <b>{p.best_oos_roi_pct:+.2f}%</b>)"
    )

    # 2. Nên đánh đài gì + Tổ hợp?
    skipped_str = (
        ", ".join(
            f"{_esc(sk.station_name)} ({_esc(sk.station_code)})" for sk in report.skipped_stations
        )
        if report.skipped_stations
        else "Không có"
    )

    if report.should_play_today:
        primary_block = _format_station_pick_block(
            p,
            heading_prefix="🏆 <b>Nên Đánh:</b>",
            compact_refs=False,
            include_extended_audit=True,
        )
        sec = report.secondary_station
        if sec is not None:
            secondary_block = "\n\n" + _format_station_pick_block(
                sec,
                heading_prefix="🥈 <b>Nên đánh thứ nhì là:</b>",
                compact_refs=True,
                include_extended_audit=True,
            )
        else:
            secondary_block = "\n\n• <b>Đài thứ nhì:</b> Không có đài thứ 2 đạt chuẩn hôm nay."

        q2_block = (
            f"<b>2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?</b>\n"
            f"{primary_block}"
            f"{secondary_block}\n"
            f"• <i>Các đài còn lại không đánh: {skipped_str}.</i>"
        )
    else:
        t_top2 = ", ".join(
            f"bóng {b} ({p.p_ai_tens[b] * 100.0:.2f}%)" for b in p.ranked_balls_tens[:2]
        )
        u_top2 = ", ".join(
            f"bóng {b} ({p.p_ai_units[b] * 100.0:.2f}%)" for b in p.ranked_balls_units[:2]
        )
        rec_nums_str = ", ".join(_esc(n) for n in p.recommended_numbers)
        skip_refs: list[str] = []
        for alt_id in ("2x2", "1x4", "4x1", "3x3", "core_2x2_sat_3x3"):
            if alt_id not in p.ticket_configs:
                continue
            alt_cfg = p.ticket_configs[alt_id]
            lbl = f"{alt_id} (Hybrid)" if alt_id == "core_2x2_sat_3x3" else alt_id
            skip_refs.append(
                f"<code>{_esc(lbl)}</code>: {', '.join(_esc(n) for n in alt_cfg.selected_numbers)}"
            )
        q2_block = (
            f"<b>2. NÊN ĐÁNH ĐÀI GÌ &amp; TỔ HỢP SỐ?</b>\n"
            f"• <b>Không đánh đài nào hôm nay (CHỈ QUAN SÁT).</b>\n"
            f"• <i>Đài quan sát tham khảo ({_esc(p.station_name)} - {_esc(p.region)}, "
            f"{_esc(p.station_code)}, AlphaScore = {p.station_alpha_score:+.2f}):</i> "
            f"Bộ <code>{_esc(p.recommended_config_id)}</code>: "
            f"<b>{rec_nums_str}</b>\n"
            f"• <i>Cầu bóng quan sát:</i> Lồng Chục Top 2: {t_top2} | Lồng Đơn Vị Top 2: {u_top2}\n"
            f"• <i>Các bộ số tham khảo:</i> {' | '.join(skip_refs)}\n"
            f"• <i>Các đài nghỉ hôm nay: {skipped_str}.</i>"
        )

    # 3. Đi vốn như thế nào (Quỹ Chuẩn 1 Triệu)?
    short_mult = (
        f"{cg.recommended_multiplier:.1f}x"
        if cg.recommended_multiplier in (0.0, 1.0, 1.5)
        else f"{cg.recommended_multiplier:.2f}x"
    )
    tier_lines: list[str] = []
    for row in cg.sample_allocations:
        lbl = row.tier_label if row.tier_label.startswith("Vốn") else f"Vốn {row.tier_label}"
        tier_lines.append(
            f"  • <b>{_esc(lbl)}:</b> <code>{row.stake_per_number_vnd:,}đ/số</code> "
            f"→ Tổng <b>{row.total_daily_cost_vnd:,}đ/ngày</b> "
            f"(1 nháy thu <code>{row.payout_per_hit_vnd:,}đ</code>, "
            f"lãi <code>{row.net_profit_1hit_vnd:+,}đ</code>)"
        )
    tiers_joined = "\n".join(tier_lines)
    q3_block = (
        f"<b>3. ĐI VỐN NHƯ THẾ NÀO (QUỸ CHUẨN 1 TRIỆU)?</b>\n"
        f"• <b>Hệ số đi vốn CPPI / House-Money:</b> <b>{cg.recommended_multiplier:.2f}x</b> "
        f"(<code>{short_mult}</code>) — Cược chuẩn: <b>{cg.benchmark_bet_vnd:,} VNĐ/ngày</b> "
        f"(Quỹ W = <code>{cg.benchmark_bankroll_vnd:,}đ</code>, "
        f"Đệm lãi C = <code>{cg.house_money_surplus_vnd:,}đ</code>)\n"
        f"• <b>Bảng quy đổi tiền cược mẫu (4 mức vốn):</b>\n"
        f"{tiers_joined}"
    )

    # 4. Footer link to Web Report (for proof, why win/lose, and capital table)
    footer_block = (
        f"────────────\n"
        f"💡 <i>Bằng chứng giải trình nguyên nhân, kết quả đối soát và bảng đi vốn "
        f"xem tại trang Web:</i>\n"
        f'🔗 <a href="{_esc(report_url)}">Xem Trang Web Giải Trình Chi Tiết '
        f"Ngày {dd_mm_yyyy} ({_esc(report.report_date)})</a>"
    )

    full_message = "\n\n".join(
        [
            header_block,
            q1_block,
            q2_block,
            q3_block,
            footer_block,
        ]
    )

    if len(full_message.encode("utf-8")) > TELEGRAM_MAX_MESSAGE_LENGTH:
        raise DataIntegrityError(
            f"Formatted Telegram message exceeds {TELEGRAM_MAX_MESSAGE_LENGTH} UTF-8 bytes "
            f"({len(full_message.encode('utf-8'))} bytes)."
        )

    return full_message


def dispatch_telegram_briefing(
    report_or_html: DailyQuantReportContract | str,
    *,
    dry_run: bool = False,
    bot_token: str | None = None,
    chat_id: str | None = None,
    public_report_base_url: str | None = None,
    preview_path: str | Path = DEFAULT_TELEGRAM_PREVIEW_PATH,
    client: httpx.Client | None = None,
    timeout_sec: float = 15.0,
) -> dict[str, Any]:
    """Dispatch the 05:00 AM Telegram executive briefing (or write local preview in dry-run).

    Args:
      report_or_html: DailyQuantReportContract or pre-rendered Telegram HTML string.
      dry_run: When True, writes preview_path and succeeds without requiring Bot Token/Chat ID.
      bot_token: Optional Telegram Bot token (falls back to TELEGRAM_BOT_TOKEN env var).
      chat_id: Optional Telegram Chat ID (falls back to TELEGRAM_CHAT_ID env var).
      public_report_base_url: Optional base URL for the daily web report link.
      preview_path: Path to write `latest_telegram_preview.txt`.
      client: Optional `httpx.Client` (e.g., `httpx.MockTransport` for deterministic tests).
      timeout_sec: HTTP timeout in seconds when creating an internal client.
    """
    if isinstance(report_or_html, DailyQuantReportContract):
        message_html = format_telegram_executive_briefing(
            report_or_html,
            public_report_base_url=public_report_base_url,
        )
    elif isinstance(report_or_html, str):
        if not report_or_html.strip():
            raise DataIntegrityError("Telegram message_html cannot be empty.")
        lower_html = report_or_html.lower()
        forbidden_tokens = (
            "<script",
            "<img",
            "<svg",
            "<iframe",
            "<object",
            "<embed",
            "onerror=",
            "onload=",
            "onclick=",
            "javascript:",
        )
        for tok in forbidden_tokens:
            if tok in lower_html:
                raise DataIntegrityError(
                    f"Forbidden unsafe HTML token {tok!r} in Telegram HTML message."
                )
        if len(report_or_html.encode("utf-8")) > TELEGRAM_MAX_MESSAGE_LENGTH:
            raise DataIntegrityError(
                f"Telegram message exceeds {TELEGRAM_MAX_MESSAGE_LENGTH} UTF-8 bytes."
            )
        message_html = report_or_html
    else:
        raise DataIntegrityError(
            f"report_or_html must be DailyQuantReportContract or str, "
            f"got {type(report_or_html).__name__}."
        )

    resolved_preview = Path(preview_path)
    resolved_preview.parent.mkdir(parents=True, exist_ok=True)
    resolved_preview.write_text(message_html, encoding="utf-8")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "preview_path": str(resolved_preview),
            "message_html": message_html,
            "char_length": len(message_html),
            "utf8_byte_length": len(message_html.encode("utf-8")),
        }

    resolved_token = (
        bot_token if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
    ).strip()
    resolved_chat_id = (
        chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")
    ).strip()

    if not resolved_token or not resolved_chat_id:
        raise DataIntegrityError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID when dry_run=False. "
            "Configure environment variables or pass --dry-run."
        )

    api_url = f"{TELEGRAM_API_BASE_URL}/bot{resolved_token}/sendMessage"
    payload = {
        "chat_id": resolved_chat_id,
        "text": message_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    def _post_with_client(http_client: httpx.Client) -> dict[str, Any]:
        try:
            response = http_client.post(api_url, json=payload)
        except httpx.HTTPError as exc:
            raise DataIntegrityError(f"Telegram API network error: {exc}") from exc

        if response.status_code != 200:
            raise DataIntegrityError(
                f"Telegram API returned non-200 status ({response.status_code}): {response.text}"
            )
        try:
            body = response.json()
        except Exception as exc:
            raise DataIntegrityError(f"Telegram API returned invalid JSON: {exc}") from exc

        if not isinstance(body, dict) or not body.get("ok", False):
            raise DataIntegrityError(f"Telegram API rejected message: {body!r}")
        return body

    if client is not None:
        tg_resp = _post_with_client(client)
    else:
        with httpx.Client(timeout=timeout_sec) as new_client:
            tg_resp = _post_with_client(new_client)

    return {
        "ok": True,
        "dry_run": False,
        "preview_path": str(resolved_preview),
        "message_html": message_html,
        "char_length": len(message_html),
        "utf8_byte_length": len(message_html.encode("utf-8")),
        "telegram_response": tg_resp,
    }


send_telegram_briefing = dispatch_telegram_briefing
