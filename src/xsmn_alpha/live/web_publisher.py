"""Stage 3 Pillar 4: Self-Contained 5-Section Static HTML Audit Report & Index Dashboard."""

from __future__ import annotations

import datetime
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from xsmn_alpha.constants import (
    BE_PROB_SINGLE_BALL,
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    HOUSE_MONEY_MAX_SURPLUS_FRACTION,
    HOUSE_MONEY_MIN_BUFFER_DAYS,
    SELECTIVE_ALPHA_JOINT_R1_MIN_PCT,
    STAGE3_TICKET_CONFIGS,
)
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.live.ledger import (
    DEFAULT_LEDGER_PATH,
    initialize_empty_ledger,
    load_benchmark_ledger,
)
from xsmn_alpha.live.telegram_bot import (
    format_telegram_executive_briefing,
    resolve_public_report_base_url,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerState,
    DailyQuantReportContract,
    DailyVerdictTier,
    validate_iso_date,
)

DEFAULT_PUBLIC_DIR: Final[Path] = Path("public")


def _esc(val: Any) -> str:
    """Safely HTML-escape any dynamic value to prevent XSS / broken markup."""
    return html.escape(str(val), quote=True)


def _fmt_dd_mm_yyyy(iso_date: str) -> str:
    """Format YYYY-MM-DD as DD/MM/YYYY."""
    try:
        return datetime.date.fromisoformat(iso_date).strftime("%d/%m/%Y")
    except ValueError:
        return _esc(iso_date)


def _verdict_badge_html(verdict_tier: DailyVerdictTier) -> str:
    """Return a styled HTML badge for a DailyVerdictTier."""
    mapping: dict[DailyVerdictTier, tuple[str, str]] = {
        "PLAY_PEAK": ("badge-green", "🟢 NÊN ĐÁNH — TÍN HIỆU HỘI TỤ ĐỈNH (PLAY_PEAK)"),
        "PLAY_STANDARD": ("badge-green", "🟢 NÊN ĐÁNH — ĐẠT CHUẨN LỢI THẾ ALPHA (PLAY_STANDARD)"),
        "PLAY_CAUTIOUS": ("badge-amber", "🟡 ĐÁNH THẬN TRỌNG — LỢI THẾ DƯƠNG NHẸ (PLAY_CAUTIOUS)"),
        "SKIP_NO_EDGE": ("badge-red", "🔴 HÔM NAY NGHỈ — BẢO TOÀN VỐN (SKIP_NO_EDGE / 0.0x)"),
    }
    css_cls, text = mapping[verdict_tier]
    return f'<span class="badge {css_cls}">{_esc(text)}</span>'


_SHARED_DARK_MODE_CSS: Final[str] = """
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --card-alt: #131c2e;
      --border: #334155;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --green: #22c55e;
      --amber: #f59e0b;
      --red: #ef4444;
      --purple: #c084fc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px 16px 72px;
      font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
      font-size: 15.5px;
    }
    .container { max-width: 1240px; margin: 0 auto; }
    .hero {
      background: linear-gradient(135deg, #1e293b 0%, #0b1324 100%);
      border: 2px solid var(--accent);
      border-radius: 14px;
      padding: 24px 26px;
      margin-bottom: 24px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    }
    h1 { font-size: 1.65rem; margin: 8px 0 10px; color: #ffffff; line-height: 1.3; }
    h2 {
      font-size: 1.32rem;
      margin-top: 32px;
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 2px solid var(--border);
      color: var(--accent);
    }
    h3 { font-size: 1.08rem; margin-top: 16px; margin-bottom: 8px; color: #ffffff; }
    .subtitle { color: #cbd5e1; font-size: 0.98rem; margin: 0; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px 22px;
      margin-bottom: 20px;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
    }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    @media (max-width: 960px) {
      .grid-2 { grid-template-columns: 1fr; }
      .grid-4 { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 600px) {
      body { padding: 14px 10px 48px; font-size: 14.5px; }
      .grid-4 { grid-template-columns: 1fr; }
      h1 { font-size: 1.35rem; }
    }
    .kpi-box {
      background: var(--card-alt);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
    }
    .kpi-label { font-size: 0.82rem; color: var(--muted); text-transform: uppercase; }
    .kpi-value { font-size: 1.28rem; font-weight: 700; color: #ffffff; margin-top: 4px; }
    .callout {
      border-left: 4px solid var(--accent);
      background: var(--card-alt);
      padding: 13px 16px;
      border-radius: 0 8px 8px 0;
      margin: 12px 0;
    }
    .callout.good { border-left-color: var(--green); background: rgba(34, 197, 94, 0.09); }
    .callout.warn { border-left-color: var(--amber); background: rgba(245, 158, 11, 0.09); }
    .callout.bad  { border-left-color: var(--red); background: rgba(239, 68, 68, 0.09); }
    .table-wrap { width: 100%; overflow-x: auto; margin: 12px 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.91rem;
      background: var(--card);
    }
    th, td {
      border: 1px solid var(--border);
      padding: 9px 11px;
      text-align: center;
      vertical-align: middle;
    }
    th { background: #0b1324; color: #e2e8f0; font-weight: 700; }
    td.left, th.left { text-align: left; }
    .badge {
      display: inline-block;
      padding: 4px 11px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 700;
    }
    .badge-green {
      background: rgba(34, 197, 94, 0.2);
      color: #4ade80;
      border: 1px solid #22c55e;
    }
    .badge-amber {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border: 1px solid #f59e0b;
    }
    .badge-red {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid #ef4444;
    }
    .badge-blue {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      border: 1px solid #0284c7;
    }
    .pos { color: #4ade80; font-weight: 700; }
    .neg { color: #f87171; font-weight: 700; }
    .prob-bar-bg {
      width: 100%;
      height: 8px;
      background: #0b1324;
      border-radius: 4px;
      overflow: hidden;
      margin-top: 4px;
    }
    .prob-bar-fill { height: 100%; background: var(--accent); border-radius: 4px; }
    .heatmap-cell {
      padding: 6px 4px;
      font-size: 0.82rem;
      border: 1px solid #263349;
      background: #131c2e;
    }
    .heatmap-recommended {
      background: rgba(34, 197, 94, 0.28) !important;
      border: 2px solid #22c55e !important;
      color: #ffffff;
      font-weight: 700;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    code {
      background: #0b1324;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: Consolas, Monaco, monospace;
      color: #38bdf8;
    }
"""


def render_equity_curve_svg(
    ledger_state: BenchmarkLedgerState | None,
    *,
    width: int = 920,
    height: int = 280,
) -> str:
    """Render a self-contained SVG equity curve for the 1,000,000 VND Benchmark Fund."""
    state = ledger_state if ledger_state is not None else initialize_empty_ledger()
    w0 = state.starting_bankroll_vnd
    settled_entries = [e for e in state.entries if e.settlement_status == "SETTLED"]

    points_data: list[tuple[str, int]] = [("Khởi tạo", w0)]
    for entry in settled_entries:
        points_data.append((entry.draw_date, entry.bankroll_after_vnd))

    vals = [v for _, v in points_data]
    min_v = min(min(vals), w0)
    max_v = max(max(vals), w0)
    span = max(max_v - min_v, 100_000)
    y_min = max(0, min_v - int(span * 0.15))
    y_max = max_v + int(span * 0.15)
    y_range = max(y_max - y_min, 1)

    pad_left = 88
    pad_right = 32
    pad_top = 28
    pad_bottom = 42
    plot_w = max(width - pad_left - pad_right, 200)
    plot_h = max(height - pad_top - pad_bottom, 100)

    def _x_coord(idx: int, total: int) -> float:
        if total <= 1:
            return float(pad_left + plot_w / 2.0)
        return float(pad_left + (idx / float(total - 1)) * plot_w)

    def _y_coord(val: int) -> float:
        ratio = (val - y_min) / float(y_range)
        return float(pad_top + plot_h - ratio * plot_h)

    n_pts = len(points_data)
    coords = [(_x_coord(i, n_pts), _y_coord(v)) for i, (_, v) in enumerate(points_data)]
    polyline_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    baseline_y = _y_coord(w0)

    if len(coords) >= 2:
        area_pts = (
            f"{coords[0][0]:.1f},{pad_top + plot_h:.1f} "
            + polyline_pts
            + f" {coords[-1][0]:.1f},{pad_top + plot_h:.1f}"
        )
    else:
        cx, cy = coords[0]
        area_pts = (
            f"{pad_left},{pad_top + plot_h} {cx:.1f},{cy:.1f} "
            f"{pad_left + plot_w},{pad_top + plot_h}"
        )

    last_label, last_val = points_data[-1]
    last_x, last_y = coords[-1]

    circles_svg = "\n".join(
        f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#22c55e" '
        f'stroke="#0f172a" stroke-width="1.5">'
        f"<title>{_esc(points_data[idx][0])}: {points_data[idx][1]:,} VNĐ</title></circle>"
        for idx, (x, y) in enumerate(coords)
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Biểu đồ Đường cong Vốn Quỹ Chuẩn 1.000.000 VNĐ">\n'
        f'  <rect x="0" y="0" width="{width}" height="{height}" rx="10" fill="#0b1324" '
        f'stroke="#334155" stroke-width="1" />\n'
        f'  <line x1="{pad_left}" y1="{baseline_y:.1f}" x2="{pad_left + plot_w}" '
        f'y2="{baseline_y:.1f}" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="6,4" />\n'
        f'  <text x="{pad_left - 8}" y="{baseline_y + 4:.1f}" fill="#fbbf24" '
        f'font-size="11" text-anchor="end">W0 {w0:,}đ</text>\n'
        f'  <polygon points="{area_pts}" fill="rgba(34, 197, 94, 0.14)" />\n'
        f'  <polyline fill="none" stroke="#22c55e" stroke-width="2.6" points="{polyline_pts}" />\n'
        f"{circles_svg}\n"
        f'  <text x="{last_x:.1f}" y="{max(pad_top + 12, last_y - 10):.1f}" '
        f'fill="#4ade80" font-size="12" font-weight="bold" text-anchor="end">'
        f"{_esc(last_label)}: {last_val:,} VNĐ</text>\n"
        f"</svg>"
    )


def render_daily_report_html(
    report: DailyQuantReportContract,
    ledger_state: BenchmarkLedgerState | None = None,
    *,
    public_report_base_url: str | None = None,
) -> str:
    """Render the self-contained 5-Section Dark-Mode HTML daily quantitative audit report."""
    if not isinstance(report, DailyQuantReportContract):
        raise DataIntegrityError(f"Expected DailyQuantReportContract, got {type(report).__name__}.")

    resolved_base_url = resolve_public_report_base_url(public_report_base_url)
    state = (
        ledger_state
        if ledger_state is not None
        else initialize_empty_ledger(updated_at=report.generated_at_ict)
    )

    p = report.primary_station
    cg = report.capital_guidance
    nlg = report.executive_nlg_vi
    audit = report.data_pipeline_audit
    dd_mm_yyyy = _fmt_dd_mm_yyyy(report.report_date)
    be_pct = BE_PROB_SINGLE_BALL * 100.0

    # -------------------------------------------------------------------------
    # Khu vực 1: Executive Verdict, 4 Core Questions & Yesterday Settlement
    # -------------------------------------------------------------------------
    y_entry = report.yesterday_settlement
    if y_entry is not None and y_entry.settlement_status == "SETTLED":
        y_hits_str = (
            ", ".join(f"{_esc(h.number)} ({_esc(h.prize_label)})" for h in y_entry.hit_details)
            if y_entry.hit_details
            else "Không trúng giải nào"
        )
        net_cls_y = "pos" if y_entry.net_profit_vnd >= 0 else "neg"
        yesterday_detail_html = (
            f"<p><strong>Chi tiết đối soát ngày {_esc(y_entry.draw_date)} "
            f"({_esc(y_entry.weekday_vn)}):</strong> "
            f"Đài <code>{_esc(y_entry.chosen_station_name)} "
            f"({_esc(y_entry.chosen_station_code)})</code> | "
            f"Cấu hình <code>{_esc(y_entry.chosen_config_id)}</code> "
            f"(Số: <code>{_esc(', '.join(y_entry.selected_numbers))}</code>) | "
            f"Hệ số <code>{y_entry.recommended_multiplier:.2f}x</code> | "
            f"Kết quả: <strong>{y_entry.hit_count_k or 0} nháy</strong> ({y_hits_str}) | "
            f"Chi: <code>{y_entry.cost_vnd:,} VNĐ</code> | "
            f"Thu: <code>{y_entry.revenue_vnd:,} VNĐ</code> | "
            f'Lãi/Lỗ ròng: <strong class="{net_cls_y}">'
            f"{y_entry.net_profit_vnd:+,} VNĐ</strong> | "
            f"Số dư Quỹ Chuẩn W: <strong>{y_entry.bankroll_after_vnd:,} VNĐ</strong> "
            f"(Quỹ Lãi Ròng C: <strong>{y_entry.house_money_after_vnd:,} VNĐ</strong>).</p>"
        )
    else:
        yesterday_detail_html = ""

    verdict_badge = _verdict_badge_html(report.verdict_tier)
    rec_nums_joined = _esc(", ".join(p.recommended_numbers))
    q1_callout_cls = "good" if report.should_play_today else "bad"
    rec_cfg_roi = p.ticket_configs[p.recommended_config_id].oos_roi_3y_pct
    if abs(p.best_oos_roi_pct - rec_cfg_roi) > 1e-6:
        kpi3_roi_text = (
            f"ROI ({_esc(p.recommended_config_id)}): {rec_cfg_roi:+.2f}% • "
            f"Best 5-cfg: {p.best_oos_roi_pct:+.2f}%"
        )
    else:
        kpi3_roi_text = f"ROI ({_esc(p.recommended_config_id)}): {rec_cfg_roi:+.2f}%"

    if report.should_play_today:
        kpi3_label = f"Bộ Số Tối Ưu ({_esc(p.recommended_config_id)})"
        kpi3_val_style = "color: var(--green);"
    else:
        kpi3_label = f"Bộ số quan sát (Không cược - {_esc(p.recommended_config_id)}):"
        kpi3_val_style = "color:var(--muted);"

    section1_html = (
        '  <section id="section-1-executive-verdict" class="card">\n'
        "    <h2>Khu vực 1 — Tóm tắt Quyết định Chiến thuật 05:00 Sáng "
        "&amp; Giải trình Toán học</h2>\n"
        '    <div class="grid-4" style="margin-bottom: 16px;">\n'
        '      <div class="kpi-box">\n'
        f'        <div class="kpi-label">Phán Quyết Ngày {_esc(report.report_date)}</div>\n'
        f'        <div class="kpi-value" style="font-size: 1.02rem;">{verdict_badge}</div>\n'
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Đài Ưu Tiên Số 1</div>\n'
        f'        <div class="kpi-value">{_esc(p.station_name)} ({_esc(p.station_code)})</div>\n'
        f'        <div style="font-size: 0.85rem; color: var(--muted);">'
        f"{_esc(p.region)} • Quay {_esc(p.draw_time_ict)} ICT</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        f'        <div class="kpi-label">{kpi3_label}</div>\n'
        f'        <div class="kpi-value" style="{kpi3_val_style}">{rec_nums_joined}</div>\n'
        f'        <div style="font-size: 0.85rem; color: var(--muted);">'
        f"JointR1 = {p.joint_r1_pct:.3f}% • {kpi3_roi_text}</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Hệ Số Vốn CPPI / House-Money</div>\n'
        f'        <div class="kpi-value">{cg.recommended_multiplier:.2f}x '
        f"({cg.benchmark_bet_vnd:,} VNĐ)</div>\n"
        f'        <div style="font-size: 0.85rem; color: var(--muted);">'
        f"Số dư W = {cg.benchmark_bankroll_vnd:,}đ • "
        f"Lãi C = {cg.house_money_surplus_vnd:,}đ</div>\n"
        "      </div>\n"
        "    </div>\n"
        '    <div class="callout warn">\n'
        "      <strong>📌 Đối soát kết quả ngày hôm qua (D - 1):</strong> "
        f"{_esc(report.yesterday_summary_vi)}\n"
        f"      {yesterday_detail_html}\n"
        "    </div>\n"
        '    <div class="grid-2">\n'
        f'      <div class="callout {q1_callout_cls}">\n'
        "        <h3>Câu hỏi 1 — Hôm nay có nên đánh không? Vì sao?</h3>\n"
        f"        <p>{_esc(nlg.q1_should_play_and_why)}</p>\n"
        "      </div>\n"
        '      <div class="callout">\n'
        "        <h3>Câu hỏi 2 — Nên đánh đài gì? Khu vực nào?</h3>\n"
        f"        <p>{_esc(nlg.q2_which_station_and_region)}</p>\n"
        "      </div>\n"
        '      <div class="callout good">\n'
        "        <h3>Câu hỏi 3 — Với đài nên đánh nhất thì đánh bộ số nào?</h3>\n"
        f"        <p>{_esc(nlg.q3_which_numbers_and_config)}</p>\n"
        "      </div>\n"
        '      <div class="callout warn">\n'
        "        <h3>Câu hỏi 4 — Đi vốn như thế nào?</h3>\n"
        f"        <p>{_esc(nlg.q4_how_to_allocate_capital)}</p>\n"
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
    )

    # -------------------------------------------------------------------------
    # Khu vực 2: Multi-Station Comparison Table (5-7 Opening Stations)
    # -------------------------------------------------------------------------
    station_rows_html: list[str] = []
    for st in report.all_today_stations:
        bocd_badge = (
            f'<span class="badge badge-red">⚠️ r*={st.bocd_map_run_length} (Thay bóng)</span>'
            if st.bocd_changepoint_warning
            else f'<span class="badge badge-blue">r*={st.bocd_map_run_length} kỳ</span>'
        )
        verdict_cls = "badge-green" if st.passes_selective_alpha else "badge-red"
        st_rec_roi = st.ticket_configs[st.recommended_config_id].oos_roi_3y_pct
        st_rec_cls = "pos" if st_rec_roi > 0 else "neg"
        if abs(st.best_oos_roi_pct - st_rec_roi) > 1e-6:
            best_cls = "pos" if st.best_oos_roi_pct > 0 else "neg"
            st_roi_html = (
                f'<span class="{st_rec_cls}">ROI ({_esc(st.recommended_config_id)}): '
                f"{st_rec_roi:+.2f}%</span><br/>"
                f'<small class="{best_cls}">Best 5-cfg: {st.best_oos_roi_pct:+.2f}%</small>'
            )
        else:
            st_roi_html = (
                f'<span class="{st_rec_cls}">ROI ({_esc(st.recommended_config_id)}): '
                f"{st_rec_roi:+.2f}%</span>"
            )
        station_rows_html.append(
            f"<tr>"
            f"<td><strong>#{st.rank_in_day}</strong></td>"
            f'<td class="left"><strong>{_esc(st.station_name)}</strong> '
            f"(<code>{_esc(st.station_code)}</code>)</td>"
            f"<td>{_esc(st.region)}<br/><small>{_esc(st.draw_time_ict)} ICT</small></td>"
            f"<td>{st.sample_draws_3y} kỳ<br/>"
            f"<small>(&lt; {_esc(st.last_draw_date_before_d)})</small></td>"
            f"<td><strong>{st.chi2_max_overall:.2f}</strong><br/>"
            f"<small>P90={st.null_chi2_p90:.2f} / P95={st.null_chi2_p95:.2f}</small></td>"
            f"<td>{st.bf10_max_overall:.3f}<br/>"
            f"<small>H={st.normalized_entropy_tens:.3f}/"
            f"{st.normalized_entropy_units:.3f}</small></td>"
            f"<td>{bocd_badge}</td>"
            f"<td>Chục: <strong>{st.oos_rank1_freq_tens_pct:.2f}%</strong><br/>"
            f"Đơn vị: <strong>{st.oos_rank1_freq_units_pct:.2f}%</strong></td>"
            f"<td><strong>{st.joint_r1_pct:.3f}%</strong><br/>"
            f"<small>(Chuẩn ≥ {SELECTIVE_ALPHA_JOINT_R1_MIN_PCT:.3f}%)</small></td>"
            f"<td><code>{_esc(st.recommended_config_id)}</code>: "
            f"<strong>{_esc(', '.join(st.recommended_numbers))}</strong><br/>"
            f"{st_roi_html}</td>"
            f"<td><strong>{st.station_alpha_score:+.2f}</strong></td>"
            f'<td><span class="badge {verdict_cls}">{_esc(st.role_label_vi)}</span></td>'
            f"</tr>"
        )

    station_rationales_html = "\n".join(
        f"<li><strong>{_esc(st.station_name)} ({_esc(st.station_code)}):</strong> "
        f"{_esc(st.rationale_vi)}</li>"
        for st in report.all_today_stations
    )

    section2_html = (
        '  <section id="section-2-station-comparison" class="card">\n'
        f"    <h2>Khu vực 2 — Bảng Chấm Điểm &amp; So Sánh Toàn Bộ "
        f"{len(report.all_today_stations)} Đài Mở Thưởng Trong Ngày</h2>\n"
        '    <p class="subtitle">\n'
        "      Kiểm định nhân quả nghiêm ngặt trước giờ mở thưởng "
        f"(<code>draw_date &lt; {_esc(report.report_date)}</code>) trên đa cửa sổ "
        "W ∈ {15, 30, 60} đối chiếu 1.000 kịch bản Monte Carlo Null (<code>seed=42</code>). "
        f"Mốc hòa vốn đơn lồng: <code>{be_pct:.4f}%</code>.\n"
        "    </p>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        "          <tr>\n"
        "            <th>Hạng</th>\n"
        '            <th class="left">Đài Mở Thưởng</th>\n'
        "            <th>Khu Vực &amp; Giờ Quay</th>\n"
        "            <th>Cỡ Mẫu 3 Năm</th>\n"
        "            <th>χ²_max vs Null (P90/P95)</th>\n"
        "            <th>BF10 &amp; Entropy</th>\n"
        "            <th>BOCD Run Length r*</th>\n"
        "            <th>OOS Rank-1 (Chục / Đơn Vị)</th>\n"
        "            <th>JointR1%</th>\n"
        "            <th>Bộ Số &amp; OOS ROI 3Y</th>\n"
        "            <th>AlphaScore</th>\n"
        "            <th>Phán Quyết</th>\n"
        "          </tr>\n"
        "        </thead>\n"
        "        <tbody>\n"
        f"          {''.join(station_rows_html)}\n"
        "        </tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "    <h3>Giải trình định lượng chi tiết từng đài mở thưởng hôm nay:</h3>\n"
        "    <ul>\n"
        f"      {station_rationales_html}\n"
        "    </ul>\n"
        "  </section>\n"
    )

    # -------------------------------------------------------------------------
    # Khu vực 3: 10-Ball Probabilities (0-9), 10x10 Heatmap (00-99) & 5 Configs
    # -------------------------------------------------------------------------
    tens_rank_of_ball = {ball: rank_idx + 1 for rank_idx, ball in enumerate(p.ranked_balls_tens)}
    units_rank_of_ball = {ball: rank_idx + 1 for rank_idx, ball in enumerate(p.ranked_balls_units)}

    def _build_cage_table_rows(
        p_ai: Sequence[float],
        p_bocd: Sequence[float],
        p_seq: Sequence[float],
        rank_map: Mapping[int, int],
    ) -> str:
        rows: list[str] = []
        for ball in range(10):
            prob_pct = p_ai[ball] * 100.0
            bocd_pct = p_bocd[ball] * 100.0
            seq_pct = p_seq[ball] * 100.0
            rk = rank_map[ball]
            bar_w = min(100.0, max(5.0, prob_pct * 5.0))
            exceeds = prob_pct >= be_pct
            badge = (
                '<span class="badge badge-green">Vượt Hòa Vốn</span>'
                if exceeds
                else '<span class="badge badge-blue">Dưới 10.69%</span>'
            )
            rows.append(
                f"<tr>"
                f"<td><strong>Bóng {ball}</strong></td>"
                f"<td>Hạng {rk}</td>"
                f"<td><strong>{prob_pct:.2f}%</strong>"
                f'<div class="prob-bar-bg">'
                f'<div class="prob-bar-fill" style="width:{bar_w:.1f}%;"></div></div></td>'
                f"<td>{bocd_pct:.2f}%</td>"
                f"<td>{seq_pct:.2f}%</td>"
                f"<td>{badge}</td>"
                f"</tr>"
            )
        return "".join(rows)

    tens_rows_html = _build_cage_table_rows(
        p.p_ai_tens, p.p_bocd_tens, p.p_seq_tens, tens_rank_of_ball
    )
    units_rows_html = _build_cage_table_rows(
        p.p_ai_units, p.p_bocd_units, p.p_seq_units, units_rank_of_ball
    )

    rec_num_set = set(p.recommended_numbers)
    heatmap_header_cols = "".join(f"<th>ĐV {b}</th>" for b in range(10))
    heatmap_rows_list: list[str] = []
    for a in range(10):
        cells: list[str] = [f"<th>Chục {a}</th>"]
        for b in range(10):
            num_str = f"{a}{b}"
            cell_prob_pct = p.joint_100_matrix[a][b] * 100.0
            cls_str = (
                "heatmap-cell heatmap-recommended" if num_str in rec_num_set else "heatmap-cell"
            )
            cells.append(
                f'<td class="{cls_str}"><div><strong>{num_str}</strong></div>'
                f"<small>{cell_prob_pct:.2f}%</small></td>"
            )
        heatmap_rows_list.append(f"<tr>{''.join(cells)}</tr>")

    config_rows_html: list[str] = []
    for cfg_id in STAGE3_TICKET_CONFIGS:
        tc = p.ticket_configs[cfg_id]
        if cfg_id == "core_2x2_sat_3x3":
            nums_detail = (
                f"<strong>Lõi (1.0x):</strong> {_esc(', '.join(tc.core_numbers))}<br/>"
                f"<small><strong>Vệ tinh (0.5x):</strong> "
                f"{_esc(', '.join(tc.satellite_numbers))}</small>"
            )
        else:
            nums_detail = f"<strong>{_esc(', '.join(tc.selected_numbers))}</strong>"
        rec_badge = (
            '<span class="badge badge-green">⭐ Khuyến Nghị Chính</span>'
            if tc.is_recommended_primary
            else '<span class="badge badge-blue">Tham Khảo</span>'
        )
        roi_cls = "pos" if tc.oos_roi_3y_pct > 0 else "neg"
        config_rows_html.append(
            f"<tr>"
            f"<td><code>{_esc(tc.config_id)}</code></td>"
            f'<td class="left">{_esc(tc.label)}</td>'
            f"<td>{tc.num_numbers} số</td>"
            f'<td class="left">{nums_detail}</td>'
            f"<td>{tc.unit_cost_per_draw:.1f}đ<br/>"
            f"<small>({tc.benchmark_1x_cost_vnd:,} VNĐ)</small></td>"
            f"<td>{tc.single_prize_hit_prob * 100.0:.2f}%</td>"
            f"<td><strong>{tc.hit_at_least_1_in_18_prob * 100.0:.2f}%</strong></td>"
            f"<td>{tc.oos_hits_per_30_draws:.2f} / {tc.be_hits_30_draws:.2f} lô</td>"
            f"<td>{tc.oos_win_rate_3y_pct:.2f}%</td>"
            f'<td class="{roi_cls}">{tc.oos_roi_3y_pct:+.2f}%</td>'
            f"<td>{rec_badge}</td>"
            f"</tr>"
        )

    section3_html = (
        '  <section id="section-3-probabilities-and-configs" class="card">\n'
        "    <h2>Khu vực 3 — Bảng Phân Phối Xác Suất 10 Quả Bóng (0–9), "
        "Ma Trận Nhiệt 100 Số (00–99) &amp; Toàn Bộ 5 Phương Án Ghép Số "
        f"({_esc(p.station_name)} - {_esc(p.station_code)})</h2>\n"
        '    <div class="grid-2">\n'
        "      <div>\n"
        "        <h3>Lồng Hàng Chục (<code>tens_cage</code>) — "
        "Phân phối hiệu chuẩn P_AI(0..9)</h3>\n"
        '        <div class="table-wrap">\n'
        "          <table>\n"
        "            <thead>\n"
        "              <tr>\n"
        "                <th>Quả Bóng</th>\n"
        "                <th>Hạng</th>\n"
        "                <th>P_AI Hiệu Chuẩn</th>\n"
        "                <th>P_BOCD</th>\n"
        "                <th>P_Seq (Markov-Gap)</th>\n"
        "                <th>So Với Mốc 10.69%</th>\n"
        "              </tr>\n"
        "            </thead>\n"
        f"            <tbody>{tens_rows_html}</tbody>\n"
        "          </table>\n"
        "        </div>\n"
        "      </div>\n"
        "      <div>\n"
        "        <h3>Lồng Hàng Đơn Vị (<code>units_cage</code>) — "
        "Phân phối hiệu chuẩn P_AI(0..9)</h3>\n"
        '        <div class="table-wrap">\n'
        "          <table>\n"
        "            <thead>\n"
        "              <tr>\n"
        "                <th>Quả Bóng</th>\n"
        "                <th>Hạng</th>\n"
        "                <th>P_AI Hiệu Chuẩn</th>\n"
        "                <th>P_BOCD</th>\n"
        "                <th>P_Seq (Markov-Gap)</th>\n"
        "                <th>So Với Mốc 10.69%</th>\n"
        "              </tr>\n"
        "            </thead>\n"
        f"            <tbody>{units_rows_html}</tbody>\n"
        "          </table>\n"
        "        </div>\n"
        "      </div>\n"
        "    </div>\n"
        "    <h3>Ma Trận Nhiệt 10 × 10 Của 100 Con Số (00–99) — "
        f"Đánh dấu nổi bật bộ số khuyến nghị ({rec_nums_joined})</h3>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        f"          <tr><th>Chục \\ ĐV</th>{heatmap_header_cols}</tr>\n"
        "        </thead>\n"
        f"        <tbody>{''.join(heatmap_rows_list)}</tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "    <h3>Bảng So Sánh Trực Diện Toàn Bộ 5 Phương Án Ghép Số Ngọt "
        "(Sweet-Spot Ticket Configs)</h3>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        "          <tr>\n"
        "            <th>Mã Cấu Hình</th>\n"
        '            <th class="left">Quy Tắc Ghép Bóng</th>\n'
        "            <th>Số Lượng</th>\n"
        '            <th class="left">Danh Sách Bộ Số Cụ Thể</th>\n'
        "            <th>Vốn Chuẩn 1.0x</th>\n"
        "            <th>Xác Suất 1 Giải</th>\n"
        "            <th>Xác Suất Nổ ≥1 Nháy / 18 Giải</th>\n"
        "            <th>Số Lô / 30 Kỳ (vs Hòa Vốn)</th>\n"
        "            <th>Tỷ Lệ Ngày Thắng</th>\n"
        "            <th>OOS ROI 3 Năm</th>\n"
        "            <th>Vai Trò</th>\n"
        "          </tr>\n"
        "        </thead>\n"
        f"        <tbody>{''.join(config_rows_html)}</tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "  </section>\n"
    )

    # -------------------------------------------------------------------------
    # Khu vực 4: CPPI / House-Money Capital Guidance & Sample VND Table
    # -------------------------------------------------------------------------
    cap_rows_html: list[str] = []
    for row in cg.sample_allocations:
        dot_tier = f"{row.capital_tier_vnd:,}".replace(",", ".")
        cap_rows_html.append(
            f"<tr>"
            f'<td class="left"><strong>{_esc(row.tier_label)}</strong><br/>'
            f"<small>{row.capital_tier_vnd:,} VNĐ ({dot_tier}đ)</small></td>"
            f"<td>{row.scale_factor:.2f}x</td>"
            f"<td><strong>{row.recommended_multiplier:.2f}x</strong></td>"
            f"<td>{row.stake_per_number_vnd:,} VNĐ/số</td>"
            f"<td><strong>{row.total_daily_cost_vnd:,} VNĐ</strong></td>"
            f"<td>{row.payout_per_hit_vnd:,} VNĐ/nháy</td>"
            f'<td class="pos">{row.net_profit_1hit_vnd:+,} VNĐ</td>'
            f'<td class="pos">{row.net_profit_2hits_vnd:+,} VNĐ</td>'
            f'<td class="pos">{row.net_profit_3hits_vnd:+,} VNĐ</td>'
            f"</tr>"
        )

    min_buffer_vnd = HOUSE_MONEY_MIN_BUFFER_DAYS * BENCHMARK_BASE_DAILY_COST_4NUM_VND
    max_surplus_pct = int(HOUSE_MONEY_MAX_SURPLUS_FRACTION * 100)

    section4_html = (
        '  <section id="section-4-capital-guidance" class="card">\n'
        "    <h2>Khu vực 4 — Bảng Tư Vấn Đi Vốn CPPI / House-Money "
        "&amp; Quy Đổi Tiền VNĐ Mẫu</h2>\n"
        '    <div class="callout good">\n'
        "      <strong>🛡️ Kỷ luật Bảo toàn 100% Vốn gốc (CPPI / House-Money Gate 5):</strong> "
        f"Vốn gốc Quỹ Chuẩn bất khả xâm phạm "
        f"<code>W0 = {BENCHMARK_INITIAL_BANKROLL_VND:,} VNĐ (1.000.000đ)</code>. "
        "Chỉ cho phép nâng hệ số lên <code>1.25x – 1.50x</code> khi Quỹ Lãi Ròng tích lũy "
        f"đạt tối thiểu 2 ngày cược cơ sở (<code>C ≥ {min_buffer_vnd:,} VNĐ</code>) "
        f"và phần tiền cược tăng thêm không vượt quá <code>{max_surplus_pct}%</code> "
        "Quỹ Lãi Ròng.<br/>\n"
        f"      <strong>Giải trình đi vốn hôm nay:</strong> {_esc(cg.sizing_rationale_vi)}\n"
        "    </div>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        "          <tr>\n"
        '            <th class="left">Quy Mô Vốn Gia Đình Mẫu</th>\n'
        "            <th>Tỷ Lệ Quy Mô (κ)</th>\n"
        "            <th>Hệ Số Hôm Nay (m_D)</th>\n"
        "            <th>Tiền Cược / 1 Số</th>\n"
        "            <th>Tổng Tiền Cược / Ngày</th>\n"
        "            <th>Tiền Thu / 1 Nháy Nổ</th>\n"
        "            <th>Lãi Ròng Nổ 1 Nháy</th>\n"
        "            <th>Lãi Ròng Nổ 2 Nháy</th>\n"
        "            <th>Lãi Ròng Nổ 3 Nháy</th>\n"
        "          </tr>\n"
        "        </thead>\n"
        f"        <tbody>{''.join(cap_rows_html)}</tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "  </section>\n"
    )

    # -------------------------------------------------------------------------
    # Khu vực 5: Data Pipeline Audit, SVG Equity Curve & Benchmark Ledger
    # -------------------------------------------------------------------------
    svg_chart = render_equity_curve_svg(state)
    ledger_rows_html: list[str] = []
    for entry in reversed(state.entries[-30:]):
        hit_labels = (
            ", ".join(f"{_esc(h.number)} ({_esc(h.prize_label)})" for h in entry.hit_details)
            if entry.hit_details
            else "-"
        )
        net_cls = "pos" if entry.net_profit_vnd >= 0 else "neg"
        status_cls = "badge-green" if entry.settlement_status == "SETTLED" else "badge-amber"
        hit_k_str = entry.hit_count_k if entry.hit_count_k is not None else "-"
        if entry.verdict_tier == "SKIP_NO_EDGE":
            station_and_pick_cells = (
                f'<td class="left"><span style="color:var(--muted);">'
                f"NGHỈ (Quan sát {_esc(entry.chosen_station_name)} - "
                f"<code>{_esc(entry.chosen_station_code)}</code>)</span></td>"
                f'<td><span style="color:var(--muted);">'
                f"Quan sát <code>{_esc(entry.chosen_config_id)}</code>: "
                f"{_esc(', '.join(entry.selected_numbers))}</span></td>"
            )
        else:
            station_and_pick_cells = (
                f'<td class="left">{_esc(entry.chosen_station_name)} '
                f"(<code>{_esc(entry.chosen_station_code)}</code>)</td>"
                f"<td><code>{_esc(entry.chosen_config_id)}</code>: "
                f"{_esc(', '.join(entry.selected_numbers))}</td>"
            )
        ledger_rows_html.append(
            f"<tr>"
            f"<td><code>{_esc(entry.draw_date)}</code><br/>"
            f"<small>{_esc(entry.weekday_vn)}</small></td>"
            f'<td><span class="badge {status_cls}">{_esc(entry.settlement_status)}</span></td>'
            f"<td>{_esc(entry.verdict_tier)}</td>"
            f"{station_and_pick_cells}"
            f"<td>{entry.recommended_multiplier:.2f}x</td>"
            f"<td>{entry.cost_vnd:,}đ</td>"
            f"<td>{hit_k_str} nháy<br/><small>{hit_labels}</small></td>"
            f"<td>{entry.revenue_vnd:,}đ</td>"
            f'<td class="{net_cls}">{entry.net_profit_vnd:+,}đ</td>'
            f"<td><strong>{entry.bankroll_after_vnd:,}đ</strong></td>"
            f"<td>{entry.house_money_after_vnd:,}đ</td>"
            f"</tr>"
        )
    if not ledger_rows_html:
        ledger_rows_html.append(
            '<tr><td colspan="12">Chưa có bút toán lịch sử trong sổ cái.</td></tr>'
        )

    gate_status_str = "PASS 100%" if audit.schema_gate_passed else "FAIL"
    gate_color_var = "var(--green)" if audit.schema_gate_passed else "var(--red)"
    section5_html = (
        '  <section id="section-5-pipeline-audit-and-ledger" class="card">\n'
        "    <h2>Khu vực 5 — Nhật Ký Thu Thập Dữ Liệu (Data Pipeline Audit), "
        "Biểu Đồ Đường Cong Vốn &amp; Sổ Cái Đối Soát Quỹ Chuẩn (1.000.000 VNĐ)</h2>\n"
        '    <div class="grid-4" style="margin-bottom: 16px;">\n'
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Trạng Thái DataSchemaGate (35 Đài)</div>\n'
        f'        <div class="kpi-value" style="color: {gate_color_var};">'
        f"{gate_status_str} ({audit.stations_synced_ok}/{audit.total_stations_35} Đài)</div>\n"
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Failover dự phòng: {audit.fallback_used_count} đài</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Số Dư Quỹ Chuẩn Hiện Tại (W_t)</div>\n'
        f'        <div class="kpi-value">{state.current_bankroll_vnd:,} VNĐ</div>\n'
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Vốn gốc W0 = {state.starting_bankroll_vnd:,} VNĐ</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Quỹ Lãi Ròng House-Money (C_t)</div>\n'
        f'        <div class="kpi-value" style="color: var(--green);">'
        f"{state.house_money_surplus_vnd:,} VNĐ</div>\n"
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Lãi/Lỗ lũy kế: {state.net_profit_vnd:+,} VNĐ</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Sụt Giảm Tối Đa (Max Drawdown)</div>\n'
        f'        <div class="kpi-value">{state.max_drawdown_vnd:,} VNĐ</div>\n'
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Đánh {state.played_days} ngày • Nghỉ {state.rest_days} ngày</div>\n"
        "      </div>\n"
        "    </div>\n"
        '    <div class="callout">\n'
        f"      <strong>🔍 Nhật ký kiểm định đường ống dữ liệu "
        f"({_esc(audit.audit_timestamp_ict)}):</strong> "
        f"{_esc(audit.notes_vi)} | Kỳ mở thưởng đã chốt gần nhất: "
        f"<code>{_esc(audit.latest_settled_date)}</code> | "
        f"Chữ ký SHA-256 Sổ cái: <code>{_esc(state.sha256[:24])}...</code>\n"
        "    </div>\n"
        "    <h3>Biểu Đồ Đường Cong Vốn Lũy Kế Của Quỹ Chuẩn Tham Chiếu (1.000.000 VNĐ)</h3>\n"
        f"    {svg_chart}\n"
        "    <h3>Bảng Sao Kê Sổ Cái Đối Soát Quỹ Chuẩn (1.000.000 VNĐ)</h3>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        "          <tr>\n"
        "            <th>Ngày Quay</th>\n"
        "            <th>Trạng Thái</th>\n"
        "            <th>Phán Quyết</th>\n"
        '            <th class="left">Đài Khuyến Nghị</th>\n'
        "            <th>Cấu Hình &amp; Bộ Số</th>\n"
        "            <th>Hệ Số</th>\n"
        "            <th>Tiền Cược</th>\n"
        "            <th>Kết Quả Nổ (18 Giải)</th>\n"
        "            <th>Tiền Thu</th>\n"
        "            <th>Lãi / Lỗ Ròng</th>\n"
        "            <th>Số Dư Sau Đối Soát</th>\n"
        "            <th>Quỹ Lãi Ròng</th>\n"
        "          </tr>\n"
        "        </thead>\n"
        f"        <tbody>{''.join(ledger_rows_html)}</tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "  </section>\n"
    )

    r_date_esc = _esc(report.report_date)
    w_vn_esc = _esc(report.weekday_vn)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="vi">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"  <title>Báo Cáo Định Lượng 05:00 Sáng — {w_vn_esc} "
        f"({dd_mm_yyyy} / {r_date_esc})</title>\n"
        f"  <style>{_SHARED_DARK_MODE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="container">\n'
        '  <header class="hero">\n'
        '    <div style="display:flex; justify-content:space-between; '
        'align-items:center; flex-wrap:wrap; gap:10px;">\n'
        '      <span class="badge badge-blue">📡 CHUYÊN VIÊN BÁO CÁO ĐỊNH LƯỢNG 05:00 SÁNG '
        "(100% TOÁN HỌC THUẦN TÚY)</span>\n"
        '      <a href="../index.html">⬅️ Về Trang Chủ Dashboard Quỹ Chuẩn</a>\n'
        "    </div>\n"
        f"    <h1>Báo Cáo Giải Trình Toán Học Ngày {dd_mm_yyyy} "
        f"({w_vn_esc} — {r_date_esc})</h1>\n"
        '    <p class="subtitle">\n'
        f"      Thời điểm kết xuất: <code>{_esc(report.generated_at_ict)}</code> •\n"
        f'      Tài liệu JSON Kiểm toán: <a href="{r_date_esc}.json">'
        f"<code>{r_date_esc}.json</code></a> •\n"
        f"      Canonical URL: <code>{_esc(resolved_base_url)}/daily/{r_date_esc}.html</code>\n"
        "    </p>\n"
        "  </header>\n"
        f"{section1_html}"
        f"{section2_html}"
        f"{section3_html}"
        f"{section4_html}"
        f"{section5_html}"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


def render_index_dashboard_html(
    reports: Sequence[DailyQuantReportContract | Mapping[str, Any]],
    ledger_state: BenchmarkLedgerState | None = None,
    *,
    public_report_base_url: str | None = None,
) -> str:
    """Render `public/index.html` listing Benchmark Fund KPIs, SVG curve & daily report links."""
    resolved_base_url = resolve_public_report_base_url(public_report_base_url)
    state = ledger_state if ledger_state is not None else initialize_empty_ledger()
    svg_chart = render_equity_curve_svg(state)

    valid_tiers = {"PLAY_PEAK", "PLAY_STANDARD", "PLAY_CAUTIOUS", "SKIP_NO_EDGE"}
    normalized_items: list[dict[str, Any]] = []
    for item in reports:
        if isinstance(item, DailyQuantReportContract):
            validated_date = validate_iso_date(item.report_date)
            rec_roi = item.primary_station.ticket_configs[
                item.primary_station.recommended_config_id
            ].oos_roi_3y_pct
            normalized_items.append(
                {
                    "report_date": validated_date,
                    "weekday_vn": item.weekday_vn,
                    "verdict_tier": item.verdict_tier,
                    "station_code": item.primary_station.station_code,
                    "station_name": item.primary_station.station_name,
                    "region": item.primary_station.region,
                    "config_id": item.primary_station.recommended_config_id,
                    "numbers": item.primary_station.recommended_numbers,
                    "joint_r1_pct": item.primary_station.joint_r1_pct,
                    "roi_pct": rec_roi,
                    "multiplier": item.capital_guidance.recommended_multiplier,
                    "bet_vnd": item.capital_guidance.benchmark_bet_vnd,
                }
            )
        elif isinstance(item, Mapping):
            validated_date = validate_iso_date(str(item.get("report_date", "")))
            raw_tier = str(item.get("verdict_tier", "SKIP_NO_EDGE"))
            if raw_tier not in valid_tiers:
                raise DataIntegrityError(
                    f"Invalid verdict_tier {raw_tier!r} in dashboard report summary."
                )
            prim = item.get("primary_station", {})
            if not isinstance(prim, Mapping):
                raise DataIntegrityError("primary_station in dashboard summary must be a mapping.")
            cap = item.get("capital_guidance", {})
            if not isinstance(cap, Mapping):
                raise DataIntegrityError("capital_guidance in dashboard summary must be a mapping.")
            normalized_items.append(
                {
                    "report_date": validated_date,
                    "weekday_vn": str(item.get("weekday_vn", "")),
                    "verdict_tier": raw_tier,
                    "station_code": str(prim.get("station_code", "")),
                    "station_name": str(prim.get("station_name", "")),
                    "region": str(prim.get("region", "")),
                    "config_id": str(prim.get("recommended_config_id", "")),
                    "numbers": list(prim.get("recommended_numbers", [])),
                    "joint_r1_pct": float(prim.get("joint_r1_pct", 0.0)),
                    "roi_pct": float(prim.get("best_oos_roi_pct", 0.0)),
                    "multiplier": float(cap.get("recommended_multiplier", 0.0)),
                    "bet_vnd": int(cap.get("benchmark_bet_vnd", 0)),
                }
            )
        else:
            raise DataIntegrityError(
                f"Expected DailyQuantReportContract or Mapping in render_index_dashboard_html, "
                f"got {type(item).__name__}."
            )

    normalized_items.sort(key=lambda r: r["report_date"], reverse=True)

    report_rows_html: list[str] = []
    for r in normalized_items:
        r_date = _esc(r["report_date"])
        nums_str = _esc(", ".join(str(x) for x in r["numbers"]))
        report_rows_html.append(
            f"<tr>"
            f"<td><strong><code>{r_date}</code></strong><br/>"
            f"<small>{_esc(r['weekday_vn'])}</small></td>"
            f"<td><code>{_esc(r['verdict_tier'])}</code></td>"
            f'<td class="left"><strong>{_esc(r["station_name"])}</strong> '
            f"(<code>{_esc(r['station_code'])}</code> — {_esc(r['region'])})</td>"
            f"<td><code>{_esc(r['config_id'])}</code>: <strong>{nums_str}</strong></td>"
            f"<td>{r['joint_r1_pct']:.3f}%</td>"
            f"<td>{r['roi_pct']:+.2f}%</td>"
            f"<td>{r['multiplier']:.2f}x ({r['bet_vnd']:,}đ)</td>"
            f"<td>"
            f'<a href="daily/{r_date}.html"><strong>📄 Xem Báo Cáo HTML</strong></a> | '
            f'<a href="daily/{r_date}.json"><code>JSON</code></a>'
            f"</td>"
            f"</tr>"
        )
    if not report_rows_html:
        report_rows_html.append(
            '<tr><td colspan="8">Chưa có báo cáo ngày nào được xuất bản.</td></tr>'
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="vi">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        "  <title>Trang Chủ Dashboard Quỹ Chuẩn 1.000.000 VNĐ — "
        "Chuyên Viên Định Lượng 05:00 Sáng</title>\n"
        f"  <style>{_SHARED_DARK_MODE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="container">\n'
        '  <header class="hero">\n'
        '    <span class="badge badge-green">🏦 HỆ THỐNG BÁO CÁO ĐỊNH LƯỢNG TỰ ĐỘNG 05:00 SÁNG '
        "(35 ĐÀI XSMN &amp; XSMT)</span>\n"
        "    <h1>Dashboard Theo Dõi Quỹ Chuẩn Tham Chiếu (1.000.000 VNĐ) "
        "&amp; Lưu Trữ Báo Cáo Hàng Ngày</h1>\n"
        '    <p class="subtitle">\n'
        "      Vận hành 100% bằng Toán học &amp; Thống kê thuần túy (NumPy/SciPy) • "
        "Không dùng AI API • Không dùng Database ngoài • "
        f"Base URL: <code>{_esc(resolved_base_url)}</code>\n"
        "    </p>\n"
        '    <div style="margin-top: 12px;">\n'
        '      <a href="logic_explainer.html" style="display: inline-block; background: rgba(56, 189, 248, 0.14); color: #38bdf8; border: 1px solid #38bdf8; padding: 6px 14px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.9rem;">📘 Mở Sổ Tay Kiểm Toán &amp; Giải Thích Logic Chọn Số Từ A Đến Z</a>\n'
        "    </div>\n"
        "  </header>\n"
        '  <section class="card">\n'
        "    <h2>1. Tổng Quan Hiệu Suất Quỹ Chuẩn Tham Chiếu (1.000.000 VNĐ)</h2>\n"
        '    <div class="grid-4" style="margin-bottom: 18px;">\n'
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Vốn Gốc Khởi Đầu (W0)</div>\n'
        f'        <div class="kpi-value">{state.starting_bankroll_vnd:,} VNĐ</div>\n'
        '        <div style="font-size: 0.84rem; color: var(--muted);">'
        "Bảo toàn 100% theo kỷ luật CPPI</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Số Dư Quỹ Chuẩn Hiện Tại (W_t)</div>\n'
        f'        <div class="kpi-value" style="color: var(--green);">'
        f"{state.current_bankroll_vnd:,} VNĐ</div>\n"
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Lãi ròng lũy kế: {state.net_profit_vnd:+,} VNĐ</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Quỹ Lãi Ròng House-Money (C_t)</div>\n'
        f'        <div class="kpi-value">{state.house_money_surplus_vnd:,} VNĐ</div>\n'
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Đỉnh vốn: {state.peak_bankroll_vnd:,} VNĐ • "
        f"MaxDD: {state.max_drawdown_vnd:,}đ</div>\n"
        "      </div>\n"
        '      <div class="kpi-box">\n'
        '        <div class="kpi-label">Thống Kê Kỷ Luật Vận Hành</div>\n'
        f'        <div class="kpi-value">{state.total_tracked_days} Ngày</div>\n'
        f'        <div style="font-size: 0.84rem; color: var(--muted);">'
        f"Đánh {state.played_days} (Thắng {state.win_days}) • "
        f"Nghỉ {state.rest_days}</div>\n"
        "      </div>\n"
        "    </div>\n"
        f"    {svg_chart}\n"
        "  </section>\n"
        '  <section class="card">\n'
        "    <h2>2. Danh Sách Báo Cáo Giải Trình Chi Tiết Các Ngày</h2>\n"
        '    <div class="table-wrap">\n'
        "      <table>\n"
        "        <thead>\n"
        "          <tr>\n"
        "            <th>Ngày Báo Cáo</th>\n"
        "            <th>Phán Quyết</th>\n"
        '            <th class="left">Đài Ưu Tiên Số 1</th>\n'
        "            <th>Bộ Số Khuyến Nghị</th>\n"
        "            <th>JointR1%</th>\n"
        "            <th>OOS ROI 3Y</th>\n"
        "            <th>Đi Vốn</th>\n"
        "            <th>Liên Kết Báo Cáo</th>\n"
        "          </tr>\n"
        "        </thead>\n"
        f"        <tbody>{''.join(report_rows_html)}</tbody>\n"
        "      </table>\n"
        "    </div>\n"
        "  </section>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


def publish_daily_web_report(
    report: DailyQuantReportContract,
    *,
    public_dir: str | Path = DEFAULT_PUBLIC_DIR,
    ledger_state_or_path: BenchmarkLedgerState | str | Path | None = None,
    public_report_base_url: str | None = None,
) -> dict[str, Path]:
    """Publish daily JSON audit, 5-section HTML report, and `public/index.html`."""
    if not isinstance(report, DailyQuantReportContract):
        raise DataIntegrityError(f"Expected DailyQuantReportContract, got {type(report).__name__}.")

    if isinstance(ledger_state_or_path, BenchmarkLedgerState):
        ledger_state = ledger_state_or_path
    elif isinstance(ledger_state_or_path, (str, Path)):
        l_path = Path(ledger_state_or_path)
        ledger_state = (
            load_benchmark_ledger(l_path)
            if l_path.exists()
            else initialize_empty_ledger(updated_at=report.generated_at_ict)
        )
    elif DEFAULT_LEDGER_PATH.exists():
        ledger_state = load_benchmark_ledger(DEFAULT_LEDGER_PATH)
    else:
        ledger_state = initialize_empty_ledger(updated_at=report.generated_at_ict)

    if not report.telegram_message_html:
        report = report.model_copy(
            update={
                "telegram_message_html": format_telegram_executive_briefing(
                    report,
                    public_report_base_url=public_report_base_url,
                )
            }
        )

    pub_root = Path(public_dir)
    daily_dir = pub_root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    daily_json_path = daily_dir / f"{report.report_date}.json"
    daily_html_path = daily_dir / f"{report.report_date}.html"
    index_html_path = pub_root / "index.html"

    daily_json_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    daily_html = render_daily_report_html(
        report,
        ledger_state,
        public_report_base_url=public_report_base_url,
    )
    daily_html_path.write_text(daily_html, encoding="utf-8")

    all_daily_reports: list[DailyQuantReportContract] = []
    for json_file in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            raw_text = json_file.read_text(encoding="utf-8")
            validated_rep = DailyQuantReportContract.model_validate_json(raw_text)
        except Exception as exc:
            raise DataIntegrityError(
                f"Invalid or corrupted daily report JSON in {json_file}: {exc}"
            ) from exc
        if json_file.stem != validated_rep.report_date:
            raise DataIntegrityError(
                f"Daily report filename {json_file.name!r} does not match "
                f"report_date {validated_rep.report_date!r}."
            )
        all_daily_reports.append(validated_rep)

    index_html = render_index_dashboard_html(
        all_daily_reports,
        ledger_state,
        public_report_base_url=public_report_base_url,
    )
    index_html_path.write_text(index_html, encoding="utf-8")

    return {
        "daily_json": daily_json_path,
        "daily_html": daily_html_path,
        "index_html": index_html_path,
    }


render_daily_audit_html = render_daily_report_html
