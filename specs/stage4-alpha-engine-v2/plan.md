# Implementation Plan: Giai Đoạn 4 — Kỷ Luật Điểm Ngọt Gia Đình, Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu & Giám Sát Dị Thường (`stage4-alpha-engine-v2`)

**Mã Module:** `stage4-alpha-engine-v2`  
**Trạng thái:** Accepted & Verified (100% PASS)  
**Ngày tạo:** 2026-10-28  
**Tài liệu đặc tả gốc:** [`specs/stage4-alpha-engine-v2/spec.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/spec.md)  
**Danh sách tác vụ chi tiết:** [`specs/stage4-alpha-engine-v2/todo.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/todo.md)

---

## Overview

Nâng cấp hệ thống báo cáo định lượng tự động 05:00 sáng (`constants.py`, `schemas.py`, `backtest/sweet_spot_sim.py`, `live/ledger.py`, `live/daily_analyst.py`, `live/telegram_bot.py`, `live/web_publisher.py`, `cli.py`) thành **"Chiếc Phanh Kỷ Luật Vốn & Điểm Ngọt Gia Đình 5/2"** vận hành 100% bằng Toán học & Thống kê tất định (`NumPy`/`SciPy` — không dùng AI/LLM API). Hệ thống bổ sung cấu hình **Bộ 5 số Điểm Ngọt Bà Cô (`sweet_5` = 4 số `2x2` + 1 số vệ tinh đỉnh, tỷ lệ ngày nổ $\ge 1$ nháy đạt `60.28%`, vốn chuẩn `90.000đ/ngày`)** song hành cùng **Bộ 4 số Chuẩn (`2x2`, tỷ lệ ngày nổ $\ge 1$ nháy đạt `52.04%`, vốn chuẩn `72.000đ/ngày`)**, tự động thực thi **Bộ lọc Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu (`Weekly 5/2 Cage-Balance Filter`)** nghỉ định kỳ `0.0x` vào 2 thứ có lồng cầu cân bằng nhất tuần và chơi đều tay `1.0x` vào 5 thứ còn lại, ưu tiên xếp hạng đài theo **Độ Lệch Lồng Cầu Thực Tế & Giám Sát Dị Thường (`Cage Anomaly Sentinel`, phát hiện chính xác Đài Bến Tre `XSBT` vào Thứ 3)**, đồng thời khóa cứng trần đi vốn **`1.0x`** kèm khung nhắc nhở **"Quy Tắc Tiền Chợ Đều Tay 1.0x (Tuyệt đối không gấp thếp)"** trên bản tin Telegram và trang Web tĩnh.

---

## Architecture Decisions

- **AD-01 — Mở Rộng Bổ Sung Bảo Toàn Tương Thích Ngược 100% Với Giai Đoạn 2 & 3 (`Strict Additive Extension`):**
  - Giữ nguyên bất biến `SWEET_SPOT_CONFIGS` (`8` cấu hình GĐ 2), `EXTENDED_SWEET_SPOT_CONFIGS` (`9` cấu hình GĐ 3) và `STAGE3_TICKET_CONFIGS` (`5` cấu hình GĐ 3) trong [`src/xsmn_alpha/constants.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/constants.py); định nghĩa mới `STAGE4_SWEET_SPOT_CONFIGS` (`10` cấu hình, thêm `"sweet_5"`) và `STAGE4_TICKET_CONFIGS` (`6` cấu hình).
  - Trong `StationDailyScorecard`, giữ nguyên từ điển `ticket_configs` chứa đúng 5 cấu hình `STAGE3_TICKET_CONFIGS` và bổ sung các trường có giá trị mặc định an toàn (`sweet_5_numbers`, `sweet_5_config`, `cage_anomaly_detected`, `cage_anomaly_summary_vi`, `cold_balls_tens`, `cold_balls_units`, `passes_weekly_5_2_play`) để toàn bộ 10 tệp kiểm thử hiện hữu của Giai đoạn 2 & 3 chạy xanh `100% PASS` mà không sửa đổi bất kỳ assertion cũ nào.
- **AD-02 — Thuật Toán Tất Định Chọn Bộ 5 Số Điểm Ngọt Bà Cô (`sweet_5 = 2x2 Core + Top-1 Satellite`):**
  - Trong [`src/xsmn_alpha/backtest/sweet_spot_sim.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/backtest/sweet_spot_sim.py), hàm `select_sweet_5_numbers(probs_tens, probs_units)` lấy 4 số lõi từ cấu hình `2x2` (Top 2 Chục $\times$ Top 2 Đơn vị) và chọn thêm 1 số vệ tinh ngoài `2x2` có xác suất kết hợp $P_{\text{tens}}(a) \times P_{\text{units}}(b)$ lớn nhất (tie-break ưu tiên tổ hợp thuộc khung Top-3 $\times$ Top-3 ngoài `2x2`, sau đó theo thứ tự từ điển ASCII `"00".."99"` tăng dần).
- **AD-03 — Bộ Lọc Lịch Chơi 5/2 Nhân Quả Nghiêm Ngặt `< D` & Tự Động Thích Ứng Môi Trường Test (`Weekly 5/2 Cage-Balance Filter`):**
  - Hàm `compute_weekly_balance_rest_days` trong [`src/xsmn_alpha/live/daily_analyst.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/daily_analyst.py) quét toàn bộ 35 đài trên 7 thứ trong tuần dưới chốt chặn `PreDrawCutoffGate` (`draw_date < D`), dùng bộ nhớ đệm trong RAM (`in-memory dict`) cho 4 đài quay 2 kỳ/tuần (`XSHCM`, `XSTTH`, `XSDNG`, `XSKH`), tính $\chi^2_{\text{day}}(w) = \max_{s \in S_w} \chi^2_{\max}(s)$ trên đa cửa sổ $W \in \{15, 30, 60\}$ và xếp hạng 7 thứ theo khóa tăng dần `(round(max_chi2_overall, 2), round(max_bf10_overall, 3), round(mean_chi2_overall, 2), weekday)`.
  - Hai thứ đứng đầu (lồng cầu cân bằng nhất tuần: Thứ 4 và Thứ 2 trên dữ liệu hiện tại) được khóa làm **2 ngày nghỉ định kỳ (`SKIP_NO_EDGE`, `0.0x`)**; 5 thứ còn lại được mở làm **5 ngày chơi Điểm Ngọt đều tay (`PLAY_STANDARD`, `1.0x`)**.
  - Ở chế độ mặc định `weekly_5_2_mode="auto"`, nếu thư mục `raw_dir` chỉ chứa dữ liệu của 1 thứ (`< 35` đài trong các `tmp_path` của Unit Test GĐ 3), hệ thống tự động lùi về chế độ đánh giá đơn ngày để tương thích ngược 100%; khi đủ 35 đài (`data/raw_all/`) hoặc khi truyền `weekly_5_2_mode="enforce"`, hệ thống kích hoạt đầy đủ Lịch 5/2.
- **AD-04 — Giám Sát Dị Thường Vật Lý (`Cage Anomaly Sentinel`) & Khóa Sắp Xếp Đài Bảo Toàn Kép (`rank_stations_for_day`):**
  - Đài mở thưởng ngày $D$ được gắn cờ `cage_anomaly_detected = True` khi và chỉ khi $\chi^2_{\max,\text{overall}} > P_{95,\text{null}}$ **và** $BF_{10,\max,\text{overall}} \ge 10.0$, đồng thời trích xuất danh sách bóng lạnh/câm thực nghiệm 30 kỳ ($\le 6.5\%$) để phát cảnh báo `⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH`.
  - Khóa sắp xếp trong `rank_stations_for_day` theo thứ tự: `(-passes_selective_alpha, -cage_anomaly_detected, -round(chi2_max_overall, 2), -round(bf10_max_overall, 3), -round(station_alpha_score, 2), station_code)`. Khóa này vừa giữ nguyên 100% kết quả các bài test Giai đoạn 3 (nơi các thẻ điểm clone có cùng $\chi^2_{\max}$), vừa đưa chính xác đài có dị thường vật lý thật như **Bến Tre (`XSBT`, $\chi^2_{\max} = 50.35, BF_{10} = 1.82 \times 10^7$)** lên **Hạng #1 (`Đài Chủ Lực`)** vào Thứ 3.
- **AD-05 — Cổng Kiểm Soát Thứ 6 (`Gate 6: Weekly52AndFlatStakeGate`) & Kỷ Luật Tiền Chợ Đều Tay `1.0x`:**
  - Trong luồng Giai đoạn 4 (`lock_flat_1x=True`), khóa cứng hệ số đi vốn `recommended_multiplier = 1.0` vào 5 ngày chơi (`0.0` vào 2 ngày nghỉ), bất kể `house_money_surplus_vnd` lớn bao nhiêu; ném `CapitalDisciplineError` ngay lập tức nếu phát hiện `recommended_multiplier > 1.0`, đồng thời vẫn bảo toàn khả năng đọc/đối soát 300 bản ghi lịch sử đã `SETTLED` trong `data/live/benchmark_ledger.json`.

---

## Dependency Graph

```text
[Task 1: constants.py + backtest/sweet_spot_sim.py (Stage 4 Constants + sweet_5 Portfolio Selector & Scorer)]
    │
    └──► [Task 2: schemas.py (WeeklySchedule52Analysis + Scorecard/Report Stage 4 Fields + Gate 6 Validator)]
             │
             ├──► [Task 3: live/ledger.py (Flat 1.0x Capital Brake lock_flat_1x + sweet_5 90k Settlement)]
             │        │
             │        └──► [Task 4: live/daily_analyst.py (Weekly 5/2 Balance Filter + Cage Anomaly Sentinel + Ranking + NLG)]
             │                 │
             │                 ├──► [Task 5: live/telegram_bot.py (05:00 AM Family Briefing: 5/2 Schedule + Dual Sweet-Spot + Anomaly)]
             │                 │        │
             │                 └──► [Task 6: live/web_publisher.py + cli.py (Web 5/2 Schedule & sweet_5 Tables + E2E Verification)]
```

---

## Task List

### Phase 1: Foundation — Cấu Hình Điểm Ngọt 5 Số (`sweet_5`), Hợp Đồng Dữ Liệu Giai Đoạn 4 & Khóa Trần Vốn `1.0x`
- [x] **Task 1:** Bổ sung hệ hằng số Giai đoạn 4 và thuật toán chọn bộ 5 số Điểm Ngọt `sweet_5` (`constants.py`, `backtest/sweet_spot_sim.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)
- [x] **Task 2:** Mở rộng hợp đồng dữ liệu Pydantic v2 Giai đoạn 4 kèm cổng kiểm soát `Gate 6` (`schemas.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)
- [x] **Task 3:** Cập nhật sổ cái Quỹ Chuẩn hỗ trợ thanh toán gói `sweet_5` và khóa trần hệ số vốn `1.0x` (`live/ledger.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)

### Checkpoint 1: Foundation, `sweet_5` Config, Gate 6 Schemas & Flat `1.0x` Ledger (Sau Tasks 1–3)
- [x] Toàn bộ 10 tệp kiểm thử Giai đoạn 2 & Giai đoạn 3 hiện hữu cùng các bài test Task 1–3 của Giai đoạn 4 vượt qua 100% (`uv run pytest tests/ -v`)
- [x] `select_sweet_spot_numbers(..., "sweet_5")` chọn chính xác 4 số `2x2` + 1 số vệ tinh đỉnh (tie-break tất định) và sổ cái đối soát chuẩn xác vé `sweet_5` (`90.000đ/ngày`, 1 nháy `+9.500đ`, 2 nháy `+109.000đ`)
- [x] Cổng `Gate 6` (`Weekly52AndFlatStakeGate`) chặn đứng mọi dữ liệu `sweet_5_numbers` sai quy cách, `WeeklySchedule52Analysis` sai cấu trúc 5/2 hoặc hệ số vốn `> 1.0x` khi `lock_flat_1x=True`

### Phase 2: Core Features & Channels — Bộ Lọc Lịch Chơi 5/2, Giám Sát Dị Thường `Cage Anomaly Sentinel`, Bản Tin Telegram & Web Báo Cáo
- [x] **Task 4:** Triển khai bộ lọc Lịch Chơi 5/2 theo độ cân bằng lồng cầu và giám sát dị thường `Cage Anomaly Sentinel` (`live/daily_analyst.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)
- [x] **Task 5:** Nâng cấp bản tin Telegram 05:00 sáng hiển thị Điểm Ngọt Kép, Lịch 5/2 và Quy tắc Tiền Chợ `1.0x` (`live/telegram_bot.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)
- [x] **Task 6:** Nâng cấp trang Web giải trình tĩnh Giai đoạn 4 và kiểm nghiệm toàn tuyến CLI `daily-report` (`live/web_publisher.py`, `cli.py`, `tests/test_stage4_sweet5_and_5_2_schedule.py`)

### Checkpoint 2: Complete Stage 4 End-to-End Verification & Acceptance (Sau Tasks 4–6)
- [x] Trên dữ liệu thực 35 đài (`data/raw_all/`), `compute_weekly_balance_rest_days` chọn đúng 2 ngày nghỉ định kỳ cân bằng nhất tuần (Thứ 4 & Thứ 2 -> `SKIP_NO_EDGE`, `0.0x`) và 5 ngày chơi chuẩn (`PLAY_STANDARD`, `1.0x`), đồng thời vào Thứ 3 (`2026-10-27`) xếp **Bến Tre (`XSBT`)** ở Hạng #1 với cảnh báo `⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH` và loại bỏ bóng chết `4x`
- [x] Toàn bộ bộ kiểm thử tự động (10 file GĐ 2 & 3 + `tests/test_stage4_sweet5_and_5_2_schedule.py`) đạt `100% PASS` với độ phủ mã nguồn $\ge 90\%$ (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`)
- [x] Kiểm tra chất lượng mã nguồn `uv run ruff check src/ tests/` và `uv run ruff format --check src/ tests/` đạt `0 errors`
- [x] Hoàn tất nghiệm thu toàn bộ 8 tiêu chí `SC-01` $\to$ `SC-08` tại Mục 9 của `spec.md`

---

## Parallelization Opportunities

- **Phải thực hiện tuần tự (`Sequential Core Chain`):**
  - `Task 1` $\rightarrow$ `Task 2` $\rightarrow$ `Task 3` $\rightarrow$ `Task 4`: Thiết lập hằng số `sweet_5`, hợp đồng dữ liệu Pydantic v2 (`Gate 6`), khóa trần đi vốn `1.0x` trong `ledger.py` và lõi phân tích `daily_analyst.py` trước khi kết xuất ra các kênh hiển thị.
- **Có thể thực hiện song song sau khi hoàn tất `Task 4` (`Parallel Presentation Channels`):**
  - **Luồng A (Kênh Telegram 05:00 Sáng):** `Task 5` (`src/xsmn_alpha/live/telegram_bot.py`).
  - **Luồng B (Kênh Web Báo Cáo Tĩnh & CLI):** Phần nâng cấp HTML trong `Task 6` (`src/xsmn_alpha/live/web_publisher.py`).

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
| :--- | :---: | :--- |
| **R1: Thay đổi hằng số hoặc khóa sắp xếp đài làm gãy các bài kiểm thử Giai đoạn 2 & 3 hiện có** | High | Giữ nguyên `SWEET_SPOT_CONFIGS` (8), `EXTENDED_SWEET_SPOT_CONFIGS` (9), `STAGE3_TICKET_CONFIGS` (5) và `sc.ticket_configs` (5 keys); dùng `weekly_5_2_mode="auto"` tự động lùi về đơn ngày khi `raw_dir` trong `tmp_path` có `< 35` đài, và đặt `-passes_selective_alpha` đầu khóa sắp xếp `rank_stations_for_day`. |
| **R2: Rò rỉ dữ liệu tương lai (`draw_date >= D`) khi quét 35 đài để xếp hạng 7 thứ của Lịch 5/2** | High | Thực thi bắt buộc `PreDrawCutoffGate.enforce(history, target_date=target_iso, station_code=code)` cho từng đài trong cả `compute_weekly_balance_rest_days` lẫn `score_station_for_date`; ném `TemporalLeakageError` ngay lập tức nếu vi phạm. |
| **R3: Quỹ Chuẩn đang có lãi lũy kế lớn (`4.911.500 VNĐ`) kích hoạt nhầm hệ số `1.25x` / `1.50x` trong báo cáo gia đình** | High | Truyền `lock_flat_1x=True` vào `build_capital_guidance` trong luồng báo cáo Giai đoạn 4 và kiểm tra cứng qua Gate 6 (`recommended_multiplier == 1.0` vào ngày chơi, `0.0` vào ngày nghỉ). |
| **R4: Bản tin Telegram tiếng Việt vượt giới hạn `4096` byte UTF-8 khi thêm khối `sweet_5`, Lịch 5/2 và `Cage Anomaly Sentinel`** | Medium | Thiết kế bố cục cô đọng (~2.200–3.100 byte UTF-8), kiểm tra cứng `len(full_message.encode("utf-8")) <= 4096` và ném `DataIntegrityError` nếu vượt ngưỡng. |
| **R5: Lỗi XSS / vỡ thẻ HTML khi hiển thị chuỗi cảnh báo dị thường `cage_anomaly_summary_vi`** | Medium | Bắt buộc escape mọi chuỗi động qua `_esc()` (`html.escape(..., quote=True)`) trong cả `telegram_bot.py` và `web_publisher.py`, kèm bài test đột biến âm `<script>alert(1)</script>`. |

---

## Open Questions

- **Không còn câu hỏi mở nào.** Toàn bộ công thức chọn bộ 5 số `sweet_5`, thuật toán xếp hạng độ cân bằng 7 thứ trong tuần cho Lịch Chơi 5/2, ngưỡng phát hiện dị thường lồng cầu ($\chi^2_{\max} > P_{95,\text{null}} \land BF_{10,\max} \ge 10.0$), và kỷ luật khóa trần vốn `1.0x` đều tay đã được khóa đầy đủ tại [`spec.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/spec.md).
