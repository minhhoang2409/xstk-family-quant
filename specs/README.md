# Chỉ Mục Hồ Sơ Đặc Tả Kỹ Thuật SDD (`specs/README.md`)

Thư mục `specs/` lưu trữ toàn bộ hồ sơ **Phát Triển Hướng Đặc Tả (`Spec-Driven Development — SDD`)** của dự án định lượng `xsmn-alpha`. Mỗi giai đoạn gồm bộ 5 tài liệu chuẩn (`intent.md`, `ideas.md`, `spec.md`, `plan.md`, `todo.md`) đóng vai trò nguồn chân lý duy nhất (`Single Source of Truth`).

---

## 1. Bảng Tổng Hợp Các Giai Đoạn SDD

| Giai đoạn | Mã Module (`specs/<module-id>/`) | Mục tiêu cốt lõi | Trạng thái | Hồ sơ 5-File Chuẩn | Bộ Kiểm Thử (`tests/`) |
| :---: | :--- | :--- | :---: | :--- | :--- |
| **Giai đoạn 1** | *(Tài liệu nền tảng gốc)* | Quy tắc dòng tiền, ma trận trả thưởng Bao Lô 18 giải (`99.500đ / 18.000đ`), điểm hòa vốn & Quản trị vốn Đa kết quả | ✅ **Locked Baseline** | [`QUY_TAC_VA_DIEM_HOA_VON.md`](file:///C:/sidehustle/XSTK/QUY_TAC_VA_DIEM_HOA_VON.md) | `test_constants_and_schemas.py` |
| **Giai đoạn 2** | [`stage2-alpha-discovery`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/) | Hệ thống Phát hiện Alpha & Dự báo Xác suất Hiệu chuẩn 1 Lồng cầu (`BOCD-Dirichlet`, `Markov-Gap`, `Calibration Pooler`, `Monte Carlo Gatekeeper`, `Walk-Forward OOS Backtest`) | ✅ **Accepted & Verified (100% PASS)** | [`intent.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/intent.md) · [`ideas.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/ideas.md) · [`spec.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/spec.md) · [`plan.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/plan.md) · [`todo.md`](file:///C:/sidehustle/XSTK/specs/stage2-alpha-discovery/todo.md) | `test_constants_and_schemas.py`, `test_pillar1..4_*.py`, `test_adversarial_mutations.py` (`71` tests) |
| **Giai đoạn 3** | [`stage3-live-family-platform`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/) | Chuyên viên Báo cáo Định lượng Tự động 05:00 Sáng & Trang Web Giải trình Tĩnh cho 35 Đài XSMN/XSMT (`Registry 35`, `Multi-Source Fetcher`, `Benchmark Ledger`, `Telegram Bot`, `Web Publisher`) | ✅ **Accepted & Verified (100% PASS)** | [`intent.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/intent.md) · [`ideas.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/ideas.md) · [`spec.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/spec.md) · [`plan.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/plan.md) · [`todo.md`](file:///C:/sidehustle/XSTK/specs/stage3-live-family-platform/todo.md) | `test_stage3_registry_and_4x1.py`, `test_stage3_ledger_and_house_money.py`, `test_stage3_daily_analyst_and_nlg.py`, `test_stage3_web_and_telegram.py` (`59` tests) |
| **Giai đoạn 4** | [`stage4-alpha-engine-v2`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/) | Kỷ Luật Điểm Ngọt Gia Đình (`sweet_5` 5 số 60.3% thắng & `2x2` 4 số 52.0% thắng), Bộ Lọc Lịch Chơi 5/2 Theo Độ Cân Bằng Lồng Cầu, Khóa Trần Vốn Đều Tay `1.0x` & Giám Sát Dị Thường (`Cage Anomaly Sentinel`) | ✅ **Accepted & Verified (100% PASS)** | [`intent.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/intent.md) · [`ideas.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/ideas.md) · [`spec.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/spec.md) · [`plan.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/plan.md) · [`todo.md`](file:///C:/sidehustle/XSTK/specs/stage4-alpha-engine-v2/todo.md) | `test_stage4_sweet5_and_5_2_schedule.py` (`37` tests — Tổng cộng `167/167` tests toàn dự án PASS) |

---

## 2. Sáu Cổng Kiểm Soát Chống Gian Lận (`Adversarial Fail-Closed Gates`)

Mọi giai đoạn trong `specs/` đều thực thi nghiêm ngặt 6 cổng kiểm soát đối kháng trong [`src/xsmn_alpha/schemas.py`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/schemas.py) và [`src/xsmn_alpha/live/`](file:///C:/sidehustle/XSTK/src/xsmn_alpha/live/):

1. **Gate 1 (`DataSchemaGate`):** Đảm bảo đủ 18 giải/kỳ, tổng bi mỗi lồng $= 18$, chống ký tự số Unicode full-width và xác thực cấu trúc bộ số (`2x2`, `sweet_5`, `1x4`, `4x1`, `3x3`, `core_2x2_sat_3x3`).
2. **Gate 2 (`PreDrawCutoffGate`):** Khóa thời gian nghiêm ngặt `draw_date < D` khi chấm điểm đài và khi xếp hạng độ cân bằng 7 thứ trong tuần; ném `TemporalLeakageError` ngay lập tức nếu phát hiện dữ liệu tương lai.
3. **Gate 3 (`SimplexCalibrationGate`):** Đảm bảo mọi vector xác suất 10 bóng và ma trận 100 số thuộc đơn hình xác suất chuẩn ($\sum p_i = 1.0 \pm 10^{-6}$, không có `NaN`/`Inf`/số âm).
4. **Gate 4 (`FalsificationCashBrakeGate`):** Khóa tiền mặt `0.0x` (`benchmark_bet_vnd = 0`, `should_play_today = False`) vào các ngày nghỉ `SKIP_NO_EDGE`.
5. **Gate 5 (`HouseMoneyAndLedgerIntegrityGate`):** Bảo toàn chuỗi số dư lũy kế, kiểm tra tính lũy đẳng (`Idempotent`) và chữ ký `SHA-256` trên sổ cái `data/live/benchmark_ledger.json`.
6. **Gate 6 (`Weekly52AndFlatStakeGate`):** Đảm bảo Lịch Chơi 5/2 luôn chọn đúng 2 thứ có lồng cầu cân bằng nhất tuần ($\chi^2_{\max}$ thấp nhất) làm ngày nghỉ định kỳ (`0.0x`) và khóa cứng trần đi vốn `1.0x` vào 5 ngày chơi trong luồng Giai đoạn 4 (`lock_flat_1x=True`).
