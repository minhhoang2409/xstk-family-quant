# Task List: Giai Đoạn 2 — Hệ Thống Phát Hiện Alpha & Dự Báo Xác Suất Hiệu Chuẩn 1 Lồng Cầu XSMN (`stage2-alpha-discovery`)

**Mã Module:** `stage2-alpha-discovery`  
**Trạng thái:** Ready for Implementation (Pha 2: TASKS)  
**Ngày cập nhật:** 2026-10-25  
**Tài liệu đặc tả gốc:** [`specs/stage2-alpha-discovery/spec.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/spec.md)  
**Kế hoạch kiến trúc:** [`specs/stage2-alpha-discovery/plan.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/plan.md)

---

## Task 1: Khởi tạo dự án `uv` kèm hệ hằng số tài chính Giai đoạn 1

**Description:** Thiết lập cấu hình dự án Python `3.11` chuẩn `uv` tại `pyproject.toml` (khai báo đầy đủ `numpy`, `scipy`, `pydantic`, `httpx`, `pytest`, `pytest-cov`, `ruff`), khởi tạo gói `src/xsmn_alpha/`, định nghĩa toàn bộ hằng số tài chính bất biến từ Giai đoạn 1 (`REAL_PAYOUT_1D = 87.5`, `PRIZES_PER_DRAW = 18`, `BAO_LO_PAYOUT_PER_HIT = 87.5 / 18`, `BE_PROB_2D_NUMBER = 1 / 87.5`, `BE_PROB_SINGLE_BALL`, cấu hình 2 đài `XSHCM` 520/312 kỳ và `XSVL` 260/156 kỳ, thông số các cấu hình Điểm Ngọt) trong `constants.py`, đồng thời xây dựng hệ thống ngoại lệ Fail-Closed (`DataIntegrityError`, `TemporalLeakageError`, `CalibrationIntegrityError`, `InsufficientSampleSizeError`) trong `exceptions.py`.

**Acceptance criteria:**
- [x] Tệp `pyproject.toml` đồng bộ thành công qua `uv sync --all-extras` với đúng phiên bản thư viện quy định tại Mục 2 của `spec.md`.
- [x] Module `src/xsmn_alpha/constants.py` xuất chính xác các hằng số Giai đoạn 1 (`REAL_PAYOUT_1D == 87.5`, `BAO_LO_PAYOUT_PER_HIT == 175 / 36`, `BE_PROB_SINGLE_BALL == 0.1 * sqrt(100 / 87.5)`), cấu hình `STATION_CONFIG` cho `XSHCM` (`5y: 520`, `3y: 312`) cùng `XSVL` (`5y: 260`, `3y: 156`) và định nghĩa các bộ Điểm Ngọt (`2x2`, `3x3`, `core_2x2_sat_3x3`, `1x4`, `2x7`, `3x6`, `negative_filter_81`, `negative_filter_87`).
- [x] Module `src/xsmn_alpha/exceptions.py` định nghĩa lớp cơ sở `XSMNAlphaError` và đủ 4 ngoại lệ chuyên biệt cho 4 cổng kiểm soát đối kháng.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v`
- [x] Build succeeds: `uv run ruff check src/ tests/`
- [x] Manual check: Chạy `uv run python -c "from xsmn_alpha.constants import REAL_PAYOUT_1D, BAO_LO_PAYOUT_PER_HIT, BE_PROB_SINGLE_BALL; print(REAL_PAYOUT_1D, BAO_LO_PAYOUT_PER_HIT, BE_PROB_SINGLE_BALL)"` xác nhận in ra `87.5 4.861111111111111 0.10690449676496976`.

**Dependencies:** None

**Files likely touched:**
- `pyproject.toml`
- `src/xsmn_alpha/__init__.py`
- `src/xsmn_alpha/constants.py`
- `src/xsmn_alpha/exceptions.py`
- `tests/conftest.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 2: Thiết lập hợp đồng dữ liệu Pydantic v2 kèm cổng `DataSchemaGate`

**Description:** Xây dựng hệ thống Pydantic v2 Schemas nghiêm ngặt (`extra="forbid"`, `allow_inf_nan=False`) trong `src/xsmn_alpha/schemas.py` cho toàn bộ đường ống Giai đoạn 2, bao gồm `CanonicalDrawRecord`, `CageWindowTestResult`, `FalsificationReport`, `CalibratedCagePrediction`, `SweetSpotPortfolioMetrics`, `HorizonBacktestReport`, `DualHorizonStationReport` và `Stage3HandoffContract`. Cài đặt cổng kiểm soát `DataSchemaGate` ngay trong model validators để chặn đứng kỳ quay không đủ 18 giải, chuỗi giải không phải 2 chữ số ASCII (`"00"`–`"99"`), vector đếm 10 chiều có tổng khác 18 hoặc phân phối xác suất vi phạm miền đơn hình, đồng thời viết bộ kiểm thử đơn vị và đột biến âm tại `tests/test_constants_and_schemas.py`.

**Acceptance criteria:**
- [x] `CanonicalDrawRecord` kiểm tra nghiêm ngặt `station_code in {"XSHCM", "XSVL"}`, `len(prizes_last2) == 18`, mọi phần tử khớp mẫu ASCII `^[0-9]{2}$` (tự động từ chối ký tự Unicode full-width như `"０８"` hoặc chữ cái `"9A"`), và `sum(tens_counts) == 18`, `sum(units_counts) == 18` khớp chính xác với `prizes_last2`.
- [x] `Stage3HandoffContract` xác thực chặt chẽ bảng xác suất 10 bóng (`len == 10`, $\sum P_i = 1.0 \pm 10^{-6}$), vector xác suất 19 trạng thái trúng $P_{\text{AI}}(K = 0\dots18)$ (`len == 19`, $\sum_{k=0}^{18} P(K=k) = 1.0 \pm 10^{-6}$), chỉ số `conviction_score` và thông số kết quả của cả 2 khung `5y` và `3y`.
- [x] Bộ kiểm thử `tests/test_constants_and_schemas.py` kiểm chứng cả luồng hợp lệ (`PASS`) lẫn các kịch bản dữ liệu bẩn (`Negative Mutation FAIL` ném `DataIntegrityError` / `ValidationError`).

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_constants_and_schemas.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/schemas.py tests/test_constants_and_schemas.py`
- [x] Manual check: Thử khởi tạo `CanonicalDrawRecord` với 17 giải hoặc ký tự `"０８"` và xác nhận hệ thống ném ngoại lệ ngay lập tức.

**Dependencies:** Task 1

**Files likely touched:**
- `src/xsmn_alpha/schemas.py`
- `tests/test_constants_and_schemas.py`

**Estimated scope:** Small: 1-2 files

---

## Task 3: Xây dựng bộ chuẩn hóa lồng cầu `canonicalizer.py` hỗ trợ cắt lát khung `5Y`/`3Y`

**Description:** Triển khai module `src/xsmn_alpha/ingest/canonicalizer.py` chuyển đổi danh sách kết quả mở thưởng thô của từng đài thành chuỗi `CanonicalDrawRecord` đã xác thực qua `DataSchemaGate`, sắp xếp tăng dần nghiêm ngặt theo `draw_date` (chặn ngày trùng lặp hoặc lộn ngược thứ tự thời gian), tính vector đếm đa thức 10 chiều `tens_counts` và `units_counts` cho từng kỳ, và cung cấp hàm cắt lát `slice_horizon(draws, station_code, horizon)` để trích xuất khung `5Y` (`520` kỳ cho `XSHCM`, `260` kỳ cho `XSVL`) cùng khung `3Y` (`312` kỳ gần nhất cho `XSHCM`, `156` kỳ gần nhất cho `XSVL`) với chỉ số `draw_index` được đánh lại tuần tự từ `0` đến $T-1$.

**Acceptance criteria:**
- [x] Hàm chuẩn hóa phân rã chính xác 18 giải (theo thứ tự Giải Tám ở index `0` đến Giải Đặc Biệt ở index `17`) thành `tens_counts` và `units_counts` thỏa mãn bất biến $\sum_{i=0}^9 n_{t,i} = 18$.
- [x] Mọi chuỗi đầu vào có ngày quay trùng nhau, lộn ngược thứ tự thời gian hoặc thiếu giải đều bị chặn bởi `DataIntegrityError`.
- [x] Hàm cắt lát `slice_horizon` trả về đúng số kỳ quy định của khung `5y` và `3y` với `draw_index` liên tục `0 .. T-1` mà không làm thay đổi dữ liệu gốc.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar1_ingest_and_features.py -k "canonical" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/ingest/ tests/test_pillar1_ingest_and_features.py`
- [x] Manual check: Kiểm tra lát cắt `3y` trên chuỗi giả lập 520 kỳ của `XSHCM` trả về đúng 312 kỳ cuối cùng với `draw_index` từ `0` đến `311`.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/ingest/__init__.py`
- `src/xsmn_alpha/ingest/canonicalizer.py`
- `tests/test_pillar1_ingest_and_features.py`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: After Tasks 1-3
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application lints and formats without errors (`uv run ruff check src/ tests/`)
- [x] Foundation constants, Pydantic contracts, `DataSchemaGate`, and 5Y/3Y canonicalizer work end-to-end
- [x] Review with human if any schema adjustments are needed before proceeding

---

## Task 4: Xây dựng bộ thu thập dữ liệu tự động đa nguồn `fetcher.py` cho `XSHCM`/`XSVL`

**Description:** Triển khai `src/xsmn_alpha/ingest/fetcher.py` tự động hóa 100% quá trình tải lịch sử mở thưởng 5 năm cho `XSHCM` (~520 kỳ) và `XSVL` (~260 kỳ) qua kiến trúc 3 lớp: (1) Nguồn chính tải theo lô bất đồng bộ (`httpx.AsyncClient`, `max_concurrency=6`, `timeout=10.0s`, `retry=3`) từ `minhngoc.net.vn` bóc tách bảng `bkqtinhmiennam` lấy đúng 9 hạng giải (`giai8` $\to$ `giaidb`, tổng 18 giải/kỳ); (2) Nguồn dự phòng tự động failover sang `xskt.com.vn` và `xoso.com.vn` nếu kỳ quay bất kỳ thiếu giải; và (3) Lưu cache cục bộ tại `data/raw/<STATION>_draws.json` kèm mã toàn vẹn `SHA-256` và cơ chế đồng bộ tăng trưởng (`Incremental Delta Sync`).

**Acceptance criteria:**
- [x] Bộ parser HTML bóc tách chính xác ngày mở thưởng và đúng 18 giải (2 chữ số cuối, từ Giải 8 đến Giải ĐB) cho cả định dạng bảng nhiều kỳ của `minhngoc.net.vn` lẫn các trang dự phòng `xskt.com.vn` / `xoso.com.vn`.
- [x] Cơ chế Failover tự động gọi sang nguồn dự phòng khi nguồn chính trả về kỳ quay thiếu giải hoặc lỗi mạng, và ném `DataIntegrityError` nếu cả 3 nguồn đều không cung cấp đủ 18 giải hợp lệ.
- [x] Cache cục bộ tại `data/raw/` lưu kèm mã băm `SHA-256`, đọc trực tiếp từ đĩa ở các lần chạy tiếp theo mà không cần tải lại toàn bộ và chỉ đồng bộ các kỳ mới phát sinh.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar1_ingest_and_features.py -k "fetcher" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/ingest/fetcher.py tests/test_pillar1_ingest_and_features.py`
- [x] Manual check: Kiểm thử parser và luồng failover với HTML mẫu của `XSHCM` và `XSVL` xác nhận trích xuất đúng 18 giải theo thứ tự Giải 8 (index `0`) đến Giải ĐB (index `17`).

**Dependencies:** Task 2, Task 3

**Files likely touched:**
- `src/xsmn_alpha/ingest/fetcher.py`
- `tests/test_pillar1_ingest_and_features.py`

**Estimated scope:** Small: 1-2 files

---

## Task 5: Xây dựng bộ trích xuất 3 nhóm đặc trưng `extractor.py` khóa `PreDrawCutoffGate`

**Description:** Triển khai `src/xsmn_alpha/features/extractor.py` tính toán độc lập cho từng lồng cầu (`tens_cage` và `units_cage`) 3 nhóm đặc trưng vật lý – thống kê tại thời điểm khóa sổ $t-1$ (`Pre-Draw Feature Vector`): Nhóm 1 (`Regime Count Vectors` và tần suất chuẩn hóa trên cửa sổ $w \in \{5, 10, 15, 30, 60\}$ kỳ tính lùi từ $t-1$), Nhóm 2 (`Zero-Hit Gap Z-Score` với $q_0 = 0.9^{18}$, `Deficit Z-Score` trên 10 kỳ, và `Burst Rebound Indicator` sau kỳ nổ $\ge 3$ nháy), và Nhóm 3 (Ma trận chuyển trạng thái Markov bậc 1 làm mượt Laplace $\alpha_{\text{lap}} = 1.0$ từ trạng thái kích hoạt $S_{\tau-1, i} = \mathbb{I}(n_{\tau-1, i} \ge 2)$ cùng tỷ trọng xuất hiện 9 giải đầu buổi so với 9 giải cuối buổi). Tích hợp cổng `PreDrawCutoffGate` kiểm tra nghiêm ngặt `history[-1].draw_index < target_draw.draw_index` và `history[-1].draw_date < target_draw.draw_date`.

**Acceptance criteria:**
- [x] `PreDrawCutoffGate` ném `TemporalLeakageError` ngay lập tức nếu lát cắt lịch sử truyền vào rỗng, không liên tục, hoặc chứa bất kỳ kỳ quay nào có `draw_index >= target_draw.draw_index` hay `draw_date >= target_draw.draw_date`.
- [x] Kết quả `extract_features(draws[:t], draws[t])` hoàn toàn bất biến khi thay đổi hoặc đảo lộn toàn bộ dữ liệu tương lai `draws[t:]` (chứng minh không rò rỉ tương lai).
- [x] Cả 3 nhóm đặc trưng (`regime_counts`, `gap_z_scores` / `deficit_z_scores` / `burst_rebound`, và ma trận Markov `M_{i->j}` $10\times10$ với tổng mỗi hàng bằng `1.0`) khớp chính xác với công thức giải tích tại Mục 5.3.A của `spec.md`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar1_ingest_and_features.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/features/ tests/test_pillar1_ingest_and_features.py`
- [x] Manual check: Xác nhận mọi hàng của ma trận chuyển tiếp Markov $M_{i \to j}(t-1)$ có tổng bằng đúng `1.0` ($\pm 10^{-9}$) và truyền `draws[:t+1]` cho kỳ mục tiêu `draws[t]` bị chặn bởi `TemporalLeakageError`.

**Dependencies:** Task 2, Task 3

**Files likely touched:**
- `src/xsmn_alpha/features/__init__.py`
- `src/xsmn_alpha/features/extractor.py`
- `tests/test_pillar1_ingest_and_features.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 6: Xây dựng bộ 4 phép kiểm định thống kê đa cửa sổ `stats_tests.py`

**Description:** Triển khai `src/xsmn_alpha/falsification/stats_tests.py` thực hiện bộ 4 phép kiểm định thống kê trên từng cửa sổ $W \in \{15, 30, 60\}$ kỳ gần nhất ($M_W = 18 \times W$ lần nhả bóng) cho mỗi lồng cầu: (1) Kiểm định $\chi^2$ đa thức (`Multinomial Chi-Square Goodness-of-Fit`, bậc tự do $df=9$), (2) Tỷ số Hệ số Bayes `Dirichlet-Multinomial Bayes Factor` ($BF_{10}^{(W)}$ với tiên nghiệm đối xứng $\alpha_0 = 18.0$ tính hoàn toàn bằng `scipy.special.gammaln`), (3) Shannon Entropy chuẩn hóa $H_{\text{norm}}^{(W)} \in [0, 1]$, và (4) Kiểm định tính độc lập chuỗi gồm `Wald-Wolfowitz Runs Test` trên chuỗi kích hoạt $S_{\tau, i} = \mathbb{I}(n_{\tau, i} \ge 2)$ cùng kiểm định $\chi^2_{\text{Markov}}$ trên bảng tần suất chuyển tiếp $10 \times 10$.

**Acceptance criteria:**
- [x] Công thức `Dirichlet-Multinomial Bayes Factor` $BF_{10}^{(W)}$ tính trong không gian logarit bằng `gammaln` không bao giờ bị tràn số (`overflow`/`underflow`), trả về $BF_{10} < 1.0$ khi tần suất 10 bóng phẳng ($O_i \approx 1.8 W$) và $BF_{10} \gg 3.0$ khi có độ lệch thực sự.
- [x] Các hàm tính $\chi^2_W$ ($p_{\chi^2} = 1 - F_{\chi^2_9}(\chi^2_W)$), $H_{\text{norm}}^{(W)} \in [0, 1]$ (đạt `1.0` khi phân phối đều tuyệt đối), và kiểm định độc lập chuỗi (`Runs Test` + `Markov Chi-Square`) trả kết quả chính xác trên cả 3 cửa sổ $W \in \{15, 30, 60\}$.
- [x] Mọi đầu vào có cỡ mẫu nhỏ hơn 60 kỳ ($T < 60$) hoặc chứa `NaN`/`Inf` đều bị chặn ngay lập tức bởi `InsufficientSampleSizeError` hoặc `DataIntegrityError`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar2_falsification_gatekeeper.py -k "stats" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/falsification/ tests/test_pillar2_falsification_gatekeeper.py`
- [x] Manual check: Chạy kiểm định trên vector đếm đồng nhất $O_i = 54$ ($W=30, M_W=540$) xác nhận $\chi^2 = 0.0, p_{\chi^2} = 1.0, H_{\text{norm}} = 1.0$ và $BF_{10} < 1.0$.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/falsification/__init__.py`
- `src/xsmn_alpha/falsification/stats_tests.py`
- `tests/test_pillar2_falsification_gatekeeper.py`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: After Tasks 4-6
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application lints and formats without errors (`uv run ruff check src/ tests/`)
- [x] Multi-source fetcher, `PreDrawCutoffGate` feature extractor, and multi-window statistical tests work cleanly together
- [x] Review with human if any feature or statistical test tolerances need adjustment before proceeding

---

## Task 7: Xây dựng bộ đối chứng 1,000 chuỗi Monte Carlo kèm phễu `gatekeeper.py`

**Description:** Triển khai `src/xsmn_alpha/falsification/monte_carlo.py` sinh $B = 1,000$ chuỗi lịch sử ngẫu nhiên giả lập chuẩn $p_i = 0.10$ bằng bộ sinh vector hóa `numpy.random.Generator(PCG64(seed=42))` tương ứng với từng quy mô mẫu (`5Y` và `3Y` của `XSHCM` và `XSVL`) để xác lập ngưỡng phân vị 90% và 95% của thống kê cực đại $\tilde{\chi}^2_{\max, b} = \max_{W \in \{15,30,60\}} \chi^2_W$. Xây dựng `src/xsmn_alpha/falsification/gatekeeper.py` thực thi cổng `FalsificationGatekeeper` phân loại trạng thái từng lồng cầu và toàn đài thành `PASS_ALPHA`, `WARN_WEAK_SIGNAL`, hoặc `FAIL_WHITE_NOISE_CASH_BRAKE` (khóa `recommended_capital_multiplier = 0.0`).

**Acceptance criteria:**
- [x] Bộ sinh 1,000 chuỗi Monte Carlo Null với `seed=42` hoàn toàn tất định (tái lập 100% cùng giá trị phân vị 90% và 95% qua các lần chạy) và hoàn tất 1,000 mô phỏng trong thời gian $< 2$ giây nhờ vector hóa `numpy`.
- [x] Khi đưa chuỗi ngẫu nhiên thuần túy ($p_i = 10.0\%$) qua `FalsificationGatekeeper`, hệ thống bắt buộc trả về `FAIL_WHITE_NOISE_CASH_BRAKE` và `recommended_capital_multiplier == 0.0`.
- [x] Khi đưa chuỗi giả lập có độ lệch vật lý thật ($+9.0\%$/lồng ở 2 bóng đầu) qua `FalsificationGatekeeper`, hệ thống xác nhận `PASS_ALPHA` với $\chi^2_{\max}$ vượt phân vị 95% của 1,000 chuỗi Null và $\max_W BF_{10}^{(W)} \ge 3.0$.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar2_falsification_gatekeeper.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/falsification/ tests/test_pillar2_falsification_gatekeeper.py`
- [x] Manual check: Chạy 2 lần liên tiếp hàm sinh Monte Carlo với `seed=42` và xác nhận phân vị 90%/95% giống hệt nhau đến chữ số thập phân thứ 12.

**Dependencies:** Task 6

**Files likely touched:**
- `src/xsmn_alpha/falsification/monte_carlo.py`
- `src/xsmn_alpha/falsification/gatekeeper.py`
- `tests/test_pillar2_falsification_gatekeeper.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 8: Xây dựng hai nhánh dự báo xác suất `bocd_dirichlet.py` cùng `markov_gap_model.py`

**Description:** Triển khai 2 nhánh dự báo độc lập trong `src/xsmn_alpha/engine/`: (1) Nhánh 1 `bocd_dirichlet.py` thực thi thuật toán `Bayesian Online Changepoint Detection` (Adams & MacKay 2007) kết hợp hậu nghiệm `Dirichlet-Multinomial` ($R_{\max} = 60$, kỳ vọng độ dài trạng thái $\lambda_{\text{regime}} = 25.0 \implies h = 0.04$, tiên nghiệm co rút $\alpha_0 = 18.0$) để tính phân phối $P_{\text{BOCD}}(0\dots9)$ tích hợp qua mọi độ dài trạng thái $r_{t-1}$; và (2) Nhánh 2 `markov_gap_model.py` ước lượng điểm logit kết hợp ma trận chuyển tiếp Markov bậc 1 từ kỳ $t-1$ và áp lực chu kỳ gan chuẩn hóa với phạt chuẩn hóa $L_2$ mạnh ($\lambda_{L2} = 10.0$) qua hàm Softmax nhiệt độ $\tau_{\text{temp}} \ge 1.0$ để xuất phân phối $P_{\text{Seq}}(0\dots9)$.

**Acceptance criteria:**
- [x] Nhánh 1 (`bocd_dirichlet.py`) bảo toàn $\sum_{r=0}^{R_{\max}} P(r_{t-1} = r \mid \mathbf{c}_{1:t-1}) = 1.0$ và $\sum_{i=0}^9 P_{\text{BOCD}}(i) = 1.0 \pm 10^{-9}$ tại mọi bước thời gian $t$.
- [x] Khi mô phỏng sự kiện nhà đài thay bộ bóng mới (đảo ngược tập bóng nóng sang tập bóng khác tại kỳ $t=100$), hậu nghiệm BOCD tự động dịch chuyển trọng số về các độ dài trạng thái ngắn và hạ xác suất của bóng nóng cũ về sát nền $10.0\%$ (sai số $< 0.8\%$) trong vòng $\le 4$ kỳ mở thưởng.
- [x] Nhánh 2 (`markov_gap_model.py`) chỉ sử dụng đặc trưng tính đến kỳ $t-1$, xuất phân phối $P_{\text{Seq}}(0\dots9)$ có tổng bằng `1.0` ($\pm 10^{-9}$) và không bao giờ sinh giá trị âm hoặc `NaN`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar3_calibrated_engine.py -k "bocd or markov" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/engine/ tests/test_pillar3_calibrated_engine.py`
- [x] Manual check: Chạy kịch bản giả lập điểm gãy trạng thái ở kỳ 100 và kiểm tra tốc độ co rút xác suất của `BayesianDirichletBOCD` trong 4 kỳ kế tiếp.

**Dependencies:** Task 5

**Files likely touched:**
- `src/xsmn_alpha/engine/__init__.py`
- `src/xsmn_alpha/engine/bocd_dirichlet.py`
- `src/xsmn_alpha/engine/markov_gap_model.py`
- `tests/test_pillar3_calibrated_engine.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 9: Xây dựng bộ hợp nhất lồi `calibration_pooler.py` khóa `SimplexCalibrationGate`

**Description:** Triển khai `src/xsmn_alpha/engine/calibration_pooler.py` thực hiện hợp nhất tuyến tính lồi $P_{\text{AI}}(i) = w_1 P_{\text{BOCD}}(i) + w_2 P_{\text{Seq}}(i) + (1 - w_1 - w_2) \cdot 0.10$ với trọng số $(w_1, w_2)$ được tối ưu hóa bằng `scipy.optimize.minimize(method="SLSQP")` trên cửa sổ trượt quá khứ $W_{\text{val}} = 30$ kỳ gần nhất ($\tau \in \{t-30 \dots t-1\}$) nhằm cực tiểu hóa `Out-of-Sample Multi-class Brier Score` có phạt chuẩn hóa. Tính toán chỉ số `conviction_score` phản ánh độ lệch hiệu chuẩn của Top bóng so với ngưỡng hòa vốn `+6.9045%/lồng` và cài đặt cổng `SimplexCalibrationGate` ném `CalibrationIntegrityError` nếu xác suất đầu ra hoặc trọng số hợp nhất vi phạm ràng buộc đơn hình.

**Acceptance criteria:**
- [x] Bộ tối ưu `SLSQP` luôn tìm được cặp trọng số hợp lệ thỏa mãn $w_1 \ge 0, w_2 \ge 0, w_1 + w_2 \le 1.0$, và bảng xác suất $P_{\text{AI}}(0\dots9)$ đạt `Out-of-Sample Multi-class Brier Score` nhỏ hơn hoặc bằng mô hình tần suất trượt ngây thơ (`Naive Rolling Frequency`).
- [x] Cổng `SimplexCalibrationGate` kiểm tra nghiêm ngặt $P_{\text{AI}}(i) \ge 0$, không chứa `NaN`/`Inf`, và $\left|\sum_{i=0}^9 P_{\text{AI}}(i) - 1.0\right| \le 10^{-6}$; tự động ném `CalibrationIntegrityError` khi truyền trọng số $w_1 + w_2 > 1.0$ hoặc xác suất âm.
- [x] Khi dữ liệu quá khứ là nhiễu trắng thuần túy, bộ hợp nhất tự động co rút trọng số $(w_1 + w_2)$ về gần `0`, kéo $P_{\text{AI}}(i)$ sát về nền an toàn $10.0\%$.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar3_calibrated_engine.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/engine/calibration_pooler.py tests/test_pillar3_calibrated_engine.py`
- [x] Manual check: Kiểm tra tổng $\sum_{i=0}^9 P_{\text{AI}}(i) == 1.0$ trên 100 kỳ trượt liên tiếp và xác nhận `CalibrationIntegrityError` được kích hoạt khi cố tình truyền $w_1 = 0.7, w_2 = 0.5$.

**Dependencies:** Task 8

**Files likely touched:**
- `src/xsmn_alpha/engine/calibration_pooler.py`
- `tests/test_pillar3_calibrated_engine.py`

**Estimated scope:** Small: 1-2 files

---

## Checkpoint: After Tasks 7-9
- [x] All tests pass (`uv run pytest tests/ -v`)
- [x] Application lints and formats without errors (`uv run ruff check src/ tests/`)
- [x] Falsification Gatekeeper (`1,000 Monte Carlo Nulls`) and Dual-Branch Calibrated Probability Engine (`BOCD + Markov-Gap + SLSQP Pooler`) work end-to-end
- [x] Review with human if any calibration or gatekeeper parameters need tuning before proceeding

---

## Task 10: Xây dựng bộ đo suy giảm Alpha kèm bộ mô phỏng Điểm Ngọt 19 trạng thái

**Description:** Triển khai `src/xsmn_alpha/backtest/alpha_decay.py` thống kê tần suất nổ thực tế ngoài mẫu theo thứ hạng bóng dự báo (`Rank 1` $\to$ `Rank 10`) trên từng lồng cầu, và `src/xsmn_alpha/backtest/sweet_spot_sim.py` chấm điểm đồng thời các cấu hình Điểm Ngọt tại mỗi kỳ $t$: các bộ đồng nhất `1.0đ`/số (`2x2 = 4 số`, `3x3 = 9 số`, `1x4 = 4 số`, `2x7 = 14 số`, `3x6 = 18 số`), danh mục lai `Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ)` (`6.5đ`/kỳ), và chiến thuật loại trừ bóng chết `Negative Filter` (`81 số` và `87 số` đánh trên Giải Đặc Biệt index `17`, trả thưởng `87.5đ`), đồng thời tính phân phối xác suất 19 trạng thái trúng $P_{\text{AI}}(K = 0\dots18)$ phục vụ công thức Kelly Đa Kết Quả ở Giai đoạn 3.

**Acceptance criteria:**
- [x] Công thức tính chi phí, doanh thu và lợi nhuận ròng từng kỳ của mọi cấu hình (`2x2` vốn `4.0đ`, `3x3` vốn `9.0đ`, `Core 2x2 + Satellite 3x3` vốn `6.5đ` với nhóm Lõi nhận `4.861111đ`/lô và nhóm Vệ tinh nhận `2.430556đ`/lô, `Negative Filter` vốn `81.0đ`/`87.0đ` nhận `87.5đ` khi trúng Giải ĐB) khớp tuyệt đối với quy tắc dòng tiền tại `QUY_TAC_VA_DIEM_HOA_VON.md`.
- [x] Bộ thống kê tổng hợp chính xác các chỉ số chuẩn 30 kỳ (`540 giải`) và toàn kỳ: `hits_per_30_draws` (so với mốc hòa vốn `24.69 lô` của bộ `2x2` và `55.54 lô` của bộ `3x3`), `daily_win_rate`, `multi_hit_rate_ge2`, `zero_hit_rate_k0`, `max_losing_streak`, `max_drawdown`, và đường cong tần suất thực tế `Rank 1 .. Rank 10` (tổng 10 hạng bằng đúng `100.0%`).
- [x] Hàm tính phân phối nhị thức/Poisson-Binomial 19 trạng thái $P_{\text{AI}}(K = 0\dots18)$ bảo toàn $\sum_{k=0}^{18} P_{\text{AI}}(K = k) = 1.0 \pm 10^{-9}$ với kỳ vọng $\sum_{k=0}^{18} k \cdot P_{\text{AI}}(K = k) = 18 \cdot p_{\mathcal{S}}$.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar4_walk_forward_backtest.py -k "decay or sweet_spot" -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/backtest/ tests/test_pillar4_walk_forward_backtest.py`
- [x] Manual check: Kiểm tra tay một kỳ mở thưởng mẫu với bộ `Core 2x2 + Satellite 3x3` khi nổ 1 lô Lõi + 1 lô Vệ tinh xác nhận thu về `4.861111 + 2.430556 = 7.291667đ` và lãi ròng `+0.791667đ`.

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `src/xsmn_alpha/backtest/__init__.py`
- `src/xsmn_alpha/backtest/alpha_decay.py`
- `src/xsmn_alpha/backtest/sweet_spot_sim.py`
- `tests/test_pillar4_walk_forward_backtest.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 11: Xây dựng bộ điều phối Walk-Forward `runner.py` kèm báo cáo HTML/CLI

**Description:** Triển khai `src/xsmn_alpha/backtest/runner.py` điều phối quy trình kiểm thử cuốn chiếu từng kỳ (`Strict Step-by-Step Walk-Forward`, `warmup = 45` kỳ) cho cả `XSHCM` và `XSVL` trên 2 khung thời gian `5Y` và `3Y`, kết nối tuần tự Trụ cột 1 $\to$ Trụ cột 2 $\to$ Trụ cột 3 $\to$ Trụ cột 4 và xuất hợp đồng bàn giao `Stage3HandoffContract`. Xây dựng `src/xsmn_alpha/reporting/html_report.py` xuất báo cáo JSON/HTML đối chiếu trực quan giữa `XSHCM` (2 kỳ/tuần) và `XSVL` (1 kỳ/tuần) qua 2 khung `5Y` vs `3Y` đặt cạnh dải phân vị 90%/95% của 1,000 chuỗi Monte Carlo Null, đồng thời hoàn thiện giao diện dòng lệnh `src/xsmn_alpha/cli.py` (`ingest`, `falsify`, `run-pipeline`) với cấu hình chuẩn UTF-8.

**Acceptance criteria:**
- [x] `WalkForwardRunner` thực thi nghiêm ngặt vòng lặp trượt từ $t = T_{\text{warmup}}$ (`45`) đến $T-1$, chỉ truyền `draws[:t]` vào bộ dự báo kỳ $t$, và đánh giá đầy đủ 4 tổ hợp thực nghiệm: `XSHCM-5Y`, `XSHCM-3Y`, `XSVL-5Y`, `XSVL-3Y`.
- [x] Module `reporting/html_report.py` xuất thành công `reports/stage2_dual_station_comparison.json`, `reports/stage2_dual_station_report.html` và 2 file hợp đồng `data/outputs/stage3_handoff_XSHCM.json`, `data/outputs/stage3_handoff_XSVL.json` hợp lệ 100% theo `Stage3HandoffContract`.
- [x] Giao diện dòng lệnh `src/xsmn_alpha/cli.py` gọi `sys.stdout.reconfigure(encoding="utf-8")` và hỗ trợ đầy đủ 3 lệnh con `ingest`, `falsify`, `run-pipeline` đúng cú pháp tại Mục 3 của `spec.md`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_pillar4_walk_forward_backtest.py -v`
- [x] Build succeeds: `uv run ruff check src/xsmn_alpha/ tests/test_pillar4_walk_forward_backtest.py`
- [x] Manual check: Chạy `uv run python -m xsmn_alpha.cli --help` xác nhận hiển thị rõ 3 lệnh `ingest`, `falsify`, `run-pipeline` cùng các tham số chuẩn không lỗi font tiếng Việt.

**Dependencies:** Task 4, Task 7, Task 9, Task 10

**Files likely touched:**
- `src/xsmn_alpha/backtest/runner.py`
- `src/xsmn_alpha/reporting/__init__.py`
- `src/xsmn_alpha/reporting/html_report.py`
- `src/xsmn_alpha/cli.py`
- `tests/test_pillar4_walk_forward_backtest.py`

**Estimated scope:** Medium: 3-5 files

---

## Task 12: Kiểm thử đột biến đối kháng kèm thực thi pipeline thực nghiệm 5 năm

**Description:** Xây dựng bộ kiểm thử đột biến đối kháng toàn diện `tests/test_adversarial_mutations.py` tấn công trực diện cả 4 cổng kiểm soát (`DataSchemaGate`, `PreDrawCutoffGate`, `SimplexCalibrationGate`, `FalsificationGatekeeper`) để chứng minh hệ thống không thể báo `PASS_ALPHA` giả tạo trước dữ liệu bẩn hoặc nhiễu trắng. Tiếp đó, thực thi trọn vẹn các lệnh CLI chuẩn để thu thập lịch sử 5 năm thực tế của `XSHCM` (~520 kỳ) và `XSVL` (~260 kỳ), chạy kiểm định 1,000 chuỗi Monte Carlo (`seed=42`) cùng Walk-Forward Backtest trên cả 2 khung `5Y` và `3Y`, sinh đầy đủ các file dữ liệu chuẩn hóa, báo cáo đối chiếu thực nghiệm và hợp đồng bàn giao sang Giai đoạn 3.

**Acceptance criteria:**
- [x] Bộ kiểm thử `tests/test_adversarial_mutations.py` xác nhận 100% kịch bản tấn công trên 4 cổng (`DataSchemaGate`, `PreDrawCutoffGate`, `SimplexCalibrationGate`, `FalsificationGatekeeper`) đều bị chặn đúng ngoại lệ quy định tại Mục 5.5 của `spec.md`.
- [x] Thực thi thành công 3 lệnh CLI chuẩn (`ingest`, `falsify`, `run-pipeline`) tạo ra các tệp thực nghiệm hợp lệ: `data/canonical/XSHCM_canonical.json`, `data/canonical/XSVL_canonical.json`, `data/outputs/stage3_handoff_XSHCM.json`, `data/outputs/stage3_handoff_XSVL.json`, và `reports/stage2_dual_station_comparison.json`.
- [x] Toàn bộ bộ kiểm thử tự động `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90` đạt `100% PASS` với độ phủ mã nguồn $\ge 90\%$ và `uv run ruff check src/ tests/` cùng `uv run ruff format --check src/ tests/` sạch lỗi 100%.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`
- [x] Build succeeds: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
- [x] Manual check: Kiểm tra sự tồn tại và tính hợp lệ của `data/outputs/stage3_handoff_XSHCM.json`, `data/outputs/stage3_handoff_XSVL.json` và bảng đối chiếu `XSHCM` vs `XSVL` (`5Y` vs `3Y`) tại `reports/`.

**Dependencies:** Task 11

**Files likely touched:**
- `tests/test_adversarial_mutations.py`
- `data/canonical/XSHCM_canonical.json`
- `data/canonical/XSVL_canonical.json`
- `data/outputs/stage3_handoff_XSHCM.json`
- `data/outputs/stage3_handoff_XSVL.json`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: After Tasks 10-12
- [x] All tests pass with coverage >= 90% (`uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`)
- [x] Application passes all lint and format checks (`uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`)
- [x] All 6 Success Criteria in Section 9 of `spec.md` are verified on real 5Y/3Y data for `XSHCM` and `XSVL`
- [x] Review final Stage 2 empirical findings and `stage3_handoff_<station>.json` files with human before transitioning to Stage 3

---

## Task 13: Nâng cấp Cửa sổ Quá khứ Thích ứng Nhân quả (`Causal Past-Window Optimizer` $W^*_{t-1}$) & Loại bỏ ngưỡng tự chế `noise_floor`

**Description:** Bổ sung hàm tính phương sai nhiễu lý thuyết trực tiếp từ bài toán $\sigma_{\text{nhiễu}}(W^*) = \frac{1}{\sqrt{200 \times W^*}}$ cùng tập ứng viên cửa sổ quá khứ $\mathcal{W} = \{3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60\}$ vào `constants.py`; triển khai bộ tối ưu hóa cửa sổ quá khứ nhân quả `CausalPastWindowOptimizer` ($W^*_{t-1}$) đánh giá độc lập cho từng lồng cầu (`tens_cage` và `units_cage`) chỉ trên dữ liệu quá khứ `draws[0 : t]` (che kín ngày hôm nay `draws[t]`) và tích hợp vào `src/xsmn_alpha/engine/bocd_dirichlet.py` và `src/xsmn_alpha/engine/calibration_pooler.py`; xóa bỏ hoàn toàn ngưỡng tự chế `noise_floor = 3.5e-4` gây lỗi tie-breaker `[0, 1, 2...]`; bổ sung unit tests kiểm chứng tính nhân quả (`draws[0 : t]`) và không còn `noise_floor = 3.5e-4`, chạy lại toàn bộ `pytest` và `run-pipeline` để xuất báo cáo mới.

**Acceptance criteria:**
- [x] Module `src/xsmn_alpha/constants.py` xuất `CANDIDATE_PAST_WINDOWS = (3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60)` và hàm `compute_theoretical_noise_std(window_draws)` tính chính xác $\sigma_{\text{nhiễu}}(W) = \frac{1}{\sqrt{200 \times W}}$.
- [x] Bộ `CausalPastWindowOptimizer` trong `src/xsmn_alpha/engine/bocd_dirichlet.py` tìm $W^*_{t-1} \in \mathcal{W}$ độc lập cho từng lồng cầu chỉ từ lịch sử `draws[0 : t]` (bất biến 100% khi thay đổi `draws[t:]`) đồng thời vẫn bảo toàn khả năng phát hiện điểm gãy thay bóng mới trong $\le 4$ kỳ.
- [x] Module `src/xsmn_alpha/engine/calibration_pooler.py` loại bỏ hoàn toàn ngưỡng tự chế `noise_floor = 3.5e-4`, sử dụng điều chuẩn giải tích dựa trên $\sigma^2_{\text{nhiễu}}(W^*_{t-1})$ và bảo toàn thứ hạng thông tin thực nghiệm mà không bị suy biến về `[0, 1, 2, 3, ...]`.
- [x] Bộ kiểm thử `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90` đạt `100% PASS` và chạy lại `run-pipeline` cập nhật đầy đủ `data/outputs/stage3_handoff_XSHCM.json`, `data/outputs/stage3_handoff_XSVL.json`, `reports/stage2_dual_station_comparison.json`, `reports/stage2_dual_station_report.html`.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`
- [x] Build succeeds: `uv run ruff check src/ tests/; uv run ruff format --check src/ tests/`
- [x] Manual check: Xác nhận không còn `noise_floor` trong `calibration_pooler.py`, kiểm tra kết quả Walk-Forward mới của `XSHCM` và `XSVL` trong `reports/stage2_dual_station_comparison.json`.

**Dependencies:** Task 8, Task 9, Task 12

**Files likely touched:**
- `src/xsmn_alpha/constants.py`
- `src/xsmn_alpha/engine/bocd_dirichlet.py`
- `src/xsmn_alpha/engine/calibration_pooler.py`
- `tests/test_pillar3_calibrated_engine.py`
- `tests/test_adversarial_mutations.py`
- `data/outputs/stage3_handoff_XSHCM.json`
- `data/outputs/stage3_handoff_XSVL.json`
- `reports/stage2_dual_station_comparison.json`
- `reports/stage2_dual_station_report.html`

**Estimated scope:** Medium: 4-6 files

---

## Task 14: Nâng cấp Quy luật Trừ Khấu Hao Kỳ Liền Trước (`Lag-1 Burst Exhaustion Filter`) & Xóa bỏ nghịch lý `Rank 1 < Rank 2`

**Description:** Cập nhật tập ứng viên cửa sổ quá khứ hội tụ `CANDIDATE_PAST_WINDOWS = (15, 20, 25, 30, 40, 50, 60)` và hằng số `LAG1_EXHAUSTION_PENALTY = 0.35` trong `src/xsmn_alpha/constants.py`; tích hợp công thức trừ khấu hao kỳ liền trước $\tilde{N}_{\tau-1, i}^{(W)} = \max\left(0, \sum_{k=1}^W n_{\tau-k, i} - \gamma_{\text{lag1}} \cdot \frac{W}{20} \cdot n_{\tau-1, i}\right)$ vào `CausalPastWindowOptimizer` và `BayesianDirichletBOCD` trong `src/xsmn_alpha/engine/bocd_dirichlet.py`; đảo dấu trọng số `w_burst` sang phạt âm (`-0.10`) trong `src/xsmn_alpha/engine/markov_gap_model.py`; bổ sung kiểm thử xác nhận `Rank 1 > Rank 2` và chạy lại toàn bộ `pytest` cùng `run-pipeline` để xuất bộ báo cáo mới.

**Acceptance criteria:**
- [x] `src/xsmn_alpha/constants.py` xuất `CANDIDATE_PAST_WINDOWS = (15, 20, 25, 30, 40, 50, 60)` và `LAG1_EXHAUSTION_PENALTY = 0.35`.
- [x] `CausalPastWindowOptimizer` và `BayesianDirichletBOCD` trong `src/xsmn_alpha/engine/bocd_dirichlet.py` áp dụng bộ lọc trừ khấu hao kỳ liền trước (`Lag-1 Burst Exhaustion Filter`) khi tính toán trên các cửa sổ hội tụ $W \ge 15$, trong khi vẫn bảo toàn bất biến đơn hình và khả năng thích ứng điểm gãy trong $\le 4$ kỳ.
- [x] `RegularizedMarkovGapModel` trong `src/xsmn_alpha/engine/markov_gap_model.py` phạt âm (`-0.10`) đối với chỉ báo nổ đột biến kỳ liền trước (`burst_rebound`).
- [x] Toàn bộ kiểm thử `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90` đạt `100% PASS` và chạy lại `run-pipeline` xác nhận trên cả 2 đài (`XSVL` và `XSHCM`), tần suất nổ thực tế ngoài mẫu của `Rank 1` cao hơn `Rank 2` trên cả Lồng Chục lẫn Lồng Đơn Vị ở cả hai khung `5Y` và `3Y`, đồng thời trên khung 3 năm hiện hành của đài có tín hiệu (`XSVL-3Y`), cả bộ `2x2` (`+11.67%`) và `1x4` (`+8.39%`) đều đạt ROI dương.

**Verification:**
- [x] Tests pass: `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90`
- [x] Build succeeds: `uv run ruff check src/ tests/; uv run ruff format --check src/ tests/`
- [x] Manual check: Kiểm tra đường cong `tens_rank_alpha_decay` và `units_rank_alpha_decay` của `XSVL` trong `reports/stage2_dual_station_comparison.json` đảm bảo `Rank 1 > Rank 2`.

**Dependencies:** Task 13

**Files likely touched:**
- `src/xsmn_alpha/constants.py`
- `src/xsmn_alpha/engine/bocd_dirichlet.py`
- `src/xsmn_alpha/engine/markov_gap_model.py`
- `tests/test_pillar3_calibrated_engine.py`
- `reports/stage2_dual_station_comparison.json`
- `reports/stage2_dual_station_report.html`
- `data/outputs/stage3_handoff_XSHCM.json`
- `data/outputs/stage3_handoff_XSVL.json`

**Estimated scope:** Medium: 4-6 files
