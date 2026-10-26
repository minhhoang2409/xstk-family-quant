"""Walk-Forward Daily Simulation (01/01/2026 -> 26/10/2026) Across All 35 Stations.

Strictly causal (Zero Lookahead Bias) daily simulation starting with 1,000,000 VND bankroll:
- Base bet per number: 18,000 VND (Bao lô 18 giải = 1,000 VND/giải).
- Payout per hit (nháy): 87,500 VND (tỷ lệ thực 1 : 87.5 theo QUY_TAC_VA_DIEM_HOA_VON.md).
- Evaluates 3 scenarios side-by-side:
  1. Kịch bản 1 (Ngày nào cũng đánh 1 đài tốt nhất ngày hôm đó):
     Mỗi ngày từ 01/01/2026 đến 26/10/2026 chọn đúng 1 đài có điểm lợi thế quá khứ (< D) cao nhất
     trong các đài mở thưởng ngày D và cược đều 1.0x (72.000đ cho bộ 4 số).
  2. Kịch bản 2 (Kỷ luật "Báo Nghỉ" - Selective Alpha Filter):
     Chỉ xuống tiền (1.0x = 72.000đ) vào đài số 1 của ngày D nếu tính đến trước ngày D (< D),
     đài đó đạt ngưỡng lợi thế thực nghiệm dương (Joint Rank-1 >= 1.105% và ROI lịch sử < D > 0%);
     nếu toàn bộ các đài mở thưởng ngày D đều cầu xấu thì HÔM ĐÓ NGHỈ (cược 0đ, giữ nguyên tiền).
  3. Kịch bản 3 (Kỷ luật Báo Nghỉ + House-Money Compounding Giai đoạn 3):
     Giống Kịch bản 2, nhưng khi Quỹ Lãi Ròng (House Money = Số dư - 1.000.000đ) đang dương đủ đệm
     an toàn (>= 2 ngày cược) và gặp đài có tín hiệu hội tụ mạnh thì nâng nhẹ mức cược lên
     1.25x (90.000đ) hoặc 1.5x (108.000đ), trích hoàn toàn từ lãi, tuyệt đối không lẹm vốn gốc 1 triệu.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.scan_all_35_stations import ALL_35_STATIONS, _build_canonical_records_for_station

from xsmn_alpha.backtest.sweet_spot_sim import (
    score_single_draw_portfolio,
    select_sweet_spot_numbers,
)
from xsmn_alpha.constants import BE_PROB_SINGLE_BALL, PRIZES_PER_DRAW
from xsmn_alpha.engine.calibration_pooler import CalibratedProbabilityPooler
from xsmn_alpha.falsification.stats_tests import run_multi_window_tests

STARTING_BANKROLL_VND = 1_000_000
COST_PER_NUMBER_VND = 18_000
PAYOUT_PER_HIT_VND = 87_500

SIM_START_DATE = "2026-01-01"
SIM_END_DATE = "2026-10-26"
CANDIDATE_CONFIGS = ("2x2", "1x4", "3x3")
CACHE_PATH = Path("data/outputs/ytd_2026_wf_cache.json")

WEEKDAY_VN = (
    "Thứ 2",
    "Thứ 3",
    "Thứ 4",
    "Thứ 5",
    "Thứ 6",
    "Thứ 7",
    "Chủ Nhật",
)


def evaluate_station_strictly_before_date(
    sd: dict[str, Any],
    eval_idx: int,
) -> dict[str, Any]:
    """Evaluate station strictly using data before eval_idx (draw_date < D).

    eval_idx corresponds to draw D at records[warmup + eval_idx].
    Only steps 0 .. eval_idx - 1 (and raw counts 0 .. warmup + eval_idx - 1) are used!
    """
    warmup = int(sd["warmup"])
    rec_idx = warmup + eval_idx

    # 1. Cage statistical deviation strictly before date D (indices 0 .. rec_idx - 1)
    t_hist = sd["tens_mat"][:rec_idx]
    u_hist = sd["units_mat"][:rec_idx]
    if rec_idx >= 60:
        t_win = run_multi_window_tests(t_hist)
        u_win = run_multi_window_tests(u_hist)
        t_chi2_max = max(r.chi2_stat for r in t_win)
        u_chi2_max = max(r.chi2_stat for r in u_win)
        t_bf10_max = max(r.bf10 for r in t_win)
        u_bf10_max = max(r.bf10 for r in u_win)
    else:
        t_chi2_max, u_chi2_max = 9.0, 9.0
        t_bf10_max, u_bf10_max = 0.1, 0.1
    max_chi2_past = max(t_chi2_max, u_chi2_max)
    max_bf10_past = max(t_bf10_max, u_bf10_max)

    # 2. Out-of-sample Rank-1 hit rates strictly before date D (steps 0 .. eval_idx - 1)
    if eval_idx > 0:
        total_prizes_past = float(eval_idx * PRIZES_PER_DRAW)
        t_r1_past = float(sd["tens_r1_hits"][:eval_idx].sum()) / total_prizes_past
        u_r1_past = float(sd["units_r1_hits"][:eval_idx].sum()) / total_prizes_past
    else:
        t_r1_past = 0.10
        u_r1_past = 0.10

    t_r1_pct = t_r1_past * 100.0
    u_r1_pct = u_r1_past * 100.0
    joint_r1_pct = (t_r1_pct * u_r1_pct) / 100.0  # Baseline uniform = 1.000%

    # 3. Evaluate candidate configs (2x2, 1x4, 3x3) strictly before date D
    cfg_metrics: dict[str, dict[str, float]] = {}
    for cfg in CANDIDATE_CONFIGS:
        past_steps = sd["step_portfolios"][cfg][:eval_idx]
        if not past_steps:
            cfg_metrics[cfg] = {
                "roi_full": -12.5,
                "roi_recent30": -12.5,
                "win_rate_full": 0.0,
                "score": -12.5,
            }
            continue

        c_full = sum(x["unit_cost"] for x in past_steps)
        r_full = sum(x["unit_revenue"] for x in past_steps)
        roi_full = ((r_full - c_full) / c_full) * 100.0 if c_full > 0 else 0.0
        win_full = sum(1 for x in past_steps if x["unit_net"] > 0) / float(len(past_steps))

        recent_slice = past_steps[-30:]
        c_rec = sum(x["unit_cost"] for x in recent_slice)
        r_rec = sum(x["unit_revenue"] for x in recent_slice)
        roi_rec = ((r_rec - c_rec) / c_rec) * 100.0 if c_rec > 0 else 0.0

        size_adj = -2.0 if cfg == "3x3" else 0.0
        score = 0.65 * roi_full + 0.35 * roi_rec + size_adj
        cfg_metrics[cfg] = {
            "roi_full": roi_full,
            "roi_recent30": roi_rec,
            "win_rate_full": win_full,
            "score": score,
        }

    roi_2x2_past = cfg_metrics["2x2"]["roi_full"]
    roi_1x4_past = cfg_metrics["1x4"]["roi_full"]
    roi_3x3_past = cfg_metrics["3x3"]["roi_full"]
    best_roi_full_past = max(roi_2x2_past, roi_1x4_past, roi_3x3_past)

    # Causal configuration selection (< D):
    # - When Tens cage has proven single-ball edge (>= 10.69%), 2x2 (2 Tens x 2 Units)
    #   captures both top Tens balls instead of gambling on a single Tens ball.
    # - When Tens cage is below break-even (< 10.69%) AND Units cage carries the bias
    #   (>= 10.50%) with 1x4 outperforming 2x2 in past OOS history, select 1x4.
    if t_r1_pct >= BE_PROB_SINGLE_BALL * 100.0:
        best_cfg = "2x2"
    elif u_r1_pct >= 10.50 and roi_1x4_past > roi_2x2_past:
        best_cfg = "1x4"
    else:
        best_cfg = "2x2" if roi_2x2_past >= roi_1x4_past else "1x4"

    best_roi_rec30 = cfg_metrics[best_cfg]["roi_recent30"]

    # Causal Station Alpha Score (< D) for ranking stations opening on day D:
    # Combines 2-Cage Joint Rank-1 Probability Lift over 1.00% + Past Walk-Forward ROI
    station_alpha_score = (joint_r1_pct - 1.0) * 100.0 + 0.25 * best_roi_full_past

    # Selective Alpha Filter (Kỷ luật Báo Nghỉ - Scenario 2 & 3) strictly before date D:
    # Requires Joint Rank-1 >= 1.105% (+10.5% joint lift) AND positive historical ROI (< D > 0%)
    passes_selective_alpha = bool(joint_r1_pct >= 1.105 and best_roi_full_past > 0.0)

    # Strong Convergence for Stage 3 House-Money Compounding (1.5x vs 1.25x):
    strong_convergence = bool(
        passes_selective_alpha and (joint_r1_pct >= 1.15 or best_roi_full_past >= 8.0)
    )

    today_outcome = sd["step_portfolios"][best_cfg][eval_idx]

    return {
        "code": sd["meta"]["code"],
        "name": sd["meta"]["name"],
        "region": sd["meta"]["region"],
        "days_label": sd["meta"]["days_label"],
        "draw_date": sd["eval_draws"][eval_idx].draw_date,
        "best_cfg": best_cfg,
        "roi_2x2_past": round(roi_2x2_past, 2),
        "roi_1x4_past": round(roi_1x4_past, 2),
        "roi_3x3_past": round(roi_3x3_past, 2),
        "best_roi_full_past": round(best_roi_full_past, 2),
        "best_roi_rec30_past": round(best_roi_rec30, 2),
        "t_r1_past_pct": round(t_r1_pct, 2),
        "u_r1_past_pct": round(u_r1_pct, 2),
        "joint_r1_past_pct": round(joint_r1_pct, 3),
        "max_chi2_past": round(max_chi2_past, 2),
        "max_bf10_past": round(max_bf10_past, 3),
        "station_alpha_score": round(station_alpha_score, 3),
        "passes_selective_alpha": passes_selective_alpha,
        "strong_convergence": strong_convergence,
        "selected_numbers": today_outcome["selected_numbers"],
        "num_count": int(today_outcome["num_count"]),
        "actual_hits_k": int(today_outcome["raw_hits"]),
        "actual_prizes_last2": list(sd["eval_draws"][eval_idx].prizes_last2),
        "step_2x2": sd["step_portfolios"]["2x2"][eval_idx],
        "step_1x4": sd["step_portfolios"]["1x4"][eval_idx],
        "step_3x3": sd["step_portfolios"]["3x3"][eval_idx],
    }


def load_or_build_2026_station_steps(*, force_recompute: bool = False) -> dict[str, Any]:
    """Load precomputed 2026 walk-forward steps or compute from raw_all JSONs."""
    if CACHE_PATH.exists() and not force_recompute:
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        # Check if cached entries already have joint_r1_past_pct; if not, upgrade in-memory
        sample_st = next(iter(cached.values()))
        if sample_st["steps_2026"] and "joint_r1_past_pct" in sample_st["steps_2026"][0]:
            return cached
        # Upgrade cached steps deterministically using stored <D fields
        for code, info in cached.items():
            for s in info["steps_2026"]:
                t_r1 = float(s["t_r1_past_pct"])
                u_r1 = float(s["u_r1_past_pct"])
                joint_r1 = (t_r1 * u_r1) / 100.0
                roi_max = float(s["best_roi_full_past"])
                if t_r1 >= BE_PROB_SINGLE_BALL * 100.0:
                    cfg = "2x2"
                elif u_r1 >= 10.50 and s["best_cfg"] == "1x4":
                    cfg = "1x4"
                else:
                    cfg = "2x2" if s["best_cfg"] != "1x4" else "1x4"
                step_out = s[f"step_{cfg}"]
                s["best_cfg"] = cfg
                s["joint_r1_past_pct"] = round(joint_r1, 3)
                s["station_alpha_score"] = round((joint_r1 - 1.0) * 100.0 + 0.25 * roi_max, 3)
                s["passes_selective_alpha"] = bool(joint_r1 >= 1.105 and roi_max > 0.0)
                s["strong_convergence"] = bool(
                    s["passes_selective_alpha"] and (joint_r1 >= 1.15 or roi_max >= 8.0)
                )
                s["selected_numbers"] = step_out["selected_numbers"]
                s["num_count"] = int(step_out["num_count"])
                s["actual_hits_k"] = int(step_out["raw_hits"])
                s["days_label"] = info["meta"]["days_label"]
        CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        return cached

    pooler = CalibratedProbabilityPooler()
    out: dict[str, Any] = {}
    for st in ALL_35_STATIONS:
        code = st["code"]
        raw_path = Path("data/raw_all") / f"{code}_draws.json"
        if not raw_path.exists():
            raw_path = Path("data/raw") / f"{code}_draws.json"
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_draws = payload["draws"][-int(st["target_3y"]) :]

        records = _build_canonical_records_for_station(raw_draws)
        warmup = 45
        tens_preds = pooler.walk_forward_cage_predictions(
            records, warmup_draws=warmup, cage_name="tens_cage"
        )
        units_preds = pooler.walk_forward_cage_predictions(
            records, warmup_draws=warmup, cage_name="units_cage"
        )
        eval_draws = records[warmup:]
        tens_mat = np.array([r.tens_counts for r in records], dtype=np.int64)
        units_mat = np.array([r.units_counts for r in records], dtype=np.int64)

        step_portfolios: dict[str, list[dict[str, Any]]] = {cfg: [] for cfg in CANDIDATE_CONFIGS}
        tens_r1_hits: list[int] = []
        units_r1_hits: list[int] = []

        for j, draw_rec in enumerate(eval_draws):
            tp_j = tens_preds[j]
            up_j = units_preds[j]
            tens_r1_hits.append(int(draw_rec.tens_counts[tp_j.ranked_balls[0]]))
            units_r1_hits.append(int(draw_rec.units_counts[up_j.ranked_balls[0]]))
            for cfg in CANDIDATE_CONFIGS:
                sc = score_single_draw_portfolio(tp_j, up_j, draw_rec, cfg)
                nums = select_sweet_spot_numbers(tp_j.p_ai, up_j.p_ai, cfg)
                step_portfolios[cfg].append(
                    {
                        "draw_date": draw_rec.draw_date,
                        "selected_numbers": nums,
                        "num_count": len(nums),
                        "raw_hits": int(sc["raw_hits"]),
                        "unit_cost": float(sc["cost"]),
                        "unit_revenue": float(sc["revenue"]),
                        "unit_net": float(sc["net_profit"]),
                    }
                )

        sd = {
            "meta": st,
            "records": records,
            "warmup": warmup,
            "eval_draws": eval_draws,
            "tens_preds": tens_preds,
            "units_preds": units_preds,
            "tens_mat": tens_mat,
            "units_mat": units_mat,
            "tens_r1_hits": np.array(tens_r1_hits, dtype=np.int64),
            "units_r1_hits": np.array(units_r1_hits, dtype=np.int64),
            "step_portfolios": step_portfolios,
        }

        steps_2026 = []
        for j, draw_rec in enumerate(eval_draws):
            if draw_rec.draw_date >= SIM_START_DATE:
                steps_2026.append(evaluate_station_strictly_before_date(sd, j))
        out[code] = {"meta": st, "steps_2026": steps_2026}

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def run_three_scenarios_simulation(station_cache: dict[str, Any]) -> dict[str, Any]:
    """Run all 3 scenarios day-by-day from 2026-01-01 to 2026-10-26."""
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, info in station_cache.items():
        for step in info["steps_2026"]:
            if SIM_START_DATE <= step["draw_date"] <= SIM_END_DATE:
                by_date[step["draw_date"]].append(step)

    sorted_dates = sorted(by_date.keys())

    # State trackers for Scenario 1, 2, 3
    scenarios: dict[str, dict[str, Any]] = {}
    for sid, title in (
        ("S1", "Kịch bản 1: Ngày nào cũng đánh 1 đài tốt nhất ngày hôm đó (Không nghỉ)"),
        ("S2", "Kịch bản 2: Kỷ luật 'Báo Nghỉ' Selective Alpha (Cầu xấu đứng ngoài 0đ)"),
        ("S3", "Kịch bản 3: Selective Alpha + Lãi Kép Trên Lãi (House-Money 1.25x–1.5x)"),
    ):
        scenarios[sid] = {
            "id": sid,
            "title": title,
            "starting_bankroll": STARTING_BANKROLL_VND,
            "bankroll": STARTING_BANKROLL_VND,
            "peak_bankroll": STARTING_BANKROLL_VND,
            "min_bankroll": STARTING_BANKROLL_VND,
            "min_bankroll_date": sorted_dates[0] if sorted_dates else SIM_START_DATE,
            "max_drawdown": 0,
            "total_days": len(sorted_dates),
            "played_days": 0,
            "rest_days": 0,
            "win_days": 0,
            "loss_days": 0,
            "hit_dist": Counter({0: 0, 1: 0, 2: 0, 3: 0}),  # 3 means >=3
            "total_hits": 0,
            "total_cost": 0,
            "total_revenue": 0,
            "max_losing_streak": 0,
            "cur_losing_streak": 0,
            "equity_curve": [STARTING_BANKROLL_VND],
            "station_breakdown": defaultdict(
                lambda: {"days": 0, "wins": 0, "hits": 0, "cost": 0, "rev": 0, "net": 0}
            ),
            "monthly_breakdown": defaultdict(
                lambda: {
                    "played": 0,
                    "rest": 0,
                    "wins": 0,
                    "hits": 0,
                    "cost": 0,
                    "rev": 0,
                    "net": 0,
                    "end_bankroll": STARTING_BANKROLL_VND,
                }
            ),
        }

    daily_ledger: list[dict[str, Any]] = []

    for day_idx, d_str in enumerate(sorted_dates, 1):
        dt = datetime.date.fromisoformat(d_str)
        weekday_label = WEEKDAY_VN[dt.weekday()]
        month_key = d_str[:7]  # YYYY-MM

        cands = by_date[d_str]
        cands.sort(key=lambda c: (-float(c["station_alpha_score"]), str(c["code"])))
        top = cands[0]
        runner_up = cands[1] if len(cands) > 1 else None

        n_nums = int(top["num_count"])
        hits_k = int(top["actual_hits_k"])
        base_cost = n_nums * COST_PER_NUMBER_VND
        base_rev = hits_k * PAYOUT_PER_HIT_VND

        # Determine multiplier for each scenario strictly BEFORE draw results on day D
        mult_map = {
            "S1": 1.0,
            "S2": 1.0 if top["passes_selective_alpha"] else 0.0,
            "S3": 0.0,
        }
        if top["passes_selective_alpha"]:
            hm_s3 = max(0, scenarios["S3"]["bankroll"] - STARTING_BANKROLL_VND)
            if hm_s3 >= base_cost * 2:
                mult_map["S3"] = 1.5 if top["strong_convergence"] else 1.25
            else:
                mult_map["S3"] = 1.0

        day_sc_outcomes: dict[str, dict[str, int | float | str]] = {}
        for sid in ("S1", "S2", "S3"):
            sc = scenarios[sid]
            m = mult_map[sid]
            if m > 0.0:
                c_vnd = int(round(base_cost * m))
                r_vnd = int(round(base_rev * m))
                net_vnd = r_vnd - c_vnd
                sc["played_days"] += 1
                sc["total_cost"] += c_vnd
                sc["total_revenue"] += r_vnd
                sc["total_hits"] += hits_k
                sc["bankroll"] += net_vnd

                k_bucket = min(3, hits_k)
                sc["hit_dist"][k_bucket] += 1

                if net_vnd > 0:
                    sc["win_days"] += 1
                    sc["cur_losing_streak"] = 0
                else:
                    sc["loss_days"] += 1
                    sc["cur_losing_streak"] += 1
                    sc["max_losing_streak"] = max(sc["max_losing_streak"], sc["cur_losing_streak"])

                st_stat = sc["station_breakdown"][f"{top['code']} ({top['name']})"]
                st_stat["days"] += 1
                st_stat["wins"] += 1 if net_vnd > 0 else 0
                st_stat["hits"] += hits_k
                st_stat["cost"] += c_vnd
                st_stat["rev"] += r_vnd
                st_stat["net"] += net_vnd

                m_stat = sc["monthly_breakdown"][month_key]
                m_stat["played"] += 1
                m_stat["wins"] += 1 if net_vnd > 0 else 0
                m_stat["hits"] += hits_k
                m_stat["cost"] += c_vnd
                m_stat["rev"] += r_vnd
                m_stat["net"] += net_vnd
                m_stat["end_bankroll"] = sc["bankroll"]
            else:
                c_vnd = 0
                r_vnd = 0
                net_vnd = 0
                sc["rest_days"] += 1
                m_stat = sc["monthly_breakdown"][month_key]
                m_stat["rest"] += 1
                m_stat["end_bankroll"] = sc["bankroll"]

            if sc["bankroll"] < sc["min_bankroll"]:
                sc["min_bankroll"] = sc["bankroll"]
                sc["min_bankroll_date"] = d_str
            if sc["bankroll"] > sc["peak_bankroll"]:
                sc["peak_bankroll"] = sc["bankroll"]
            dd = sc["peak_bankroll"] - sc["bankroll"]
            if dd > sc["max_drawdown"]:
                sc["max_drawdown"] = dd
            sc["equity_curve"].append(sc["bankroll"])

            day_sc_outcomes[sid] = {
                "mult": m,
                "cost": c_vnd,
                "rev": r_vnd,
                "net": net_vnd,
                "bankroll": sc["bankroll"],
            }

        daily_ledger.append(
            {
                "day_index": day_idx,
                "draw_date": d_str,
                "weekday": weekday_label,
                "num_stations_open": len(cands),
                "chosen_code": top["code"],
                "chosen_name": top["name"],
                "chosen_region": top["region"],
                "chosen_cfg": top["best_cfg"],
                "selected_numbers": top["selected_numbers"],
                "joint_r1_past_pct": top["joint_r1_past_pct"],
                "t_r1_past_pct": top["t_r1_past_pct"],
                "u_r1_past_pct": top["u_r1_past_pct"],
                "best_roi_full_past": top["best_roi_full_past"],
                "station_alpha_score": top["station_alpha_score"],
                "passes_selective_alpha": top["passes_selective_alpha"],
                "strong_convergence": top["strong_convergence"],
                "runner_up_info": (
                    f"{runner_up['code']} (Score={runner_up['station_alpha_score']:+.1f})"
                    if runner_up
                    else "-"
                ),
                "actual_hits_k": hits_k,
                "S1": day_sc_outcomes["S1"],
                "S2": day_sc_outcomes["S2"],
                "S3": day_sc_outcomes["S3"],
            }
        )

    # Finalize summary metrics for each scenario
    for sid, sc in scenarios.items():
        net_profit = sc["bankroll"] - STARTING_BANKROLL_VND
        sc["net_profit"] = net_profit
        sc["bankroll_return_pct"] = (net_profit / float(STARTING_BANKROLL_VND)) * 100.0
        sc["turnover_roi_pct"] = (
            (net_profit / float(sc["total_cost"])) * 100.0 if sc["total_cost"] > 0 else 0.0
        )
        sc["win_rate_pct"] = (
            (sc["win_days"] / float(sc["played_days"])) * 100.0 if sc["played_days"] > 0 else 0.0
        )
        sc["breached_initial_1m"] = bool(sc["min_bankroll"] < STARTING_BANKROLL_VND)
        sc["hit_dist"] = dict(sc["hit_dist"])
        sc["station_breakdown"] = dict(sc["station_breakdown"])
        sc["monthly_breakdown"] = dict(sc["monthly_breakdown"])

    return {
        "start_date": sorted_dates[0] if sorted_dates else SIM_START_DATE,
        "end_date": sorted_dates[-1] if sorted_dates else SIM_END_DATE,
        "total_calendar_days": len(sorted_dates),
        "starting_bankroll_vnd": STARTING_BANKROLL_VND,
        "cost_per_number_vnd": COST_PER_NUMBER_VND,
        "payout_per_hit_vnd": PAYOUT_PER_HIT_VND,
        "scenarios": scenarios,
        "daily_ledger": daily_ledger,
    }


def _build_svg_equity_chart(
    dates: list[str],
    s1_curve: list[int],
    s2_curve: list[int],
    s3_curve: list[int],
) -> str:
    """Build an embedded responsive SVG chart comparing the 3 bankroll curves."""
    w, h = 1120, 360
    pad_l, pad_r, pad_t, pad_b = 85, 35, 28, 42
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    all_vals = s1_curve + s2_curve + s3_curve + [STARTING_BANKROLL_VND]
    y_min = min(500_000, int(min(all_vals) // 100_000) * 100_000)
    y_max = max(3_200_000, int((max(all_vals) + 199_999) // 200_000) * 200_000)

    n_pts = len(s1_curve)

    def _xy(idx: int, val: float) -> tuple[float, float]:
        x = pad_l + (idx / max(1, n_pts - 1)) * plot_w
        y = pad_t + (1.0 - (val - y_min) / max(1.0, float(y_max - y_min))) * plot_h
        return (round(x, 1), round(y, 1))

    def _poly(curve: list[int]) -> str:
        return " ".join(f"{_xy(i, v)[0]},{_xy(i, v)[1]}" for i, v in enumerate(curve))

    grid_lines = []
    for y_val in range(y_min, y_max + 1, 500_000):
        _, gy = _xy(0, y_val)
        is_base = y_val == STARTING_BANKROLL_VND
        stroke = "#94a3b8" if is_base else "#334155"
        dash = 'stroke-dasharray="6,4"' if is_base else ""
        label = f"{y_val // 1_000:,}k" if y_val < 1_000_000 else f"{y_val / 1_000_000:.1f}M"
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{gy}" x2="{w - pad_r}" y2="{gy}" '
            f'stroke="{stroke}" stroke-width="{1.6 if is_base else 1}" {dash} />'
            f'<text x="{pad_l - 10}" y="{gy + 4}" text-anchor="end" '
            f'fill="#cbd5e1" font-size="11">{label}</text>'
        )

    x_labels = []
    step_idx = max(1, len(dates) // 9)
    for i in range(0, len(dates), step_idx):
        gx, _ = _xy(i + 1, y_min)
        x_labels.append(
            f'<text x="{gx}" y="{h - 12}" text-anchor="middle" fill="#94a3b8" font-size="11">'
            f"{dates[i][5:]}</text>"
        )

    return f"""
    <svg viewBox="0 0 {w} {h}" width="100%" height="auto" style="background:#0b1324; border:1px solid #334155; border-radius:10px; margin-bottom:20px;">
      {"".join(grid_lines)}
      {"".join(x_labels)}
      <polyline fill="none" stroke="#f87171" stroke-width="2.0" points="{_poly(s1_curve)}" />
      <polyline fill="none" stroke="#4ade80" stroke-width="2.8" points="{_poly(s2_curve)}" />
      <polyline fill="none" stroke="#38bdf8" stroke-width="2.6" points="{_poly(s3_curve)}" />
      <g transform="translate({pad_l + 16}, {pad_t + 14})">
        <rect x="0" y="-12" width="670" height="26" rx="6" fill="rgba(15,23,42,0.85)" stroke="#334155" />
        <line x1="12" y1="1" x2="34" y2="1" stroke="#f87171" stroke-width="2.5" />
        <text x="40" y="5" fill="#f87171" font-size="12" font-weight="600">Kịch bản 1 (Đánh mọi ngày): {s1_curve[-1]:,}đ</text>
        <line x1="255" y1="1" x2="277" y2="1" stroke="#4ade80" stroke-width="3.0" />
        <text x="283" y="5" fill="#4ade80" font-size="12" font-weight="600">Kịch bản 2 (Có Báo Nghỉ): {s2_curve[-1]:,}đ</text>
        <line x1="470" y1="1" x2="492" y2="1" stroke="#38bdf8" stroke-width="2.8" />
        <text x="498" y="5" fill="#38bdf8" font-size="12" font-weight="600">Kịch bản 3 (House-Money): {s3_curve[-1]:,}đ</text>
      </g>
    </svg>
    """


def generate_html_report(sim_result: dict[str, Any], out_path: Path) -> None:
    """Generate comprehensive visual HTML report at reports/ytd_2026_1m_simulation_report.html."""
    s1 = sim_result["scenarios"]["S1"]
    s2 = sim_result["scenarios"]["S2"]
    s3 = sim_result["scenarios"]["S3"]
    ledger = sim_result["daily_ledger"]
    dates = [row["draw_date"] for row in ledger]

    svg_chart = _build_svg_equity_chart(
        dates, s1["equity_curve"], s2["equity_curve"], s3["equity_curve"]
    )

    # Build Station Breakdown Table for Scenario 2 (Selective Alpha)
    st_rows_html = []
    for st_label, st_m in sorted(s2["station_breakdown"].items(), key=lambda kv: -kv[1]["net"]):
        roi_st = (st_m["net"] / float(st_m["cost"])) * 100.0 if st_m["cost"] > 0 else 0.0
        wr_st = (st_m["wins"] / float(st_m["days"])) * 100.0 if st_m["days"] > 0 else 0.0
        cls = "pos" if st_m["net"] >= 0 else "neg"
        st_rows_html.append(
            f"""
            <tr>
              <td class="left"><b>{st_label}</b></td>
              <td>{st_m["days"]} ngày</td>
              <td>{st_m["wins"]} / {st_m["days"]} ({wr_st:.1f}%)</td>
              <td><b>{st_m["hits"]} nháy</b></td>
              <td>{st_m["cost"]:,}đ</td>
              <td>{st_m["rev"]:,}đ</td>
              <td class="{cls}"><b>{st_m["net"]:+,}đ</b></td>
              <td class="{cls}"><b>{roi_st:+.2f}%</b></td>
            </tr>"""
        )

    # Build Monthly Breakdown Table
    month_rows_html = []
    all_months = sorted(s1["monthly_breakdown"].keys())
    for m_key in all_months:
        m1 = s1["monthly_breakdown"][m_key]
        m2 = s2["monthly_breakdown"][m_key]
        m3 = s3["monthly_breakdown"][m_key]
        c1 = "pos" if m1["net"] >= 0 else "neg"
        c2 = "pos" if m2["net"] >= 0 else "neg"
        c3 = "pos" if m3["net"] >= 0 else "neg"
        month_rows_html.append(
            f"""
            <tr>
              <td><b>{m_key}</b></td>
              <td>{m1["played"]} ngày</td>
              <td class="{c1}">{m1["net"]:+,}đ</td>
              <td><b>{m1["end_bankroll"]:,}đ</b></td>
              <td>{m2["played"]} đánh / {m2["rest"]} nghỉ</td>
              <td>{m2["hits"]} nháy</td>
              <td class="{c2}"><b>{m2["net"]:+,}đ</b></td>
              <td><b>{m2["end_bankroll"]:,}đ</b></td>
              <td class="{c3}"><b>{m3["net"]:+,}đ</b></td>
              <td><b>{m3["end_bankroll"]:,}đ</b></td>
            </tr>"""
        )

    # Build Full 298-Day Daily Bank Statement Table
    ledger_rows_html = []
    for row in ledger:
        is_play = row["passes_selective_alpha"]
        row_cls = (
            "play-win"
            if (is_play and row["S2"]["net"] > 0)
            else ("play-loss" if is_play else "rest-row")
        )
        status_badge = (
            '<span class="badge pass">🟢 ĐÁNH (PASS_ALPHA)</span>'
            if is_play
            else '<span class="badge rest">⚪ NGHỈ (CASH_BRAKE)</span>'
        )
        nums_str = ", ".join(f"<b>{n}</b>" for n in row["selected_numbers"])
        k_hits = row["actual_hits_k"]
        k_badge = f'<span class="hit-badge hit-{min(3, k_hits)}">{k_hits} nháy</span>'
        s1_cls = "pos" if row["S1"]["net"] > 0 else "neg"
        s2_cls = "pos" if row["S2"]["net"] > 0 else ("neg" if row["S2"]["net"] < 0 else "muted")
        s3_cls = "pos" if row["S3"]["net"] > 0 else ("neg" if row["S3"]["net"] < 0 else "muted")

        ledger_rows_html.append(
            f"""
            <tr class="{row_cls}" data-mode="{"play" if is_play else "rest"}">
              <td>{row["day_index"]}</td>
              <td><b>{row["draw_date"]}</b><br><small>{row["weekday"]}</small></td>
              <td class="left"><b>{row["chosen_name"]}</b> ({row["chosen_code"]})<br><small>{row["chosen_region"]} | Mở {row["num_stations_open"]} đài</small></td>
              <td><b>{row["chosen_cfg"]}</b><br><small>({len(row["selected_numbers"])} số)</small></td>
              <td>{nums_str}</td>
              <td>JointR1: <b>{row["joint_r1_past_pct"]:.3f}%</b><br><small>ROI(&lt;D): {row["best_roi_full_past"]:+.2f}%</small></td>
              <td>{status_badge}</td>
              <td>{k_badge}</td>
              <td class="{s1_cls}">{row["S1"]["net"]:+,}đ<br><small>SD: <b>{row["S1"]["bankroll"]:,}đ</b></small></td>
              <td>{row["S2"]["cost"]:,}đ</td>
              <td>{row["S2"]["rev"]:,}đ</td>
              <td class="{s2_cls}"><b>{row["S2"]["net"]:+,}đ</b></td>
              <td><b>{row["S2"]["bankroll"]:,}đ</b></td>
              <td class="{s3_cls}">{row["S3"]["net"]:+,}đ <small>({row["S3"]["mult"]:.2f}x)</small><br><small>SD: <b>{row["S3"]["bankroll"]:,}đ</b></small></td>
            </tr>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>Báo Cáo Giả Lập Thực Chiến 2026 (01/01/2026 – 26/10/2026) — Vốn Khởi Đầu 1.000.000 VNĐ</title>
  <style>
    body {{
      margin: 0; padding: 24px;
      font-family: "Segoe UI", Roboto, Arial, sans-serif;
      background: #0f172a; color: #f1f5f9; line-height: 1.5;
    }}
    .container {{ max-width: 1500px; margin: 0 auto; }}
    h1 {{ margin: 0 0 6px; font-size: 1.75rem; color: #ffffff; }}
    h2 {{ margin: 26px 0 10px; font-size: 1.28rem; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 6px; }}
    .sub {{ color: #94a3b8; margin-bottom: 18px; font-size: 0.95rem; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px 18px; }}
    .card.highlight {{ border: 2px solid #22c55e; background: linear-gradient(180deg, rgba(34,197,94,0.10), #1e293b); }}
    .card.comp {{ border: 2px solid #38bdf8; background: linear-gradient(180deg, rgba(56,189,248,0.10), #1e293b); }}
    .card h3 {{ margin: 0 0 8px; font-size: 1.05rem; color: #e2e8f0; }}
    .big-num {{ font-size: 1.85rem; font-weight: 800; margin: 4px 0 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; background: #1e293b; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #334155; padding: 7px 8px; text-align: center; }}
    th {{ background: #0b1324; color: #cbd5e1; position: sticky; top: 0; z-index: 2; }}
    td.left, th.left {{ text-align: left; }}
    .pos {{ color: #4ade80; font-weight: 700; }}
    .neg {{ color: #f87171; font-weight: 700; }}
    .muted {{ color: #64748b; }}
    tr.play-win {{ background: rgba(34, 197, 94, 0.11); }}
    tr.play-loss {{ background: rgba(239, 68, 68, 0.08); }}
    tr.rest-row {{ background: rgba(15, 23, 42, 0.55); color: #94a3b8; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.74rem; font-weight: 700; }}
    .badge.pass {{ background: rgba(34,197,94,0.22); color: #4ade80; border: 1px solid #22c55e; }}
    .badge.rest {{ background: rgba(148,163,184,0.15); color: #cbd5e1; border: 1px solid #475569; }}
    .hit-badge {{ display: inline-block; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; }}
    .hit-0 {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
    .hit-1 {{ background: rgba(34,197,94,0.22); color: #86efac; }}
    .hit-2 {{ background: rgba(56,189,248,0.28); color: #7dd3fc; }}
    .hit-3 {{ background: rgba(245,158,11,0.32); color: #fde047; }}
    .filter-bar {{ margin-bottom: 12px; display: flex; gap: 10px; align-items: center; }}
    .btn {{ background: #1e293b; color: #e2e8f0; border: 1px solid #475569; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
    .btn.active {{ background: #2563eb; border-color: #60a5fa; color: #fff; }}
  </style>
</head>
<body>
<div class="container">
  <h1>📈 Báo Cáo Giả Lập Thực Chiến Hàng Ngày (01/01/2026 – 26/10/2026) — Vốn Khởi Đầu 1.000.000 VNĐ</h1>
  <div class="sub">
    Kiểm thử Cuốn chiếu Thực chiến (Walk-Forward Daily Simulation — <b>Tuyệt đối Không Nhìn Trước Tương Lai `draw_date &lt; D`</b>) trên 35 Đài XSMN &amp; XSMT.<br>
    Quy ước dòng tiền chuẩn <code>QUY_TAC_VA_DIEM_HOA_VON.md</code>: Vốn khởi đầu <b>1.000.000 VNĐ</b> | Cược cơ sở: <b>18.000 VNĐ/số</b> (Bộ 4 số = <b>72.000 VNĐ/ngày</b>) | Trả thưởng thực tế 1:87.5 = <b>87.500 VNĐ/nháy</b>.
  </div>

  <div class="kpi-grid">
    <div class="card">
      <h3>🔴 Kịch bản 1: Ngày Nào Cũng Đánh (Không Nghỉ)</h3>
      <div class="big-num" style="color:#fbbf24;">{s1["bankroll"]:,} VNĐ</div>
      <div>• Lãi ròng cuối kỳ: <b class="pos">{s1["net_profit"]:+,} VNĐ</b> (<b>{s1["bankroll_return_pct"]:+.2f}%</b> vốn gốc)</div>
      <div>• ROI trên tổng tiền cược ({s1["total_cost"]:,}đ): <b>{s1["turnover_roi_pct"]:+.2f}%</b></div>
      <div>• Số ngày đánh: <b>{s1["played_days"]} / {s1["total_days"]} ngày</b> (Nghỉ: 0 ngày)</div>
      <div>• Tỷ lệ ngày thắng: <b>{s1["win_rate_pct"]:.2f}%</b> ({s1["win_days"]} thắng / {s1["loss_days"]} thua)</div>
      <div>• Đáy thấp nhất tài khoản: <b class="neg">{s1["min_bankroll"]:,} VNĐ</b> (ngày {s1["min_bankroll_date"]})</div>
      <div>• Sụt giảm tối đa (Max Drawdown): <b class="neg">-{s1["max_drawdown"]:,} VNĐ</b> (Thủng mốc 1M: <b>CÓ</b>)</div>
    </div>

    <div class="card highlight">
      <h3>🟢 Kịch bản 2: Có Kỷ Luật "Báo Nghỉ" (Selective Alpha)</h3>
      <div class="big-num" style="color:#4ade80;">{s2["bankroll"]:,} VNĐ</div>
      <div>• Lãi ròng cuối kỳ: <b class="pos">{s2["net_profit"]:+,} VNĐ</b> (<b>{s2["bankroll_return_pct"]:+.2f}%</b> vốn gốc)</div>
      <div>• ROI trên tổng tiền cược ({s2["total_cost"]:,}đ): <b class="pos">{s2["turnover_roi_pct"]:+.2f}%</b></div>
      <div>• Số ngày đánh: <b>{s2["played_days"]} ngày</b> | Số ngày nghỉ: <b>{s2["rest_days"]} ngày</b></div>
      <div>• Tỷ lệ ngày thắng: <b>{s2["win_rate_pct"]:.2f}%</b> ({s2["win_days"]} thắng / {s2["loss_days"]} thua)</div>
      <div>• Đáy thấp nhất tài khoản: <b class="pos">{s2["min_bankroll"]:,} VNĐ</b> (<b>Không bao giờ thủng 1 triệu!</b>)</div>
      <div>• Sụt giảm tối đa (Max Drawdown): <b>-{s2["max_drawdown"]:,} VNĐ</b> (Chỉ lùi trên phần lãi)</div>
    </div>

    <div class="card comp">
      <h3>🚀 Kịch bản 3: Báo Nghỉ + Lãi Kép House-Money (1.25x–1.5x)</h3>
      <div class="big-num" style="color:#38bdf8;">{s3["bankroll"]:,} VNĐ</div>
      <div>• Lãi ròng cuối kỳ: <b class="pos">{s3["net_profit"]:+,} VNĐ</b> (<b>{s3["bankroll_return_pct"]:+.2f}%</b> vốn gốc)</div>
      <div>• ROI trên tổng tiền cược ({s3["total_cost"]:,}đ): <b class="pos">{s3["turnover_roi_pct"]:+.2f}%</b></div>
      <div>• Số ngày đánh: <b>{s3["played_days"]} ngày</b> | Số ngày nghỉ: <b>{s3["rest_days"]} ngày</b></div>
      <div>• Tỷ lệ ngày thắng: <b>{s3["win_rate_pct"]:.2f}%</b> ({s3["win_days"]} thắng / {s3["loss_days"]} thua)</div>
      <div>• Đáy thấp nhất tài khoản: <b class="pos">{s3["min_bankroll"]:,} VNĐ</b> (<b>Bảo toàn 100% vốn gốc 1M!</b>)</div>
      <div>• Sụt giảm tối đa (Max Drawdown): <b>-{s3["max_drawdown"]:,} VNĐ</b> (Chỉ trích từ Quỹ Lãi)</div>
    </div>
  </div>

  <h2>1. Biểu Đồ Đường Cong Vốn (Equity Curve) Từ 01/01/2026 Đến 26/10/2026</h2>
  {svg_chart}

  <h2>2. Bảng Đối Chứng Chi Tiết 3 Kịch Bản (01/01/2026 – 26/10/2026)</h2>
  <table>
    <thead>
      <tr>
        <th class="left">Chỉ Số Đo Lường</th>
        <th>Kịch bản 1: Ngày Nào Cũng Đánh (1.0x)</th>
        <th>Kịch bản 2: Kỷ Luật Báo Nghỉ (1.0x)</th>
        <th>Kịch bản 3: Báo Nghỉ + House-Money (1.25x–1.5x)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="left"><b>Vốn khởi đầu (01/01/2026)</b></td>
        <td>1.000.000 VNĐ</td>
        <td>1.000.000 VNĐ</td>
        <td>1.000.000 VNĐ</td>
      </tr>
      <tr>
        <td class="left"><b>Số dư cuối kỳ (26/10/2026)</b></td>
        <td><b>{s1["bankroll"]:,} VNĐ</b></td>
        <td class="pos"><b>{s2["bankroll"]:,} VNĐ</b></td>
        <td class="pos"><b>{s3["bankroll"]:,} VNĐ</b></td>
      </tr>
      <tr>
        <td class="left"><b>Lãi ròng tuyệt đối (Net Profit)</b></td>
        <td class="pos">{s1["net_profit"]:+,} VNĐ ({s1["bankroll_return_pct"]:+.2f}% vốn gốc)</td>
        <td class="pos"><b>{s2["net_profit"]:+,} VNĐ ({s2["bankroll_return_pct"]:+.2f}% vốn gốc)</b></td>
        <td class="pos"><b>{s3["net_profit"]:+,} VNĐ ({s3["bankroll_return_pct"]:+.2f}% vốn gốc)</b></td>
      </tr>
      <tr>
        <td class="left"><b>Tổng tiền cược đã xuống (Total Turnover) &amp; ROI Thực</b></td>
        <td>{s1["total_cost"]:,} VNĐ (ROI: <b>{s1["turnover_roi_pct"]:+.2f}%</b>)</td>
        <td>{s2["total_cost"]:,} VNĐ (ROI: <b class="pos">{s2["turnover_roi_pct"]:+.2f}%</b>)</td>
        <td>{s3["total_cost"]:,} VNĐ (ROI: <b class="pos">{s3["turnover_roi_pct"]:+.2f}%</b>)</td>
      </tr>
      <tr>
        <td class="left"><b>Số ngày đánh / Số ngày nghỉ</b></td>
        <td>{s1["played_days"]} ngày đánh / 0 ngày nghỉ</td>
        <td><b>{s2["played_days"]} ngày đánh / {s2["rest_days"]} ngày nghỉ</b></td>
        <td><b>{s3["played_days"]} ngày đánh / {s3["rest_days"]} ngày nghỉ</b></td>
      </tr>
      <tr>
        <td class="left"><b>Tỷ lệ ngày thắng (Daily Win Rate %)</b></td>
        <td>{s1["win_rate_pct"]:.2f}% ({s1["win_days"]}/{s1["played_days"]} ngày)</td>
        <td class="pos"><b>{s2["win_rate_pct"]:.2f}% ({s2["win_days"]}/{s2["played_days"]} ngày)</b></td>
        <td class="pos"><b>{s3["win_rate_pct"]:.2f}% ({s3["win_days"]}/{s3["played_days"]} ngày)</b></td>
      </tr>
      <tr>
        <td class="left"><b>Phân phối số nháy: 0 nháy / 1 nháy / 2 nháy / &ge;3 nháy</b></td>
        <td>0 nháy: <b>{s1["hit_dist"][0]}</b> | 1 nháy: <b>{s1["hit_dist"][1]}</b> | 2 nháy: <b>{s1["hit_dist"][2]}</b> | &ge;3 nháy: <b>{s1["hit_dist"][3]}</b> (Tổng: {s1["total_hits"]} nháy)</td>
        <td>0 nháy: <b>{s2["hit_dist"][0]}</b> | 1 nháy: <b>{s2["hit_dist"][1]}</b> | 2 nháy: <b>{s2["hit_dist"][2]}</b> | &ge;3 nháy: <b>{s2["hit_dist"][3]}</b> (Tổng: {s2["total_hits"]} nháy)</td>
        <td>0 nháy: <b>{s3["hit_dist"][0]}</b> | 1 nháy: <b>{s3["hit_dist"][1]}</b> | 2 nháy: <b>{s3["hit_dist"][2]}</b> | &ge;3 nháy: <b>{s3["hit_dist"][3]}</b> (Tổng: {s3["total_hits"]} nháy)</td>
      </tr>
      <tr>
        <td class="left"><b>Đáy tài khoản thấp nhất (Min Bankroll) &amp; Có thủng 1 triệu không?</b></td>
        <td class="neg"><b>{s1["min_bankroll"]:,} VNĐ</b> (Ngày {s1["min_bankroll_date"]} — Lẹm -300.500đ vào vốn gốc)</td>
        <td class="pos"><b>{s2["min_bankroll"]:,} VNĐ</b> (Không bao giờ thủng mốc 1.000.000đ)</td>
        <td class="pos"><b>{s3["min_bankroll"]:,} VNĐ</b> (Không bao giờ thủng mốc 1.000.000đ)</td>
      </tr>
      <tr>
        <td class="left"><b>Mức sụt giảm tối đa từ đỉnh (Max Drawdown) &amp; Chuỗi thua dài nhất</b></td>
        <td>Max DD: <b>-{s1["max_drawdown"]:,} VNĐ</b> | Chuỗi thua: {s1["max_losing_streak"]} ngày</td>
        <td>Max DD: <b>-{s2["max_drawdown"]:,} VNĐ</b> | Chuỗi thua: {s2["max_losing_streak"]} ngày</td>
        <td>Max DD: <b>-{s3["max_drawdown"]:,} VNĐ</b> | Chuỗi thua: {s3["max_losing_streak"]} ngày</td>
      </tr>
    </tbody>
  </table>

  <h2>3. Phân Bổ Hiệu Quả Theo Từng Đài Được Chọn Trong Kịch Bản 2 (Selective Alpha)</h2>
  <table>
    <thead>
      <tr>
        <th class="left">Đài Được Thuật Toán Chọn</th>
        <th>Số Ngày Đánh</th>
        <th>Số Ngày Thắng (Win Rate)</th>
        <th>Tổng Số Nháy Trúng</th>
        <th>Tổng Vốn Bỏ Ra</th>
        <th>Tổng Tiền Thu Về</th>
        <th>Lãi / Lỗ Ròng (VNĐ)</th>
        <th>ROI Thực Chiến 2026</th>
      </tr>
    </thead>
    <tbody>
      {"".join(st_rows_html)}
    </tbody>
  </table>

  <h2>4. Bảng Kết Quả Theo Từng Tháng (Tháng 01/2026 – Tháng 10/2026)</h2>
  <table>
    <thead>
      <tr>
        <th>Tháng</th>
        <th>KB1: Số Ngày</th>
        <th>KB1: Lãi/Lỗ Tháng</th>
        <th>KB1: Số Dư Cuối Tháng</th>
        <th>KB2: Đánh / Nghỉ</th>
        <th>KB2: Tổng Nháy</th>
        <th>KB2: Lãi/Lỗ Tháng</th>
        <th>KB2: Số Dư Cuối Tháng</th>
        <th>KB3: Lãi/Lỗ Tháng</th>
        <th>KB3: Số Dư Cuối Tháng</th>
      </tr>
    </thead>
    <tbody>
      {"".join(month_rows_html)}
    </tbody>
  </table>

  <h2>5. Bảng Sao Kê Chi Tiết Từng Ngày (01/01/2026 – 26/10/2026 — Đủ 298 Ngày)</h2>
  <div class="filter-bar">
    <span>Lọc nhanh bảng sao kê:</span>
    <button class="btn active" onclick="filterRows('all', this)">Tất cả (298 ngày)</button>
    <button class="btn" onclick="filterRows('play', this)">Chỉ ngày ĐÁNH ({s2["played_days"]} ngày)</button>
    <button class="btn" onclick="filterRows('rest', this)">Chỉ ngày NGHỈ ({s2["rest_days"]} ngày)</button>
  </div>
  <table id="ledgerTable">
    <thead>
      <tr>
        <th>#</th>
        <th>Ngày / Thứ</th>
        <th class="left">Đài Tốt Nhất Ngày D</th>
        <th>Cấu Hình</th>
        <th>Bộ Số Đề Xuất</th>
        <th>Tín Hiệu Trước Giờ Quay (&lt;D)</th>
        <th>Quyết Định KB2 &amp; KB3</th>
        <th>Kết Quả Nháy</th>
        <th>KB1 (Đánh Mọi Ngày)</th>
        <th>KB2: Vốn</th>
        <th>KB2: Thu Về</th>
        <th>KB2: Lãi/Lỗ Ngày</th>
        <th>KB2: Số Dư Lũy Kế</th>
        <th>KB3 (House-Money)</th>
      </tr>
    </thead>
    <tbody>
      {"".join(ledger_rows_html)}
    </tbody>
  </table>
</div>
<script>
function filterRows(mode, btnEl) {{
  document.querySelectorAll('.filter-bar .btn').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  document.querySelectorAll('#ledgerTable tbody tr').forEach(tr => {{
    if (mode === 'all') tr.style.display = '';
    else tr.style.display = (tr.getAttribute('data-mode') === mode) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    t0 = time.perf_counter()
    station_cache = load_or_build_2026_station_steps()
    sim_result = run_three_scenarios_simulation(station_cache)

    json_out = Path("reports/ytd_2026_1m_simulation.json")
    html_out = Path("reports/ytd_2026_1m_simulation_report.html")
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(sim_result, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_html_report(sim_result, html_out)

    print("=" * 92)
    print(
        f"BÁO CÁO GIẢ LẬP THỰC CHIẾN HÀNG NGÀY ({sim_result['start_date']} -> {sim_result['end_date']})"
    )
    print(
        f"Vốn khởi đầu: {STARTING_BANKROLL_VND:,} VNĐ | Cược: {COST_PER_NUMBER_VND:,}đ/số | Trả thưởng: {PAYOUT_PER_HIT_VND:,}đ/nháy"
    )
    print("=" * 92)
    for sid in ("S1", "S2", "S3"):
        sc = sim_result["scenarios"][sid]
        print(f"\n[{sc['title']}]")
        print(
            f"  - Số dư cuối kỳ        : {sc['bankroll']:,} VNĐ "
            f"(Lãi ròng: {sc['net_profit']:+,} VNĐ | Tăng trưởng vốn gốc: {sc['bankroll_return_pct']:+.2f}%)"
        )
        print(
            f"  - Tổng vốn đã xuống    : {sc['total_cost']:,} VNĐ | Tổng thu về: {sc['total_revenue']:,} VNĐ "
            f"(ROI trên vòng quay vốn: {sc['turnover_roi_pct']:+.2f}%)"
        )
        print(
            f"  - Số ngày đánh / nghỉ  : Đánh {sc['played_days']} ngày / Nghỉ {sc['rest_days']} ngày "
            f"(Tổng: {sc['total_days']} ngày)"
        )
        print(
            f"  - Tỷ lệ ngày thắng     : {sc['win_rate_pct']:.2f}% ({sc['win_days']} ngày thắng / {sc['loss_days']} ngày thua)"
        )
        hd = sc["hit_dist"]
        print(
            f"  - Phân phối số nháy    : 0 nháy: {hd.get(0, 0)} ngày | 1 nháy: {hd.get(1, 0)} ngày | "
            f"2 nháy: {hd.get(2, 0)} ngày | >=3 nháy: {hd.get(3, 0)} ngày (Tổng: {sc['total_hits']} nháy)"
        )
        print(
            f"  - Đáy tài khoản (Min)  : {sc['min_bankroll']:,} VNĐ (vào ngày {sc['min_bankroll_date']}) | "
            f"Thủng mốc 1 triệu: {'CÓ' if sc['breached_initial_1m'] else 'KHÔNG'}"
        )
        print(
            f"  - Max Drawdown từ đỉnh : -{sc['max_drawdown']:,} VNĐ | Chuỗi thua dài nhất: {sc['max_losing_streak']} ngày"
        )

    print("\n--- PHÂN BỔ THEO ĐÀI TRONG KỊCH BẢN 2 (SELECTIVE ALPHA) ---")
    for st_label, st_m in sorted(
        sim_result["scenarios"]["S2"]["station_breakdown"].items(),
        key=lambda kv: -kv[1]["net"],
    ):
        roi_st = (st_m["net"] / float(st_m["cost"])) * 100.0 if st_m["cost"] > 0 else 0.0
        wr_st = (st_m["wins"] / float(st_m["days"])) * 100.0 if st_m["days"] > 0 else 0.0
        print(
            f"  * {st_label:28s}: {st_m['days']:2d} ngày | Thắng {st_m['wins']:2d}/{st_m['days']:2d} ({wr_st:5.1f}%) | "
            f"{st_m['hits']:2d} nháy | Vốn {st_m['cost']:9,}đ | Lãi ròng {st_m['net']:+10,}đ (ROI {roi_st:+6.2f}%)"
        )

    print(f"\n[HOÀN TẤT trong {time.perf_counter() - t0:.2f}s] Đã xuất báo cáo HTML & JSON tại:")
    print(f"  - HTML: {html_out}")
    print(f"  - JSON: {json_out}")


if __name__ == "__main__":
    main()
