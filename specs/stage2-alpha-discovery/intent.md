# Statement of Intent — Giai Đoạn 2: Ứng Dụng AI & Thống Kê Vào Chọn Bóng Lồng Cầu (`Alpha Discovery & Backtesting`)

**Trạng thái:** Đã xác nhận (Confirmed - YES)
**Ngày cập nhật:** 2026-10-25
- **Tài liệu quy ước gốc (Single Source of Truth - Giai đoạn 1):**
  - `C:\sidehustle\XSTK\QUY_TAC_VA_DIEM_HOA_VON.md`
  - `C:\sidehustle\XSTK\BANG_NGHIEN_CUU_CHIEN_THUAT_XSMN.html`
- **Báo cáo trực quan hóa & Mô phỏng Phương án Giai đoạn 2:**
  - `C:\sidehustle\XSTK\BAO_CAO_PHUONG_AN_GIAI_DOAN_2_AI.html`
  - `C:\sidehustle\XSTK\specs\stage2-alpha-discovery\ideas.md`

---

## 1. Bản Đúc Kết Ý Định (Confirmed Statement of Intent)

- **Outcome (Đầu ra mục tiêu):** Xây dựng **Phương pháp luận nghiên cứu & Khung thực nghiệm AI cho Giai đoạn 2 (`Alpha Discovery & Backtesting`)** đối với bài toán **1 Lồng Cầu (`0`–`9`)** (áp dụng đồng nhất cho Lồng Hàng Chục và Lồng Hàng Đơn Vị trên 1 đài XSMN mẫu trước khi nhân rộng), bao gồm 4 trụ cột:
  1. **Tổ chức dữ liệu & Đặc trưng đầu vào (`Data Schema & Feature Engineering`):** Thiết kế cách thu thập, làm sạch và cấu trúc hóa lịch sử mở thưởng 18 giải/kỳ của đài XSMN thành chuỗi dữ liệu lồng cầu từ con số 0, xác định rõ các biến đầu vào (`input features`) cho mô hình.
  2. **Kiểm định thống kê (`Statistical Falsification`):** Thiết lập bộ công cụ kiểm định giả thuyết để chứng minh khách quan xem lồng cầu thực tế của đài có độ lệch/bất thường (`bias/anomaly`) so với mức lý tưởng 10%/số hay chỉ là nhiễu trắng ngẫu nhiên thuần túy.
  3. **Mô hình AI dự báo phân phối xác suất 10 quả bóng (`Calibrated Probability Estimation`):** Xây dựng mô hình AI xuất bảng độ tự tin hiệu chuẩn cho 10 quả bóng trước mỗi kỳ quay (ví dụ: `0: 6%, 7: 9%, 8: 11%...`, bảo toàn tổng xác suất $\sum_{i=0}^9 P_i = 100\%$).
  4. **Đo lường lợi thế theo Bộ số Điểm Ngọt (`Sweet-Spot Portfolio Backtesting`):** Kiểm thử thực nghiệm xem bảng xác suất của AI hội tụ lợi thế (`Alpha`) tốt nhất ở cấu hình bộ số nào (**Bộ $2\times2 = 4$ số**, **Bộ $3\times3 = 9$ số**, **Danh mục Core $2\times2$ + Satellite $3\times3$**, các điểm ngọt $2\times7=14$, $3\times6=18$..., hay loại trừ bóng chết) để cung cấp thông số thực tế cho Giai đoạn 3 (Quản lý vốn Quỹ).

- **User (Người sử dụng):** Chủ dự án — người thiết kế và vận hành hệ thống nghiên cứu định lượng XSMN theo lộ trình 3 giai đoạn.

- **Why now (Lý do thực hiện):**
  - **Giai đoạn 1 (`Break-Even Benchmark`)** đã hoàn tất tại `QUY_TAC_VA_DIEM_HOA_VON.md` và `BANG_NGHIEN_CUU_CHIEN_THUAT_XSMN.html`.
  - Theo **Định lý Phụ thuộc (Mục 8.3 - `QUY_TAC_VA_DIEM_HOA_VON.md`)**, cả Chiến thuật chọn quy mô bộ số $N = A \times B$ lẫn Quản lý vốn ở Giai đoạn 3 đều phụ thuộc tuyệt đối vào phân phối xác suất thực tế ($P_{\text{AI}}$) và kết quả Backtest của phương pháp chọn bóng ở Giai đoạn 2.

- **Success (Tiêu chí thành công):**
  1. Định hình được phương pháp luận và quy trình thực nghiệm rõ ràng để trả lời minh bạch trên dữ liệu thực XSMN: Lồng cầu của đài có vượt ngưỡng lệch chuẩn hòa vốn **`+6.90%`/lồng** ($\ge 10.69\%$/bóng, tương đương gộp 2 lồng đạt **$\ge +14.29\%$** hay xác suất mỗi số đạt $\ge \frac{1}{87.5} \approx 1.1429\%$) hay không.
  2. Đo lường chính xác các chỉ số thực nghiệm trên từng cấu hình bộ số (đặc biệt là **Bộ $2\times2 = 4$ số**, **Bộ $3\times3 = 9$ số**, **Core $2\times2$ + Satellite $3\times3$**):
     - Tổng số lô trúng trong chu kỳ 30 ngày / 540 giải (ví dụ: ở Bộ $2\times2 = 4$ số, vượt qua Điểm Hòa Vốn Tháng `24.69 lô` để đạt **$\ge 25$ lô/tháng**, tức bù thêm $\ge +3.1$ lô so với mức ngẫu nhiên `21.6 lô`).
     - Tỷ lệ ngày có lãi (`Daily Win Rate`), tần suất ngày nổ đa nháy ($\ge 2$ lô), và chuỗi thua tối đa (`Max Losing Streak` / `Max Drawdown`).

- **Constraint (Ràng buộc cốt lõi):**
  - Tuân thủ tuyệt đối hệ quy chiếu dòng tiền chuẩn hóa tại `QUY_TAC_VA_DIEM_HOA_VON.md`: Hệ số trả thưởng thực `1 : 87.5`; trong Bao lô 18 giải, mỗi 1 đồng vốn mua 1 số thu về $R_{\text{1 lô}} = \frac{87.5}{18} \approx \mathbf{4.8611 \text{ đồng}}$ trên mỗi lô trúng (tương đương nếu tính 18 đồng/số thì mỗi lô trúng thu 87.5 đồng).
  - Mỗi kỳ mở thưởng chọn một **Bộ $N = A \times B$ số** (ghép từ $A$ bóng Lồng Hàng Chục $\times$ $B$ bóng Lồng Hàng Đơn Vị) nằm sát dưới bậc thang hòa vốn $K \times 4.8611$.
  - Phương pháp luận và kiến trúc mô hình của **1 Lồng Cầu (`0`–`9`)** phải đồng nhất cho cả Lồng Hàng Chục và Lồng Hàng Đơn Vị, thiết kế chuẩn hóa trên 1 đài để có thể áp dụng cho mọi đài khác (ưu tiên **Đài TP.HCM - `XSHCM`** quay 2 kỳ/tuần làm đài thí điểm chuẩn đầu tiên vì mật độ dữ liệu gấp đôi đài tỉnh).
  - **Chống rò rỉ tương lai (`Pre-Draw Temporal Cutoff`):** Dự báo cho kỳ mở thưởng $t$ chỉ được phép dùng dữ liệu từ kỳ $t-1$ trở về trước (tuyệt đối không dùng các giải đầu của ngày $t$ để dự đoán các giải sau của ngày $t$ trong bài toán Bao Lô).
  - **Chống ngụy tạo Alpha trên cỡ mẫu nhỏ (`Anti-Overfitting & Regime Shift Safeguard`):** Bắt buộc đối chứng với phân phối giả lập ngẫu nhiên (`Monte Carlo Null Permutation`) và có cơ chế thích ứng khi nhà đài thay bộ bóng/bảo trì máy (`Online Changepoint Detection`).
  - Bắt đầu từ con số 0 về mặt dữ liệu (chưa có sẵn file dữ liệu sạch).

- **Out of scope (Ngoài phạm vi):**
  - Không tính toán lại các công thức Điểm Hòa Vốn đã chốt ở Giai đoạn 1.
  - Không tách thành 18 mô hình riêng biệt cho từng giải thưởng từ Giải 8 đến Giải ĐB.
  - Không sử dụng các phương pháp "soi cầu/bạc nhớ" cảm tính thiếu kiểm định thống kê hoặc các chiêu gấp thếp cờ bạc truyền thống (`1-3-2-6`, Martingale).
  - Chưa viết code cào dữ liệu và huấn luyện tràn lan toàn bộ 21 đài Miền Nam trước khi chốt xong phương pháp luận và kiểm chứng quy trình chuẩn trên 1 đài đại diện.
