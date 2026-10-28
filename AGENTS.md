# AGENTS.md — Hướng Dẫn Kiến Trúc, Quy Trình SDD & Kỷ Luật Định Lượng (`xsmn-alpha`)

Tài liệu này là bản đồ trung tâm dành cho các kỹ sư và AI Agent làm việc trên kho mã nguồn **`xsmn-alpha`** (`C:\sidehustle\XSTK`).

---

## 1. Tổng Quan Hệ Thống & Triết Lý Thiết Kế

**`xsmn-alpha`** là hệ thống phân tích định lượng, kiểm định giả thuyết lồng cầu, quản trị kỷ luật vốn gia đình và xuất bản báo cáo tự động lúc **05:00 sáng** cho **35 đài Xổ Số Kiến Thiết Miền Nam (`XSMN`, 21 đài) & Miền Trung (`XSMT`, 14 đài)**.

- **100% Toán Học & Thống Kê Tất Định (`Zero LLM API`):** Toàn bộ mô hình xác suất (`BOCD-Dirichlet`, `Markov-Gap`, `Calibration Pooler`, `Monte Carlo Gatekeeper`), bộ lọc **Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu**, bộ giám sát **`Cage Anomaly Sentinel`** và trình sinh ngôn ngữ giải trình (`NLG`) đều vận hành bằng `NumPy` / `SciPy` thuần túy, tái lập 100% (`seed=42`).
- **Kiến Trúc Không Database (`Zero-Database GitOps Static Stack`):** Dữ liệu lịch sử 35 đài (`data/raw_all/<CODE>_draws.json`) và sổ cái đối soát tự động (`data/live/benchmark_ledger.json`) được bảo vệ bằng chữ ký `SHA-256` ngay trong Git, xuất bản báo cáo tĩnh ra `public/` (`GitHub Pages`) và gửi tin nhắn tóm tắt qua `Telegram Bot API` ($\le 4096$ byte UTF-8).
- **Kỷ Luật Điểm Ngọt Gia Đình 5/2 & Khóa Trần Vốn `1.0x` (`Stage 4 Family Discipline`):**
  - Quét toàn bộ 35 đài trên 7 thứ trong tuần nghiêm ngặt trước ngày báo cáo (`draw_date < D`) để xác định **2 thứ có lồng cầu cân bằng nhất tuần** ($\chi^2_{\max}$ thấp nhất) làm **2 ngày nghỉ định kỳ (`SKIP_NO_EDGE`, `0.0x`)**, tiết kiệm `28.6%` chi phí tuần.
  - Trong **5 ngày chơi còn lại trong tuần (`PLAY_STANDARD`, khóa cứng hệ số vốn `1.0x`)**, ưu tiên chọn **1 Đài Chủ Lực** có độ lệch lồng cầu / tín hiệu dị thường vật lý mạnh nhất ngày (ví dụ: Thứ 3 tự động chọn **Bến Tre `XSBT`** với $\chi^2_{\max} = 50.35, BF_{10} = 1.82 \times 10^7$) và cung cấp song song **Bộ 5 số Điểm Ngọt Bà Cô (`sweet_5` — 60.28% ngày lời, vốn `90.000đ/ngày`)** cùng **Bộ 4 số Chuẩn (`2x2` — 52.04% ngày lời, vốn `72.000đ/ngày`)**.

---

## 2. Cấu Trúc Thư Mục & Các Module Cốt Lõi

```text
C:\sidehustle\XSTK\
├── AGENTS.md                                      # Tài liệu hướng dẫn trung tâm cho AI Agent & Developer (File này)
├── QUY_TAC_VA_DIEM_HOA_VON.md                     # [GĐ 1] Quy tắc gốc về dòng tiền, trả thưởng 99.5k/18k & điểm hòa vốn
├── specs/
│   ├── README.md                                  # Chỉ mục tổng hợp các vòng SDD của dự án
│   ├── stage2-alpha-discovery/                    # [GĐ 2] Hồ sơ SDD 5-file: Lõi phát hiện Alpha & hiệu chuẩn 1 lồng cầu
│   ├── stage3-live-family-platform/               # [GĐ 3] Hồ sơ SDD 5-file: Nền tảng 35 đài, Sổ cái Quỹ Chuẩn, Web & Telegram
│   └── stage4-alpha-engine-v2/                    # [GĐ 4] Hồ sơ SDD 5-file: Điểm Ngọt sweet_5, Lịch 5/2, Khóa 1.0x & Cage Anomaly
├── src/xsmn_alpha/
│   ├── constants.py                               # Hệ hằng số bất biến GĐ 1–4, danh mục 35 đài, cấu hình vé Điểm Ngọt
│   ├── exceptions.py                              # Hệ ngoại lệ Fail-Closed (DataIntegrityError, TemporalLeakageError, ...)
│   ├── schemas.py                                 # Hợp đồng Pydantic v2 (StrictBaseModel) & 6 Cổng kiểm soát đối kháng (Gates 1–6)
│   ├── cli.py                                     # Giao diện dòng lệnh hợp nhất (fetch-live, daily-report, backtest, ...)
│   ├── ingest/                                    # Thu thập & chuẩn hóa dữ liệu mở thưởng 18 giải (fetcher.py, canonicalizer.py)
│   ├── features/                                  # Trích xuất đặc trưng nhân quả < D (extractor.py)
│   ├── falsification/                             # Kiểm định Chi-Square, Bayes Factor BF10, Entropy & Monte Carlo Null (gatekeeper.py)
│   ├── engine/                                    # Hội đồng xác suất BOCD-Dirichlet + Markov-Gap + Calibration Pooler
│   ├── backtest/                                  # Kiểm định Walk-Forward OOS & mô phỏng danh mục Điểm Ngọt (sweet_spot_sim.py)
│   ├── reporting/                                 # Xuất báo cáo HTML kiểm định GĐ 2 (html_report.py)
│   └── live/                                      # Luồng vận hành 05:00 sáng: registry.py, multi_fetcher.py, ledger.py,
│                                                  # daily_analyst.py, telegram_bot.py, web_publisher.py
└── tests/                                         # Bộ 11 tệp kiểm thử tự động (167 bài test — Độ phủ > 90%)
```

---

## 3. Các Câu Lệnh Thực Thi Chuẩn (`Standard Commands`)

Luôn chạy mọi công cụ qua `uv run ...` tại thư mục gốc `C:\sidehustle\XSTK`:

```powershell
# 1. Đồng bộ môi trường Python 3.11 + uv
uv sync --all-extras

# 2. Chạy toàn bộ 167 bài kiểm thử (Stage 2 + Stage 3 + Stage 4) kèm cổng kiểm tra độ phủ >= 90%
uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90

# 3. Chạy kiểm tra chất lượng mã nguồn & định dạng (Ruff Lint & Format)
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 4. Chạy báo cáo định lượng 05:00 sáng ở chế độ Dry-Run (không cần token thật)
uv run python -m xsmn_alpha.cli daily-report --date 2026-10-27 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run
```

---

## 4. Ranh Giới & Quy Tắc Bất Biến Cho AI Agent (`Mandatory Guardrails`)

1. **Chống Rò Rỉ Tương Lai Tuyệt Đối (`Gate 2 — PreDrawCutoffGate`):** Mọi phép tính đặc trưng, kiểm định thống kê lồng cầu, xếp hạng Lịch Chơi 5/2 và chọn số cho ngày $D$ bắt buộc chỉ dùng dữ liệu có `draw_date < D`.
2. **Bảo Toàn Tương Thích Ngược (`100% Backward Compatibility`):** Không bao giờ xóa, skip (`@pytest.mark.skip`), hoặc làm yếu các bài kiểm thử của Giai đoạn 2, 3, 4; giữ nguyên cấu trúc các hằng số gốc (`SWEET_SPOT_CONFIGS`, `EXTENDED_SWEET_SPOT_CONFIGS`, `STAGE3_TICKET_CONFIGS`, `STAGE4_SWEET_SPOT_CONFIGS`) và khả năng đọc sổ cái `data/live/benchmark_ledger.json`.
3. **Khóa Trần Kỷ Luật Vốn Gia Đình `1.0x` (`Gate 6 — Weekly52AndFlatStakeGate`):** Trong luồng báo cáo hàng ngày Giai đoạn 4 (`lock_flat_1x=True`), tuyệt đối không phát sinh hệ số đi vốn `> 1.0x` hay gợi ý đánh gấp thếp sau ngày trượt.
4. **An Toàn Kênh Hiển Thị (`Telegram <= 4096 UTF-8 bytes & HTML Escape`):** Mọi chuỗi động đưa vào `telegram_bot.py` và `web_publisher.py` phải được escape qua `html.escape(..., quote=True)` và kiểm tra giới hạn byte UTF-8 trước khi xuất bản.
