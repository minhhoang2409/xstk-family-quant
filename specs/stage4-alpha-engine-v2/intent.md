# Statement of Intent — Giai đoạn 4: Kiểm toán & Nâng cấp Thuật toán Lõi Chọn Số (`stage4-alpha-engine-v2`)

**Trạng thái:** ĐÃ CHỐT (User đã xác nhận mục tiêu & phương án cuối sau Pha 0–3 của `idea-refine`)
**Ngày tạo:** 2026-10-27
**Tài liệu quy ước gốc:** `QUY_TAC_VA_DIEM_HOA_VON.md`, `specs/stage2-alpha-discovery/`, `specs/stage3-live-family-platform/`
**Bằng chứng thực nghiệm:** `scratch/audit_engine_v2_benchmark.py` → `scratch/audit_engine_v2_results.json`, `scratch/audit_engine_v2_run.log`

---

## 1. Yêu cầu gốc của User (nguyên văn rút gọn)

Kiểm toán sâu thuật toán chọn số hiện tại (`engine/bocd_dirichlet.py`, `engine/markov_gap_model.py`,
`engine/calibration_pooler.py`, `backtest/sweet_spot_sim.py`, `live/daily_analyst.py`) và khắc phục 5 điểm yếu:

1. Bỏ thủ thuật hậu nghiệm `swap_top2` (`calibration_pooler.py` L438-472) → thay bằng mô hình xác suất có nguyên lý.
2. Nhánh 2 Markov-Gap cộng dồn lịch sử không có hệ số quên (exponential forgetting) → w2 ≈ 0.
3. Mở rộng chọn 4 số ngoài hình chữ nhật (2x2/1x4/4x1): Top-4 ô không ràng buộc + 2D Empirical-Bayes shrinkage với prior P_tens ⊗ P_units.
4. Tận dụng cấu trúc giải trong buổi quay (`session_early_ratios`) / động học chu kỳ đa khung.
5. Bộ chọn cấu hình vé & điểm đài (`select_optimal_ticket_config`, `station_alpha_score`) theo hiệu suất trượt thích ứng thay vì trung bình 3 năm tĩnh.

**Ràng buộc bắt buộc:** chỉ nâng cấp những thành phần **chứng minh vượt trội ngoài mẫu** trong Walk-Forward che kín 100% tương lai (< D) trên `data/raw_all/`.

## 2. Outcome (Đầu ra mục tiêu — dự thảo)

Một Engine v2 mà **mọi thành phần đều đã qua cổng ngụy biện (falsification gate)** so với cả Engine v1 lẫn
bộ chọn ngẫu nhiên (`NULL_RAND`), và một sản phẩm báo cáo **trung thực** về việc có/không có lợi thế.

## 3. Tiêu chí thành công (đề xuất — chờ User xác nhận)

- **Cổng ngụy biện (bắt buộc):** một thành phần chỉ được đưa vào v2 nếu paired walk-forward vs V1 **và** vs NULL_RAND cho z ≥ 3.0
  (đã hiệu chỉnh đa kiểm định) trên ROI hoặc JointR1, và **cùng dấu ở cả 2 nửa thời gian** (H1/H2).
- **Ngưỡng hòa vốn tham chiếu:** vé 4 số Bao Lô cần mỗi ô ≥ 1/87.5 = 1.1429%/giải (lift +14.3% so với 1%);
  tương đương Rank-1 mỗi lồng ≥ 10.69%.
- **Không rò rỉ tương lai:** leakage probe (dự báo tại t từ dữ liệu đầy đủ ≡ từ dữ liệu cắt tại t) phải = 0.

## 4. Phát hiện mới trong Pha 0 (back-propagated)

- **N1 — Không thành phần nào (v1 hay v2) vượt NULL_RAND ngoài mẫu.** Toàn bộ 5 điểm yếu là có thật về mặt kỹ thuật,
  nhưng sửa chúng không tạo ra lợi thế đo được (xem bảng trong briefing).
- **N2 — Dị thường cấu trúc thật duy nhất:** đài **XSBT** có chữ số hàng chục `4` xuất hiện ~3–5%/giải từ 2024 (kỳ vọng 10%),
  χ² p ≈ 5e-14, đều trên cả 18 vị trí giải. Cần xác minh toàn vẹn dữ liệu (nguồn scrape) trước khi coi là tín hiệu vật lý.
  Quét sâu (`scratch/anomaly_scan.py`, 531 kiểm định đài × lồng × năm, BH-FDR 5%): **8/8 kết quả có ý nghĩa đều thuộc XSBT**
  (tens 2024/2025/2026, units 2026 chữ số `6` = 4.23%, ma trận 100 số). 65/147 kỳ từ 2024 không có hàng chục `4` (kỳ vọng ≈22).
  34 đài còn lại: không vượt FDR. Chữ số "nóng" năm k sang năm k+1 trung bình 9.89% ± 0.07 (không bền vững).
  Khai thác tối đa XSBT 2026 (né tens-4 & units-6): ≈1.13%/ô < ngưỡng 1.143% → vẫn âm nhẹ.
- **N3 — Ràng buộc sản phẩm:** bộ thông điệp “Đài Chủ Lực / PLAY_PEAK” của Stage 3 dựa trên ngưỡng JointR1 ≥ 1.105% đo
  trong mẫu; ngoài mẫu, chính các ngày được chọn vẫn cho ROI ≈ −12.65% ± 4.7%.
- **N4 — Sổ cái 2026 (+27.5%) là kết quả thiết kế-trong-mẫu (`scratch/ytd_sim_replay.py`).** Chạy lại đúng logic
  `scripts/simulate_ytd_2026_1m.py` (tái tạo 256/299 ngày của `benchmark_ledger.json`) trên các năm luật chưa được tinh chỉnh:
  2026 z=+3.07 (ROI +31.7% ± 10.5 @99.5k) · 2025 z=+0.31 (+2.9% ± 11.0) · 2024 z=0.00 (−0.5% ± 7.7 = đúng mức ngẫu nhiên).
  Số nháy trung bình mỗi số của engine trên mọi đài-ngày: 0.179–0.184 mỗi năm (ngẫu nhiên = 0.180).
- **N5 — Pipeline live hiện tại ≠ logic đã backtest:** `score_station_for_date` + `rank_stations_for_day` chỉ trùng 8/21 ngày
  (01–21/01/2026) với sổ cái (`scratch/production_replay.py`).
- **N6 — Tỷ lệ trả thưởng đang dùng là 99.500đ/18.000đ** (commit `9e2f050`) → kỳ vọng chọn ngẫu nhiên −0.5%, ngưỡng hòa vốn
  1.005%/ô. Ở tỷ lệ này, dị thường XSBT (nếu dữ liệu đúng) cho kỳ vọng ≈ +6% khi né hàng chục `4` → ứng viên lợi thế duy nhất,
  **phụ thuộc hoàn toàn vào xác minh dữ liệu nguồn thứ hai** và rủi ro đối tác của kênh trả thưởng online.
- **Mong muốn của User (17:26):** tin rằng đánh 4 số Bao Lô mỗi ngày có lời dài hạn; cần một chuyên gia toán khái quát
  thành công thức chọn bộ số.

## 4b. Bản chất trò chơi do User cung cấp (18:18) — nguồn gốc thật của dự án

- **Cơ chế vật lý:** lồng cầu cơ học (đài quay tay hoặc máy thổi hơi), tối đa 6 lồng/đài; Bao Lô chỉ phụ thuộc **2 lồng cuối**
  (hàng chục, hàng đơn vị) cho mọi giải; sau mỗi giải 2 bi được **trả lại lồng** rồi quay tiếp (có hoàn lại); thứ tự G8 → ĐB.
  Không rõ lịch thay bộ bi; không có video công khai. ⇒ Mô hình 2 lồng × 18 lượt độc lập là **đúng về vật lý**.
- **Luật nhà cái:** Bao Lô 18.000đ/số, trúng 99.500đ/nháy; không khuyến mãi/hoàn trả; chốt cược trước giờ xổ 1 tiếng;
  không nhận cược khi đang quay. ⇒ Lợi thế nhà cái 0.5%; không có kẽ hở về luật/khuyến mãi/cược muộn.
- **Động lực gốc:** cô của User đánh 5 số cố định mỗi ngày nhiều năm, “trúng 1 là huề, trúng 2 là lời, gần như ngày nào cũng ăn”.
  Ba của User muốn dùng AI tìm bản chất: nhà cái định giá sai hay có lỗ hổng?
- **Kết quả kiểm chứng (`scratch/game_mechanics_probe.py`):** phân phối nháy thực tế khớp lý thuyết Binomial(18, 5%) tới 0.1%
  (P≥1 nháy = 60.2%); ROI trung bình của 20.000 bộ 5 số cố định trong 1.642 ngày = −0.48% (lý thuyết −0.50%); **42.5%** bộ số
  vẫn đang có lãi sau ~4.5 năm (tốt nhất +14.5 triệu) — do dao động ±1.76 triệu/năm lớn gấp ~11 lần mức lỗ kỳ vọng 164k/năm.
  Cơ chế trả bi: lặp chữ số ở lượt kế tiếp 10.00% (chục) / 10.10% (đơn vị) — không có hiệu ứng “bi vừa trả nằm trên”.
- **Giả thuyết “top-2 nóng mỗi lồng ghép 2x2” của User (18:29, `scratch/hot_digit_direct_test.py`):** 10 cửa sổ (5 → toàn bộ
  lịch sử), 6.220 đài-ngày: chữ số được chọn trông nóng 10.8–14.4% trong quá khứ, kỳ kế tiếp ra 9.98–10.12%; tỷ lệ nháy/số
  trung bình 0.996% (hòa vốn 1.005%). Độ “nóng” quan sát khớp mô phỏng lồng công bằng tới 0.01–0.04 điểm. Dữ liệu hiện có
  (447.840 lượt) có SE 0.015 điểm → không thể phân biệt 1.01% với 1.00% (cần ~20 lần dữ liệu).
- **Điểm gãy thiết bị (19:17, `scratch/changepoint_scan.py`):** 64/70 lồng không có dấu vết thay đổi phát hiện được; XSBT lồng chục
  gãy ~04/2024 (bi 4: 10.2% → 3.6%, p<0.0002 sau hiệu chỉnh), XSBT lồng đơn vị ~01/2026 (bi 6 → 4.2%, p=0.0016, sát ngưỡng).
  Yêu cầu: cửa sổ quan sát = “kể từ điểm gãy gần nhất do dữ liệu phát hiện”, không cố định; chỉ hành động khi độ lệch đủ lớn để
  phát hiện kịp (≥ ~2–3 điểm với đài 1 kỳ/tuần).
- **Khảo sát mức tin cậy (19:23, `scratch/confidence_level_survey.py`, User yêu cầu):** 7 mức (50–99%) × 4 cửa sổ × bi nóng/lạnh,
  walk-forward: không cấu hình nào ổn định trên hòa vốn qua các năm; mức 50% (~70k vé) cho ROI −0.04% → −0.8% ± 0.43 (= đánh ngẫu
  nhiên); chỉ “bi lạnh, toàn lịch sử, 99%” dương (+8.7% ± 10.1, 145 vé) và biến mất khi bỏ XSBT. ⇒ Quy tắc ra quyết định nên là
  “lãi kỳ vọng hậu nghiệm > 0 với prior trung thực (Empirical Bayes)”, không phải một mức tin cậy cố định.

## 5. Quyết định đã chốt của User (20:30 – 21:30)

- **Đối tượng sử dụng & mục tiêu thật:** Ba của User (người tin vào xác suất thống kê, muốn có bộ số mỗi sáng qua Telegram để dò vui và kỳ vọng kiếm tiền chợ, dễ gặp rủi ro nếu tự soi cầu hoặc gấp thếp). Hệ thống đóng vai trò **"Chiếc Phanh Kỷ Luật Vốn & Điểm Ngọt Gia Đình"** gửi qua Telegram lúc 05:00 sáng.
- **Cấu trúc Điểm Ngọt (Sweet-Spot Ticket):**
  - Đánh **4 số (`2x2`, vốn chuẩn `72.000đ/ngày`)** cho tỷ lệ **52,0% ngày có lời** (`1 nháy = +27.500đ`, `2 nháy = +127.000đ`) hoặc **5 số Điểm Ngọt Bà Cô (vốn chuẩn `90.000đ/ngày`)** cho tỷ lệ **60,3% ngày có lời** (`1 nháy = +9.500đ`, `2 nháy = +109.000đ`) với mức hao hụt kỳ vọng cực mỏng `-0.50%` (`-360đ` đến `-450đ/ngày`).
  - Định hướng lại kỳ vọng "Tiền chợ" ngay trên tin nhắn Bot AI: Ngày 1 nháy mục tiêu là **Hoàn vốn + Cà phê**; tiền chợ (`220k–450k` ở mức cược chuẩn gia đình `1x–2x`) được thu tự động vào những ngày nổ **2–3 nháy** (13%–23% số ngày), tuyệt đối không nhân gấp `18x` (`1,3 triệu/ngày`) để đòi ăn 500k ngay ở ngày 1 nháy.
- **Quy tắc Lịch Chơi 5/2 ("Càng đánh ít càng tốt — Nghỉ 2 ngày lồng cầu cân bằng nhất tuần"):**
  - Mỗi tuần có 7 ngày (`Thứ 2` → `Chủ Nhật`), Engine tự động chấm điểm độ cân bằng lồng cầu (`chi2_max_overall`, `bf10_max_overall`, `normalized_entropy`) của các đài mở thưởng từng ngày.
  - **2 ngày trong tuần có lồng cầu cân bằng nhất** (hiện tại là **Thứ 2** `Max Chi2 = 15.07` và **Thứ 4** `Max Chi2 = 13.22`, nơi mọi đài đều có `BF10 < 1` và `Entropy >= 0.9938`): Hệ thống báo **`🔴 NGHỈ ĐỊNH KỲ (Lồng cầu quá cân bằng — Quy tắc 5/2 bảo toàn vốn)`** (`0x`).
  - **5 ngày còn lại trong tuần**: Hệ thống chọn 1 Đài chủ lực có độ lệch lồng cầu cao nhất trong ngày, phát bộ số 4 số (`2x2`) và 5 số Điểm Ngọt với hệ số đi vốn **khóa cứng `1.0x` đều tay** (bỏ hoàn toàn mức gấp `1.5x` `PLAY_PEAK` của Engine cũ).
- **Bộ Giám Sát Lồng Cầu Bất Thường (`Cage Anomaly Sentinel`):**
  - Tích hợp cảnh báo tự động khi phát hiện bi lệch vượt ngưỡng kiểm định đa bội (như bi `4` lồng hàng chục của đài Bến Tre `XSBT` vào Thứ 3 tụt xuống `3.6%`, `Chi2 = 50.35`, `BF10 > 1.8e7`) để loại trừ số chết và ưu tiên các quả bi có tần suất vượt trội.

## 6. Non-goals (Ràng buộc loại trừ)

- Không tinh chỉnh siêu tham số trên chính tập OOS để “ép” ROI dương ảo (Goodhart / data-snooping).
- Không dùng hệ số nhân vốn `1.5x` (`PLAY_PEAK`) hay bất kỳ cơ chế gấp thếp nào sau ngày trượt.
- Không khuyến khích tạo đa tài khoản (multi-accounting) để săn khuyến mãi 1% do rủi ro khóa cổng rút tiền (KYC một chiều).
