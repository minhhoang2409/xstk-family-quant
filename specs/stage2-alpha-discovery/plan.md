# Implementation Plan: Giai Đoạn 2 — Hệ Thống Phát Hiện Alpha & Dự Báo Xác Suất Hiệu Chuẩn 1 Lồng Cầu XSMN (`stage2-alpha-discovery`)

**Mã Module:** `stage2-alpha-discovery`  
**Trạng thái:** Ready for Review (Pha 2: PLAN)  
**Ngày cập nhật:** 2026-10-25  
**Tài liệu đặc tả gốc:** [`specs/stage2-alpha-discovery/spec.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/spec.md)  
**Danh sách tác vụ chi tiết:** [`specs/stage2-alpha-discovery/todo.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/todo.md)

---

## Overview

Triển khai trọn vẹn hệ thống định lượng Giai đoạn 2 (`xsmn_alpha`) theo **Phương án C: Kiến Trúc Lai Hai Tầng "Phễu Kiểm Định Chống Nhiễu + Hội Đồng Co Rút Thích Ứng" (`Two-Stage Gatekeeper & Regularized Ensemble`)** cho bài toán chọn bóng trên **1 Lồng Cầu (`0`–`9`)**, áp dụng độc lập và đồng nhất cho **Lồng Hàng Chục (`tens_cage`)** và **Lồng Hàng Đơn Vị (`units_cage`)** trên **Đài TP. Hồ Chí Minh (`XSHCM` — 2 kỳ/tuần)** và **Đài Vĩnh Long (`XSVL` — 1 kỳ/tuần)** qua cả 2 khung thời gian lịch sử **5 năm (`5Y`)** và **3 năm gần nhất (`3Y`)**. Hệ thống tự động thu thập và xác thực chéo dữ liệu 18 giải/kỳ, trích xuất 3 nhóm đặc trưng vật lý – thống kê dưới chốt chặn `Pre-Draw Temporal Cutoff (t-1)`, đối chứng trực tiếp với 1,000 chuỗi ngẫu nhiên giả lập (`Monte Carlo Null Benchmark`, `seed=42`), hợp nhất xác suất hiệu chuẩn $\sum_{i=0}^9 P_{\text{AI}}(i) = 1.0$, kiểm thử trượt (`Walk-Forward Backtest`) các cấu hình Điểm Ngọt (`2x2=4`, `3x3=9`, `Core 2x2 + Satellite 3x3`, `1x4`, `2x7`, `3x6`, `Negative Filter 81/87`) và xuất hợp đồng JSON 19 trạng thái trúng $P_{\text{AI}}(K=0\dots18)$ bàn giao trực tiếp sang Giai đoạn 3 (Quản lý vốn Kelly Đa Kết Quả).

---

## Architecture Decisions

- **AD-01 — Kiến trúc Mô-đun Tách biệt theo 4 Trụ cột & 4 Cổng Kiểm soát Đối kháng (`Fail-Closed Adversarial Gates`):**
  - Tách bạch rõ ràng các lớp `constants.py` / `schemas.py` / `exceptions.py` $\rightarrow$ `ingest` & `features` (Trụ cột 1) $\rightarrow$ `falsification` (Trụ cột 2) $\rightarrow$ `engine` (Trụ cột 3) $\rightarrow$ `backtest` & `reporting` (Trụ cột 4).
  - Cài đặt 4 chốt chặn cứng (`DataSchemaGate`, `PreDrawCutoffGate`, `SimplexCalibrationGate`, `FalsificationGatekeeper`) ném ngoại lệ chuyên biệt ngay tại biên hàm để ngăn chặn tuyệt đối dữ liệu bẩn, rò rỉ tương lai (*Look-Ahead Leakage*) hoặc xác suất lệch chuẩn.
- **AD-02 — Thu thập Dữ liệu Bất đồng bộ Đa nguồn Có Kiểm soát (`Polite Async Batching + Dual Fallback + Incremental Cache`):**
  - Sử dụng `httpx.AsyncClient` (`max_concurrency=6`, `timeout=10.0s`, `retry=3`) tải theo lô từ `minhngoc.net.vn` (`6–7 kỳ/trang`, chỉ cần ~87 trang cho `XSHCM` và ~38 trang cho `XSVL`), tự động failover sang `xskt.com.vn` và `xoso.com.vn` nếu thiếu giải, và lưu cache `data/raw/<STATION>_draws.json` kèm mã băm `SHA-256` để các lần chạy sau đạt tốc độ tức thì (`0 giây` chờ mạng).
- **AD-03 — Tính toán Vector hóa trong Không gian Logarit (`Log-Space Numerical Stability`):**
  - Mọi phép tính xác suất đa thức, hàm hợp lý biên `Dirichlet-Multinomial Bayes Factor` ($BF_{10}$), và cập nhật lưới độ dài trạng thái `Bayesian Dirichlet-BOCD` ($R_{\max}=60$) đều thực hiện bằng `scipy.special.gammaln` và `scipy.special.logsumexp` trên mảng `numpy.float64` để triệt tiêu hoàn toàn hiện tượng tràn số dưới (*underflow*) khi nhân qua $18 \times 60 = 1,080$ lần nhả bóng.
- **AD-04 — Hợp nhất Lồi Hiệu chuẩn Ngoài mẫu (`Out-of-Sample Convex Brier Pooling`):**
  - Sử dụng `scipy.optimize.minimize(method="SLSQP")` trên cửa sổ trượt 30 kỳ quá khứ ($\tau \in \{t-30 \dots t-1\}$) với ràng buộc $w_1 \ge 0, w_2 \ge 0, w_1 + w_2 \le 1$ để kết hợp `Bayesian Dirichlet-BOCD`, `Regularized Markov-Gap` và phân phối đều $0.10$. Cách thiết kế này bảo toàn toán học $\sum_{i=0}^9 P_{\text{AI}}(i) = 1.0$ và tự động co rút về $0.10$ khi tín hiệu quá khứ nhiễu.
- **AD-05 — Đánh giá Kép Đa Khung Thời Gian (`Dual-Horizon 5Y & 3Y`) và Khớp nối Kelly 19 Trạng thái:**
  - Từ một bộ dữ liệu chuẩn hóa 5 năm duy nhất của mỗi đài (`XSHCM`: 520 kỳ, `XSVL`: 260 kỳ), hệ thống cắt lát tự động thành khung `5Y` và khung `3Y` (`312` kỳ gần nhất cho `XSHCM`, `156` kỳ gần nhất cho `XSVL`) với cùng `warmup = 45` kỳ để đối chiếu trực tiếp độ bền dài hạn so với thế hệ máy quay hiện hành.

---

## Dependency Graph

```text
[Task 1: pyproject.toml + constants.py + exceptions.py]
    │
    └──► [Task 2: schemas.py + DataSchemaGate]
             │
             ├──► [Task 3: ingest/canonicalizer.py (5Y/3Y Slicing)]
             │        │
             │        ├──► [Task 4: ingest/fetcher.py (Async Multi-Source + Cache)]
             │        │
             │        ├──► [Task 5: features/extractor.py + PreDrawCutoffGate]
             │        │        │
             │        │        └──► [Task 8: engine/bocd_dirichlet.py + markov_gap_model.py]
             │        │                 │
             │        │                 └──► [Task 9: engine/calibration_pooler.py + SimplexCalibrationGate]
             │        │                          │
             │        └──► [Task 6: falsification/stats_tests.py]
             │                 │                 │
             │                 └──► [Task 7: falsification/monte_carlo.py + gatekeeper.py]
             │                                   │
             └───────────────────────────────────┼──► [Task 10: backtest/alpha_decay.py + sweet_spot_sim.py]
                                                 │        │
                                                 └────────┴──► [Task 11: backtest/runner.py + html_report.py + cli.py]
                                                                   │
                                                                   └──► [Task 12: Adversarial Mutation Suite + Full 5Y/3Y E2E Run]
```

---

## Task List

### Phase 1: Foundation & Contracts (Nền tảng, Hằng số GĐ 1 & Hợp đồng Dữ liệu)
- [x] **Task 1:** Khởi tạo dự án `uv` kèm hệ hằng số tài chính Giai đoạn 1 (`pyproject.toml`, `constants.py`, `exceptions.py`)
- [x] **Task 2:** Thiết lập hợp đồng dữ liệu Pydantic v2 kèm cổng `DataSchemaGate` (`schemas.py`, `test_constants_and_schemas.py`)
- [x] **Task 3:** Xây dựng bộ chuẩn hóa lồng cầu `canonicalizer.py` hỗ trợ cắt lát khung `5Y`/`3Y` (`ingest/canonicalizer.py`)

### Checkpoint 1: Foundation & Schema Gate (Sau Tasks 1–3)
- [x] Môi trường `uv sync --all-extras` cài đặt sạch, `pytest` và `ruff` hoạt động trơn tru
- [x] Toàn bộ hằng số Giai đoạn 1 (`87.5`, `4.861111`, ngưỡng hòa vốn `+6.9045%/lồng`) và `DataSchemaGate` vượt qua 100% unit tests & negative tests
- [x] Hàm chuẩn hóa phân rã đúng 18 giải thành vector đếm 10 chiều ($\sum n_{t,i} = 18$) và cắt lát chính xác khung `5Y` / `3Y`

### Phase 2: Automated Ingestion, Pre-Draw Features & Statistical Tests (Thu thập, Đặc trưng & Kiểm định)
- [x] **Task 4:** Xây dựng bộ thu thập dữ liệu tự động đa nguồn `fetcher.py` cho `XSHCM`/`XSVL` (`ingest/fetcher.py`)
- [x] **Task 5:** Xây dựng bộ trích xuất 3 nhóm đặc trưng `extractor.py` khóa `PreDrawCutoffGate` (`features/extractor.py`)
- [x] **Task 6:** Xây dựng bộ 4 phép kiểm định thống kê đa cửa sổ `stats_tests.py` (`falsification/stats_tests.py`)

### Checkpoint 2: Ingestion, Features & Statistical Tests (Sau Tasks 4–6)
- [x] Bộ tải dữ liệu bóc tách chuẩn 18 giải/kỳ, hỗ trợ failover đa nguồn và lưu cache kèm `SHA-256`
- [x] `PreDrawCutoffGate` chặn đứng mọi hành vi truyền dữ liệu kỳ $\ge t$ vào bộ trích xuất đặc trưng kỳ $t$ (`TemporalLeakageError`)
- [x] Bộ 4 kiểm định ($\chi^2$, $BF_{10}$, $H_{\text{norm}}$, Runs/Markov test) tính toán chính xác trong không gian logarit trên 3 cửa sổ $W \in \{15, 30, 60\}$

### Phase 3: Monte Carlo Gatekeeper & Calibrated Probability Engine (Phễu Chống Nhiễu & Hội Đồng Dự Báo)
- [x] **Task 7:** Xây dựng bộ đối chứng 1,000 chuỗi Monte Carlo kèm phễu `gatekeeper.py` (`falsification/monte_carlo.py`, `falsification/gatekeeper.py`)
- [x] **Task 8:** Xây dựng hai nhánh dự báo xác suất `bocd_dirichlet.py` cùng `markov_gap_model.py` (`engine/bocd_dirichlet.py`, `engine/markov_gap_model.py`)
- [x] **Task 9:** Xây dựng bộ hợp nhất lồi `calibration_pooler.py` khóa `SimplexCalibrationGate` (`engine/calibration_pooler.py`)

### Checkpoint 3: Gatekeeper & Calibrated Engine (Sau Tasks 7–9)
- [x] Chuỗi nhiễu trắng ngẫu nhiên ($p=10\%$) bị Phễu Gatekeeper khóa chặt ở trạng thái `FAIL_WHITE_NOISE_CASH_BRAKE` (`multiplier = 0.0`), trong khi chuỗi có độ lệch thật $+9.0\%$ vượt ngưỡng `PASS_ALPHA`
- [x] Thuật toán `Bayesian Dirichlet-BOCD` phát hiện điểm thay bóng mới và co rút xác suất bóng cũ về nền $10.0\%$ trong vòng $\le 4$ kỳ
- [x] Bộ hợp nhất `SLSQP` xuất bảng xác suất $P_{\text{AI}}(0\dots9)$ bảo toàn tuyệt đối $\sum_{i=0}^9 P_{\text{AI}}(i) = 1.0 \pm 10^{-6}$ và đạt Brier Score ngoài mẫu tốt hơn hoặc bằng tần suất trượt ngây thơ

### Phase 4: Walk-Forward Sweet-Spot Backtester, CLI & Full 5Y/3Y Verification (Kiểm thử Trượt & Nghiệm thu)
- [x] **Task 10:** Xây dựng bộ đo suy giảm Alpha kèm bộ mô phỏng Điểm Ngọt 19 trạng thái (`backtest/alpha_decay.py`, `backtest/sweet_spot_sim.py`)
- [x] **Task 11:** Xây dựng bộ điều phối Walk-Forward `runner.py` kèm báo cáo HTML/CLI (`backtest/runner.py`, `reporting/html_report.py`, `cli.py`)
- [x] **Task 12:** Kiểm thử đột biến đối kháng kèm thực thi pipeline thực nghiệm 5 năm (`tests/test_adversarial_mutations.py`, `data/`, `reports/`)
- [x] **Task 13:** Nâng cấp Cửa sổ Quá khứ Thích ứng Nhân quả (`Causal Past-Window Optimizer` $W^*_{t-1}$) & Loại bỏ ngưỡng tự chế `noise_floor` (`constants.py`, `engine/bocd_dirichlet.py`, `engine/calibration_pooler.py`, `tests/`)
- [x] **Task 14:** Nâng cấp Quy luật Trừ Khấu Hao Kỳ Liền Trước (`Lag-1 Burst Exhaustion Filter`) trên tập cửa sổ hội tụ $\mathcal{W} = \{15, 20, 25, 30, 40, 50, 60\}$ & Xóa bỏ nghịch lý `Rank 1 < Rank 2` (`constants.py`, `engine/bocd_dirichlet.py`, `engine/markov_gap_model.py`, `tests/`)

### Checkpoint 4: Complete End-to-End Verification & Stage 3 Handoff (Sau Tasks 10–12)
- [x] Thu thập đủ 5 năm lịch sử chuẩn hóa tại `data/canonical/XSHCM_canonical.json` (~520 kỳ) và `data/canonical/XSVL_canonical.json` (~260 kỳ)
- [x] Xuất thành công `data/outputs/stage3_handoff_XSHCM.json`, `data/outputs/stage3_handoff_XSVL.json`, `reports/stage2_dual_station_comparison.json` và báo cáo HTML trực quan cho cả 2 khung `5Y` và `3Y`
- [x] Toàn bộ kiểm thử tự động `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-fail-under=90` và `uv run ruff check src/ tests/` đạt `100% PASS`
- [x] Sẵn sàng bàn giao sang Giai đoạn 3 (Quản lý vốn Quỹ & Kelly Criterion)

---

## Parallelization Opportunities

- **Phải thực hiện tuần tự (`Sequential Foundation & Integration`):**
  - `Task 1` $\rightarrow$ `Task 2` $\rightarrow$ `Task 3` (Khởi tạo hằng số, hợp đồng dữ liệu Pydantic và bộ chuẩn hóa lồng cầu).
  - `Task 11` $\rightarrow$ `Task 12` (Tích hợp toàn tuyến Walk-Forward CLI và chạy thực nghiệm dữ liệu thật 5 năm).
- **Có thể thực hiện song song sau khi xong `Task 3` (`Parallel Feature Slices`):**
  - **Luồng A (Thu thập dữ liệu):** `Task 4` (`ingest/fetcher.py`).
  - **Luồng B (Đặc trưng & Mô hình AI):** `Task 5` (`features/extractor.py`) $\rightarrow$ `Task 8` (`bocd_dirichlet.py` + `markov_gap_model.py`) $\rightarrow$ `Task 9` (`calibration_pooler.py`).
  - **Luồng C (Kiểm định & Monte Carlo Null):** `Task 6` (`falsification/stats_tests.py`) $\rightarrow$ `Task 7` (`monte_carlo.py` + `gatekeeper.py`).
  - **Luồng D (Đo lường Điểm Ngọt độc lập):** `Task 10` (`alpha_decay.py` + `sweet_spot_sim.py` chỉ phụ thuộc vào `constants.py` và `schemas.py`).

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
| :--- | :---: | :--- |
| **R1: Nguồn web XSMN thay đổi cấu trúc HTML hoặc thiếu kỳ quay lịch sử lẻ** | High | Thiết kế `fetcher.py` với 1 nguồn chính tải theo lô (`minhngoc.net.vn`, 6–7 kỳ/trang) + 2 nguồn dự phòng độc lập (`xskt.com.vn`, `xoso.com.vn`) tự động failover theo từng ngày quay bị thiếu, kèm cache cục bộ `SHA-256`. |
| **R2: Rò rỉ dữ liệu tương lai (`Look-Ahead / Intra-Draw Leakage`) trong quá trình Walk-Forward** | High | Cài đặt chốt chặn cứng `PreDrawCutoffGate` ngay trong `extract_features(history, target_draw)` kiểm tra bất biến `history[-1].draw_index < target_draw.draw_index` và `history[-1].draw_date < target_draw.draw_date`, kèm kiểm thử đột biến âm bắt buộc. |
| **R3: Ảo ảnh phương sai mẫu nhỏ (`Small-Sample Variance Illusion`) khiến mô hình báo lãi giả trên nhiễu trắng** | High | Bắt buộc đối chiếu mọi thống kê trên 3 cửa sổ $W \in \{15, 30, 60\}$ với dải phân vị 90%/95% của 1,000 chuỗi Monte Carlo Null (`PCG64(seed=42)`) và dùng `Dirichlet-BOCD` ($\alpha_0 = 18.0$) để co rút xác suất về $10.0\%$ khi cỡ mẫu nhỏ. |
| **R4: Tràn số dưới (`Numerical Underflow`) khi tính Bayes Factor $BF_{10}$ và lưới BOCD qua 1,080 lần nhả bóng** | Medium | Thực hiện 100% phép tính đa thức và cập nhật hậu nghiệm trong miền Logarit bằng `scipy.special.gammaln` và `scipy.special.logsumexp`. |
| **R5: Lỗi mã hóa ký tự tiếng Việt `UnicodeEncodeError (cp1252)` trên Windows PowerShell** | Low | Bắt buộc gọi `sys.stdout.reconfigure(encoding="utf-8")` ở điểm vào CLI và chỉ định rõ `encoding="utf-8"` trên mọi thao tác đọc/ghi tệp JSON/HTML. |

---

## Open Questions

Tất cả các câu hỏi thiết kế và phạm vi dữ liệu đã được Chủ dự án giải quyết và khóa hoàn toàn tại [`spec.md` (Mục 0 & Mục 10)](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/spec.md#L14-L26):
- **Đài mục tiêu:** Đối chiếu trực tiếp 2 đài đại diện: **Đài TP.HCM (`XSHCM` — 2 kỳ/tuần)** và **Đài Vĩnh Long (`XSVL` — 1 kỳ/tuần)**.
- **Khung thời gian lịch sử:** Thu thập 5 năm gần nhất và đánh giá song song trên cả **Khung 5 năm (`5Y`)** lẫn **Khung 3 năm gần nhất (`3Y`)**.
