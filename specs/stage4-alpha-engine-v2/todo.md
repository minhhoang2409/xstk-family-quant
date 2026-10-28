# Task List: Giai Đoạn 4 — Kỷ Luật Điểm Ngọt Gia Đình, Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu & Giám Sát Dị Thường (`stage4-alpha-engine-v2`)

**Mã Module:** `stage4-alpha-engine-v2`  
**Trạng thái:** Accepted & Verified (6/6 Tasks — 100% PASS)  
**Ngày tạo:** 2026-10-28  
**Tài liệu đặc tả gốc:** [`specs/stage4-alpha-engine-v2/spec.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/spec.md)  
**Kế hoạch kiến trúc:** [`specs/stage4-alpha-engine-v2/plan.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/plan.md)

---

## Task 1: Bổ sung hệ hằng số Giai đoạn 4 và thuật toán chọn bộ 5 số Điểm Ngọt `sweet_5`

**Description:** Mở rộng `src/xsmn_alpha/constants.py` để bổ sung đầy đủ bộ hằng số Giai đoạn 4 theo Mục 5.1 của `spec.md` (`BENCHMARK_BASE_DAILY_COST_5NUM_VND = 90_000`, `SWEET_5_NET_PROFIT_1HIT_VND = 9_500`, `SWEET_5_NET_PROFIT_2HITS_VND = 109_000`, `SWEET_4_NET_PROFIT_1HIT_VND = 27_500`, `SWEET_4_NET_PROFIT_2HITS_VND = 127_000`, `THEORETICAL_WIN_RATE_4NUM_PCT = 52.04`, `THEORETICAL_WIN_RATE_5NUM_PCT = 60.28`, `THEORETICAL_MULTI_HIT_4NUM_PCT = 16.13`, `THEORETICAL_MULTI_HIT_5NUM_PCT = 22.65`, `STAGE4_MAX_STAKE_MULTIPLIER = 1.0`, `WEEKLY_SCHEDULE_PLAY_DAYS = 5`, `WEEKLY_SCHEDULE_REST_DAYS = 2`, `CAGE_ANOMALY_BF10_THRESHOLD = 10.0`, `CAGE_COLD_BALL_FREQ_MAX_PCT = 6.5`, `CAGE_HOT_BALL_FREQ_MIN_PCT = 14.0`, `STAGE4_TICKET_CONFIGS`, `STAGE4_SWEET_SPOT_CONFIGS`) trong khi giữ nguyên tuyệt đối `SWEET_SPOT_CONFIGS` (8 cấu hình), `EXTENDED_SWEET_SPOT_CONFIGS` (9 cấu hình) và `STAGE3_TICKET_CONFIGS` (5 cấu hình). Cập nhật `src/xsmn_alpha/backtest/sweet_spot_sim.py` bổ sung hàm `select_sweet_5_numbers(probs_tens, probs_units)` và hỗ trợ cấu hình `"sweet_5"` (4 số `2x2` + 1 số vệ tinh có tích xác suất $P_{\text{tens}}(a) \times P_{\text{units}}(b)$ cao nhất ngoài `2x2`, tie-break ưu tiên tổ hợp thuộc khung Top-3 $\times$ Top-3 rồi theo chuỗi ASCII `"00".."99"` tăng dần) trong `select_sweet_spot_numbers`, `compute_portfolio_set_probability`, `score_single_draw_portfolio`, `evaluate_sweet_spot_portfolio` và `evaluate_stage4_ticket_portfolios`.

**Acceptance criteria:**
- [x] `src/xsmn_alpha/constants.py` định nghĩa đầy đủ các hằng số Giai đoạn 4 và cấu hình `"sweet_5"` trong `STAGE4_SWEET_SPOT_CONFIGS` (`num_numbers = 5`, `cost_per_draw = 5.0`, `be_hits_30_draws = (30.0 * 5.0) / BAO_LO_PAYOUT_PER_HIT`) đồng thời giữ nguyên `len(SWEET_SPOT_CONFIGS) == 8`, `len(EXTENDED_SWEET_SPOT_CONFIGS) == 9` và `STAGE3_TICKET_CONFIGS`.
- [x] Hàm `select_sweet_5_numbers` và `select_sweet_spot_numbers(p_tens, p_units, "sweet_5")` trong `src/xsmn_alpha/backtest/sweet_spot_sim.py` trả về đúng 5 số 2 chữ số phân biệt đã sắp xếp gồm trọn 4 số của `"2x2"` cộng với 1 số vệ tinh tối ưu (xử lý đúng điều kiện biên tie-break `BC-01` khi phân phối đều).
- [x] Các hàm `compute_portfolio_set_probability`, `score_single_draw_portfolio` và `evaluate_sweet_spot_portfolio` tính toán chính xác xác suất, chi phí `5.0đ`, doanh thu và các chỉ số OOS cho `"sweet_5"` mà không làm thay đổi kết quả của các bài kiểm thử Giai đoạn 2 & 3.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_constants_and_schemas.py tests/test_stage3_registry_and_4x1.py tests/test_stage4_sweet5_and_5_2_schedule.py -k "sweet_5 or constants" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/constants.py src/xsmn_alpha/backtest/sweet_spot_sim.py tests/test_stage4_sweet5_and_5_2_schedule.py`
- [x] Manual check: Chạy `uv run python -c "from xsmn_alpha.backtest.sweet_spot_sim import select_sweet_spot_numbers; print(select_sweet_spot_numbers([0.1]*10, [0.1]*10, 'sweet_5'))"` xác nhận trả về đúng 5 số hợp lệ `['00', '01', '02', '10', '11']`.

**Dependencies:** None

**Files likely touched:**
- `src/xsmn_alpha/constants.py`
- `src/xsmn_alpha/backtest/sweet_spot_sim.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 2: Mở rộng hợp đồng dữ liệu Pydantic v2 Giai đoạn 4 kèm cổng kiểm soát `Gate 6`

**Description:** Mở rộng `src/xsmn_alpha/schemas.py` để bổ sung hai mô hình `WeekdayCageBalanceSummary` và `WeeklySchedule52Analysis` cùng các trường mở rộng có giá trị mặc định tương thích ngược trên `StationDailyScorecard` (`sweet_5_numbers`, `sweet_5_config`, `cage_anomaly_detected`, `cage_anomaly_summary_vi`, `cold_balls_tens`, `cold_balls_units`, `passes_weekly_5_2_play`) và `DailyQuantReportContract` (`weekly_5_2_schedule`). Cập nhật danh sách cấu hình hợp lệ trong `SweetSpotPortfolioMetrics`, `TicketConfigRecommendation` và `BenchmarkLedgerEntry` sang `STAGE4_SWEET_SPOT_CONFIGS`, đồng thời cài đặt các bộ kiểm tra bất biến của **Gate 6 (`Weekly52AndFlatStakeGate`)** theo Mục 5.3 và Mục 5.5 của `spec.md`.

**Acceptance criteria:**
- [x] `WeeklySchedule52Analysis` thực thi nghiêm ngặt Gate 6: kiểm tra đủ 7 thứ `0..6` không trùng lặp, `balance_rank` tăng dần `1..7` theo `max_chi2_overall` không giảm, đúng 2 thứ đầu có `is_rest_day == True` (`rest_weekdays`), đúng 5 thứ sau có `is_rest_day == False` (`play_weekdays`), và ném `DataIntegrityError` ngay lập tức nếu vi phạm.
- [x] `StationDailyScorecard` xác thực `sweet_5_numbers` (khi khác rỗng) phải có đúng 5 số ASCII 2 chữ số không trùng lặp và chứa trọn 4 số của `ticket_configs["2x2"].selected_numbers`, đồng thời hỗ trợ khởi tạo `TicketConfigRecommendation` cho `"sweet_5"` (4 số `core_numbers` + 1 số `satellite_numbers`).
- [x] `DailyQuantReportContract` cho phép ngày chơi hợp lệ khi `primary_station.passes_selective_alpha == True` hoặc `primary_station.passes_weekly_5_2_play == True` (ném `DataIntegrityError` nếu cả hai đều `False`), đồng thời giữ tương thích ngược 100% với toàn bộ bài kiểm thử schema của Giai đoạn 2 & 3.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_constants_and_schemas.py tests/test_stage3_registry_and_4x1.py tests/test_stage4_sweet5_and_5_2_schedule.py -k "schema or gate6 or sweet_5" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/schemas.py tests/test_stage4_sweet5_and_5_2_schedule.py`
- [x] Manual check: Khởi tạo thử `StationDailyScorecard` với `sweet_5_numbers` chỉ có 4 số hoặc không chứa đủ 4 số của `2x2` và xác nhận hệ thống ném `DataIntegrityError`.

**Dependencies:** Task 1

**Files likely touched:**
- `src/xsmn_alpha/schemas.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Small: 1-2 files

---

## Task 3: Cập nhật sổ cái Quỹ Chuẩn hỗ trợ thanh toán gói `sweet_5` và khóa trần hệ số vốn `1.0x`

**Description:** Cập nhật `src/xsmn_alpha/live/ledger.py` để hỗ trợ ghi nhận khuyến nghị (`record_pending_recommendation`) và đối soát kết quả 18 giải (`settle_entry_with_prizes`, `settle_ledger_for_date`) cho cấu hình `"sweet_5"` (`5 số`, chi phí chuẩn `90.000 VNĐ/ngày` ở mức `1.0x`, trúng 1 nháy thu `99.500 VNĐ` lãi `+9.500 VNĐ`, trúng 2 nháy thu `199.000 VNĐ` lãi `+109.000 VNĐ`). Bổ sung tham số `lock_flat_1x: bool = False` vào `build_capital_guidance` (và `compute_multiplier_for_verdict_tier`) để trong chế độ Giai đoạn 4 (`lock_flat_1x=True`), hệ thống khóa cứng `recommended_multiplier = 1.0` vào mọi ngày chơi (kể cả khi `house_money_surplus_vnd` đang có thặng dư lớn hàng triệu đồng theo `BC-07`) và ném `CapitalDisciplineError` ngay lập tức nếu truyền `recommended_multiplier > 1.0` (`EARS-R02`), đồng thời giữ tương thích 100% với tệp `data/live/benchmark_ledger.json` (`BC-08`).

**Acceptance criteria:**
- [x] Khi gọi `build_capital_guidance(..., lock_flat_1x=True)` vào ngày chơi, hệ thống luôn trả về `recommended_multiplier == 1.0` (`72.000 VNĐ` cho 4 số hoặc `90.000 VNĐ` cho 5 số) bất kể `house_money_surplus_vnd` lớn bao nhiêu, và ném `CapitalDisciplineError` ngay lập tức nếu truyền `recommended_multiplier = 1.25` hoặc `1.5`.
- [x] `record_pending_recommendation` và `settle_ledger_for_date` xử lý chính xác gói `"sweet_5"` ở mức `1.0x` (`cost_vnd = 90_000`, 1 nháy `net_profit_vnd = +9_500`, 2 nháy `net_profit_vnd = +109_000`) và bảo toàn tính lũy đẳng (`Idempotent`) cùng chữ ký `SHA-256`.
- [x] `load_benchmark_ledger("data/live/benchmark_ledger.json")` đọc và xác thực thành công toàn bộ các bản ghi lịch sử đã `SETTLED`, và toàn bộ bài kiểm thử trong `tests/test_stage3_ledger_and_house_money.py` tiếp tục vượt qua 100%.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_ledger_and_house_money.py tests/test_stage4_sweet5_and_5_2_schedule.py -k "ledger or flat_1x or house_money" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/ledger.py tests/test_stage4_sweet5_and_5_2_schedule.py`
- [x] Manual check: Chạy `uv run python -c "from xsmn_alpha.live.ledger import load_benchmark_ledger; s = load_benchmark_ledger(); print(s.total_tracked_days, s.current_bankroll_vnd)"` xác nhận nạp thành công sổ cái hiện có mà không báo lỗi.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/live/ledger.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Small: 1-2 files

---

## Checkpoint: After Tasks 1-3
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application builds and lints without errors (`uv run ruff check src/ tests/`)
- [x] `sweet_5` portfolio selection/scoring, Stage 4 Pydantic contracts (`Gate 6`), and flat `1.0x` ledger settlement work end-to-end with 100% Stage 2 & Stage 3 backward compatibility
- [x] Review with human if any constant or schema contract adjustments are needed before proceeding

---

## Task 4: Triển khai bộ lọc Lịch Chơi 5/2 theo độ cân bằng lồng cầu và giám sát dị thường `Cage Anomaly Sentinel`

**Description:** Nâng cấp `src/xsmn_alpha/live/daily_analyst.py` để triển khai: (1) hàm `detect_cage_anomaly` phát hiện lồng cầu lệch vật lý ($\chi^2_{\max,\text{overall}} > P_{95,\text{null}} \land BF_{10,\max,\text{overall}} \ge 10.0$), trích xuất bóng lạnh/câm thực nghiệm 30 kỳ (`cold_balls_tens`, `cold_balls_units`) và sinh chuỗi cảnh báo `cage_anomaly_summary_vi`; (2) cập nhật `score_station_for_date` để tính toán đầy đủ `sweet_5_numbers`, `sweet_5_config` và các trường `cage_anomaly_*` trên `StationDailyScorecard`; (3) hàm `compute_weekly_balance_rest_days` quét toàn bộ 35 đài trên 7 thứ trong tuần dưới chốt chặn `PreDrawCutoffGate` (`draw_date < D`, dùng bộ nhớ đệm cho 4 đài quay 2 kỳ/tuần) để xác định 2 ngày nghỉ định kỳ cân bằng nhất tuần và 5 ngày chơi Điểm Ngọt; (4) nâng cấp `rank_stations_for_day`, `build_executive_nlg_vi` và `generate_daily_quant_report` (`weekly_5_2_mode="auto"`) ưu tiên đài có dị thường vật lý (như `XSBT` vào Thứ 3) và khóa cứng hệ số vốn `1.0x` vào 5 ngày chơi.

**Acceptance criteria:**
- [x] `compute_weekly_balance_rest_days` kiểm tra nghiêm ngặt `PreDrawCutoffGate` trên toàn bộ 35 đài (ném `TemporalLeakageError` nếu bất kỳ đài nào có `draw_date >= target_date`), xếp hạng đúng 7 thứ theo `(round(max_chi2_overall, 2), round(max_bf10_overall, 3), round(mean_chi2_overall, 2), weekday)` và trên dữ liệu `data/raw_all/` tại ngày `2026-10-27` chọn đúng Thứ 4 (`Max Chi2 = 13.22`) và Thứ 2 (`Max Chi2 = 15.07`) làm 2 ngày nghỉ định kỳ (`SKIP_NO_EDGE`, `0.0x`).
- [x] Vào Thứ 3 (`2026-10-27` trên `data/raw_all/`), `score_station_for_date` và `rank_stations_for_day` xếp **Đài Bến Tre (`XSBT`)** ở vị trí **Hạng #1 (`Đài Chủ Lực`)** nhờ `cage_anomaly_detected == True` ($\chi^2_{\max} = 50.35 > P_{95}, BF_{10} > 10$), nhận diện bóng lạnh `4` ở Lồng Chục, loại trừ hoàn toàn các số đầu `4x` khỏi cả `2x2` lẫn `sweet_5`, và khóa `recommended_multiplier == 1.0`.
- [x] Khi chạy ở chế độ mặc định `weekly_5_2_mode="auto"` trên thư mục `tmp_path` chỉ có 5 đài của Unit Test Giai đoạn 3 (`< 35` đài), `generate_daily_quant_report` tự động bảo toàn hành vi đánh giá đơn ngày giúp toàn bộ `tests/test_stage3_daily_analyst_and_nlg.py` vượt qua 100%.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_daily_analyst_and_nlg.py tests/test_stage4_sweet5_and_5_2_schedule.py -k "weekly or anomaly or analyst or xsbt" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/daily_analyst.py tests/test_stage4_sweet5_and_5_2_schedule.py`
- [x] Manual check: Chạy `uv run python -c "from xsmn_alpha.live.daily_analyst import generate_daily_quant_report; r = generate_daily_quant_report('2026-10-27'); print(r.verdict_tier, r.primary_station.station_code, r.primary_station.cage_anomaly_detected, r.primary_station.sweet_5_numbers, r.capital_guidance.recommended_multiplier)"` xác nhận in ra `PLAY_STANDARD XSBT True ... 1.0`.

**Dependencies:** Task 1, Task 2, Task 3

**Files likely touched:**
- `src/xsmn_alpha/live/daily_analyst.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Small: 1-2 files

---

## Task 5: Nâng cấp bản tin Telegram 05:00 sáng hiển thị Điểm Ngọt Kép, Lịch 5/2 và Quy tắc Tiền Chợ `1.0x`

**Description:** Nâng cấp `src/xsmn_alpha/live/telegram_bot.py` để bản tin chiến thuật 05:00 sáng hiển thị rõ ràng, trực quan cho gia đình: (1) Trạng thái **Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu** (báo nghỉ định kỳ `0.0x` vào 2 ngày lồng cầu cân bằng nhất tuần, hoặc báo chơi đều tay `1.0x` vào 5 ngày có độ lệch cao hơn); (2) Cảnh báo **`⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH`** khi `cage_anomaly_detected == True`; (3) **Cấu hình Vé Điểm Ngọt Kép** trên Đài Chủ Lực gồm **Bộ 5 số Điểm Ngọt Bà Cô (`sweet_5` — 60.28% ngày lời, vốn 1.0x = 90k: 1 nháy +9.5k, 2 nháy +109k)** và **Bộ 4 số Chuẩn (`2x2` — 52.04% ngày lời, vốn 1.0x = 72k: 1 nháy +27.5k, 2 nháy +127k)**; (4) Khung nhắc nhở **"🛡️ Kỷ Luật Tiền Chợ Đều Tay 1.0x (Tuyệt đối không gấp thếp)"** kèm đường link mở Trang Web Báo Cáo Giải Trình Chi Tiết ở cuối tin.

**Acceptance criteria:**
- [x] Bản tin Telegram ngày chơi hiển thị đầy đủ trạng thái Lịch 5/2, cả 2 gói Điểm Ngọt (`sweet_5` 5 số và `2x2` 4 số), khung nhắc nhở Kỷ Luật Tiền Chợ Đều Tay `1.0x` (không gấp thếp), cảnh báo `⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH` (khi `cage_anomaly_detected == True`), link Web cuối tin, và có kích thước luôn $\le 4096$ byte UTF-8 (`BC-09`).
- [x] Bản tin Telegram vào 2 ngày nghỉ định kỳ của Lịch 5/2 (`SKIP_NO_EDGE`, `0.0x`) giải thích rõ lý do nghỉ định kỳ do lồng cầu thuộc nhóm 2 ngày cân bằng nhất tuần để bảo toàn vốn.
- [x] Mọi chuỗi động (bao gồm `cage_anomaly_summary_vi`) đều được escape an toàn qua `_esc()` chống XSS (`<script>alert(1)</script>` $\rightarrow$ `&lt;script&gt;`), và toàn bộ bài kiểm thử trong `tests/test_stage3_web_and_telegram.py` tiếp tục vượt qua 100%.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_web_and_telegram.py tests/test_stage4_sweet5_and_5_2_schedule.py -k "telegram" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/telegram_bot.py tests/test_stage4_sweet5_and_5_2_schedule.py`
- [x] Manual check: Kiểm tra độ dài `len(msg.encode("utf-8")) <= 4096` trên cả bản tin ngày nghỉ (`2026-10-26`) và bản tin ngày chơi có dị thường (`2026-10-27`).

**Dependencies:** Task 4

**Files likely touched:**
- `src/xsmn_alpha/live/telegram_bot.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Small: 1-2 files

---

## Task 6: Nâng cấp trang Web giải trình tĩnh Giai đoạn 4 và kiểm nghiệm toàn tuyến CLI `daily-report`

**Description:** Nâng cấp `src/xsmn_alpha/live/web_publisher.py` để hiển thị trực quan trên trang báo cáo hàng ngày `public/daily/YYYY-MM-DD.html`: (1) Hộp cảnh báo **`⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH` (`Cage Anomaly Sentinel`)** và **Bảng Xếp Hạng Độ Cân Bằng 7 Thứ Trong Tuần (Lịch Chơi 5/2)** khi `report.weekly_5_2_schedule` hiện diện; (2) Bổ sung cấu hình **Bộ 5 số Điểm Ngọt Bà Cô (`sweet_5`)** vào bảng so sánh các phương án ghép số tại Khu vực 3 và nổi bật trên ma trận nhiệt; (3) Bổ sung khung **"Kỷ Luật Tiền Chợ Đều Tay 1.0x (So sánh Bộ 4 số `2x2` & Bộ 5 số `sweet_5` ở mức 1.0x và 2.0x — Tuyệt đối không gấp thếp)"** tại Khu vực 4. Kiểm tra tích hợp với `src/xsmn_alpha/cli.py`, hoàn thiện toàn bộ 5 tầng kiểm thử trong `tests/test_stage4_sweet5_and_5_2_schedule.py` và chạy nghiệm thu thực tế lệnh `daily-report --dry-run` cho ngày nghỉ (`2026-10-26` / `2026-10-28`) và ngày chơi có dị thường (`2026-10-27`).

**Acceptance criteria:**
- [x] `render_daily_report_html` kết xuất đầy đủ bảng Xếp hạng 7 thứ Lịch Chơi 5/2, hộp cảnh báo `Cage Anomaly Sentinel` (khi có dị thường), thông số gói `sweet_5` (`60.28%` ngày thắng, `90.000đ/ngày`) và bảng đối chiếu Kỷ Luật Tiền Chợ Đều Tay `1.0x`, đồng thời escape toàn bộ chuỗi động qua `_esc()` chống XSS.
- [x] Chạy thực tế lệnh CLI `daily-report --dry-run` cho ngày `2026-10-26` (Thứ 2 — Nghỉ định kỳ Lịch 5/2 `0.0x`) và ngày `2026-10-27` (Thứ 3 — Chơi Điểm Ngọt `1.0x` tại Đài Bến Tre `XSBT`) xuất thành công các tệp HTML/JSON tại `public/` và bản xem trước Telegram tại `data/live/latest_telegram_preview.txt`.
- [x] Toàn bộ bộ kiểm thử tự động (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`) đạt `100% PASS` với độ phủ $\ge 90\%$, đồng thời `uv run ruff check src/ tests/` và `uv run ruff format --check src/ tests/` đạt `0 errors`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`
- [x] Build succeeds: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
- [x] Manual check: Chạy `uv run python -m xsmn_alpha.cli daily-report --date 2026-10-26 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run` và `uv run python -m xsmn_alpha.cli daily-report --date 2026-10-27 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run`, kiểm tra trực tiếp đầu ra tại `public/daily/` và `data/live/latest_telegram_preview.txt`.

**Dependencies:** Task 4, Task 5

**Files likely touched:**
- `src/xsmn_alpha/live/web_publisher.py`
- `src/xsmn_alpha/cli.py`
- `tests/test_stage4_sweet5_and_5_2_schedule.py`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: After Tasks 4-6
- [x] All tests pass with coverage >= 90% (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`)
- [x] Application passes all lint and format checks (`uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`)
- [x] All 8 Success Criteria (`SC-01` through `SC-08`) in Section 9 of `spec.md` are verified end-to-end
- [x] Review final Stage 4 Web Audit Report (`public/daily/2026-10-26.html`, `public/daily/2026-10-27.html`) and Telegram 05:00 AM Briefing with human
