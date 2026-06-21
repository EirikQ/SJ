"""
experiment.py — MWM 商业因果实验系统模块
====================================================================
挂到现有 China Auto AI Marketing System，不改动原发帖逻辑。

在现有 main.py 顶部加：
    from experiment import router as experiment_router, init_db as init_experiment_db
在 app 创建后加：
    app.include_router(experiment_router)
    init_experiment_db()

依赖（requirements.txt 追加）：
    psycopg2-binary
    requests   # 现有项目应已有
环境变量（Railway 已自带 DATABASE_URL；FB token 复用现有）：
    DATABASE_URL, FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN
====================================================================
"""
import os
import json
from datetime import datetime, timedelta

import requests
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/experiment", tags=["experiment"])

DATABASE_URL = os.getenv("DATABASE_URL")
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FB_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")
FB_API = "https://graph.facebook.com/v19.0"


# ---------------------------------------------------------------------
# DB 工具
# ---------------------------------------------------------------------
def get_conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL 未配置")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """启动时确保 3 张表存在。SQL 与 schema.sql 一致。"""
    ddl = """
    CREATE TABLE IF NOT EXISTS content_log (
        id BIGSERIAL PRIMARY KEY, platform TEXT NOT NULL DEFAULT 'facebook',
        content_type TEXT NOT NULL, country TEXT, car_model TEXT,
        fb_post_id TEXT, ad_spend NUMERIC(12,2) DEFAULT 0,
        posted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_content_type ON content_log(content_type);
    CREATE INDEX IF NOT EXISTS idx_content_fbpost ON content_log(fb_post_id);

    CREATE TABLE IF NOT EXISTS funnel_log (
        id BIGSERIAL PRIMARY KEY,
        content_id BIGINT NOT NULL REFERENCES content_log(id) ON DELETE CASCADE,
        impressions INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0,
        ctr NUMERIC(6,4) DEFAULT 0, messages INTEGER DEFAULT 0,
        inquiries INTEGER DEFAULT 0, deals INTEGER DEFAULT 0,
        revenue NUMERIC(14,2) DEFAULT 0,
        synced_at TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_funnel_content ON funnel_log(content_id);

    CREATE TABLE IF NOT EXISTS experiment_log (
        id BIGSERIAL PRIMARY KEY, hypothesis TEXT NOT NULL, variable TEXT NOT NULL,
        test_group TEXT NOT NULL, control_group TEXT NOT NULL,
        metric TEXT NOT NULL DEFAULT 'inquiry_rate', result_metrics JSONB,
        conclusion TEXT DEFAULT 'pending', confidence_score NUMERIC(4,3) DEFAULT 0,
        status TEXT DEFAULT 'running',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_exp_status ON experiment_log(status);
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)
        conn.commit()


# =====================================================================
# Agent 1: Data Recorder —— 只记录事实，不分析
# =====================================================================
class RecordContentIn(BaseModel):
    content_type: str          # 案例 / 参数 / 价格 / 信任 / 情绪
    country: str | None = None
    car_model: str | None = None
    fb_post_id: str | None = None
    ad_spend: float = 0
    platform: str = "facebook"


@router.post("/record/content")
def record_content(body: RecordContentIn):
    """Agent1: 发帖后登记一条内容记录。只写事实。
    建议在现有发帖成功的地方调用本接口，把 Facebook 返回的 post_id 传进来。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO content_log
               (platform, content_type, country, car_model, fb_post_id, ad_spend)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (body.platform, body.content_type, body.country,
             body.car_model, body.fb_post_id, body.ad_spend))
        cid = cur.fetchone()[0]
        conn.commit()
    return {"content_id": cid, "recorded": True}


def _fetch_fb_insight(post_id: str) -> dict:
    """从 Facebook 洞察拉曝光/点击。只取事实，不解释。"""
    try:
        url = f"{FB_API}/{post_id}/insights"
        params = {
            "metric": "post_impressions,post_clicks",
            "access_token": FB_TOKEN,
        }
        r = requests.get(url, params=params, timeout=20)
        data = r.json().get("data", [])
        out = {"impressions": 0, "clicks": 0}
        for m in data:
            name = m.get("name")
            val = (m.get("values") or [{}])[0].get("value", 0)
            if name == "post_impressions":
                out["impressions"] = val
            elif name == "post_clicks":
                out["clicks"] = val
        return out
    except Exception as e:
        return {"impressions": 0, "clicks": 0, "error": str(e)}


class SyncFunnelIn(BaseModel):
    content_id: int
    messages: int = 0
    inquiries: int = 0
    deals: int = 0          # 成交手动录入
    revenue: float = 0      # 成交金额手动录入


@router.post("/record/funnel")
def sync_funnel(body: SyncFunnelIn):
    """Agent1: 同步某条内容的漏斗数据。
    曝光/点击自动从 Facebook 洞察拉；私信/询盘/成交按传入值（成交需手动）。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT fb_post_id FROM content_log WHERE id=%s", (body.content_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "content_id 不存在")
        post_id = row[0]
        ins = _fetch_fb_insight(post_id) if post_id else {"impressions": 0, "clicks": 0}
        imp = ins.get("impressions", 0) or 0
        clk = ins.get("clicks", 0) or 0
        ctr = round(clk / imp, 4) if imp else 0
        cur.execute(
            """INSERT INTO funnel_log
               (content_id, impressions, clicks, ctr, messages, inquiries, deals, revenue)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (body.content_id, imp, clk, ctr, body.messages,
             body.inquiries, body.deals, body.revenue))
        fid = cur.fetchone()[0]
        conn.commit()
    return {"funnel_id": fid, "impressions": imp, "clicks": clk, "ctr": ctr,
            "fb_error": ins.get("error")}


# =====================================================================
# Agent 2: Causal Analyst —— 发现变化、提假设，禁止下最终结论
# =====================================================================
@router.get("/analyst/observe")
def observe():
    """Agent2: 对比近 7 天 vs 近 30 天，找出变化最大的 content_type。
    只输出观察事实，不下结论。"""
    sql = """
    WITH agg AS (
      SELECT c.content_type,
             CASE WHEN c.posted_at >= now() - interval '7 days' THEN '7d' ELSE '30d' END AS win,
             AVG(CASE WHEN f.impressions>0 THEN f.inquiries::numeric/f.impressions ELSE 0 END) AS inq_rate,
             AVG(f.ctr) AS ctr, COUNT(*) AS n
      FROM content_log c JOIN funnel_log f ON f.content_id=c.id
      WHERE c.posted_at >= now() - interval '30 days'
      GROUP BY c.content_type, win)
    SELECT content_type, win, inq_rate, ctr, n FROM agg ORDER BY content_type, win;
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    # 计算每个 content_type 的 7d vs 30d 变化（纯事实）
    by_type: dict = {}
    for r in rows:
        t = r["content_type"]
        by_type.setdefault(t, {})[r["win"]] = {
            "inquiry_rate": float(r["inq_rate"] or 0),
            "ctr": float(r["ctr"] or 0), "samples": r["n"]}
    observations = []
    for t, w in by_type.items():
        r7 = w.get("7d", {}).get("inquiry_rate", 0)
        r30 = w.get("30d", {}).get("inquiry_rate", 0)
        change = round(r7 - r30, 4)
        observations.append({"content_type": t, "inquiry_rate_7d": r7,
                             "inquiry_rate_30d": r30, "change": change})
    observations.sort(key=lambda x: abs(x["change"]), reverse=True)
    return {"observations": observations,
            "note": "仅为观察事实，未下结论。变化最大者列首。"}


class RunExperimentIn(BaseModel):
    hypothesis: str
    variable: str = "content_type"
    test_group: str          # 如 "案例"
    control_group: str       # 如 "参数"
    metric: str = "inquiry_rate"   # inquiry_rate / ctr / deal_rate
    days: int = 30


def _group_stats(cur, variable, value, metric, days):
    """取某组的聚合指标。当前仅支持 variable=content_type。"""
    cur.execute(f"""
        SELECT COALESCE(SUM(f.impressions),0) imp, COALESCE(SUM(f.clicks),0) clk,
               COALESCE(SUM(f.inquiries),0) inq, COALESCE(SUM(f.deals),0) deals,
               COUNT(DISTINCT c.id) n
        FROM content_log c JOIN funnel_log f ON f.content_id=c.id
        WHERE c.{variable}=%s AND c.posted_at >= now() - interval '{days} days'
    """, (value,))
    r = cur.fetchone()
    imp, clk, inq, deals, n = r
    imp = imp or 0
    if metric == "ctr":
        rate = clk / imp if imp else 0
    elif metric == "deal_rate":
        rate = deals / imp if imp else 0
    else:  # inquiry_rate
        rate = inq / imp if imp else 0
    return {"rate": round(rate, 4), "impressions": imp, "inquiries": inq,
            "clicks": clk, "deals": deals, "samples": n}


@router.post("/run")
def run_experiment(body: RunExperimentIn):
    """假设验证引擎核心：对比实验组 vs 对照组，算 lift + 简易置信度。
    Agent2 提供观察与证据，结论由统计规则给出（仍标注为初步）。"""
    if body.variable != "content_type":
        raise HTTPException(400, "MVP 仅支持 variable=content_type")
    with get_conn() as conn, conn.cursor() as cur:
        test = _group_stats(cur, body.variable, body.test_group, body.metric, body.days)
        ctrl = _group_stats(cur, body.variable, body.control_group, body.metric, body.days)

        lift = round(test["rate"] - ctrl["rate"], 4)
        rel_lift = round((test["rate"] / ctrl["rate"] - 1), 4) if ctrl["rate"] else None

        # 简易置信度：样本越多、相对提升越大 → 置信越高（MVP 启发式，非严格统计检验）
        min_n = min(test["samples"], ctrl["samples"])
        sample_factor = min(min_n / 10.0, 1.0)            # 每组 >=10 帖给满
        effect_factor = min(abs(rel_lift or 0), 1.0)
        confidence = round(sample_factor * (0.4 + 0.6 * effect_factor), 3)

        # 支持/反对证据（Agent2 风格，不武断）
        support, against = [], []
        if lift > 0:
            support.append(f"实验组 {body.metric}={test['rate']} 高于对照组 {ctrl['rate']}")
        else:
            against.append(f"实验组 {body.metric}={test['rate']} 未高于对照组 {ctrl['rate']}")
        if min_n < 5:
            against.append(f"样本偏少（实验组{test['samples']}/对照组{ctrl['samples']}帖），结论不稳")
        if test["impressions"] < 100 or ctrl["impressions"] < 100:
            against.append("曝光量低，指标波动大")

        # 结论判定（仍为初步，可被后续数据推翻）
        if min_n < 3 or confidence < 0.3:
            conclusion = "不显著"
        elif lift > 0 and confidence >= 0.5:
            conclusion = "成立"
        elif lift <= 0 and confidence >= 0.5:
            conclusion = "推翻"
        else:
            conclusion = "不显著"

        result = {
            "test": test, "control": ctrl,
            "lift_abs": lift, "lift_rel": rel_lift,
            "support_evidence": support, "against_evidence": against,
        }
        cur.execute(
            """INSERT INTO experiment_log
               (hypothesis, variable, test_group, control_group, metric,
                result_metrics, conclusion, confidence_score, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'done') RETURNING id""",
            (body.hypothesis, body.variable, body.test_group, body.control_group,
             body.metric, json.dumps(result), conclusion, confidence))
        eid = cur.fetchone()[0]
        conn.commit()

    return {"experiment_id": eid, "hypothesis": body.hypothesis,
            "conclusion": conclusion, "confidence_score": confidence,
            "result_metrics": result,
            "note": "结论为初步判定，会随新数据被强化或推翻。"}


@router.get("/list")
def list_experiments():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM experiment_log ORDER BY created_at DESC LIMIT 100")
        return {"experiments": cur.fetchall()}


# =====================================================================
# Dashboard 聚合 —— 世界实验仪表盘
# =====================================================================
@router.get("/dashboard")
def dashboard():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
              COUNT(*) FILTER (WHERE status='running')            AS active_hypotheses,
              COUNT(*) FILTER (WHERE conclusion='成立')            AS confirmed_patterns,
              COUNT(*) FILTER (WHERE conclusion='推翻')            AS overturned_patterns,
              COUNT(*) FILTER (WHERE status='running')            AS running_experiments,
              COALESCE(AVG(confidence_score),0)                    AS avg_confidence,
              MAX(updated_at)                                      AS last_update
            FROM experiment_log
        """)
        s = cur.fetchone()
    return {
        "active_hypotheses": s["active_hypotheses"] or 0,
        "confirmed_patterns": s["confirmed_patterns"] or 0,
        "overturned_patterns": s["overturned_patterns"] or 0,
        "running_experiments": s["running_experiments"] or 0,
        "avg_confidence": round(float(s["avg_confidence"] or 0), 3),
        "last_update": s["last_update"],
    }
