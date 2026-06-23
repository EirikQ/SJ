"""
experiment.py — Business World Model Engine
====================================================================
系统定位：Reality-to-Knowledge Engine（现实世界商业规律提取器）
目标变量：Profit（利润）
终极输出：Pattern → Prediction → Better Decisions

完整归因链路（hypothesis_id 贯穿全链）：
  Content → Lead → Quote → Deal → Profit → Pattern → Prediction

六层架构：
  Layer 1: Profit Attribution   利润归因
  Layer 2: Hypothesis Engine    假设绑定
  Layer 3: Knowledge Extraction 规律提取
  Layer 4: Counter Example      反例系统
  Layer 5: Dashboard            利润排行榜
  Layer 6: Prediction           预测系统

表结构（共11张）：
  content_log      发帖记录（绑定假设）
  funnel_log       Facebook指标
  hypothesis_log   假设库
  lead_log         询盘/线索
  quotation_log    报价
  deal_log         成交
  profit_log       利润归因（完整链路）
  pattern_library  规律库
  counter_example  反例库
  experiment_log   实验记录
  prediction_log   预测记录
====================================================================
"""
import os
import json
from datetime import datetime, timedelta, date

import requests
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/experiment", tags=["experiment"])

DATABASE_URL = os.getenv("DATABASE_URL")
FB_TOKEN     = os.getenv("FACEBOOK_PAGE_TOKEN")
FB_API       = "https://graph.facebook.com/v19.0"
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")


# ─────────────────────────────────────────────────────────────────────
# DB 工具
# ─────────────────────────────────────────────────────────────────────
def get_conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL 未配置")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """启动时建表（幂等）。新增表不影响旧表。"""
    ddl = """
    -- ── Layer 0: 内容记录 ────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS content_log (
        id              BIGSERIAL PRIMARY KEY,
        platform        TEXT NOT NULL DEFAULT 'facebook',
        content_type    TEXT NOT NULL,
        country         TEXT,
        car_model       TEXT,
        fb_post_id      TEXT,
        ad_spend        NUMERIC(12,2) DEFAULT 0,
        hypothesis_id   BIGINT,              -- 绑定假设（Layer 2）
        posted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_content_type       ON content_log(content_type);
    CREATE INDEX IF NOT EXISTS idx_content_fbpost     ON content_log(fb_post_id);
    CREATE INDEX IF NOT EXISTS idx_content_posted     ON content_log(posted_at);
    CREATE INDEX IF NOT EXISTS idx_content_hypothesis ON content_log(hypothesis_id);
    -- 为旧表加字段（已存在则跳过）
    ALTER TABLE content_log ADD COLUMN IF NOT EXISTS hypothesis_id BIGINT;

    -- ── Layer 0: Facebook 漏斗指标 ──────────────────────────────
    CREATE TABLE IF NOT EXISTS funnel_log (
        id          BIGSERIAL PRIMARY KEY,
        content_id  BIGINT NOT NULL REFERENCES content_log(id) ON DELETE CASCADE,
        impressions INTEGER DEFAULT 0,
        clicks      INTEGER DEFAULT 0,
        ctr         NUMERIC(6,4) DEFAULT 0,
        messages    INTEGER DEFAULT 0,
        synced_at   TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_funnel_content ON funnel_log(content_id);

    -- ── Layer 2: 假设库 ──────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS hypothesis_log (
        id              BIGSERIAL PRIMARY KEY,
        code            TEXT UNIQUE,         -- H001, H002...
        statement       TEXT NOT NULL,       -- 假设描述
        variable        TEXT,                -- 被测变量
        test_group      TEXT,
        control_group   TEXT,
        status          TEXT DEFAULT 'active',  -- active/confirmed/rejected/paused
        confidence      NUMERIC(4,3) DEFAULT 0,
        support_count   INT DEFAULT 0,
        counter_count   INT DEFAULT 0,
        total_profit    NUMERIC(14,2) DEFAULT 0,
        total_leads     INT DEFAULT 0,
        total_deals     INT DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypothesis_log(status);
    CREATE INDEX IF NOT EXISTS idx_hyp_code   ON hypothesis_log(code);

    -- ── Layer 0: 询盘/线索 ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS lead_log (
        id              BIGSERIAL PRIMARY KEY,
        content_id      BIGINT REFERENCES content_log(id),
        hypothesis_id   BIGINT REFERENCES hypothesis_log(id),
        country         TEXT,
        source_platform TEXT DEFAULT 'whatsapp',
        whatsapp        TEXT,
        car_model       TEXT,
        lead_quality    TEXT DEFAULT 'medium',
        quality_reason  TEXT,
        status          TEXT DEFAULT 'new',
        notes           TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_lead_content    ON lead_log(content_id);
    CREATE INDEX IF NOT EXISTS idx_lead_status     ON lead_log(status);
    CREATE INDEX IF NOT EXISTS idx_lead_quality    ON lead_log(lead_quality);
    CREATE INDEX IF NOT EXISTS idx_lead_hypothesis ON lead_log(hypothesis_id);
    ALTER TABLE lead_log ADD COLUMN IF NOT EXISTS hypothesis_id BIGINT REFERENCES hypothesis_log(id);

    -- ── Layer 0: 报价 ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS quotation_log (
        id                BIGSERIAL PRIMARY KEY,
        lead_id           BIGINT NOT NULL REFERENCES lead_log(id),
        hypothesis_id     BIGINT REFERENCES hypothesis_log(id),
        car_model         TEXT,
        quoted_price      NUMERIC(14,2),
        quotation_status  TEXT DEFAULT 'sent',
        notes             TEXT,
        quotation_time    TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_quot_lead      ON quotation_log(lead_id);
    CREATE INDEX IF NOT EXISTS idx_quot_status    ON quotation_log(quotation_status);
    ALTER TABLE quotation_log ADD COLUMN IF NOT EXISTS hypothesis_id BIGINT REFERENCES hypothesis_log(id);

    -- ── Layer 0: 成交 ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS deal_log (
        id              BIGSERIAL PRIMARY KEY,
        lead_id         BIGINT NOT NULL REFERENCES lead_log(id),
        quotation_id    BIGINT REFERENCES quotation_log(id),
        hypothesis_id   BIGINT REFERENCES hypothesis_log(id),
        car_model       TEXT,
        deal_amount     NUMERIC(14,2) DEFAULT 0,
        cost            NUMERIC(14,2) DEFAULT 0,
        profit          NUMERIC(14,2) DEFAULT 0,
        close_time      TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_deal_lead      ON deal_log(lead_id);
    CREATE INDEX IF NOT EXISTS idx_deal_hypothesis ON deal_log(hypothesis_id);
    ALTER TABLE deal_log ADD COLUMN IF NOT EXISTS hypothesis_id BIGINT REFERENCES hypothesis_log(id);

    -- ── Layer 1: 利润归因（完整链路快照）─────────────────────────
    CREATE TABLE IF NOT EXISTS profit_log (
        id              BIGSERIAL PRIMARY KEY,
        deal_id         BIGINT NOT NULL REFERENCES deal_log(id),
        content_id      BIGINT REFERENCES content_log(id),
        lead_id         BIGINT REFERENCES lead_log(id),
        quotation_id    BIGINT REFERENCES quotation_log(id),
        hypothesis_id   BIGINT REFERENCES hypothesis_log(id),
        country         TEXT,
        car_model       TEXT,
        content_type    TEXT,
        lead_quality    TEXT,
        revenue         NUMERIC(14,2) DEFAULT 0,
        cost            NUMERIC(14,2) DEFAULT 0,
        profit          NUMERIC(14,2) DEFAULT 0,
        profit_margin   NUMERIC(6,4) DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_profit_content    ON profit_log(content_id);
    CREATE INDEX IF NOT EXISTS idx_profit_hypothesis ON profit_log(hypothesis_id);
    CREATE INDEX IF NOT EXISTS idx_profit_country    ON profit_log(country);
    CREATE INDEX IF NOT EXISTS idx_profit_model      ON profit_log(car_model);

    -- ── Layer 3: 规律库 ──────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS pattern_library (
        id               BIGSERIAL PRIMARY KEY,
        pattern_name     TEXT NOT NULL,
        description      TEXT,
        dimension        TEXT,        -- content_type/country/car_model/lead_quality
        dimension_value  TEXT,
        metric           TEXT,        -- profit/inquiry_rate/deal_rate/qualified_rate
        effect_size      NUMERIC(10,4),
        support_count    INT DEFAULT 0,
        counter_count    INT DEFAULT 0,
        confidence       NUMERIC(4,3) DEFAULT 0,
        profit_contribution NUMERIC(14,2) DEFAULT 0,
        status           TEXT DEFAULT 'active',  -- active/weakened/overturned
        last_update      TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_pattern_status ON pattern_library(status);
    CREATE INDEX IF NOT EXISTS idx_pattern_dim    ON pattern_library(dimension);

    -- ── Layer 4: 反例库 ──────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS counter_example (
        id               BIGSERIAL PRIMARY KEY,
        pattern_id       BIGINT REFERENCES pattern_library(id),
        description      TEXT NOT NULL,
        evidence         JSONB,       -- 具体数据证据
        dimension        TEXT,
        dimension_value  TEXT,
        finding          TEXT,        -- 反例发现（如：案例视频询盘多但利润为0）
        severity         NUMERIC(4,3) DEFAULT 0,  -- 对规律的威胁程度 0-1
        action_taken     TEXT DEFAULT 'noted',    -- noted/weakened/overturned
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_counter_pattern ON counter_example(pattern_id);
    CREATE INDEX IF NOT EXISTS idx_counter_severity ON counter_example(severity);

    -- ── Layer 6: 预测记录 ────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS prediction_log (
        id               BIGSERIAL PRIMARY KEY,
        pattern_id       BIGINT REFERENCES pattern_library(id),
        statement        TEXT NOT NULL,
        predicted_value  NUMERIC(10,4),
        confidence       NUMERIC(4,3),
        verify_at        TIMESTAMPTZ,
        status           TEXT DEFAULT 'pending',  -- pending/success/fail
        actual_value     NUMERIC(10,4),
        error_rate       NUMERIC(6,4),
        outcome          TEXT,        -- reinforce/weaken/overturn
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_pred_status ON prediction_log(status);

    -- ── 实验记录 ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS experiment_log (
        id               BIGSERIAL PRIMARY KEY,
        hypothesis       TEXT NOT NULL,
        variable         TEXT NOT NULL,
        test_group       TEXT NOT NULL,
        control_group    TEXT NOT NULL,
        metric           TEXT NOT NULL DEFAULT 'profit_per_content',
        result_metrics   JSONB,
        conclusion       TEXT DEFAULT 'pending',
        confidence_score NUMERIC(4,3) DEFAULT 0,
        status           TEXT DEFAULT 'running',
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS idx_exp_status ON experiment_log(status);
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────
# Facebook 洞察
# ─────────────────────────────────────────────────────────────────────
def _fetch_fb_insight(post_id: str) -> dict:
    try:
        r = requests.get(f"{FB_API}/{post_id}/insights",
            params={"metric":"post_impressions,post_clicks","access_token":FB_TOKEN},
            timeout=20)
        data = r.json().get("data", [])
        out = {"impressions":0, "clicks":0}
        for m in data:
            val = (m.get("values") or [{}])[0].get("value", 0)
            if m.get("name")=="post_impressions": out["impressions"]=val
            elif m.get("name")=="post_clicks":    out["clicks"]=val
        return out
    except Exception as e:
        return {"impressions":0,"clicks":0,"error":str(e)}


# ─────────────────────────────────────────────────────────────────────
# DeepSeek 工具
# ─────────────────────────────────────────────────────────────────────
def _deepseek(prompt: str, max_tokens: int = 200, temperature: float = 0.1) -> str:
    if not DEEPSEEK_KEY:
        return ""
    try:
        r = requests.post("https://api.deepseek.com/chat/completions",
            headers={"Authorization":f"Bearer {DEEPSEEK_KEY}","Content-Type":"application/json"},
            json={"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],
                  "temperature":temperature,"max_tokens":max_tokens},
            timeout=30)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return ""


def _score_lead_quality(notes: str, car_model: str, country: str) -> dict:
    if not notes:
        return {"quality":"medium","reason":"无询盘内容，默认中等"}
    text = _deepseek(f"""评估以下汽车出口询盘质量。
询盘内容：{notes}
车型：{car_model or '未知'}，国家：{country or '未知'}

high=明确车型+预算+采购计划；medium=有兴趣无细节；low=随便问问

只输出JSON：{{"quality":"high/medium/low","reason":"一句话"}}""")
    try:
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return {"quality":"medium","reason":"评分失败"}


# ─────────────────────────────────────────────────────────────────────
# Layer 2: 假设库 CRUD
# ─────────────────────────────────────────────────────────────────────
class HypothesisIn(BaseModel):
    code: str           # H001
    statement: str
    variable: str = "content_type"
    test_group: str | None = None
    control_group: str | None = None


@router.post("/hypotheses")
def create_hypothesis(body: HypothesisIn):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO hypothesis_log (code, statement, variable, test_group, control_group)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (code) DO UPDATE
              SET statement=EXCLUDED.statement, updated_at=now()
            RETURNING id
        """, (body.code, body.statement, body.variable, body.test_group, body.control_group))
        hid = cur.fetchone()[0]
        conn.commit()
    return {"hypothesis_id": hid, "code": body.code}


@router.get("/hypotheses")
def list_hypotheses():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM hypothesis_log ORDER BY code")
        return {"hypotheses": cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────
# Layer 0: 内容登记
# ─────────────────────────────────────────────────────────────────────
class RecordContentIn(BaseModel):
    content_type: str
    country: str | None = None
    car_model: str | None = None
    fb_post_id: str | None = None
    ad_spend: float = 0
    platform: str = "facebook"
    hypothesis_id: int | None = None


@router.post("/record/content")
def record_content(body: RecordContentIn):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO content_log
              (platform,content_type,country,car_model,fb_post_id,ad_spend,hypothesis_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (body.platform,body.content_type,body.country,body.car_model,
              body.fb_post_id,body.ad_spend,body.hypothesis_id))
        cid = cur.fetchone()[0]
        conn.commit()
    return {"content_id":cid,"recorded":True}


# ─────────────────────────────────────────────────────────────────────
# Layer 0: Lead 录入
# ─────────────────────────────────────────────────────────────────────
class LeadIn(BaseModel):
    content_id: int | None = None
    hypothesis_id: int | None = None
    country: str | None = None
    source_platform: str = "whatsapp"
    whatsapp: str | None = None
    car_model: str | None = None
    notes: str | None = None
    lead_quality: str | None = None


@router.post("/leads")
def create_lead(body: LeadIn):
    # 自动继承 content 的 hypothesis_id
    hyp_id = body.hypothesis_id
    if not hyp_id and body.content_id:
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT hypothesis_id FROM content_log WHERE id=%s", (body.content_id,))
                row = cur.fetchone()
                if row: hyp_id = row[0]
        except: pass

    scored = _score_lead_quality(body.notes or "", body.car_model or "", body.country or "")
    quality = body.lead_quality or scored["quality"]
    reason  = scored["reason"]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lead_log
              (content_id,hypothesis_id,country,source_platform,
               whatsapp,car_model,lead_quality,quality_reason,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (body.content_id,hyp_id,body.country,body.source_platform,
              body.whatsapp,body.car_model,quality,reason,body.notes))
        lid = cur.fetchone()[0]
        # 更新假设的 lead 计数
        if hyp_id:
            cur.execute("UPDATE hypothesis_log SET total_leads=total_leads+1, updated_at=now() WHERE id=%s", (hyp_id,))
        conn.commit()
    return {"lead_id":lid,"lead_quality":quality,"quality_reason":reason}


@router.get("/leads")
def list_leads(status: str | None = None, days: int = 30):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """
            SELECT l.*,
                   c.content_type, c.posted_at, c.fb_post_id,
                   h.code AS hypothesis_code, h.statement AS hypothesis_statement,
                   q.id AS quotation_id, q.quoted_price, q.quotation_status,
                   d.id AS deal_id, d.deal_amount,
                   p.profit
            FROM lead_log l
            LEFT JOIN content_log c     ON c.id = l.content_id
            LEFT JOIN hypothesis_log h  ON h.id = l.hypothesis_id
            LEFT JOIN quotation_log q   ON q.lead_id = l.id
            LEFT JOIN deal_log d        ON d.lead_id = l.id
            LEFT JOIN profit_log p      ON p.lead_id = l.id
            WHERE l.created_at >= now() - interval '%s days'
        """ % days
        params = []
        if status:
            sql += " AND l.status=%s"
            params.append(status)
        sql += " ORDER BY l.created_at DESC"
        cur.execute(sql, params)
        return {"leads": cur.fetchall()}


class UpdateLeadStatus(BaseModel):
    status: str


@router.patch("/leads/{lead_id}/status")
def update_lead_status(lead_id: int, body: UpdateLeadStatus):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE lead_log SET status=%s,updated_at=now() WHERE id=%s",
                    (body.status, lead_id))
        conn.commit()
    return {"updated": True}


# ─────────────────────────────────────────────────────────────────────
# Layer 0: 报价录入
# ─────────────────────────────────────────────────────────────────────
class QuotationIn(BaseModel):
    lead_id: int
    car_model: str | None = None
    quoted_price: float
    notes: str | None = None


@router.post("/quotations")
def create_quotation(body: QuotationIn):
    with get_conn() as conn, conn.cursor() as cur:
        # 继承 hypothesis_id
        cur.execute("SELECT hypothesis_id FROM lead_log WHERE id=%s", (body.lead_id,))
        row = cur.fetchone()
        hyp_id = row[0] if row else None
        cur.execute("""
            INSERT INTO quotation_log (lead_id,hypothesis_id,car_model,quoted_price,notes)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (body.lead_id,hyp_id,body.car_model,body.quoted_price,body.notes))
        qid = cur.fetchone()[0]
        cur.execute("UPDATE lead_log SET status='quoted',updated_at=now() WHERE id=%s",(body.lead_id,))
        conn.commit()
    return {"quotation_id": qid}


@router.patch("/quotations/{qid}/status")
def update_quotation_status(qid: int, status: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE quotation_log SET quotation_status=%s,updated_at=now() WHERE id=%s",(status,qid))
        conn.commit()
    return {"updated": True}


# ─────────────────────────────────────────────────────────────────────
# Layer 0+1: 成交录入 → 自动写 profit_log
# ─────────────────────────────────────────────────────────────────────
class DealIn(BaseModel):
    lead_id: int
    quotation_id: int | None = None
    car_model: str | None = None
    deal_amount: float
    cost: float = 0


@router.post("/deals")
def create_deal(body: DealIn):
    profit = round(body.deal_amount - body.cost, 2)
    margin = round(profit / body.deal_amount, 4) if body.deal_amount else 0

    with get_conn() as conn, conn.cursor() as cur:
        # 取归因链路信息
        cur.execute("""
            SELECT l.hypothesis_id, l.content_id, l.country, l.car_model, l.lead_quality
            FROM lead_log l WHERE l.id=%s
        """, (body.lead_id,))
        lead_row = cur.fetchone()
        hyp_id = lead_row[0] if lead_row else None
        cid    = lead_row[1] if lead_row else None
        ctry   = lead_row[2] if lead_row else None
        cmodel = body.car_model or (lead_row[3] if lead_row else None)
        lq     = lead_row[4] if lead_row else None

        # 取 content_type
        ctype = None
        if cid:
            cur.execute("SELECT content_type FROM content_log WHERE id=%s",(cid,))
            r = cur.fetchone()
            if r: ctype = r[0]

        # 写 deal_log
        cur.execute("""
            INSERT INTO deal_log (lead_id,quotation_id,hypothesis_id,car_model,deal_amount,cost,profit)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (body.lead_id,body.quotation_id,hyp_id,cmodel,body.deal_amount,body.cost,profit))
        did = cur.fetchone()[0]

        # 写 profit_log（完整归因快照）
        cur.execute("""
            INSERT INTO profit_log
              (deal_id,content_id,lead_id,quotation_id,hypothesis_id,
               country,car_model,content_type,lead_quality,
               revenue,cost,profit,profit_margin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (did,cid,body.lead_id,body.quotation_id,hyp_id,
              ctry,cmodel,ctype,lq,body.deal_amount,body.cost,profit,margin))

        # 更新 lead 状态
        cur.execute("UPDATE lead_log SET status='won',updated_at=now() WHERE id=%s",(body.lead_id,))
        if body.quotation_id:
            cur.execute("UPDATE quotation_log SET quotation_status='accepted' WHERE id=%s",(body.quotation_id,))

        # 更新假设利润/成交统计
        if hyp_id:
            cur.execute("""UPDATE hypothesis_log
                SET total_profit=total_profit+%s, total_deals=total_deals+1, updated_at=now()
                WHERE id=%s""", (profit, hyp_id))

        conn.commit()

    # 异步触发反例检测（不阻塞响应）
    try:
        _detect_counter_examples(ctype, ctry, cmodel)
    except: pass

    return {"deal_id":did,"profit":profit,"profit_margin":f"{margin:.1%}",
            "attribution":{"content_id":cid,"lead_id":body.lead_id,
                           "hypothesis_id":hyp_id,"content_type":ctype}}


# ─────────────────────────────────────────────────────────────────────
# Layer 3: 规律提取
# ─────────────────────────────────────────────────────────────────────
def _get_pattern_maturity(sample_size: int) -> tuple:
    """Sample Size Guard: 根据样本量返回 (maturity, label, allow_prediction)"""
    if sample_size < 10:
        return ("OBSERVING",      "观察中",     False)
    elif sample_size < 30:
        return ("PRELIMINARY",    "初步规律",   True)
    elif sample_size <= 100:
        return ("VALIDATED",      "可信规律",   True)
    else:
        return ("HIGH_CONFIDENCE","高可信规律", True)


def _extract_patterns():
    """每周自动运行：从归因链路提取规律，写入 pattern_library。
    Sample Size Guard：样本 < 10 只记录为「观察信号」，不输出「发现规律」。"""
    patterns_saved = 0
    signals_saved  = 0
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 按内容类型统计完整归因指标
        cur.execute("""
            SELECT
                p.content_type,
                COUNT(DISTINCT p.id)                AS profit_count,
                COALESCE(SUM(p.profit),0)           AS total_profit,
                COALESCE(AVG(p.profit_margin),0)    AS avg_margin,
                COUNT(DISTINCT l.id)                AS lead_count,
                COUNT(DISTINCT l.id) FILTER (WHERE l.lead_quality='high') AS hq_lead_count,
                COUNT(DISTINCT f.id) FILTER (WHERE f.impressions>0) AS content_count,
                COALESCE(SUM(f.impressions),0)      AS total_impressions
            FROM profit_log p
            LEFT JOIN lead_log l    ON l.id = p.lead_id
            LEFT JOIN content_log c ON c.id = p.content_id
            LEFT JOIN LATERAL (
                SELECT * FROM funnel_log WHERE content_id=c.id ORDER BY synced_at DESC LIMIT 1
            ) f ON TRUE
            WHERE p.created_at >= now() - interval '90 days'
            GROUP BY p.content_type
        """)
        rows = cur.fetchall()

        for r in rows:
            if not r["content_type"]: continue
            sample_n = r["lead_count"] or 0
            maturity, label, allow_pred = _get_pattern_maturity(sample_n)
            profit_per_lead = float(r["total_profit"]) / max(sample_n, 1)
            hq_rate = (r["hq_lead_count"] or 0) / max(sample_n, 1)
            conf = min(sample_n / 10.0, 1.0) * (0.5 + 0.5 * min((r["profit_count"] or 0) / 5.0, 1.0))
            # 样本不足：记为「观察信号」，不输出「规律」
            pname = (f"{r['content_type']}内容利润规律"
                     if maturity != "OBSERVING"
                     else f"{r['content_type']}内容观察信号（样本不足）")
            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name, description, dimension, dimension_value,
                   metric, effect_size, support_count, confidence,
                   profit_contribution, sample_size, pattern_maturity)
                VALUES (%s,%s,'content_type',%s,'profit_per_lead',%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (pname,
                  f"[{label}] {r['content_type']}类内容每条询盘平均利润 ${profit_per_lead:.0f}，"
                  f"高质量询盘率 {hq_rate:.1%}，样本 {sample_n} 条",
                  r["content_type"], round(profit_per_lead, 2),
                  sample_n, round(conf, 3), float(r["total_profit"]),
                  sample_n, maturity))
            if maturity == "OBSERVING": signals_saved += 1
            else: patterns_saved += 1

        # 按国家提取规律
        cur.execute("""
            SELECT country, COUNT(*) AS deals, COALESCE(SUM(profit),0) AS profit,
                   COUNT(DISTINCT lead_id) AS leads
            FROM profit_log WHERE created_at >= now()-interval '90 days'
            AND country IS NOT NULL
            GROUP BY country
        """)
        for r in cur.fetchall():
            sample_n = r["deals"] or 0
            maturity, label, _ = _get_pattern_maturity(sample_n)
            pname = (f"{r['country']}市场利润规律"
                     if maturity != "OBSERVING"
                     else f"{r['country']}市场观察信号（样本不足）")
            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name, dimension, dimension_value, metric,
                   effect_size, support_count, confidence, profit_contribution,
                   sample_size, pattern_maturity)
                VALUES (%s,'country',%s,'profit_per_deal',%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (pname, r["country"],
                  round(float(r["profit"])/max(sample_n,1), 2),
                  sample_n, round(min(sample_n/5.0,1.0)*0.6, 3), float(r["profit"]),
                  sample_n, maturity))
            if maturity == "OBSERVING": signals_saved += 1
            else: patterns_saved += 1

        conn.commit()
    return {"patterns_extracted": patterns_saved,
            "signals_recorded": signals_saved,
            "note": "样本 < 10 的记录为观察信号，不进入预测系统。"}


@router.post("/patterns/extract")
def trigger_pattern_extraction():
    """手动触发规律提取。"""
    return _extract_patterns()


@router.get("/patterns")
def list_patterns():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM pattern_library ORDER BY profit_contribution DESC, confidence DESC")
        return {"patterns": cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────
# Layer 4: 反例检测
# ─────────────────────────────────────────────────────────────────────
def _detect_counter_examples(content_type: str, country: str, car_model: str):
    """每次成交后自动检测：高CTR但无利润、高询盘但无成交等反例。"""
    findings = []
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not content_type:
            return findings

        # 检查：这个内容类型询盘多但利润差
        cur.execute("""
            SELECT
                c.content_type,
                COUNT(DISTINCT l.id) AS leads,
                COALESCE(SUM(p.profit),0) AS profit,
                COUNT(DISTINCT p.id) AS deals
            FROM content_log c
            LEFT JOIN lead_log l  ON l.content_id=c.id
            LEFT JOIN profit_log p ON p.content_id=c.id
            WHERE c.content_type=%s
              AND c.posted_at >= now()-interval '30 days'
            GROUP BY c.content_type
        """, (content_type,))
        r = cur.fetchone()
        if r and r["leads"] >= 5 and r["profit"] == 0:
            desc = f"「{content_type}」内容近30天产生{r['leads']}条询盘，但利润为零"
            cur.execute("""
                INSERT INTO counter_example (description,dimension,dimension_value,
                    finding,severity,evidence)
                VALUES (%s,'content_type',%s,%s,%s,%s::jsonb)
            """, (desc, content_type,
                  "高询盘低利润反例", 0.7,
                  json.dumps({"leads":r["leads"],"profit":0,"deals":r["deals"]})))
            findings.append(desc)

        # 检查：高CTR但低转化
        cur.execute("""
            SELECT AVG(f.ctr) AS avg_ctr, COUNT(DISTINCT l.id) AS leads
            FROM content_log c
            JOIN LATERAL (SELECT * FROM funnel_log WHERE content_id=c.id
                ORDER BY synced_at DESC LIMIT 1) f ON TRUE
            LEFT JOIN lead_log l ON l.content_id=c.id
            WHERE c.content_type=%s AND c.posted_at>=now()-interval '30 days'
        """, (content_type,))
        r2 = cur.fetchone()
        if r2 and r2["avg_ctr"] and float(r2["avg_ctr"]) > 0.05 and (r2["leads"] or 0) == 0:
            desc = f"「{content_type}」CTR高达{float(r2['avg_ctr']):.1%}但询盘为零"
            cur.execute("""
                INSERT INTO counter_example (description,dimension,dimension_value,
                    finding,severity,evidence)
                VALUES (%s,'content_type',%s,%s,%s,%s::jsonb)
            """, (desc, content_type, "高CTR低询盘反例", 0.6,
                  json.dumps({"avg_ctr":float(r2["avg_ctr"]),"leads":0})))
            findings.append(desc)

        conn.commit()
    return findings


@router.get("/counter-examples")
def list_counter_examples():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM counter_example ORDER BY severity DESC, created_at DESC LIMIT 50")
        return {"counter_examples": cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────
# Layer 5: 利润排行榜
# ─────────────────────────────────────────────────────────────────────
@router.get("/leaderboard")
def leaderboard(days: int = 30):
    """利润排行榜：内容类型 / 国家 / 车型。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        def rank(group_by, label):
            cur.execute(f"""
                SELECT {group_by} AS name,
                       COUNT(*) AS deals,
                       COALESCE(SUM(profit),0) AS total_profit,
                       COALESCE(AVG(profit_margin),0) AS avg_margin,
                       COUNT(DISTINCT lead_id) AS leads
                FROM profit_log
                WHERE created_at >= now()-interval '{days} days'
                  AND {group_by} IS NOT NULL
                GROUP BY {group_by} ORDER BY total_profit DESC LIMIT 10
            """)
            return cur.fetchall()

        by_content = rank("content_type", "内容类型")
        by_country = rank("country", "国家")
        by_model   = rank("car_model", "车型")

        # 假设利润排行
        cur.execute("""
            SELECT h.code, h.statement, h.total_profit, h.total_leads,
                   h.total_deals, h.confidence
            FROM hypothesis_log h
            ORDER BY h.total_profit DESC LIMIT 10
        """)
        by_hypothesis = cur.fetchall()

    return {
        "by_content_type": [dict(r) for r in by_content],
        "by_country":      [dict(r) for r in by_country],
        "by_car_model":    [dict(r) for r in by_model],
        "by_hypothesis":   [dict(r) for r in by_hypothesis],
    }


# ─────────────────────────────────────────────────────────────────────
# 归因统计（供实验引擎使用）
# ─────────────────────────────────────────────────────────────────────
def _attribution_stats(cur, content_type: str, days: int) -> dict:
    cur.execute(f"""
        SELECT
          COUNT(DISTINCT c.id)                                           AS content_count,
          COALESCE(SUM(f.impressions),0)                                AS impressions,
          COALESCE(SUM(f.clicks),0)                                     AS clicks,
          COALESCE(AVG(f.ctr),0)                                        AS avg_ctr,
          COUNT(DISTINCT l.id)                                           AS leads,
          COUNT(DISTINCT l.id) FILTER (WHERE l.lead_quality='high')     AS high_quality_leads,
          COUNT(DISTINCT q.id)                                           AS quotations,
          COUNT(DISTINCT d.id)                                           AS deals,
          COALESCE(SUM(p.profit),0)                                      AS total_profit,
          COALESCE(SUM(c.ad_spend),0)                                   AS total_cost
        FROM content_log c
        LEFT JOIN LATERAL (SELECT * FROM funnel_log WHERE content_id=c.id
            ORDER BY synced_at DESC LIMIT 1) f ON TRUE
        LEFT JOIN lead_log l      ON l.content_id=c.id
        LEFT JOIN quotation_log q ON q.lead_id=l.id
        LEFT JOIN deal_log d      ON d.lead_id=l.id
        LEFT JOIN profit_log p    ON p.content_id=c.id
        WHERE c.content_type=%s AND c.posted_at>=now()-interval '{days} days'
    """, (content_type,))
    r = cur.fetchone()
    cc,imp,clk,ctr,leads,hq,quots,deals,profit,cost = r
    imp=imp or 0; leads=leads or 0; hq=hq or 0; deals=deals or 0
    profit=float(profit or 0); cost=float(cost or 0); cc=cc or 0
    return {
        "content_count":      cc,
        "impressions":        imp,
        "clicks":             clk or 0,
        "ctr":                round(float(ctr or 0),4),
        "leads":              leads,
        "high_quality_leads": hq,
        "quotations":         quots or 0,
        "deals":              deals,
        "total_profit":       profit,
        "total_cost":         cost,
        "inquiry_rate":       round(leads/imp,6)     if imp    else 0,
        "qualified_rate":     round(hq/leads,4)      if leads  else 0,
        "quote_rate":         round((quots or 0)/leads,4) if leads else 0,
        "deal_rate":          round(deals/leads,4)   if leads  else 0,
        "profit_per_content": round(profit/cc,2)     if cc     else 0,
        "profit_per_lead":    round(profit/leads,2)  if leads  else 0,
        "content_roi":        round(profit/cost,4)   if cost   else None,
    }


# ─────────────────────────────────────────────────────────────────────
# 实验引擎
# ─────────────────────────────────────────────────────────────────────
class RunExperimentIn(BaseModel):
    hypothesis: str
    variable: str = "content_type"
    test_group: str
    control_group: str
    metric: str = "profit_per_content"
    days: int = 30


@router.post("/run")
def run_experiment(body: RunExperimentIn):
    if body.variable != "content_type":
        raise HTTPException(400, "MVP 仅支持 variable=content_type")
    with get_conn() as conn, conn.cursor() as cur:
        test = _attribution_stats(cur, body.test_group, body.days)
        ctrl = _attribution_stats(cur, body.control_group, body.days)
        t_val = test.get(body.metric,0) or 0
        c_val = ctrl.get(body.metric,0) or 0
        lift  = round(t_val-c_val,4)
        rel   = round((t_val/c_val-1),4) if c_val else None
        min_n = min(test["leads"],ctrl["leads"])
        sf    = min(min_n/5.0,1.0)
        ef    = min(abs(rel or 0),1.0)
        conf  = round(sf*(0.4+0.6*ef),3)
        support, against = [], []
        if test["total_profit"]>ctrl["total_profit"]:
            support.append(f"实验组利润 ${test['total_profit']:.0f} > 对照组 ${ctrl['total_profit']:.0f}")
        else:
            against.append(f"实验组利润 ${test['total_profit']:.0f} ≤ 对照组 ${ctrl['total_profit']:.0f}")
        if test["qualified_rate"]>ctrl["qualified_rate"]:
            support.append(f"高质量询盘率 {test['qualified_rate']:.1%} > 对照组 {ctrl['qualified_rate']:.1%}")
        if min_n<3: against.append(f"询盘样本不足（各{min_n}条），继续积累中")
        if test["deals"]<2 and ctrl["deals"]<2:
            against.append("成交样本极少，利润对比暂不可信")
        if min_n<2 or conf<0.25: conclusion="数据不足"
        elif lift>0 and conf>=0.5: conclusion="成立"
        elif lift<=0 and conf>=0.5: conclusion="推翻"
        else: conclusion="不显著"
        result={"test":test,"control":ctrl,"lift_abs":lift,"lift_rel":rel,
                "support_evidence":support,"against_evidence":against}
        cur.execute("""
            INSERT INTO experiment_log
              (hypothesis,variable,test_group,control_group,metric,
               result_metrics,conclusion,confidence_score,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'done') RETURNING id
        """, (body.hypothesis,body.variable,body.test_group,body.control_group,
              body.metric,json.dumps(result,default=str),conclusion,conf))
        eid = cur.fetchone()[0]
        conn.commit()
    return {"experiment_id":eid,"conclusion":conclusion,"confidence_score":conf,
            "result_metrics":result,"note":"目标变量：利润。CTR/询盘量为中间变量。"}


@router.get("/list")
def list_experiments():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM experiment_log ORDER BY created_at DESC LIMIT 100")
        return {"experiments": cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────
# 帖子查询（晨会录入用）
# ─────────────────────────────────────────────────────────────────────
@router.get("/posts/date")
def get_posts_by_date(date: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT c.id, c.content_type, c.car_model, c.country,
                   c.fb_post_id, c.posted_at, c.hypothesis_id,
                   h.code AS hypothesis_code,
                   COALESCE(f.impressions,0) AS impressions,
                   COALESCE(f.clicks,0) AS clicks,
                   COALESCE(f.ctr,0) AS ctr,
                   COUNT(DISTINCT l.id)  AS lead_count,
                   COUNT(DISTINCT d.id)  AS deal_count,
                   COALESCE(SUM(p.profit),0) AS total_profit
            FROM content_log c
            LEFT JOIN hypothesis_log h ON h.id=c.hypothesis_id
            LEFT JOIN LATERAL (SELECT * FROM funnel_log WHERE content_id=c.id
                ORDER BY synced_at DESC LIMIT 1) f ON TRUE
            LEFT JOIN lead_log l  ON l.content_id=c.id
            LEFT JOIN deal_log d  ON d.lead_id=l.id
            LEFT JOIN profit_log p ON p.content_id=c.id
            WHERE DATE(c.posted_at)=%s
            GROUP BY c.id,c.content_type,c.car_model,c.country,
                     c.fb_post_id,c.posted_at,c.hypothesis_id,
                     h.code,f.impressions,f.clicks,f.ctr
            ORDER BY c.posted_at DESC
        """, (date,))
        return {"posts": cur.fetchall()}


@router.get("/posts/yesterday")
def get_yesterday_posts():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return get_posts_by_date(yesterday)


# ─────────────────────────────────────────────────────────────────────
# Layer 5: 核心 Dashboard
# ─────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 实验统计
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE status='running')  AS active_hypotheses,
                   COUNT(*) FILTER (WHERE conclusion='成立')  AS confirmed_patterns,
                   COUNT(*) FILTER (WHERE conclusion='推翻')  AS overturned_patterns,
                   COALESCE(AVG(confidence_score),0)          AS avg_confidence,
                   MAX(updated_at)                            AS last_update
            FROM experiment_log
        """)
        exp = cur.fetchone()

        # 归因漏斗（30天）
        cur.execute("""
            SELECT COUNT(DISTINCT l.id)                                      AS total_leads,
                   COUNT(DISTINCT l.id) FILTER (WHERE l.lead_quality='high') AS hq_leads,
                   COUNT(DISTINCT q.id)                                      AS quotations,
                   COUNT(DISTINCT d.id)                                      AS deals,
                   COALESCE(SUM(p.profit),0)                                 AS total_profit,
                   COALESCE(SUM(p.revenue),0)                                AS total_revenue
            FROM lead_log l
            LEFT JOIN quotation_log q ON q.lead_id=l.id
            LEFT JOIN deal_log d      ON d.lead_id=l.id
            LEFT JOIN profit_log p    ON p.lead_id=l.id
            WHERE l.created_at >= now()-interval '30 days'
        """)
        funnel = cur.fetchone()

        # 内容类型利润排行
        cur.execute("""
            SELECT content_type, COUNT(*) AS deals,
                   COALESCE(SUM(profit),0) AS profit,
                   COUNT(DISTINCT lead_id) AS leads
            FROM profit_log WHERE created_at>=now()-interval '30 days'
            GROUP BY content_type ORDER BY profit DESC
        """)
        profit_rank = cur.fetchall()

        # 本周新增/失效规律
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE created_at>=now()-interval '7 days') AS new_patterns,
                   COUNT(*) FILTER (WHERE status='overturned' AND last_update>=now()-interval '7 days') AS dead_patterns
            FROM pattern_library
        """)
        pw = cur.fetchone()

        # 本周发现反例
        cur.execute("""
            SELECT COUNT(*) AS new_counters FROM counter_example
            WHERE created_at>=now()-interval '7 days'
        """)
        cw = cur.fetchone()

    return {
        "active_hypotheses":   exp["active_hypotheses"] or 0,
        "confirmed_patterns":  exp["confirmed_patterns"] or 0,
        "overturned_patterns": exp["overturned_patterns"] or 0,
        "avg_confidence":      round(float(exp["avg_confidence"] or 0),3),
        "last_update":         exp["last_update"],
        "total_leads":         funnel["total_leads"] or 0,
        "hq_leads":            funnel["hq_leads"] or 0,
        "quotations":          funnel["quotations"] or 0,
        "deals":               funnel["deals"] or 0,
        "total_profit":        float(funnel["total_profit"] or 0),
        "total_revenue":       float(funnel["total_revenue"] or 0),
        "profit_by_content":   [dict(r) for r in profit_rank],
        "new_patterns_week":   pw["new_patterns"] or 0,
        "dead_patterns_week":  pw["dead_patterns"] or 0,
        "counter_examples_week": cw["new_counters"] or 0,
    }
"""
experiment_patch.py
追加到 experiment.py 末尾。包含：
  L0 占位接口（3个，返回占位响应）
  L1 content_intelligence 录入/查询/实验/Dashboard
  L2 Business Dashboard / 漏斗转化率 / 排行榜补充
  L3 predictions生成/验证 / 周报 / 跨层规律提取 / Knowledge Dashboard
  L4 占位接口（3个，返回占位响应）
"""

# ─────────────────────────────────────────────────────────────────────
# L0: Environment Model 占位接口
# ─────────────────────────────────────────────────────────────────────
class EnvironmentSignalIn(BaseModel):
    signal_type: str = "market_trend"
    country: str | None = None
    signal_date: str | None = None   # YYYY-MM-DD
    description: str = ""
    impact_level: str = "medium"
    source: str = "manual"


@router.post("/environment")
def create_environment_signal(body: EnvironmentSignalIn):
    """L0 占位：录入环境信号。暂不实现分析逻辑。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO environment_signal
              (signal_type, country, signal_date, description, impact_level, source)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (body.signal_type, body.country, body.signal_date or None,
              body.description, body.impact_level, body.source))
        sid = cur.fetchone()[0]
        conn.commit()
    return {"signal_id": sid, "status": "recorded",
            "note": "L0 环境感知层已记录，分析逻辑待后续实现。"}


@router.get("/environment")
def list_environment_signals(days: int = 30):
    """L0 占位：查询环境信号。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM environment_signal
            WHERE created_at >= now() - interval '%s days'
            ORDER BY created_at DESC LIMIT 50
        """ % days)
        return {"signals": cur.fetchall(), "note": "L0 分析逻辑待后续实现。"}


@router.get("/dashboard/environment")
def dashboard_environment():
    """L0 占位：环境感知 Dashboard。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM environment_signal WHERE created_at >= now()-interval '30 days'")
        cnt = cur.fetchone()[0] or 0
    return {
        "total_signals_30d": cnt,
        "market_trend_count": 0,
        "competitor_count": 0,
        "policy_count": 0,
        "note": "L0 环境感知层占位。分析逻辑待后续实现。",
        "status": "placeholder"
    }


# ─────────────────────────────────────────────────────────────────────
# L1: Content World Model
# ─────────────────────────────────────────────────────────────────────
class ContentIntelligenceIn(BaseModel):
    content_id: int | None = None
    platform: str = "facebook"
    # ── 内容形式（P1）──────────────────────────────────────────
    content_type: str | None = None
    # 观点/案例/参数/价格/对比/故事/新闻/客户案例
    video_style: str | None = None
    # 数字人口播/真人口播/实拍/混剪/幻灯片
    production_source: str | None = None
    # AI_SLIDESHOW / DIGITAL_HUMAN / REAL_PERSON / REAL_SHOOT / AI_MIX / HYBRID
    duration_sec: int | None = None
    hook_type: str | None = None
    # 问题/震惊/价格/故事/数据
    country: str | None = None
    car_model: str | None = None
    # ── AI 分析能力预留（P2）──────────────────────────────────
    analysis_source: str = "manual"       # manual / ai
    content_summary: str | None = None
    hook_text: str | None = None
    content_tags: list | None = None      # ["案例","价格","故事"]
    emotion_type: str | None = None
    # RATIONAL / TRUST / AUTHORITY / CURIOSITY / FEAR / GREED / SCARCITY
    target_audience: str | None = None
    # DEALER / END_CUSTOMER / IMPORTER / CAR_TRADER / ENTERPRISE
    cta_type: str | None = None
    # WHATSAPP / DM / COMMENT / FOLLOW / INQUIRY
    # ── 平台指标 ──────────────────────────────────────────────
    impressions: int = 0
    reach: int = 0
    retention_3s: float = 0
    retention_5s: float = 0
    avg_watch_time: float = 0
    completion_rate: float = 0
    like_rate: float = 0
    comment_rate: float = 0
    share_rate: float = 0
    save_rate: float = 0
    follow_rate: float = 0


@router.post("/content-intelligence")
def create_content_intelligence(body: ContentIntelligenceIn):
    """L1 V2: 录入内容智能数据（内容形式 + 生产方式 + AI预留字段 + 平台指标）。"""
    ct = body.content_type; country = body.country; model = body.car_model
    if body.content_id and not (ct and country and model):
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT content_type, country, car_model FROM content_log WHERE id=%s",
                    (body.content_id,))
                row = cur.fetchone()
                if row:
                    ct = ct or row[0]; country = country or row[1]; model = model or row[2]
        except: pass

    import json as _json
    tags = _json.dumps(body.content_tags) if body.content_tags else '[]'

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO content_intelligence
              (content_id, platform, content_type, video_style, production_source,
               duration_sec, hook_type, country, car_model,
               analysis_source, content_summary, hook_text,
               content_tags, emotion_type, target_audience, cta_type,
               impressions, reach, retention_3s, retention_5s,
               avg_watch_time, completion_rate, like_rate, comment_rate,
               share_rate, save_rate, follow_rate)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (body.content_id, body.platform, ct, body.video_style,
              body.production_source, body.duration_sec, body.hook_type,
              country, model, body.analysis_source, body.content_summary,
              body.hook_text, tags, body.emotion_type, body.target_audience,
              body.cta_type, body.impressions, body.reach,
              body.retention_3s, body.retention_5s, body.avg_watch_time,
              body.completion_rate, body.like_rate, body.comment_rate,
              body.share_rate, body.save_rate, body.follow_rate))
        cid = cur.fetchone()[0]
        conn.commit()
    return {"content_intelligence_id": cid, "content_type": ct,
            "production_source": body.production_source}


@router.get("/content-intelligence")
def list_content_intelligence(content_type: str | None = None,
                               video_style: str | None = None,
                               days: int = 30):
    """L1: 查询内容智能列表。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """
            SELECT ci.*, c.fb_post_id, c.posted_at
            FROM content_intelligence ci
            LEFT JOIN content_log c ON c.id = ci.content_id
            WHERE ci.synced_at >= now() - interval '%s days'
        """ % days
        params = []
        if content_type:
            sql += " AND ci.content_type=%s"; params.append(content_type)
        if video_style:
            sql += " AND ci.video_style=%s"; params.append(video_style)
        sql += " ORDER BY ci.synced_at DESC LIMIT 200"
        cur.execute(sql, params)
        return {"items": cur.fetchall()}


@router.post("/content-experiment/run")
def run_content_experiment(test_value: str, control_value: str,
                            dimension: str = "content_type",
                            metric: str = "completion_rate",
                            days: int = 30):
    """L1 V2: 内容实验——支持多维度对比。
    dimension: content_type / video_style / production_source /
               hook_type / emotion_type / target_audience / cta_type
    metric:    completion_rate / retention_3s / avg_engagement /
               inquiry_rate / deal_rate / profit_per_content
    """
    VALID_DIMS = {"content_type","video_style","production_source",
                  "hook_type","emotion_type","target_audience","cta_type"}
    if dimension not in VALID_DIMS:
        raise HTTPException(400, f"dimension 必须是 {VALID_DIMS} 之一")

    with get_conn() as conn, conn.cursor() as cur:
        def stats(val):
            # 平台指标：直接从 content_intelligence
            cur.execute(f"""
                SELECT COUNT(*) n,
                       COALESCE(AVG(completion_rate),0) cr,
                       COALESCE(AVG(retention_3s),0) r3,
                       COALESCE(AVG(like_rate+comment_rate+share_rate),0) eng,
                       COALESCE(AVG(impressions),0) imp
                FROM content_intelligence
                WHERE {dimension}=%s
                  AND synced_at>=now()-interval '{days} days'
            """, (val,))
            r = cur.fetchone()
            n,cr,r3,eng,imp = r
            # 商业指标：JOIN 归因链路
            cur.execute(f"""
                SELECT COUNT(DISTINCT l.id) leads,
                       COUNT(DISTINCT d.id) deals,
                       COALESCE(SUM(p.profit),0) profit,
                       COALESCE(SUM(ci.impressions),0) total_imp
                FROM content_intelligence ci
                LEFT JOIN content_log c ON c.id=ci.content_id
                LEFT JOIN lead_log l    ON l.content_id=c.id
                LEFT JOIN deal_log d    ON d.lead_id=l.id
                LEFT JOIN profit_log p  ON p.content_id=c.id
                WHERE ci.{dimension}=%s
                  AND ci.synced_at>=now()-interval '{days} days'
            """, (val,))
            b = cur.fetchone()
            leads,deals,profit,total_imp = b
            profit = float(profit or 0); total_imp = float(total_imp or 0)
            return {
                "value": val, "n": n or 0,
                "completion_rate": round(float(cr or 0),4),
                "retention_3s":    round(float(r3 or 0),4),
                "avg_engagement":  round(float(eng or 0),4),
                "avg_impressions": round(float(imp or 0),1),
                "leads": leads or 0, "deals": deals or 0,
                "total_profit": profit,
                "inquiry_rate": round((leads or 0)/total_imp,6) if total_imp else 0,
                "deal_rate":    round((deals or 0)/(leads or 1),4) if (leads or 0)>0 else 0,
                "profit_per_content": round(profit/(n or 1),2) if (n or 0)>0 else 0,
            }

        test = stats(test_value); ctrl = stats(control_value)
        metric_val = test.get(metric,0); ctrl_val = ctrl.get(metric,0)
        lift = round(metric_val - ctrl_val, 4)
        rel  = round((metric_val/ctrl_val-1),4) if ctrl_val else None
        min_n = min(test["n"], ctrl["n"])
        conf  = round(min(min_n/10.0,1.0)*(0.4+0.6*min(abs(rel or 0),1.0)),3)
        if min_n < 3: conclusion = "数据不足"
        elif lift > 0 and conf >= 0.4: conclusion = "成立"
        elif lift <= 0 and conf >= 0.4: conclusion = "推翻"
        else: conclusion = "不显著"

    return {
        "dimension": dimension, "metric": metric,
        "test": test, "control": ctrl,
        "lift_abs": lift, "lift_rel": rel,
        "confidence": conf, "conclusion": conclusion,
        "insight": f"{test_value} vs {control_value}：{metric} 差异 {lift:+.4f}，置信度 {conf:.2f}",
        "note": "平台指标反映算法喜好，利润指标反映商业价值。两者共同验证方为完整结论。"
    }


@router.get("/dashboard/content")
def dashboard_content(days: int = 30):
    """L1 V2: Content Dashboard——内容类型/生产方式/标签/互动排行。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 总体指标
        cur.execute(f"""
            SELECT COUNT(*) total,
                   COALESCE(AVG(completion_rate),0) avg_cr,
                   COALESCE(AVG(retention_3s),0) avg_r3,
                   COALESCE(AVG(like_rate+comment_rate+share_rate),0) avg_engagement,
                   COALESCE(AVG(impressions),0) avg_imp
            FROM content_intelligence
            WHERE synced_at >= now()-interval '{days} days'
        """)
        s = cur.fetchone()

        # 内容类型排行（完播率 + 互动率）
        cur.execute(f"""
            SELECT content_type, COUNT(*) n,
                   COALESCE(AVG(completion_rate),0) avg_cr,
                   COALESCE(AVG(retention_3s),0) avg_r3,
                   COALESCE(AVG(like_rate+comment_rate+share_rate),0) avg_eng
            FROM content_intelligence
            WHERE synced_at >= now()-interval '{days} days'
              AND content_type IS NOT NULL
            GROUP BY content_type ORDER BY avg_cr DESC
        """)
        by_type = cur.fetchall()

        # 生产方式分布
        cur.execute(f"""
            SELECT production_source, COUNT(*) n,
                   COALESCE(AVG(completion_rate),0) avg_cr,
                   COALESCE(AVG(like_rate+comment_rate+share_rate),0) avg_eng
            FROM content_intelligence
            WHERE synced_at >= now()-interval '{days} days'
              AND production_source IS NOT NULL
            GROUP BY production_source ORDER BY avg_cr DESC
        """)
        by_production = cur.fetchall()

        # Production ROI Ranking（生产方式 × 完播/互动/询盘/利润）
        cur.execute(f"""
            SELECT ci.production_source,
                   COUNT(DISTINCT ci.id) content_count,
                   COALESCE(AVG(ci.completion_rate),0) avg_cr,
                   COALESCE(AVG(ci.like_rate+ci.comment_rate+ci.share_rate),0) avg_eng,
                   COUNT(DISTINCT l.id) leads,
                   COUNT(DISTINCT d.id) deals,
                   COALESCE(SUM(p.profit),0) profit
            FROM content_intelligence ci
            LEFT JOIN content_log c ON c.id=ci.content_id
            LEFT JOIN lead_log l    ON l.content_id=c.id
            LEFT JOIN deal_log d    ON d.lead_id=l.id
            LEFT JOIN profit_log p  ON p.content_id=c.id
            WHERE ci.synced_at >= now()-interval '{days} days'
              AND ci.production_source IS NOT NULL
            GROUP BY ci.production_source
            ORDER BY profit DESC, avg_cr DESC
        """)
        production_roi = cur.fetchall()

        # hook 类型排行
        cur.execute(f"""
            SELECT hook_type, COUNT(*) n,
                   COALESCE(AVG(retention_3s),0) avg_r3,
                   COALESCE(AVG(completion_rate),0) avg_cr
            FROM content_intelligence
            WHERE synced_at >= now()-interval '{days} days'
              AND hook_type IS NOT NULL
            GROUP BY hook_type ORDER BY avg_r3 DESC
        """)
        by_hook = cur.fetchall()

        # 内容标签排行（从 JSONB 数组展开）
        cur.execute(f"""
            SELECT tag, COUNT(*) n,
                   COALESCE(AVG(ci.completion_rate),0) avg_cr
            FROM content_intelligence ci,
                 jsonb_array_elements_text(ci.content_tags) AS tag
            WHERE ci.synced_at >= now()-interval '{days} days'
            GROUP BY tag ORDER BY n DESC LIMIT 15
        """)
        by_tag = cur.fetchall()

        # 情绪类型分布
        cur.execute(f"""
            SELECT emotion_type, COUNT(*) n,
                   COALESCE(AVG(completion_rate),0) avg_cr
            FROM content_intelligence
            WHERE synced_at >= now()-interval '{days} days'
              AND emotion_type IS NOT NULL
            GROUP BY emotion_type ORDER BY avg_cr DESC
        """)
        by_emotion = cur.fetchall()

    return {
        "total_content":        s["total"] or 0,
        "avg_completion_rate":  round(float(s["avg_cr"] or 0), 4),
        "avg_retention_3s":     round(float(s["avg_r3"] or 0), 4),
        "avg_engagement_rate":  round(float(s["avg_engagement"] or 0), 4),
        "avg_impressions":      round(float(s["avg_imp"] or 0), 1),
        "by_content_type":      [dict(r) for r in by_type],
        "by_production_source": [dict(r) for r in by_production],
        "production_roi":       [dict(r) for r in production_roi],
        "by_hook_type":         [dict(r) for r in by_hook],
        "by_content_tag":       [dict(r) for r in by_tag],
        "by_emotion_type":      [dict(r) for r in by_emotion],
    }


@router.get("/leaderboard/content")
def leaderboard_content(days: int = 30):
    """L1+L2 内容排行：完播率 / 互动率 / 询盘率 / 利润。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT ci.content_type,
                   COUNT(DISTINCT ci.id) n,
                   COALESCE(AVG(ci.completion_rate),0) avg_cr,
                   COALESCE(AVG(ci.like_rate+ci.comment_rate+ci.share_rate),0) avg_eng,
                   COUNT(DISTINCT l.id) leads,
                   COALESCE(SUM(p.profit),0) profit
            FROM content_intelligence ci
            LEFT JOIN content_log c     ON c.id=ci.content_id
            LEFT JOIN lead_log l        ON l.content_id=c.id
            LEFT JOIN profit_log p      ON p.content_id=c.id
            WHERE ci.synced_at >= now()-interval '{days} days'
              AND ci.content_type IS NOT NULL
            GROUP BY ci.content_type
            ORDER BY profit DESC, avg_cr DESC
        """)
        return {"leaderboard": [dict(r) for r in cur.fetchall()],
                "note": "按利润降序排列，利润相同则按完播率。"}


# ─────────────────────────────────────────────────────────────────────
# L2: Business Dashboard 补充
# ─────────────────────────────────────────────────────────────────────
@router.get("/dashboard/business")
def dashboard_business(days: int = 30):
    """L2: Business Dashboard——询盘/报价/成交/利润/ROI。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT COUNT(DISTINCT l.id) leads,
                   COUNT(DISTINCT l.id) FILTER (WHERE l.lead_quality='high') hq,
                   COUNT(DISTINCT q.id) quotes,
                   COUNT(DISTINCT d.id) deals,
                   COALESCE(SUM(p.profit),0) profit,
                   COALESCE(SUM(p.revenue),0) revenue,
                   COALESCE(SUM(c.ad_spend),0) ad_spend
            FROM lead_log l
            LEFT JOIN quotation_log q ON q.lead_id=l.id
            LEFT JOIN deal_log d      ON d.lead_id=l.id
            LEFT JOIN profit_log p    ON p.lead_id=l.id
            LEFT JOIN content_log c   ON c.id=l.content_id
            WHERE l.created_at >= now()-interval '{days} days'
        """)
        s = cur.fetchone()
        leads=s["leads"] or 0; hq=s["hq"] or 0
        quotes=s["quotes"] or 0; deals=s["deals"] or 0
        profit=float(s["profit"] or 0); revenue=float(s["revenue"] or 0)
        ad_spend=float(s["ad_spend"] or 0)
    return {
        "total_leads": leads, "hq_leads": hq,
        "quotations": quotes, "deals": deals,
        "total_profit": profit, "total_revenue": revenue,
        "roi": round(profit/ad_spend, 2) if ad_spend else None,
        "qualified_rate": round(hq/leads, 4) if leads else 0,
        "quote_rate":     round(quotes/leads, 4) if leads else 0,
        "deal_rate":      round(deals/leads, 4) if leads else 0,
        "profit_per_lead": round(profit/leads, 2) if leads else 0,
    }


@router.get("/funnel/conversion")
def funnel_conversion(days: int = 30):
    """L2: 完整漏斗转化率——Content→Lead→Quote→Deal→Profit。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM content_log WHERE posted_at>=now()-interval '{days} days'")
        contents = cur.fetchone()[0] or 0
        cur.execute(f"SELECT COUNT(*) FROM lead_log WHERE created_at>=now()-interval '{days} days'")
        leads = cur.fetchone()[0] or 0
        cur.execute(f"SELECT COUNT(*) FROM quotation_log WHERE quotation_time>=now()-interval '{days} days'")
        quotes = cur.fetchone()[0] or 0
        cur.execute(f"SELECT COUNT(*) FROM deal_log WHERE close_time>=now()-interval '{days} days'")
        deals = cur.fetchone()[0] or 0
        cur.execute(f"SELECT COALESCE(SUM(profit),0) FROM profit_log WHERE created_at>=now()-interval '{days} days'")
        profit = float(cur.fetchone()[0] or 0)
    return {
        "contents": contents, "leads": leads,
        "quotes": quotes, "deals": deals, "total_profit": profit,
        "content_to_lead": round(leads/contents, 4) if contents else 0,
        "lead_to_quote":   round(quotes/leads, 4)   if leads else 0,
        "quote_to_deal":   round(deals/quotes, 4)   if quotes else 0,
        "deal_to_profit":  profit/deals              if deals else 0,
    }


# ─────────────────────────────────────────────────────────────────────
# L3: Knowledge — Predictions / Weekly Report / 跨层规律
# ─────────────────────────────────────────────────────────────────────
class PredictionIn(BaseModel):
    pattern_id: int
    statement: str
    predicted_value: float
    confidence: float
    verify_days: int = 7


@router.post("/predictions")
def create_prediction(body: PredictionIn):
    """L3: 基于规律生成预测。"""
    verify_at = datetime.utcnow() + timedelta(days=body.verify_days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO prediction_log
              (pattern_id, statement, predicted_value, confidence, verify_at)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (body.pattern_id, body.statement, body.predicted_value,
              body.confidence, verify_at))
        pid = cur.fetchone()[0]
        cur.execute("UPDATE pattern_library SET prediction_count=prediction_count+1 WHERE id=%s",
                    (body.pattern_id,))
        conn.commit()
    return {"prediction_id": pid, "verify_at": verify_at.isoformat()}


class VerifyPredictionIn(BaseModel):
    actual_value: float
    outcome: str   # reinforce / weaken / overturn


@router.post("/predictions/{pid}/verify")
def verify_prediction(pid: int, body: VerifyPredictionIn):
    """L3: 验证预测，回写结果，更新规律计数。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT pattern_id, predicted_value FROM prediction_log WHERE id=%s", (pid,))
        row = cur.fetchone()
        if not row: raise HTTPException(404, "预测不存在")
        pattern_id, pred_val = row
        err = round(abs(body.actual_value - pred_val) / pred_val, 4) if pred_val else None
        status = "success" if body.outcome == "reinforce" else "fail"
        cur.execute("""
            UPDATE prediction_log
            SET actual_value=%s, error_rate=%s, outcome=%s,
                status=%s, verified_time=now()
            WHERE id=%s
        """, (body.actual_value, err, body.outcome, status, pid))
        # 更新规律预测成功/失败计数
        if body.outcome == "reinforce":
            cur.execute("UPDATE pattern_library SET prediction_success=prediction_success+1 WHERE id=%s", (pattern_id,))
        else:
            cur.execute("UPDATE pattern_library SET prediction_failure=prediction_failure+1 WHERE id=%s", (pattern_id,))
        conn.commit()
    return {"verified": True, "status": status, "error_rate": err, "outcome": body.outcome}


@router.post("/patterns/extract-l1")
def extract_l1_patterns():
    """L3: 从 content_intelligence 提取 L1 内容规律（含 Sample Size Guard）。"""
    saved = signals = 0
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT content_type, COUNT(*) n,
                   AVG(completion_rate) cr, AVG(retention_3s) r3,
                   AVG(like_rate+comment_rate+share_rate) eng
            FROM content_intelligence
            WHERE content_type IS NOT NULL
              AND synced_at >= now()-interval '90 days'
            GROUP BY content_type
        """)
        for r in cur.fetchall():
            sample_n = r["n"] or 0
            maturity, label, _ = _get_pattern_maturity(sample_n)
            pname = (f"{r['content_type']}内容完播规律"
                     if maturity != "OBSERVING"
                     else f"{r['content_type']}内容完播观察信号（样本不足）")
            conf = round(min(sample_n/10.0, 1.0) * 0.7, 3)
            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name, description, dimension, dimension_value,
                   metric, effect_size, support_count, confidence,
                   profit_contribution, sample_size, pattern_maturity)
                VALUES (%s,%s,'content_type',%s,'completion_rate',%s,%s,%s,0,%s,%s)
                ON CONFLICT DO NOTHING
            """, (pname,
                  f"[{label}] {r['content_type']}完播率均值{float(r['cr'] or 0):.1%}，"
                  f"3秒留存{float(r['r3'] or 0):.1%}，样本 {sample_n} 条",
                  r["content_type"], round(float(r["cr"] or 0),4),
                  sample_n, conf, sample_n, maturity))
            if maturity == "OBSERVING": signals += 1
            else: saved += 1
        conn.commit()
    return {"patterns_extracted": saved, "signals_recorded": signals, "layer": "L1"}


@router.post("/patterns/extract-cross")
def extract_cross_patterns():
    """L3: 提取跨层规律（L1内容指标 AND L2利润双维度）。"""
    saved = 0
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT ci.content_type,
                   COUNT(DISTINCT ci.id) n,
                   AVG(ci.completion_rate) avg_cr,
                   COALESCE(SUM(p.profit),0) total_profit,
                   COUNT(DISTINCT l.id) leads
            FROM content_intelligence ci
            LEFT JOIN content_log c ON c.id=ci.content_id
            LEFT JOIN lead_log l    ON l.content_id=c.id
            LEFT JOIN profit_log p  ON p.content_id=c.id
            WHERE ci.content_type IS NOT NULL
              AND ci.synced_at >= now()-interval '90 days'
            GROUP BY ci.content_type HAVING COUNT(DISTINCT ci.id)>=3
        """)
        for r in cur.fetchall():
            pname = f"{r['content_type']}内容跨层规律（完播率+利润）"
            profit_per = float(r["total_profit"] or 0) / max(r["n"],1)
            conf = round(min(r["n"]/8.0, 1.0) * (0.4 + 0.6*min(r["leads"]/5.0,1.0)), 3)
            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name, description, dimension, dimension_value,
                   metric, effect_size, support_count, confidence, profit_contribution)
                VALUES (%s,%s,'content_type',%s,'profit_per_content',%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (pname,
                  f"完播率{float(r['avg_cr'] or 0):.1%}，每条内容利润${profit_per:.0f}，样本{r['n']}条",
                  r["content_type"], round(profit_per,2), r["n"], conf, float(r["total_profit"] or 0)))
            saved += 1
        conn.commit()
    return {"patterns_extracted": saved, "layer": "L1+L2 cross"}


@router.get("/weekly-report")
def weekly_report():
    """L3: 每周知识报告——新增规律/失效规律/反例/预测成功率/四排行榜。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) n FROM pattern_library WHERE created_at>=now()-interval '7 days'")
        new_patterns = cur.fetchone()["n"] or 0
        cur.execute("SELECT COUNT(*) n FROM pattern_library WHERE status='overturned' AND last_update>=now()-interval '7 days'")
        dead_patterns = cur.fetchone()["n"] or 0
        cur.execute("SELECT COUNT(*) n FROM counter_example WHERE created_at>=now()-interval '7 days'")
        new_counters = cur.fetchone()["n"] or 0
        cur.execute("""
            SELECT COUNT(*) total,
                   COUNT(*) FILTER (WHERE status='success') success
            FROM prediction_log WHERE verified_time>=now()-interval '7 days'
        """)
        pr = cur.fetchone()
        pred_total = pr["total"] or 0
        pred_success = pr["success"] or 0
        pred_accuracy = round(pred_success/pred_total, 3) if pred_total else None

        # 内容规律排行
        cur.execute("SELECT pattern_name, confidence, profit_contribution FROM pattern_library WHERE dimension='content_type' AND status='active' ORDER BY profit_contribution DESC LIMIT 5")
        top_content = cur.fetchall()
        # 国家利润排行
        cur.execute("SELECT country, COUNT(*) deals, COALESCE(SUM(profit),0) profit FROM profit_log WHERE created_at>=now()-interval '7 days' GROUP BY country ORDER BY profit DESC LIMIT 5")
        top_country = cur.fetchall()
        # 车型利润排行
        cur.execute("SELECT car_model, COUNT(*) deals, COALESCE(SUM(profit),0) profit FROM profit_log WHERE created_at>=now()-interval '7 days' GROUP BY car_model ORDER BY profit DESC LIMIT 5")
        top_model = cur.fetchall()

    return {
        "period": "last_7_days",
        "new_patterns": new_patterns,
        "dead_patterns": dead_patterns,
        "new_counter_examples": new_counters,
        "prediction_accuracy": pred_accuracy,
        "prediction_total": pred_total,
        "top_content_patterns": [dict(r) for r in top_content],
        "top_country_profit":   [dict(r) for r in top_country],
        "top_model_profit":     [dict(r) for r in top_model],
    }


@router.get("/dashboard/knowledge")
def dashboard_knowledge():
    """L3: Knowledge Dashboard——规律/置信度/预测准确率/反例/WM Score。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT COUNT(*) total,
                   COUNT(*) FILTER (WHERE status='active') active,
                   COUNT(*) FILTER (WHERE status='overturned') overturned,
                   COALESCE(AVG(confidence),0) avg_conf,
                   COALESCE(SUM(prediction_count),0) pred_total,
                   COALESCE(SUM(prediction_success),0) pred_success
            FROM pattern_library
        """)
        p = cur.fetchone()
        cur.execute("SELECT COUNT(*) n FROM counter_example WHERE created_at>=now()-interval '30 days'")
        counters = cur.fetchone()["n"] or 0
        pred_acc = round(float(p["pred_success"] or 0)/float(p["pred_total"] or 1), 3) if (p["pred_total"] or 0)>0 else 0
        # WM Score
        active_r = float(p["active"] or 0)/max(float(p["total"] or 1),1)
        wm_score = round((0.35*pred_acc + 0.25*active_r + 0.20*min(counters/5.0,1.0) + 0.20*float(p["avg_conf"] or 0))*100, 1)
    return {
        "total_patterns": p["total"] or 0,
        "active_patterns": p["active"] or 0,
        "overturned_patterns": p["overturned"] or 0,
        "avg_confidence": round(float(p["avg_conf"] or 0), 3),
        "prediction_accuracy": pred_acc,
        "counter_examples_30d": counters,
        "world_model_score": wm_score,
    }


# ─────────────────────────────────────────────────────────────────────
# P3: Content Analyzer 占位接口（不实现任何分析逻辑）
# ─────────────────────────────────────────────────────────────────────
class AnalyzeContentIn(BaseModel):
    content_id: int
    media_url: str | None = None


@router.post("/content-analyzer/submit")
def submit_content_for_analysis(body: AnalyzeContentIn):
    """P3 占位：提交内容到分析队列。自动分析逻辑待后续实现。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO content_analyzer_queue (content_id, media_url, status)
            VALUES (%s,%s,'pending') RETURNING id
        """, (body.content_id, body.media_url))
        qid = cur.fetchone()[0]
        conn.commit()
    return {"queue_id": qid, "status": "pending",
            "note": "Content Analyzer 自动分析功能待后续实现。当前仅入队，不执行分析。"}


@router.get("/content-analyzer/queue")
def get_analyzer_queue():
    """P3 占位：查看分析队列。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT q.*, c.content_type, c.car_model
            FROM content_analyzer_queue q
            LEFT JOIN content_log c ON c.id=q.content_id
            ORDER BY q.created_at DESC LIMIT 50
        """)
        return {"queue": cur.fetchall(), "status": "placeholder",
                "note": "自动分析（字幕/Hook/分类/标签/情绪/CTA识别）待后续实现。"}


# ─────────────────────────────────────────────────────────────────────
# L4: Decision Engine 占位接口
# ─────────────────────────────────────────────────────────────────────
@router.get("/decisions")
def list_decisions():
    """L4 占位：查询决策建议列表。分析逻辑待后续实现。"""
    return {"decisions": [], "status": "placeholder",
            "note": "L4 Decision Engine 待 L1/L2/L3 数据积累后实现。"}


@router.post("/decisions/generate")
def generate_decisions():
    """L4 占位：触发决策生成。暂不实现任何决策逻辑。"""
    return {"status": "not_implemented",
            "note": "L4 Decision Engine 待 L1/L2/L3 数据积累后实现。当前请手动分析 /weekly-report 和 /leaderboard 数据做决策。"}


@router.get("/dashboard/decision")
def dashboard_decision():
    """L4 占位：Decision Dashboard。"""
    return {
        "pending_decisions": 0,
        "executed_decisions": 0,
        "decision_hit_rate": None,
        "next_week_recommendation": None,
        "status": "placeholder",
        "note": "L4 Decision Engine 占位。待 L3 规律库达到 20+ 条高置信规律后开始实现。"
    }


# =====================================================================
# World Model V1.1 — 模块1: Sample Size Guard API
# =====================================================================
@router.get("/patterns/maturity")
def list_patterns_by_maturity():
    """按成熟度分层展示规律：高可信/可信/初步/观察信号。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, pattern_name, description, dimension, dimension_value,
                   sample_size, confidence, pattern_maturity, status,
                   profit_contribution, prediction_count, prediction_success
            FROM pattern_library
            ORDER BY
                CASE pattern_maturity
                    WHEN 'HIGH_CONFIDENCE' THEN 1
                    WHEN 'VALIDATED'       THEN 2
                    WHEN 'PRELIMINARY'     THEN 3
                    WHEN 'OBSERVING'       THEN 4
                    ELSE 5
                END,
                confidence DESC
        """)
        rows = cur.fetchall()
    by_maturity = {"HIGH_CONFIDENCE":[], "VALIDATED":[], "PRELIMINARY":[], "OBSERVING":[]}
    for r in rows:
        m = r.get("pattern_maturity") or "OBSERVING"
        by_maturity.setdefault(m, []).append(dict(r))
    return {
        "by_maturity": by_maturity,
        "summary": {k: len(v) for k,v in by_maturity.items()},
        "note": "样本 < 10 的为观察信号，不进入预测系统。样本 10-30 为初步规律，谨慎参考。"
    }


# =====================================================================
# World Model V1.1 — 模块2: Data Quality Score
# =====================================================================
class DataQualityInput(BaseModel):
    actual_lead_count: int = 0    # 实际收到询盘数（人工填）
    actual_deal_count: int = 0    # 实际成交数（人工填）
    notes: str | None = None


@router.post("/data-quality/measure")
def measure_data_quality(body: DataQualityInput):
    """计算今日数据质量评分，写入 data_quality_metrics。"""
    with get_conn() as conn, conn.cursor() as cur:
        # 内容完整率：已录入CI / 已发布帖数
        cur.execute("SELECT COUNT(*) FROM content_log WHERE DATE(posted_at)=CURRENT_DATE")
        published = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM content_intelligence WHERE DATE(synced_at)=CURRENT_DATE")
        recorded_ci = cur.fetchone()[0] or 0
        content_rate = round(recorded_ci / published, 4) if published else 0

        # 询盘完整率
        cur.execute("SELECT COUNT(*) FROM lead_log WHERE DATE(created_at)=CURRENT_DATE")
        recorded_leads = cur.fetchone()[0] or 0
        lead_rate = round(recorded_leads / body.actual_lead_count, 4) if body.actual_lead_count else 0

        # 报价完整率（有询盘且已跟进报价）
        cur.execute("""SELECT COUNT(DISTINCT l.id) FROM lead_log l JOIN quotation_log q ON q.lead_id=l.id
                       WHERE DATE(l.created_at)=CURRENT_DATE""")
        quoted = cur.fetchone()[0] or 0
        quote_rate = round(quoted / max(recorded_leads,1), 4) if recorded_leads else 0

        # 成交完整率
        cur.execute("SELECT COUNT(*) FROM deal_log WHERE DATE(close_time)=CURRENT_DATE")
        recorded_deals = cur.fetchone()[0] or 0
        deal_rate = round(recorded_deals / body.actual_deal_count, 4) if body.actual_deal_count else 0

        # 利润完整率
        cur.execute("SELECT COUNT(*) FROM profit_log WHERE DATE(created_at)=CURRENT_DATE")
        recorded_profit = cur.fetchone()[0] or 0
        profit_rate = round(recorded_profit / body.actual_deal_count, 4) if body.actual_deal_count else 0

        # 综合评分（加权）
        score = round((
            content_rate * 25 +
            lead_rate    * 35 +
            deal_rate    * 25 +
            profit_rate  * 15
        ), 1)
        if score >= 90:   level = "EXCELLENT"
        elif score >= 80: level = "GOOD"
        elif score >= 60: level = "FAIR"
        else:             level = "DANGER"

        cur.execute("""
            INSERT INTO data_quality_metrics
              (measured_date, content_completion_rate, lead_completion_rate,
               quote_completion_rate, deal_completion_rate, profit_completion_rate,
               published_content_count, recorded_content_count,
               actual_lead_count, recorded_lead_count,
               actual_deal_count, recorded_deal_count,
               overall_score, quality_level, notes)
            VALUES (CURRENT_DATE,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (content_rate, lead_rate, quote_rate, deal_rate, profit_rate,
              published, recorded_ci, body.actual_lead_count, recorded_leads,
              body.actual_deal_count, recorded_deals, score, level, body.notes))
        conn.commit()

    return {
        "overall_score": score,
        "quality_level": level,
        "breakdown": {
            "content": f"{content_rate:.1%} ({recorded_ci}/{published})",
            "lead":    f"{lead_rate:.1%} ({recorded_leads}/{body.actual_lead_count})",
            "quote":   f"{quote_rate:.1%}",
            "deal":    f"{deal_rate:.1%} ({recorded_deals}/{body.actual_deal_count})",
            "profit":  f"{profit_rate:.1%}",
        },
        "allow_pattern_extraction": score >= 80,
        "warning": None if score >= 80 else "⚠️ 数据质量不足（<80分），规律提取已暂停，请补录数据后再提取。"
    }


@router.get("/data-quality/history")
def get_data_quality_history(days: int = 30):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM data_quality_metrics
            WHERE measured_date >= CURRENT_DATE - interval '%s days'
            ORDER BY measured_date DESC
        """ % days)
        rows = cur.fetchall()
    latest = dict(rows[0]) if rows else None
    return {
        "latest": latest,
        "history": [dict(r) for r in rows],
        "allow_pattern_extraction": (latest["overall_score"] >= 80) if latest else False,
    }


@router.get("/data-quality/dashboard")
def data_quality_dashboard():
    """数据质量仪表盘：综合评分 + 各层完整率 + 是否允许规律提取。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM data_quality_metrics ORDER BY measured_date DESC LIMIT 1
        """)
        latest = cur.fetchone()
        cur.execute("""
            SELECT AVG(overall_score) avg_score
            FROM data_quality_metrics
            WHERE measured_date >= CURRENT_DATE - interval '7 days'
        """)
        week = cur.fetchone()
    if not latest:
        return {"status": "no_data", "note": "尚未进行数据质量评估，请调用 /data-quality/measure 录入。"}
    score = float(latest["overall_score"] or 0)
    return {
        "overall_score":    score,
        "quality_level":    latest["quality_level"],
        "week_avg_score":   round(float(week["avg_score"] or 0), 1),
        "allow_pattern_extraction": score >= 80,
        "content_rate":  float(latest["content_completion_rate"] or 0),
        "lead_rate":     float(latest["lead_completion_rate"] or 0),
        "deal_rate":     float(latest["deal_completion_rate"] or 0),
        "profit_rate":   float(latest["profit_completion_rate"] or 0),
        "measured_date": latest["measured_date"],
        "warning": None if score >= 80 else "⚠️ 数据质量低于80分，Knowledge Layer已暂停自动规律提取。请补录数据。"
    }


# =====================================================================
# World Model V1.1 — 模块3: Pattern Health Monitor
# =====================================================================
@router.post("/patterns/health/check")
def check_pattern_health():
    """计算所有活跃规律的健康度（准确率趋势），写入 pattern_health。"""
    updated = 0
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id FROM pattern_library WHERE status='active'")
        pattern_ids = [r["id"] for r in cur.fetchall()]
        for pid in pattern_ids:
            def acc(days):
                cur.execute("""
                    SELECT COUNT(*) total,
                           COUNT(*) FILTER (WHERE status='success') success
                    FROM prediction_log
                    WHERE pattern_id=%s
                      AND verified_time >= now()-interval '%s days'
                      AND verified_time IS NOT NULL
                """ % (pid, days))
                r = cur.fetchone()
                t = r["total"] or 0; s = r["success"] or 0
                return round(s/t, 4) if t else None
            a30 = acc(30); a60 = acc(60); a90 = acc(90)
            # 趋势
            vals = [v for v in [a90, a60, a30] if v is not None]
            if len(vals) >= 2:
                trend = "UP" if vals[-1] > vals[0] else ("DOWN" if vals[-1] < vals[0] else "FLAT")
            else:
                trend = "FLAT"
            # 连续下降次数（从 pattern_health 历史记录）
            cur.execute("""
                SELECT consecutive_down FROM pattern_health
                WHERE pattern_id=%s ORDER BY measured_at DESC LIMIT 1
            """, (pid,))
            prev = cur.fetchone()
            prev_down = (prev["consecutive_down"] or 0) if prev else 0
            consec_down = prev_down + 1 if trend == "DOWN" else 0
            health = "HEALTHY"
            if consec_down >= 5:   health = "INVALID"
            elif consec_down >= 3: health = "WEAKENING"
            cur.execute("""
                INSERT INTO pattern_health
                  (pattern_id, last_30d_accuracy, last_60d_accuracy, last_90d_accuracy,
                   trend, consecutive_down, health_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (pid, a30, a60, a90, trend, consec_down, health))
            # 同步更新规律状态
            if health == "INVALID":
                cur.execute("UPDATE pattern_library SET status='overturned' WHERE id=%s", (pid,))
            elif health == "WEAKENING":
                cur.execute("UPDATE pattern_library SET status='weakened' WHERE id=%s", (pid,))
            updated += 1
        conn.commit()
    return {"patterns_checked": updated}


@router.get("/patterns/health/report")
def pattern_health_report():
    """本周规律健康报告：失效/弱化/新增/健康。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT p.id, p.pattern_name, p.sample_size, p.confidence,
                   p.pattern_maturity, p.status,
                   ph.trend, ph.health_status, ph.consecutive_down,
                   ph.last_30d_accuracy, ph.measured_at
            FROM pattern_library p
            LEFT JOIN LATERAL (
                SELECT * FROM pattern_health WHERE pattern_id=p.id
                ORDER BY measured_at DESC LIMIT 1
            ) ph ON TRUE
            ORDER BY ph.health_status, p.confidence DESC
        """)
        rows = cur.fetchall()
        new_p  = [r for r in rows if r["status"]=="active" and
                  r.get("measured_at") and
                  str(r["measured_at"]) > str(datetime.utcnow() - timedelta(days=7))]
        weak   = [r for r in rows if r.get("health_status")=="WEAKENING"]
        invalid= [r for r in rows if r.get("health_status")=="INVALID"]
        healthy= [r for r in rows if r.get("health_status")=="HEALTHY"]
    return {
        "new_patterns_week":    len(new_p),
        "weakening_patterns":   len(weak),
        "invalid_patterns":     len(invalid),
        "healthy_patterns":     len(healthy),
        "weakening_list":  [dict(r) for r in weak],
        "invalid_list":    [dict(r) for r in invalid],
    }


# =====================================================================
# World Model V1.1 — 模块4: Prediction Graveyard
# =====================================================================
@router.post("/predictions/{pid}/bury")
def bury_prediction(pid: int, failure_reason: str = "model_error",
                    lesson_learned: str | None = None):
    """将失败预测移入墓地，供世界模型学习。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM prediction_log WHERE id=%s", (pid,))
        pred = cur.fetchone()
        if not pred: raise HTTPException(404, "预测不存在")
        err = float(pred["error_rate"] or 0)
        severity = "HIGH" if err > 0.5 else ("MEDIUM" if err > 0.2 else "LOW")
        cur.execute("""
            INSERT INTO prediction_graveyard
              (prediction_id, prediction_content, expected_result, actual_result,
               error_rate, failure_reason, severity, lesson_learned)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (pid, pred["statement"], pred["predicted_value"], pred["actual_value"],
              err, failure_reason, severity, lesson_learned))
        conn.commit()
    return {"buried": True, "severity": severity,
            "note": "已记入预测墓地，用于修正世界模型。"}


@router.get("/predictions/graveyard")
def list_graveyard(limit: int = 20):
    """预测墓地列表：失败预测供模型学习。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT g.*, p.statement AS original_statement
            FROM prediction_graveyard g
            LEFT JOIN prediction_log p ON p.id=g.prediction_id
            ORDER BY g.error_rate DESC NULLS LAST, g.created_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        # Top 10 高误差
        cur.execute("""
            SELECT g.prediction_content, g.error_rate, g.failure_reason, g.severity
            FROM prediction_graveyard g
            ORDER BY g.error_rate DESC NULLS LAST LIMIT 10
        """)
        top_errors = cur.fetchall()
    return {
        "graveyard": [dict(r) for r in rows],
        "top_10_errors": [dict(r) for r in top_errors],
        "note": "世界模型优先从失败案例学习。高误差预测是模型最重要的修正信号。"
    }


# =====================================================================
# World Model V1.1 — 统一健康仪表盘
# =====================================================================
@router.get("/dashboard/world-model-health")
def world_model_health():
    """世界模型综合健康仪表盘：数据质量 + 规律成熟度 + 预测墓地 + Pattern Health。"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 数据质量
        cur.execute("SELECT * FROM data_quality_metrics ORDER BY measured_date DESC LIMIT 1")
        dq = cur.fetchone()
        dq_score = float((dq["overall_score"] or 0)) if dq else 0

        # 规律成熟度分布
        cur.execute("""
            SELECT pattern_maturity, COUNT(*) n
            FROM pattern_library GROUP BY pattern_maturity
        """)
        maturity_dist = {r["pattern_maturity"]: r["n"] for r in cur.fetchall()}

        # Pattern Health
        cur.execute("""
            SELECT health_status, COUNT(*) n FROM (
                SELECT DISTINCT ON (pattern_id) pattern_id, health_status
                FROM pattern_health ORDER BY pattern_id, measured_at DESC
            ) sub GROUP BY health_status
        """)
        health_dist = {r["health_status"]: r["n"] for r in cur.fetchall()}

        # 预测墓地
        cur.execute("SELECT COUNT(*) n, AVG(error_rate) avg_err FROM prediction_graveyard")
        grave = cur.fetchone()

        # 规律提取是否被暂停
        allow_extract = dq_score >= 80

    return {
        "data_quality_score":   dq_score,
        "data_quality_level":   (dq["quality_level"] if dq else "UNKNOWN"),
        "allow_pattern_extraction": allow_extract,
        "pattern_maturity": {
            "HIGH_CONFIDENCE": maturity_dist.get("HIGH_CONFIDENCE", 0),
            "VALIDATED":       maturity_dist.get("VALIDATED", 0),
            "PRELIMINARY":     maturity_dist.get("PRELIMINARY", 0),
            "OBSERVING":       maturity_dist.get("OBSERVING", 0),
        },
        "pattern_health": {
            "healthy":   health_dist.get("HEALTHY", 0),
            "weakening": health_dist.get("WEAKENING", 0),
            "invalid":   health_dist.get("INVALID", 0),
        },
        "prediction_graveyard_count": grave["n"] or 0,
        "avg_error_rate": round(float(grave["avg_err"] or 0), 4),
        "warning": (None if allow_extract
                    else "⚠️ 数据质量低于80分，Knowledge Layer规律提取已暂停。"),
        "status_summary": (
            "🟢 健康" if dq_score >= 80 and health_dist.get("WEAKENING",0) == 0
            else "🟡 注意" if dq_score >= 60
            else "🔴 危险"
        )
    }
