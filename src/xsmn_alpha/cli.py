"""Unified Command-Line Interface (Stage 2 & Stage 3) for XSMN/XSMT Quantitative Platform."""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import numpy as np

from xsmn_alpha.backtest.runner import (
    WalkForwardRunner,
    _compute_next_expected_draw_date,
    build_stage3_handoff_contract,
)
from xsmn_alpha.constants import (
    DEFAULT_MONTE_CARLO_SIMS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_WARMUP_DRAWS,
    MIN_SAMPLE_SIZE_DRAWS,
    VALID_HORIZONS,
    VALID_STATIONS,
)
from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler
from xsmn_alpha.exceptions import CapitalDisciplineError, DataIntegrityError
from xsmn_alpha.falsification.gatekeeper import FalsificationGatekeeper
from xsmn_alpha.ingest.canonicalizer import (
    load_canonical_draws,
    save_canonical_draws,
    slice_horizon,
)
from xsmn_alpha.ingest.fetcher import fetch_station_draws
from xsmn_alpha.live.daily_analyst import generate_daily_quant_report
from xsmn_alpha.live.ledger import (
    DEFAULT_LEDGER_PATH,
    initialize_empty_ledger,
    load_benchmark_ledger,
    record_pending_recommendation,
    save_benchmark_ledger,
    settle_ledger_for_date,
)
from xsmn_alpha.live.multi_fetcher import (
    DEFAULT_RAW_ALL_DIR,
    load_station_raw_cache,
    sync_all_35_stations,
)
from xsmn_alpha.live.registry import VALID_35_STATION_CODES
from xsmn_alpha.live.telegram_bot import (
    DEFAULT_TELEGRAM_PREVIEW_PATH,
    dispatch_telegram_briefing,
    format_telegram_executive_briefing,
)
from xsmn_alpha.live.web_publisher import (
    DEFAULT_PUBLIC_DIR,
    publish_daily_web_report,
)
from xsmn_alpha.reporting.html_report import (
    export_dual_station_reports,
    save_stage3_handoff_contract,
)
from xsmn_alpha.schemas import (
    BenchmarkLedgerState,
    CanonicalDrawRecord,
    DataPipelineAuditRecord,
    DualHorizonStationReport,
    HorizonCode,
    Stage3HandoffContract,
    StationCode,
    validate_iso_date,
)


def _configure_utf8_stdio() -> None:
    """Reconfigure stdout and stderr to UTF-8 on Windows PowerShell to prevent cp1252 errors."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8")
            except Exception:
                pass


def _load_or_fetch_canonical_station_draws(
    station_code: str,
    *,
    canonical_dir: Path = Path("data/canonical"),
    raw_dir: Path = Path("data/raw"),
    years: int = 5,
) -> list[CanonicalDrawRecord]:
    """Load canonical draws from disk if present, otherwise fetch from providers and save."""
    canonical_path = canonical_dir / f"{station_code}_canonical.json"
    if canonical_path.exists():
        return load_canonical_draws(canonical_path, station_code=station_code)
    draws = fetch_station_draws(station_code, years=years, raw_dir=raw_dir)
    save_canonical_draws(draws, canonical_path)
    return draws


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser supporting ingest, falsify, and run-pipeline."""
    parser = argparse.ArgumentParser(
        prog="xsmn_alpha.cli",
        description="Giai đoạn 2: Hệ thống Phát hiện Alpha & Dự báo Xác suất Hiệu chuẩn XSMN.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. ingest command
    p_ingest = subparsers.add_parser(
        "ingest",
        help="Thu thập & chuẩn hóa dữ liệu lịch sử 5 năm cho XSHCM và XSVL.",
    )
    p_ingest.add_argument(
        "--stations",
        nargs="+",
        default=["XSHCM", "XSVL"],
        choices=sorted(VALID_STATIONS),
        help="Danh sách mã đài cần thu thập (mặc định: XSHCM XSVL).",
    )
    p_ingest.add_argument(
        "--years",
        type=int,
        default=5,
        help="Số năm lịch sử cần thu thập (mặc định: 5).",
    )
    p_ingest.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/canonical"),
        help="Thư mục lưu dữ liệu chuẩn hóa (mặc định: data/canonical/).",
    )
    p_ingest.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Thư mục lưu cache dữ liệu thô kèm SHA-256 (mặc định: data/raw/).",
    )

    # 2. falsify command
    p_falsify = subparsers.add_parser(
        "falsify",
        help="Chạy Phễu Kiểm Định Thống Kê & Đối chứng 1,000 chuỗi Monte Carlo trên khung 5Y & 3Y.",
    )
    p_falsify.add_argument(
        "--stations",
        nargs="+",
        default=["XSHCM", "XSVL"],
        choices=sorted(VALID_STATIONS),
        help="Danh sách đài mục tiêu (mặc định: XSHCM XSVL).",
    )
    p_falsify.add_argument(
        "--horizons",
        nargs="+",
        default=["5y", "3y"],
        choices=list(VALID_HORIZONS),
        help="Khung thời gian đánh giá (mặc định: 5y 3y).",
    )
    p_falsify.add_argument(
        "--null-sims",
        type=int,
        default=DEFAULT_MONTE_CARLO_SIMS,
        help="Số chuỗi giả lập Monte Carlo Null (mặc định: 1000).",
    )
    p_falsify.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Hạt giống ngẫu nhiên cố định (mặc định: 42).",
    )
    p_falsify.add_argument(
        "--canonical-dir",
        type=Path,
        default=Path("data/canonical"),
        help="Thư mục chứa dữ liệu chuẩn hóa (mặc định: data/canonical/).",
    )

    # 3. run-pipeline command
    p_run = subparsers.add_parser(
        "run-pipeline",
        help="Chạy trọn vẹn Pipeline Giai đoạn 2 + Xuất Báo cáo Đối chiếu & Handoff GĐ 3.",
    )
    p_run.add_argument(
        "--stations",
        nargs="+",
        default=["XSHCM", "XSVL"],
        choices=sorted(VALID_STATIONS),
        help="Danh sách đài mục tiêu (mặc định: XSHCM XSVL).",
    )
    p_run.add_argument(
        "--horizons",
        nargs="+",
        default=["5y", "3y"],
        choices=list(VALID_HORIZONS),
        help="Khung thời gian đánh giá (mặc định: 5y 3y).",
    )
    p_run.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP_DRAWS,
        help="Số kỳ khởi động Walk-Forward (mặc định: 45).",
    )
    p_run.add_argument(
        "--null-sims",
        type=int,
        default=DEFAULT_MONTE_CARLO_SIMS,
        help="Số chuỗi giả lập Monte Carlo Null (mặc định: 1000).",
    )
    p_run.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Hạt giống ngẫu nhiên cố định (mặc định: 42).",
    )
    p_run.add_argument(
        "--out-dir",
        type=Path,
        default=Path("reports"),
        help="Thư mục xuất báo cáo HTML/JSON (mặc định: reports/).",
    )
    p_run.add_argument(
        "--canonical-dir",
        type=Path,
        default=Path("data/canonical"),
        help="Thư mục dữ liệu chuẩn hóa (mặc định: data/canonical/).",
    )
    p_run.add_argument(
        "--handoff-dir",
        type=Path,
        default=Path("data/outputs"),
        help="Thư mục lưu file JSON bàn giao GĐ 3 (mặc định: data/outputs/).",
    )

    # 4. sync-35 command (Stage 3)
    p_sync35 = subparsers.add_parser(
        "sync-35",
        help="Thu thập & cập nhật tăng trưởng kết quả 18 giải cho toàn bộ 35 đài XSMN/XSMT.",
    )
    p_sync35.add_argument(
        "--date",
        type=str,
        default=None,
        help="Ngày mục tiêu YYYY-MM-DD (mặc định: ngày hiện tại).",
    )
    p_sync35.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_ALL_DIR,
        help="Thư mục lưu cache 35 đài kèm SHA-256 (mặc định: data/raw_all/).",
    )
    p_sync35.add_argument(
        "--stations",
        nargs="+",
        default=None,
        choices=sorted(VALID_35_STATION_CODES),
        help="Danh sách mã đài cụ thể cần đồng bộ (mặc định: toàn bộ 35 đài).",
    )
    p_sync35.add_argument(
        "--offline",
        action="store_true",
        help="Chỉ xác thực và nạp từ cache local mà không gọi mạng ngoài.",
    )

    # 5. settle-ledger command (Stage 3)
    p_settle = subparsers.add_parser(
        "settle-ledger",
        help="Đối soát tự động kết quả 18 giải vào Sổ cái Quỹ Chuẩn Tham Chiếu (1.000.000 VNĐ).",
    )
    p_settle.add_argument(
        "--date",
        type=str,
        required=True,
        help="Ngày mở thưởng cần đối soát YYYY-MM-DD (ví dụ: 2026-10-25).",
    )
    p_settle.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Đường dẫn tệp sổ cái Quỹ Chuẩn (mặc định: data/live/benchmark_ledger.json).",
    )
    p_settle.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_ALL_DIR,
        help="Thư mục dữ liệu 35 đài chứa kết quả 18 giải (mặc định: data/raw_all/).",
    )

    # 6. daily-report command (Stage 3)
    p_daily = subparsers.add_parser(
        "daily-report",
        help="Chạy Báo cáo Định lượng 05:00 sáng (Đối soát + Chấm điểm + Web + Telegram).",
    )
    p_daily.add_argument(
        "--date",
        type=str,
        default=None,
        help="Ngày báo cáo mục tiêu YYYY-MM-DD (mặc định: ngày hiện tại).",
    )
    p_daily.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_ALL_DIR,
        help="Thư mục chứa cache lịch sử 35 đài (mặc định: data/raw_all/).",
    )
    p_daily.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Đường dẫn tệp sổ cái Quỹ Chuẩn (mặc định: data/live/benchmark_ledger.json).",
    )
    p_daily.add_argument(
        "--public-dir",
        type=Path,
        default=DEFAULT_PUBLIC_DIR,
        help="Thư mục gốc xuất bản trang Web tĩnh (mặc định: public/).",
    )
    p_daily.add_argument(
        "--preview-path",
        type=Path,
        default=DEFAULT_TELEGRAM_PREVIEW_PATH,
        help="Đường dẫn lưu bản xem trước Telegram (data/live/latest_telegram_preview.txt).",
    )
    p_daily.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="URL gốc của trang Web báo cáo công khai (mặc định đọc từ PUBLIC_REPORT_BASE_URL).",
    )
    p_daily.add_argument(
        "--null-sims",
        type=int,
        default=DEFAULT_MONTE_CARLO_SIMS,
        help="Số chuỗi giả lập Monte Carlo Null (mặc định: 1000).",
    )
    p_daily.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Hạt giống ngẫu nhiên cố định (mặc định: 42).",
    )
    p_daily.add_argument(
        "--send-telegram",
        action="store_true",
        help="Kích hoạt tạo/gửi bản tin chiến thuật 05:00 sáng qua Telegram.",
    )
    p_daily.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy chế độ an toàn không cần Token (lưu bản xem trước Telegram ra file).",
    )
    p_daily.add_argument(
        "--weekly-5-2-mode",
        type=str,
        choices=["auto", "enforce", "off"],
        default="auto",
        help="Chế độ Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu (mặc định: auto).",
    )
    p_daily.add_argument(
        "--ticket-config",
        "--ledger-config",
        dest="ticket_config",
        type=str,
        choices=["auto", "2x2", "sweet_5"],
        default="auto",
        help="Cấu hình bộ số ghi sổ cái Quỹ Chuẩn (auto, 2x2 4 số, hoặc sweet_5 5 số).",
    )

    return parser


def run_ingest_cmd(args: argparse.Namespace) -> int:
    """Execute the 'ingest' subcommand."""
    out_dir: Path = args.out_dir
    raw_dir: Path = args.raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for st in args.stations:
        draws = fetch_station_draws(st, years=args.years, raw_dir=raw_dir)
        out_path = save_canonical_draws(draws, out_dir / f"{st}_canonical.json")
        print(f"[INGEST OK] Đài {st}: Đã xác thực & lưu {len(draws)} kỳ mở thưởng -> {out_path}")
    return 0


def run_falsify_cmd(args: argparse.Namespace) -> int:
    """Execute the 'falsify' subcommand."""
    gatekeeper = FalsificationGatekeeper(null_sims=args.null_sims, seed=args.seed)
    pooler = CalibratedProbabilityPooler()
    summaries = []
    for st in args.stations:
        draws_all = _load_or_fetch_canonical_station_draws(st, canonical_dir=args.canonical_dir)
        for h in args.horizons:
            sliced = slice_horizon(draws_all, station_code=st, horizon=h)
            tens_probs: list[float] | None = None
            units_probs: list[float] | None = None
            if len(sliced) >= MIN_SAMPLE_SIZE_DRAWS:
                tens_counts_all = np.array([d.tens_counts for d in sliced], dtype=np.int64)
                units_counts_all = np.array([d.units_counts for d in sliced], dtype=np.int64)
                last_draw = sliced[-1]
                next_draw_date = _compute_next_expected_draw_date(last_draw.draw_date, st)
                latest_tens_pred = pooler.predict_cage(
                    tens_counts_all,
                    cage_name="tens_cage",
                    target_draw_index=last_draw.draw_index + 1,
                    target_draw_date=next_draw_date,
                )
                latest_units_pred = pooler.predict_cage(
                    units_counts_all,
                    cage_name="units_cage",
                    target_draw_index=last_draw.draw_index + 1,
                    target_draw_date=next_draw_date,
                )
                tens_probs = latest_tens_pred.p_ai
                units_probs = latest_units_pred.p_ai
            rep = gatekeeper.evaluate_station(
                sliced,
                station_code=cast(StationCode, st),
                horizon=cast(HorizonCode, h),
                tens_calibrated_probs=tens_probs,
                units_calibrated_probs=units_probs,
            )
            summaries.append(rep.model_dump())
            t_c = rep.tens_cage
            u_c = rep.units_cage
            print(
                f"[FALSIFY] Đài {st} ({h.upper()}, {rep.sample_size_draws} kỳ): "
                f"status={rep.overall_status} | "
                f"tens_chi2={t_c.observed_chi2_max:.2f} "
                f"(P95={t_c.null_chi2_max_p95:.2f}, BF10={t_c.observed_bf10_max:.3f}) | "
                f"units_chi2={u_c.observed_chi2_max:.2f} "
                f"(P95={u_c.null_chi2_max_p95:.2f}, BF10={u_c.observed_bf10_max:.3f}) | "
                f"multiplier={rep.recommended_capital_multiplier:.2f}x"
            )
    return 0


def run_pipeline_cmd(args: argparse.Namespace) -> int:
    """Execute the 'run-pipeline' subcommand."""
    requested_horizons = (
        list(args.horizons) if getattr(args, "horizons", None) is not None else list(VALID_HORIZONS)
    )
    if not requested_horizons or any(h not in VALID_HORIZONS for h in requested_horizons):
        raise DataIntegrityError(
            f"Invalid horizons {requested_horizons!r}; must be a subset of {VALID_HORIZONS}."
        )

    runner = WalkForwardRunner(
        warmup_draws=args.warmup,
        null_sims=args.null_sims,
        seed=args.seed,
    )
    station_reports: dict[str, DualHorizonStationReport] = {}
    handoff_contracts: dict[str, Stage3HandoffContract] = {}

    for st in args.stations:
        draws_all = _load_or_fetch_canonical_station_draws(st, canonical_dir=args.canonical_dir)
        dual_rep = runner.evaluate_station_dual_horizons(
            draws_all, station_code=st, horizons=requested_horizons
        )
        handoff = build_stage3_handoff_contract(dual_rep, horizons=requested_horizons)
        handoff_path = save_stage3_handoff_contract(handoff, out_dir=args.handoff_dir)
        station_reports[st] = dual_rep
        handoff_contracts[st] = handoff
        horizon_summary_parts = []
        if "5y" in requested_horizons:
            horizon_summary_parts.append(
                f"5Y={dual_rep.horizon_5y.falsification_report.overall_status}"
            )
        if "3y" in requested_horizons:
            horizon_summary_parts.append(
                f"3Y={dual_rep.horizon_3y.falsification_report.overall_status}"
            )
        print(
            f"[PIPELINE] Đài {st}: {', '.join(horizon_summary_parts)} | "
            f"Handoff GĐ 3 -> {handoff_path}"
        )

    json_path, html_path = export_dual_station_reports(
        station_reports,
        handoff_contracts,
        reports_dir=args.out_dir,
    )
    print(f"[REPORT OK] JSON đối chiếu: {json_path}")
    print(f"[REPORT OK] HTML trực quan: {html_path}")
    return 0


def run_sync_35_cmd(args: argparse.Namespace) -> int:
    """Execute the Stage 3 'sync-35' subcommand."""
    target_iso = (
        validate_iso_date(args.date)
        if getattr(args, "date", None) is not None
        else datetime.date.today().isoformat()
    )
    raw_dir: Path = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    draws_by_station, audit = sync_all_35_stations(
        target_date=target_iso,
        raw_dir=raw_dir,
        station_codes=getattr(args, "stations", None),
        offline=bool(getattr(args, "offline", False)),
    )
    print(
        f"[SYNC-35 OK] Đã xác thực & đồng bộ {len(draws_by_station)} đài "
        f"(target_date={target_iso}, fallback_used={audit.fallback_used_count}, "
        f"latest={audit.latest_settled_date}) -> {raw_dir}"
    )
    return 0


def run_settle_ledger_cmd(args: argparse.Namespace) -> int:
    """Execute the Stage 3 'settle-ledger' subcommand."""
    target_iso = validate_iso_date(args.date)
    ledger_path: Path = Path(args.ledger)
    raw_dir: Path = Path(args.raw_dir)

    state = settle_ledger_for_date(
        ledger_path,
        target_iso,
        raw_dir=raw_dir,
        ledger_path=ledger_path,
    )
    settled_entry = next((e for e in state.entries if e.draw_date == target_iso), None)
    hit_k = settled_entry.hit_count_k if settled_entry is not None else 0
    net_vnd = settled_entry.net_profit_vnd if settled_entry is not None else 0
    print(
        f"[SETTLE OK] Ngày {target_iso}: status=SETTLED | K={hit_k} nháy | "
        f"Lãi/Lỗ={net_vnd:+,} VNĐ | Số dư Quỹ Chuẩn={state.current_bankroll_vnd:,} VNĐ "
        f"(Quỹ Lãi Ròng={state.house_money_surplus_vnd:,} VNĐ) -> {ledger_path}"
    )
    return 0


def _build_verified_pipeline_audit(
    raw_dir: Path,
    target_iso: str,
    ledger_state: BenchmarkLedgerState,
) -> DataPipelineAuditRecord:
    """Verify how many of the 35 station cache files in raw_dir exist and pass Gate 1 validation."""
    verified_count = 0
    latest_date_seen = ""
    if raw_dir.is_dir():
        for st_code in VALID_35_STATION_CODES:
            cache_file = raw_dir / f"{st_code}_draws.json"
            if not cache_file.is_file():
                continue
            draws = load_station_raw_cache(
                st_code,
                raw_dir=raw_dir,
                verify_sha256=True,
                allow_unhashed_legacy=True,
            )
            verified_count += 1
            for d in reversed(draws):
                dt_str = str(d.get("draw_date", ""))
                if dt_str < target_iso:
                    if dt_str > latest_date_seen:
                        latest_date_seen = dt_str
                    break

    settled_dates = [
        e.draw_date
        for e in ledger_state.entries
        if e.settlement_status == "SETTLED" and e.draw_date < target_iso
    ]
    if settled_dates and max(settled_dates) > latest_date_seen:
        latest_date_seen = max(settled_dates)
    if not latest_date_seen:
        latest_date_seen = (
            datetime.date.fromisoformat(target_iso) - datetime.timedelta(days=1)
        ).isoformat()

    total_35 = len(VALID_35_STATION_CODES)
    schema_ok = verified_count > 0
    return DataPipelineAuditRecord(
        audit_timestamp_ict=f"{target_iso}T05:00:00+07:00",
        target_date=target_iso,
        total_stations_35=total_35,
        stations_synced_ok=verified_count,
        fallback_used_count=0,
        schema_gate_passed=schema_ok,
        latest_settled_date=latest_date_seen,
        notes_vi=(
            f"Đã kiểm định thực tế thư mục {raw_dir.as_posix()}: "
            f"{verified_count}/{total_35} đài hợp lệ qua DataSchemaGate & SHA-256 "
            f"(kỳ trước gần nhất={latest_date_seen})."
        ),
    )


def run_daily_report_cmd(args: argparse.Namespace) -> int:
    """Execute the Stage 3 'daily-report' subcommand."""
    target_iso = (
        validate_iso_date(args.date)
        if getattr(args, "date", None) is not None
        else datetime.date.today().isoformat()
    )
    raw_dir: Path = Path(args.raw_dir)
    ledger_path: Path = Path(args.ledger)
    public_dir: Path = Path(args.public_dir)
    preview_path: Path = Path(args.preview_path)
    base_url: str | None = getattr(args, "base_url", None)

    # 1. Load or initialize Benchmark Ledger State
    if ledger_path.exists():
        ledger_state = load_benchmark_ledger(ledger_path)
    else:
        ledger_state = initialize_empty_ledger(updated_at=f"{target_iso}T05:00:00+07:00")

    # 2. Auto-settle any PENDING entries strictly before target_iso (< D) if 18 prizes exist
    for entry in list(ledger_state.entries):
        if entry.settlement_status == "PENDING" and entry.draw_date < target_iso:
            try:
                ledger_state = settle_ledger_for_date(
                    ledger_state,
                    entry.draw_date,
                    raw_dir=raw_dir,
                    ledger_path=ledger_path,
                    updated_at=f"{target_iso}T05:00:00+07:00",
                )
            except CapitalDisciplineError:
                raise
            except DataIntegrityError as exc:
                msg = str(exc)
                if (
                    "No 18-prize draw found for station" in msg
                    or "Raw cache file does not exist" in msg
                ):
                    continue
                raise

    # 3. Verify 35-station cache directory and generate Daily Quantitative Report (< D)
    pipeline_audit = _build_verified_pipeline_audit(raw_dir, target_iso, ledger_state)
    weekly_52_mode = str(getattr(args, "weekly_5_2_mode", "auto"))
    ticket_cfg_choice = str(getattr(args, "ticket_config", "auto"))
    report = generate_daily_quant_report(
        target_iso,
        raw_dir=raw_dir,
        ledger_state_or_path=ledger_state,
        pipeline_audit=pipeline_audit,
        null_sims=int(getattr(args, "null_sims", DEFAULT_MONTE_CARLO_SIMS)),
        seed=int(getattr(args, "seed", DEFAULT_RANDOM_SEED)),
        weekly_5_2_mode=weekly_52_mode,  # type: ignore[arg-type]
    )
    if base_url:
        report.telegram_message_html = format_telegram_executive_briefing(
            report,
            public_report_base_url=base_url,
        )

    # 4. Record today's recommendation in the ledger (preserving SETTLED if already settled)
    already_settled_today = any(
        e.draw_date == target_iso and e.settlement_status == "SETTLED" for e in ledger_state.entries
    )
    if ticket_cfg_choice == "sweet_5" and report.primary_station.sweet_5_numbers:
        chosen_cfg_id = "sweet_5"
        chosen_nums = list(report.primary_station.sweet_5_numbers)
    elif ticket_cfg_choice == "2x2" and "2x2" in report.primary_station.ticket_configs:
        chosen_cfg_id = "2x2"
        chosen_nums = list(report.primary_station.ticket_configs["2x2"].selected_numbers)
    else:
        chosen_cfg_id = report.primary_station.recommended_config_id
        chosen_nums = list(report.primary_station.recommended_numbers)

    if already_settled_today:
        save_benchmark_ledger(ledger_state, ledger_path)
    else:
        ledger_state = record_pending_recommendation(
            ledger_state,
            draw_date=target_iso,
            verdict_tier=report.verdict_tier,
            chosen_station_code=report.primary_station.station_code,
            chosen_config_id=chosen_cfg_id,
            selected_numbers=chosen_nums,
            recommended_multiplier=report.capital_guidance.recommended_multiplier,
            lock_flat_1x=(report.weekly_5_2_schedule is not None),
            ledger_path=ledger_path,
            updated_at=report.generated_at_ict,
        )

    # 5. Publish 5-Section Daily HTML, JSON Audit & Index Dashboard
    published_paths = publish_daily_web_report(
        report,
        public_dir=public_dir,
        ledger_state_or_path=ledger_state,
        public_report_base_url=base_url,
    )
    print(
        f"[DAILY-REPORT OK] Ngày {target_iso} ({report.weekday_vn}): "
        f"verdict={report.verdict_tier} | primary={report.primary_station.station_code} "
        f"({report.primary_station.recommended_config_id}: "
        f"{', '.join(report.primary_station.recommended_numbers)}) | "
        f"multiplier={report.capital_guidance.recommended_multiplier:.2f}x"
    )
    print(f"[WEB OK] Daily HTML : {published_paths['daily_html']}")
    print(f"[WEB OK] Daily JSON : {published_paths['daily_json']}")
    print(f"[WEB OK] Index HTML : {published_paths['index_html']}")

    # 6. Dispatch 05:00 AM Telegram Executive Briefing (or save dry-run preview)
    if getattr(args, "send_telegram", False) or getattr(args, "dry_run", False):
        tg_res = dispatch_telegram_briefing(
            report,
            dry_run=bool(getattr(args, "dry_run", False)),
            preview_path=preview_path,
            public_report_base_url=base_url,
        )
        mode_str = "DRY-RUN" if tg_res["dry_run"] else "LIVE"
        print(f"[TELEGRAM {mode_str} OK] Preview -> {tg_res['preview_path']}")

    return 0


_run_daily_report = run_daily_report_cmd


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for python -m xsmn_alpha.cli."""
    _configure_utf8_stdio()
    parser = build_parser()
    parsed = parser.parse_args(list(argv) if argv is not None else None)

    if parsed.command == "ingest":
        return run_ingest_cmd(parsed)
    if parsed.command == "falsify":
        return run_falsify_cmd(parsed)
    if parsed.command == "run-pipeline":
        return run_pipeline_cmd(parsed)
    if parsed.command == "sync-35":
        return run_sync_35_cmd(parsed)
    if parsed.command == "settle-ledger":
        return run_settle_ledger_cmd(parsed)
    if parsed.command == "daily-report":
        return run_daily_report_cmd(parsed)
    raise DataIntegrityError(f"Unsupported CLI command: {parsed.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
