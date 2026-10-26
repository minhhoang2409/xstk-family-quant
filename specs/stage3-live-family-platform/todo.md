# Task List: Giai Đoạn 3 — Chuyên Viên Báo Cáo Định Lượng Tự Động 5h Sáng & Trang Web Giải Trình Chi Tiết (`stage3-live-family-platform`)

**Mã Module:** `stage3-live-family-platform`  
**Trạng thái:** Completed — Verified 100% PASS (Pha 4: VERIFY)  
**Ngày cập nhật:** 2026-10-27  
**Tài liệu đặc tả gốc:** [`specs/stage3-live-family-platform/spec.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/spec.md)  
**Kế hoạch kiến trúc:** [`specs/stage3-live-family-platform/plan.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/plan.md)

---

## Task 1: Mở rộng hằng số Giai đoạn 3, ngoại lệ `CapitalDisciplineError`, cấu hình đối xứng `4x1` & danh mục chuẩn 35 đài

**Description:** Mở rộng `src/xsmn_alpha/constants.py` để bổ sung hệ hằng số Quỹ Chuẩn Tham Chiếu VNĐ (`BENCHMARK_INITIAL_BANKROLL_VND = 1_000_000`, `BENCHMARK_STAKE_PER_NUMBER_VND = 18_000`, `BENCHMARK_BASE_DAILY_COST_4NUM_VND = 72_000`, `BENCHMARK_PAYOUT_PER_HIT_VND = 87_500`, `HOUSE_MONEY_MIN_BUFFER_DAYS = 2`, `HOUSE_MONEY_MAX_SURPLUS_FRACTION = 0.50`, `SELECTIVE_ALPHA_JOINT_R1_MIN_PCT = 1.105`, `PEAK_CONVICTION_JOINT_R1_PCT = 1.150`, `SAMPLE_CAPITAL_TIERS_VND = (500_000, 1_000_000, 2_000_000, 5_000_000)`), cấu hình đối xứng `"4x1"` (Top 4 Chục $\times$ Top 1 Đơn vị = 4 số) trong `STAGE3_TICKET_CONFIGS` (`"2x2"`, `"1x4"`, `"4x1"`, `"3x3"`, `"core_2x2_sat_3x3"`) và `EXTENDED_SWEET_SPOT_CONFIGS` mà vẫn giữ nguyên bất biến `VALID_STATIONS`, `STATION_CONFIG`, `SWEET_SPOT_CONFIGS` của Giai đoạn 2. Bổ sung ngoại lệ `CapitalDisciplineError` vào `src/xsmn_alpha/exceptions.py`, cập nhật `src/xsmn_alpha/backtest/sweet_spot_sim.py` hỗ trợ chọn số/tính xác suất/chấm điểm cho `"4x1"`, và xây dựng `src/xsmn_alpha/live/registry.py` định nghĩa danh mục chuẩn 35 đài (`STATION_REGISTRY_35`, `VALID_35_STATION_CODES`) kèm hàm tra cứu lịch mở thưởng theo thứ từ Thứ 2 đến Chủ Nhật.

**Acceptance criteria:**
- [x] `STATION_REGISTRY_35` trong `src/xsmn_alpha/live/registry.py` chứa đúng 35 đài (21 đài Miền Nam quay lúc `16:15` + 14 đài Miền Trung quay lúc `17:15`), 4 đài quay 2 kỳ/tuần (`XSHCM`, `XSTTH`, `XSDNG`, `XSKH` với `target_3y = 312`) và 31 đài quay 1 kỳ/tuần (`target_3y = 156`), trả về đúng danh sách 5–7 đài mở thưởng cho từng ngày từ Thứ 2 (`0`) đến Chủ Nhật (`6`) khớp bảng Mục 5.2 của `spec.md`.
- [x] `src/xsmn_alpha/backtest/sweet_spot_sim.py` hỗ trợ đầy đủ cấu hình `"4x1"` (chọn đúng 4 số từ Top 4 bóng Lồng Chục $\times$ Top 1 bóng Lồng Đơn Vị, `cost_per_draw == 4.0`, `be_hits_30_draws == (30.0 * 4.0) / BAO_LO_PAYOUT_PER_HIT`) đồng thời giữ nguyên 8 cấu hình gốc trong `SWEET_SPOT_CONFIGS`.
- [x] Toàn bộ bộ kiểm thử Giai đoạn 2 hiện hữu (`tests/test_constants_and_schemas.py` và `tests/test_pillar4_walk_forward_backtest.py`) tiếp tục vượt qua 100% mà không cần sửa đổi bất kỳ assertion cũ nào.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_constants_and_schemas.py tests/test_pillar4_walk_forward_backtest.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/ tests/`
- [x] Manual check: Chạy `uv run python -c "from xsmn_alpha.live.registry import STATION_REGISTRY_35; print(len(STATION_REGISTRY_35))"` xác nhận in ra `35`.

**Dependencies:** None

**Files likely touched:**
- `src/xsmn_alpha/constants.py`
- `src/xsmn_alpha/exceptions.py`
- `src/xsmn_alpha/backtest/sweet_spot_sim.py`
- `src/xsmn_alpha/live/__init__.py`
- `src/xsmn_alpha/live/registry.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 2: Thiết lập hợp đồng dữ liệu Pydantic v2 Giai đoạn 3 kèm cổng `FalsificationCashBrakeGate` & `HouseMoneyAndLedgerIntegrityGate`

**Description:** Mở rộng `src/xsmn_alpha/schemas.py` bổ sung các mô hình Pydantic v2 `StrictBaseModel` (`extra="forbid"`, `allow_inf_nan=False`, `validate_assignment=True`) cho toàn bộ đường ống Giai đoạn 3: `HitDetailRecord`, `BenchmarkLedgerEntry`, `BenchmarkLedgerState`, `SampleCapitalAllocationRow`, `CapitalGuidanceContract`, `TicketConfigRecommendation`, `StationDailyScorecard`, `DataPipelineAuditRecord`, `ExecutiveNLGContract` và `DailyQuantReportContract`. Cài đặt các model validators thực thi nghiêm ngặt Gate 1 (`DataSchemaGate` cho 35 đài), Gate 3 (`SimplexCalibrationGate` cho phân phối 10 bóng và ma trận $10 \times 10$ của 100 số), Gate 4 (`FalsificationCashBrakeGate` khóa cứng `should_play_today = False`, `recommended_multiplier = 0.0`, `cost_vnd = 0` khi `verdict_tier == "SKIP_NO_EDGE"`), và Gate 5 (`HouseMoneyAndLedgerIntegrityGate` kiểm tra phương trình kế toán $W_t = W_{t-1} + \text{Rev}_t - \text{Cost}_t$, điều kiện đệm lãi ròng $\ge 144.000\text{ VNĐ}$ và không lẹm vốn gốc $1.000.000\text{ VNĐ}$ khi $m_t > 1.0$).

**Acceptance criteria:**
- [x] Các schema `BenchmarkLedgerEntry`, `BenchmarkLedgerState` và `DailyQuantReportContract` xác thực nghiêm ngặt cấu trúc JSON tại Mục 5.4 của `spec.md`, từ chối mọi trường thừa (`extra="forbid"`) hoặc giá trị `NaN`/`Inf`.
- [x] Gate 4 (`FalsificationCashBrakeGate`) ném `DataIntegrityError` ngay lập tức nếu `verdict_tier == "SKIP_NO_EDGE"` mà `should_play_today == True` hoặc `recommended_multiplier > 0.0` hoặc bất kỳ dòng vốn mẫu nào có `total_daily_cost_vnd > 0`.
- [x] Gate 5 (`HouseMoneyAndLedgerIntegrityGate`) ném `CapitalDisciplineError` (hoặc `DataIntegrityError`) nếu `recommended_multiplier > 1.0` khi `house_money_before_vnd < 144_000`, hoặc phần cược tăng thêm vượt quá $50\%$ Quỹ Lãi Ròng, hoặc `bankroll_before_vnd - cost_vnd < 1_000_000`, hoặc sai lệch phương trình `bankroll_after_vnd == bankroll_before_vnd + revenue_vnd - cost_vnd`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_constants_and_schemas.py tests/test_stage3_registry_and_4x1.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/schemas.py tests/test_stage3_registry_and_4x1.py`
- [x] Manual check: Thử khởi tạo `BenchmarkLedgerEntry` với `recommended_multiplier=1.5` khi `house_money_before_vnd=50_000` và xác nhận hệ thống ném `CapitalDisciplineError`.

**Dependencies:** Task 1

**Files likely touched:**
- `src/xsmn_alpha/schemas.py`
- `tests/test_stage3_registry_and_4x1.py`

**Estimated scope:** Small: 1-2 files

---

## Task 3: Xây dựng trình thu thập tăng trưởng đa nguồn 35 đài `multi_fetcher.py` kèm Failover 3 tầng & chữ ký `SHA-256`

**Description:** Triển khai `src/xsmn_alpha/live/multi_fetcher.py` tự động thu thập và cập nhật tăng trưởng (`Incremental Delta Sync`) kết quả 18 giải mới nhất cho toàn bộ 35 đài XSMN (`mien-nam`) và XSMT (`mien-trung`) vào `data/raw_all/<CODE>_draws.json`. Hỗ trợ chuyển đổi dự phòng tự động 3 tầng (`minhngoc.net.vn` $\to$ `xskt.com.vn` $\to$ `xoso.com.vn`), kiểm định từng kỳ quay qua `DataSchemaGate` (đủ 18 giải ASCII `00`–`99`, tổng đếm mỗi lồng $= 18$, ngày mở thưởng hợp lệ và không trùng lặp), tính toán và xác thực mã băm `SHA-256` cho mỗi tệp cache, đồng thời hoàn thiện bộ kiểm thử `tests/test_stage3_registry_and_4x1.py`.

**Acceptance criteria:**
- [x] Hàm đồng bộ trong `multi_fetcher.py` đọc cache hiện có tại `data/raw_all/<CODE>_draws.json`, chỉ tải bổ sung các kỳ mở thưởng mới thiếu (hoặc nạp từ cache nếu đã cập nhật đến ngày mục tiêu) và ghi kèm trường `sha256` hợp lệ.
- [x] Khi nguồn chính `minhngoc.net.vn` gặp lỗi mạng hoặc trả về bảng đang quay dở ($< 18$ giải), `multi_fetcher.py` tự động chuyển sang nguồn dự phòng `xskt.com.vn` / `xoso.com.vn` và ghi nhận `fallback_used_count` vào `DataPipelineAuditRecord`.
- [x] Bộ kiểm thử `tests/test_stage3_registry_and_4x1.py` kiểm chứng đầy đủ cả kịch bản `PASS` (35 đài, lịch quay từng thứ, cấu hình `4x1`, failover thành công) lẫn kịch bản `Negative Mutation FAIL` (mã đài lạ `"XSHN"`, kỳ quay 17 giải, ký tự Unicode full-width `"０８"` bị chặn bởi `DataIntegrityError`).

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_registry_and_4x1.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/ tests/test_stage3_registry_and_4x1.py`
- [x] Manual check: Chạy kiểm thử đồng bộ trên dữ liệu cache 35 đài tại `data/raw_all/` và xác nhận `DataPipelineAuditRecord.schema_gate_passed == True`.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/live/multi_fetcher.py`
- `tests/test_stage3_registry_and_4x1.py`

**Estimated scope:** Small: 1-2 files

---

## Checkpoint: After Tasks 1-3
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application builds and lints without errors (`uv run ruff check src/ tests/`)
- [x] 35-Station Registry, symmetric `4x1` config, Stage 3 Pydantic contracts, and 3-tier failover `multi_fetcher.py` work end-to-end while preserving 100% Stage 2 backward compatibility
- [x] Review with human if any station metadata or schema adjustments are needed before proceeding

---

## Task 4: Xây dựng bộ quản lý Sổ cái Quỹ Chuẩn Tham Chiếu (`1.000.000 VNĐ`) & Động cơ Đi vốn CPPI / House-Money

**Description:** Triển khai `src/xsmn_alpha/live/ledger.py` quản lý trọn vẹn vòng đời của Sổ cái Quỹ Chuẩn Tham Chiếu (`data/live/benchmark_ledger.json`, vốn gốc $W_0 = 1.000.000\text{ VNĐ}$, cược cơ sở `18.000 VNĐ/số` = `72.000 VNĐ/ngày` cho bộ 4 số, trả thưởng `87.500 VNĐ/nháy`). Cài đặt hàm `compute_house_money_multiplier` và `build_sample_capital_allocations` (quy đổi tỷ lệ thuận cho 4 mức vốn mẫu `500.000đ`, `1.000.000đ`, `2.000.000đ`, `5.000.000đ`), hàm ghi nhận khuyến nghị `"PENDING"` trước giờ quay, và hàm đối soát tự động `settle_ledger_for_date` sau giờ quay (đếm số nháy $K$ trên 18 giải, trích xuất `hit_details` chỉ rõ giải nổ từ `Giải Tám` đến `Giải Đặc Biệt`, cập nhật doanh thu, lãi/lỗ ròng, số dư $W_t$, Quỹ Lãi Ròng $C_t$, `max_drawdown_vnd` và chữ ký `SHA-256`). Viết bộ kiểm thử toàn diện tại `tests/test_stage3_ledger_and_house_money.py`.

**Acceptance criteria:**
- [x] Hàm `compute_house_money_multiplier` tuân thủ tuyệt đối Gate 5: trả về `(0.0, 0)` khi `not passes_selective_alpha`, `(1.0, 72_000)` khi $C_{t-1} < 144.000\text{ VNĐ}$ hoặc tín hiệu thận trọng, và chỉ trả về `(1.25, 90_000)` hoặc `(1.50, 108_000)` khi $C_{t-1} \ge 144.000\text{ VNĐ}$ sao cho $\Delta \text{Cost}_t \le 0.50 \times C_{t-1}$ và $W_{t-1} - \text{Cost}_t \ge W_0$.
- [x] Hàm đối soát `settle_ledger_for_date` chấm điểm chính xác số nháy $K$ và tên giải nổ trên 18 giải, chuyển trạng thái từ `"PENDING"` sang `"SETTLED"`, bảo toàn tính lũy đẳng (`Idempotent` — gọi lặp lại nhiều lần cho cùng một ngày đã `"SETTLED"` không bao giờ cộng/trừ tiền 2 lần) và xác thực mã `sha256` trước/sau khi lưu.
- [x] Bộ kiểm thử `tests/test_stage3_ledger_and_house_money.py` vượt qua 100% cả luồng `PASS` lẫn `Negative Mutation FAIL` (cố tình ép hệ số `1.5x` khi chưa đủ lãi ròng hoặc khi số dư $< 1.000.000\text{đ}$ bị chặn bởi `CapitalDisciplineError`; sửa tay số dư hoặc làm lệch `sha256` trong file JSON bị chặn bởi `DataIntegrityError`).

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_ledger_and_house_money.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/ledger.py tests/test_stage3_ledger_and_house_money.py`
- [x] Manual check: Kiểm tra đối soát một kỳ mở thưởng mẫu nổ 2 nháy ở mức cược `1.0x` (`72.000đ`) xác nhận thu về `175.000đ`, lãi ròng `+103.000đ` và gọi `settle_ledger_for_date` lần thứ 2 giữ nguyên tuyệt đối số dư.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/live/ledger.py`
- `tests/test_stage3_ledger_and_house_money.py`

**Estimated scope:** Small: 1-2 files

---

## Task 5: Xây dựng Chuyên viên Chấm điểm Đài Hàng ngày khóa chặt `PreDrawCutoffGate` (`draw_date < D`)

**Description:** Triển khai phần lõi chấm điểm định lượng trong `src/xsmn_alpha/live/daily_analyst.py` cho ngày mục tiêu $D$: xác định toàn bộ 5–7 đài có lịch mở thưởng vào thứ của ngày $D$, lọc lịch sử quá khứ nghiêm ngặt $\mathcal{H}_{s, <D} = \{r \mid r.\text{draw\_date} < D\}$ dưới chốt chặn `PreDrawCutoffGate` (ném `TemporalLeakageError` nếu phát hiện bất kỳ bản ghi nào có `draw_date >= D`), chạy kiểm định thống kê đa cửa sổ $W \in \{15, 30, 60\}$ ($\chi^2$, $BF_{10}$, Entropy) đối chiếu với 1,000 chuỗi Monte Carlo Null (`seed=42`), chạy `CalibratedProbabilityPooler` để dự báo xác suất 10 bóng $\mathbf{p}_{s, D}^{\text{tens}}, \mathbf{p}_{s, D}^{\text{units}}$ cùng ma trận $10 \times 10$ của 100 số (`00`–`99`), tính tần suất nổ bóng Hạng 1 ngoài mẫu OOS ($\hat{p}_{\text{tens, R1}}^{(<D)}, \hat{p}_{\text{units, R1}}^{(<D)}, \text{JointR1}^{(<D)}$) cùng OOS ROI 3 năm của cả 5 cấu hình (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`), chọn cấu hình tối ưu $C^*_{s, D}$, xếp hạng các đài theo `StationAlphaScore` và phân hạng tín hiệu ngày (`PLAY_PEAK`, `PLAY_STANDARD`, `PLAY_CAUTIOUS`, `SKIP_NO_EDGE`).

**Acceptance criteria:**
- [x] Cổng `PreDrawCutoffGate` trong `daily_analyst.py` kiểm tra nghiêm ngặt mọi kỳ quay đầu vào đều có `draw_date < target_date` và ném `TemporalLeakageError` ngay lập tức nếu truyền dữ liệu có `draw_date >= target_date`.
- [x] Với mỗi đài trong 5–7 đài mở thưởng ngày $D$, `StationDailyScorecard` tính đầy đủ phân phối xác suất hiệu chuẩn 10 bóng ($\sum P_i = 1.0$), ma trận 100 số ($\sum_{a,b} P(ab) = 1.0$), thông số 5 cấu hình ghép số (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`), điểm `station_alpha_score` và sắp xếp giảm dần tất định (tie-break theo `station_code`).
- [x] Phân hạng tín hiệu ngày (`verdict_tier`) tuân thủ chính xác công thức tại Mục 5.3.B của `spec.md`: trả về `SKIP_NO_EDGE` (`m_D = 0.0x`) khi mọi đài trong ngày đều có $\text{JointR1} < 1.105\%$ hoặc $\text{BestROI} \le 0.0\%$, và phân loại đúng `PLAY_PEAK`, `PLAY_STANDARD`, `PLAY_CAUTIOUS` khi vượt bộ lọc.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_daily_analyst_and_nlg.py -k "score or cutoff or verdict" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/daily_analyst.py tests/test_stage3_daily_analyst_and_nlg.py`
- [x] Manual check: Thử truyền bản ghi kỳ quay có `draw_date == target_date` vào hàm chấm điểm đài và xác nhận `TemporalLeakageError` được ném ra ngay lập tức.

**Dependencies:** Task 1, Task 2, Task 4

**Files likely touched:**
- `src/xsmn_alpha/live/daily_analyst.py`
- `tests/test_stage3_daily_analyst_and_nlg.py`

**Estimated scope:** Small: 1-2 files

---

## Task 6: Xây dựng Bộ sinh Lời giải trình Định lượng Tất định Tiếng Việt (`Deterministic Quantitative NLG`) trả lời 4 câu hỏi cốt lõi

**Description:** Hoàn thiện `src/xsmn_alpha/live/daily_analyst.py` bằng việc triển khai bộ sinh văn bản giải trình định lượng tất định 100% bằng Python thuần túy (`Deterministic Quantitative NLG` — tuyệt đối không dùng bất kỳ AI/LLM API nào). Tự động lắp ghép lời giải trình tiếng Việt rõ ràng, trung thực cho từng đài và cho toàn ngày (`ExecutiveNLGContract`: `q1_should_play_and_why`, `q2_which_station_and_region`, `q3_which_numbers_and_config`, `q4_how_to_allocate_capital`) từ chính các chỉ số kiểm định toán học của ngày $D$ ($\text{JointR1}\%$ so với mốc $1.105\%$, tần suất Rank-1 Lồng Chục & Lồng Đơn Vị so với mốc hòa vốn $10.69\%$, $\chi^2_{\max}$ so với phân vị Monte Carlo Null $P_{90}/P_{95}$, $BF_{10}$, độ dài chế độ `BOCD` $r^*_{t-1}$ kèm cảnh báo thay bóng nếu $r^*_{t-1} \le 4$, OOS ROI 3 năm, và quy tắc đi vốn House-Money), đồng thời hoàn thiện bộ kiểm thử `tests/test_stage3_daily_analyst_and_nlg.py`.

**Acceptance criteria:**
- [x] Hàm sinh `ExecutiveNLGContract` trả lời đầy đủ, rõ ràng cả 4 câu hỏi cốt lõi bằng tiếng Việt có dấu chuẩn mực, trích dẫn khớp 1:1 các con số thực tế trong `DailyQuantReportContract` mà không gọi bất kỳ API ngoài nào.
- [x] Khi chạy 2 lần liên tiếp với cùng dữ liệu đầu vào, `daily_analyst.py` tạo ra kết quả `DailyQuantReportContract` và văn bản `executive_nlg_vi` giống hệt nhau 100% từng ký tự (Deterministic Reproducibility).
- [x] Bộ kiểm thử `tests/test_stage3_daily_analyst_and_nlg.py` vượt qua 100% các bài kiểm tra cho cả ngày `PLAY_PEAK` / `PLAY_STANDARD`, ngày `SKIP_NO_EDGE` (giải thích rõ lý do cầu nhiễu trắng và khuyên nghỉ `0.0x`), cảnh báo thay bóng `BOCD`, và bài kiểm tra đột biến âm `TemporalLeakageError`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_daily_analyst_and_nlg.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/daily_analyst.py tests/test_stage3_daily_analyst_and_nlg.py`
- [x] Manual check: In thử 4 đoạn giải trình `q1..q4` cho một ngày thực nghiệm và kiểm tra mọi con số phần trăm / tiền VNĐ đều khớp chính xác với scorecard.

**Dependencies:** Task 5

**Files likely touched:**
- `src/xsmn_alpha/live/daily_analyst.py`
- `tests/test_stage3_daily_analyst_and_nlg.py`

**Estimated scope:** Small: 1-2 files

---

## Checkpoint: After Tasks 4-6
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application builds and lints without errors (`uv run ruff check src/ tests/`)
- [x] Benchmark 1M Ledger, CPPI / House-Money sizing engine, Pre-Draw (< D) Daily Station Analyst, and Deterministic Quantitative NLG work end-to-end
- [x] Review with human if any NLG phrasing or scoring thresholds need refinement before proceeding

---

## Task 7: Xây dựng Trình xuất Trang Web Báo cáo Giải trình Chi tiết 5 Khu vực & Trang chủ Dashboard

**Description:** Triển khai `src/xsmn_alpha/live/web_publisher.py` tự động xuất bản tệp dữ liệu kiểm toán `public/daily/YYYY-MM-DD.json`, trang báo cáo chi tiết từng ngày `public/daily/YYYY-MM-DD.html` và trang chủ tổng hợp `public/index.html` với giao diện Dark-Mode sắc nét, tốc độ tải tức thì, tương thích hoàn hảo trên cả điện thoại di động lẫn máy tính. Trang báo cáo hàng ngày bắt buộc hiển thị đầy đủ **5 khu vực bằng chứng toán học** theo Mục 5.5.B của `spec.md`: (1) Tóm tắt Quyết định Chiến thuật 05:00 Sáng & Giải trình 4 câu hỏi + Đối soát hôm qua, (2) Bảng Chấm điểm & So sánh toàn bộ 5–7 đài mở thưởng trong ngày, (3) Bảng Phân phối Xác suất 10 quả bóng (`0`–`9`), Ma trận nhiệt $10 \times 10$ của 100 số (`00`–`99`) & Bảng so sánh 5 phương án ghép số (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`), (4) Bảng Tư vấn Đi vốn CPPI / House-Money & Quy đổi Tiền VNĐ mẫu (`500k`, `1M`, `2M`, `5M`), và (5) Nhật ký Thu thập Dữ liệu (`Data Pipeline Audit`), Biểu đồ SVG Đường cong Vốn & Sổ cái Đối soát Quỹ Chuẩn.

**Acceptance criteria:**
- [x] Hàm xuất bản tạo thành công `public/daily/YYYY-MM-DD.json`, `public/daily/YYYY-MM-DD.html` (chứa đầy đủ cả 5 khu vực bắt buộc, ma trận nhiệt 100 số và biểu đồ SVG đường cong vốn) cùng trang chủ `public/index.html` liệt kê lịch sử báo cáo các ngày và trạng thái Quỹ Chuẩn `1.000.000 VNĐ`.
- [x] Mọi dữ liệu chuỗi động đưa vào HTML đều được escape an toàn qua `html.escape` để ngăn chặn tuyệt đối lỗi vỡ bảng biểu hoặc tấn công HTML/Script Injection (`<script>alert(1)</script>`).
- [x] Giao diện HTML tự chứa 100% (`Self-Contained CSS + SVG`, không phụ thuộc thư viện JS/CSS nặng bên ngoài), hiển thị rõ nét trên cả màn hình điện thoại và máy tính.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_web_and_telegram.py -k "web" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/web_publisher.py tests/test_stage3_web_and_telegram.py`
- [x] Manual check: Mở file `public/daily/YYYY-MM-DD.html` và `public/index.html` kiểm tra sự hiện diện của đủ 5 khu vực, bảng 5 cấu hình ghép số và bảng quy đổi vốn VNĐ.

**Dependencies:** Task 4, Task 6

**Files likely touched:**
- `src/xsmn_alpha/live/web_publisher.py`
- `tests/test_stage3_web_and_telegram.py`

**Estimated scope:** Small: 1-2 files

---

## Task 8: Xây dựng Trình phát Bản tin Chiến thuật 05:00 Sáng qua Telegram Bot API kèm chế độ `--dry-run`

**Description:** Triển khai `src/xsmn_alpha/live/telegram_bot.py` định dạng bản tin chiến thuật 05:00 sáng (`parse_mode="HTML"`, độ dài $\le 4096$ ký tự UTF-8) trình bày súc tích, dễ đọc ngay trên điện thoại: Tiêu đề & Đối soát nhanh kết quả hôm qua (`D - 1`), trả lời trực diện 4 câu hỏi cốt lõi (*1. Hôm nay có nên đánh không & Vì sao? 2. Nên đánh đài gì, khu vực nào? 3. Với đài nên đánh nhất thì đánh bộ số nào? 4. Đi vốn như thế nào?* kèm bảng quy đổi tiền mẫu cho vốn `500k`, `1 Triệu`, `2 Triệu`, `5 Triệu`), và đính kèm đường link mở trực tiếp Trang Web Báo Cáo Giải Trình Chi Tiết của ngày hôm đó ở cuối tin nhắn. Hỗ trợ lưu bản xem trước ra `data/live/latest_telegram_preview.txt` khi chạy `--dry-run` và gửi thực tế qua `Telegram Bot HTTP API` (`httpx`), đồng thời hoàn thiện bộ kiểm thử `tests/test_stage3_web_and_telegram.py`.

**Acceptance criteria:**
- [x] Bản tin Telegram HTML sinh ra chứa đầy đủ Tiêu đề + Đối soát hôm qua + 4 mục trả lời 4 câu hỏi cốt lõi + thẻ `<a href="{PUBLIC_REPORT_BASE_URL}/daily/{YYYY-MM-DD}.html">...</a>` ở cuối tin, với tổng độ dài luôn $\le 4096$ ký tự UTF-8.
- [x] Khi chạy với `dry_run=True` (hoặc cờ `--dry-run`), hệ thống lưu toàn bộ nội dung tin nhắn ra `data/live/latest_telegram_preview.txt` mà không yêu cầu biến môi trường `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; khi `dry_run=False`, hệ thống kiểm tra biến môi trường (ném `DataIntegrityError` nếu thiếu) và gửi HTTP POST tới `https://api.telegram.org/bot<TOKEN>/sendMessage`.
- [x] Bộ kiểm thử `tests/test_stage3_web_and_telegram.py` vượt qua 100% cả luồng `PASS` (render Web 5 khu vực, render Telegram 4 câu hỏi, gửi qua `httpx.MockTransport`, chế độ `--dry-run`) lẫn `Negative Mutation FAIL` (escape chuỗi độc hại `<script>alert(1)</script>`, ném `DataIntegrityError` khi gửi thật mà thiếu Token).

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_stage3_web_and_telegram.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/live/telegram_bot.py tests/test_stage3_web_and_telegram.py`
- [x] Manual check: Kiểm tra nội dung file `data/live/latest_telegram_preview.txt` xác nhận hiển thị rõ 4 câu hỏi cốt lõi, bảng tiền mẫu VNĐ và link Web báo cáo chi tiết.

**Dependencies:** Task 6, Task 7

**Files likely touched:**
- `src/xsmn_alpha/live/telegram_bot.py`
- `tests/test_stage3_web_and_telegram.py`

**Estimated scope:** Small: 1-2 files

---

## Task 9: Tích hợp CLI (`sync-35`, `settle-ledger`, `daily-report`), Workflow GitHub Actions 05:00 Sáng & Nghiệm thu Toàn tuyến E2E

**Description:** Mở rộng giao diện dòng lệnh `src/xsmn_alpha/cli.py` để tích hợp 3 lệnh con mới của Giai đoạn 3 (`sync-35`, `settle-ledger`, `daily-report`) đúng cú pháp tại Mục 3 của `spec.md` trong khi giữ nguyên 100% hoạt động của 3 lệnh Giai đoạn 2 (`ingest`, `falsify`, `run-pipeline`). Đóng gói quy trình tự động hóa miễn phí trong `.github/workflows/daily_quant_report.yml` (lập lịch thu thập kết quả sau giờ quay và phát bản tin lúc `05:00 ICT` / `22:00 UTC` kèm xuất bản GitHub Pages). Khởi tạo sổ cái `data/live/benchmark_ledger.json` nối tiếp từ chuỗi kiểm chứng thực chiến năm 2026, chạy thực nghiệm toàn tuyến các lệnh CLI (`sync-35`, `settle-ledger`, `daily-report --dry-run`) để sinh `public/index.html`, `public/daily/2026-10-26.html`, `public/daily/2026-10-26.json`, `data/live/latest_telegram_preview.txt`, và chạy toàn bộ bộ kiểm thử `pytest` (độ phủ $\ge 90\%$) cùng `ruff`.

**Acceptance criteria:**
- [x] Giao diện dòng lệnh `uv run python -m xsmn_alpha.cli` thực thi trơn tru cả 6 lệnh (`ingest`, `falsify`, `run-pipeline`, `sync-35`, `settle-ledger`, `daily-report`) và tệp `.github/workflows/daily_quant_report.yml` cấu hình chuẩn xác lịch cron `0 22 * * *` (`05:00 ICT`), đọc `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` từ GitHub Secrets và triển khai `public/` lên GitHub Pages.
- [x] Chạy thực tế lệnh `uv run python -m xsmn_alpha.cli daily-report --date 2026-10-26 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run` tạo đầy đủ `data/live/benchmark_ledger.json`, `data/live/latest_telegram_preview.txt`, `public/index.html`, `public/daily/2026-10-26.html` và `public/daily/2026-10-26.json`.
- [x] Toàn bộ bộ kiểm thử tự động `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90` đạt `100% PASS` với tổng độ phủ mã nguồn $\ge 90\%$, đồng thời `uv run ruff check src/ tests/` và `uv run ruff format --check src/ tests/` đạt `0 errors`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`
- [x] Build succeeds: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
- [x] Manual check: Chạy `uv run python -m xsmn_alpha.cli daily-report --date 2026-10-26 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run` và kiểm tra trực tiếp các tệp đầu ra tại `public/` và `data/live/`.

**Dependencies:** Task 3, Task 4, Task 6, Task 7, Task 8

**Files likely touched:**
- `src/xsmn_alpha/cli.py`
- `.github/workflows/daily_quant_report.yml`
- `data/live/benchmark_ledger.json`
- `public/index.html`
- `public/daily/2026-10-26.html`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: After Tasks 7-9
- [x] All tests pass with coverage >= 90% (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`)
- [x] Application passes all lint and format checks (`uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`)
- [x] All 8 Success Criteria (`SC-01` through `SC-08`) in Section 9 of `spec.md` are verified end-to-end
- [x] Review final Stage 3 Web Audit Report (`public/index.html` & `public/daily/2026-10-26.html`) and Telegram 05:00 AM Briefing with human
