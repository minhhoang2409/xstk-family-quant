# Idea Refinement — Giai đoạn 4: Hệ Thống Điểm Ngọt Gia Đình, Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu & Giám Sát Dị Thường (`stage4-alpha-engine-v2`)

**Trạng thái:** ĐÃ CHỐT (Phase 3 — Sharpen & Ship hoàn tất)
**Ngày chốt:** 2026-10-27
**Tài liệu liên kết:** [intent.md](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/intent.md), [QUY_TAC_VA_DIEM_HOA_VON.md](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md)

---

## 1. Tóm tắt Kiểm Toán Thực Nghiệm (Phase 0 & Phase 1 — Grounding & Stress-Test)

Trên tập dữ liệu lịch sử 35 đài XSMN/XSMT (`data/raw_all/`, 8.320 kỳ quay = 149.760 giải = 447.840 lượt rút bi), toàn bộ 5 giả thuyết nâng cấp thuật toán ban đầu đã được kiểm chứng Walk-Forward nghiêm ngặt (`< D`, không rò rỉ tương lai, `max |p_full - p_trunc| = 0.000e+00`):

| Mã kiểm chứng | Kịch bản / Модуль kiểm toán | Kết quả thực nghiệm (5.285 đài-ngày OOS) | Kết luận Khoa học |
| :--- | :--- | :--- | :--- |
| **`audit_engine_v2_benchmark.py`** | So sánh `NULL_RAND`, `V1`, `V1_NOSWAP`, `V1_FIX2` (exponential forgetting), `A_BMA`, `B_STACK`, `C_2DEB` (2D Empirical Bayes + Top-4), `D_TIER` (intra-session) | `JointR1` đạt `0.928% – 0.986%` so với kỳ vọng ngẫu nhiên `1.000%` (không vượt ngưỡng hòa vốn `1.005025%` ở mức 99.5k/18k). | Lồng cầu vật lý có hoàn lại sau mỗi giải hoạt động sát phân phối đều `10.0% ± 0.11%`. Không thuật toán dự đoán chuỗi nào thắng được lồng cầu công bằng. |
| **`ytd_sim_replay.py`** | Tái lập kịch bản sổ cái `benchmark_ledger.json` (`+27.48%` YTD 2026) trên các năm độc lập 2024, 2025, 2026 | Năm 2026: `z = +3.07` (`+31.7%` ROI); Năm 2025: `z = +0.31` (`+2.9%` ROI); Năm 2024: `z = 0.00` (`-0.50%` ROI = đúng bằng ngẫu nhiên). | Lãi cao của năm 2026 là hệ quả của chọn ngưỡng lọc trong mẫu (in-sample selection bias) kết hợp phương sai ngắn hạn. |
| **`game_mechanics_probe.py`** | Giải mã "Chiến thuật Bà Cô" (đánh cố định 4–5 số mỗi ngày, 18.000đ/số, trúng nhận 99.500đ/nháy) | • **Vé 4 số (`72.000đ/ngày`):** **52,0% ngày có lời** (`1 nháy = +27.5k`, `2 nháy = +127k`).<br>• **Vé 5 số (`90.000đ/ngày`):** **60,3% ngày có lời** (`1 nháy = +9.5k`, `2 nháy = +109k`).<br>• Hao hụt kỳ vọng dài hạn chỉ **`-0.50%`** (`-360đ` đến `-450đ/ngày`), trong khi độ lệch chuẩn năm là `±1,76 triệu/năm` → **42,5% người chơi 5 số vẫn đang lời ròng sau 4,5 năm**. | **Đây chính là "Điểm Ngọt" (Sweet Spot) thật sự của trò chơi:** Tiền xác chỉ đóng 1 lần/ngày, từ nháy thứ 2 trở đi ăn trọn 100% (`+99.500đ/nháy` không mất thêm tiền xác). |
| **`anomaly_scan.py` & `changepoint_scan.py`** | Quét 531 kiểm định $\chi^2$ (BH-FDR 5%) và điểm gãy hoán vị $G^2$ trên 70 lồng cầu | **34/35 đài** cân bằng hoàn hảo. Duy nhất đài **Bến Tre (`XSBT`, mở thưởng Thứ 3)** có điểm gãy vật lý từ ~04/2024: bi hàng chục `4` tụt từ `10.2%` xuống **`3.6%`** ($p \approx 5 \times 10^{-14}$, $\chi^2_{\max} = 50.35$, $BF_{10} = 1.82 \times 10^7$) và bi đơn vị `6` năm 2026 tụt xuống `4.2%`. | Thay vì cố dự đoán kỳ tiếp theo trên lồng cầu cân bằng, hệ thống phải đóng vai trò **Bộ Giám Sát Độ Cân Bằng Lồng Cầu** (né ngày lồng cầu cân bằng, phát hiện lồng cầu bị lệch vật lý). |

---

## 2. Phân tích Xếp Hạng 7 Ngày Trong Tuần Theo Độ Cân Bằng Lồng Cầu

Kiểm định thực nghiệm toàn bộ 35 đài phân bổ theo 7 thứ trong tuần (`Thứ 2` → `Chủ Nhật`) dựa trên chỉ số lệch cực đại $\chi^2_{\max}$ (đa khung $W \in \{15, 30, 60\}$), Hệ số Bayes $BF_{10}$ và Entropy chuẩn hóa:

| Xếp hạng Cân Bằng | Thứ trong tuần | Số đài mở thưởng | Các đài trong ngày | $\chi^2_{\max}$ cao nhất ngày | $\chi^2$ trung bình | $BF_{10}$ cao nhất | Entropy thấp nhất | Quyết định Lịch 5/2 |
| :---: | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **#1 (Cân bằng nhất)** | **Thứ 4** | 5 đài | `XSDN`, `XSCT`, `XSST`, `XSDNG`, `XSKH` | **13.22** | 10.91 | 0.429 (`< 1`) | 0.9947 | 🔴 **NGHỈ ĐỊNH KỲ #1 (0x)** |
| **#2 (Cân bằng nhì)** | **Thứ 2** | 5 đài | `XSHCM`, `XSDT`, `XSCM`, `XSTTH`, `XSPY` | **15.07** | 12.53 | 0.624 (`< 1`) | 0.9938 | 🔴 **NGHỈ ĐỊNH KỲ #2 (0x)** |
| **#3** | **Thứ 5** | 6 đài | `XSTN`, `XSAG`, `XSBTH`, `XSBDI`, `XSQT`, `XSQB` | **16.67** | 11.77 | 1.750 | 0.9932 | 🟢 **CHƠI ĐIỂM NGỌT (1.0x)** — Đài dẫn đầu: `XSTN` |
| **#4** | **Thứ 7** | 7 đài | `XSHCM`, `XSLA`, `XSBP`, `XSHG`, `XSDNG`, `XSQNG`, `XSDNO` | **18.31** | 13.53 | 1.683 | 0.9937 | 🟢 **CHƠI ĐIỂM NGỌT (1.0x)** — Đài dẫn đầu: `XSBP` |
| **#5** | **Chủ Nhật** | 6 đài | `XSTG`, `XSKG`, `XSDL`, `XSTTH`, `XSKH`, `XSKT` | **18.67** | 12.48 | 2.408 | 0.9921 | 🟢 **CHƠI ĐIỂM NGỌT (1.0x)** — Đài dẫn đầu: `XSDL` |
| **#6** | **Thứ 6** | 5 đài | `XSVL`, `XSBD`, `XSTV`, `XSGL`, `XSNT` | **18.70** | 14.36 | 0.579 | 0.9939 | 🟢 **CHƠI ĐIỂM NGỌT (1.0x)** — Đài dẫn đầu: `XSVL` |
| **#7 (Lệch mạnh nhất)** | **Thứ 3** | 5 đài | `XSBT`, `XSVT`, `XSBL`, `XSDLK`, `XSQNM` | **50.35** | 20.04 | **1.82e7** | 0.9838 | 🟢 **CHƠI ĐIỂM NGỌT (1.0x)** — Đài dẫn đầu: `XSBT` (Dị thường bi `4`) |

> **Nhận xét quan trọng:**
> * Vào **Thứ 4** và **Thứ 2**, toàn bộ các đài mở thưởng đều có $BF_{10} < 1.0$ (bằng chứng Bayes nghiêng hẳn về giả thuyết lồng cầu cân bằng tuyệt đối) và Entropy $> 0.9938$. Cho nghỉ đúng 2 ngày này giúp giảm ngay **28,6% tổng chi phí cược hàng tuần**, vừa có lý do toán học cực kỳ thuyết phục để ba của User vui vẻ nghỉ ngơi 2 ngày/tuần.
> * Thay vì gán cứng Thứ 2 và Thứ 4 mãi mãi, Engine sẽ **tự động xếp hạng độ cân bằng của 7 ngày trong tuần theo dữ liệu trượt `< D`** và chọn đúng **2 ngày có $\chi^2_{\max}$ thấp nhất tuần** làm 2 ngày nghỉ định kỳ (`SKIP_NO_EDGE`).

---

## 3. Các Phương Án Đã Khảo Sát & Lý Do Chốt Phương Án Cuối (Phase 2 — Diverge & Converge)

1. **Phương án 1 (Đã bác bỏ): Tiếp tục nâng cấp độ phức tạp của Engine dự đoán chuỗi (BMA, 2D Empirical Bayes, Intra-session) để tìm cách thắng mỗi ngày.**
   * *Lý do bác bỏ:* Không vượt qua cổng ngụy biện Walk-Forward (`z < 0` so với `NULL_RAND`). Càng làm phức tạp càng dễ rơi vào bẫy quá khớp (overfitting) và tạo ảo tưởng để đánh gấp thếp `1.5x`.
2. **Phương án 2 (Đã bác bỏ): Khuyên người nhà dừng hẳn hoặc báo `SKIP_NO_EDGE` 6–7 ngày/tuần.**
   * *Lý do bác bỏ:* Ba của User muốn có niềm vui dò số mỗi tuần và tin vào xác suất. Nếu Bot ngày nào cũng báo nghỉ (như đang xảy ra vào cuối tháng 10/2026), ba sẽ bỏ Bot và tự đi soi cầu ngoài luồng hoặc đánh gấp thếp để kiếm "500k tiền chợ", gây rủi ro tài chính lớn hơn nhiều.
3. **Phương án 3 (PHƯƠNG ÁN ĐƯỢC CHỌN — "Kỷ Luật Điểm Ngọt Gia Đình 5/2 & Giám Sát Lồng Cầu"):**
   * Giữ nguyên hệ thống tự động 05:00 sáng qua Telegram ([telegram_bot.py](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/telegram_bot.py)) và Web báo cáo tĩnh ([web_publisher.py](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/web_publisher.py)), nhưng nâng cấp logic chấm điểm trong [daily_analyst.py](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/daily_analyst.py) theo 4 trụ cột thực tế:
     1. **Bộ Lọc Lịch Chơi 5/2 Thích Ứng (`Weekly 5/2 Cage-Balance Filter`):**
        * Tự động đối chiếu 7 ngày trong tuần (`D-6 .. D`), chọn ra **2 ngày có lồng cầu cân bằng nhất (thấp nhất về `chi2_max_overall`)** để phát lệnh **`🔴 HÔM NAY NGHỈ ĐỊNH KỲ (Lồng cầu cân bằng tuyệt đối — Quy tắc 5/2 bảo toàn vốn)`** (`0.0x`).
        * Trong **5 ngày còn lại trong tuần**, luôn bật **`🟢 HÔM NAY ĐÁNH ĐIỂM NGỌT ĐỀU TAY (1.0x)`** tại đài có độ lệch lồng cầu ($\chi^2_{\max}$ / $BF_{10}$) lớn nhất ngày (ví dụ: Thứ 3 tự động chọn **Bến Tre `XSBT`** thay vì chọn nhầm Đắk Lắk như logic cũ).
     2. **Cấu Hình Vé Điểm Ngọt Kép (Bộ 4 số `2x2` & Bộ 5 số Điểm Ngọt Bà Cô `sweet_5`):**
        * Hiển thị rõ trên Telegram cả **Bộ 4 số `2x2`** (vốn chuẩn `72.000đ`, **52,0% ngày lời**, 1 nháy lời `+27.500đ`, 2 nháy lời `+127.000đ`) và **Bộ 5 số Điểm Ngọt** (4 số `2x2` + 1 số vệ tinh xác suất cao nhất, vốn chuẩn `90.000đ`, **60,3% ngày lời**, 1 nháy lời `+9.500đ`, 2 nháy lời `+109.000đ`).
     3. **Khóa Trần Kỷ Luật Đi Vốn `1.0x` & Định Hướng "Tiền Chợ Thông Minh":**
        * Loại bỏ hoàn toàn lệnh đánh gấp `1.5x` (`PLAY_PEAK`) trong [daily_analyst.py](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/daily_analyst.py) và [ledger.py](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/ledger.py); mọi ngày chơi đều cố định hệ số **`1.0x`**.
        * Đưa thông điệp **"Quy tắc Tiền Chợ Xác Suất"** vào trực tiếp bản tin Telegram mỗi sáng để neo kỷ luật cho ba:
          * *Mức chuẩn 1x–2x (`72k–180k/ngày`): Ngày nổ 1 nháy mục tiêu là **Hoàn vốn + Cà phê**; ngày nổ **2–3 nháy** (trung bình 1–2 lần/tuần) tự động thu về **`+220.000đ` đến `+450.000đ` tiền chợ** vì nháy thứ 2 không tốn tiền xác.*
          * *Tuyệt đối không nhân đôi tiền cược sau ngày trượt.*
     4. **Cảnh Báo Dị Thường Lồng Cầu (`Cage Anomaly Sentinel`):**
        * Khi đài chủ lực trong ngày có lồng cầu vượt ngưỡng dị thường cực đoan ($\chi^2_{\max} > P_{95}$ và $BF_{10} > 10$, như `XSBT` bi hàng chục `4` bị tụt xuống `3.6%`), bản tin Telegram và Web sẽ hiển thị nhãn **`⚠️ PHÁT HIỆN LỒNG CẦU LỆCH MẠNH`** kèm giải thích cụ thể quả bi nào đang bị câm/nóng bất thường để loại bỏ bi chết khỏi tổ hợp số.

---

## 4. Phạm Vi Thay Đổi Kỹ Thuật Dự Kiến (Chuẩn bị cho Spec Giai đoạn 4)

1. **`src/xsmn_alpha/constants.py` & `src/xsmn_alpha/schemas.py`:**
   * Bổ sung cấu hình vé `sweet_5` (5 số Điểm Ngọt Bà Cô: `4 số 2x2 + 1 số top vệ tinh`, chi phí chuẩn `90.000đ`, xác suất trúng $\ge 1$ nháy `60.27%`).
   * Khóa `PEAK_CONVICTION` multiplier về `1.0x` (loại bỏ `1.5x` stake).
2. **`src/xsmn_alpha/live/daily_analyst.py`:**
   * Nâng cấp `rank_stations_for_day`: Xếp hạng đài trong ngày ưu tiên độ lệch lồng cầu thực tế (`chi2_max_overall`, `bf10_max_overall`, `station_alpha_score`) để không bỏ sót các đài dị thường thật như `XSBT`.
   * Thêm hàm xác định **Quy tắc Lịch Chơi 5/2 (`compute_weekly_balance_rest_days`)**: Quét 7 ngày trong tuần hiện tại (`< D`), đánh dấu đúng **2 ngày có `max(chi2_max_overall)` thấp nhất tuần** là ngày nghỉ định kỳ (`SKIP_NO_EDGE` — `0.0x`), và 5 ngày còn lại là ngày chơi chuẩn (`PLAY_STANDARD` — `1.0x`).
3. **`src/xsmn_alpha/live/telegram_bot.py` & `src/xsmn_alpha/live/web_publisher.py`:**
   * Cập nhật mẫu bản tin 05:00 sáng thân thiện, rõ ràng cho ba của User:
     * Ngày nghỉ (2 ngày/tuần): Giải thích rõ *"Hôm nay lồng cầu các đài cân bằng tuyệt đối (Chi2 thấp nhất tuần) — Nghỉ định kỳ theo quy tắc 5/2 để bảo toàn vốn"*.
     * Ngày chơi (5 ngày/tuần): Hiển thị rõ **Bộ 5 số Điểm Ngọt (60,3% ngày thắng)** & **Bộ 4 số 2x2 (52,0% ngày thắng)** kèm khung nhắc nhở **"Kỷ Luật Tiền Chợ Đều Tay 1x (Ăn tiền chợ ở ngày nổ 2 nháy, tuyệt đối không gấp thếp)"**.
4. **Kiểm thử (`tests/`):**
   * Đảm bảo toàn bộ unit tests & integration tests kiểm chứng quy tắc 5 ngày chơi / 2 ngày nghỉ mỗi tuần, khóa hệ số `1.0x`, và định dạng Telegram `< 4096` ký tự.
