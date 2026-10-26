# Spec: Giai Đoạn 3 — Chuyên Viên Báo Cáo Định Lượng Tự Động 5h Sáng & Trang Web Giải Trình Chi Tiết (`stage3-live-family-platform`)

**Mã Module:** `stage3-live-family-platform`  
**Trạng thái:** Completed — Verified 100% PASS (Pha 4: VERIFY)  
**Ngày cập nhật:** 2026-10-27  
**Tài liệu tham chiếu gốc (Upstream Single Source of Truth):**
- Bản Ý Định Gốc (Pha 1A): [`specs/stage3-live-family-platform/intent.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/intent.md)
- Phương Án Kiến Trúc Đã Chốt (Pha 1B): [`specs/stage3-live-family-platform/ideas.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/ideas.md)
- Quy Tắc Dòng Tiền & Điểm Hòa Vốn (Giai đoạn 1): [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md)
- Hợp Đồng Đặc Tả Kỹ Thuật Giai Đoạn 2: [`specs/stage2-alpha-discovery/spec.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/spec.md)
- Radar Kiểm Định 35 Đài & Giả Lập Thực Chiến 2026: [`scripts/scan_all_35_stations.py`](file:///C:/sidehustle/XSTK/scripts/scan_all_35_stations.py), [`scripts/simulate_ytd_2026_1m.py`](file:///C:/sidehustle/XSTK/scripts/simulate_ytd_2026_1m.py)
- Báo Cáo Quyết Định Kiến Trúc Giai Đoạn 3: [`reports/stage3_architecture_decision_guide.html`](file:///C:/sidehustle/XSTK/reports/stage3_architecture_decision_guide.html)

---

## 0. Các Quyết Định & Giả Định Kỹ Thuật Đã Khóa (`Locked Decisions & Assumptions`)

1. **Môi trường thực thi chuẩn (`uv` + Python 3.11.17):** Toàn bộ quy trình thu thập dữ liệu, đối soát sổ cái, chấm điểm 35 đài, xuất bản trang Web tĩnh và gửi tin nhắn Telegram được thực thi qua `uv run ...` trên nền bộ thư viện toán học hiện hữu (`numpy`, `scipy`, `pydantic`, `httpx`), không cài thêm bất kỳ SDK AI trả phí hay trình điều khiển cơ sở dữ liệu ngoài nào.
2. **Vận hành 100% bằng Code Toán học Thuần túy (`100% Pure Mathematical Python — Zero AI API`):** Tuyệt đối không gọi bất kỳ API LLM bên ngoài nào (OpenAI, Gemini, Claude). Toàn bộ lời văn nhận định và giải trình lý do *"Vì sao hôm nay nên đánh hay nên nghỉ"* trên Telegram và trên Trang Web đều được sinh tự động tất định (`Deterministic Quantitative NLG`) từ chính các chỉ số kiểm định toán học thực tế của ngày hôm đó ($\chi^2$, $BF_{10}$, phân vị Monte Carlo Null $P_{90}/P_{95}$, độ dài trạng thái `BOCD`, tần suất nổ bóng Hạng 1 ngoài mẫu OOS so với mốc hòa vốn $10.6904\%$, và OOS ROI 3 năm).
3. **Kiến trúc Không Database Siêu Bền Bỉ (`Zero-Database GitOps Static Stack`):** Không sử dụng tính năng nhập tiền thủ công rườm rà của từng người và không dùng Database động (không dùng Supabase hay Cloudflare D1). Toàn bộ dữ liệu lịch sử 35 đài (`data/raw_all/<CODE>_draws.json`) và sổ cái đối soát của **Quỹ Chuẩn Tham Chiếu Tự Động (`data/live/benchmark_ledger.json`)** được lưu trữ dưới dạng tệp JSON có mã kiểm chuẩn `SHA-256` ngay trong kho lưu trữ Git, xuất bản Trang Web Báo cáo Tĩnh (`public/index.html` & `public/daily/YYYY-MM-DD.html`) lên `GitHub Pages` / `Cloudflare Pages` và gửi bản tin qua `Telegram Bot API` với chi phí 0 đồng trọn đời.
4. **Tương thích Ngược Tuyệt đối với Bộ Kiểm thử Giai đoạn 2 (`100% Backward Compatibility with Stage 2 Suite`):**
   - Giữ nguyên bất biến `STATION_CONFIG` (`XSHCM`, `XSVL`), `VALID_STATIONS` và 8 cấu hình gốc trong `SWEET_SPOT_CONFIGS` của [`src/xsmn_alpha/constants.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/constants.py) để toàn bộ bài kiểm thử Giai đoạn 2 ([`tests/test_constants_and_schemas.py`](file:///C:/sidehustle/XSTK/tests/test_constants_and_schemas.py), [`tests/test_pillar4_walk_forward_backtest.py`](file:///C:/sidehustle/XSTK/tests/test_pillar4_walk_forward_backtest.py)) tiếp tục vượt qua 100% mà không cần sửa đổi bất kỳ assertion cũ nào.
   - Bổ sung danh mục chuẩn 35 đài `STATION_REGISTRY_35` (`VALID_35_STATION_CODES` gồm 21 đài Miền Nam quay lúc `16:15` + 14 đài Miền Trung quay lúc `17:15`) và cấu hình đối xứng **`"4x1"` (Top 4 Chục $\times$ Top 1 Đơn vị = 4 số)** vào `STAGE3_TICKET_CONFIGS` (`"2x2"`, `"1x4"`, `"4x1"`, `"3x3"`, `"core_2x2_sat_3x3"`) cùng `EXTENDED_SWEET_SPOT_CONFIGS` trong [`src/xsmn_alpha/constants.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/constants.py) và [`src/xsmn_alpha/backtest/sweet_spot_sim.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/backtest/sweet_spot_sim.py).
5. **Quỹ Chuẩn Tham Chiếu Tự Động (`Automated Reference Benchmark Fund — 1.000.000 VNĐ`):** Hệ thống duy trì một Quỹ Chuẩn tự động khởi đầu với vốn gốc $W_0 = \mathbf{1.000.000\text{ VNĐ}}$ (khởi tạo nối tiếp từ kết quả kiểm chứng thực chiến năm 2026), mức cược cơ sở `1.0x = 72.000 VNĐ/ngày` (`18.000 VNĐ/số` cho bộ 4 số, trúng 1 nháy thu `87.500 VNĐ`). Sau mỗi kỳ mở thưởng, hệ thống tự động đối soát 18 giải để tính Lãi/Lỗ thực tế, cập nhật Số dư ($W_t$) và Quỹ Lãi Ròng ($C_t = \max(0, W_t - W_0)$) làm cơ sở tính hệ số đi vốn CPPI / House-Money (`0.0x`, `1.0x`, `1.25x`, `1.5x`).
6. **Chế Độ Chạy Thử An Toàn Không Cần Token (`Safe Local Dry-Run Fallback`):** Các thông số kết nối (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PUBLIC_REPORT_BASE_URL`) được đọc từ biến môi trường (hoặc GitHub Secrets). Khi chạy với cờ `--dry-run` hoặc khi chưa khai báo biến môi trường trên máy local, hệ thống vẫn chạy trọn vẹn 100% quy trình toán học, xuất trang Web HTML và lưu bản xem trước tin nhắn Telegram ra `data/live/latest_telegram_preview.txt` mà không báo lỗi kết nối.

---

## 1. Objective (Mục Tiêu & Phạm Vi)

### 1.1. Mục tiêu cốt lõi
Xây dựng hệ thống **"Chuyên viên Báo cáo Định lượng Trung thực Tự động 100%" (`Automated 05:00 AM Quantitative Reporter & Web Audit Platform`)** vận hành hoàn toàn bằng code Toán học & Thống kê thuần túy (`NumPy`/`SciPy`), tự động thu thập kết quả mở thưởng của **35 đài XSMN & XSMT**, tự động đối soát hiệu quả của **Quỹ Chuẩn Tham Chiếu (`1.000.000 VNĐ`)**, tái hiệu chuẩn mô hình lồng cầu mỗi ngày, xuất bản **Trang Web Báo Cáo Giải Trình Chi Tiết** và gửi **Bản Tin Tóm Tắt Chiến Thuật lúc 05:00 sáng qua Telegram** trả lời trực diện 4 câu hỏi cốt lõi cho gia đình.

### 1.2. Năm trụ cột chức năng bắt buộc
1. **Trụ cột 1 — Mở Rộng Lõi 35 Đài XSMN/XSMT, Thu Thập Tăng Trưởng Đa Nguồn & Cấu Hình `4x1` (`35-Station Registry, Incremental Multi-Source Fetcher & Symmetric 4x1 Config`):**
   - Chuẩn hóa danh mục **35 đài** (21 đài Miền Nam mở thưởng `16:15 ICT`, 14 đài Miền Trung mở thưởng `17:15 ICT`) với lịch quay chính xác theo từng thứ trong tuần (Thứ 2 $\to$ Chủ Nhật).
   - Tự động cào kết quả 18 giải mới nhất từ `minhngoc.net.vn` kèm cơ chế tự động chuyển đổi dự phòng 3 tầng (`minhngoc.net.vn` $\to$ `xskt.com.vn` $\to$ `xoso.com.vn`), kiểm định nghiêm ngặt qua `DataSchemaGate` (đủ 18 giải, tổng đếm mỗi lồng $= 18$, chống trùng lặp ngày) và lưu vào `data/raw_all/<CODE>_draws.json` kèm chữ ký `SHA-256`.
   - Mở rộng [`src/xsmn_alpha/backtest/sweet_spot_sim.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/backtest/sweet_spot_sim.py) để hỗ trợ đầy đủ **5 cấu hình bộ số ngọt chuẩn**: `2x2` (4 số), `1x4` (4 số), `4x1` (4 số — đối xứng cho đài lệch mạnh Lồng Đơn Vị), `3x3` (9 số), và `core_2x2_sat_3x3` (`Hybrid` 4 số Lõi + 5 số Vệ tinh).
2. **Trụ cột 2 — Sổ Cái Đối Soát Tự Động Quỹ Chuẩn Tham Chiếu & Quản Trị Vốn CPPI / House-Money (`Automated Benchmark Settlement Ledger & House-Money Sizing Engine`):**
   - Duy trì tệp sổ cái `data/live/benchmark_ledger.json` ghi nhận trung thực từng ngày khuyến nghị, bộ số đã chọn, hệ số vốn đã áp dụng, kết quả 18 giải thực tế sau giờ quay, số nháy nổ ($K$), danh sách giải nổ, tiền cược, tiền thu, lãi/lỗ ròng, số dư lũy kế $W_t$, Quỹ Lãi Ròng $C_t = \max(0, W_t - W_0)$ và mức sụt giảm tối đa (`Max Drawdown`).
   - Thực thi nghiêm ngặt quy tắc đi vốn **Bảo toàn 100% Vốn gốc (`CPPI + House-Money`)**: `0.0x` vào ngày cầu nhiễu trắng (`SKIP_NO_EDGE`), `1.0x` tiêu chuẩn, và chỉ nâng lên `1.25x – 1.5x` khi Quỹ Lãi Ròng $C_{t-1} \ge 144.000\text{ VNĐ}$ (tối thiểu 2 ngày cược cơ sở) sao cho phần tiền cược tăng thêm $\Delta \text{Cost}_t \le 0.50 \times C_{t-1}$ và $W_{t-1} - \text{Cost}_t \ge W_0$.
3. **Trụ cột 3 — Chuyên Viên Chấm Điểm Đài Hàng Ngày & Sinh Lời Giải Trình Định Lượng Tất Định (`Daily Station Analyst & Deterministic Quantitative NLG`):**
   - Với toàn bộ 5–7 đài có lịch mở thưởng trong ngày mục tiêu $D$, chạy kiểm định thống kê đa cửa sổ $W \in \{15, 30, 60\}$ kỳ ($\chi^2$, $BF_{10}$, Entropy) đối chiếu với 1,000 kịch bản Monte Carlo Null, kết hợp `CalibratedProbabilityPooler` (`BayesianDirichletBOCD` + `RegularizedMarkovGapModel`) và đánh giá Walk-Forward OOS 3 năm nghiêm ngặt trước ngày $D$ (`draw_date < D`).
   - Xếp hạng các đài mở thưởng trong ngày, chọn **Đài Ưu Tiên Số 1** (và Đài Phụ nếu đạt chuẩn), chọn cấu hình ghép số tối ưu nhất trong 5 cấu hình, phân hạng tín hiệu ngày (`PLAY_PEAK`, `PLAY_STANDARD`, `PLAY_CAUTIOUS`, `SKIP_NO_EDGE`), và sinh tự động lời văn giải trình toán học tiếng Việt rõ ràng, trung thực 100%.
4. **Trụ cột 4 — Trình Xuất Trang Web Báo Cáo Giải Trình Chi Tiết Tĩnh (`Static HTML Daily Audit Report & Index Dashboard Generator`):**
   - Sinh tự động trang báo cáo chi tiết từng ngày tại `public/daily/YYYY-MM-DD.html` (kèm bản lưu JSON `public/daily/YYYY-MM-DD.json`) và cập nhật trang chủ tổng hợp `public/index.html` với giao diện Dark-Mode chuẩn mực, tốc độ tải tức thì, trình bày đầy đủ 5 khu vực bằng chứng toán học.
5. **Trụ cột 5 — Trình Phát Bản Tin Chiến Thuật 05:00 Sáng Qua Telegram & Luồng Tự Động GitHub Actions (`05:00 AM Telegram Executive Dispatcher & Zero-Cost GitOps Workflow`):**
   - Đúng `05:00 ICT` mỗi sáng, gửi tin nhắn tóm tắt chiến thuật vào Telegram trả lời trực diện 4 câu hỏi cốt lõi (*1. Có nên đánh hôm nay không & Vì sao? 2. Đánh đài gì, khu vực nào? 3. Đánh bộ số nào? 4. Đi vốn như thế nào?*) kèm đường link mở trực tiếp Trang Web Báo Cáo Chi Tiết của ngày hôm đó.
   - Đóng gói quy trình tự động trong `.github/workflows/daily_quant_report.yml` vận hành miễn phí 100% trên GitHub Actions + GitHub Pages / Cloudflare Pages.

---

## 2. Tech Stack (Công Nghệ & Thư Viện Chuẩn)

- **Ngôn ngữ & Runtime:** Python `3.11.17` quản lý qua `uv 0.13.1` ([`pyproject.toml`](file:///C:/sidehustle/XSTK/pyproject.toml) + `uv.lock`).
- **Thư viện Tính toán, Kiểm định & Mạng (`dependencies` — Không dùng AI API, Không dùng Database ngoài):**
  - `numpy >= 1.26.0, < 2.2.0` — Tính toán vector/ma trận, đại số tuyến tính, BOCD trellis và Monte Carlo Null (`PCG64(seed=42)`).
  - `scipy >= 1.12.0` — Kiểm định thống kê ($\chi^2$, `gammaln` cho Dirichlet-Multinomial Bayes Factor $BF_{10}$, tối ưu hóa lồi `SLSQP` cho Brier Pooling).
  - `pydantic >= 2.7.0` — Kiểm tra hợp đồng dữ liệu đầu vào/đầu ra nghiêm ngặt (`StrictBaseModel`, `extra="forbid"`, `allow_inf_nan=False`).
  - `httpx >= 0.27.0` — Thu thập kết quả xổ số 35 đài bất đồng bộ có retry/failover và gửi bản tin qua `Telegram Bot HTTP API`.
- **Hạ tầng Tự động hóa & Xuất bản Web Miễn phí (`Zero-Cost Infrastructure`):**
  - `GitHub Actions` — Lập lịch tự động thu thập kết quả sau giờ quay và phát bản tin lúc `05:00 ICT` (`22:00 UTC`).
  - `GitHub Pages` / `Cloudflare Pages` — Lưu trữ và phục vụ trang Web báo cáo tĩnh (`public/index.html` & `public/daily/YYYY-MM-DD.html`).
  - `Telegram Bot API` — Gửi tin nhắn định dạng HTML chuẩn qua endpoint `https://api.telegram.org/bot<TOKEN>/sendMessage`.
- **Thư viện Kiểm thử & Chất lượng Mã nguồn (`dev-dependencies`):**
  - `pytest >= 8.2.0`, `pytest-cov >= 5.0.0` (độ phủ mã nguồn yêu cầu $\ge 90\%$), `ruff >= 0.5.0`.

---

## 3. Commands (Các Câu Lệnh Thực Thi Chuẩn)

Tất cả câu lệnh được thực thi tại thư mục gốc `C:\sidehustle\XSTK` thông qua `uv`:

```powershell
# 1. Đồng bộ môi trường ảo và dependencies
uv sync --all-extras

# 2. Thu thập & cập nhật tăng trưởng kết quả 18 giải mới nhất cho toàn bộ 35 đài (21 XSMN + 14 XSMT)
uv run python -m xsmn_alpha.cli sync-35 --date 2026-10-26 --raw-dir data/raw_all/

# 3. Đối soát tự động kết quả mở thưởng vào Sổ cái Quỹ Chuẩn Tham Chiếu (1.000.000 VNĐ)
uv run python -m xsmn_alpha.cli settle-ledger --date 2026-10-25 --ledger data/live/benchmark_ledger.json --raw-dir data/raw_all/

# 4. Chạy trọn vẹn quy trình Báo cáo Định lượng 05:00 sáng (Đối soát + Chấm điểm đài ngày D + Xuất Web + Xem trước Telegram Dry-Run)
uv run python -m xsmn_alpha.cli daily-report --date 2026-10-26 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram --dry-run

# 5. Gửi bản tin 05:00 sáng thực tế tới Telegram (khi đã cấu hình TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID)
uv run python -m xsmn_alpha.cli daily-report --date 2026-10-26 --raw-dir data/raw_all/ --ledger data/live/benchmark_ledger.json --public-dir public/ --send-telegram

# 6. Chạy toàn bộ bộ kiểm thử (Stage 2 + Stage 3 Unit, Invariant & Adversarial Negative Mutation Tests) kèm đo Coverage
uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-report=term-missing --cov-fail-under=90

# 7. Kiểm tra chất lượng mã nguồn (Lint & Format check)
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

---

## 4. Project Structure (Cấu Trúc Thư Mục Dự Án)

```text
C:\sidehustle\XSTK\
├── .github/
│   └── workflows/
│       └── daily_quant_report.yml           # [GĐ 3] Workflow GitHub Actions tự động cào KQ, xuất Web & gửi Telegram 05:00 sáng
├── QUY_TAC_VA_DIEM_HOA_VON.md               # [GĐ 1] Quy ước gốc dòng tiền & Điểm hòa vốn (Bất biến)
├── specs/
│   ├── stage2-alpha-discovery/              # [GĐ 2] Hồ sơ đặc tả Giai đoạn 2 (Đã hoàn tất)
│   └── stage3-live-family-platform/
│       ├── intent.md                        # [Pha 1A] Bản đúc kết ý định GĐ 3 đã xác nhận
│       ├── ideas.md                         # [Pha 1B] Kiến trúc Chuyên viên Báo cáo 5h sáng & Web Giải trình
│       ├── spec.md                          # [Pha 1C] Hợp đồng đặc tả kỹ thuật GĐ 3 (File này)
│       ├── plan.md                          # [Pha 2] Kế hoạch triển khai kiến trúc (Tạo ở Pha 2)
│       └── todo.md                          # [Pha 2] Danh sách tác vụ chi tiết (Tạo ở Pha 2)
├── pyproject.toml                           # Cấu hình dự án Python & dependencies cho uv
├── src/
│   └── xsmn_alpha/
│       ├── __init__.py
│       ├── constants.py                     # Hằng số GĐ 1-3 (Bổ sung STATION_REGISTRY_35, cấu hình 4x1, hằng số Quỹ Chuẩn VNĐ)
│       ├── schemas.py                       # Pydantic v2 Schemas GĐ 2 & GĐ 3 (StrictBaseModel, Fail-Closed Validators)
│       ├── exceptions.py                    # Hệ thống ngoại lệ Fail-Closed (bổ sung CapitalDisciplineError)
│       ├── ingest/                          # [GĐ 2] Bộ thu thập & chuẩn hóa cơ sở
│       ├── features/                        # [GĐ 2] Trích xuất đặc trưng với khóa Pre-Draw (t-1)
│       ├── falsification/                   # [GĐ 2] Phễu kiểm định bác bỏ nhiễu & 1,000 Monte Carlo Null
│       ├── engine/                          # [GĐ 2] Hội đồng xác suất hiệu chuẩn P_AI(0..9) (BOCD + Markov-Gap + Pooler)
│       ├── backtest/                        # [GĐ 2 & 3] Kiểm thử trượt Điểm Ngọt (mở rộng hỗ trợ 4x1 trong sweet_spot_sim.py)
│       ├── reporting/                       # [GĐ 2] Báo cáo đối chiếu 2 đài chuẩn
│       ├── live/                            # [GĐ 3 - MỚI] Hệ thống Chuyên viên Báo cáo Tự động 5h Sáng & Web Giải trình
│       │   ├── __init__.py
│       │   ├── registry.py                  # Danh mục chuẩn 35 đài (21 MN 16:15 + 14 MT 17:15), lịch mở thưởng Thứ 2 -> CN
│       │   ├── multi_fetcher.py             # Thu thập tăng trưởng đa nguồn cho 35 đài + Failover 3 tầng + SHA-256
│       │   ├── ledger.py                    # Quản lý Sổ cái Quỹ Chuẩn (benchmark_ledger.json), đối soát 18 giải & tính House-Money
│       │   ├── daily_analyst.py             # Chấm điểm 5-7 đài mở thưởng ngày D, tối ưu 5 cấu hình & sinh lời giải trình NLG tất định
│       │   ├── web_publisher.py             # Xuất trang Web giải trình chi tiết (public/daily/YYYY-MM-DD.html & public/index.html)
│       │   └── telegram_bot.py              # Định dạng bản tin 05:00 sáng (4 câu hỏi cốt lõi + link Web) & gửi qua Telegram Bot API
│       └── cli.py                           # Giao diện dòng lệnh hợp nhất (ingest, falsify, run-pipeline, sync-35, settle-ledger, daily-report)
├── data/
│   ├── raw/                                 # Cache dữ liệu thô GĐ 2 (XSHCM, XSVL)
│   ├── raw_all/                             # Cache dữ liệu lịch sử 35 đài XSMN/XSMT (<CODE>_draws.json kèm SHA-256)
│   ├── canonical/                           # Dữ liệu chuẩn hóa
│   ├── outputs/                             # Dữ liệu đầu ra kiểm thử & cache Walk-Forward
│   └── live/                                # [GĐ 3] Sổ cái đối soát Quỹ Chuẩn (benchmark_ledger.json) & bản xem trước Telegram
├── public/                                  # [GĐ 3] Thư mục gốc xuất bản Trang Web Tĩnh (GitHub Pages / Cloudflare Pages)
│   ├── index.html                           # Trang chủ Dashboard tổng hợp Quỹ Chuẩn & danh sách báo cáo các ngày
│   └── daily/
│       ├── YYYY-MM-DD.html                  # Trang Web Báo cáo Giải trình Chi tiết của từng ngày
│       └── YYYY-MM-DD.json                  # Dữ liệu kiểm toán JSON của ngày tương ứng
├── reports/                                 # Các báo cáo phân tích & kiểm chứng lịch sử
└── tests/                                   # Bộ kiểm thử tự động (PASS + Adversarial Negative Mutation FAIL, coverage >= 90%)
    ├── conftest.py
    ├── test_constants_and_schemas.py        # [GĐ 2] Giữ nguyên 100%
    ├── test_pillar1_ingest_and_features.py  # [GĐ 2] Giữ nguyên 100%
    ├── test_pillar2_falsification_gatekeeper.py
    ├── test_pillar3_calibrated_engine.py
    ├── test_pillar4_walk_forward_backtest.py
    ├── test_adversarial_mutations.py
    ├── test_stage3_registry_and_4x1.py      # [GĐ 3] Kiểm thử 35 đài, lịch mở thưởng, cấu hình 4x1 & multi_fetcher
    ├── test_stage3_ledger_and_house_money.py# [GĐ 3] Kiểm thử Sổ cái Quỹ Chuẩn, đối soát 18 giải & Gate 5 House-Money
    ├── test_stage3_daily_analyst_and_nlg.py # [GĐ 3] Kiểm thử chấm điểm đài ngày D, khóa Pre-Draw & sinh lời văn NLG tất định
    └── test_stage3_web_and_telegram.py      # [GĐ 3] Kiểm thử xuất Web 5 khu vực, bản tin Telegram 4 mục & chống Injection
```

---

## 5. Hợp Đồng Dữ Liệu, Công Thức Toán Học & Cổng Kiểm Soát Đối Kháng (`Data Contracts, Math Spec & Adversarial Gates`)

### 5.1. Hệ Hằng Số Tài Chính, 5 Cấu Hình Bộ Số Ngọt & Quy Ước Quỹ Chuẩn VNĐ

| Hằng số (`constants.py`) | Công thức / Giá trị | Ý nghĩa trong Giai đoạn 3 |
| :--- | :---: | :--- |
| `REAL_PAYOUT_1D` | `87.5` ($\frac{70}{0.8}$) | Hệ số trả thưởng thực tế trên 1 đồng vốn sau chiết khấu 20% |
| `PRIZES_PER_DRAW` | `18` | Tổng số giải mở thưởng trong 1 kỳ của mỗi đài Miền Nam & Miền Trung |
| `BAO_LO_PAYOUT_PER_HIT` | `4.861111111111111` ($\frac{87.5}{18}$) | Số đồng thu về cho mỗi 1 nháy (1 lô) khi đặt `1.0đ`/số Bao Lô 18 giải |
| `BE_PROB_SINGLE_BALL` | `0.10690449676496976` ($\approx 10.6904\%$) | Xác suất hòa vốn tối thiểu của 1 quả bóng đơn lẻ trên mỗi lồng cầu ($\text{Lift} +6.9045\%$) |
| `BE_PROB_2D_NUMBER` | `0.011428571428571429` ($\approx 1.1429\%$) | Xác suất hòa vốn của 1 bộ số 2 chữ số trong mỗi giải ($\text{Lift} +14.2857\%$) |
| `SELECTIVE_ALPHA_JOINT_R1_MIN_PCT` | `1.105` ($1.105\%$) | Ngưỡng xác suất nổ đồng thời tối thiểu của cặp bóng Hạng 1 ($\hat{p}_{\text{tens, R1}} \times \hat{p}_{\text{units, R1}} \ge 1.105\%$, tức $\text{Lift} \ge +10.5\%$) để vượt qua bộ lọc Báo Nghỉ |
| `PEAK_CONVICTION_JOINT_R1_PCT` | `1.150` ($1.150\%$) | Ngưỡng hội tụ đỉnh của cặp bóng Hạng 1 ($\ge 1.150\%$) hoặc OOS ROI $\ge +8.0\%$ để kích hoạt trạng thái `PLAY_PEAK` |
| `BENCHMARK_INITIAL_BANKROLL_VND` | `1_000_000` (`1.000.000 VNĐ`) | Vốn gốc khởi đầu bất khả xâm phạm ($W_0$) của Quỹ Chuẩn Tham Chiếu Tự Động |
| `BENCHMARK_STAKE_PER_NUMBER_VND` | `18_000` (`18.000 VNĐ/số`) | Mức cược cơ sở `1.0x` cho 1 con số Bao lô 18 giải (`1.000 VNĐ/giải` $\times 18$ giải) |
| `BENCHMARK_BASE_DAILY_COST_4NUM_VND` | `72_000` (`72.000 VNĐ/ngày`) | Tổng vốn cược cơ sở `1.0x` cho bộ 4 số (`2x2`, `1x4`, `4x1`) |
| `BENCHMARK_PAYOUT_PER_HIT_VND` | `87_500` (`87.500 VNĐ/nháy`) | Số tiền thực thu về cho mỗi 1 nháy trúng ở mức cược cơ sở `1.0x` (trúng 1 nháy lãi ròng `+15.500 VNĐ`) |
| `HOUSE_MONEY_MIN_BUFFER_DAYS` | `2` (`144.000 VNĐ`) | Quỹ Lãi Ròng tối thiểu ($C_t \ge 2 \times 72.000 = 144.000\text{ VNĐ}$) trước khi cho phép nâng hệ số vốn lên `1.25x` hoặc `1.5x` |
| `HOUSE_MONEY_MAX_SURPLUS_FRACTION` | `0.50` ($50\%$) | Trần trích Quỹ Lãi Ròng cho phần vốn tăng thêm: $\Delta \text{Cost}_t = (m_t - 1.0) \times \text{BaseCost} \le 0.50 \times C_{t-1}$ |
| `SAMPLE_CAPITAL_TIERS_VND` | `(500_000, 1_000_000, 2_000_000, 5_000_000)` | 4 mốc quy mô vốn mẫu (`500k`, `1 Triệu`, `2 Triệu`, `5 Triệu`) hiển thị trong bảng quy đổi tiền VNĐ trên Web & Telegram |

#### Bảng 5 Cấu Hình Bộ Số Ngọt Chuẩn Của Giai Đoạn 3 (`STAGE3_TICKET_CONFIGS`)

| Mã cấu hình (`config_id`) | Quy tắc ghép bóng (Lồng Chục $\times$ Lồng Đơn Vị) | Số lượng số | Vốn đơn vị chuẩn (`cost_per_draw`) | Tiền cược chuẩn `1.0x` (`18.000đ/số`) | Tiền thu mỗi nháy (`1.0x`) | Số nháy tối thiểu có lãi | Điểm hòa vốn 30 kỳ (`be_hits_30_draws`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`2x2`** | Top 2 Chục $\times$ Top 2 Đơn vị | `4 số` | `4.0đ` | `72.000 VNĐ` | `87.500 VNĐ` | `1 nháy` (`+15.500đ`) | `24.69 lô` (mục tiêu $\ge 25$) |
| **`1x4`** | Top 1 Chục $\times$ Top 4 Đơn vị | `4 số` | `4.0đ` | `72.000 VNĐ` | `87.500 VNĐ` | `1 nháy` (`+15.500đ`) | `24.69 lô` (mục tiêu $\ge 25$) |
| **`4x1`** *(Mới)* | Top 4 Chục $\times$ Top 1 Đơn vị | `4 số` | `4.0đ` | `72.000 VNĐ` | `87.500 VNĐ` | `1 nháy` (`+15.500đ`) | `24.69 lô` (mục tiêu $\ge 25$) |
| **`3x3`** | Top 3 Chục $\times$ Top 3 Đơn vị | `9 số` | `9.0đ` | `162.000 VNĐ` | `87.500 VNĐ` | `2 nháy` (`+13.000đ`) | `55.54 lô` (mục tiêu $\ge 56$) |
| **`core_2x2_sat_3x3`** | 4 số Lõi `2x2` (`1.0` phần) + 5 số Vệ tinh (`0.5` phần) | `9 số` | `6.5đ` | `117.000 VNĐ` | Lõi `87.500đ` / VT `43.750đ` | `2 nháy` (hoặc `1 Lõi + 1 VT = +14.250đ`) | `40.11 lô` quy đổi (mục tiêu $\ge 41$) |

---

### 5.2. Danh Mục Chuẩn 35 Đài XSMN/XSMT & Lịch Mở Thưởng Theo Thứ (`STATION_REGISTRY_35`)

Module [`src/xsmn_alpha/live/registry.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/registry.py) định nghĩa bất biến toàn bộ **35 đài** (21 đài Miền Nam quay lúc `16:15 ICT`, 14 đài Miền Trung quay lúc `17:15 ICT`) với mã đài, tên tiếng Việt, khu vực, khung giờ mở thưởng, các ngày mở thưởng trong tuần (`0 = Thứ 2, ..., 6 = Chủ Nhật`), số kỳ/tuần (`1` hoặc `2`), cỡ mẫu 3 năm (`156` hoặc `312` kỳ), và bộ slug cho cả 3 nguồn (`minhngoc.net.vn`, `xskt.com.vn`, `xoso.com.vn`):

| Thứ trong tuần (`weekday`) | Đài Mở Thưởng Miền Nam (`16:15 ICT` — 21 Đài) | Đài Mở Thưởng Miền Trung (`17:15 ICT` — 14 Đài) | Tổng số đài trong ngày |
| :--- | :--- | :--- | :---: |
| **Thứ Hai (`0`)** | `XSHCM` (TP. Hồ Chí Minh), `XSDT` (Đồng Tháp), `XSCM` (Cà Mau) | `XSTTH` (Thừa Thiên Huế), `XSPY` (Phú Yên) | **5 đài** |
| **Thứ Ba (`1`)** | `XSBT` (Bến Tre), `XSVT` (Vũng Tàu), `XSBL` (Bạc Liêu) | `XSDLK` (Đắk Lắk), `XSQNM` (Quảng Nam) | **5 đài** |
| **Thứ Tư (`2`)** | `XSDN` (Đồng Nai), `XSCT` (Cần Thơ), `XSST` (Sóc Trăng) | `XSDNG` (Đà Nẵng), `XSKH` (Khánh Hòa) | **5 đài** |
| **Thứ Năm (`3`)** | `XSTN` (Tây Ninh), `XSAG` (An Giang), `XSBTH` (Bình Thuận) | `XSBDI` (Bình Định), `XSQT` (Quảng Trị), `XSQB` (Quảng Bình) | **6 đài** |
| **Thứ Sáu (`4`)** | `XSVL` (Vĩnh Long), `XSBD` (Bình Dương), `XSTV` (Trà Vinh) | `XSGL` (Gia Lai), `XSNT` (Ninh Thuận) | **5 đài** |
| **Thứ Bảy (`5`)** | `XSHCM` (TP. Hồ Chí Minh), `XSLA` (Long An), `XSBP` (Bình Phước), `XSHG` (Hậu Giang) | `XSDNG` (Đà Nẵng), `XSQNG` (Quảng Ngãi), `XSDNO` (Đắk Nông) | **7 đài** |
| **Chủ Nhật (`6`)** | `XSTG` (Tiền Giang), `XSKG` (Kiên Giang), `XSDL` (Đà Lạt) | `XSTTH` (Thừa Thiên Huế), `XSKH` (Khánh Hòa), `XSKT` (Kon Tum) | **6 đài** |

- **4 đài mở thưởng 2 kỳ/tuần (`target_3y = 312` kỳ):** `XSHCM` (Thứ 2, Thứ 7), `XSTTH` (Thứ 2, Chủ Nhật), `XSDNG` (Thứ 4, Thứ 7), `XSKH` (Thứ 4, Chủ Nhật).
- **31 đài mở thưởng 1 kỳ/tuần (`target_3y = 156` kỳ):** Tất cả các đài còn lại.

---

### 5.3. Công Thức Toán Học Cho Chấm Điểm Đài Hàng Ngày, Chọn Cấu Hình & Quản Trị Vốn CPPI / House-Money

#### A. Đánh Giá Nhân Quả Nghiêm Ngặt Trước Ngày Mở Thưởng (`Strict Pre-Draw Evaluation < D`)
Đối với ngày mục tiêu $D$ (chạy lúc `05:00 sáng` ngày $D$ trước khi lồng cầu quay lúc `16:15` / `17:15`), với mỗi đài $s$ có lịch mở thưởng vào thứ của ngày $D$:
1. **Lọc lịch sử quá khứ nghiêm ngặt:** Chỉ lấy chuỗi kỳ quay chuẩn hóa $\mathcal{H}_{s, <D} = \{r \in \text{draws}_s \mid r.\text{draw\_date} < D\}$ (tối đa $N_{3Y} \in \{156, 312\}$ kỳ gần nhất tính đến trước ngày $D$). Nếu xuất hiện bất kỳ bản ghi nào có `draw_date >= D` trong đầu vào tính toán, `PreDrawCutoffGate` ném `TemporalLeakageError` ngay lập tức.
2. **Kiểm định thống kê đa cửa sổ & Đối chứng 1,000 chuỗi Monte Carlo Null:**
   - Tính thống kê $\chi^2_W$, Hệ số Bayes $BF_{10}^{(W)}$ và Entropy chuẩn hóa $H_{\text{norm}}^{(W)}$ trên 3 cửa sổ $W \in \{15, 30, 60\}$ kỳ gần nhất của $\mathcal{H}_{s, <D}$ cho từng lồng cầu (`tens_cage`, `units_cage`).
   - Đối chiếu $\chi^2_{\max} = \max_{W \in \{15,30,60\}} \chi^2_W$ với ngưỡng phân vị $P_{90}, P_{95}$ của $1,000$ chuỗi ngẫu nhiên giả lập (`seed=42`).
3. **Dự báo Xác suất Hiệu chuẩn 10 Quả bóng (`CalibratedProbabilityPooler`) cho kỳ mở thưởng ngày $D$:**
   - Chạy `CalibratedProbabilityPooler.predict_cage` trên $\mathcal{H}_{s, <D}$ để thu được:
     - Vector xác suất hiệu chuẩn 10 bóng Lồng Chục $\mathbf{p}_{s, D}^{\text{tens}} = [p_0^{\text{tens}}, \dots, p_9^{\text{tens}}]$ ($\sum_{i=0}^9 p_i^{\text{tens}} = 1.0$) và thứ hạng bóng $a_{(1)}, \dots, a_{(10)}$.
     - Vector xác suất hiệu chuẩn 10 bóng Lồng Đơn Vị $\mathbf{p}_{s, D}^{\text{units}} = [p_0^{\text{units}}, \dots, p_9^{\text{units}}]$ ($\sum_{j=0}^9 p_j^{\text{units}} = 1.0$) và thứ hạng bóng $b_{(1)}, \dots, b_{(10)}$.
     - Độ dài chế độ hậu nghiệm cực đại (`map_run_length` $r^*_{t-1}$) từ nhánh `BayesianDirichletBOCD` để nhận diện nhà đài vừa thay bóng/bảo trì máy ($r^*_{t-1} \le 4$) hay đang duy trì chế độ ổn định ($r^*_{t-1} \ge 15$).
   - Ma trận xác suất kết hợp 100 con số (`00`–`99`):
     $$P_{s, D}(ab) = p_a^{\text{tens}} \times p_b^{\text{units}}, \quad \sum_{a=0}^{9}\sum_{b=0}^{9} P_{s, D}(ab) = 1.0$$
4. **Đo Hiệu suất Walk-Forward Out-of-Sample (OOS) Quá khứ ($< D$) và Chọn Cấu hình Bộ số Tối ưu:**
   - Trên chuỗi kiểm thử trượt ngoài mẫu của $\mathcal{H}_{s, <D}$ (sau `warmup_draws = 45` kỳ), tính:
     - Tần suất nổ thực tế ngoài mẫu của bóng Hạng 1 Lồng Chục $\hat{p}_{s, \text{tens, R1}}^{(<D)}$ và Lồng Đơn Vị $\hat{p}_{s, \text{units, R1}}^{(<D)}$ (mốc chuẩn ngẫu nhiên $= 10.00\%$, mốc hòa vốn đơn bóng $= 10.6904\%$).
     - Tần suất nổ đồng thời quy đổi của cặp bóng Hạng 1:
       $$\hat{p}_{s, \text{joint, R1}}^{(<D)} = \hat{p}_{s, \text{tens, R1}}^{(<D)} \times \hat{p}_{s, \text{units, R1}}^{(<D)} \quad (\text{tính theo } \%, \text{ mốc nền ngẫu nhiên } = 1.000\%)$$
     - Hiệu suất OOS ($\text{ROI}_{\text{cfg}}^{(<D)}$, tỷ lệ ngày thắng, số nháy/30 kỳ) của cả **5 cấu hình**: `2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`.
   - **Quy tắc chọn cấu hình khuyến nghị chính $C^*_{s, D}$ (ưu tiên nhóm 4 số vốn nhỏ `72.000đ` để bảo vệ dòng tiền hàng ngày, đồng thời hiển thị đầy đủ cả 5 cấu hình trên Web):**
     - Nếu $\hat{p}_{s, \text{tens, R1}}^{(<D)} \ge 10.6904\%$ và $\hat{p}_{s, \text{units, R1}}^{(<D)} \ge 10.6904\%$: chọn `2x2` (bắt trọn Top 2 Chục $\times$ Top 2 Đơn vị).
     - Nếu Lồng Chục lệch mạnh hơn hẳn ($\hat{p}_{s, \text{tens, R1}}^{(<D)} < 10.6904\%$ nhưng Lồng Đơn Vị gánh độ lệch $\ge 10.50\%$ và $\text{ROI}_{1\times4}^{(<D)} > \max(\text{ROI}_{2\times2}^{(<D)}, \text{ROI}_{4\times1}^{(<D)})$): chọn `1x4` (1 Chục $\times$ 4 Đơn vị).
     - Nếu Lồng Chục có 4 bóng dẫn đầu đồng đều và Lồng Đơn Vị có 1 bóng trụ cột vượt trội ($\hat{p}_{s, \text{units, R1}}^{(<D)} \ge 10.6904\%$ và $\text{ROI}_{4\times1}^{(<D)} > \max(\text{ROI}_{2\times2}^{(<D)}, \text{ROI}_{1\times4}^{(<D)}) + 1.5\%$): chọn `4x1` (4 Chục $\times$ 1 Đơn vị).
     - Các trường hợp còn lại: chọn cấu hình có $\text{ROI}^{(<D)}$ cao nhất giữa `2x2` và `1x4`.
5. **Điểm Xếp hạng Đài Trong Ngày (`StationAlphaScore`):**
   $$\text{AlphaScore}_{s, D} = \left(\hat{p}_{s, \text{joint, R1}}^{(<D)} \text{ (in \%)} - 1.0\right) \times 100.0 + 0.25 \times \max_{\text{cfg} \in \{\text{2x2, 1x4, 4x1, 3x3}\}} \text{ROI}_{\text{cfg}}^{(<D)}$$
   Các đài mở thưởng trong ngày $D$ được sắp xếp giảm dần theo $\text{AlphaScore}_{s, D}$ (nếu bằng nhau thì tie-break tất định theo mã đài `station_code` tăng dần bảng chữ cái). Đài đứng đầu bảng xếp hạng là **Đài Ưu Tiên Số 1 ($s^*_1$)**; đài đứng thứ hai (nếu cũng vượt qua bộ lọc lợi thế chọn lọc) được ghi nhận là **Đài Phụ Tham Khảo ($s^*_2$)**.

#### B. Phân Hạng Tín Hiệu Ngày (`DailyVerdictTier`) & Công Thức Đi Vốn CPPI / House-Money
Gọi $s^*_1$ là đài đứng số 1 trong ngày $D$, với $\text{JointR1}_1 = \hat{p}_{s^*_1, \text{joint, R1}}^{(<D)}$ (tính theo $\%$) và $\text{BestROI}_1 = \max_{\text{cfg}} \text{ROI}_{s^*_1, \text{cfg}}^{(<D)}$.
Gọi $W_{D-1}$ là số dư hiện tại của Quỹ Chuẩn trước giờ mở thưởng ngày $D$, $W_0 = 1,000,000\text{ VNĐ}$ là vốn gốc, $C_{D-1} = \max(0, W_{D-1} - W_0)$ là Quỹ Lãi Ròng, và $B_0 = 72,000\text{ VNĐ}$ là mức cược cơ sở `1.0x` (cho bộ 4 số):

1. **Điều kiện vượt Bộ lọc Lợi thế Chọn lọc (`passes_selective_alpha`):**
   $$\text{passes\_selective\_alpha} \iff \left(\text{JointR1}_1 \ge 1.105\%\right) \land \left(\text{BestROI}_1 > 0.0\%\right)$$
2. **Bốn phân hạng tín hiệu ngày (`verdict_tier`) và hệ số đi vốn (`recommended_multiplier` $m_D$):**
   - 🔴 **`SKIP_NO_EDGE` (`HÔM NAY NGHỈ — BẢO TOÀN VỐN`):**
     - **Điều kiện:** $\neg \text{passes\_selective\_alpha}$ (tất cả 5–7 đài mở thưởng hôm nay đều có $\text{JointR1} < 1.105\%$ hoặc $\text{BestROI} \le 0.0\%$).
     - **Hệ số đi vốn:** $m_D = \mathbf{0.0\text{x}}$ $\implies \text{Cost}_D = \mathbf{0\text{ VNĐ}}$ (Đứng ngoài 100%, giữ nguyên số dư $W_D = W_{D-1}$).
   - 🟢 **`PLAY_PEAK` (`NÊN ĐÁNH — TÍN HIỆU HỘI TỤ ĐỈNH`):**
     - **Điều kiện:** $\text{passes\_selective\_alpha} \land \left(\text{JointR1}_1 \ge 1.150\% \lor \text{BestROI}_1 \ge +8.0\%\right)$.
     - **Hệ số đi vốn (`House-Money Sizing`):**
       - Nếu Quỹ Lãi Ròng $C_{D-1} \ge 2 \times B_0 = 144,000\text{ VNĐ}$: nâng hệ số lên $m_D = \mathbf{1.50\text{x}}$ (`108.000 VNĐ/ngày`, tức `27.000 VNĐ/số`; phần vốn tăng thêm $\Delta \text{Cost}_D = 36,000\text{ VNĐ} \le 0.50 \times C_{D-1}$, đảm bảo nếu trượt trắng $K=0$ thì số dư $W_D = W_{D-1} - 108,000 \ge W_0$).
       - Nếu $C_{D-1} < 144,000\text{ VNĐ}$: đi vốn chuẩn $m_D = \mathbf{1.00\text{x}}$ (`72.000 VNĐ/ngày`, tức `18.000 VNĐ/số`).
   - 🟢 **`PLAY_STANDARD` (`NÊN ĐÁNH — ĐẠT CHUẨN LỢI THẾ ALPHA`):**
     - **Điều kiện:** $\text{passes\_selective\_alpha}$ nhưng chưa đạt ngưỡng `PLAY_PEAK`, và $\text{BestROI}_1 \ge +3.0\%$ (hoặc $\text{JointR1}_1 \ge 1.125\%$).
     - **Hệ số đi vốn (`House-Money Sizing`):**
       - Nếu Quỹ Lãi Ròng $C_{D-1} \ge 2 \times B_0 = 144,000\text{ VNĐ}$: nâng nhẹ hệ số lên $m_D = \mathbf{1.25\text{x}}$ (`90.000 VNĐ/ngày`, tức `22.500 VNĐ/số`; phần vốn tăng thêm $\Delta \text{Cost}_D = 18,000\text{ VNĐ} \le 0.50 \times C_{D-1}$).
       - Nếu $C_{D-1} < 144,000\text{ VNĐ}$: đi vốn chuẩn $m_D = \mathbf{1.00\text{x}}$ (`72.000 VNĐ/ngày`).
   - 🟡 **`PLAY_CAUTIOUS` (`ĐÁNH THẬN TRỌNG — LỢI THẾ DƯƠNG NHẸ`):**
     - **Điều kiện:** $\text{passes\_selective\_alpha}$ với $0.0\% < \text{BestROI}_1 < +3.0\%$ và $1.105\% \le \text{JointR1}_1 < 1.125\%$.
     - **Hệ số đi vốn:** Luôn giữ ở mức chuẩn $m_D = \mathbf{1.00\text{x}}$ (`72.000 VNĐ/ngày`), không kích hoạt bội số House-Money.

#### C. Bảng Quy Đổi Tiền Mẫu VNĐ Theo Quy Mô Vốn Gia Đình (`SampleCapitalAllocationRow`)
Để bất kỳ thành viên nào trong gia đình cũng có thể nhìn vào áp dụng ngay mà không cần nhập số tiền lên Web, hệ thống tự động tính sẵn bảng quy đổi tỷ lệ thuận với Quỹ Chuẩn `1.000.000 VNĐ` cho 4 mức tổng vốn $V \in \{500.000, \ 1.000.000, \ 2.000.000, \ 5.000.000\}\text{ VNĐ}$ với tỷ lệ quy mô $\kappa(V) = \frac{V}{1,000,000}$:
- Tiền cược mỗi số (cho bộ 4 số): $\text{StakePerNumber}(V) = \text{round}\left(18,000 \times \kappa(V) \times m_D\right)\text{ VNĐ}$.
- Tổng tiền cược trong ngày: $\text{TotalDailyCost}(V) = 4 \times \text{StakePerNumber}(V)\text{ VNĐ}$ (bằng `0 VNĐ` nếu $m_D = 0.0\text{x}$).
- Tiền thực thu về cho mỗi 1 nháy nổ: $\text{PayoutPerHit}(V) = \text{round}\left(87,500 \times \kappa(V) \times m_D\right)\text{ VNĐ}$.
- Lãi ròng khi nổ 1 nháy ($K=1$): $\text{NetProfit1Hit}(V) = \text{PayoutPerHit}(V) - \text{TotalDailyCost}(V)$.
- Lãi ròng khi nổ 2 nháy ($K=2$): $\text{NetProfit2Hits}(V) = 2 \times \text{PayoutPerHit}(V) - \text{TotalDailyCost}(V)$.

---

### 5.4. Hợp Đồng Dữ Liệu Sổ Cái Quỹ Chuẩn & Báo Cáo Hàng Ngày (`Pydantic v2 Schemas`)

Tất cả các mô hình dữ liệu Giai đoạn 3 kế thừa từ `StrictBaseModel` (`extra="forbid"`, `allow_inf_nan=False`, `validate_assignment=True`) trong [`src/xsmn_alpha/schemas.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/schemas.py):

#### 5.4.1. Bản Ghi Sổ Cái Quỹ Chuẩn (`BenchmarkLedgerEntry` & `BenchmarkLedgerState`)
Tệp `data/live/benchmark_ledger.json` lưu trữ toàn bộ lịch sử đối soát lũy kế của Quỹ Chuẩn Tham Chiếu (`1.000.000 VNĐ`):

```json
{
  "schema_version": "3.0.0",
  "starting_bankroll_vnd": 1000000,
  "base_stake_per_number_vnd": 18000,
  "payout_per_hit_vnd": 87500,
  "current_bankroll_vnd": 2922875,
  "house_money_surplus_vnd": 1922875,
  "peak_bankroll_vnd": 3130625,
  "min_bankroll_vnd": 1000000,
  "max_drawdown_vnd": 741125,
  "total_tracked_days": 298,
  "played_days": 168,
  "rest_days": 130,
  "win_days": 109,
  "loss_days": 59,
  "total_cost_vnd": 17874000,
  "total_revenue_vnd": 19796875,
  "net_profit_vnd": 1922875,
  "updated_at": "2026-10-26T05:00:00+07:00",
  "sha256": "a1b2c3d4...",
  "entries": [
    {
      "draw_date": "2026-10-25",
      "weekday_vn": "Chủ Nhật",
      "settlement_status": "SETTLED",
      "verdict_tier": "PLAY_PEAK",
      "chosen_station_code": "XSDL",
      "chosen_station_name": "Đà Lạt (Lâm Đồng)",
      "chosen_region": "Miền Nam",
      "chosen_config_id": "1x4",
      "selected_numbers": ["21", "22", "23", "28"],
      "recommended_multiplier": 1.5,
      "bankroll_before_vnd": 2959625,
      "house_money_before_vnd": 1959625,
      "cost_vnd": 108000,
      "actual_prizes_last2": ["41", "19", "73", "08", "83", "39", "88", "14", "57", "81", "23", "90", "38", "84", "61", "03", "78", "83"],
      "hit_count_k": 1,
      "hit_details": [{"prize_index": 10, "prize_label": "Giải Tư (5)", "number": "23"}],
      "revenue_vnd": 131250,
      "net_profit_vnd": 23250,
      "bankroll_after_vnd": 2982875,
      "house_money_after_vnd": 1982875
    }
  ]
}
```

- **Hai trạng thái đối soát (`settlement_status`):**
  - `"PENDING"`: Khuyến nghị vừa được phát ra lúc 05:00 sáng ngày $D$ (khi chưa mở thưởng); lúc này `actual_prizes_last2 = []`, `hit_count_k = None`, `revenue_vnd = 0`, `net_profit_vnd = 0`, `bankroll_after_vnd = bankroll_before_vnd`.
  - `"SETTLED"`: Sau khi có kết quả mở thưởng đủ 18 giải của đài `chosen_station_code` trong ngày $D$ (hoặc ngay lập tức nếu `verdict_tier == "SKIP_NO_EDGE"` với `cost_vnd = 0`), hệ thống chấm điểm chính xác số nháy $K$, điền `hit_details` (chỉ rõ nổ ở giải mấy, con số nào), cập nhật `revenue_vnd`, `net_profit_vnd = revenue_vnd - cost_vnd`, và `bankroll_after_vnd = bankroll_before_vnd + net_profit_vnd`.
- **Tính lũy đẳng (`Idempotent Settlement`):** Nếu `settle-ledger` được gọi nhiều lần cho cùng một `draw_date` đã ở trạng thái `"SETTLED"` với cùng bộ 18 giải, sổ cái giữ nguyên tuyệt đối số dư mà không bao giờ cộng/trừ tiền lặp 2 lần.

#### 5.4.2. Hợp Đồng Báo Cáo Định Lượng Hàng Ngày (`DailyQuantReportContract`)
Đối tượng `DailyQuantReportContract` chứa trọn vẹn bằng chứng toán học của ngày $D$ để xuất ra `public/daily/YYYY-MM-DD.json`, render `public/daily/YYYY-MM-DD.html` và tạo nội dung bản tin Telegram 05:00 sáng:
- `report_date`: Ngày báo cáo `YYYY-MM-DD` (ví dụ: `"2026-10-26"`).
- `weekday_vn`: Thứ tiếng Việt (`"Thứ 2"` $\to$ `"Chủ Nhật"`).
- `generated_at_ict`: Thời điểm sinh báo cáo theo múi giờ `Asia/Ho_Chi_Minh`.
- `data_pipeline_audit`: Nhật ký thu thập & kiểm định dữ liệu đầu vào (`total_stations_35`, `stations_synced_ok`, `fallback_used_count`, `schema_gate_passed: bool`, `latest_settled_date`).
- `yesterday_settlement`: Bản ghi đối soát kết quả của ngày hôm trước (`D - 1`) kèm lời tóm tắt kết quả Thắng/Thua/Nghỉ.
- `verdict_tier`: Một trong 4 giá trị `"PLAY_PEAK" | "PLAY_STANDARD" | "PLAY_CAUTIOUS" | "SKIP_NO_EDGE"`.
- `should_play_today`: `bool` (`True` khi `verdict_tier != "SKIP_NO_EDGE"`, `False` khi `"SKIP_NO_EDGE"`).
- `primary_station`: `StationDailyScorecard` của đài đứng số 1 trong ngày.
- `secondary_station`: `StationDailyScorecard | None` của đài đứng số 2 (nếu cũng đạt `passes_selective_alpha == True`).
- `skipped_stations`: Danh sách các đài mở thưởng hôm nay bị xếp vào diện bỏ qua / nhiễu trắng.
- `all_today_stations`: Danh sách đầy đủ 5–7 `StationDailyScorecard` của tất cả các đài mở thưởng trong ngày $D$, mỗi đài gồm:
  - Thông tin đài (`station_code`, `station_name`, `region`, `draw_time_ict`, `sample_draws_3y`, `last_draw_date_before_d`).
  - Kết quả kiểm định thống kê ($\chi^2_{15}, \chi^2_{30}, \chi^2_{60}$, $\chi^2_{\max}$, phân vị Monte Carlo Null $P_{90}, P_{95}$, $BF_{10, \max}$, Entropy chuẩn hóa, độ dài chế độ `bocd_map_run_length`, trạng thái cảnh báo thay bóng `bocd_changepoint_warning: bool`).
  - Bảng phân phối xác suất hiệu chuẩn 10 quả bóng (`0`–`9`) của Lồng Hàng Chục (`p_ai_tens`, `p_bocd_tens`, `p_seq_tens`, `ranked_balls_tens`) và Lồng Hàng Đơn Vị (`p_ai_units`, `p_bocd_units`, `p_seq_units`, `ranked_balls_units`).
  - Ma trận xác suất kết hợp 100 con số (`joint_100_matrix`: ma trận $10 \times 10$ tổng bằng $1.0$).
  - Chi tiết cả 5 phương án ghép số (`ticket_configs`: `2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`) kèm bộ số cụ thể, xác suất trúng 1 giải $p_{\mathcal{S}}$, xác suất trúng $\ge 1$ nháy trong 18 giải $1 - (1 - p_{\mathcal{S}})^{18}$, và OOS ROI 3 năm.
  - Điểm xếp hạng `station_alpha_score`, `passes_selective_alpha` và lời giải trình định lượng riêng cho từng đài.
- `capital_guidance`: Hướng dẫn đi vốn CPPI / House-Money (`recommended_multiplier`, `benchmark_bankroll_vnd`, `house_money_surplus_vnd`, `benchmark_bet_vnd`, `sample_allocations: list[SampleCapitalAllocationRow]`).
- `executive_nlg_vi`: Khối văn bản giải trình định lượng tất định trả lời trực diện 4 câu hỏi cốt lõi (`q1_should_play_and_why`, `q2_which_station_and_region`, `q3_which_numbers_and_config`, `q4_how_to_allocate_capital`).
- `telegram_message_html`: Chuỗi tin nhắn định dạng Telegram HTML chuẩn mực (đã escape an toàn và đính kèm đường link Web báo cáo cuối tin).

---

### 5.5. Hợp Đồng Nội Dung Bản Tin Telegram 05:00 Sáng & Trang Web Báo Cáo Chi Tiết

#### A. Cấu Trúc Bản Tin Chiến Thuật 05:00 Sáng Trên Telegram (`Telegram Executive Briefing`)
Tin nhắn gửi qua Telegram (`parse_mode="HTML"`, độ dài $\le 4096$ byte UTF-8) bắt buộc trình bày súc tích, rõ ràng, tối ưu trên màn hình điện thoại theo cấu trúc **Tiêu đề + Đối soát Hôm qua (`D - 1`) + 3 Khối Chiến Thuật Cốt Lõi (tích hợp đủ 4 câu hỏi gia đình) + Link Web Báo Cáo Chi Tiết**:

1. **Tiêu đề & Đối soát nhanh hôm qua (`D - 1`):**
   - Ngày báo cáo (`📡 BẢN TIN 05:00 SÁNG — THỨ ..., (DD/MM/YYYY)`).
   - Dòng tóm tắt kết quả đối soát kỳ trước (`report.yesterday_summary_vi`): Đài đã khuyến nghị (hoặc Nghỉ), số nháy nổ ($K$), Lãi/Lỗ thực tế, Số dư Quỹ Chuẩn hiện tại ($W_{D-1}$) và Quỹ Lãi Ròng ($C_{D-1}$).
2. **Mục 1 (`1. HÔM NAY CÓ NÊN ĐÁNH KHÔNG?`) — Trả lời Câu hỏi 1 & Bằng chứng số học (`< D`):**
   - Hiển thị rõ biểu tượng quyết định: `🟢 CÓ — HÔM NAY NÊN ĐÁNH (PLAY_PEAK / PLAY_STANDARD)` hoặc `🟡 CÓ — HÔM NAY ĐÁNH NHẸ THẬN TRỌNG (PLAY_CAUTIOUS)` hoặc `🔴 KHÔNG NÊN ĐÁNH — HÔM NAY NGHỈ (SKIP_NO_EDGE)`.
   - Giải trình ngắn gọn bằng số liệu thật trước giờ quay (`< D`): Tần suất nổ đồng thời cặp bóng Hạng 1 ngoài mẫu ($\text{JointR1}\%$ so với mốc chuẩn $1.105\%$), tần suất bóng Hạng 1 Lồng Chục & Lồng Đơn Vị so với mốc hòa vốn $10.69\%$, thống kê $\chi^2_{\max}$ so với ngưỡng Monte Carlo Null $P_{90}/P_{95}$, hệ số Bayes $BF_{10}$, độ dài chế độ lồng cầu `BOCD` ($r^*$), và `OOS ROI` 3 năm của cấu hình khuyến nghị (kèm `Best` ROI).
3. **Mục 2 (`2. NÊN ĐÁNH ĐÀI GÌ & TỔ HỢP SỐ?`) — Trả lời Câu hỏi 2 & Câu hỏi 3:**
   - Chỉ rõ **Đài Ưu Tiên Số 1 (`🏆 Nên Đánh:`)**: Tên đài, Khu vực (`Miền Nam` / `Miền Trung`), Mã đài, Giờ quay (`16:15` / `17:15`), và điểm xếp hạng `AlphaScore`.
   - Hiển thị **Cầu bóng dẫn đầu**: Top 2 bóng Lồng Hàng Chục (kèm xác suất hiệu chuẩn $\%$) và Top 2 bóng Lồng Hàng Đơn Vị (kèm xác suất hiệu chuẩn $\%$).
   - Chỉ rõ **Bộ số nên đánh nhất**: Cấu hình tối ưu được chọn (`2x2`, `1x4`, hoặc `4x1` kèm `ROI` OOS) và **in đậm danh sách các con số 2 chữ số cần đánh**, kèm **Các bộ số tham khảo** đầy đủ cho các cấu hình còn lại trong 5 cấu hình (`2x2`, `1x4`, `4x1`, `3x3` 9 số, và `core_2x2_sat_3x3` Hybrid 9 số).
   - Nêu **Đài Phụ (`🥈 Nên đánh thứ nhì là:`)** nếu đạt chuẩn lợi thế dương, và liệt kê rõ tên các đài còn lại trong ngày không đánh (`Các đài còn lại không đánh`). Vào ngày `SKIP_NO_EDGE`, ghi rõ `Không đánh đài nào hôm nay (CHỈ QUAN SÁT)` kèm thông số quan sát tham khảo.
4. **Mục 3 (`3. ĐI VỐN NHƯ THẾ NÀO (QUỸ CHUẨN 1 TRIỆU)?`) — Trả lời Câu hỏi 4:**
   - Chỉ rõ hệ số đi vốn CPPI / House-Money khuyến nghị (`0.0x`, `1.0x`, `1.25x`, hoặc `1.5x` / `0.00x..1.50x`), mức cược chuẩn (`VNĐ/ngày`), Số dư Quỹ Chuẩn $W$ và Đệm lãi $C$.
   - Bảng quy đổi tiền cược mẫu thực tế cho **4 mức vốn gia đình** (`Vốn 500k`, `Vốn 1 Triệu`, `Vốn 2 Triệu`, `Vốn 5 Triệu`): ghi rõ tiền cược mỗi số (`đ/số`), tổng tiền cược trong ngày (`đ/ngày`), tiền thu khi trúng 1 nháy và lãi ròng 1 nháy.
5. **Chân trang — Đường link Báo Cáo Giải Trình Chi Tiết trên Trang Web:**
   - Đính kèm thẻ `<a href="{PUBLIC_REPORT_BASE_URL}/daily/{YYYY-MM-DD}.html">Xem Trang Web Giải Trình Chi Tiết Ngày {DD/MM/YYYY} ({YYYY-MM-DD})</a>`.

#### B. Cấu Trúc 5 Khu Vực Của Trang Web Báo Cáo Giải Trình Chi Tiết (`public/daily/YYYY-MM-DD.html`)
Khi bấm vào đường link từ Telegram, trang Web mở ra giao diện Dark-Mode sắc nét, tương thích hoàn hảo cả trên điện thoại di động lẫn máy tính, hiển thị đầy đủ **5 khu vực bằng chứng toán học**:
1. **Khu vực 1 — Tóm tắt Quyết định Chiến thuật 05:00 Sáng & Giải trình Toán học (`Executive Verdict & Deterministic Rationale`):** Thẻ KPI nổi bật trả lời 4 câu hỏi cốt lõi và kết quả đối soát ngày hôm qua.
2. **Khu vực 2 — Bảng Chấm Điểm & So Sánh Toàn Bộ 5–7 Đài Mở Thưởng Trong Ngày (`Multi-Station Comparison Table`):** Đối chiếu tất cả các đài mở thưởng hôm nay (Miền Nam & Miền Trung) với đầy đủ các cột: Khu vực & Giờ quay, Cỡ mẫu 3 năm, $\chi^2_{\max}$ vs Ngưỡng Monte Carlo Null ($P_{90}/P_{95}$), Hệ số Bayes $BF_{10}$, Độ dài chế độ `BOCD` ($r^*_{t-1}$), Tần suất OOS Rank-1 Lồng Chục & Lồng Đơn Vị, $\text{JointR1}\%$, OOS ROI của các cấu hình, Điểm `AlphaScore`, và Phán quyết (`Đài Số 1`, `Đài Phụ`, `Đứng Ngoài`).
3. **Khu vực 3 — Bảng Phân Phối Xác Suất 10 Quả Bóng (`0`–`9`), Ma Trận Nhiệt 100 Số (`00`–`99`) & Toàn Bộ 5 Phương Án Ghép Số (`Cage Probability Distributions, 10x10 Heatmap & 5 Sweet-Spot Configs`):**
   - Hiển thị chi tiết xác suất hiệu chuẩn $P_{\text{AI}}, P_{\text{BOCD}}, P_{\text{Seq}}$ và thứ hạng `Rank 1` $\to$ `Rank 10` cho cả 2 lồng cầu của đài mục tiêu.
   - Bảng ma trận nhiệt $10 \times 10$ của 100 con số (`00`–`99`) đánh dấu nổi bật các ô thuộc bộ số khuyến nghị.
   - Bảng so sánh trực diện cả 5 cấu hình ghép số (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`) kèm danh sách số cụ thể, xác suất nổ $\ge 1$ nháy trong 18 giải, và OOS ROI 3 năm.
4. **Khu vực 4 — Bảng Tư Vấn Đi Vốn CPPI / House-Money & Quy Đổi Tiền VNĐ Mẫu (`Capital Sizing & VND Conversion Guide`):** Bảng hướng dẫn chi tiết số tiền cược/số, tổng tiền/ngày, tiền thu khi nổ 1 nháy, 2 nháy, 3 nháy cho các mức vốn `500.000đ`, `1.000.000đ`, `2.000.000đ`, `5.000.000đ` kèm giải thích quy tắc khóa trần 50% Quỹ Lãi Ròng.
5. **Khu vực 5 — Nhật Ký Thu Thập Dữ Liệu (`Data Pipeline Audit`) & Biểu Đồ Đường Cong Vốn + Sổ Cái Đối Soát Quỹ Chuẩn (`Benchmark Equity Curve SVG & Historical Settlement Ledger`):** Hiển thị trạng thái kiểm định đầu vào 35 đài, biểu đồ SVG đường cong vốn lũy kế của Quỹ Chuẩn `1.000.000 VNĐ`, và bảng sao kê đối soát lịch sử các ngày gần nhất.

---

### 5.6. Năm Cổng Kiểm Soát Chống Gian Lận (`Adversarial Gate Hardening — Anti-False-PASS`)

| Cổng Kiểm Soát (`Gate`) | Kịch Bản Tấn Công / Dữ Liệu Bẩn (`Adversarial Vector`) | Hành Vi Chặn Đứng (`Fail-Closed Rule`) |
| :--- | :--- | :--- |
| **Gate 1: `DataSchemaGate`** | Kỳ quay cào về bị thiếu giải ($<18$) hoặc thừa giải ($>18$) khi trang web nhà đài đang quay dở; ký tự số Unicode full-width (`"０８"`), chuỗi rỗng, mã đài không thuộc 35 đài chuẩn, trùng lặp ngày `draw_date`, hoặc tổng vector đếm $\sum_{i=0}^9 n_{t,i} \ne 18$. | Ném ngoại lệ `DataIntegrityError` ngay lập tức và tự động chuyển sang nguồn dự phòng tiếp theo (`minhngoc` $\to$ `xskt` $\to$ `xoso`); tuyệt đối không tự động điền `"00"` hay ghi bản ghi thiếu giải vào cache. |
| **Gate 2: `PreDrawCutoffGate`** | Khi chấm điểm các đài cho ngày mục tiêu $D$, dữ liệu đầu vào vô tình chứa kỳ mở thưởng của chính ngày $D$ hoặc ngày tương lai $> D$ (`Look-Ahead Leakage`), hoặc dùng kết quả thực tế của ngày $D$ để chọn đài/cấu hình cho ngày $D$. | Mọi hàm chấm điểm trong `daily_analyst.py` bắt buộc kiểm tra `assert all(r.draw_date < target_date for r in history_draws)`. Nếu phát hiện bất kỳ bản ghi nào có `draw_date >= target_date`, ném `TemporalLeakageError` ngay lập tức. |
| **Gate 3: `SimplexCalibrationGate`** | Phân phối xác suất 10 bóng $P_{\text{AI}}(0\dots9)$ hoặc ma trận xác suất 100 số $P(00\dots99)$ có phần tử âm, `NaN`, `Inf`, hoặc tổng lệch khỏi $1.0$ quá $10^{-6}$. | Ném ngoại lệ `CalibrationIntegrityError` ngay lập tức; không bao giờ xuất bảng xác suất lỗi lên trang Web hay bản tin Telegram. |
| **Gate 4: `FalsificationCashBrakeGate`** | Tất cả các đài mở thưởng trong ngày $D$ đều rơi vào vùng nhiễu trắng ($\neg \text{passes\_selective\_alpha}$), nhưng báo cáo vẫn hiển thị hệ số vốn $> 0.0\text{x}$ hoặc số tiền cược $> 0\text{ VNĐ}$. | Khi `verdict_tier == "SKIP_NO_EDGE"`, bắt buộc khóa cứng `should_play_today = False`, `recommended_multiplier = 0.0`, và `cost_vnd = 0` trên mọi mức vốn mẫu. Nếu vi phạm, ném `DataIntegrityError`. |
| **Gate 5: `HouseMoneyAndLedgerIntegrityGate`** *(Mới cho GĐ 3)* | (a) Nâng hệ số vốn $m_D > 1.0\text{x}$ khi Quỹ Lãi Ròng $C_{D-1} < 144.000\text{ VNĐ}$ hoặc phần cược tăng thêm $\Delta \text{Cost}_D > 0.50 \times C_{D-1}$ hoặc làm số dư sau cược có nguy cơ lẹm vào vốn gốc $1.000.000\text{ VNĐ}$; (b) Tự ý tăng hệ số vốn sau ngày thua kiểu gấp thếp (`Martingale`); (c) Chấm điểm trùng lặp 2 lần cùng một ngày `draw_date` hoặc sửa tay làm lệch `sha256` / lệch phương trình kế toán $W_t = W_{t-1} + \text{Rev}_t - \text{Cost}_t$ trong `benchmark_ledger.json`. | Ném ngoại lệ `CapitalDisciplineError` (hoặc `DataIntegrityError`) ngay lập tức. Đảm bảo bất biến $\forall t, \ W_t - \text{Cost}_t \ge W_0$ khi $m_t > 1.0$, kiểm tra `sha256` trước và sau khi ghi sổ cái, và đảm bảo đối soát lũy đẳng (`Idempotent`). |

---

## 6. Code Style (Phong Cách Mã Nguồn & Quy Ước Kỹ Thuật)

- **Kiểu tĩnh nghiêm ngặt & Hợp đồng Pydantic v2 (`Strict Typing & Fail-Closed Contracts`):** Mọi module trong `src/xsmn_alpha/live/` bắt buộc khai báo `from __future__ import annotations`, định nghĩa đầy đủ Type Hints và kiểm tra đầu vào/đầu ra qua `StrictBaseModel`.
- **Sinh lời văn giải trình toán học tất định (`Deterministic Quantitative NLG`):** Tuyệt đối không dùng LLM sinh văn bản tự do; mọi câu giải trình phải được lắp ghép chính xác từ số liệu kiểm định thực tế và khớp 1:1 với các con số trong bảng biểu.

```python
from __future__ import annotations

from xsmn_alpha.constants import (
    BENCHMARK_BASE_DAILY_COST_4NUM_VND,
    BENCHMARK_INITIAL_BANKROLL_VND,
    HOUSE_MONEY_MAX_SURPLUS_FRACTION,
    HOUSE_MONEY_MIN_BUFFER_DAYS,
)
from xsmn_alpha.exceptions import CapitalDisciplineError


def compute_house_money_multiplier(
    *,
    passes_selective_alpha: bool,
    strong_convergence: bool,
    current_bankroll_vnd: int,
    initial_bankroll_vnd: int = BENCHMARK_INITIAL_BANKROLL_VND,
    base_daily_cost_vnd: int = BENCHMARK_BASE_DAILY_COST_4NUM_VND,
) -> tuple[float, int]:
    """Compute fail-closed CPPI / House-Money capital multiplier and daily bet in VND."""
    if current_bankroll_vnd < 0 or initial_bankroll_vnd <= 0 or base_daily_cost_vnd <= 0:
        raise CapitalDisciplineError("Bankroll and base cost parameters must be positive integers.")

    if not passes_selective_alpha:
        return (0.0, 0)

    house_money_vnd = max(0, current_bankroll_vnd - initial_bankroll_vnd)
    min_buffer_vnd = HOUSE_MONEY_MIN_BUFFER_DAYS * base_daily_cost_vnd

    if house_money_vnd < min_buffer_vnd:
        return (1.0, base_daily_cost_vnd)

    candidate_mult = 1.50 if strong_convergence else 1.25
    total_cost_vnd = int(round(base_daily_cost_vnd * candidate_mult))
    extra_cost_vnd = total_cost_vnd - base_daily_cost_vnd

    # Gate 5: Never risk more than 50% of House-Money surplus and never breach initial principal
    if (
        extra_cost_vnd > int(house_money_vnd * HOUSE_MONEY_MAX_SURPLUS_FRACTION)
        or (current_bankroll_vnd - total_cost_vnd) < initial_bankroll_vnd
    ):
        return (1.0, base_daily_cost_vnd)

    return (candidate_mult, total_cost_vnd)
```

---

## 7. Testing Strategy (Chiến Lược Kiểm Thử Toàn Diện — PASS & Negative Mutation FAIL)

Sử dụng `pytest` tại thư mục `tests/` với yêu cầu độ phủ tối thiểu **`>= 90%`** trên toàn bộ `src/xsmn_alpha` (bao gồm cả Giai đoạn 2 và Giai đoạn 3), bắt buộc kiểm tra cả **luồng chuẩn (`PASS`)** lẫn **đột biến âm đối kháng (`Adversarial Negative Mutation FAIL`)**:

1. **Tầng 0 — Bảo toàn 100% Bộ Kiểm thử Giai đoạn 2 hiện hữu (`tests/test_constants_and_schemas.py` $\to$ `tests/test_adversarial_mutations.py`):**
   - Toàn bộ các bài kiểm thử của Giai đoạn 2 phải tiếp tục chạy xanh 100% mà không xóa hay hạ thấp bất kỳ điều kiện kiểm tra nào.
2. **Tầng 1 — Kiểm thử Danh mục 35 Đài, Cấu hình Đối xứng `4x1` & Trình cào Đa nguồn (`tests/test_stage3_registry_and_4x1.py`):**
   - **PASS:** Xác nhận `STATION_REGISTRY_35` chứa đúng 35 đài (21 đài Miền Nam `16:15` + 14 đài Miền Trung `17:15`), lịch mở thưởng từng thứ từ Thứ 2 đến Chủ Nhật khớp đúng thực tế (5–7 đài/ngày), cấu hình `4x1` chọn đúng Top 4 Chục $\times$ Top 1 Đơn vị $= 4$ số (`cost_per_draw == 4.0`, `be_hits_30_draws == 24.6857...`), và `multi_fetcher.py` tự động chuyển sang nguồn dự phòng `xskt` / `xoso` khi `minhngoc` trả về bảng lỗi.
   - **FAIL (Negative Mutation):** Truyền mã đài lạ ngoài 35 đài (`"XSHN"`), truyền kỳ quay chỉ có 17 giải (đang quay dở chưa có Giải ĐB), hoặc ký tự Unicode `"０８"` $\rightarrow$ bắt buộc `DataSchemaGate` chặn đứng bằng `DataIntegrityError`.
3. **Tầng 2 — Kiểm thử Sổ cái Quỹ Chuẩn & Cổng Kỷ luật Vốn House-Money (`tests/test_stage3_ledger_and_house_money.py`):**
   - **PASS:** Kiểm tra khởi tạo và cập nhật `benchmark_ledger.json`, đối soát chính xác số nháy $K \in \{0, 1, 2, \dots\}$ trên 18 giải, liệt kê đúng tên giải nổ (`Giải Tám` $\to$ `Giải ĐB`), tính lũy đẳng (`Idempotent`) khi gọi `settle-ledger` nhiều lần cho cùng một ngày, và tính đúng hệ số `0.0x`, `1.0x`, `1.25x`, `1.5x` kèm bảng quy đổi tiền mẫu (`500k`, `1M`, `2M`, `5M`).
   - **FAIL (Negative Mutation):**
     - Cố tình truyền hệ số `1.5x` khi Quỹ Lãi Ròng $C_{t-1} < 144.000\text{ VNĐ}$ hoặc khi $W_{t-1} = 950.000\text{ VNĐ}$ $\rightarrow$ bắt buộc ném `CapitalDisciplineError`.
     - Sửa tay số dư trong `benchmark_ledger.json` làm lệch phương trình $W_t = W_{t-1} + \text{Rev}_t - \text{Cost}_t$ hoặc làm sai lệch mã `sha256` $\rightarrow$ bắt buộc ném `DataIntegrityError`.
4. **Tầng 3 — Kiểm thử Chuyên viên Chấm điểm Đài Hàng ngày & Lời văn Giải trình Tất định (`tests/test_stage3_daily_analyst_and_nlg.py`):**
   - **PASS:** Kiểm tra chấm điểm 5–7 đài mở thưởng trong ngày $D$, xác nhận tính tất định 100% (chạy 2 lần cùng đầu vào cho ra cùng thứ hạng đài, cùng bộ số và cùng lời văn giải trình `executive_nlg_vi`), kiểm tra ngày tất cả các đài đều nhiễu trắng thì trả về `SKIP_NO_EDGE` (`0.0x`).
   - **FAIL (Negative Mutation):** Cố tình đưa bản ghi kỳ quay có `draw_date == D` hoặc `draw_date > D` vào dữ liệu lịch sử khi chấm điểm cho ngày $D$ $\rightarrow$ bắt buộc `PreDrawCutoffGate` ném `TemporalLeakageError`.
5. **Tầng 4 — Kiểm thử Xuất Bản Trang Web Báo Cáo Chi Tiết & Bản Tin Telegram 05:00 Sáng (`tests/test_stage3_web_and_telegram.py`):**
   - **PASS:** Xác nhận `web_publisher.py` sinh thành công `public/daily/YYYY-MM-DD.html` và `public/index.html` có đầy đủ 5 khu vực bắt buộc (Tóm tắt chiến thuật, Bảng so sánh 5–7 đài, Bảng xác suất 10 bóng + Ma trận 100 số + 5 cấu hình ghép số, Bảng quy đổi vốn VNĐ, Biểu đồ SVG đường cong vốn & Sổ cái đối soát); xác nhận `telegram_bot.py` sinh bản tin đủ 4 câu hỏi cốt lõi + link Web cuối tin, hỗ trợ `--dry-run` và gửi HTTP POST thành công qua Mock Transport.
   - **FAIL (Negative Mutation):** Truyền chuỗi chứa thẻ HTML độc hại (`<script>alert(1)</script>`) hoặc thiếu cấu hình Token khi không bật `--dry-run` $\rightarrow$ bắt buộc escape an toàn toàn bộ ký tự đặc biệt và ném lỗi cấu hình tường minh (`DataIntegrityError`) thay vì im lặng bỏ qua.

---

## 8. Boundaries (Ranh Giới Thực Thi 3 Tầng)

- **Always do (`Luôn luôn thực hiện`):**
  - Thực thi mọi lệnh Python, `pytest` và `ruff` thông qua `uv run ...` với `encoding="utf-8"`.
  - Áp dụng nghiêm ngặt 5 cổng kiểm soát đối kháng (`DataSchemaGate`, `PreDrawCutoffGate`, `SimplexCalibrationGate`, `FalsificationCashBrakeGate`, `HouseMoneyAndLedgerIntegrityGate`).
  - Mọi lời khuyên "Nên đánh" hay "Hôm nay nghỉ" trên Telegram đều phải đi kèm số liệu toán học cụ thể và đường link dẫn tới Trang Web Báo Cáo Giải Trình Chi Tiết của đúng ngày đó.
  - Bảo toàn 100% sự hoạt động của toàn bộ bài kiểm thử Giai đoạn 2 hiện hữu.
- **Ask first (`Hỏi ý kiến Chủ dự án trước khi làm`):**
  - Thay đổi bất kỳ ngưỡng toán học cốt lõi nào đã khóa (mốc hòa vốn `10.6904%`, ngưỡng lọc `JointR1 >= 1.105%`, trần trích Quỹ Lãi Ròng `50%`, hoặc vốn gốc Quỹ Chuẩn `1.000.000 VNĐ`).
  - Thêm bất kỳ thư viện phụ thuộc mới nào vào `pyproject.toml`.
  - Thay đổi khung giờ gửi tin nhắn mặc định (`05:00 ICT`) trong `.github/workflows/daily_quant_report.yml`.
- **Never do (`Tuyệt đối nghiêm cấm`):**
  - **Không bao giờ** gọi bất kỳ API AI / LLM bên ngoài nào (OpenAI, Gemini, Claude) để sinh số hay viết lời bình.
  - **Không bao giờ** gợi ý gấp thếp khi thua (`Martingale`, `Fibonacci`, `1-3-2-6`) hoặc nâng hệ số vốn $> 1.0\text{x}$ khi Quỹ Chuẩn chưa có đủ đệm lãi ròng ($\ge 144.000\text{ VNĐ}$).
  - **Không bao giờ** dùng dữ liệu của ngày $\ge D$ khi tính toán báo cáo khuyến nghị cho ngày $D$ (`Zero Look-Ahead Bias`).
  - **Không bao giờ** lưu cứng (`hardcode`) `TELEGRAM_BOT_TOKEN` hay `TELEGRAM_CHAT_ID` vào mã nguồn Git.
  - **Không bao giờ** xóa, skip (`@pytest.mark.skip`), hoặc nới lỏng các bài kiểm thử đang có để ép pass.

---

## 9. Success Criteria (Tiêu Chí Nghiệm Thu Định Lượng)

Hệ thống Giai đoạn 3 (`stage3-live-family-platform`) chỉ được nghiệm thu hoàn tất khi thỏa mãn đồng thời **8 điều kiện kiểm chứng cụ thể** sau:

- [x] **SC-01 (Hoàn chỉnh 35 Đài & Cấu hình `4x1`):** `STATION_REGISTRY_35` định nghĩa đầy đủ 35 đài (21 XSMN + 14 XSMT) với lịch mở thưởng chính xác từ Thứ 2 đến Chủ Nhật; `sweet_spot_sim.py` hỗ trợ đầy đủ 5 cấu hình (`2x2`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`) và không làm gãy bất kỳ bài kiểm thử Giai đoạn 2 nào.
- [x] **SC-02 (Tự động Thu thập Đa nguồn & Đối soát Sổ cái Quỹ Chuẩn):** Lệnh `uv run python -m xsmn_alpha.cli sync-35` và `settle-ledger` tự động cập nhật kết quả 18 giải mới nhất, đối soát chính xác số nháy nổ ($K$), giải nổ và cập nhật số dư Quỹ Chuẩn (`1.000.000 VNĐ` khởi đầu) trong `data/live/benchmark_ledger.json` kèm mã kiểm chuẩn `SHA-256`.
- [x] **SC-03 (Chuyên viên Báo cáo Định lượng 100% Toán học — Không AI API):** Lệnh `uv run python -m xsmn_alpha.cli daily-report --date YYYY-MM-DD` chấm điểm toàn bộ 5–7 đài mở thưởng trong ngày (khóa chặt `draw_date < D`), phân hạng chính xác (`PLAY_PEAK`, `PLAY_STANDARD`, `PLAY_CAUTIOUS`, `SKIP_NO_EDGE`), tính hệ số vốn CPPI / House-Money và sinh lời văn giải trình tiếng Việt tất định 100% không gọi bất kỳ API AI nào.
- [x] **SC-04 (Trang Web Báo Cáo Giải Trình Chi Tiết Đủ 5 Khu Vực):** Xuất bản thành công `public/daily/YYYY-MM-DD.html` và `public/index.html` hiển thị rõ nét, không lỗi bảng biểu cả 5 khu vực: (1) Tóm tắt quyết định & lý do, (2) Bảng so sánh 5–7 đài trong ngày, (3) Bảng xác suất 10 bóng + Ma trận 100 số + 5 cấu hình ghép số, (4) Bảng tư vấn đi vốn & quy đổi tiền mẫu (`500k`, `1M`, `2M`, `5M`), (5) Nhật ký dữ liệu + Biểu đồ đường cong vốn SVG & Sổ cái đối soát.
- [x] **SC-05 (Bản Tin Telegram 05:00 Sáng Trả Lời Trực Diện 4 Câu Hỏi + Link Web):** Bản tin Telegram sinh ra trả lời đầy đủ 4 câu hỏi cốt lõi (*Có nên đánh không & Vì sao? Đánh đài gì, khu vực nào? Đánh bộ số nào? Đi vốn như thế nào?*), đính kèm link mở trực tiếp trang Web báo cáo chi tiết cuối tin nhắn, chạy mượt ở cả chế độ `--dry-run` lẫn chế độ gửi thật qua `Telegram Bot API`.
- [x] **SC-06 (Tự Động Hóa 0 Đồng Qua GitHub Actions):** Tệp `.github/workflows/daily_quant_report.yml` được cấu hình hoàn chỉnh để tự động cào kết quả, đối soát sổ cái, xuất bản trang Web tĩnh (`public/`) lên GitHub Pages và gửi bản tin Telegram lúc `05:00 ICT` mỗi sáng.
- [x] **SC-07 (Độ Phủ Kiểm Thử & Chống Đột Biến Âm):** `uv run pytest tests/ -v --cov=src/xsmn_alpha --cov-fail-under=90` đạt `100% PASS` trên toàn bộ test suite (Giai đoạn 2 + Giai đoạn 3 PASS & Negative Mutation FAIL) với tổng độ phủ mã nguồn **$\ge 90\%$**.
- [x] **SC-08 (Chuẩn Cú Pháp & Định Dạng):** `uv run ruff check src/ tests/` và `uv run ruff format --check src/ tests/` trả về `0 errors`.

---

## 10. Open Questions (Câu Hỏi Mở)

- **Không còn câu hỏi mở nào về mặt toán học hay kiến trúc.** Toàn bộ các thông số kết nối thực tế (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PUBLIC_REPORT_BASE_URL`) được thiết kế đọc từ biến môi trường / GitHub Secrets kèm chế độ `--dry-run` an toàn để kiểm thử trọn vẹn trên máy local trước khi kích hoạt lịch chạy tự động trên GitHub Actions.
