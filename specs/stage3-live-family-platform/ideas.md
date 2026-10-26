# Chuyên Viên Báo Cáo Định Lượng Tự Động 5h Sáng & Trang Web Giải Trình Chi Tiết (`Stage 3: Automated 05:00 AM Quantitative Reporter & Web Audit Platform`)

## Domain Context & Core Principles

1. **Vận hành 100% bằng Code Toán học Thuần túy (`100% Pure Mathematical Python — Zero AI API`):**
   - Toàn bộ hệ thống Giai đoạn 3 vận hành dựa trên các mô hình Xác suất Bayes, Kiểm định Thống kê Đa cửa sổ ($\chi^2$, Hệ số Bayes $BF_{10}$, $1.000$ kịch bản Monte Carlo Null), Phát hiện Điểm gãy Chế độ (`BOCD` khi nhà đài thay bóng/bảo trì lồng cầu), và Bộ gộp Xác suất Nhân quả (`CalibratedProbabilityPooler`) đã được kiểm chứng trong `src/xsmn_alpha/`.
   - **Tuyệt đối không sử dụng bất kỳ API AI / LLM bên ngoài nào (như OpenAI, Claude, Gemini):** Loại bỏ hoàn toàn chi phí mua token, rủi ro đứt gãy API, và căn bệnh "ảo giác / bịa lý do" của các mô hình ngôn ngữ. Mọi lời văn giải thích *"Vì sao hôm nay nên đánh hay nên nghỉ"* đều được sinh tự động tất định (`Deterministic Quantitative NLG`) từ chính các chỉ số kiểm định toán học thực tế của ngày hôm đó.

2. **Kiến trúc "Không Database" Siêu Bền Bỉ (`Zero-Database GitOps Static Architecture`):**
   - Bằng việc loại bỏ thao tác nhập tiền thủ công của từng thành viên và định vị hệ thống như một **Chuyên viên Báo cáo Định lượng Trung thực**, hệ thống không cần duy trì bất kỳ Cơ sở dữ liệu động nào (không cần Supabase hay Cloudflare D1).
   - Toàn bộ dữ liệu lịch sử 35 đài (`data/raw_all/` & `data/canonical/`) và sổ cái đối soát của **Quỹ Chuẩn Hệ Thống (`data/live/benchmark_ledger.json`)** được lưu trữ dưới dạng tệp JSON có kiểm chuẩn SHA-256 ngay trong kho lưu trữ.
   - Mỗi ngày, `GitHub Actions` tự động cào kết quả mới, chấm điểm ngày hôm qua, chạy lại mô hình cho các đài mở thưởng hôm nay, xuất bản **Trang Web Báo Cáo Giải Trình Chi Tiết (Static HTML)** lên `GitHub Pages` / `Cloudflare Pages`, và gửi **Bản tin Tóm tắt 05:00 sáng** qua `Telegram Bot API`.

3. **Kỷ luật Quản lý Vốn "CPPI + House-Money" & 5 Cấu hình Ghép Số Chuẩn:**
   - **Hệ số trả thưởng chuẩn hóa:** $1 : 87.5$ (tương đương $\frac{87.5}{18} \approx \mathbf{4.8611\text{ lần}}$ cho mỗi 1 nháy Bao lô 18 giải; mốc hòa vốn đơn bóng $p_{\text{BE}} \approx \mathbf{10.69045\%}$).
   - **5 Cấu hình Bộ số Ngọt (`Sweet-Spot Ticket Configs`):** Mở rộng từ 4 cấu hình của Giai đoạn 2 bằng cách bổ sung cấu hình đối xứng **`4x1` (Top 4 Chục $\times$ Top 1 Đơn vị = 4 số)** bên cạnh `2x2` (4 số), `1x4` (4 số), `3x3` (9 số), và `core_2x2_sat_3x3` (`Hybrid` 4 số Lõi + 5 số Vệ tinh) để bắt trọn cả những đài có Lồng Đơn Vị lệch mạnh hơn Lồng Chục.
   - **Quy tắc Đi vốn Bảo toàn 100% Vốn gốc (`House-Money Compounding`):**
     - Ngày tất cả các đài đều nhiễu trắng (`CASH_BRAKE`): Đi vốn **`0.0x`** (Báo **HÔM NAY NGHỈ**).
     - Ngày có đài đạt chuẩn nhưng chưa có đệm lãi hoặc tín hiệu tiêu chuẩn: Đi vốn chuẩn **`1.0x`** (Không bao giờ gấp thếp sau ngày thua).
     - Ngày có đài đạt **Hội tụ Đỉnh (`PEAK_CONVICTION`)** VÀ Quỹ Chuẩn đang có Lãi Ròng tích lũy ($C_t = \max(0, W_t - W_0) > 0$): Cho phép nâng vốn lên **`1.25x – 1.5x`**, nhưng phần tiền cược tăng thêm bị khóa trần $\Delta \text{Cost}_t \le 0.50 \times C_t$ để đảm bảo dù trượt trắng ($K=0$) cũng không bao giờ chạm vào vốn gốc $W_0$.

---

## Problem Statement

> **Làm thế nào để chúng ta** tự động hóa hoàn toàn quy trình thu thập kết quả 35 đài XSMN/XSMT, tái hiệu chuẩn mô hình lồng cầu mỗi ngày và gửi một bản báo cáo chiến thuật trung thực, rõ ràng vào lúc 05:00 sáng qua Telegram (kèm trang Web giải trình chi tiết toàn bộ số liệu toán học) bằng 100% code thuần túy với chi phí 0 đồng trọn đời?

---

## Chosen Architecture & Inner Mechanics

### 1. Luồng Vận Hành Tự Động Hàng Ngày (Step-by-Step Pipeline)

1. **Bước 1 — Thu thập Kết quả Đa nguồn & Kiểm định Toàn vẹn (`Multi-Source Incremental Ingest`):**
   - Mở rộng danh mục đài hợp lệ trong `src/xsmn_alpha/` lên đầy đủ **35 đài** (21 đài Miền Nam quay lúc `16h15`, 14 đài Miền Trung quay lúc `17h15`) với lịch mở thưởng từ Thứ 2 đến Chủ Nhật.
   - Tự động cào kết quả mới nhất từ `minhngoc.net.vn` (tự động chuyển sang nguồn dự phòng `xskt.com.vn` và `xoso.com.vn` nếu nguồn chính chậm hoặc lỗi).
   - Áp dụng cổng kiểm duyệt `DataSchemaGate`: Bắt buộc kiểm tra đủ đúng **18 giải hợp lệ** (`Giải 8` $\rightarrow$ `Giải ĐB`), chuẩn hóa ngày `YYYY-MM-DD`, tách đếm 10 quả bóng Lồng Chục & Lồng Đơn vị (`sum == 18`), và chống trùng lặp trước khi ghi vào kho lịch sử.

2. **Bước 2 — Đối soát Trung thực Quỹ Chuẩn Tham Chiếu (`Automated Benchmark Settlement`):**
   - Đối chiếu kết quả 18 giải vừa cào được với khuyến nghị mà hệ thống đã phát ra cho ngày hôm đó trong `data/live/benchmark_ledger.json` (khởi đầu với vốn chuẩn `1.000.000 VNĐ`, mức cược cơ sở `1.0x = 72.000 VNĐ/ngày` tương ứng `18.000 VNĐ/số` cho bộ 4 số, trúng 1 nháy thu `87.500 VNĐ`).
   - Đếm chính xác số nháy nổ ($K$), liệt kê rõ nổ ở giải nào, cập nhật Số dư hiện tại ($W_t$), Quỹ Lãi Ròng ($C_t = \max(0, W_t - W_0)$), Tỷ lệ ngày thắng và Max Drawdown lũy kế.

3. **Bước 3 — Tái Hiệu Chuẩn Mô Hình & Chấm Điểm Các Đài Mở Thưởng Trong Ngày (`Daily Station Scoring & Ticket Optimization`):**
   - Với tất cả các đài có lịch mở thưởng trong ngày mục tiêu $D$ (từ 5 đến 7 đài):
     - Chạy kiểm định thống kê trên cửa sổ $W \in \{15, 30, 60\}$ kỳ ($\chi^2$, $BF_{10}$, Entropy) so với ngưỡng phân vị $P_{90}, P_{95}$ của $1.000$ kịch bản Monte Carlo Null.
     - Chạy `CalibratedProbabilityPooler` (kết hợp nhánh `BayesianDirichletBOCD` phát hiện điểm gãy lồng cầu + nhánh `RegularizedMarkovGapModel`) để xuất vector xác suất đã hiệu chuẩn $\mathbf{p}_{\text{tens}}, \mathbf{p}_{\text{units}}$ ($\sum p_i = 1.0$) và bảng xếp hạng 10 quả bóng (`Rank 1` $\rightarrow$ `Rank 10`).
     - Đánh giá hiệu suất Walk-Forward Out-of-Sample (OOS) 3 năm và Expected Value (EV) của cả **5 cấu hình bộ số** (`2x2`, `1x4`, `4x1`, `3x3`, `Hybrid`).
   - **Phân hạng Tín hiệu Ngày (`Daily Verdict Classification`):**
     - 🟢 **`PLAY_PEAK` (`1.25x – 1.5x` từ Quỹ Lãi):** Đài có OOS ROI $\ge +8.0\%$, tần suất trúng bóng Hạng 1 OOS $\ge 10.69\%$, và điểm lệch lồng cầu mạnh ($\chi^2$ hoặc Lift hiện tại vượt chuẩn).
     - 🟢 **`PLAY_STANDARD` (`1.0x`):** Đài đạt chuẩn lợi thế dương rõ rệt (OOS ROI $\ge +5.0\%$ và Rank-1 OOS $\ge 10.69\%$, hoặc điểm lệch hiện tại vượt ngưỡng kiểm định).
     - 🟡 **`PLAY_CAUTIOUS` (`1.0x` hoặc Chia giỏ 30%):** Đài có OOS ROI dương nhẹ ($> 0\%$) và có tín hiệu lệch cục bộ.
     - 🔴 **`SKIP_NO_EDGE` (`0.0x — BÁO NGHỈ`):** Khi tất cả các đài mở thưởng trong ngày đều rơi vào vùng nhiễu trắng (`FAIL_WHITE_NOISE_CASH_BRAKE`), hệ thống phát lệnh **"HÔM NAY NGHỈ — BẢO TOÀN VỐN"**.

4. **Bước 4 — Xuất Bản Trang Web Báo Cáo Chi Tiết (`Static HTML Audit Generator`):**
   - Sinh tự động trang báo cáo HTML tĩnh cho ngày $D$ (`reports/daily/YYYY-MM-DD.html` và cập nhật trang chủ `index.html`) với giao diện Dark-Mode sắc nét, không lỗi bảng biểu, gồm 5 khu vực:
     1. **Tóm tắt Quyết định Chiến thuật & Giải trình Lý do Toán học.**
     2. **Bảng So sánh Toàn bộ 5–7 Đài Mở thưởng Hôm nay** (Miền Nam & Miền Trung) kèm các chỉ số $\chi^2$, $BF_{10}$, ngưỡng Monte Carlo Null, trạng thái BOCD, và OOS ROI 3 năm.
     3. **Bảng Phân phối Xác suất 10 Quả bóng (`0`–`9`) của 2 Lồng cầu & Ma trận 100 Số (`00`–`99`)** cho từng đài, kèm 5 phương án ghép số (`2x2`, `1x4`, `4x1`, `3x3`, `Hybrid`).
     4. **Bảng Tư vấn Đi vốn & Bảng Quy đổi Tiền VNĐ Mẫu** (cho các quy mô vốn `500.000đ`, `1.000.000đ`, `2.000.000đ`, `5.000.000đ` và theo đơn vị Điểm lô `14.400đ` / `18.000đ`).
     5. **Nhật ký Thu thập Dữ liệu (`Data Pipeline Audit`) & Lịch sử Kiểm toán Quỹ Chuẩn (`Benchmark Equity Curve & Settlement Log`)**.

5. **Bước 5 — Phát Bản Tin Tóm Tắt 05:00 Sáng qua Telegram (`05:00 AM Telegram Dispatcher`):**
   - Đúng `05:00 ICT` mỗi sáng (qua GitHub Actions Schedule / CLI), gửi tin nhắn định dạng HTML/Markdown chuẩn mực tới `TELEGRAM_CHAT_ID` qua `https://api.telegram.org/bot<TOKEN>/sendMessage` gồm đúng 4 mục:
     1. **Có nên đánh hôm nay không? Vì sao?**
     2. **Nên đánh đài gì? Khu vực nào (Miền Nam hay Miền Trung)?**
     3. **Đài nên đánh nhất thì đánh bộ số nào?** (Kèm Top bóng Chục, Top bóng Đơn vị và bộ số cụ thể).
     4. **Đi vốn như thế nào?** (Hệ số vốn + tiền mẫu VNĐ + cập nhật kết quả hôm qua).
     - Cuối tin nhắn đính kèm **Đường link trực tiếp mở Trang Web Báo Cáo Chi Tiết của ngày hôm đó**.

---

## Key Assumptions to Validate

- [ ] **Giả định 1 (Độ trễ Cron của GitHub Actions vào sáng sớm):** Lịch `cron` của GitHub Actions có thể dao động 5–15 phút. *Cách kiểm chứng & xử lý:* Đặt lịch chạy chuẩn bị dữ liệu và gửi tin quanh khung `04:45 – 05:00 ICT` (tức `21:45 – 22:00 UTC` đêm hôm trước), đồng thời tách bước cào kết quả buổi chiều tối (`18:15 ICT`) để dữ liệu luôn sẵn sàng từ tối hôm trước.
- [ ] **Giả định 2 (Tính đầy đủ 18 giải khi cào dữ liệu tự động):** Nguồn `minhngoc.net.vn` có thể đôi lúc bảo trì hoặc thay đổi nhẹ cấu trúc trang. *Cách kiểm chứng & xử lý:* Tích hợp bộ chuyển đổi dự phòng 3 tầng (`minhngoc.net.vn` $\rightarrow$ `xskt.com.vn` $\rightarrow$ `xoso.com.vn`) và chỉ chấp nhận kỳ quay khi vượt qua cổng kiểm tra đủ 18 giải (`DataSchemaGate`).
- [ ] **Giả định 3 (Hiệu quả bổ sung của cấu hình `4x1`):** Một số đài có Lồng Đơn Vị lệch mạnh hơn Lồng Chục sẽ đạt ROI cao hơn khi dùng `4x1` thay vì `1x4`. *Cách kiểm chứng:* Đưa `4x1` vào `sweet_spot_sim.py` và chạy kiểm thử Walk-Forward 3 năm trên toàn bộ 35 đài.

---

## MVP Scope

**Những gì NẰM TRONG phạm vi xây dựng (In Scope):**
1. **Nâng cấp Lõi `src/xsmn_alpha/` cho 35 Đài & Cấu hình `4x1`:**
   - Mở rộng registry chuẩn cho toàn bộ 35 đài (21 MN + 14 MT) kèm lịch mở thưởng theo thứ trong tuần và khung giờ quay (`16h15` MN, `17h15` MT).
   - Bổ sung cấu hình `4x1` (Top 4 Chục $\times$ Top 1 Đơn vị = 4 số) vào `sweet_spot_sim.py`.
2. **Mô-đun Chuyên viên Báo cáo Hàng ngày (`Daily Quantitative Analyst & Benchmark Ledger`):**
   - Tự động cào kết quả mới cho các đài vừa mở thưởng, đối soát Lãi/Lỗ vào sổ cái `data/live/benchmark_ledger.json` (khởi tạo tiếp nối từ kết quả kiểm thử 2026).
   - Tính toán bảng xếp hạng đài trong ngày, chọn đài số 1 (và đài phụ nếu có), chọn cấu hình ghép số tối ưu nhất, tính hệ số đi vốn CPPI / House-Money (`0.0x`, `1.0x`, `1.25x`, `1.5x`), và sinh lời văn giải trình toán học tiếng Việt.
3. **Trình Xuất Trang Web Báo Cáo Chi Tiết (`Daily Static HTML Report & Index Dashboard`):**
   - Xuất trang báo cáo chi tiết từng ngày (`public/daily/YYYY-MM-DD.html`) và trang chủ tổng hợp (`public/index.html`) hiển thị đầy đủ quy trình thu thập dữ liệu, xử lý kiểm định, bảng phân phối xác suất 10 bóng & 100 số, hướng dẫn đi vốn và lịch sử Quỹ Chuẩn.
4. **Trình Gửi Bản Tin Telegram 05:00 Sáng & Workflow Tự Động (`GitHub Actions + Telegram Bot`):**
   - Module gửi tin nhắn Telegram chuẩn xác (có chế độ chạy thử `--dry-run` in ra màn hình/file khi chưa điền Token) và cấu hình `.github/workflows/daily_quant_report.yml` tự động chạy mỗi ngày + tự động xuất bản trang Web miễn phí.

---

## Not Doing (and Why)

- **Không làm tính năng 4 Ví thành viên tự nhập tiền/ghi sổ trên Web** — *Lý do:* Gây rườm rà không cần thiết cho người trong gia đình và buộc phải dùng Database động. Thay bằng bảng quy đổi tiền mẫu (`500k`, `1M`, `2M`, `5M`) và 1 Quỹ Chuẩn Tự Động làm thước đo trung thực.
- **Không dùng bất kỳ API AI / LLM bên ngoài nào (OpenAI, Gemini, Claude)** — *Lý do:* Tốn phí, phụ thuộc bên thứ ba và có nguy cơ "bịa số / ảo giác". Toàn bộ phân tích và lời văn giải thích đều được lập trình tất định 100% từ kết quả toán học thật.
- **Không dùng Database trả phí hay Supabase dễ bị ngủ đông sau 7 ngày** — *Lý do:* Lưu trữ bằng file JSON chuẩn kết hợp Static Web (`GitHub Pages` / `Cloudflare Pages`) đạt độ bền bỉ 100%, tốc độ tải trang `< 0.01 giây` và miễn phí vĩnh viễn.
- **Không bao giờ gợi ý gấp thếp khi thua (`Martingale` / `1-3-2-6`)** — *Lý do:* Vi phạm nguyên tắc sống còn bảo vệ 100% vốn gốc trong `QUY_TAC_VA_DIEM_HOA_VON.md`.

---

## Open Questions

- Không còn câu hỏi mở nào về mặt kiến trúc. Các thông số kết nối thực tế (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, và `PUBLIC_REPORT_BASE_URL`) sẽ được thiết kế dưới dạng biến môi trường (`Environment Variables / GitHub Secrets`) có chế độ fallback chạy local an toàn để kiểm thử hoàn chỉnh trước khi đưa lên GitHub.
