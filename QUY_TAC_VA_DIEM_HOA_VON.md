# QUY TẮC CHUẨN HÓA DÒNG TIỀN, ĐIỂM HÒA VỐN & THIẾT LẬP BÀI TOÁN AI (XỔ SỐ MIỀN NAM)

Tài liệu này là **bản quy ước gốc (Single Source of Truth)** cho toàn bộ dự án phân tích và ứng dụng mô hình Toán học / AI vào bài toán Xổ số Miền Nam (XSMN). Mọi tính toán về vốn, lợi nhuận, điểm hòa vốn và hiệu quả mô hình về sau đều tuân thủ tuyệt đối các định nghĩa tại đây.

---

## 1. THỐNG NHẤT PHẠM VI & QUY ƯỚC CHUẨN HÓA DÒNG TIỀN

### 1.1. Phạm vi dữ liệu (Xổ số Miền Nam - XSMN)
* **Không gian mẫu:** 100 con số (từ `00` đến `99`), xét 2 chữ số cuối của các giải.
* **Cấu trúc 1 đài XSMN:** Gồm **18 giải (18 lô)** mở thưởng mỗi kỳ:
  * **Giải Đầu:** Giải Tám (chỉ có **1 giải**, gồm 2 chữ số).
  * **Giải Đuôi:** Giải Đặc Biệt (chỉ có **1 giải**, xét 2 chữ số cuối).
  * **Bao Lô:** Xét toàn bộ **18 giải** từ Giải Tám đến Giải Đặc Biệt.

### 1.2. Chuẩn hóa đơn vị tiền tệ ("1 Đồng Thực")
Trong thực tế, nhà cái quy định *"1 ăn 70, chỉ thu 0.8"*. Tuy nhiên, để loại bỏ hoàn toàn sự nhầm lẫn giữa "tiền xác" và "tiền cò", chúng ta thống nhất quy đổi toàn bộ về **Dòng tiền thực tế (Cash-in / Cash-out)**:

> **Quy ước gốc:**
> * **1 đơn vị vốn (`1 đồng`)** = Số tiền thực tế chúng ta phải rút ví đưa cho nhà cái.
> * Không sử dụng khái niệm "tiền xác 0.8" trong báo cáo lãi/lỗ nữa, mà quy đổi trực tiếp sang **Tỷ lệ nhận lại thực tế trên mỗi 1 đồng vốn bỏ ra**.

Cụ thể, với tỷ lệ gốc (đưa $0.8$ nhận lại $70$):
$$\text{Hệ số trả thưởng thực tế (Real Payout)} = \frac{70}{0.8} = \mathbf{87.5 \text{ lần}}$$

*(Ghi chú: Nếu sau này làm việc với nhà cái có tỷ lệ khác, ví dụ 1 ăn 75 thu 0.8 $\rightarrow$ Hệ số thực là $75 / 0.8 = 93.75$, ta chỉ cần thay hằng số `87.5` này).*

---

## 2. BÀI TOÁN 1: ĐÁNH ĐẦU HOẶC ĐUÔI (BÀI TOÁN 1 GIẢI ĐƠN LẺ)

*(Phân tích cho 1 giải cố định, ví dụ chỉ đánh **Đuôi - Giải ĐB** hoặc chỉ đánh **Đầu - Giải 8**. Đánh cả "Đầu - Đuôi" thực chất là thực hiện 2 bài toán đơn lẻ này cùng lúc).*

### 2.1. Quy tắc dòng tiền
* **Chi phí mua 1 con số:** `1 đồng`.
* **Chi phí mua một dàn $N$ con số khác nhau ($1 \le N \le 100$):** `N đồng`.
* **Số tiền nhận lại khi trúng (có đúng 1 con số trong dàn $N$ số trùng với kết quả):** **`87.5 đồng`**.
* **Lợi nhuận ròng trong kỳ nếu trúng:** $87.5 - N \text{ (đồng)}$.

### 2.2. Điểm hòa vốn ($N_{\text{BE}}$ - Break-Even Point)
Giả sử mô hình AI chọn ra một tập hợp gồm $N$ con số sao cho kết quả mở thưởng **chắc chắn nằm trong tập $N$ số này (tỷ lệ thắng 100%)**:

$$\text{Điểm hòa vốn } N_{\text{BE}} = \mathbf{87.5 \text{ con số}}$$

* **Ý nghĩa thực chiến:**
  * Thay vì lầm tưởng chỉ được mua tối đa 70 số như tên gọi "1 ăn 70", trên thực tế **chúng ta được phép mua tối đa tới `87 con số`**.
  * Nếu mua **87 số** (tốn `87 đồng`) và trúng 100%, ta thu về `87.5 đồng` $\rightarrow$ **Lãi ròng `+0.5 đồng`/kỳ** (Tỷ suất sinh lời $ROI = \frac{0.5}{87} \approx +0.57\%$/ngày).
  * Nếu mô hình không đạt độ chính xác 100% ở mọi ngày mà đạt **Tỷ lệ ngày thắng là $P_{\text{win}}$** khi đánh dàn $N$ số, điều kiện để hòa vốn dài hạn là:
    $$P_{\text{win}} \ge \frac{N}{87.5}$$
    *(Ví dụ: Đánh dàn $N = 50$ số $\rightarrow$ Cần thắng tối thiểu $\frac{50}{87.5} = \mathbf{57.14\%}$ số kỳ mở thưởng).*

---

## 3. BÀI TOÁN 2: ĐÁNH BAO LÔ (BÀI TOÁN 18 GIẢI)

### 3.1. Quy tắc dòng tiền
Khi đánh Bao Lô, tiền cược cho 1 con số phải chia đều để mua cả 18 giải.
* Trong thực tế: 1k xác $\times 18$ giải $\times 0.8 = 14.4\text{k}$ thực trả; trúng 1 nháy nhận $70\text{k}$.
* **Chuẩn hóa về `1 đồng` thực tế bỏ ra cho 1 con số Bao Lô:**
  * **Chi phí mua 1 con số Bao Lô:** `1 đồng` (tương đương $\frac{1}{18}$ đồng cho mỗi giải).
  * **Số tiền nhận lại cho MỖI 1 NHÁY (1 lần xuất hiện trong 18 giải):**
    $$R_{\text{1 nháy}} = \frac{70}{14.4} = \frac{87.5}{18} = \frac{175}{36} \approx \mathbf{4.8611 \text{ đồng}}$$
  * Nếu con số đó (hoặc dàn số đó) xuất hiện tổng cộng **$K$ nháy** trong 18 giải ($0 \le K \le 18$), tổng tiền nhận lại là:
    $$\text{Tổng thu về} = K \times \frac{87.5}{18} \approx K \times \mathbf{4.8611 \text{ đồng}}$$

### 3.2. Điểm hòa vốn ($N_{\text{BE}}$) của Bao Lô
Khác với Đầu/Đuôi (chỉ trúng tối đa 1 lần), Bao Lô có tới **18 giải** nên điểm hòa vốn phụ thuộc vào **số nháy trúng được ($K$)**:

$$\text{Điều kiện hòa vốn: } N \le K \times \frac{87.5}{18} \approx K \times 4.8611$$

Bảng tra cứu điểm hòa vốn theo số lượng số mua ($N$) và số nháy trúng ($K$):

| Số nháy trúng tối thiểu kỳ vọng ($K$) | Số tiền thu về ($K \times 4.8611$) | Điểm hòa vốn lý thuyết ($N_{\text{BE}}$) | Số lượng con số tối đa được mua để CÓ LÃI ($N_{\max}$) |
| :---: | :---: | :---: | :---: |
| **Trúng 1 nháy ($K = 1$)** | `4.8611 đồng` | `4.86 số` | **Tối đa 4 con số** (Tốn 4 đồng, thu 4.86 đồng $\rightarrow$ Lãi +0.86 đồng) |
| **Trúng 2 nháy ($K = 2$)** | `9.7222 đồng` | `9.72 số` | **Tối đa 9 con số** (Tốn 9 đồng, thu 9.72 đồng $\rightarrow$ Lãi +0.72 đồng) |
| **Trúng 3 nháy ($K = 3$)** | `14.5833 đồng` | `14.58 số` | **Tối đa 14 con số** (Tốn 14 đồng, thu 14.58 đồng $\rightarrow$ Lãi +0.58 đồng) |
| **...** | ... | ... | ... |
| **Bao trọn cả 18 giải ($K = 18$)** | `87.5000 đồng` | `87.50 số` | **Tối đa 87 con số** *(Với điều kiện cả 18 giải đều nằm trong 87 số này)* |

---

## 4. SO SÁNH CHIẾN LƯỢC: BÀI TOÁN NÀO CHÚNG TA CÓ LỢI THẾ HƠN?

Về mặt toán học cơ bản, nhà cái thiết kế cả 2 trò chơi với **cùng một biên lợi nhuận (House Edge = 12.5%, Tỷ lệ trả thưởng kỳ vọng = 87.5%)**. Nghĩa là nếu chọn số ngẫu nhiên, cứ bỏ ra `1 đồng` thì kỳ vọng thu về đúng `0.875 đồng` ở cả 2 cách chơi.

Tuy nhiên, khi **thiết lập bài toán cho AI / Mô hình xác suất**, hai cách chơi này có bản chất hoàn toàn trái ngược nhau. Lợi thế thuộc về bài toán nào phụ thuộc vào **Chiến thuật dự đoán** mà chúng ta chọn:

### Chiến thuật A: Chiến thuật "Mũi nhọn" (Chọn Top 1 đến 4 con số có xác suất cao nhất) $\rightarrow$ **BAO LÔ THẮNG ÁP ĐẢO**

Nếu mô hình AI được huấn luyện để tìm ra một nhóm nhỏ các con số sáng giá nhất mỗi ngày ($N$ từ `1` đến `4` số):
1. **Dữ liệu huấn luyện (Signal-to-Noise) lớn gấp 18 lần:**
   * Đánh Đuôi (Giải ĐB) mỗi ngày chỉ có 1 điểm dữ liệu. Một con số trung bình 100 ngày mới về ĐB 1 lần $\rightarrow$ Dữ liệu quá thưa (sparse), nhiễu cực lớn.
   * Bao Lô mỗi ngày có **18 điểm dữ liệu**. Trung bình 5–6 ngày một con số lại xuất hiện trong lô. Các đặc trưng chuỗi thời gian (nhịp lô, chu kỳ lô gan, tần suất rơi lại, xác suất có điều kiện giữa các giải) rõ ràng và ổn định hơn rất nhiều để AI học.
2. **Xác suất vượt điểm hòa vốn trong ngày cực cao:**
   * Giả sử AI chọn ra **$N = 4$ con số** (Tổng chi phí = `4 đồng`).
   * Để có lãi, ta chỉ cần **ít nhất 1 nháy** xuất hiện trong 18 giải (thu về `4.8611 đồng` > `4 đồng`).
   * Ngay cả khi chọn ngẫu nhiên (chưa có AI), xác suất 4 con số nổ ít nhất 1 nháy trong 18 giải đã là:
     $$P(\text{Trúng} \ge 1 \text{ nháy}) = 1 - \left(\frac{96}{100}\right)^{18} \approx \mathbf{52.04\%}$$
   * Cộng thêm khả năng nổ **2 nháy** (`9.72 đồng`), **3 nháy** (`14.58 đồng`), mô hình AI chỉ cần nhích nhẹ độ chính xác lên trên mức ngẫu nhiên khoảng $6\% - 7\%$ là dòng tiền tăng trưởng rất đều và ít bị chuỗi thua dài (low drawdown).

### Chiến thuật B: Chiến thuật "Loại trừ / Vét cạn" (Mua dàn rộng để thắng gần 100%) $\rightarrow$ **ĐẦU / ĐUÔI (1 GIẢI) THẮNG ÁP ĐẢO**

Nếu bạn muốn đi theo hướng bạn đề cập trong câu hỏi: *"Tìm phương pháp mua một lượng lớn con số (ví dụ 70 - 87 số) để tỷ lệ thắng tiệm cận 100%"*:
1. **Tại sao KHÔNG THỂ dùng chiến thuật mua 87 số cho Bao Lô?**
   * Để thu về đủ `87.5 đồng` trong Bao Lô, bạn phải trúng **trọn vẹn cả 18 nháy** ($K = 18$).
   * Giả sử bạn dùng AI loại bỏ 13 con số xấu nhất, và mua **87 con số** còn lại. Vì có tới 18 giải quay độc lập, xác suất để **cả 18 giải** đều không rơi vào 13 con số bị loại kia chỉ là:
     $$(0.87)^{18} \approx \mathbf{8.16\%}$$
   * Hầu hết các ngày, trong 18 giải sẽ có 1–3 giải rơi vào 13 số bạn đã loại, khiến bạn chỉ trúng 15–17 nháy (thu về $72.9 \to 82.6$ đồng), dẫn đến **lỗ vốn** so với 87 đồng bỏ ra!
2. **Tại sao Đánh Đuôi (hoặc Đầu - 1 giải) lại tối ưu cho chiến thuật "Loại trừ"?**
   * Khi chỉ đánh **1 giải duy nhất** (ví dụ Giải Đặc Biệt): Chỉ có **1 kết quả duy nhất** cần né 13 con số bị loại.
   * Nếu AI được thiết kế như một **Bộ lọc loại trừ (Negative Filter)**: Thay vì đoán con số nào sẽ ra (rất khó, xác suất 1%), AI chỉ cần tìm ra **13 đến 20 con số CÓ XÁC SUẤT RA THẤP NHẤT** trong ngày hôm đó để loại bỏ, và ta mua toàn bộ $80 \to 87$ con số còn lại.
   * Xác suất thắng tự nhiên mỗi ngày đã là **80% – 87%**, và mỗi ngày thắng đều thu trọn vẹn **`87.5 đồng`**!

---

## 5. MA TRẬN TƯƠNG QUAN BỘ SỐ ($N$) vs SỐ LÔ TRÚNG ($K$) & BÀI TOÁN 2 LỒNG CẦU

### 5.1. Bản chất vật lý 2 Lồng Cầu (Hàng Chục $\times$ Hàng Đơn Vị)
Trong XSMN, 2 chữ số cuối của mọi giải đều được tạo thành từ **2 lồng cầu độc lập**:
* **Lồng Hàng Chục:** 10 quả bóng (`0`–`9`).
* **Lồng Hàng Đơn Vị:** 10 quả bóng (`0`–`9`).

Khi phân tích dữ liệu lịch sử của từng đài để tìm **điểm bất thường (anomaly/bias)**:
* Nếu ta chọn ra $A$ quả bóng có tần suất cao bất thường ở Lồng Hàng Chục và $B$ quả bóng ở Lồng Hàng Đơn Vị, ta sẽ ghép được một **Bộ số gồm $N = A \times B$ con số**.
* **Hiệu ứng lãi kép xác suất của 2 lồng cầu:** Giả sử mỗi lồng cầu chỉ cần có độ lệch $+10\%$ so với ngẫu nhiên ($\times 1.10$), thì xác suất xuất hiện của bộ số ghép $N = A \times B$ sẽ tăng lên:
  $$1.10 \times 1.10 = \mathbf{1.21 \text{ lần}} \quad (\text{tức } +21\%, \text{ vượt qua rào cản hòa vốn } +14.29\% \text{ của nhà cái!})$$

### 5.2. Quy đổi cảm giác "Bao lô không cố định vị trí & không giới hạn số lô" thành TIỀN
Tại sao khi đánh một **Bộ $N$ số** dựa trên sự bất thường của lồng cầu, **Bao Lô** lại có lợi thế vượt trội so với **Đầu - Đuôi**?

1. **Lồng cầu không phân biệt giải:** Trong một buổi quay, 2 lồng cầu Hàng Chục và Hàng Đơn Vị quay tổng cộng **18 lần**. Sự bất thường vật lý (nếu có) sẽ phân bổ trên cả 18 lần quay đó, chứ không chỉ xuất hiện ở đúng lần quay Giải 8 (Đầu) hay Giải ĐB (Đuôi).
2. **Định lượng bằng con số (Khi cùng bỏ ra vốn `N đồng` cho bộ $N$ số):**
   * **Độ biến động rủi ro (Standard Deviation) giảm $\sqrt{18} \approx \mathbf{4.24 \text{ lần}}$:**
     $$\sigma_{\text{Bao Lô}} = \frac{\sigma_{\text{Đuôi}}}{\sqrt{18}} \approx \frac{\sigma_{\text{Đuôi}}}{4.24}$$
     *(Phương sai rủi ro dòng tiền giảm đi đúng **18 lần**).*
   * **Cơ chế "Thu hồi vốn từng phần" (Partial Recovery) chống cháy tài khoản:**
     * Ở **Đầu/Đuôi (1 giải)**: Là trò chơi "Được ăn cả, ngã về không" (Nhị phân $0$ hoặc $87.5$ đồng). Nếu lần quay Giải ĐB trượt khỏi bộ $N$ số $\rightarrow$ **Mất trắng 100% vốn (`0 đồng`)**.
     * Ở **Bao Lô (18 giải)**: Mỗi lần lồng cầu rơi vào bộ $N$ số (dù là cùng 1 số nổ lặp lại hay nhiều số khác nhau trong bộ cùng nổ), bạn đều được cộng **`4.8611 đồng`**. Ngay cả trong ngày chưa đạt đủ số lô hòa vốn, các lô trúng lẻ vẫn giúp **thu hồi $35\% \to 80\%$ vốn**, giảm xác suất mất trắng về gần `0%`.

### 5.3. Bảng Ma Trận Điểm Ngọt (Sweet Spots): Tương quan giữa Bộ số ($N$) và Số lô cần trúng ($K$)
Vì số lô trúng $K$ phải là **số nguyên** ($1, 2, 3, \dots$) và mỗi lô trả **`4.8611 đồng`**, nên khi chọn quy mô bộ số $N$, ta **BẮT BUỘC phải chọn $N$ nằm sát dưới ngưỡng $K \times 4.8611$** để không lãng phí hạn mức số được mua:

| Số lô cần trúng để có lãi ($K$) | Tiền thu về khi đạt $K$ lô | Điểm hòa vốn ($N_{\text{BE}}$) | Số lượng số tối đa nên đánh ($N_{\max}$) | Cách ghép 2 Lồng Cầu tối ưu ($A \text{ chục} \times B \text{ đơn vị}$) | Xác suất đạt $\ge K$ lô (Ngẫu nhiên) | Xác suất đạt $\ge K$ lô (Khi 2 lồng lệch +10%) | Xác suất mất trắng 100% vốn ($K=0$) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$K = 1$ lô** | `4.86 đồng` | `4.86 số` | **`4 số`** | **$2 \times 2 = 4$ số** | `52.04%` | **`59.1%`** | `41.3%` |
| **$K = 2$ lô** | `9.72 đồng` | `9.72 số` | **`9 số`** | **$3 \times 3 = 9$ số** | `49.09%` | **`59.8%`** | `12.8%` |
| **$K = 3$ lô** | `14.58 đồng` | `14.58 số` | **`14 số`** | **$2 \times 7 = 14$ số** | `47.13%` | **`60.9%`** | `3.6%` |
| **$K = 4$ lô** | `19.44 đồng` | `19.44 số` | **`18 - 19 số`** | **$3 \times 6 = 18$ số** | `45.54%` | **`62.1%`** | `0.9%` |
| **$K = 5$ lô** | `24.31 đồng` | `24.31 số` | **`24 số`** | **$4 \times 6 = 24$ số** | `44.14%` | **`63.5%`** | `0.2%` |
| **$K = 6$ lô** | `29.17 đồng` | `29.17 số` | **`28 - 29 số`** | **$4 \times 7 = 28$ số** | `42.81%` | **`64.8%`** | `0.04%` |
| **$K = 8$ lô** | `38.89 đồng` | `38.89 số` | **`36 - 38 số`** | **$6 \times 6 = 36$ số** | `36.81%` | **`69.8%`** | `0.00%` |
| **$K = 9$ lô** | `43.75 đồng` | `43.75 số` | **`42 - 43 số`** | **$6 \times 7 = 42$ số** | `35.56%` | **`72.3%`** | `0.00%` |
| **$K = 10$ lô** | `48.61 đồng` | `48.61 số` | **`48 số`** | **$6 \times 8 = 48$ số** | `34.21%` | **`75.1%`** | `0.00%` |

> **Quy tắc vàng khi chọn kích thước bộ số $N$ trong Bao Lô:**
> Tuyệt đối tránh các con số "lửng lơ" ngay trên bậc thang hòa vốn!
> * Ví dụ: Đánh **9 số** ($3 \times 3$) chỉ cần trúng **2 lô** là thu `9.72 đồng` (**Lãi `+0.72 đồng`**).
> * Nhưng nếu đánh **10 số** ($2 \times 5$), khi trúng **2 lô** vẫn chỉ thu `9.72 đồng` (**Lỗ `-0.28 đồng`**), bắt buộc phải trúng tới **3 lô** mới có lãi!
> * Do đó, các cấu hình bộ số chuẩn tối ưu nhất cho Bao Lô là: **`4 số` ($2\times2$), `9 số` ($3\times3$), `14 số` ($2\times7$), `18 số` ($3\times6$), `24 số` ($4\times6$), `28 số` ($4\times7$), `48 số` ($6\times8$)**.

---

## 6. BÀI TOÁN KINH DOANH 30 NGÀY: PHÂN BIỆT "TỶ LỆ NGÀY THẮNG" VS "LỢI NHUẬN CUỐI THÁNG" & QUẢN LÝ VỐN QUỸ ĐẦU TƯ

### 6.1. Thống nhất 2 Định nghĩa Cốt lõi (Tránh nhầm lẫn)
Khi vận hành liên tục 30 ngày/tháng (tương đương $30 \times 18 = \mathbf{540 \text{ giải mở thưởng}}$), ta phải tách bạch 2 chỉ số:

1. **Tỷ lệ Ngày Thắng (`Daily Win Rate`):**
   * Là tỷ lệ % số ngày trong tháng mà `Tiền thu về trong ngày > Tiền vốn bỏ ra trong ngày`.
   * Với **Bộ $2\times2 = 4$ số** (vốn `4 đồng`/ngày): Chỉ cần nổ $\ge 1$ lô là thu `4.8611 đồng` (lãi `+0.8611 đồng`, tức **`+21.53%`/ngày**).
   * Ngay cả khi đánh ngẫu nhiên hoàn toàn, tỷ lệ ngày thắng của Bộ 4 số đã là **$52.04\%$** (~15.6 ngày thắng / 30 ngày). Khi 2 lồng cầu có độ lệch $+10\%$ mỗi lồng, tỷ lệ ngày thắng lên tới **$59.06\%$** (~18 ngày thắng / 30 ngày).

2. **Điểm Hòa Vốn Tháng (`Monthly Break-Even Target`):**
   * **Tại sao đánh ngẫu nhiên thắng 52.04% số ngày nhưng cuối tháng vẫn lỗ?**
     Vì sự bất đối xứng giữa ngày thắng 1 lô (chỉ lãi `+0.86 đồng`) và ngày thua trắng $K=0$ (mất `-4.00 đồng`).
   * Để **Cuối tháng có Lợi Nhuận Dương (khi đi vốn đều `Flat Betting`)**, tổng số lô trúng trong cả 30 ngày ($K_{\text{tháng}}$) phải vượt qua ngưỡng:
     $$K_{\text{tháng}} \ge \frac{30 \times N}{4.8611}$$
   * Cụ thể với **Bộ $2\times2 = 4$ số** (Tổng vốn 30 ngày = `120 đồng`):
     * Ngẫu nhiên 30 ngày nổ: $540 \times 4\% = \mathbf{21.60 \text{ lô}}$ (Thu `105 đồng` $\rightarrow$ Lỗ `-15 đồng`).
     * Điểm Hòa Vốn Tháng: $\frac{120}{4.8611} = \mathbf{24.69 \text{ lô}}$ $\rightarrow$ **Từ `25 lô / tháng` trở lên là CÓ LÃI DƯƠNG!**
     * **Khoảng cách cần thuật toán bù đắp:** Chỉ cần trúng nhiều hơn ngẫu nhiên **`+3.1 lô` trong cả 1 tháng 30 ngày** (tức trung bình cứ 10 ngày mới cần thuật toán giúp nổ thêm 1 lô!).

### 6.2. Tại sao Cấu hình Nhỏ (`2x2 = 4 số` & `3x3 = 9 số`) giảm Áp lực Tính toán nhiều nhất?
Theo **Định luật Bảo toàn Tổng Xác Suất trong Lồng cầu ($\sum_{i=0}^9 P_i = 100\%$):**
* Mỗi lồng cầu chỉ có đúng 10 quả bóng (`0`–`9`). Khi có sự bất thường vật lý, lợi thế xác suất chỉ **tập trung đậm đặc ở Top 2 hoặc Top 3 quả bóng đứng đầu** mỗi lồng cầu.
* Nếu chọn bộ số quá lớn (như $6\times6 = 36$ số hay $6\times8 = 48$ số), ta buộc phải lấy tới 6–8 quả bóng trong 10 quả, dẫn đến việc gom cả những quả bóng có xác suất thấp vào giỏ, làm **pha loãng (dilute)** lợi thế về lại mức trung bình ngẫu nhiên!
* Do đó, **Bộ $2\times2 = 4$ số** và **Bộ $3\times3 = 9$ số** là 2 cấu trúc giúp giảm áp lực tính toán nhiều nhất: chỉ cần tìm đúng 2–3 quả bóng bất thường nhất ở mỗi lồng cầu.

### 6.3. Ba Chiến lược Quản lý Vốn Quỹ Đầu Tư (Fund Management) cho Chu kỳ 30 Ngày
1. **Cấu trúc Danh mục "Core $2\times2$ + Satellite $3\times3$" (Vốn `6.5 đồng`/ngày):**
   * Chọn 3 bóng chục $\times$ 3 bóng đơn vị = 9 số, nhưng phân bổ vốn bất đối xứng:
     * **Nhóm Lõi $2\times2$ (4 số mạnh nhất):** Đặt `1.0 đồng`/số (`4.0 đồng`). Nổ 1 lô thu `4.86 đồng`.
     * **Nhóm Vệ tinh bảo hiểm (5 số còn lại):** Đặt `0.5 đồng`/số (`2.5 đồng`). Nổ 1 lô thu `2.43 đồng` (hoàn trả chi phí bảo hiểm).
   * Kết hợp được biên lãi cao của Bộ $2\times2$ với lưới an toàn chống trắng bảng của Bộ $3\times3$ (giảm tỷ lệ ngày $K=0$ từ $48\%$ xuống chỉ còn $12\% - 18\%$).
2. **Đi vốn theo Độ mạnh Tín hiệu (`Conviction Sizing`):**
   * Ngày tín hiệu tiêu chuẩn (~20 ngày/tháng): Đi vốn cơ sở `1.0x`.
   * Ngày tín hiệu hội tụ đỉnh (~10 ngày/tháng khi độ lệch lồng cầu rõ nhất): Đi vốn `2.0x`.
3. **Bậc thang Bù lỗ Mềm & Khóa lãi (`Soft Recovery 1.0x - 1.4x - 1.8x` & `Profit Lock`):**
   * Không bao giờ gấp thếp nhân đôi (Martingale). Chỉ tăng nhẹ `1.0x -> 1.4x -> 1.8x` (khóa trần `2.2x`) sau ngày trắng bảng.
   * Tận dụng các ngày nổ **$\ge 2$ lô** (xảy ra 5–7 lần/tháng ở bộ $2\times2$) để một ngày thắng lớn xóa sạch lỗ của 2–3 ngày trước và khóa lợi nhuận dương cuối tháng.

---

## 7. CẢNH BÁO TÀI CHÍNH: TẠI SAO KHÔNG DÙNG CHIÊU "1 - 3 - 2 - 6" TRONG BAO LÔ?

Trong giới cờ bạc truyền thống (Baccarat / Tài Xỉu), nhiều người truyền tai nhau công thức **`1 - 3 - 2 - 6`** (Thắng nâng cược theo nấc $1 \to 3 \to 2 \to 6$, thua ở bất kỳ nấc nào thì quay về $1$). Tuy nhiên, dưới góc độ Toán học Quỹ đầu tư, công thức này có **2 tử huyệt chí mạng**:

### 7.1. Tử huyệt 1: Bẫy "Thắng - Thua xen kẽ" (`W - L - W - L`) tự động rút ruột vốn
* Ngay cả trong trò chơi "1 ăn 1" (đặt 1 thắng lãi +1), khi bạn thắng ở Bậc 1 (`+1 đồng`) rồi nâng lên Bậc 2 (`3 đồng`) và bị thua (`-3 đồng`), kết quả của cặp **1 Thắng - 1 Thua (`W - L`) là LỖ RÒNG `-2 đồng`** (trong khi đi tiền đều `1 - 1` thì hòa vốn `0 đồng`).
* Thậm chí nếu thắng 3 bậc đầu (`+1 + 3 + 2 = +6 đồng`) rồi thua ở Bậc 4 (`-6 đồng`), chuỗi **3 Thắng - 1 Thua (`W - W - W - L`) vẫn về mo (`0 đồng`)**!
* Người chơi chỉ thực sự có lãi lớn nếu ăn thông cả 4 ván liên tiếp (`W - W - W - W`), vốn chỉ có xác suất $\frac{1}{16} = \mathbf{6.25\%}$. Trong 93.75% thời gian còn lại, khi thị trường đi ngang (Thắng - Thua đan xen), tài khoản bị bào mòn cực nhanh.

### 7.2. Tử huyệt 2: Lệch pha Tỷ lệ Lãi/Vốn khi áp vào Bao Lô (Thảm họa nhân 3 vốn)
* Ở trò "1 ăn 1", thắng Bậc 1 bạn lãi `+100%` vốn (`+1 đồng`), nên lên Bậc 2 (`3 đồng`) thực chất chỉ bỏ thêm `1 đồng` tiền túi.
* **Nhưng ở Bao Lô (Bộ $2\times2 = 4$ số, vốn gốc `4.00 đồng`/ngày):**
  * Ngày 1 (Mức `1x` = `4.00 đồng`) trúng 1 lô chỉ thu `4.86 đồng` $\rightarrow$ **Lãi ròng chỉ là `+0.86 đồng` (`+21.5%` vốn)**.
  * Nếu Ngày 2 máy móc nhân 3 lên Mức `3x` (Vốn = **`12.00 đồng`**) và bị trượt ($K=0$): Bạn mất **`-12.00 đồng`**.
  * **Tổng kết sau 1 ngày Thắng + 1 ngày Thua (`W - L`):** $+0.86 - 12.00 = \mathbf{-11.14 \text{ đồng}}$ (mất sạch thành quả của **13 ngày thắng cộng lại**!).
  * Nếu thắng 3 ngày liên tiếp (mỗi ngày 1 lô ở mức `1x, 3x, 2x` gom được `+5.17 đồng` lãi), rồi thua ở Ngày thứ 4 (mức `6x` = `-24.00 đồng`): Tổng kết 3 Thắng - 1 Thua bị **LỖ NẶNG `-18.83 đồng`**!

### 7.3. Giải pháp thay thế chuẩn Quỹ Đầu Tư: "Tái đầu tư từ Quỹ Lãi Ròng" (`House-Money Compounding`)
Nếu muốn áp dụng triết lý *"Thắng mới nâng vốn, Thua giữ nguyên `1.0x`"*, Quỹ đầu tư tuân thủ quy tắc:
* **Không bao giờ nâng vốn vượt quá 50% số tiền Lãi Ròng thực tế đã cất vào két (`Profit Buffer`).**
* Ngày trúng 1 lô (lãi `+0.86đ`): Cất vào Quỹ Lãi, ngày hôm sau **vẫn đánh `1.0x` (`4.00đ`)**.
* Chỉ khi gặp ngày nổ **$\ge 2$ lô** (lãi ròng `+5.72đ`) hoặc Quỹ Lãi đã gom đủ $\ge 4.00\text{đ}$: Ngày hôm sau mới trích 50% Quỹ Lãi (`+2.00đ`) để đánh mức **`1.5x` (`6.00đ`)**. Dù ngày hôm sau có thua trắng (`-6.00đ`), tổng kết 2 ngày vẫn hòa vốn (`+5.72 - 6.00 = -0.28đ`), miễn nhiễm hoàn toàn với bẫy Thắng - Thua xen kẽ!

---

## 8. ĐỊNH DANH CHUYÊN NGÀNH CỦA BÀI TOÁN & LỘ TRÌNH 3 GIAI ĐOẠN (CHỐT QUY TRÌNH)

### 8.1. Tên gọi chuyên ngành của bài toán chúng ta đang tham gia
Khác với trò chơi tỉ lệ `1:1` (như Tung đồng xu / Tài Xỉu / Baccarat) vốn được gọi là **Bài toán Nhị phân Đối xứng (`Symmetric Binary Bernoulli Trial`)**, bài toán Số đề / Bao lô XSMN thuộc 2 phân lớp phức tạp hơn trong Toán Tài Chính:

1. **Đánh Đầu / Đuôi (1 giải):**
   * **Tên chuyên ngành:** **Bài toán Nhị phân Bất đối xứng Cực đoan (`Highly Skewed / Asymmetric Binary Payoff` — tương đương `Deep Out-of-the-Money Binary Option`)**.
   * **Đặc trưng:** Chỉ có 1 phép thử ($n=1$), xác suất trúng $p$ nhỏ nhưng tỷ lệ trả thưởng khi trúng rất lớn (`87.5 lần`), đầu ra chỉ có 2 trạng thái: Mất `-100%` vốn hoặc Nhận `87.5 đồng`.
2. **Đánh Bao Lô (18 giải với một Bộ $N$ số):**
   * **Tên chuyên ngành:** **Bài toán Tổ hợp Đa phép thử Nhị thức có Trả thưởng Tuyến tính & Lệch phải (`Multi-Trial Binomial Portfolio with Linear Payoff & Positive Right-Skewness` — tương đương `Multi-Event Options Basket`)**.
   * **3 Đặc trưng cốt lõi:**
     * **Đa phép thử ($n = 18$ trials/kỳ):** Mỗi ngày có 18 lần quay độc lập của 2 lồng cầu.
     * **Đầu ra Đa mức rời rạc ($K \in \{0, 1, 2, \dots, 18\}$):** Không phải Thắng/Thua nhị phân, mà có 4 vùng kết quả: (1) Mất trắng khi $K=0$; (2) **Thu hồi vốn một phần (`Partial Recovery`)** khi $0 < K < K_{\text{BE}}$; (3) Thắng tiêu chuẩn khi $K = K_{\text{BE}}$; và (4) **Thắng đột biến (`Multi-hit Fat Tail`)** khi $K > K_{\text{BE}}$.
     * **Độ lệch dương (`Positive Skewness`):** Rủi ro lỗ tối đa bị chặn dưới ở `-100% vốn ngày`, nhưng lợi nhuận ngày mở rộng lên `+100%`, `+200%`, `+300%` khi nổ nhiều lô.

### 8.2. Phương pháp Quản lý vốn chuyên ngành cho bài toán này
Trong Tài chính Định lượng, với bài toán **Multi-Trial Binomial / Multi-Outcome**, phương pháp quản lý vốn chuẩn mực được sử dụng là:
* **Tiêu chuẩn Kelly Đa Kết Quả (`Generalized Multi-Outcome Kelly Criterion` / `Fractional Kelly`):**
  Tìm tỷ trọng vốn $f^*$ tối ưu trích từ Tổng Quỹ (`Bankroll`) bằng cách cực đại hóa kỳ vọng hàm Logarit của tài sản qua cả 19 trạng thái ($K = 0 \dots 18$):
  $$\max_{f} \ \sum_{k=0}^{18} P_{\text{AI}}(K = k) \cdot \ln\left(1 + f \cdot \left(\frac{k \times 4.8611 - N}{N}\right)\right)$$
* **Định cỡ vị thế theo Độ tin cậy & Biến động (`Conviction & Volatility-Adjusted Position Sizing`):** Quy mô tiền cược mỗi ngày là một hàm số phụ thuộc trực tiếp vào **Độ lệch xác suất ($p_{\text{AI}}$) của ngày hôm đó**.

### 8.3. Định lý Phụ thuộc & Lộ trình 3 Giai đoạn Chuẩn Định Lượng
> **Nguyên lý cốt lõi (Chốt thống nhất):**
> Cả **Chiến thuật chơi** (chọn bộ bao nhiêu số $N$, đánh Bao Lô hay Đuôi) lẫn **Quản lý vốn** (đi tiền bao nhiêu %) đều **PHỤ THUỘC TUYỆT ĐỐI vào Tỷ lệ trúng và Phân phối xác suất thực tế ($P_{\text{AI}}$) của phương pháp chọn số!**
> Nếu chưa có kết quả kiểm định (Backtest) từ phương pháp chọn số của AI, mọi thiết kế bộ số hay công thức đi tiền chỉ là giả định trên giấy.

Do đó, dự án tuân thủ nghiêm ngặt **Lộ trình 3 Giai đoạn**:
1. **Giai đoạn 1 — Xác định Điểm Hòa Vốn (`Break-Even Benchmark`) [ĐÃ HOÀN THÀNH]:**
   * Mốc Hòa Vốn chuẩn cho mọi phương pháp chọn số: Xác suất trúng thực tế trên mỗi con số (hoặc mỗi lần quay lồng cầu) phải đạt tối thiểu **$\frac{1}{87.5} \approx \mathbf{1.1429\%}$** (tức **tốt hơn ngẫu nhiên tối thiểu $+14.29\%$**, tương ứng trung bình **$\ge 0.2057$ lô / 1 số Bao Lô / ngày**).
2. **Giai đoạn 2 — Ứng dụng AI & Thống kê vào Chọn Số (`Alpha Discovery & Backtesting`) [GIAI ĐOẠN TIẾP THEO]:**
   * Phân tích dữ liệu lịch sử các đài XSMN trên 2 lồng cầu (Hàng Chục & Hàng Đơn Vị).
   * Đo lường thực nghiệm xem phương pháp chọn số của AI tạo ra lợi thế xác suất cao nhất ở quy mô nào (Top 1 bóng, Top 2 bóng, Top 3 bóng hay Loại trừ bóng chết), tần suất nổ thực tế và chuỗi thua tối đa (`Max Losing Streak`) là bao nhiêu.
3. **Giai đoạn 3 — Thiết kế Chiến thuật Chơi & Quản lý Vốn Tối ưu (`Strategy & Kelly Sizing`):**
   * Từ thông số thực tế của Giai đoạn 2, chốt kích thước Bộ số $N$ có lợi thế lớn nhất và ráp vào công thức Quản lý vốn Quỹ để tối đa hóa lợi nhuận tháng.




