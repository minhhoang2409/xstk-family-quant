"""Reporting Module: Exports JSON Handoff Contracts and Dual-Station HTML Dashboard."""

from __future__ import annotations

import datetime
import html
import json
from collections.abc import Mapping
from pathlib import Path

from xsmn_alpha.constants import (
    BE_LIFT_SINGLE_BALL,
    BE_PROB_SINGLE_BALL,
    SWEET_SPOT_CONFIGS,
)
from xsmn_alpha.exceptions import DataIntegrityError
from xsmn_alpha.schemas import (
    DualHorizonStationReport,
    HorizonBacktestReport,
    Stage3HandoffContract,
)


def save_stage3_handoff_contract(
    contract: Stage3HandoffContract,
    *,
    out_dir: str | Path = Path("data/outputs"),
) -> Path:
    """Validate and write stage3_handoff_<station_code>.json with UTF-8 encoding."""
    if not isinstance(contract, Stage3HandoffContract):
        raise DataIntegrityError("contract must be a Stage3HandoffContract instance.")
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"stage3_handoff_{contract.station_code}.json"
    payload = contract.model_dump()
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def _badge_for_status(status: str) -> str:
    if status == "PASS_ALPHA":
        return '<span class="badge pass">PASS_ALPHA (Vượt Ngưỡng Hòa Vốn)</span>'
    if status == "WARN_WEAK_SIGNAL":
        return '<span class="badge warn">WARN_WEAK_SIGNAL (Tín Hiệu Yếu &lt; Hòa Vốn)</span>'
    return (
        '<span class="badge fail">'
        "[FAIL_WHITE_NOISE_CASH_BRAKE] (Nhiễu Trắng - Khóa Vốn 0.0x)"
        "</span>"
    )


def _render_horizon_section(rep: HorizonBacktestReport) -> str:
    f_rep = rep.falsification_report
    t_cage = f_rep.tens_cage
    u_cage = f_rep.units_cage

    decay_rows = []
    for r_idx in range(10):
        t_freq = rep.tens_rank_alpha_decay[r_idx] * 100.0
        u_freq = rep.units_rank_alpha_decay[r_idx] * 100.0
        t_lift = ((rep.tens_rank_alpha_decay[r_idx] / 0.10) - 1.0) * 100.0
        u_lift = ((rep.units_rank_alpha_decay[r_idx] / 0.10) - 1.0) * 100.0
        decay_rows.append(
            f"<tr>"
            f"<td><strong>Rank {r_idx + 1}</strong></td>"
            f"<td>{t_freq:.2f}% ({t_lift:+.2f}%)</td>"
            f"<td>{u_freq:.2f}% ({u_lift:+.2f}%)</td>"
            f"</tr>"
        )

    portfolio_rows = []
    for cfg_id, m in rep.portfolio_metrics.items():
        label = html.escape(str(SWEET_SPOT_CONFIGS[cfg_id]["label"]))
        profit_cls = "pos" if m.net_profit >= 0.0 else "neg"
        portfolio_rows.append(
            f"<tr>"
            f"<td><code>{html.escape(cfg_id)}</code> — {label}</td>"
            f"<td>{m.cost_per_draw:.1f}đ</td>"
            f"<td>{m.hits_per_30_draws:.2f} / {m.break_even_hits_30_draws:.2f}</td>"
            f"<td>{m.daily_win_rate * 100.0:.1f}%</td>"
            f"<td>{m.multi_hit_rate_ge2 * 100.0:.1f}%</td>"
            f"<td>{m.zero_hit_rate_k0 * 100.0:.1f}%</td>"
            f"<td>{m.max_losing_streak} kỳ</td>"
            f"<td>{m.max_drawdown:.1f}đ</td>"
            f'<td class="{profit_cls}">{m.net_profit:+.2f}đ ({m.roi_pct:+.2f}%)</td>'
            f"</tr>"
        )

    h_title = html.escape(rep.horizon.upper())
    t_top2 = (
        f"{t_cage.top2_calibrated_prob_mean * 100.0:.2f}% "
        f"({t_cage.top2_calibrated_lift * 100.0:+.2f}%)"
    )
    u_top2 = (
        f"{u_cage.top2_calibrated_prob_mean * 100.0:.2f}% "
        f"({u_cage.top2_calibrated_lift * 100.0:+.2f}%)"
    )
    be_prob_pct = BE_PROB_SINGLE_BALL * 100.0
    be_lift_pct = BE_LIFT_SINGLE_BALL * 100.0

    return (
        f'<div class="horizon-card">\n'
        f"  <h3>Khung {h_title} ({rep.total_draws} kỳ | "
        f"Kiểm thử ngoài mẫu: {rep.evaluated_draws} kỳ)</h3>\n"
        f"  <p>Trạng thái Phễu Gatekeeper: {_badge_for_status(f_rep.overall_status)} | "
        f"Hệ số vốn khuyến nghị: <strong>{f_rep.recommended_capital_multiplier:.2f}x</strong></p>\n"
        f"  <h4>1. Đối chứng 1,000 Chuỗi Ngẫu Nhiên Giả Lập "
        f"(Monte Carlo Null, Seed={f_rep.seed})</h4>\n"
        f"  <table>\n"
        f"    <thead>\n"
        f"      <tr>\n"
        f"        <th>Lồng Cầu</th>\n"
        f"        <th>Chi-Square Cực Đại Quan Sát</th>\n"
        f"        <th>Ngưỡng Null P90 / P95</th>\n"
        f"        <th>p-value (MC)</th>\n"
        f"        <th>Bayes Factor BF10 Max</th>\n"
        f"        <th>Xác Suất Hiệu Chuẩn Top-2 (Lift)</th>\n"
        f"        <th>Brier Ngoài Mẫu (AI vs Naive)</th>\n"
        f"        <th>Phán Quyết</th>\n"
        f"      </tr>\n"
        f"    </thead>\n"
        f"    <tbody>\n"
        f"      <tr>\n"
        f"        <td><strong>Lồng Chục (tens_cage)</strong></td>\n"
        f"        <td>{t_cage.observed_chi2_max:.2f}</td>\n"
        f"        <td>{t_cage.null_chi2_max_p90:.2f} / {t_cage.null_chi2_max_p95:.2f}</td>\n"
        f"        <td>{t_cage.mc_p_value:.4f}</td>\n"
        f"        <td>{t_cage.observed_bf10_max:.4f}</td>\n"
        f"        <td>{t_top2}</td>\n"
        f"        <td>{rep.tens_oos_brier_score:.5f} vs {rep.tens_naive_brier_score:.5f}</td>\n"
        f"        <td>{_badge_for_status(t_cage.gate_status)}</td>\n"
        f"      </tr>\n"
        f"      <tr>\n"
        f"        <td><strong>Lồng Đơn Vị (units_cage)</strong></td>\n"
        f"        <td>{u_cage.observed_chi2_max:.2f}</td>\n"
        f"        <td>{u_cage.null_chi2_max_p90:.2f} / {u_cage.null_chi2_max_p95:.2f}</td>\n"
        f"        <td>{u_cage.mc_p_value:.4f}</td>\n"
        f"        <td>{u_cage.observed_bf10_max:.4f}</td>\n"
        f"        <td>{u_top2}</td>\n"
        f"        <td>{rep.units_oos_brier_score:.5f} vs {rep.units_naive_brier_score:.5f}</td>\n"
        f"        <td>{_badge_for_status(u_cage.gate_status)}</td>\n"
        f"      </tr>\n"
        f"    </tbody>\n"
        f"  </table>\n"
        f"  <h4>2. Đường Cong Suy Giảm Alpha Ngoài Mẫu "
        f"(Rank 1 &rarr; Rank 10, Chuẩn Hòa Vốn: {be_prob_pct:.4f}% / {be_lift_pct:+.4f}%)</h4>\n"
        f"  <table>\n"
        f"    <thead>\n"
        f"      <tr><th>Thứ Hạng Dự Báo</th>"
        f"<th>Tần Suất Nổ Thực Tế Lồng Chục</th>"
        f"<th>Tần Suất Nổ Thực Tế Lồng Đơn Vị</th></tr>\n"
        f"    </thead>\n"
        f"    <tbody>\n"
        f"      {''.join(decay_rows)}\n"
        f"    </tbody>\n"
        f"  </table>\n"
        f"  <h4>3. Bảng Chấm Điểm Trượt Walk-Forward Các Cấu Hình Điểm Ngọt</h4>\n"
        f"  <table>\n"
        f"    <thead>\n"
        f"      <tr>\n"
        f"        <th>Cấu Hình Điểm Ngọt</th>\n"
        f"        <th>Vốn/Kỳ</th>\n"
        f"        <th>Lô Trúng / Hòa Vốn (30 Kỳ)</th>\n"
        f"        <th>Tỷ Lệ Ngày Lãi</th>\n"
        f"        <th>Nổ &ge; 2 Lô</th>\n"
        f"        <th>Trắng Bảng (K=0)</th>\n"
        f"        <th>Chuỗi Thua Max</th>\n"
        f"        <th>Max Drawdown</th>\n"
        f"        <th>Lãi/Lỗ Ròng (ROI)</th>\n"
        f"      </tr>\n"
        f"    </thead>\n"
        f"    <tbody>\n"
        f"      {''.join(portfolio_rows)}\n"
        f"    </tbody>\n"
        f"  </table>\n"
        f"</div>\n"
    )


def render_dual_station_html_report(
    station_reports: Mapping[str, DualHorizonStationReport],
    handoff_contracts: Mapping[str, Stage3HandoffContract],
) -> str:
    """Render complete HTML report comparing stations across 5Y and 3Y horizons."""
    station_blocks = []
    for st_code, st_rep in station_reports.items():
        handoff = handoff_contracts.get(st_code)
        handoff_summary = ""
        if handoff is not None:
            tens_str = ", ".join(f"{i}: {p * 100.0:.2f}%" for i, p in enumerate(handoff.p_ai_tens))
            units_str = ", ".join(
                f"{i}: {p * 100.0:.2f}%" for i, p in enumerate(handoff.p_ai_units)
            )
            nums_str = ", ".join(handoff.selected_numbers_2d)
            st_esc = html.escape(st_code)
            cfg_esc = html.escape(handoff.recommended_portfolio_config)
            handoff_summary = (
                f'<div class="handoff-box">\n'
                f"  <h4>Hợp Đồng Bàn Giao Sang Giai Đoạn 3 "
                f"(<code>stage3_handoff_{st_esc}.json</code>)</h4>\n"
                f"  <p><strong>Ngày chốt dữ liệu:</strong> "
                f"{html.escape(handoff.as_of_draw_date)} | "
                f"<strong>Conviction Score:</strong> {handoff.conviction_score:.2f}/100 | "
                f"<strong>Bộ số {cfg_esc} kỳ tới:</strong> "
                f"<code>{html.escape(nums_str)}</code></p>\n"
                f"  <p><strong>Xác suất hiệu chuẩn Lồng Chục P_AI(0..9):</strong> "
                f"{tens_str}</p>\n"
                f"  <p><strong>Xác suất hiệu chuẩn Lồng Đơn Vị P_AI(0..9):</strong> "
                f"{units_str}</p>\n"
                f"</div>\n"
            )

        st_name_esc = html.escape(st_rep.station_name)
        st_code_esc = html.escape(st_code)
        block = (
            f'<section class="station-section">\n'
            f"  <h2>Đài {st_name_esc} "
            f"(<code>{st_code_esc}</code> — {st_rep.draws_per_week} kỳ/tuần)</h2>\n"
            f"  {handoff_summary}\n"
            f"  {_render_horizon_section(st_rep.horizon_5y)}\n"
            f"  {_render_horizon_section(st_rep.horizon_3y)}\n"
            f"</section>\n"
        )
        station_blocks.append(block)

    generated_ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    css = (
        "body { font-family: system-ui, sans-serif; background: #0f172a; "
        "color: #e2e8f0; margin: 0; padding: 24px; line-height: 1.5; }\n"
        "h1, h2, h3, h4 { color: #f8fafc; margin-top: 0.8em; margin-bottom: 0.4em; }\n"
        ".container { max-width: 1280px; margin: 0 auto; }\n"
        ".station-section { background: #1e293b; border: 1px solid #334155; "
        "border-radius: 12px; padding: 20px; margin-bottom: 28px; }\n"
        ".horizon-card { background: #0f172a; border: 1px solid #334155; "
        "border-radius: 8px; padding: 16px; margin-top: 16px; }\n"
        ".handoff-box { background: #172554; border: 1px solid #1d4ed8; "
        "border-radius: 8px; padding: 14px; margin-bottom: 16px; }\n"
        "table { width: 100%; border-collapse: collapse; margin: 10px 0 18px 0; "
        "font-size: 0.9rem; }\n"
        "th, td { border: 1px solid #334155; padding: 8px 10px; text-align: left; }\n"
        "th { background: #1e293b; color: #93c5fd; }\n"
        ".badge { padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 0.82rem; }\n"
        ".badge.pass { background: #065f46; color: #6ee7b7; }\n"
        ".badge.warn { background: #78350f; color: #fcd34d; }\n"
        ".badge.fail { background: #7f1d1d; color: #fca5a5; }\n"
        ".pos { color: #4ade80; font-weight: 600; }\n"
        ".neg { color: #f87171; font-weight: 600; }\n"
        "code { background: #334155; padding: 2px 5px; border-radius: 4px; color: #fde047; }\n"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="vi">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        "  <title>Báo Cáo Thực Nghiệm Giai Đoạn 2 — Phát Hiện Alpha XSMN</title>\n"
        f"  <style>\n{css}  </style>\n"
        "</head>\n"
        "<body>\n"
        '  <div class="container">\n'
        "    <h1>Báo Cáo Thực Nghiệm Giai Đoạn 2: "
        "Hệ Thống Phát Hiện Alpha &amp; Hội Đồng Xác Suất Hiệu Chuẩn XSMN</h1>\n"
        f"    <p>Thời điểm xuất báo cáo: <code>{generated_ts}</code> | "
        "Phương án C: Phễu Kiểm Định Chống Nhiễu (1,000 Monte Carlo Null) + "
        "Hội Đồng BOCD &amp; Markov-Gap Hiệu Chuẩn Lồi SLSQP</p>\n"
        f"    {''.join(station_blocks)}\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def export_dual_station_reports(
    station_reports: Mapping[str, DualHorizonStationReport],
    handoff_contracts: Mapping[str, Stage3HandoffContract],
    *,
    reports_dir: str | Path = Path("reports"),
) -> tuple[Path, Path]:
    """Write stage2_dual_station_comparison.json and stage2_dual_station_report.html."""
    if not station_reports:
        raise DataIntegrityError("station_reports cannot be empty.")

    target_dir = Path(reports_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "stage2_dual_station_comparison.json"
    html_path = target_dir / "stage2_dual_station_report.html"

    comparison_payload = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "stations": {st_code: rep.model_dump() for st_code, rep in station_reports.items()},
        "stage3_handoffs": {
            st_code: contract.model_dump() for st_code, contract in handoff_contracts.items()
        },
    }
    json_path.write_text(
        json.dumps(comparison_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    html_content = render_dual_station_html_report(station_reports, handoff_contracts)
    html_path.write_text(html_content, encoding="utf-8")
    return json_path, html_path
