"""Reporting package for Stage 2 XSMN Alpha Discovery."""

from __future__ import annotations

from xsmn_alpha.reporting.html_report import (
    export_dual_station_reports,
    render_dual_station_html_report,
    save_stage3_handoff_contract,
)

__all__ = [
    "export_dual_station_reports",
    "render_dual_station_html_report",
    "save_stage3_handoff_contract",
]
