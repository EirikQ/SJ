"""
scheduler.py — MWM 实验系统定时调度
====================================================================
两个定时任务，挂到现有系统：
  1. 刷新漏斗 (refresh_all_funnels)：每天定时把所有近 30 天发的帖
     从 Facebook 洞察重新拉一遍曝光/点击，更新 funnel_log。
  2. 自动跑实验 (auto_run_experiments)：对预设的几组假设
     （案例 vs 参数 等）自动跑一遍 /run 的逻辑，结果写入 experiment_log。

复用 experiment.py 里已有的函数，不重复写业务逻辑。

挂载方式见文件末尾「如何启动」，以及 接入指南 第六节。
依赖：apscheduler（requirements.txt 追加 apscheduler）
====================================================================
"""
import os
import json
from datetime import datetime

import psycopg2
import psycopg2.extras

# 复用 experiment.py 里的连接、洞察抓取、分组统计
from experiment import get_conn, _fetch_fb_insight, _group_stats

# ---------------------------------------------------------------------
# 预设要自动验证的假设清单。
# 想加新假设，往这个列表里加一条即可，无需改其它代码。
# variable 目前仅支持 content_type（与 experiment.py 一致）。
# ---------------------------------------------------------------------
PRESET_HYPOTHESES = [
    {
        "hypothesis": "案例内容比参数内容更容易获得询盘",
        "variable": "content_type",
        "test_group": "案例",
        "control_group": "参数",
        "metric": "inquiry_rate",
    },
    {
        "hypothesis": "情绪内容比参数内容点击率更高",
        "variable": "content_type",
        "test_group": "情绪",
        "control_group": "参数",
        "metric": "ctr",
    },
    {
        "hypothesis": "价格内容比信任内容更容易成交",
        "variable": "content_type",
        "test_group": "价格",
        "control_group": "信任",
        "metric": "deal_rate",
    },
]

WINDOW_DAYS = 30  # 实验取数窗口


# =====================================================================
# 任务 1：刷新所有近 30 天帖子的漏斗（曝光/点击来自 FB 洞察）
# =====================================================================
def refresh_all_funnels():
    """重新拉每条内容的 FB 洞察，写一条新的 funnel_log（保留历史，取最新）。
    私信/询盘/成交沿用该帖最近一条 funnel_log 的值（这些靠人工录入，不覆盖为 0）。"""
    started = datetime.utcnow().isoformat()
    updated, skipped, errors = 0, 0, 0
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, fb_post_id FROM content_log
            WHERE posted_at >= now() - interval '%s days'
              AND fb_post_id IS NOT NULL
        """ % WINDOW_DAYS)
        contents = cur.fetchall()

        for c in contents:
            try:
                ins = _fetch_fb_insight(c["fb_post_id"])
                if ins.get("error"):
                    errors += 1
                imp = ins.get("impressions", 0) or 0
                clk = ins.get("clicks", 0) or 0
                ctr = round(clk / imp, 4) if imp else 0

                # 取该帖最近一条人工录入值（私信/询盘/成交），避免被刷新清零
                cur.execute("""
                    SELECT messages, inquiries, deals, revenue
                    FROM funnel_log WHERE content_id=%s
                    ORDER BY synced_at DESC LIMIT 1
                """, (c["id"],))
                prev = cur.fetchone() or {}
                cur.execute("""
                    INSERT INTO funnel_log
                      (content_id, impressions, clicks, ctr, messages, inquiries, deals, revenue)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (c["id"], imp, clk, ctr,
                      prev.get("messages", 0) or 0,
                      prev.get("inquiries", 0) or 0,
                      prev.get("deals", 0) or 0,
                      prev.get("revenue", 0) or 0))
                updated += 1
            except Exception as e:
                errors += 1
                print(f"[refresh_funnels] content {c['id']} 失败: {e}")
        conn.commit()

    print(f"[refresh_funnels] {started} 完成: 更新 {updated} / 跳过 {skipped} / 错误 {errors}")
    return {"updated": updated, "errors": errors}


# =====================================================================
# 任务 2：自动跑预设假设（复用 /run 的统计逻辑）
# =====================================================================
def _evaluate(test, ctrl, metric):
    """与 experiment.py /run 内一致的判定逻辑，抽出来供调度复用。"""
    lift = round(test["rate"] - ctrl["rate"], 4)
    rel_lift = round((test["rate"] / ctrl["rate"] - 1), 4) if ctrl["rate"] else None
    min_n = min(test["samples"], ctrl["samples"])
    sample_factor = min(min_n / 10.0, 1.0)
    effect_factor = min(abs(rel_lift or 0), 1.0)
    confidence = round(sample_factor * (0.4 + 0.6 * effect_factor), 3)

    support, against = [], []
    if lift > 0:
        support.append(f"实验组 {metric}={test['rate']} 高于对照组 {ctrl['rate']}")
    else:
        against.append(f"实验组 {metric}={test['rate']} 未高于对照组 {ctrl['rate']}")
    if min_n < 5:
        against.append(f"样本偏少（{test['samples']}/{ctrl['samples']}帖）")
    if test["impressions"] < 100 or ctrl["impressions"] < 100:
        against.append("曝光量低，指标波动大")

    if min_n < 3 or confidence < 0.3:
        conclusion = "不显著"
    elif lift > 0 and confidence >= 0.5:
        conclusion = "成立"
    elif lift <= 0 and confidence >= 0.5:
        conclusion = "推翻"
    else:
        conclusion = "不显著"

    return {
        "result": {"test": test, "control": ctrl, "lift_abs": lift, "lift_rel": rel_lift,
                   "support_evidence": support, "against_evidence": against},
        "conclusion": conclusion, "confidence": confidence,
    }


def auto_run_experiments():
    """对 PRESET_HYPOTHESES 逐条跑实验，结果写 experiment_log。
    每次跑都新增一行（保留历史），可在仪表盘看同一假设随时间的演化。"""
    started = datetime.utcnow().isoformat()
    ran = 0
    with get_conn() as conn, conn.cursor() as cur:
        for h in PRESET_HYPOTHESES:
            try:
                test = _group_stats(cur, h["variable"], h["test_group"], h["metric"], WINDOW_DAYS)
                ctrl = _group_stats(cur, h["variable"], h["control_group"], h["metric"], WINDOW_DAYS)
                ev = _evaluate(test, ctrl, h["metric"])
                cur.execute("""
                    INSERT INTO experiment_log
                      (hypothesis, variable, test_group, control_group, metric,
                       result_metrics, conclusion, confidence_score, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'done')
                """, (h["hypothesis"], h["variable"], h["test_group"], h["control_group"],
                      h["metric"], json.dumps(ev["result"]), ev["conclusion"], ev["confidence"]))
                ran += 1
            except Exception as e:
                print(f"[auto_run] 假设 '{h['hypothesis']}' 失败: {e}")
        conn.commit()
    print(f"[auto_run] {started} 完成: 跑了 {ran} 个假设")
    return {"ran": ran}


# =====================================================================
# 闭环串联：先刷新漏斗 → 再跑实验
# =====================================================================
def run_full_cycle():
    """一个完整闭环节拍：刷新现实数据 → 验证假设。"""
    r1 = refresh_all_funnels()
    r2 = auto_run_experiments()
    return {"refresh": r1, "experiments": r2}


# =====================================================================
# 启动调度器
# =====================================================================
_scheduler = None


def start_scheduler():
    """用 APScheduler 后台调度。在 FastAPI startup 时调用一次。
    默认：每天 02:00 (UTC) 刷新漏斗，02:30 跑实验。可按需改 cron。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = BackgroundScheduler(timezone="UTC")
    # 每天刷新漏斗
    _scheduler.add_job(refresh_all_funnels, CronTrigger(hour=2, minute=0),
                       id="refresh_funnels", replace_existing=True)
    # 每天跑实验（晚于刷新，确保用的是最新数据）
    _scheduler.add_job(auto_run_experiments, CronTrigger(hour=2, minute=30),
                       id="auto_run", replace_existing=True)
    _scheduler.start()
    print("[scheduler] 已启动：02:00 刷新漏斗，02:30 自动跑实验 (UTC)")
    return _scheduler


# ---------------------------------------------------------------------
# 如何启动（二选一）：
#
# 【方式 A：APScheduler，推荐，进程内调度】
#   requirements.txt 追加：apscheduler
#   main.py 的 startup 事件里加：
#       from scheduler import start_scheduler
#       start_scheduler()
#   ——部署到 Railway 后会一直在后台按点跑。
#
# 【方式 B：手动/外部 Cron 触发】
#   如果不想用 APScheduler，可加一个受保护的接口手动触发，
#   再用 Railway Cron / cron-job.org 定时去 POST 它（见下方接口）。
# ---------------------------------------------------------------------

# 可选：给方式 B 用的手动触发接口。把下面整段加进 experiment.py 即可，
# 或在 main.py 里 import run_full_cycle 自行包一个接口。
#
# from fastapi import Header, HTTPException
# @router.post("/cron/run-cycle")
# def cron_run_cycle(x_cron_key: str = Header(None)):
#     if x_cron_key != os.getenv("CRON_KEY"):   # 设一个密钥防滥用
#         raise HTTPException(403, "forbidden")
#     from scheduler import run_full_cycle
#     return run_full_cycle()
