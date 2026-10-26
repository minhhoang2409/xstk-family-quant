# Implementation Plan: Giai Đoạn 3 — Chuyên Viên Báo Cáo Định Lượng Tự Động 5h Sáng & Trang Web Giải Trình Chi Tiết (`stage3-live-family-platform`)

**Mã Module:** `stage3-live-family-platform`  
**Trạng thái:** Completed — Verified 100% PASS (Pha 4: VERIFY)  
**Ngày cập nhật:** 2026-10-27  
**Tài liệu đặc tả gốc:** [`specs/stage3-live-family-platform/spec.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/spec.md)  
**Danh sách tác vụ chi tiết:** [`specs/stage3-live-family-platform/todo.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/todo.md)

---

## Overview

Triển khai trọn vẹn hệ thống **"Chuyên viên Báo cáo Định lượng Trung thực Tự động 100%" (`Automated 05:00 AM Quantitative Reporter & Web Audit Platform`)** vận hành hoàn toàn bằng code Toán học & Thống kê thuần túy (`NumPy`/`SciPy` — tuyệt đối không dùng AI/LLM API và không dùng Database ngoài). Hệ thống mở rộng lõi định lượng sang toàn bộ **35 đài XSMN & XSMT** (21 đài Miền Nam mở thưởng `16:15 ICT` + 14 đài Miền Trung mở thưởng `17:15 ICT`) cùng **5 cấu hình bộ số ngọt chuẩn** (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`), tự động thu thập kết quả 18 giải mới nhất có chuyển đổi dự phòng 3 tầng, tự động đối soát sổ cái của **Quỹ Chuẩn Tham Chiếu (`1.000.000 VNĐ`)** theo kỷ luật bảo toàn vốn gốc **CPPI / House-Money**, chấm điểm nhân quả nghiêm ngặt các đài mở thưởng trong ngày (`draw_date < D`), sinh lời văn giải trình định lượng tất định tiếng Việt, xuất bản **Trang Web Báo Cáo Giải Trình Chi Tiết 5 Khu Vực** (`public/daily/YYYY-MM-DD.html` & `public/index.html`) và gửi **Bản Tin Chiến Thuật lúc 05:00 sáng qua Telegram** trả lời trực diện 4 câu hỏi cốt lõi cho gia đình.

---

## Architecture Decisions

- **AD-01 — Bảo toàn Tương thích Ngược 100% với Giai đoạn 2 (`Additive Extension Pattern`):**
  - Giữ nguyên bất biến `STATION_CONFIG` (`XSHCM`, `XSVL`), `VALID_STATIONS` và 8 cấu hình gốc trong `SWEET_SPOT_CONFIGS` của [`src/xsmn_alpha/constants.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/constants.py) để toàn bộ bộ kiểm thử Giai đoạn 2 hiện hữu tiếp tục vượt qua 100% mà không sửa bất kỳ assertion cũ nào.
  - Bổ sung danh mục 35 đài `STATION_REGISTRY_35` (`VALID_35_STATION_CODES`), cấu hình đối xứng `"4x1"` (Top 4 Chục $\times$ Top 1 Đơn vị = 4 số) trong `STAGE3_TICKET_CONFIGS` / `EXTENDED_SWEET_SPOT_CONFIGS`, và đóng gói toàn bộ nghiệp vụ Giai đoạn 3 vào gói mô-đun mới [`src/xsmn_alpha/live/`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/).
- **AD-02 — Kiến trúc Không Database Siêu Bền Bỉ (`Zero-Database GitOps Static Stack`):**
  - Toàn bộ lịch sử 35 đài (`data/raw_all/<CODE>_draws.json`) và sổ cái đối soát của Quỹ Chuẩn Tham Chiếu (`data/live/benchmark_ledger.json`) được lưu trữ dưới dạng tệp JSON chuẩn hóa kèm chữ ký kiểm chuẩn `SHA-256`.
  - Không yêu cầu người dùng nhập số dư cá nhân lên Web; thay vào đó, hệ thống đối soát tự động trên **Quỹ Chuẩn `1.000.000 VNĐ`** (`1.0x = 72.000 VNĐ/ngày` cho bộ 4 số, trúng 1 nháy thu `87.500 VNĐ`) và xuất sẵn **Bảng quy đổi tiền VNĐ mẫu** cho 4 mức vốn gia đình (`500.000đ`, `1.000.000đ`, `2.000.000đ`, `5.000.000đ`).
- **AD-03 — Năm Cổng Kiểm Soát Chống Gian Lận (`5 Fail-Closed Adversarial Gates`):**
  - Kết hợp 4 cổng từ Giai đoạn 2 (`DataSchemaGate`, `PreDrawCutoffGate`, `SimplexCalibrationGate`, `FalsificationCashBrakeGate`) với cổng thứ 5 mới **`HouseMoneyAndLedgerIntegrityGate`** (`CapitalDisciplineError` & `DataIntegrityError`): khóa cứng $m_D = 0.0\text{x}$ khi cầu nhiễu trắng (`SKIP_NO_EDGE`), chỉ cho phép nâng hệ số lên `1.25x` / `1.5x` khi Quỹ Lãi Ròng $C_{D-1} \ge 144.000\text{ VNĐ}$ sao cho $\Delta \text{Cost}_D \le 0.50 \times C_{D-1}$ và $W_{D-1} - \text{Cost}_D \ge W_0$, đồng thời đảm bảo đối soát sổ cái lũy đẳng (`Idempotent Settlement`).
- **AD-04 — Sinh Lời Giải Trình Định Lượng Tất Định (`100% Deterministic Quantitative NLG — Zero AI API`):**
  - Toàn bộ nhận định trong bản tin Telegram và trên trang Web đều được lắp ghép tất định từ chính các con số thống kê thực tế của ngày $D$ ($\text{JointR1}\%$, tần suất nổ bóng Hạng 1 ngoài mẫu của từng lồng so với mốc hòa vốn $10.6904\%$, thống kê $\chi^2_{\max}$ so với phân vị Monte Carlo Null $P_{90}/P_{95}$, Hệ số Bayes $BF_{10}$, độ dài chế độ `BOCD` $r^*_{t-1}$ và OOS ROI 3 năm), đảm bảo khớp 1:1 với bảng biểu kiểm toán.
- **AD-05 — Xuất Bản Tĩnh Đa Kênh & Chế Độ `--dry-run` An Toàn (`Telegram Executive Briefing + 5-Section Web Audit`):**
  - Tách biệt rõ bản tin tóm tắt chiến thuật gửi qua Telegram lúc `05:00 ICT` (trả lời ngắn gọn 4 câu hỏi cốt lõi + link Web) và trang Web báo cáo giải trình chi tiết 5 khu vực (`public/daily/YYYY-MM-DD.html` & `public/index.html`). Khi chạy local với `--dry-run`, toàn bộ pipeline toán học và xuất Web hoạt động 100% và lưu bản xem trước tin nhắn vào `data/live/latest_telegram_preview.txt`.

---

## Dependency Graph

```text
[Task 1: constants.py + exceptions.py + live/registry.py + sweet_spot_sim.py (4x1)]
    │
    └──► [Task 2: schemas.py (Stage 3 Contracts + Gate 4 & Gate 5 Validators)]
             │
             ├──► [Task 3: live/multi_fetcher.py (35-Station Incremental Sync + 3-Tier Failover + SHA-256)]
             │        │
             ├──► [Task 4: live/ledger.py (Benchmark 1M Ledger + Idempotent Settlement + House-Money Gate 5)]
             │        │
             │        └──► [Task 5: live/daily_analyst.py (Pre-Draw < D Station Scoring + 5-Config Selector)]
             │                 │
             │                 └──► [Task 6: live/daily_analyst.py (Deterministic Quantitative NLG 4 Questions)]
             │                          │
             │                          ├──► [Task 7: live/web_publisher.py (5-Section Daily HTML + Index Dashboard)]
             │                          │
             │                          └──► [Task 8: live/telegram_bot.py (05:00 AM Briefing + Dry-Run + HTML Escape)]
             │                                   │
             └───────────────────────────────────┴──► [Task 9: cli.py + .github/workflows/daily_quant_report.yml + E2E Run]
```

---

## Task List

### Phase 1: Foundation, 35-Station Registry, Symmetric `4x1` Config & Multi-Source Fetcher (Trụ cột 1)
- [x] **Task 1:** Mở rộng hằng số Giai đoạn 3, ngoại lệ `CapitalDisciplineError`, cấu hình đối xứng `4x1` & danh mục chuẩn 35 đài (`constants.py`, `exceptions.py`, `live/registry.py`, `backtest/sweet_spot_sim.py`)
- [x] **Task 2:** Thiết lập hợp đồng dữ liệu Pydantic v2 Giai đoạn 3 kèm cổng `FalsificationCashBrakeGate` & `HouseMoneyAndLedgerIntegrityGate` (`schemas.py`, `tests/test_stage3_registry_and_4x1.py`)
- [x] **Task 3:** Xây dựng trình thu thập tăng trưởng đa nguồn 35 đài `multi_fetcher.py` kèm Failover 3 tầng & chữ ký `SHA-256` (`live/multi_fetcher.py`, `tests/test_stage3_registry_and_4x1.py`)

### Checkpoint 1: Foundation, 35-Station Registry & Multi-Source Fetcher (Sau Tasks 1–3)
- [x] Toàn bộ bài kiểm thử Giai đoạn 2 hiện hữu tiếp tục vượt qua 100% (`uv run pytest tests/ -v`)
- [x] `STATION_REGISTRY_35` định nghĩa chuẩn xác 35 đài (21 XSMN `16:15` + 14 XSMT `17:15`), lịch quay Thứ 2 $\to$ Chủ Nhật (5–7 đài/ngày) và `sweet_spot_sim.py` tính toán chính xác cấu hình đối xứng `4x1`
- [x] `multi_fetcher.py` đồng bộ tăng trưởng, chuyển đổi dự phòng `minhngoc` $\to$ `xskt` $\to$ `xoso` và chặn đứng dữ liệu bẩn qua `DataSchemaGate`

### Phase 2: Benchmark Settlement Ledger, House-Money Engine & Daily Station Analyst + NLG (Trụ cột 2 & 3)
- [x] **Task 4:** Xây dựng bộ quản lý Sổ cái Quỹ Chuẩn Tham Chiếu (`1.000.000 VNĐ`) & Động cơ Đi vốn CPPI / House-Money (`live/ledger.py`, `tests/test_stage3_ledger_and_house_money.py`)
- [x] **Task 5:** Xây dựng Chuyên viên Chấm điểm Đài Hàng ngày khóa chặt `PreDrawCutoffGate` (`draw_date < D`) (`live/daily_analyst.py`, `tests/test_stage3_daily_analyst_and_nlg.py`)
- [x] **Task 6:** Xây dựng Bộ sinh Lời giải trình Định lượng Tất định Tiếng Việt (`Deterministic Quantitative NLG`) trả lời 4 câu hỏi cốt lõi (`live/daily_analyst.py`, `tests/test_stage3_daily_analyst_and_nlg.py`)

### Checkpoint 2: Benchmark Ledger, House-Money Sizing & Daily Analyst + NLG (Sau Tasks 4–6)
- [x] Sổ cái `benchmark_ledger.json` đối soát chính xác 18 giải, bảo toàn phương trình kế toán $W_t = W_{t-1} + \text{Rev}_t - \text{Cost}_t$, kiểm tra `sha256` và đảm bảo tính lũy đẳng (`Idempotent`)
- [x] Cổng `HouseMoneyAndLedgerIntegrityGate` chặn đứng mọi hành vi nâng hệ số vốn $> 1.0\text{x}$ khi Quỹ Lãi Ròng $< 144.000\text{ VNĐ}$ hoặc nguy cơ lẹm vốn gốc `1.000.000 VNĐ` (`CapitalDisciplineError`)
- [x] `daily_analyst.py` chấm điểm 5–7 đài mở thưởng trong ngày hoàn toàn tất định dưới khóa `draw_date < D` (`TemporalLeakageError` nếu vi phạm) và sinh lời văn giải trình tiếng Việt khớp 1:1 với số liệu

### Phase 3: Static Web Audit Publisher, 05:00 AM Telegram Dispatcher, CLI & GitOps Workflow (Trụ cột 4 & 5)
- [x] **Task 7:** Xây dựng Trình xuất Trang Web Báo cáo Giải trình Chi tiết 5 Khu vực & Trang chủ Dashboard (`live/web_publisher.py`, `tests/test_stage3_web_and_telegram.py`)
- [x] **Task 8:** Xây dựng Trình phát Bản tin Chiến thuật 05:00 Sáng qua Telegram Bot API kèm chế độ `--dry-run` (`live/telegram_bot.py`, `tests/test_stage3_web_and_telegram.py`)
- [x] **Task 9:** Tích hợp CLI (`sync-35`, `settle-ledger`, `daily-report`), Workflow GitHub Actions 05:00 Sáng & Nghiệm thu Toàn tuyến E2E (`cli.py`, `.github/workflows/daily_quant_report.yml`, `data/live/`, `public/`)

### Checkpoint 3: Complete Stage 3 End-to-End Verification & Acceptance (Sau Tasks 7–9)
- [x] Xuất thành công `public/daily/YYYY-MM-DD.html`, `public/daily/YYYY-MM-DD.json`, `public/index.html` đủ 5 khu vực bằng chứng toán học và `data/live/latest_telegram_preview.txt` đủ 4 câu hỏi cốt lõi + link Web
- [x] Toàn bộ bộ kiểm thử tự động (Stage 2 + Stage 3 PASS & Negative Mutation FAIL) đạt `100% PASS` với độ phủ mã nguồn $\ge 90\%$ (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`)
- [x] Kiểm tra chất lượng mã nguồn `uv run ruff check src/ tests/` và `uv run ruff format --check src/ tests/` đạt `0 errors`
- [x] Hoàn tất nghiệm thu với Chủ dự án trên cả 8 tiêu chí `SC-01` $\to$ `SC-08` tại Mục 9 của `spec.md`

---

## Parallelization Opportunities

- **Phải thực hiện tuần tự (`Sequential Foundation & Core Contracts`):**
  - `Task 1` $\rightarrow$ `Task 2` (Thiết lập hằng số Giai đoạn 3, danh mục 35 đài, cấu hình `4x1` và hợp đồng dữ liệu Pydantic v2).
  - `Task 5` $\rightarrow$ `Task 6` (Chấm điểm toán học các đài mở thưởng trong ngày trước khi lắp ghép lời văn giải trình tất định).
  - `Task 9` (Tích hợp CLI hợp nhất và chạy kiểm nghiệm E2E sau khi tất cả các mô-đun trong `src/xsmn_alpha/live/` đã hoàn tất).
- **Có thể thực hiện song song sau khi xong `Task 2` (`Parallel Feature Slices`):**
  - **Luồng A (Thu thập dữ liệu 35 đài):** `Task 3` (`live/multi_fetcher.py`).
  - **Luồng B (Sổ cái đối soát & Quản trị vốn House-Money):** `Task 4` (`live/ledger.py`).
- **Có thể thực hiện song song sau khi xong `Task 6` (`Parallel Output Channels`):**
  - **Luồng C (Xuất bản Trang Web Báo cáo 5 Khu vực):** `Task 7` (`live/web_publisher.py`).
  - **Luồng D (Bản tin Chiến thuật Telegram 05:00 Sáng):** `Task 8` (`live/telegram_bot.py`).

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
| :--- | :---: | :--- |
| **R1: Nguồn web xổ số đang quay dở hoặc lỗi mạng khiến kỳ quay thiếu giải ($< 18$ giải)** | High | Áp dụng `DataSchemaGate` kiểm tra đủ 18 giải ASCII `00`–`99` và tự động failover qua 3 nguồn độc lập (`minhngoc.net.vn` $\to$ `xskt.com.vn` $\to$ `xoso.com.vn`); tuyệt đối không ghi bản ghi thiếu giải vào `data/raw_all/`. |
| **R2: Rò rỉ dữ liệu ngày mở thưởng (`Look-Ahead Leakage` $\ge D$) khi chấm điểm đài lúc 05:00 sáng** | High | Cài đặt `PreDrawCutoffGate` ngay đầu mọi hàm chấm điểm trong `daily_analyst.py` kiểm tra `all(r.draw_date < target_date for r in history_draws)`, ném `TemporalLeakageError` ngay lập tức nếu vi phạm. |
| **R3: Rủi ro lẹm vốn gốc `1.000.000 VNĐ` hoặc cộng/trừ tiền trùng lặp khi chạy lại lệnh đối soát** | High | Cài đặt `HouseMoneyAndLedgerIntegrityGate` khóa cứng điều kiện nâng vốn ($C_{D-1} \ge 144.000\text{đ}$, $\Delta \text{Cost}_D \le 0.50 \times C_{D-1}$, $W_{D-1} - \text{Cost}_D \ge W_0$) và thiết kế `settle-ledger` lũy đẳng (`Idempotent`) kèm kiểm tra chữ ký `SHA-256`. |
| **R4: Phá vỡ tương thích ngược với 6 tệp kiểm thử Giai đoạn 2 khi mở rộng lên 35 đài và thêm cấu hình `4x1`** | Medium | Giữ nguyên `VALID_STATIONS`, `STATION_CONFIG` và `SWEET_SPOT_CONFIGS` cho Giai đoạn 2; định nghĩa `VALID_35_STATION_CODES`, `STATION_REGISTRY_35`, `STAGE3_TICKET_CONFIGS` và `EXTENDED_SWEET_SPOT_CONFIGS` song song. |
| **R5: Lỗi cú pháp HTML Telegram (`400 Bad Request: can't parse entities`) hoặc XSS trên trang Web tĩnh** | Medium | Sử dụng `html.escape` cho mọi chuỗi động trước khi đưa vào template Telegram HTML và Web HTML, kiểm tra giới hạn $\le 4096$ ký tự UTF-8 và kiểm thử đột biến âm với chuỗi `<script>alert(1)</script>`. |

---

## Open Questions

- **Không còn câu hỏi mở nào.** Toàn bộ quy tắc toán học, ngưỡng lọc `JointR1 >= 1.105%`, quy tắc đi vốn CPPI / House-Money trên Quỹ Chuẩn `1.000.000 VNĐ`, danh mục 35 đài XSMN/XSMT và cấu trúc 4 câu hỏi cốt lõi trên Telegram + 5 khu vực trên Trang Web đã được khóa hoàn toàn tại [`spec.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/spec.md).
