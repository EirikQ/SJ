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
def _extract_patterns():
    """每周自动运行：从归因链路提取规律，写入 pattern_library。"""
    patterns_saved = 0
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
            if not r["content_type"] or r["lead_count"] < 2:
                continue
            pname = f"{r['content_type']}内容利润规律"
            profit_per_lead = (float(r["total_profit"]) / r["lead_count"]) if r["lead_count"] else 0
            hq_rate = r["hq_lead_count"] / r["lead_count"] if r["lead_count"] else 0
            conf = min(r["lead_count"] / 10.0, 1.0) * (0.5 + 0.5 * min(r["profit_count"] / 5.0, 1.0))

            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name,description,dimension,dimension_value,
                   metric,effect_size,support_count,confidence,profit_contribution)
                VALUES (%s,%s,'content_type',%s,'profit_per_lead',%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (pname,
                  f"{r['content_type']}类内容每条询盘平均利润 ${profit_per_lead:.0f}，高质量询盘率 {hq_rate:.1%}",
                  r["content_type"], round(profit_per_lead, 2),
                  r["lead_count"], round(conf, 3), float(r["total_profit"])))
            patterns_saved += 1

        # 按国家提取规律
        cur.execute("""
            SELECT country, COUNT(*) AS deals, COALESCE(SUM(profit),0) AS profit,
                   COUNT(DISTINCT lead_id) AS leads
            FROM profit_log WHERE created_at >= now()-interval '90 days'
            AND country IS NOT NULL
            GROUP BY country HAVING COUNT(*)>=2
        """)
        for r in cur.fetchall():
            cur.execute("""
                INSERT INTO pattern_library
                  (pattern_name,dimension,dimension_value,metric,
                   effect_size,support_count,confidence,profit_contribution)
                VALUES (%s,'country',%s,'profit_per_deal',%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (f"{r['country']}市场利润规律", r["country"],
                  round(float(r["profit"])/r["deals"],2) if r["deals"] else 0,
                  r["deals"], round(min(r["deals"]/5.0,1.0)*0.6, 3), float(r["profit"])))
            patterns_saved += 1

        conn.commit()
    return {"patterns_extracted": patterns_saved}


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
