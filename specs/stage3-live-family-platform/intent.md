# Statement of Intent — Giai Đoạn 3: Chuyên Viên Báo Cáo Định Lượng Tự Động 5h Sáng & Trang Web Giải Trình Chi Tiết (`Automated 05:00 AM Quantitative Reporter & Web Audit Platform`)

**Trạng thái:** Đã xác nhận & Đồng bộ hóa sau Pha Nghiên cứu Kiến trúc (`Confirmed & Back-Propagated`)
**Ngày cập nhật:** 2026-10-26
- **Tài liệu quy ước gốc (Giai đoạn 1 & Giai đoạn 2):**
  - `C:\sidehustle\XSTK\QUY_TAC_VA_DIEM_HOA_VON.md`
  - `C:\sidehustle\XSTK\specs\stage2-alpha-discovery\intent.md`
  - `C:\sidehustle\XSTK\specs\stage2-alpha-discovery\spec.md`
  - `C:\sidehustle\XSTK\scripts\scan_all_35_stations.py`
  - `C:\sidehustle\XSTK\reports\all_35_stations_radar_report.html`
  - `C:\sidehustle\XSTK\reports\ytd_2026_1m_simulation_report.html`
  - `C:\sidehustle\XSTK\reports\stage3_architecture_decision_guide.html`

---

## 1. Bản Đúc Kết Ý Định (Confirmed Statement of Intent)

- **Outcome (Đầu ra mục tiêu):** Xây dựng hệ thống **"Chuyên viên Báo cáo Định lượng Trung thực Tự động 100%"** vận hành hoàn toàn bằng **code Toán học & Thống kê thuần túy (`NumPy`/`SciPy` — tuyệt đối không phụ thuộc bất kỳ API AI trả phí nào)**, tự động gửi bản tin chiến thuật lúc **05:00 sáng mỗi ngày qua Telegram** kèm đường link dẫn tới **Trang Web Báo Cáo Giải Trình Chi Tiết**:
  1. **Tự động thu thập, Đối soát Lịch sử & Tái hiệu chuẩn mô hình mỗi ngày (`Daily Auto-Fetch, Settlement & Rolling Recalibration`):**
     - Tự động lấy kết quả xổ số 18 giải mới nhất của các đài mở thưởng từ `minhngoc.net.vn` (kèm cơ chế tự thử lại và nguồn dự phòng `xskt.com.vn` / `xoso.com.vn`), nối vào lịch sử 35 đài (21 đài Miền Nam & 14 đài Miền Trung).
     - Tự động chấm điểm Lãi/Lỗ của ngày hôm trước trên **Quỹ Chuẩn Tham Chiếu Tự Động (`1.000.000 VNĐ` khởi đầu)** để báo cáo trung thực hiệu quả thực chiến lũy kế.
     - Chạy lại toàn bộ thuật toán kiểm định thống kê ($\chi^2$ đa cửa sổ, Bayes Factor $BF_{10}$, 1.000 Monte Carlo Null) + phát hiện điểm gãy chế độ (`BOCD` khi nhà đài thay bóng/bảo trì máy) + hiệu chuẩn xác suất (`Causal Calibrated Pooler`) để mô hình luôn tự thích nghi qua nhiều năm vận hành.
  2. **Bản Tin Tóm Tắt Chiến Thuật 05:00 Sáng qua Telegram (`05:00 AM Telegram Executive Briefing`):**
     Đúng 05:00 sáng mỗi ngày (giờ Việt Nam `Asia/Ho_Chi_Minh`), gửi một tin nhắn tóm tắt súc tích, dễ đọc vào Telegram trả lời trực diện 4 câu hỏi cốt lõi:
     - **Có nên đánh hôm nay không? Vì sao?** (Chỉ rõ tín hiệu `🟢 NÊN ĐÁNH` hay `🔴 HÔM NAY NGHỈ — BẢO TOÀN VỐN` kèm lý do định lượng cụ thể từ số liệu kiểm định $\chi^2$, xác suất bóng Hạng 1 so với mốc hòa vốn `10.69%`, và ROI kiểm thử 3 năm).
     - **Nên đánh thì đánh đài gì? Khu vực nào?** (Chỉ định rõ đài ưu tiên số 1 mở thưởng trong ngày thuộc Miền Nam `16h15` hay Miền Trung `17h15`, đài phụ nếu có, và danh sách các đài nhiễu trắng cần bỏ qua).
     - **Với đài nên đánh nhất thì đánh bộ số nào?** (Hiển thị rõ Top bóng Lồng Hàng Chục, Top bóng Lồng Hàng Đơn Vị, cấu hình ghép số tối ưu nhất trong 5 cấu hình chuẩn: `2x2 = 4 số`, `1x4 = 4 số`, `4x1 = 4 số`, `3x3 = 9 số`, hoặc `Hybrid Core 2x2 + Satellite 3x3` kèm bộ số cụ thể).
     - **Đi vốn như thế nào?** (Tư vấn hệ số đi vốn chuẩn kỷ luật CPPI / House-Money: `0.0x` khi báo Nghỉ, `1.0x` tiêu chuẩn, hoặc `1.25x – 1.5x` trích tối đa 50% từ Quỹ Lãi Ròng vào ngày tín hiệu hội tụ đỉnh; kèm bảng quy đổi mẫu ra tiền VNĐ thực tế để dễ áp dụng).
     - **Đường link Báo Cáo Chi Tiết trên Trang Web** nằm ngay cuối tin nhắn Telegram.
  3. **Trang Web Báo Cáo Giải Trình Chi Tiết Hàng Ngày (`Daily Detailed Web Audit Report`):**
     Khi bấm vào đường link từ Telegram, trang Web trình bày trực quan, rõ ràng toàn bộ bằng chứng toán học của ngày hôm đó:
     - Nhật ký thu thập & kiểm định dữ liệu đầu vào (nguồn cào, ngày mở thưởng mới nhất, kiểm tra đủ 18 giải, trạng thái điểm gãy `BOCD`).
     - Bảng chấm điểm & so sánh toàn bộ 5–7 đài mở thưởng trong ngày (Miền Nam & Miền Trung).
     - Bảng phân phối xác suất đầy đủ của 10 quả bóng (`0`–`9`) ở Lồng Hàng Chục và Lồng Hàng Đơn Vị, ma trận xác suất 100 con số (`00`–`99`), và toàn bộ 5 phương án ghép số (`2x2`, `1x4`, `4x1`, `3x3`, `Hybrid`).
     - Bảng hướng dẫn đi vốn quy đổi mẫu theo các mức vốn phổ biến (`500k`, `1 Triệu`, `2 Triệu`, `5 Triệu`) và biểu đồ đường cong vốn + lịch sử đối soát trung thực của **Quỹ Chuẩn Hệ Thống**.

- **User (Người sử dụng):** Chủ dự án và các thành viên trong gia đình (nhận bản tin 05:00 sáng trên Telegram và bấm link xem trang Web báo cáo giải trình chi tiết khi cần).

- **Why now (Lý do thực hiện):**
  - Đã hoàn tất **Giai đoạn 1 (`Break-Even Benchmark`)**, **Giai đoạn 2 (`Alpha Discovery & 35-Station Radar`)**, và báo cáo kiểm chứng thực chiến **2026 (`ytd_2026_1m_simulation_report.html`)**.
  - Việc rút gọn hệ thống thành một **Chuyên viên Báo cáo Định lượng Trung thực lúc 5h sáng** (loại bỏ thao tác nhập tiền thủ công rườm rà của từng người) giúp hệ thống đạt độ tinh gọn tối đa, không cần Database phức tạp, không cần API AI trả phí, và vận hành tự động bền bỉ nhiều năm với chi phí 0 đồng.

- **Success (Tiêu chí thành công):**
  1. **Vận hành 100% bằng Code Toán học — Không cần AI API — Tự động hoàn toàn:** Mỗi ngày trước 05:00 sáng, hệ thống tự cào kết quả mới, tự đối soát lịch sử Quỹ Chuẩn, tự chạy lại mô hình 35 đài, xuất bản trang Web báo cáo chi tiết và gửi tin nhắn Telegram đúng 05:00 sáng.
  2. **Trung thực & Minh bạch tuyệt đối:** Mọi lời khuyên "Đánh" hay "Nghỉ" đều đi kèm số liệu giải trình rõ ràng trên Web và được tự động kiểm toán kết quả Thắng/Thua vào ngày hôm sau.
  3. **Bảo vệ tài sản & Hướng tới lãi ròng dài hạn:** Thực thi nghiêm ngặt kỷ luật không gấp thếp khi thua, đứng ngoài những ngày cầu nhiễu trắng, và chỉ nâng vốn (`1.25x – 1.5x`) từ Quỹ Lãi Ròng (`House-Money`).
  4. **Chi phí vận hành 0 đồng trọn đời:** Chạy hoàn toàn trên gói miễn phí của GitHub Actions + GitHub Pages / Cloudflare Pages + Telegram Bot API.

- **Constraint (Ràng buộc cốt lõi):**
  - **100% Pure Code & Zero AI API:** Không gọi bất kỳ API LLM (OpenAI / Gemini / Claude) nào; mọi tính toán xác suất và lời văn giải trình đều được sinh tất định (deterministic) từ kết quả kiểm định toán học.
  - **Hạ tầng miễn phí 100% (`Zero-Database Static GitOps Stack`):** Sử dụng GitHub Actions + GitHub Pages / Cloudflare Pages + Telegram Bot API + Sổ cái JSON chuẩn trong kho lưu trữ.
  - **Toán học & Quản trị rủi ro nhất quán:** Tuân thủ hệ số trả thưởng thực `1 : 87.5` (`4.8611 đồng/lô` trên mỗi `1 đồng/số` Bao lô 18 giải), chống rò rỉ dữ liệu tương lai (`Pre-Draw Temporal Cutoff`), và cấm mọi biến tướng gấp thếp (`Martingale`, `1-3-2-6`).

- **Out of scope (Ngoài phạm vi):**
  - Không làm tính năng nhập số tiền / ghi sổ cá nhân cho 4 ví thành viên trên Web (để tránh rườm rà và loại bỏ nhu cầu dùng Database động).
  - Không tự động kết nối hay đặt cược tiền thật vào bất kỳ trang nhà cái nào.
  - Không dùng bất kỳ dịch vụ trả phí nào (Zalo OA trả phí, VPS trả phí, AI API trả phí).
