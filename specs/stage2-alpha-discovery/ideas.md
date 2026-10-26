# Phương Án Kiến Trúc Giai Đoạn 2: Hệ Thống Phát Hiện Alpha & Dự Báo Xác Suất Hiệu Chuẩn 1 Lồng Cầu (`Two-Stage Gatekeeper & Regularized Ensemble` — Phương Án C)

**Trạng thái:** Đã chốt hướng kiến trúc (Confirmed — Phương án C)  
**Ngày cập nhật:** 2026-10-25  
**Tài liệu liên kết:**
- Bản Ý Định Gốc: [`specs/stage2-alpha-discovery/intent.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/intent.md)
- Quy Ước Dòng Tiền & Điểm Hòa Vốn (GĐ 1): [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md)
- Báo Cáo Trực Quan & Mô Phỏng GĐ 2: [`BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html`](file:///C:/sidehustle/XSTK/BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html)

---

## Domain Context & Core Principles

Bài toán dự báo chọn bóng trên **1 Lồng Cầu (`0`–`9`)** của một đài Xổ Số Miền Nam (XSMN) với **18 giải mở thưởng mỗi kỳ** chịu sự chi phối của 4 quy luật toán học – vật lý cốt lõi đã được thiết lập tại Pha 0:

1. **Hệ quy chiếu Hòa Vốn Bất biến (từ Giai đoạn 1):**
   - Tỷ lệ trả thưởng thực tế: `1 : 87.5` (Biên lợi nhuận nhà cái = `12.5%`).
   - Trong Bao Lô 18 giải, mỗi `1 đồng` vốn mua 1 số thu về $R_{\text{1 lô}} = \frac{87.5}{18} \approx \mathbf{4.8611 \text{ đồng}}$ trên mỗi lô trúng.
   - Để vượt qua Điểm Hòa Vốn trong dài hạn, xác suất trúng của mỗi con số 2 chữ số phải đạt $\ge \frac{1}{87.5} \approx \mathbf{1.1429\%}$ (tức độ lệch gộp 2 lồng đạt **$\ge +14.29\%$** so với mức ngẫu nhiên $1.00\%$).
   - Quy về từng lồng cầu độc lập (`Hàng Chục` và `Hàng Đơn Vị`), mỗi lồng cầu cần đạt độ lệch chuẩn hóa tối thiểu:
     $$\text{Lift}_{\text{BE/lồng}} = \sqrt{\frac{100}{87.5}} - 1 \approx \mathbf{+6.90\% / \text{lồng}} \quad (\text{tức xác suất bóng được chọn đạt } \ge \mathbf{10.69\%} \text{ so với } 10.00\%)$$

2. **Quy tắc Chốt dữ liệu Trước giờ quay (`Pre-Draw Temporal Cutoff`):**
   - Trong 1 kỳ mở thưởng ngày $t$, mỗi lồng cầu nhả bóng 18 lần độc lập (Giải 8 $\to$ Giải ĐB). Tuy nhiên, vì quyết định đặt cược Bao Lô phải thực hiện trước giờ quay thưởng, mọi mô hình dự báo cho kỳ $t$ chỉ được phép sử dụng thông tin lịch sử từ kỳ $t-1$ trở về trước. Tuyệt đối cấm rò rỉ dữ liệu nội bộ kỳ $t$ (*Intra-Draw Look-Ahead Leakage*).

3. **Ảo ảnh Phương sai Mẫu nhỏ & Công thức Phương sai Lý thuyết từ Bài toán (`Problem-Derived Noise Standard Error`):**
   - Trong mỗi kỳ mở thưởng có $m = 18$ giải và $10$ quả bóng ($p_0 = 0.10$). Khi nhìn lại một khoảng thời gian $W$ kỳ mở thưởng trong quá khứ ($N_W = 18 \times W$ lần nhả bóng), độ lệch chuẩn nhiễu tự nhiên của mỗi quả bóng được định đoạt 100% bởi cấu trúc bài toán mà không cần bất kỳ con số giả định nào:
     $$\sigma_{\text{nhiễu}}(W) = \sqrt{\frac{p_0 (1 - p_0)}{18 \times W}} = \sqrt{\frac{0.10 \times 0.90}{18 \times W}} = \frac{1}{\sqrt{200 \times W}}$$
   - Ví dụ: Tại $W = 30$ kỳ ($540$ giải), $\sigma_{\text{nhiễu}}(30) = \frac{1}{\sqrt{6000}} \approx \mathbf{1.29\%}$ (nhiễu 95% là $\pm 2.53\%$); tại $W = 50 \div 60$ kỳ ($900 \div 1,080$ giải), $\sigma_{\text{nhiễu}}(W) \approx 0.91\% \div 1.00\%$ (nhiễu 95% là $\pm 1.79\% \div 1.96\%$). Nếu không có **Phễu Kiểm Định Bác Bỏ Nhiễu (`Statistical Falsification`)** và **Co rút Bayes dựa trên $\sigma_{\text{nhiễu}}(W^*)$**, mô hình sẽ nhầm nhiễu quá khứ là cầu thật và thua lỗ khi chạy thực tế ngoài mẫu (*Out-of-Sample*).

4. **Tính Dừng Cục Bộ, Điểm Gãy & Tối Ưu Hóa Cửa Sổ Quá Khứ Nhân Quả (`Regime Shifts & Causal Past-Window Optimizer` $W^*_{t-1}$):**
   - Độ lệch vật lý của mỗi lồng cầu (`Lồng Hàng Chục` và `Lồng Hàng Đơn Vị`) có chu kỳ tồn tại khác nhau tùy đài và tùy thời điểm bảo dưỡng máy quay. Thay vì áp đặt một cửa sổ cố định từ kinh nghiệm, tại mỗi bước thời gian $t$ (khi kết quả ngày hôm nay `draws[t]` bị che kín hoàn toàn), hệ thống sử dụng bộ **Tìm Kiếm Cửa Sổ Quá Khứ Thích Ứng Nhân Quả (`Causal Past-Window Optimizer` $W^*_{t-1}$)** quét độc lập cho từng lồng cầu trên tập ứng viên:
     $$\mathcal{W} = \{15, 20, 25, 30, 40, 50, 60\}$$
     chỉ dùng lịch sử quá khứ `draws[0 : t]` để tìm xem khoảng thời gian nhìn lại $W^*_{t-1}$ bao nhiêu kỳ dự đoán ngày kế tiếp chuẩn xác nhất, kết hợp với phát hiện điểm gãy trực tuyến (`Online Changepoint Detection`) để tự động reset bộ nhớ khi trạng thái cũ kết thúc.

---

## Problem Statement

> **Làm thế nào để chúng ta (HMW)** thiết kế một quy trình dữ liệu, kiểm định thống kê và mô hình AI chuẩn hóa cho **1 Lồng Cầu (`0`–`9`)** từ con số 0 trên 1 đài XSMN mẫu, có khả năng **(1) tự động phân biệt độ lệch vật lý thật với nhiễu mẫu nhỏ và phát hiện điểm thay bóng mới**, **(2) xuất ra bảng xác suất hiệu chuẩn $\sum_{i=0}^9 P_i = 100\%$ trước mỗi kỳ quay**, và **(3) kiểm thử trượt (`Walk-Forward Backtest`) khách quan trên các cấu hình Điểm Ngọt ($2\times2 = 4$ số, $3\times3 = 9$ số, `Core 2x2 + Satellite 3x3`)** để cung cấp thông số thực nghiệm chính xác cho Giai đoạn 3?

---

## Chosen Architecture & Inner Mechanics

Chủ dự án đã quyết định chọn **Phương án C: Kiến Trúc Lai Hai Tầng "Phễu Kiểm Định Chống Nhiễu + Hội Đồng Co Rút Thích Ứng" (`Two-Stage Gatekeeper & Regularized Ensemble`)**.

Kiến trúc này áp dụng đồng nhất cho cả **Lồng Hàng Chục** và **Lồng Hàng Đơn Vị**, vận hành qua **4 Trụ cột tuần tự**:

### Trụ cột 1: Tổ chức Dữ liệu Chuẩn hóa & Bộ Đặc trưng Tinh gọn (`Compact Data Schema & Feature Engineering`)
1. **Lựa chọn Đài Mẫu Chuẩn (`Pilot Station`):**
   - Sử dụng **Đài TP. Hồ Chí Minh (`XSHCM`)** làm đài thí điểm đầu tiên vì đài này mở thưởng **2 kỳ/tuần (Thứ Hai & Thứ Bảy)** $\rightarrow \approx 104$ kỳ/năm ($1,872$ lần nhả bóng/lồng/năm), giúp thu thập đủ độ dày thống kê nhanh gấp đôi các đài tỉnh (vốn chỉ quay 1 kỳ/tuần), đồng thời dễ dàng áp dụng sang 20 đài còn lại do cùng cấu trúc 18 giải.
2. **Cấu trúc Bảng Dữ liệu Chuẩn (`Canonical Schema`):**
   - Mỗi kỳ mở thưởng $t$ của một đài được tách thành 18 bản ghi giải thưởng (hoặc 1 bản ghi tổng hợp kỳ) với 2 chữ số cuối của từng giải $g \in \{1\dots18\}$ được phân rã thành:
     - `tens_digit` ($d_{t,g}^{\text{Chục}} \in \{0\dots9\}$)
     - `units_digit` ($d_{t,g}^{\text{Đơn vị}} \in \{0\dots9\}$)
   - Tổng hợp ở cấp độ kỳ $t$ cho mỗi lồng cầu thành vector đếm đa thức 10 chiều:
     $$\mathbf{c}_t = [n_{t,0}, n_{t,1}, \dots, n_{t,9}] \quad \text{với } \sum_{i=0}^9 n_{t,i} = 18$$
3. **3 Nhóm Đặc trưng Đầu vào (`Input Features`) tính tại thời điểm $t-1$:**
   - **Nhóm 1 — Chuỗi tần suất đa thức theo cửa sổ trạng thái (`Regime Count Vectors`):** Vector số lần xuất hiện tích lũy của từng quả bóng $i \in \{0\dots9\}$ trên các độ dài trạng thái $r \in \{1, 2, \dots, R_{\max}\}$.
   - **Nhóm 2 — Động học Nhịp rơi & Áp lực Chu kỳ Gan (`Recency & Standardized Gap Z-Score`):** Số kỳ liên tiếp quả bóng $i$ vắng mặt hoàn toàn ($n_{t,i} = 0$) hoặc nổ yếu ($\le 1$ nháy), được chuẩn hóa thành điểm $Z\text{-score}$ so với kỳ vọng nhị thức, cùng tốc độ rơi lại sau kỳ nổ đột biến ($\ge 3$ nháy/kỳ).
   - **Nhóm 3 — Ma trận Chuyển trạng thái Markov Bậc 1 làm mượt Laplace (`Smoothed First-Order Markov Transitions`):** Xác suất có điều kiện để bóng $i$ xuất hiện vượt mức trung bình ở kỳ $t$ dựa trên tập bóng thống trị ở kỳ $t-1$ và nhóm giải đầu/cuối buổi.

### Trụ cột 2: Phễu Kiểm Định Bác Bỏ Nhiễu & Đối Chứng Giả Lập (`Statistical Falsification Gatekeeper`)
Trước khi cho phép mô hình xuất tín hiệu đặt cược, dữ liệu của từng lồng cầu phải đi qua **Phễu Kiểm Định Kép**:
1. **Bộ 4 Phép Kiểm Định Thống Kê Đa Cửa Sổ ($W \in \{15, 30, 60\}$ kỳ):**
   - **Kiểm định $\chi^2$ Đa thức (`Multinomial Chi-Square Goodness-of-Fit`):** Đo độ lệch tần suất của 10 quả bóng so với phân phối đều $10.0\%$:
     $$\chi^2 = \sum_{i=0}^9 \frac{(O_i - E_i)^2}{E_i}, \quad E_i = 0.10 \times 18 \times W$$
   - **Tỷ số Hệ số Bayes (`Dirichlet-Multinomial Bayes Factor` $BF_{10}$):** So sánh trực tiếp xác suất biên của dữ liệu dưới giả thuyết $H_1$ (lồng cầu có độ lệch) so với giả thuyết $H_0$ (lồng cầu chuẩn $10\%$).
   - **Shannon Entropy Chuẩn hóa ($H_{\text{norm}} \in [0, 1]$):** Đo mức độ tập trung xác suất trong lồng cầu.
   - **Kiểm định Tính độc lập Chuỗi (`Wald-Wolfowitz Runs Test` & `Markov Transition Chi-Square`):** Kiểm tra xem lồng cầu có tính bám chuỗi hay quy luật chuyển trạng thái giữa các kỳ liên tiếp hay không.
2. **Đối chứng với 1,000 Lịch sử Ngẫu nhiên Giả lập (`Monte Carlo Permutation / Null Benchmark`):**
   - Hệ thống tự động sinh **1,000 chuỗi lịch sử mở thưởng ngẫu nhiên chuẩn $10.0\%$** có cùng số kỳ $T$ với dữ liệu thực của đài.
   - Mọi chỉ số thống kê và lợi nhuận Backtest trên dữ liệu thực đều được đặt cạnh dải phân vị **90% và 95%** của 1,000 chuỗi ngẫu nhiên. Nếu đài đang xét nằm hoàn toàn trong vùng nhiễu trắng ($p\text{-value} > 0.05$ và $BF_{10} < 1$), Phễu Gatekeeper gắn nhãn **`[NHIỄU TRẮNG — KÍCH HOẠT PHANH TIỀN MẶT]`** để bảo vệ vốn tuyệt đối.

### Trụ cột 3: Hội Đồng Dự Báo Xác Suất Hiệu Chuẩn 10 Quả Bóng (`Dual-Branch Calibrated Probability Engine` + `Causal Past-Window Optimizer` $W^*_{t-1}$)
Với mỗi lồng cầu trước kỳ mở thưởng $t$ (chỉ dùng lịch sử quá khứ `draws[0 : t]`, che kín 100% kết quả kỳ $t$), mô hình kết hợp 2 nhánh ước lượng độc lập để xuất bảng xác suất $P_{\text{AI}}(0\dots9)$ bảo toàn $\sum_{i=0}^9 P_i = 100\%$:
1. **Nhánh 1 — Ước lượng Độ lệch Vật lý, Điểm thay bóng, Tối ưu Cửa sổ Quá khứ Nhân quả ($W^*_{t-1}$) & Bộ lọc Hụt hơi Kỳ liền trước (`Lag-1 Burst Exhaustion Filter`):**
   - Thực nghiệm trên dữ liệu 5 năm của XSMN cho thấy tương quan bậc 1 (`Lag-1` giữa kỳ $t-1$ và $t$) mang dấu âm (`-0.006` đến `-0.013`): quả bóng vừa nổ đột biến $\ge 3$ hoặc $\ge 4$ nháy ở kỳ hôm qua $t-1$ bị hụt hơi ngắn hạn (*Lag-1 Exhaustion*), tụt xác suất nổ ở kỳ hôm nay $t$ xuống `9.52% – 9.76%`. Nếu cộng nguyên vẹn $n_{t-1}$ hoặc xét các cửa sổ quá ngắn ($W < 15$), quả bóng nổ ảo hôm qua sẽ chiếm ngôi `Rank 1` rồi hụt hơi hôm nay, gây ra nghịch lý `Rank 1 < Rank 2`.
   - Tại mỗi kỳ $t$, bộ **Causal Past-Window Optimizer** đánh giá độc lập cho từng lồng cầu (`tens_cage` và `units_cage`) trên tập cửa sổ hội tụ $\mathcal{W} = \{15, 20, 25, 30, 40, 50, 60\}$ (với $\sigma_{\text{nhiễu}}(W) \le 1.83\%$) kết hợp **Trừ Khấu Hao Kỳ Liền Trước (`Lag-1 Burst Exhaustion Filter`)**:
     $$\tilde{N}_{\tau-1, i}^{(W)} = \max\left(0, \sum_{k=1}^{W} n_{\tau-k, i} - \gamma_{\text{lag1}} \cdot \frac{W}{20} \cdot n_{\tau-1, i}\right) \quad (\gamma_{\text{lag1}} = 0.35)$$
     bằng cách đo hiệu suất dự báo một bước về trước tại các bước quá khứ $\tau \le t-1$ (chỉ dùng $[\tau-W : \tau)$ để đoán $\tau$) nhằm tìm ra độ dài cửa sổ quá khứ tối ưu $W^*_{t-1} \in \mathcal{W}$ đảm bảo `Rank 1 > Rank 2`.
   - Theo dõi phân phối hậu nghiệm của độ dài trạng thái hiện hành $P(r_{t-1} \mid \text{Data}_{0:t-1})$ với kỳ vọng trạng thái thích ứng theo $W^*_{t-1}$ và công thức phương sai lý thuyết của bài toán $\sigma_{\text{nhiễu}}(W^*_{t-1}) = \frac{1}{\sqrt{200 \times W^*_{t-1}}}$.
   - Với mỗi độ dài trạng thái $r$, xác suất hậu nghiệm của bóng $i$ được cập nhật giải tích với tiên nghiệm đều $\alpha_0$, tích hợp cùng ước lượng cửa sổ tối ưu $W^*_{t-1}$ (đã trừ khấu hao kỳ liền trước $t-1$) để bảo toàn thứ hạng thực nghiệm `Rank 1 > Rank 2 > ... > Rank 10`.
   - Khi nhà đài vừa thay bóng mới (kết quả 18 giải đi ngược phân phối cũ, thống kê $G^2$ hai mẫu vượt ngưỡng), trọng số của các trạng thái ngắn tăng vọt, tự động kéo xác suất của bóng nóng cũ về mức an toàn $10.0\%$ chỉ sau $3 \to 4$ kỳ.
2. **Nhánh 2 — Ước lượng Động học Chuỗi có Phạt Chuẩn hóa (`Regularized Markov & Gap Multinomial Model`):**
   - Sử dụng mô hình hồi quy Đa thức có phạt chuẩn hóa $L_2$ mạnh trên Nhóm đặc trưng 2 và 3 để xuất phân phối $P_{\text{Seq}}(i)$, trong đó chỉ báo nổ đột biến kỳ liền trước ($\mathbb{I}(n_{t-1, i} \ge 3)$) mang **trọng số phạt âm (`-0.10`, Lag-1 Burst Exhaustion Penalty)** thay vì cộng thưởng dương.
3. **Bộ Hợp Nhất Hiệu Chuẩn Tối Ưu Không Ngưỡng Cắt Tự Chế (`Out-of-Sample Brier Pooling without Arbitrary Noise-Floor Clipping`):**
   - Kết hợp tuyến tính lồi hai nhánh với nền ngẫu nhiên $U_i = 0.10$:
     $$P_{\text{AI}}(i) = w_1 P_{\text{BOCD}}(i) + w_2 P_{\text{Seq}}(i) + (1 - w_1 - w_2) \cdot 0.10$$
   - Trong đó trọng số $(w_1, w_2)$ với $w_1 + w_2 \le 1$ được tối ưu hóa trượt trên tập Validation quá khứ để cực tiểu hóa **Multi-class Brier Score** có điều chuẩn giải tích dựa trên phương sai lý thuyết $\sigma^2_{\text{nhiễu}}(W^*_{t-1}) = \frac{1}{200 \times W^*_{t-1}}$. **Tuyệt đối không dùng ngưỡng tự chế `noise_floor = 3.5e-4`** (vốn ép cứng $w_1 = w_2 = 0$ và gây ra lỗi tie-breaker chọn mù bóng `[0, 1, 2...]`). Đảm bảo tuyệt đối $\sum_{i=0}^9 P_{\text{AI}}(i) = 100\%$ và bảo toàn thứ hạng thông tin thực nghiệm từ cửa sổ quá khứ $W^*_{t-1}$.

### Trụ cột 4: Kiểm Thử Trượt Điểm Ngọt & Đường Cong Suy Giảm Alpha (`Walk-Forward Sweet-Spot Portfolio Backtester`)
Chạy kiểm thử cuốn chiếu từng kỳ (`Strict Step-by-Step Walk-Forward`) từ kỳ $T_{\text{warmup}}$ đến hết lịch sử:
1. **Đo Đường cong Suy giảm Alpha theo Thứ hạng Bóng (`Rank-Ordered Alpha Decay`):**
   - Ở mỗi kỳ $t$, sắp xếp 10 quả bóng theo $P_{\text{AI}}$ giảm dần (`Rank 1` $\to$ `Rank 10`), sau đó thống kê tần suất nổ thực tế ở kỳ $t+1$ của từng thứ hạng để biết chính xác: Bóng `Rank 1`, `Rank 2`, `Rank 3` thực sự đạt bao nhiêu `%` ngoài mẫu, và Bóng `Rank 10` (bóng chết) bị ức chế xuống bao nhiêu `%`.
2. **Đo lường & Đối đầu Trực tiếp các Cấu hình Điểm Ngọt ($N = A \times B$):**
   - Ghép xác suất 2 lồng cầu $P(ab) = P_{\text{AI}}^{\text{Chục}}(a) \times P_{\text{AI}}^{\text{Đơn vị}}(b)$ và chấm điểm đồng thời trên chu kỳ trượt 30 kỳ (`540 giải`):
     - **Bộ $2\times2 = 4$ số** (Vốn `4.0đ`/kỳ — Hòa vốn tháng `24.69 lô`, mục tiêu $\ge 25$ lô/30 kỳ).
     - **Bộ $3\times3 = 9$ số** (Vốn `9.0đ`/kỳ — Hòa vốn tháng `55.54 lô`, mục tiêu $\ge 56$ lô/30 kỳ).
     - **Danh mục Lai `Core 2x2 (1.0đ) + Satellite 3x3 (0.5đ)`** (Vốn `6.5đ`/kỳ — kết hợp biên lãi cao của nhóm Lõi 4 số với lưới bảo hiểm thu hồi vốn của 5 số Vệ tinh).
     - **Các cấu hình Điểm Ngọt mở rộng & Bất đối xứng:** $1\times4 = 4$ số, $2\times7 = 14$ số ($K=3$), $3\times6 = 18$ số ($K=4$).
     - **Chiến thuật Loại trừ bóng chết (`Negative Filter`):** Loại 1–2 bóng có $P_{\text{AI}}$ thấp nhất mỗi lồng cầu (phục vụ đánh Đuôi 81–87 số).
   - Xuất đầy đủ bộ chỉ số chuẩn bị cho Giai đoạn 3: Tổng lô trúng/30 kỳ, `Daily Win Rate`, tần suất ngày đa nháy ($\ge 2$ lô), tỷ lệ ngày trắng bảng ($K=0$), `Max Losing Streak`, `Max Drawdown`, và `Realized ROI (%)`.

---

## Key Assumptions to Validate

- [ ] **Giả định 1 — Tồn tại Độ lệch Cục bộ Vượt Ngưỡng Hòa Vốn (`Local Regime Bias Existence`):**
  - *Nội dung:* Trên dữ liệu thực của đài XSMN (bắt đầu từ Đài TP.HCM `XSHCM`), tồn tại các cửa sổ trạng thái mà Top 2 hoặc Top 3 quả bóng do mô hình chọn đạt tần suất nổ ngoài mẫu $\ge 10.69\%$/bóng ($\ge +6.90\%$/lồng) hoặc vượt phân vị 95% của 1,000 chuỗi ngẫu nhiên.
  - *Cách kiểm chứng:* Chạy Trụ cột 2 & Trụ cột 4 trên lịch sử 3–5 năm của Đài TP.HCM và so sánh trực tiếp đường lợi nhuận Walk-Forward với dải phân vị 95% của 1,000 chuỗi Monte Carlo Null.
- [ ] **Giả định 2 — Hình thái Suy giảm từ Bóng Top 2 sang Bóng Top 3 (`Top-2 vs Top-3 Alpha Decay`):**
  - *Nội dung:* Quả bóng đứng thứ 3 (`Rank 3`) vẫn giữ được độ lệch dương đủ tốt để cấu hình `Core 2x2 + Satellite 3x3` (vốn `6.5đ`) đạt tỷ suất lợi nhuận/rủi ro (Sharpe / Calmar Ratio) cao hơn đánh thuần `2x2 = 4 số`.
  - *Cách kiểm chứng:* Đo trực tiếp tần suất nổ thực nghiệm ngoài mẫu của riêng từng hạng bóng `Rank 1`, `Rank 2`, `Rank 3` trên cả Lồng Hàng Chục và Lồng Hàng Đơn Vị.
- [ ] **Giả định 3 — Độ dài Trạng thái Đủ Lâu so với Độ trễ BOCD (`Regime Persistence vs Detection Lag`):**
  - *Nội dung:* Một trạng thái lồng cầu/bộ bóng kéo dài trung bình $\ge 15–20$ kỳ quay, đủ dài hơn độ trễ phát hiện điểm gãy ($3 \to 4$ kỳ) của thuật toán BOCD để thu về lợi nhuận ròng dương.
  - *Cách kiểm chứng:* Phân tích phân phối độ dài trạng thái hậu nghiệm $P(r_t \mid \text{Data})$ trên dữ liệu lịch sử thực.

---

## MVP Scope

Phạm vi tối thiểu (MVP) của Giai đoạn 2 tập trung giải quyết trọn vẹn quy trình chuẩn trên **1 đài thí điểm đầu tiên (`Đài TP.HCM - XSHCM`)** (và hỗ trợ nạp bất kỳ đài XSMN nào khác theo cùng định dạng):

1. **Bộ thu thập & Chuẩn hóa Dữ liệu (`Data Ingestion & Canonical Schema`):**
   - Thu thập lịch sử mở thưởng 18 giải/kỳ của Đài TP.HCM (`XSHCM`, tối thiểu 3–5 năm gần nhất $\approx 300 \to 500$ kỳ quay, tương đương $5,400 \to 9,000$ giải) và lưu trữ thành file CSV/JSON sạch tại `data/`.
   - Xây dựng bộ trích xuất 3 nhóm đặc trưng chuẩn hóa cho Lồng Hàng Chục và Lồng Hàng Đơn Vị với cơ chế khóa thời gian `Pre-Draw Cutoff (t-1)`.
2. **Module Kiểm định Thống kê & Đối chứng Monte Carlo (`Statistical Falsification Engine`):**
   - Thực thi bộ kiểm định $\chi^2$, Shannon Entropy, Runs Test, Markov Transition Test và đối chứng với 1,000 chuỗi Monte Carlo Null.
3. **Mô hình Dự báo Xác suất Hiệu chuẩn (`Dual-Branch Dirichlet-BOCD & Regularized Markov Engine`):**
   - Xuất bảng xác suất hiệu chuẩn 10 quả bóng (`0`–`9`, bảo toàn $\sum P_i = 100\%$) tại mỗi kỳ quay kèm chỉ số độ tin cậy trạng thái (`Regime Conviction Score`).
4. **Khung Kiểm thử Trượt Điểm Ngọt (`Walk-Forward Portfolio Backtester & Dashboard Report`):**
   - Chạy Walk-Forward Backtest đối đầu giữa các cấu hình Điểm Ngọt (`2x2 = 4 số`, `3x3 = 9 số`, `Core 2x2 + Satellite 3x3`, `2x7 = 14 số`, `3x6 = 18 số`, `Negative Filter`) và xuất báo cáo kết quả thực nghiệm minh bạch phục vụ Giai đoạn 3.

---

## Not Doing (and Why)

- **Không dùng Mạng Nơ-ron Sâu (Deep Learning / LSTM / Transformer) nhiều tham số** — Vì 1 đài XSMN chỉ có 52–104 kỳ quay/năm, các mô hình Deep Learning hàng vạn tham số chắc chắn sẽ học thuộc lòng nhiễu quá khứ (*Overfitting*) và sập khi chạy ngoài mẫu.
- **Không tách thành 18 mô hình riêng biệt cho từng giải (từ Giải 8 đến Giải ĐB)** — Vì cả 18 giải trong cùng một buổi quay đều dùng chung một lồng cầu Hàng Chục và một lồng cầu Hàng Đơn Vị; tách nhỏ sẽ làm giảm cỡ mẫu đi 18 lần và làm tăng phương sai nhiễu lên $\sqrt{18} \approx 4.24$ lần.
- **Không cào dữ liệu và huấn luyện ồ ạt cả 21 đài Miền Nam ngay từ bước đầu** — Phải xây dựng, kiểm thử và chứng minh quy trình chuẩn hoàn chỉnh trên Đài mẫu (`XSHCM`) trước để tránh bẫy *"ngụy tạo đa giả thuyết"* (*Multiple Testing / Data Snooping*), sau đó mới nhân rộng sang các đài khác.
- **Không trộn lẫn các chiêu gấp thếp tiền cược (`Martingale`, `1-3-2-6`) vào đánh giá Giai đoạn 2** — Giai đoạn 2 phải đo lường **Alpha thuần túy của phương pháp chọn bóng** trên vốn chuẩn hóa (`Flat 1x` cho từng cấu hình Điểm Ngọt) trước khi bàn giao sang Giai đoạn 3 (Quản lý vốn Quỹ & Kelly Criterion).

---

## Open Questions (Resolved)

- [x] **Khung thời gian lịch sử (`5Y` & `3Y`):** Thu thập trọn vẹn **5 năm lịch sử gần nhất** và chạy đánh giá song song trên cả **Khung 5 năm (`5Y`)** lẫn **Khung 3 năm gần nhất (`3Y`)**.
- [x] **Đài mục tiêu (`XSHCM` & `XSVL`):** Triển khai đồng thời trên **Đài TP.HCM (`XSHCM` — 2 kỳ/tuần: ~520 kỳ 5Y / ~312 kỳ 3Y)** và **Đài Vĩnh Long (`XSVL` — 1 kỳ/tuần: ~260 kỳ 5Y / ~156 kỳ 3Y)** để đối chiếu trực tiếp giữa đài thành phố quay dày và đài tỉnh tiêu chuẩn.
