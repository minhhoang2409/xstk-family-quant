# Spec: Giai Đoạn 2 — Hệ Thống Phát Hiện Alpha & Dự Báo Xác Suất Hiệu Chuẩn 1 Lồng Cầu XSMN (`stage2-alpha-discovery`)

**Mã Module:** `stage2-alpha-discovery`  
**Trạng thái:** Approved — Đã chốt toàn bộ thông số kỹ thuật (Pha 1C: SPECIFY)  
**Ngày cập nhật:** 2026-10-25  
**Tài liệu tham chiếu gốc (Upstream Single Source of Truth):**
- Bản Ý Định Gốc (Pha 1A): [`specs/stage2-alpha-discovery/intent.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/intent.md)
- Phương Án Kiến Trúc Đã Chốt (Pha 1B — Phương án C): [`specs/stage2-alpha-discovery/ideas.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/ideas.md)
- Quy Tắc Dòng Tiền & Điểm Hòa Vốn (Giai đoạn 1): [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md)
- Báo Cáo Trực Quan & Mô Phỏng Giai Đoạn 2: [`BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html`](file:///C:/sidehustle/XSTK/BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html)

---

## 0. Các Quyết Định & Giả Định Kỹ Thuật Đã Khóa (`Locked Decisions & Assumptions`)

1. **Môi trường thực thi chuẩn (`uv` + Python 3.11):** Máy trạm sử dụng `uv 0.13.1` và `cpython-3.11.17` (`C:\Users\Admin\.local\bin\uv.exe`). Toàn bộ quy trình đóng gói, chạy kiểm định và kiểm thử thực thi qua `uv run ...` để đảm bảo tính tái lập 100%.
2. **Hai Đài Mục Tiêu Chuẩn (`Dual-Station Scope: XSHCM & XSVL`):**
   - **Đài Thành Phố (Tần suất cao — 2 kỳ/tuần vào Thứ Hai & Thứ Bảy):** **Đài TP. Hồ Chí Minh (`XSHCM`)** — đại diện cho đài quay mật độ dày (~104 kỳ/năm = 1,872 giải/năm).
   - **Đài Tỉnh Đối Chứng (Tần suất chuẩn — 1 kỳ/tuần vào Thứ Sáu):** **Đài Vĩnh Long (`XSVL`)** — đại diện chuẩn cho nhóm đài tỉnh miền Nam (~52 kỳ/năm = 936 giải/năm).
3. **Đánh Giá Kép Trên 2 Khung Thời Gian Lịch Sử (`Dual-Horizon Evaluation: 5-Year & 3-Year`):**
   - Thu thập trọn vẹn **5 năm lịch sử gần nhất** cho cả 2 đài và chạy đánh giá song song trên **2 khung cửa sổ lịch sử**:
     - **Khung 5 Năm (`5Y Horizon`):** `XSHCM` (~520 kỳ = 9,360 giải) và `XSVL` (~260 kỳ = 4,680 giải) — kiểm tra độ bền thống kê dài hạn qua nhiều chu kỳ bảo dưỡng máy.
     - **Khung 3 Năm Gần Nhất (`3Y Horizon`):** `XSHCM` (~312 kỳ = 5,616 giải) và `XSVL` (~156 kỳ = 2,808 giải) — phản ánh sát nhất thế hệ máy quay và bộ bóng hiện hành.
4. **Cơ chế Giả lập 1,000 Chuỗi Ngẫu nhiên (`Monte Carlo Null Benchmark`) có Hạt giống Cố định (`Deterministic Seed = 42`):** Quá trình sinh 1,000 lịch sử quay ngẫu nhiên chuẩn $p = 10.0\%$ (cho từng quy mô mẫu tương ứng của `XSHCM` và `XSVL` ở cả khung `5Y` và `3Y`) sử dụng `numpy.random.Generator(PCG64(seed=42))` để tái lập chính xác 100%.
5. **Chuẩn đầu ra bàn giao sang Giai đoạn 3 (`Stage 3 Handoff Contract`):** Xuất các file JSON bàn giao chuẩn hóa (`stage3_handoff_XSHCM.json`, `stage3_handoff_XSVL.json`) chứa bảng xác suất hiệu chuẩn 10 bóng $P_{\text{AI}}(0\dots9)$, chỉ số `conviction_score` và phân phối xác suất rời rạc 19 trạng thái trúng $P_{\text{AI}}(K = 0\dots18)$ để nạp thẳng vào công thức **Tiêu chuẩn Kelly Đa Kết Quả (`Generalized Multi-Outcome Kelly Criterion`)** tại Mục 8.2 của [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md#L247-L250).

---

## 1. Objective (Mục Tiêu & Phạm Vi)

### 1.1. Mục tiêu cốt lõi
Xây dựng hệ thống định lượng hoàn chỉnh thực thi **Phương án C: Kiến Trúc Lai Hai Tầng "Phễu Kiểm Định Chống Nhiễu + Hội Đồng Co Rút Thích Ứng" (`Two-Stage Gatekeeper & Regularized Ensemble`)** cho bài toán chọn bóng trên **1 Lồng Cầu (`0`–`9`)**, áp dụng đồng nhất và độc lập cho **Lồng Hàng Chục (`tens_cage`)** và **Lồng Hàng Đơn Vị (`units_cage`)** trên **Đài TP. Hồ Chí Minh (`XSHCM`)** và **Đài Vĩnh Long (`XSVL`)** qua cả 2 khung thời gian **5 năm (`5Y`)** và **3 năm gần nhất (`3Y`)**.

### 1.2. Bốn trụ cột chức năng bắt buộc
1. **Trụ cột 1 — Tổ chức Dữ liệu Chuẩn hóa & Bộ Đặc trưng Tinh gọn (`Compact Data Schema & Feature Engineering`):**
   - Thu thập, làm sạch và chuẩn hóa lịch sử mở thưởng 18 giải/kỳ của `XSHCM` (520 kỳ) và `XSVL` (260 kỳ) thành chuỗi vector đếm đa thức 10 chiều $\mathbf{c}_t = [n_{t,0}, \dots, n_{t,9}]$ ($\sum_{i=0}^9 n_{t,i} = 18$) cho từng lồng cầu.
   - Trích xuất 3 nhóm đặc trưng vật lý – thống kê tại thời điểm khóa sổ $t-1$ (`Pre-Draw Temporal Cutoff`):
     1. Chuỗi tần suất đa thức theo độ dài trạng thái (`Regime Count Vectors`).
     2. Động học nhịp rơi, chu kỳ vắng mặt chuẩn hóa (`Standardized Gap Z-Score`) & tốc độ rơi lại sau kỳ nổ đột biến ($\ge 3$ nháy/kỳ).
     3. Ma trận chuyển trạng thái Markov bậc 1 làm mượt Laplace (`Smoothed First-Order Markov Transitions`) và tỷ trọng xuất hiện giải đầu/cuối buổi.
2. **Trụ cột 2 — Phễu Kiểm Định Bác Bỏ Nhiễu & Đối Chứng 1,000 Chuỗi Giả Lập (`Statistical Falsification Gatekeeper`):**
   - Chạy bộ 4 kiểm định thống kê đa cửa sổ $W \in \{15, 30, 60\}$ kỳ:
     1. Kiểm định $\chi^2$ đa thức (`Multinomial Chi-Square Goodness-of-Fit`).
     2. Tỷ số Hệ số Bayes (`Dirichlet-Multinomial Bayes Factor` $BF_{10}$).
     3. Shannon Entropy chuẩn hóa ($H_{\text{norm}} \in [0, 1]$).
     4. Kiểm định tính độc lập chuỗi (`Wald-Wolfowitz Runs Test` & `Markov Transition Chi-Square`).
   - Đối chiếu trực tiếp với dải phân vị **90% và 95%** của **1,000 chuỗi lịch sử ngẫu nhiên giả lập (`Monte Carlo Null Histories`)** tương ứng với từng khung độ dài (`5Y` và `3Y`). Tự động kích hoạt phanh tiền mặt **`[FAIL_WHITE_NOISE_CASH_BRAKE]`** nếu dữ liệu nằm trong vùng nhiễu trắng ($p_{\text{MC}} > 0.05$ và $BF_{10} < 1.0$).
3. **Trụ cột 3 — Hội Đồng Dự Báo Xác Suất Hiệu Chuẩn 10 Quả Bóng (`Dual-Branch Calibrated Probability Engine`):**
   - **Nhánh 1 (`Bayesian Dirichlet-BOCD`):** Ước lượng độ lệch vật lý lồng cầu tích hợp qua phân phối hậu nghiệm độ dài trạng thái $P(r_t \mid \text{Data}_{1:t})$ với xác suất điểm gãy tiên nghiệm $H(r) = \frac{1}{\lambda_{\text{regime}}}$. Tự động phát hiện khi nhà đài thay bóng/bảo trì máy để co rút xác suất về mức an toàn $10.0\%$ sau $3 \to 4$ kỳ.
   - **Nhánh 2 (`Regularized Markov & Gap Multinomial Model`):** Ước lượng động học chuỗi có phạt chuẩn hóa $L_2$ mạnh trên Nhóm đặc trưng 2 & 3 để xuất phân phối $P_{\text{Seq}}(0\dots9)$.
   - **Bộ Hợp Nhất Hiệu Chuẩn Tối Ưu (`Out-of-Sample Brier / Log-Loss Pooling`):** Kết hợp lồi $P_{\text{AI}}(i) = w_1 P_{\text{BOCD}}(i) + w_2 P_{\text{Seq}}(i) + (1 - w_1 - w_2) \cdot 0.10$ bảo toàn tuyệt đối $\sum_{i=0}^9 P_{\text{AI}}(i) = 1.0$ ($100\%$).
4. **Trụ cột 4 — Kiểm Thử Trượt Điểm Ngọt & Đường Cong Suy Giảm Alpha (`Walk-Forward Sweet-Spot Portfolio Backtester`):**
   - Chạy kiểm thử cuốn chiếu từng kỳ (`Strict Step-by-Step Walk-Forward`) cho cả `XSHCM` và `XSVL` trên cả 2 khung `5Y` và `3Y`.
   - Đo **Đường cong suy giảm Alpha theo thứ hạng bóng (`Rank-Ordered Alpha Decay`: `Rank 1` $\to$ `Rank 10`)** ngoài mẫu.
   - Chấm điểm đối đầu trực tiếp giữa các cấu hình Điểm Ngọt trên chu kỳ trượt 30 kỳ (`540 giải`) và toàn bộ lịch sử:
     - **Bộ $2\times2 = 4$ số** (`4.0đ`/kỳ, Hòa vốn 30 kỳ `24.69 lô`, mục tiêu $\ge 25$ lô/30 kỳ).
     - **Bộ $3\times3 = 9$ số** (`9.0đ`/kỳ, Hòa vốn 30 kỳ `55.54 lô`, mục tiêu $\ge 56$ lô/30 kỳ).
     - **Danh mục Lai `Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ)`** (`6.5đ`/kỳ, Hòa vốn 30 kỳ quy đổi `40.11 lô` tương đương `195.0đ`).
     - **Cấu hình Điểm Ngọt mở rộng:** $1\times4 = 4$ số (`4.0đ`/kỳ), $2\times7 = 14$ số (`14.0đ`/kỳ, $K_{\min}=3$), $3\times6 = 18$ số (`18.0đ`/kỳ, $K_{\min}=4$).
     - **Chiến thuật Loại trừ bóng chết (`Negative Cold-Ball Filter`):** Đánh giá loại 1 bóng thấp nhất mỗi lồng ($9\times9 = 81$ số) và loại 13 số thấp nhất ($87$ số) trên bài toán **1 Giải Đuôi (Giải ĐB — trả thưởng `87.5đ`)**.

---

## 2. Tech Stack (Công Nghệ & Thư Viện Chuẩn)

- **Ngôn ngữ & Runtime:** Python `3.11.17` quản lý qua `uv 0.13.1` (`pyproject.toml` + `uv.lock`).
- **Thư viện Tính toán & Thống kê Cốt lõi (Giải tích minh bạch, không dùng Deep Learning):**
  - `numpy >= 1.26.0, < 2.2.0` — Tính toán ma trận, đại số tuyến tính, BOCD run-length trellis và sinh chuỗi Monte Carlo (`PCG64`).
  - `scipy >= 1.12.0` — Kiểm định thống kê ($\chi^2$, hàm `gammaln` cho Dirichlet-Multinomial Bayes Factor, tối ưu hóa lồi `scipy.optimize.minimize` với phương pháp `SLSQP` cho Brier/Log-Loss Pooling).
  - `pydantic >= 2.7.0` — Kiểm tra hợp đồng dữ liệu đầu vào/đầu ra nghiêm ngặt (`Fail-Closed Schema Validation`).
  - `httpx >= 0.27.0` — Thu thập dữ liệu lịch sử mở thưởng XSMN cho `XSHCM` và `XSVL` có kiểm soát timeout và retry.
- **Thư viện Kiểm thử & Chất lượng Mã nguồn (`dev-dependencies`):**
  - `pytest >= 8.2.0` — Khung kiểm thử đơn vị, kiểm thử bất biến toán học và kiểm thử đột biến âm (`Negative Mutation Tests`).
  - `pytest-cov >= 5.0.0` — Đo độ phủ mã nguồn (yêu cầu $\ge 90\%$ trên các module toán học cốt lõi).
  - `ruff >= 0.5.0` — Kiểm tra chuẩn cú pháp (Linting) và định dạng code (Formatting).

---

## 3. Commands (Các Câu Lệnh Thực Thi Chuẩn)

Tất cả câu lệnh được thực thi tại thư mục gốc `C:\sidehustle\XSTK` thông qua `uv`:

```powershell
# 1. Khởi tạo / Đồng bộ môi trường ảo và cài đặt dependencies
uv sync --all-extras

# 2. Thu thập & Chuẩn hóa dữ liệu lịch sử 5 năm cho cả 2 đài: TP.HCM (XSHCM ~ 520 kỳ) & Vĩnh Long (XSVL ~ 260 kỳ)
uv run python -m xsmn_alpha.cli ingest --stations XSHCM XSVL --years 5 --out-dir data/canonical/

# 3. Chạy Phễu Kiểm Định Thống Kê & Đối chứng 1,000 chuỗi Monte Carlo trên cả 2 khung 5Y & 3Y
uv run python -m xsmn_alpha.cli falsify --stations XSHCM XSVL --horizons 5y 3y --null-sims 1000 --seed 42

# 4. Chạy trọn vẹn Pipeline Giai đoạn 2 (XSHCM & XSVL | Khung 5Y & 3Y) + Xuất Báo cáo Đối chiếu & Handoff GĐ 3
uv run python -m xsmn_alpha.cli run-pipeline --stations XSHCM XSVL --horizons 5y 3y --warmup 45 --null-sims 1000 --seed 42 --out-dir reports/

# 5. Chạy toàn bộ bộ kiểm thử (Unit + Invariant + Adversarial Negative Tests) kèm đo Coverage
uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90

# 6. Kiểm tra chất lượng mã nguồn (Lint & Format check)
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

---

## 4. Project Structure (Cấu Trúc Thư Mục Dự Án)

```text
C:\sidehustle\XSTK\
├── QUY_TAC_VA_DIEM_HOA_VON.md               # [GĐ 1] Quy ước gốc dòng tiền & Điểm hòa vốn (Bất biến)
├── BANG_NGHIEN_CUU_CHIEN_THUAT_XSMN.html    # [GĐ 1] Dashboard Điểm hòa vốn & Chiến thuật
├── BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html    # [GĐ 2] Báo cáo trực quan kiến trúc Phương án C
├── specs/
│   └── stage2-alpha-discovery/
│       ├── intent.md                        # [Pha 1A] Bản đúc kết ý định đã xác nhận
│       ├── ideas.md                         # [Pha 1B] Kiến trúc Phương án C đã chốt
│       ├── spec.md                          # [Pha 1C] Hợp đồng đặc tả kỹ thuật (File này — Đã chốt)
│       ├── plan.md                          # [Pha 2] Kế hoạch triển khai kiến trúc (Sẽ tạo ở bước sau)
│       └── todo.md                          # [Pha 2] Danh sách tác vụ chi tiết (Sẽ tạo ở bước sau)
├── pyproject.toml                           # Cấu hình dự án Python & dependencies cho uv
├── src/
│   └── xsmn_alpha/
│       ├── __init__.py
│       ├── constants.py                     # Hằng số bất biến GĐ 1 (87.5, 4.861111, cấu hình XSHCM & XSVL, Điểm Ngọt)
│       ├── schemas.py                       # Pydantic v2 Schemas (CanonicalDraw, DualHorizonReport, Stage3Handoff)
│       ├── exceptions.py                    # Các ngoại lệ Fail-Closed (TemporalLeakageError, CalibrationIntegrityError...)
│       ├── ingest/                          # [Trụ cột 1A] Thu thập, làm sạch & chuẩn hóa dữ liệu 18 giải
│       │   ├── __init__.py
│       │   ├── fetcher.py                   # Tải và xác thực lịch sử 5 năm cho XSHCM (2 kỳ/tuần) & XSVL (1 kỳ/tuần)
│       │   └── canonicalizer.py             # Phân rã 2 số cuối -> vector đếm 10 chiều Lồng Chục & Lồng Đơn vị + cắt lát 5Y/3Y
│       ├── features/                        # [Trụ cột 1B] Trích xuất 3 nhóm đặc trưng với khóa Pre-Draw (t-1)
│       │   ├── __init__.py
│       │   └── extractor.py                 # Regime counts, Standardized Gap Z-score, Smoothed Markov transitions
│       ├── falsification/                   # [Trụ cột 2] Phễu kiểm định bác bỏ nhiễu & 1,000 Monte Carlo Null
│       │   ├── __init__.py
│       │   ├── stats_tests.py               # Chi-Square, Dirichlet Bayes Factor BF10, Normalized Entropy, Runs & Markov test
│       │   ├── monte_carlo.py               # Bộ sinh 1,000 chuỗi ngẫu nhiên giả lập & tính phân vị 90%/95% theo cỡ mẫu 5Y/3Y
│       │   └── gatekeeper.py                # Logic phán quyết PASS_ALPHA / WARN_WEAK_SIGNAL / FAIL_WHITE_NOISE_CASH_BRAKE
│       ├── engine/                          # [Trụ cột 3] Hội đồng dự báo xác suất hiệu chuẩn P_AI(0..9)
│       │   ├── __init__.py
│       │   ├── bocd_dirichlet.py            # Nhánh 1: Bayesian Online Changepoint Detection + Dirichlet Shrinkage
│       │   ├── markov_gap_model.py          # Nhánh 2: Regularized Markov & Gap Multinomial L2 Estimator
│       │   └── calibration_pooler.py        # Hợp nhất lồi tối ưu Out-of-Sample Brier / Log-Loss (∑ P_i = 1.0)
│       ├── backtest/                        # [Trụ cột 4] Kiểm thử trượt Điểm Ngọt & Đường cong suy giảm Alpha
│       │   ├── __init__.py
│       │   ├── alpha_decay.py               # Đo tần suất nổ thực tế ngoài mẫu theo Rank 1 -> Rank 10
│       │   ├── sweet_spot_sim.py            # Chấm điểm 2x2, 3x3, Core+Sat, 1x4, 2x7, 3x6, Negative Filter + DP 19-state
│       │   └── runner.py                    # Điều phối Walk-Forward cho XSHCM & XSVL trên cả 2 khung 5Y & 3Y
│       ├── reporting/                       # Xuất báo cáo JSON & Dashboard HTML đối chiếu XSHCM vs XSVL (5Y vs 3Y)
│       │   ├── __init__.py
│       │   └── html_report.py               # Sinh báo cáo HTML/JSON minh bạch từ dữ liệu thực
│       └── cli.py                           # Giao diện dòng lệnh hợp nhất (ingest, falsify, run-pipeline)
├── data/
│   ├── raw/                                 # Dữ liệu lịch sử gốc (XSHCM_draws.json, XSVL_draws.json) kèm SHA-256
│   ├── canonical/                           # Dữ liệu chuẩn hóa (XSHCM_canonical.json, XSVL_canonical.json)
│   └── outputs/                             # File JSON bàn giao GĐ 3 (stage3_handoff_XSHCM.json, stage3_handoff_XSVL.json)
├── reports/                                 # Báo cáo thực nghiệm Walk-Forward & Kiểm định (HTML/JSON)
└── tests/                                   # Bộ kiểm thử tự động (PASS + Adversarial Negative Mutation FAIL)
    ├── conftest.py
    ├── test_constants_and_schemas.py
    ├── test_pillar1_ingest_and_features.py
    ├── test_pillar2_falsification_gatekeeper.py
    ├── test_pillar3_calibrated_engine.py
    ├── test_pillar4_walk_forward_backtest.py
    └── test_adversarial_mutations.py
```

---

## 5. Hợp Đồng Dữ Liệu, Công Thức Toán Học & Cổng Kiểm Soát Đối Kháng (`Data Contracts, Math Spec & Adversarial Gates`)

### 5.1. Hệ Hằng Số Tài Chính & Cấu Hình Đài Mục Tiêu (Đồng bộ 1:1 với Giai đoạn 1)

| Hằng số (`constants.py`) | Công thức gốc | Giá trị số học | Ý nghĩa |
| :--- | :---: | :---: | :--- |
| `REAL_PAYOUT_1D` | $\frac{70}{0.8}$ | `87.5` | Số đồng thu về khi trúng 1 giải đơn lẻ (Đầu/Đuôi) trên `1.0đ` vốn thực |
| `PRIZES_PER_DRAW` | $18$ | `18` | Tổng số giải (lô) mở thưởng trong 1 kỳ của 1 đài XSMN |
| `BAO_LO_PAYOUT_PER_HIT` | $\frac{87.5}{18} = \frac{175}{36}$ | `4.861111111111111` | Số đồng thu về cho **mỗi 1 nháy (1 lô)** khi mua `1.0đ`/số Bao Lô 18 giải |
| `BE_PROB_2D_NUMBER` | $\frac{1}{87.5}$ | `0.011428571428571429` | Xác suất hòa vốn của 1 con số 2 chữ số trong mỗi giải ($\approx 1.1429\%$, Lift $+14.29\%$) |
| `BE_PROB_SINGLE_BALL` | $\frac{1}{10}\sqrt{\frac{100}{87.5}}$ | `0.10690449676496976` | Xác suất hòa vốn tối thiểu của 1 quả bóng trên mỗi lồng cầu ($\approx 10.6904\%$, Lift $+6.9045\%$) |
| `CANDIDATE_PAST_WINDOWS` | $\{15, 20, 25, 30, 40, 50, 60\}$ | `(15, ..., 60)` | Tập ứng viên cửa sổ quá khứ hội tụ ($\sigma_{\text{nhiễu}} \le 1.83\%$) cho bộ tối ưu hóa cửa sổ nhân quả $W^*_{t-1}$ độc lập trên từng lồng cầu |
| `LAG1_EXHAUSTION_PENALTY` | $\gamma_{\text{lag1}} = 0.35$ | `0.35` | Hệ số trừ khấu hao hụt hơi kỳ liền trước ($t-1$) ngăn bóng nổ ảo hôm qua chiếm ngôi `Rank 1` |
| `compute_theoretical_noise_std(W)` | $\sqrt{\frac{0.10 \times 0.90}{18 \times W}} = \frac{1}{\sqrt{200 \times W}}$ | Hàm của $W$ | Độ lệch chuẩn nhiễu lý thuyết của 1 quả bóng qua $W$ kỳ ($18W$ lần nhả bóng), suy trực tiếp từ bài toán |
| `STATION_CONFIG["XSHCM"]` | 2 kỳ/tuần (T2, T7) | `5Y: 520 kỳ` \| `3Y: 312 kỳ` | Đài TP.HCM: Khung 5 năm (`9,360` giải) và Khung 3 năm gần nhất (`5,616` giải) |
| `STATION_CONFIG["XSVL"]` | 1 kỳ/tuần (Thứ 6) | `5Y: 260 kỳ` \| `3Y: 156 kỳ` | Đài Vĩnh Long: Khung 5 năm (`4,680` giải) và Khung 3 năm gần nhất (`2,808` giải) |

### 5.2. Kiến Trúc Thu Thập Dữ Liệu Tự Động 100% & Hợp Đồng Dữ Liệu Đầu Vào (`Automated Multi-Source Ingestion & Canonical Schema` — Trụ cột 1)

#### 5.2.1. Cơ Chế Thu Thập Tự Động Đa Nguồn (`Zero Manual Effort — Batch Crawler + Fallback Verifiers`)
Chủ dự án **không phải thu thập hay nhập tay bất kỳ dữ liệu nào**. Module `src/xsmn_alpha/ingest/fetcher.py` tự động hóa 100% việc tải, làm sạch, đối chiếu và lưu cache 5 năm lịch sử cho `XSHCM` (~520 kỳ) và `XSVL` (~260 kỳ) qua kiến trúc 3 lớp:

1. **Nguồn Chính Tải Theo Lô (`Primary Multi-Draw Batch Provider` — `minhngoc.net.vn`):**
   - **Endpoint mẫu:** `https://www.minhngoc.net.vn/ket-qua-xo-so/mien-nam/{slug}/{DD-MM-YYYY}.html`
     - Đài TP.HCM (`XSHCM`): `slug = "tp-hcm"` (mỗi trang trả về **6 kỳ mở thưởng liên tiếp** tính lùi từ ngày `{DD-MM-YYYY}`).
     - Đài Vĩnh Long (`XSVL`): `slug = "vinh-long"` (mỗi trang trả về **7 kỳ mở thưởng liên tiếp** tính lùi từ ngày `{DD-MM-YYYY}`).
   - **Quy tắc bóc tách DOM chuẩn (`bkqtinhmiennam`):**
     - Trên mỗi bảng `<table class="bkqtinhmiennam">`, trích xuất ngày quay `DD/MM/YYYY` (chuẩn hóa về `YYYY-MM-DD`) và bóc tách chính xác 9 class giải thưởng theo thứ tự mở thưởng: `giai8` (1 số), `giai7` (1 số), `giai6` (3 số), `giai5` (1 số), `giai4` (7 số), `giai3` (2 số), `giai2` (1 số), `giai1` (1 số), `giaidb` (1 số) $\rightarrow$ **Tổng cộng đúng 18 giải/kỳ**, lấy 2 chữ số cuối (`str[-2:]`) của mỗi giải.
   - **Tốc độ & Tải bất đồng bộ có kiểm soát (`Polite Async Batching`):**
     - Nhờ mỗi trang chứa sẵn 6–7 kỳ mở thưởng, để lấy đủ 5 năm lịch sử chỉ cần tải **~87 trang cho `XSHCM`** (bước nhảy lùi 21 ngày/trang) và **~38 trang cho `XSVL`** (bước nhảy lùi 49 ngày/trang).
     - Sử dụng `httpx.AsyncClient` với `max_concurrency = 6`, `timeout = 10.0s`, `retry = 3` (exponential backoff) giúp hoàn tất thu thập toàn bộ 5 năm của cả 2 đài chỉ trong **~15–25 giây**.
2. **Nguồn Dự Phòng & Đối Chiếu Chéo Tự Động (`Automatic Fallback Providers` — `xskt.com.vn` & `xoso.com.vn`):**
   - **Fallback 1 (`xskt.com.vn`):** `https://xskt.com.vn/{xskt_slug}/ngay-{DD-MM-YYYY}` (`xshcm-xstp` cho TP.HCM, `xsvl` cho Vĩnh Long).
   - **Fallback 2 (`xoso.com.vn`):** `https://xoso.com.vn/{xoso_slug}-{DD-MM-YYYY}.html` (`xshcm` cho TP.HCM, `xsvl` cho Vĩnh Long).
   - **Cơ chế Failover:** Nếu bất kỳ kỳ quay nào từ Nguồn Chính bị thiếu hoặc không vượt qua kiểm tra `DataSchemaGate` (ví dụ: trang web đang cập nhật dở hoặc thiếu giải), `fetcher.py` tự động gọi sang Fallback 1 và Fallback 2 của đúng ngày `DD-MM-YYYY` đó để lấy đủ 18 giải và xác thực chéo.
3. **Cơ Chế Lưu Cache Cục Bộ & Đồng Bộ Tăng Trưởng (`Incremental Local Cache & Offline-First`):**
   - Toàn bộ dữ liệu thô đã xác thực được lưu xuống `data/raw/XSHCM_draws.json` và `data/raw/XSVL_draws.json` kèm mã kiểm tra toàn vẹn `SHA-256`.
   - Trong các lần chạy tiếp theo, hệ thống đọc trực tiếp từ cache cục bộ (`0 giây` chờ mạng) và chỉ tải bổ sung các kỳ quay mới phát sinh kể từ `last_draw_date` (`Incremental Delta Sync`).
   - Toàn bộ CLI và bộ nạp dữ liệu bắt buộc gọi `sys.stdout.reconfigure(encoding="utf-8")` và mở file với `encoding="utf-8"` để ngăn chặn triệt để lỗi `UnicodeEncodeError (cp1252)` trên Windows PowerShell.

#### 5.2.2. Cấu Trúc Bản Ghi Chuẩn Hóa (`CanonicalDrawRecord`)

Mỗi kỳ mở thưởng $t \in \{0, 1, \dots, T-1\}$ của từng đài (`XSHCM` hoặc `XSVL`, sắp xếp theo `draw_date` tăng dần nghiêm ngặt) được định nghĩa bởi Pydantic model `CanonicalDrawRecord`:

```json
{
  "station_code": "XSHCM",
  "draw_date": "2026-10-24",
  "draw_index": 519,
  "prizes_last2": [
    "42", "18", "73", "08", "83", "39", "88", "14", "57",
    "81", "23", "90", "38", "84", "61", "03", "78", "83"
  ],
  "tens_counts": [2, 2, 1, 2, 1, 1, 1, 2, 5, 1],
  "units_counts": [1, 2, 1, 4, 2, 0, 0, 1, 5, 2]
}
```

- **Quy ước thứ tự 18 giải trong `prizes_last2`:** Lưu đúng 2 chữ số cuối (`00`–`99`) theo thứ tự quay thưởng thực tế trong buổi mở thưởng XSMN:
  - Index `0`: Giải Tám (Giải Đầu — 1 giải).
  - Index `1`: Giải Bảy (1 giải).
  - Index `2..4`: Giải Sáu (3 giải).
  - Index `5`: Giải Năm (1 giải).
  - Index `6..12`: Giải Tư (7 giải).
  - Index `13..14`: Giải Ba (2 giải).
  - Index `15`: Giải Nhì (1 giải).
  - Index `16`: Giải Nhất (1 giải).
  - Index `17`: Giải Đặc Biệt (Giải Đuôi — 1 giải).
- **Vector đếm đa thức 10 chiều (`tens_counts`, `units_counts`):**
  - Với mỗi giải $g \in \{0\dots17\}$, ký tự đầu là $d_{t,g}^{\text{tens}} \in \{0\dots9\}$ và ký tự thứ hai là $d_{t,g}^{\text{units}} \in \{0\dots9\}$.
  - $n_{t,i}^{\text{cage}} = \sum_{g=0}^{17} \mathbb{I}(d_{t,g}^{\text{cage}} = i)$ với ràng buộc bất biến:
    $$\forall t, \quad \sum_{i=0}^{9} n_{t,i}^{\text{tens}} = 18 \quad \text{và} \quad \sum_{i=0}^{9} n_{t,i}^{\text{units}} = 18$$
- **Quy tắc cắt lát Khung `5Y` và Khung `3Y` (`Horizon Slicing`):**
  - Khung `5Y`: Toàn bộ chuỗi chuẩn hóa $T_{5Y}$ kỳ của đài (`520` kỳ cho `XSHCM`, `260` kỳ cho `XSVL`).
  - Khung `3Y`: Lát cắt $T_{3Y}$ kỳ gần nhất (`draws[-312:]` cho `XSHCM`, `draws[-156:]` cho `XSVL`), đánh lại chỉ số `draw_index` từ `0` đến $T_{3Y}-1$ để chạy độc lập và đối chiếu trực tiếp với khung `5Y`.

### 5.3. Công Thức Toán Học Chi Tiết Cho 4 Trụ Cột

#### A. Trụ cột 1 — Bộ 3 Nhóm Đặc Trưng Tại Thời Điểm $t-1$ (`Pre-Draw Feature Vector`)
Để dự báo cho kỳ mục tiêu $t$, bộ trích xuất đặc trưng chỉ được nhận lát cắt lịch sử $\mathcal{H}_{0:t-1} = \{\mathbf{c}_0, \mathbf{c}_1, \dots, \mathbf{c}_{t-1}\}$:
1. **Nhóm 1 (`Regime Count Vectors`):** Tích lũy số lần nổ của từng bóng $i \in \{0\dots9\}$ trên các độ dài cửa sổ $w \in \{5, 10, 15, 30, 60\}$ kỳ tính lùi từ $t-1$:
   $$N_{t-1, i}^{(w)} = \sum_{\tau = \max(0, t-w)}^{t-1} n_{\tau, i}, \quad \hat{f}_{t-1, i}^{(w)} = \frac{N_{t-1, i}^{(w)}}{18 \cdot \min(t, w)}$$
2. **Nhóm 2 (`Recency, Standardized Gap Z-Score & Multi-Hit Rebound`):**
   - **Chu kỳ vắng mặt tuyệt đối (`Zero-Hit Gap` $G_{t-1, i}^{(0)}$):** Số kỳ liên tiếp tính lùi từ $t-1$ mà bóng $i$ không xuất hiện lần nào ($n_{\tau, i} = 0$). Với $q_0 = (0.9)^{18} \approx 0.1500946$, $\mu_G = \frac{q_0}{1 - q_0} \approx 0.1766$, $\sigma_G = \frac{\sqrt{q_0}}{1 - q_0} \approx 0.4560$:
     $$Z_{t-1, i}^{\text{gap}} = \frac{G_{t-1, i}^{(0)} - \mu_G}{\sigma_G}$$
   - **Áp lực thiếu hụt ngắn hạn (`Deficit Z-Score` trên 10 kỳ):**
     $$Z_{t-1, i}^{\text{def10}} = \frac{18.0 - N_{t-1, i}^{(10)}}{\sqrt{180 \times 0.10 \times 0.90}}$$
   - **Tốc độ rơi lại sau kỳ nổ đột biến (`Burst Rebound Indicator`):** Tần suất bóng $i$ nổ ở kỳ kế tiếp sau khi vừa nổ $\ge 3$ nháy ở kỳ $t-1$ ($\mathbb{I}(n_{t-1, i} \ge 3)$).
3. **Nhóm 3 (`Smoothed First-Order Markov Transitions & Session Split`):**
   - Trạng thái kích hoạt của bóng $i$ tại kỳ $\tau$: $S_{\tau, i} = \mathbb{I}(n_{\tau, i} \ge 2)$.
   - Ma trận chuyển trạng thái Markov bậc 1 làm mượt Laplace ($\alpha_{\text{lap}} = 1.0$) từ tập bóng kích hoạt kỳ $\tau-1$ sang bóng $j$ ở kỳ $\tau$:
     $$M_{i \to j}(t-1) = \frac{1.0 + \sum_{\tau=1}^{t-1} S_{\tau-1, i} \cdot n_{\tau, j}}{10.0 + 18 \cdot \sum_{\tau=1}^{t-1} S_{\tau-1, i}}$$
   - Tỷ trọng xuất hiện nhóm giải đầu buổi (9 giải đầu: index `0..8`) so với nửa cuối buổi (9 giải cuối: index `9..17`) ở kỳ $t-1$.

#### B. Trụ cột 2 — Phễu Kiểm Định Bác Bỏ Nhiễu & 1,000 Chuỗi Monte Carlo (`Falsification Gatekeeper`)
Trên mỗi cửa sổ $W \in \{15, 30, 60\}$ kỳ gần nhất (với tổng số lần nhả bóng $M_W = 18 \times W$ và số lần xuất hiện quan sát $O_i = \sum_{\tau=t-W}^{t-1} n_{\tau, i}$):
1. **Kiểm định $\chi^2$ Đa thức (`Multinomial Chi-Square`):**
   $$\chi^2_W = \sum_{i=0}^{9} \frac{(O_i - E_W)^2}{E_W}, \quad E_W = 0.10 \times M_W, \quad p_{\chi^2} = 1 - F_{\chi^2_9}(\chi^2_W)$$
2. **Tỷ số Hệ số Bayes (`Dirichlet-Multinomial Bayes Factor` $BF_{10}$):**
   So sánh giả thuyết $H_1$ (vector xác suất $\mathbf{p} \sim \text{Dirichlet}(\alpha_0, \dots, \alpha_0)$ với $\alpha_0 = 18.0$) và giả thuyết $H_0$ ($p_i \equiv 0.10$ cố định):
   $$\ln P(D \mid H_1) = \ln \Gamma(10\alpha_0) - \ln \Gamma(10\alpha_0 + M_W) + \sum_{i=0}^{9} \left[\ln \Gamma(\alpha_0 + O_i) - \ln \Gamma(\alpha_0)\right]$$
   $$\ln P(D \mid H_0) = M_W \ln(0.10) \quad \Longrightarrow \quad BF_{10}^{(W)} = \exp\left(\ln P(D \mid H_1) - \ln P(D \mid H_0)\right)$$
3. **Shannon Entropy Chuẩn hóa ($H_{\text{norm}}$):**
   $$\hat{p}_i = \frac{O_i}{M_W}, \quad H_{\text{norm}}^{(W)} = -\frac{1}{\ln 10} \sum_{i: \hat{p}_i > 0} \hat{p}_i \ln \hat{p}_i \in [0, 1]$$
4. **Kiểm định Độc lập Chuỗi (`Wald-Wolfowitz Runs Test` & `Markov Transition Chi-Square`):**
   - Kiểm định số đoạn chạy (`Runs`) trên chuỗi nhị phân $S_{\tau, i} = \mathbb{I}(n_{\tau, i} \ge 2)$ và thống kê $\chi^2_{\text{Markov}}$ trên bảng tần suất chuyển tiếp $10 \times 10$.
5. **Đối chứng 1,000 Chuỗi Ngẫu nhiên Giả lập (`Monte Carlo Null Benchmark`):**
   - Sinh $B = 1,000$ lịch sử giả lập $\tilde{\mathcal{H}}^{(b)}$ ($b = 1 \dots 1000$) có cùng số kỳ $T$ với từng khung (`5Y` và `3Y`) của từng đài (`XSHCM` và `XSVL`).
   - Tính thống kê $\tilde{\chi}^2_{\max, b} = \max_{W \in \{15,30,60\}} \chi^2_W(\tilde{\mathcal{H}}^{(b)})$ để hiệu chỉnh đa kiểm định.
   - Phân loại trạng thái Phễu Gatekeeper:
     - `PASS_ALPHA`: Vượt ngưỡng kiểm định Monte Carlo 95% (hoặc $\max_W BF_{10}^{(W)} \ge 3.0$) **VÀ** trung bình xác suất hiệu chuẩn của Top 2 bóng đạt $\ge 10.6904\%$ ($\text{Lift} \ge +6.9045\%$).
     - `WARN_WEAK_SIGNAL`: Có dấu hiệu lệch nhẹ ($\chi^2$ vượt phân vị 90% hoặc $BF_{10} \ge 1.0$) nhưng $\text{Lift}_{\text{Top2, Calibrated}} < +6.9045\%$.
     - `FAIL_WHITE_NOISE_CASH_BRAKE`: Nằm trong vùng nhiễu trắng ($p_{\text{MC}} > 0.10$ và $BF_{10} < 1.0$) $\rightarrow$ Khuyến nghị hệ số vốn `0.0x` (Phanh tiền mặt bảo vệ vốn).

#### C. Trụ cột 3 — Hội Đồng Dự Báo Xác Suất Hiệu Chuẩn & Tối Ưu Hóa Cửa Sổ Quá Khứ Nhân Quả (`Dual-Branch Calibrated Engine` + `Causal Past-Window Optimizer` $W^*_{t-1}$)
Tại mỗi kỳ $t-1$ (dự báo cho kỳ $t$, chỉ sử dụng lịch sử quá khứ `draws[0 : t]`, che kín 100% kết quả kỳ $t$):
1. **Nhánh 1 — `Bayesian Dirichlet-BOCD` kết hợp `Causal Past-Window Optimizer` $W^*_{t-1}$ & `Lag-1 Burst Exhaustion Filter`:**
   - **Tối ưu hóa cửa sổ quá khứ nhân quả $W^*_{t-1}$ kèm Trừ Khấu Hao Kỳ Liền Trước (`Lag-1 Exhaustion Filter`) độc lập cho từng lồng cầu (`tens_cage` và `units_cage`):**
     - Trên tập ứng viên cửa sổ quá khứ hội tụ $\mathcal{W} = \{15, 20, 25, 30, 40, 50, 60\}$ (loại bỏ các cửa sổ quá ngắn $< 15$ kỳ vốn bị nhiễu $\sigma > 2\%$ làm đảo ngược `Rank 1 < Rank 2`), tại thời điểm $t-1$, hệ thống chỉ dùng dữ liệu quá khứ $\mathcal{H}_{0:t-1}$ (`draws[0 : t]`) và áp dụng bộ lọc trừ khấu hao hụt hơi kỳ liền trước $\tau-1$:
       $$\tilde{N}_{\tau-1, i}^{(W)} = \max\left(0, \sum_{k=1}^{W} n_{\tau-k, i} - \gamma_{\text{lag1}} \cdot \frac{W}{20} \cdot n_{\tau-1, i}\right) \quad (\gamma_{\text{lag1}} = 0.35)$$
       để chấm điểm khả năng dự báo bước kế tiếp tại các bước quá khứ $\tau \le t-1$ (tối ưu hóa đồng thời tỷ lệ nổ của Top 2 bóng và ưu thế dẫn đầu của `Rank 1`) nhằm chọn ra cửa sổ tối ưu $W^*_{t-1} \in \mathcal{W}$.
     - Độ lệch chuẩn nhiễu lý thuyết của cửa sổ $W^*_{t-1}$ được tính trực tiếp từ quy tắc 18 giải/kỳ và 10 bóng/lồng mà không dùng hằng số kinh nghiệm:
       $$\sigma_{\text{nhiễu}}(W^*_{t-1}) = \sqrt{\frac{0.10 \times 0.90}{18 \times W^*_{t-1}}} = \frac{1}{\sqrt{200 \times W^*_{t-1}}}$$
   - **Cập nhật hậu nghiệm `Bayesian Dirichlet-BOCD` (Adams & MacKay 2007 cho dữ liệu Đa thức):**
     - Duy trì phân phối độ dài trạng thái hiện hành $r_{t-1} \in \{0, 1, \dots, R_{\max}\}$ ($R_{\max} = 60$, kỳ vọng độ dài trạng thái thích ứng theo $W^*_{t-1}$, tham số co rút tiên nghiệm $\alpha_0 = 18.0$).
     - Xác suất dự báo hậu nghiệm tại độ dài trạng thái $r$:
       $$P_{\text{BOCD}}(i \mid r_{t-1} = r) = \frac{\alpha_0 + \sum_{\tau = t - r}^{t-1} n_{\tau, i}}{10\alpha_0 + 18 \cdot r}$$
     - Khi không có cảnh báo thay bóng mới từ kiểm định 2 mẫu $G^2$, phân phối dự báo tích hợp trực tiếp vector đếm đã trừ khấu hao kỳ liền trước $\tilde{N}_{t-1, i}^{(W^*_{t-1})}$ tại cửa sổ tối ưu nhân quả $W^*_{t-1}$ để bảo toàn nghiêm ngặt trật tự thực nghiệm `Rank 1 > Rank 2`.
2. **Nhánh 2 — `Regularized Markov & Gap Multinomial Model`:**
   - Điểm logit tuyến tính có phạt chuẩn hóa $L_2$ ($\lambda_{L2} = 10.0$) kết hợp xác suất chuyển tiếp Markov bậc 1 từ kỳ $t-1$, áp lực chu kỳ gan chuẩn hóa, và **phạt âm `-0.10` trên chỉ báo nổ đột biến kỳ liền trước (`Lag-1 Burst Exhaustion Penalty`)**, đưa qua hàm Softmax có nhiệt độ làm mượt $\tau_{\text{temp}} \ge 1.0$ để xuất $P_{\text{Seq}}(i)$.
3. **Bộ Hợp Nhất Hiệu Chuẩn Tối Ưu Không Ngưỡng Cắt Tự Chế (`Out-of-Sample Brier Pooling without Arbitrary Noise-Floor Clipping`):**
   - Hợp nhất lồi 2 nhánh với phân phối đều $U_i = 0.10$:
     $$P_{\text{AI}}(i) = w_1 P_{\text{BOCD}}(i) + w_2 P_{\text{Seq}}(i) + (1 - w_1 - w_2) \cdot 0.10$$
   - Trọng số $(w_1, w_2)$ được giải bằng quy hoạch lồi (`SLSQP`) trên cửa sổ trượt quá khứ $W_{\text{val}} = 30$ kỳ gần nhất ($\tau \in \{t-30 \dots t-1\}$) để cực tiểu hóa **Multi-class Brier Score + Phạt điều chuẩn giải tích dựa trên phương sai lý thuyết $\sigma^2_{\text{nhiễu}}(W^*_{t-1}) = \frac{1}{200 \times W^*_{t-1}}$**, thỏa mãn $w_1 \ge 0, w_2 \ge 0, w_1 + w_2 \le 1$.
   - **Loại bỏ hoàn toàn ngưỡng tự chế `noise_floor = 3.5e-4`:** Tuyệt đối không dùng ngưỡng cắt cứng `noise_floor = 3.5e-4` làm triệt tiêu $(w_1, w_2) \to (0, 0)$ và gây lỗi tie-breaker chọn mù bóng `[0, 1, 2...]`; bảo toàn liên tục thứ hạng thông tin thực nghiệm từ cửa sổ quá khứ nhân quả $W^*_{t-1}$.

#### D. Trụ cột 4 — Ghép Bộ Số Điểm Ngọt, Quy Hoạch Động 19 Trạng Thái & Kiểm Thử Trượt
Tại mỗi kỳ kiểm thử $t \in \{T_{\text{warmup}}, \dots, T-1\}$ (với $T_{\text{warmup}} = 45$ kỳ để đảm bảo đủ cỡ mẫu khởi động trên cả khung `3Y` của `XSVL` gồm 156 kỳ, оставляя $111$ kỳ kiểm thử ngoài mẫu cho `XSVL-3Y`, $215$ kỳ cho `XSVL-5Y`, $267$ kỳ cho `XSHCM-3Y` và $475$ kỳ cho `XSHCM-5Y`):
1. **Xếp hạng bóng độc lập trên từng lồng cầu:**
   - Sắp xếp 10 quả bóng Lồng Chục theo $P_{\text{AI}}^{\text{tens}}$ giảm dần: $a_{(1)}, a_{(2)}, \dots, a_{(10)}$.
   - Sắp xếp 10 quả bóng Lồng Đơn vị theo $P_{\text{AI}}^{\text{units}}$ giảm dần: $b_{(1)}, b_{(2)}, \dots, b_{(10)}$.
2. **Định nghĩa Bộ số Điểm Ngọt $\mathcal{S}_{A \times B}$ và Tính lãi/lỗ thực tế tại kỳ $t$:**
   - Tập hợp $N = A \times B$ con số 2 chữ số: $\mathcal{S}_{A \times B} = \{(a_{(u)}, b_{(v)}) \mid 1 \le u \le A, \ 1 \le v \le B\}$.
   - Số lô trúng thực tế trong 18 giải của kỳ $t$: $K_t(\mathcal{S}_{A \times B}) = \sum_{g=0}^{17} \mathbb{I}(\text{prizes\_last2}_{t, g} \in \mathcal{S}_{A \times B})$.
   - **Cấu hình Đồng nhất (`2x2`, `3x3`, `1x4`, `2x7`, `3x6` — đặt `1.0đ`/số):**
     $$\text{Cost}_t = N \text{ (đồng)}, \quad \text{Revenue}_t = K_t(\mathcal{S}_{A \times B}) \times \frac{87.5}{18}, \quad \text{NetProfit}_t = \text{Revenue}_t - \text{Cost}_t$$
   - **Danh mục Lai `Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ)`:**
     - Nhóm Lõi $\mathcal{S}_{\text{Core}} = \mathcal{S}_{2\times2}$ (4 số @ `1.0đ`/số = `4.0đ`); Nhóm Vệ tinh $\mathcal{S}_{\text{Sat}} = \mathcal{S}_{3\times3} \setminus \mathcal{S}_{2\times2}$ (5 số @ `0.5đ`/số = `2.5đ`); Tổng vốn $\text{Cost}_t = 6.5\text{đ}$.
     - $\text{Revenue}_t = K_t(\mathcal{S}_{\text{Core}}) \times \frac{87.5}{18} + K_t(\mathcal{S}_{\text{Sat}}) \times \left(0.5 \times \frac{87.5}{18}\right)$.
   - **Chiến thuật Loại trừ Bóng chết (`Negative Filter` trên Giải Đuôi — index `17`):**
     - `negative_filter_81` ($9\times9=81$ số, vốn `81.0đ`/kỳ, trúng Giải ĐB thu `87.5đ`) và `negative_filter_87` (87 số cao nhất, vốn `87.0đ`/kỳ, trúng Giải ĐB thu `87.5đ`).
3. **Phân phối Xác suất 19 Trạng thái Số Nháy $P_{\text{AI}}(K = k)$ cho Giai đoạn 3 (`Kelly Criterion Adapter`):**
   - Tính chính xác $P_{\text{AI}}(K = k \mid \mathcal{S}) = \binom{18}{k} p_{\mathcal{S}}^k (1 - p_{\mathcal{S}})^{18 - k}$ cho $k \in \{0, 1, \dots, 18\}$ với $\sum_{k=0}^{18} P_{\text{AI}}(K = k \mid \mathcal{S}) = 1.0$.

### 5.4. Hợp Đồng Đầu Ra Bàn Giao Sang Giai Đoạn 3 (`Downstream Stage 3 Handoff Schema`)

Hai file `data/outputs/stage3_handoff_XSHCM.json` và `data/outputs/stage3_handoff_XSVL.json` (cùng file tổng hợp `reports/stage2_dual_station_comparison.json`) được kiểm tra nghiêm ngặt bằng Pydantic model `Stage3HandoffContract` (`extra="forbid"`, `allow_inf_nan=False`), lưu kết quả của cả 2 khung `5y` và `3y` để Giai đoạn 3 sử dụng trực tiếp.

### 5.5. Bốn Cổng Kiểm Soát Chống Gian Lận (`Adversarial Gate Hardening — Anti-False-PASS`)

| Cổng Kiểm Soát (`Gate`) | Kịch Bản Tấn Công / Dữ Liệu Bẩn (`Adversarial Vector`) | Hành Vi Chặn Đứng (`Fail-Closed Rule`) |
| :--- | :--- | :--- |
| **Gate 1: `DataSchemaGate`** | Kỳ quay thiếu giải ($<18$) hoặc thừa giải ($>18$), ký tự số Unicode full-width (`"０８"`), chuỗi rỗng, trùng ngày `draw_date`, ngày quay bị lộn ngược thứ tự thời gian, hoặc tổng vector đếm $\sum_{i=0}^9 n_{t,i} \ne 18$. | Ném ngoại lệ `DataIntegrityError` ngay lập tức; tuyệt đối không tự động điền `"00"` hay bỏ qua giải lỗi. |
| **Gate 2: `PreDrawCutoffGate`** | Hàm tạo đặc trưng hoặc bộ hiệu chuẩn tại kỳ mục tiêu $t$ vô tình đọc dữ liệu từ chỉ số $\ge t$ (rò rỉ tương lai `Look-Ahead Leakage`) hoặc dùng Giải 8 của ngày $t$ để đoán Giải ĐB ngày $t$. | Mọi hàm `extract_features(history, target_draw)` kiểm tra `assert history[-1].draw_index < target_draw.draw_index` và `history[-1].draw_date < target_draw.draw_date`. Nếu vi phạm, ném `TemporalLeakageError` ngay lập tức. |
| **Gate 3: `SimplexCalibrationGate`** | Bảng xác suất dự báo $P_{\text{AI}}(0\dots9)$ có phần tử âm ($P_i < 0$), `NaN`, `Inf`, hoặc tổng $\left|\sum_{i=0}^9 P_i - 1.0\right| > 10^{-6}$, hoặc trọng số hợp nhất $(w_1, w_2)$ nằm ngoài miền lồi. | Ném ngoại lệ `CalibrationIntegrityError`; không bao giờ cho phép xuất xác suất chưa chuẩn hóa sang bộ chọn Điểm Ngọt hay Giai đoạn 3. |
| **Gate 4: `FalsificationGatekeeper`** | Đưa chuỗi ngẫu nhiên thuần túy (`White Noise`) vào hệ thống nhưng mô hình vẫn cố báo lãi ảo trong mẫu, hoặc truyền cỡ mẫu quá ngắn ($T < 60$ kỳ). | Nếu $T < 60$ ném `InsufficientSampleSizeError`. Nếu chuỗi không vượt ngưỡng kiểm định đối chứng 1,000 chuỗi Monte Carlo ($p_{\text{MC}} > 0.05$ và $BF_{10} < 1.0$), bắt buộc khóa trạng thái `FAIL_WHITE_NOISE_CASH_BRAKE` và đặt `recommended_capital_multiplier = 0.0`. |

---

## 6. Code Style (Phong Cách Mã Nguồn & Quy Ước Kỹ Thuật)

- **Kiểu tĩnh & Kiểm định Hợp đồng (`Strict Typing & Pydantic v2`):** Mọi hàm công khai phải có đầy đủ Type Hints (`from __future__ import annotations`). Không dùng `Any` cho cấu trúc dữ liệu đầu vào/đầu ra.
- **Tính toán Vector hóa & Ổn định Số học (`Log-Space Numerical Stability`):** Khi tính xác suất đa thức và hệ số Bayes $BF_{10}$, bắt buộc tính trong không gian Logarit (`scipy.special.gammaln` và `scipy.special.logsumexp`) để tránh tràn số dưới (`underflow`) khi nhân qua 18 giải $\times$ 60 kỳ.

---

## 7. Testing Strategy (Chiến Lược Kiểm Thử Toàn Diện — PASS & Negative Mutation FAIL)

Sử dụng `pytest` tại thư mục `tests/` với yêu cầu độ phủ tối thiểu **`>= 90%`** và bắt buộc bao gồm cả **kiểm thử luồng chuẩn (`PASS`)** lẫn **kiểm thử đột biến âm đối kháng (`Adversarial Negative Mutation FAIL`)**:

1. **Tầng 1 — Kiểm thử Hằng số Giai đoạn 1 & Hợp đồng Schema (`tests/test_constants_and_schemas.py`):**
   - **PASS:** Xác nhận `REAL_PAYOUT_1D == 87.5`, `BAO_LO_PAYOUT_PER_HIT == 87.5 / 18`, cấu hình `XSHCM` (`520`/`312` kỳ) & `XSVL` (`260`/`156` kỳ), và `Stage3HandoffContract`.
   - **FAIL (Negative Mutation):** Truyền vector 17 giải, ký tự `"9A"` hoặc `"０８"`, hoặc xác suất tổng `0.995` $\rightarrow$ bắt buộc ném `ValidationError` / `DataIntegrityError`.
2. **Tầng 2 — Kiểm thử Chống Rò Rỉ Tương Lai & Trích Xuất Đặc Trưng (`tests/test_pillar1_ingest_and_features.py`):**
   - **PASS:** Kiểm tra bất biến `extract_features(draws[:t], draws[t])` không đổi dù thay đổi `draws[t:]`, và kiểm tra cắt lát `5Y` vs `3Y`.
   - **FAIL (Negative Mutation):** Cố tình truyền lịch sử chứa kỳ $t$ hoặc $t+1$ vào hàm tạo đặc trưng cho kỳ $t$ $\rightarrow$ bắt buộc ném `TemporalLeakageError`.
3. **Tầng 3 — Kiểm thử Phễu Bác Bỏ Nhiễu & 1,000 Chuỗi Monte Carlo (`tests/test_pillar2_falsification_gatekeeper.py`):**
   - **PASS (Synthetic White Noise Immunity):** Đưa chuỗi ngẫu nhiên thuần túy ($p_i = 10.0\%$ đều nhau) qua Phễu Gatekeeper $\rightarrow$ bắt buộc trả về `FAIL_WHITE_NOISE_CASH_BRAKE` và `recommended_capital_multiplier == 0.0`.
   - **PASS (Synthetic True Regime Bias Detection):** Đưa chuỗi giả lập có độ lệch vật lý thật ($+9.0\%$/lồng ở 2 bóng đầu) $\rightarrow$ xác nhận `PASS_ALPHA`, $\chi^2$ vượt phân vị 95% của 1,000 chuỗi Null và $BF_{10} > 3.0$.
   - **FAIL (Negative Mutation):** Đưa chuỗi ngắn $< 60$ kỳ hoặc chứa `NaN` $\rightarrow$ bắt buộc ném `InsufficientSampleSizeError`.
4. **Tầng 4 — Kiểm thử Hội Đồng Xác Suất Hiệu Chuẩn, Cửa Sổ Quá Khứ Nhân Quả $W^*_{t-1}$ & Phát Hiện Điểm Gãy BOCD (`tests/test_pillar3_calibrated_engine.py`):**
   - **PASS:** Xác nhận $\sum_{i=0}^9 P_{\text{AI}}(i) = 1.0 \pm 10^{-9}$, công thức phương sai lý thuyết $\sigma_{\text{nhiễu}}(W^*) = \frac{1}{\sqrt{200 \times W^*}}$ chính xác tuyệt đối, bộ tối ưu hóa cửa sổ nhân quả $W^*_{t-1}$ trên tập $\mathcal{W} = \{15, 20, 25, 30, 40, 50, 60\}$ hoàn toàn bất biến trước mọi thay đổi ở `draws[t:]` (không rò rỉ tương lai), không còn ngưỡng tự chế `noise_floor = 3.5e-4` gây lỗi tie-breaker `[0, 1, 2...]`, và khi mô phỏng thay bóng mới ở kỳ $t = 100$ thì BOCD hạ xác suất bóng cũ về sát nền $10.0\%$ trong vòng $\le 4$ kỳ.
   - **FAIL (Negative Mutation):** Truyền trọng số hợp nhất $w_1 + w_2 = 1.2 > 1.0$ hoặc xác suất âm $\rightarrow$ bắt buộc ném `CalibrationIntegrityError`.
5. **Tầng 5 — Kiểm thử Trượt Điểm Ngọt & Khớp Nối Giai Đoạn 3 (`tests/test_pillar4_walk_forward_backtest.py`):**
   - **PASS:** Kiểm tra công thức tính dòng tiền của Bộ `2x2` (`4.0đ`/kỳ), `3x3` (`9.0đ`/kỳ), `Core 2x2 + Satellite 3x3` (`6.5đ`/kỳ), `Negative Filter` (`81.0đ` / `87.0đ` trên Giải ĐB) và tổng xác suất 19 trạng thái $\sum_{k=0}^{18} P_{\text{AI}}(K = k) = 1.0$.

---

## 8. Boundaries (Ranh Giới Quyền Hạn 3 Tầng)

- **Always do (Luôn luôn thực hiện):**
  - Tuân thủ tuyệt đối hệ quy chiếu dòng tiền tại [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md): Tỷ lệ trả thưởng thực `87.5`, doanh thu mỗi nháy Bao Lô `87.5 / 18 ≈ 4.861111 đồng` trên `1 đồng` vốn mua 1 số.
  - Khóa thời gian `Pre-Draw Temporal Cutoff (t-1)` trên mọi phép tính đặc trưng, hiệu chuẩn và kiểm thử trượt.
  - Chạy đầy đủ bộ test `uv run pytest` và `uv run ruff check` trước khi hoàn tất mỗi tác vụ triển khai.
  - Luôn đặt kết quả thực nghiệm của cả `XSHCM` và `XSVL` (trên cả 2 khung `5Y` và `3Y`) cạnh dải phân vị 90%/95% của 1,000 chuỗi Monte Carlo ngẫu nhiên giả lập.
- **Ask first (Hỏi ý kiến Chủ dự án trước khi làm):**
  - Thay đổi cấu trúc file hợp đồng đầu ra `stage3_handoff_<station_code>.json` hoặc thay đổi các ngưỡng kiểm định mặc định ($\alpha_0 = 18.0, \lambda_{\text{regime}} = 25.0$).
  - Mở rộng thu thập sang 19 đài miền Nam còn lại ngoài `XSHCM` và `XSVL`.
  - Thêm bất kỳ thư viện phụ thuộc (dependency) mới nào ngoài danh sách đã chốt ở Mục 2.
- **Never do (Tuyệt đối cấm):**
  - Không dùng dữ liệu của Giải 8..Giải Nhất trong ngày $t$ để dự đoán cho chính ngày $t$ trong bài toán Bao Lô (*Intra-Draw Leakage*).
  - Không dùng mạng Deep Learning (LSTM, Transformer, MLP nhiều tầng) hoặc tách thành 18 mô hình riêng lẻ cho 18 giải.
  - Không trộn lẫn các công thức gấp thếp tiền cược (`Martingale`, `1-3-2-6`) vào bộ chấm điểm Alpha ở Giai đoạn 2.
  - Không bao giờ sửa test hoặc hạ ngưỡng kiểm định để ép một đài nhiễu trắng báo `PASS_ALPHA` giả tạo.

---

## 9. Success Criteria (Tiêu Chí Nghiệm Thu Hoàn Thành Giai Đoạn 2)

Giai đoạn 2 (`stage2-alpha-discovery`) được nghiệm thu hoàn tất khi thỏa mãn đồng thời 6 điều kiện kiểm chứng được sau:

1. **Dữ liệu Chuẩn hóa 2 Đài (`XSHCM` & `XSVL`):** Hai tệp `data/canonical/XSHCM_canonical.json` (~520 kỳ 5 năm) và `data/canonical/XSVL_canonical.json` (~260 kỳ 5 năm) vượt qua 100% kiểm tra `DataSchemaGate` (đúng 18 giải/kỳ, $\sum n_{t,i} = 18$ cho cả Lồng Chục và Lồng Đơn vị) và hỗ trợ cắt lát chính xác khung `5Y` và `3Y`.
2. **Phễu Kiểm định Bác bỏ Nhiễu Minh bạch (2 Đài $\times$ 2 Khung Thời Gian):** Xuất báo cáo đầy đủ $\chi^2_W$, $BF_{10}^{(W)}$, $H_{\text{norm}}^{(W)}$, Runs/Markov test trên 3 cửa sổ $W \in \{15, 30, 60\}$ đặt cạnh phân vị 90% & 95% của 1,000 chuỗi Monte Carlo ngẫu nhiên giả lập cho cả `XSHCM` (5Y & 3Y) và `XSVL` (5Y & 3Y), trả lời dứt khoát đài nào/khung nào vượt ngưỡng hòa vốn `+6.90%/lồng`.
3. **Độ Chuẩn Xác & Bảo Toàn Xác Suất Của Hội Đồng Dự Báo:** Tại mọi bước kiểm thử trượt $t$, bảng xác suất $P_{\text{AI}}^{\text{tens}}(0\dots9)$ và $P_{\text{AI}}^{\text{units}}(0\dots9)$ có tổng bằng đúng `100.0000%` ($\pm 10^{-6}$), và đạt `Out-of-Sample Multi-class Brier Score` nhỏ hơn hoặc bằng mô hình ngây thơ quá khứ (`Naive Rolling Frequency`).
4. **Báo Cáo Thực Nghiệm Điểm Ngọt & Đường Cong Alpha Decay Đối Chiếu (`XSHCM` vs `XSVL`, `5Y` vs `3Y`):** Xuất đầy đủ bảng so sánh thực nghiệm Walk-Forward giữa `Bộ 2x2 = 4 số`, `Bộ 3x3 = 9 số`, `Core 2x2 + Satellite 3x3 (6.5đ)`, `1x4`, `2x7`, `3x6` và `Negative Filter (81/87 số)` kèm các chỉ số: Tổng lô trúng/30 kỳ, `Daily Win Rate`, tần suất ngày nổ $\ge 2$ lô, tỷ lệ ngày trắng bảng ($K=0$), `Max Losing Streak`, `Max Drawdown`, và đường cong tần suất nổ thực tế ngoài mẫu từ `Rank 1` đến `Rank 10`.
5. **Hợp Đồng Bàn Giao Sang Giai Đoạn 3 (`stage3_handoff_XSHCM.json` & `stage3_handoff_XSVL.json`):** Sinh thành công cả 2 file JSON hợp lệ theo `Stage3HandoffContract` chứa bảng xác suất hiệu chuẩn, chỉ số `conviction_score` và vector xác suất 19 trạng thái $P_{\text{AI}}(K = 0\dots18)$ sẵn sàng cho công thức Kelly ở Giai đoạn 3.
6. **Kiểm Thử Tự Động Xanh 100%:** Toàn bộ unit tests và negative mutation tests chạy qua `uv run pytest` đạt `100% PASS` với độ phủ mã nguồn $\ge 90\%$ và `uv run ruff check` không có lỗi.

---

## 10. Open Questions (Đã Giải Quyết & Khóa Hoàn Toàn — Resolved)

- [x] **Câu hỏi 1 (Khung thời gian lịch sử):** Đã chốt lấy **cả 5 năm gần nhất (`5Y`) lẫn 3 năm gần nhất (`3Y`)** để đánh giá song song độ bền dài hạn và trạng thái máy quay hiện tại.
- [x] **Câu hỏi 2 (Đài mục tiêu):** Đã chốt triển khai và đối chiếu trực tiếp trên **2 đài: Đài TP. Hồ Chí Minh (`XSHCM` — 2 kỳ/tuần)** và **Đài Vĩnh Long (`XSVL` — 1 kỳ/tuần)**.
