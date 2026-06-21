from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv, set_key
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, date
import requests, os, random, json, pytz

load_dotenv()

app = FastAPI(title="柳汽出口 AI 营销系统", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173","https://china-auto-frontend-sa4h.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 动态配置（可通过设置页修改）────────────────────────────
def get_env(key, default=""):
    return os.getenv(key, default)

DAKAR_TZ   = pytz.timezone("Africa/Dakar")
post_log   = []
daily_stats = {}
scheduler  = BackgroundScheduler(timezone=DAKAR_TZ)
scheduled_jobs = {}

# ══════════════════════════════════════════════════════════════
# 车型知识库
# ══════════════════════════════════════════════════════════════
VEHICLE_KB = {
    "T5 EVO": {
        "full_name": "Forthing T5 EVO", "type": "紧凑型SUV",
        "engine": "1.5T涡轮增压 194马力 285Nm",
        "transmission": "7速双离合DCT", "seats": 5,
        "key_features": [
            "1.5T涡轮增压194马力，动力充沛",
            "7速DCT双离合，换挡迅速",
            "L2+辅助驾驶系统",
            "12英寸高清触摸屏",
            "全景天窗",
            "无线充电",
            "360度全景摄像头（顶配）",
            "全新未上牌，享受完整质保",
        ],
        "price_usd": "16,000起", "usp": "比丰田便宜30%，全新车非二手",
        "target_audience": "25-45岁城市家庭和商务人士",
        "image_style": "silver SUV on modern Dakar street golden hour lighting African city",
        "hashtags": ["#ForthingT5EVO","#T5EVO","#SUV","#ChinaAuto","#Dakar",
                     "#Algerie","#AfricaAuto","#NewCar","#ForthingAfrica","#SUVLife",
                     "#FamilyCar","#MadeInChina","#AfricaDrives","#CarOfTheYear"],
    },
    "FRIDAY": {
        "full_name": "Forthing Friday（星期五）", "type": "纯电MPV",
        "engine": "纯电动", "range_km": "420km CLTC", "seats": 7,
        "key_features": [
            "100%纯电动，零燃油费",
            "CLTC续航420公里",
            "7座大空间，适合全家出行",
            "30分钟快充至80%",
            "宽大电动侧滑门",
            "全景玻璃车顶",
            "智能语音控制",
        ],
        "price_usd": "18,000起", "usp": "7座纯电家用MPV，零油费零污染",
        "target_audience": "大家庭、出租车运营商、环保用车人群",
        "image_style": "electric MPV teal color modern African city blue sky futuristic",
        "hashtags": ["#ForthingFriday","#ElectricMPV","#EVAfrica","#ZeroEmission",
                     "#ElectricCar","#7Seats","#FamilyVan","#ChinaEV",
                     "#GreenTransport","#Dakar","#FutureOfDriving","#CleanEnergy"],
    },
    "V9": {
        "full_name": "Forthing V9", "type": "豪华MPV",
        "engine": "2.0T涡轮增压 224马力",
        "transmission": "8速自动", "seats": 7,
        "key_features": [
            "2.0T 224马力，动力强劲",
            "商务头等舱座椅（带按摩功能）",
            "双区自动恒温空调",
            "BOSE高级12扬声器音响",
            "256色氛围灯",
            "商务级豪华内饰",
            "电动侧滑门",
        ],
        "price_usd": "22,000起", "usp": "商务级豪华MPV，价格仅是同级竞品的一半",
        "target_audience": "企业高管、VIP接送、大家庭",
        "image_style": "black luxury MPV night luxury hotel dramatic lighting red carpet",
        "hashtags": ["#ForthingV9","#LuxuryMPV","#BusinessCar","#V9MPV",
                     "#ChinaLuxury","#VIPTransport","#Algerie","#MPV",
                     "#PremiumCar","#ExecutiveCar","#ForthingAfrica","#LuxuryLife"],
    },
    "P6": {
        "full_name": "Forthing P6", "type": "运动轿车",
        "engine": "1.5T涡轮增压 177马力",
        "transmission": "7速DCT", "seats": 5,
        "key_features": [
            "欧式溜背运动造型",
            "177马力涡轮增压",
            "10.25英寸全液晶仪表盘",
            "无线CarPlay/Android Auto",
            "LED矩阵大灯",
            "疲劳驾驶监测",
            "全新未上牌，完整质保",
        ],
        "price_usd": "14,000起", "usp": "欧式运动轿车，科技配置，价格亲民",
        "target_audience": "25-40岁年轻专业人士，追求个性的买家",
        "image_style": "sporty white sedan coastal road Mediterranean sea cinematic",
        "hashtags": ["#ForthingP6","#P6Sedan","#Sedan","#ChinaAuto",
                     "#AfricaCar","#NewCar","#ForthingAfrica","#SportSedan",
                     "#StyleAndPerformance","#Dakar","#Algerie","#YoungAndFree"],
    },
    "P8": {
        "full_name": "Forthing P8", "type": "旗舰SUV",
        "engine": "2.0T涡轮增压 224马力 / 插混版可选",
        "transmission": "8速自动", "seats": 5,
        "key_features": [
            "2.0T 224马力旗舰性能",
            "插混PHEV版本可选",
            "双12.3英寸全景联屏",
            "L2+高速辅助驾驶",
            "空气悬挂（顶配）",
            "高级真皮内饰",
            "全景天窗",
        ],
        "price_usd": "24,000起", "usp": "旗舰混动SUV，豪华配置，面向未来",
        "target_audience": "30-55岁高端买家和企业高管",
        "image_style": "dark flagship SUV misty mountain road luxury mood cinematic",
        "hashtags": ["#ForthingP8","#P8SUV","#FlagshipSUV","#PHEV",
                     "#HybridCar","#LuxurySUV","#ChinaAuto","#Algerie",
                     "#PremiumSUV","#ForthingAfrica","#HybridLife","#FutureCar"],
    },
}

POST_TYPES = {
    "product_intro":     "写一篇令人兴奋的产品介绍帖子。用强有力的标题开头，用emoji突出3个核心卖点，最后加WhatsApp联系方式。",
    "price_value":       "写一篇强调价格优势的帖子，对比'同类品牌'（不点名），让读者感受到物超所值。制造紧迫感：数量有限。最后加WhatsApp。",
    "lifestyle":         "写一篇情感共鸣的生活方式帖子，描绘用车场景：家庭出游、商务出行、周末探险。语言生动有画面感，最后轻柔引导联系。",
    "feature_spotlight": "深度介绍这款车的某一个特色功能，解释它在非洲日常生活中的实际价值。教育性+互动性，最后提一个问题引导评论。",
    "new_arrival":       "写一篇高能量的新车到货公告！使用：终于、独家、限量等词。核心参数用列表展示。最后强力引导WhatsApp咨询。",
}

BEST_POST_TIMES = [
    {"hour": 9,  "minute": 0,  "label": "早间高峰"},
    {"hour": 13, "minute": 0,  "label": "午间高峰"},
    {"hour": 20, "minute": 30, "label": "晚间黄金"},
]

# ══════════════════════════════════════════════════════════════
# 核心函数
# ══════════════════════════════════════════════════════════════
def call_deepseek(messages, temperature=0.85, max_tokens=800):
    api_key = get_env("DEEPSEEK_API_KEY")
    model   = get_env("AI_MODEL", "deepseek-chat")
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": model, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=60,
    )
    return resp.json()["choices"][0]["message"]["content"].strip()

def build_post_prompt(model, market, language, post_type, whatsapp):
    kb = VEHICLE_KB.get(model, VEHICLE_KB["T5 EVO"])
    features = "\n".join(f"- {f}" for f in kb["key_features"])
    tags = random.sample(kb["hashtags"], min(6, len(kb["hashtags"])))
    lang_note = {
        "French":  "全部用法语写作，使用塞内加尔/阿尔及利亚的现代口语法语。",
        "English": "全部用英语写作，语气积极有活力。",
        "Arabic":  "全部用现代标准阿拉伯语（فصحى）写作。",
    }.get(language, "用法语写作。")
    return f"""你是{market}市场的{kb['full_name']}汽车社交媒体营销专家。

车辆信息：
- 车型：{kb['full_name']} | {kb['type']} | 起售价{kb['price_usd']}美元
- 核心卖点：
{features}
- 差异化优势：{kb['usp']}
- 目标用户：{kb['target_audience']}

帖子类型：{POST_TYPES.get(post_type, POST_TYPES['product_intro'])}

语言要求：{lang_note}

格式规范：
- 正文100-140字（不含hashtag）
- 自然融入3-5个emoji
- 结尾必须包含：WhatsApp: {whatsapp}
- 最后一行：从以下选6个hashtag：{' '.join(tags)}
- 禁止使用"您是否在寻找一辆车？"等套话
- 要像真人营销专家写的，不像机器人

现在写这篇帖子："""

def post_to_facebook(message):
    page_id = get_env("FACEBOOK_PAGE_ID")
    token   = get_env("FACEBOOK_PAGE_TOKEN")
    url  = f"https://graph.facebook.com/v23.0/{page_id}/feed"
    resp = requests.post(url,
        data={"message": message, "access_token": token}, timeout=60)
    return resp.json()

def log_post(model, language, market, post_type, content, fb_response):
    today_str = date.today().isoformat()
    now_dakar = datetime.now(DAKAR_TZ)
    success   = "id" in fb_response
    hour      = now_dakar.hour
    entry = {
        "timestamp":      now_dakar.isoformat(),
        "date":           today_str,
        "hour":           hour,
        "model":          model,
        "language":       language,
        "market":         market,
        "post_type":      post_type,
        "content_preview": content[:80] + "...",
        "success":        success,
        "fb_post_id":     fb_response.get("id", ""),
        "char_count":     len(content),
        "has_emoji":      any(ord(c) > 127 for c in content),
        "has_hashtag":    "#" in content,
    }
    post_log.append(entry)
    if today_str not in daily_stats:
        daily_stats[today_str] = {
            "posts": 0, "success": 0, "failed": 0,
            "models": {}, "post_types": {}, "markets": {},
            "languages": {}, "hours": {},
        }
    s = daily_stats[today_str]
    s["posts"] += 1
    if success:
        s["success"] += 1
    else:
        s["failed"] += 1
    s["models"][model]         = s["models"].get(model, 0) + 1
    s["post_types"][post_type] = s["post_types"].get(post_type, 0) + 1
    s["markets"][market]       = s["markets"].get(market, 0) + 1
    s["languages"][language]   = s["languages"].get(language, 0) + 1
    s["hours"][str(hour)]      = s["hours"].get(str(hour), 0) + 1

def run_scheduled_post(model, market, language, post_type, whatsapp, post_mode="text"):
    print(f"[定时任务] 自动发帖: {model} | {market} | {language} | 模式:{post_mode}")
    try:
        prompt  = build_post_prompt(model, market, language, post_type, whatsapp)
        content = call_deepseek([
            {"role": "system", "content": "你是非洲市场汽车社交媒体营销专家。"},
            {"role": "user",   "content": prompt},
        ])
        if post_mode == "image":
            # 图文模式：调用图片生成接口
            from image_post import generate_image_sf, overlay_text, publish_photo_to_facebook
            img_bytes = generate_image_sf(model)
            img_bytes = overlay_text(img_bytes, content, model)
            fb_resp   = publish_photo_to_facebook(img_bytes, content)
        elif post_mode == "video":
            # 视频模式：调用视频生成接口
            from video_post import generate_sf_image, make_slideshow_gif, publish_gif_to_facebook
            frames    = [generate_sf_image(model) for _ in range(3)]
            gif_bytes = make_slideshow_gif(frames, content)
            fb_resp   = publish_gif_to_facebook(gif_bytes, content)
        else:
            # 纯文字
            fb_resp = post_to_facebook(content)
        log_post(model, language, market, post_type, content, fb_resp)
        print(f"[定时任务] ✅ 发布成功: {fb_resp.get('id', '失败')}")
    except Exception as e:
        print(f"[定时任务] ❌ 错误: {e}")

# ══════════════════════════════════════════════════════════════
# AI 日报生成
# ══════════════════════════════════════════════════════════════
def generate_detailed_report(target_date: str = None) -> dict:
    today = target_date or date.today().isoformat()
    s     = daily_stats.get(today, {
        "posts":0,"success":0,"failed":0,
        "models":{},"post_types":{},"markets":{},
        "languages":{},"hours":{}
    })

    # 近7天数据
    all_dates = sorted(daily_stats.keys())[-7:]
    weekly_total   = sum(daily_stats[d]["success"] for d in all_dates)
    weekly_avg     = round(weekly_total / max(len(all_dates), 1), 1)

    # 车型热度排名
    model_rank = sorted(s["models"].items(), key=lambda x: x[1], reverse=True)

    # 最佳发帖时间
    hour_data   = s.get("hours", {})
    best_hour   = max(hour_data, key=hour_data.get) if hour_data else "未知"

    # 最受欢迎市场
    market_rank = sorted(s["markets"].items(), key=lambda x: x[1], reverse=True)

    # 用 DeepSeek 生成 AI 建议
    stats_summary = f"""
今日数据（{today}）：
- 总发帖：{s['posts']} 条，成功：{s['success']} 条，失败：{s['failed']} 条
- 车型分布：{json.dumps(s['models'], ensure_ascii=False)}
- 帖子类型分布：{json.dumps(s['post_types'], ensure_ascii=False)}
- 目标市场分布：{json.dumps(s['markets'], ensure_ascii=False)}
- 发帖时段分布：{json.dumps(s['hours'], ensure_ascii=False)}
- 近7天日均发帖：{weekly_avg} 条
"""
    ai_advice        = ""
    ai_schedule_json = []   # AI推荐的定时任务配置
    try:
        # 第一步：生成文字分析
        ai_advice = call_deepseek([
            {"role": "system", "content": "你是一位非洲汽车市场社交媒体运营专家，擅长分析Facebook运营数据并给出具体可执行的优化建议。"},
            {"role": "user",   "content": f"""基于以下运营数据，给出详细分析和下周执行建议：

{stats_summary}

请按以下格式输出：

📊 数据解读
（分析今日表现，指出亮点和不足）

🏆 车型热度分析
（哪款车反响最好，为什么，建议加大哪款的推广）

⏰ 发帖时间建议
（根据时段数据，建议调整发帖时间）

📅 下周执行计划
（具体到每天推荐发什么车型、什么类型的帖子）

💡 内容优化建议
（3条具体的文案改进建议）

⚠️ 风险提示
（有什么需要注意的问题）"""},
        ], temperature=0.7, max_tokens=1000)

        # 第二步：生成AI推荐时间表（JSON格式）
        top_model = model_rank[0][0] if model_rank else "T5 EVO"
        best_h    = int(best_hour) if best_hour != "未知" else 9

        schedule_prompt = f"""基于以下运营数据，生成下周最优定时发帖时间表。

数据摘要：
- 今日发帖最多的车型：{top_model}
- 发帖互动最好的时段：{best_hour}:00
- 各时段分布：{json.dumps(hour_data, ensure_ascii=False)}
- 车型分布：{json.dumps(s['models'], ensure_ascii=False)}
- 帖子类型分布：{json.dumps(s['post_type_dist'] if 'post_type_dist' in locals() else s.get('post_types',{}), ensure_ascii=False)}

可用车型：T5 EVO, FRIDAY, V9, P6, P8
可用帖子类型：product_intro（产品介绍）, price_value（价格优势）, lifestyle（生活方式）, feature_spotlight（功能聚焦）, new_arrival（新车到货）
可用发帖方式：text（纯文字）, image（图文）, video（视频）
可用语言：French, English, Arabic
可用市场：Senegal, Algeria

请生成5条最优定时任务配置，严格按照以下JSON格式输出，不要有任何其他文字：
[
  {{
    "model": "车型名",
    "market": "市场",
    "language": "语言",
    "post_type": "帖子类型ID",
    "post_mode": "发帖方式",
    "hour": 小时数字,
    "minute": 分钟数字,
    "days": "mon,wed,fri",
    "reason": "推荐理由（一句话）"
  }}
]

注意：
- hour必须是互动率高的时段（9、13、20、21点）
- 热门车型多安排几次
- 互动好的帖子类型优先
- 只输出JSON数组，不要其他内容"""

        schedule_raw = call_deepseek([
            {"role": "system", "content": "你是JSON生成专家，只输出合法的JSON，不输出任何其他内容。"},
            {"role": "user",   "content": schedule_prompt},
        ], temperature=0.3, max_tokens=800)

        # 清理并解析JSON
        import re
        json_match = re.search(r'\[.*\]', schedule_raw, re.DOTALL)
        if json_match:
            ai_schedule_json = json.loads(json_match.group())
        else:
            ai_schedule_json = []

    except Exception as e:
        ai_advice = f"AI建议生成失败：{str(e)}"
        ai_schedule_json = []

    return {
        "date":           today,
        "overview": {
            "total_posts":    s["posts"],
            "success":        s["success"],
            "failed":         s["failed"],
            "success_rate":   f"{round(s['success']/max(s['posts'],1)*100)}%",
            "weekly_avg":     weekly_avg,
            "weekly_total":   weekly_total,
        },
        "model_ranking":   model_rank,
        "market_ranking":  market_rank,
        "post_type_dist":  s.get("post_types", {}),
        "language_dist":   s.get("languages", {}),
        "best_hour":       best_hour,
        "hour_dist":       hour_data,
        "ai_analysis":     ai_advice,
        "ai_schedule":     ai_schedule_json,
        "recent_posts":    post_log[-20:],
    }

def run_daily_report():
    print("[定时任务] 生成日报...")
    try:
        report_data = generate_detailed_report()
        # 发简要日报到Facebook
        summary = f"""📊 China Auto AI 今日运营日报
━━━━━━━━━━━━━━━
📅 日期：{report_data['date']}
✅ 发布成功：{report_data['overview']['success']} 条
📈 成功率：{report_data['overview']['success_rate']}
🏆 最热车型：{report_data['model_ranking'][0][0] if report_data['model_ranking'] else 'N/A'}
⏰ 最佳时段：{report_data['best_hour']}:00
━━━━━━━━━━━━━━━
China Auto AI v3.0"""
        post_to_facebook(summary)
        print("[定时任务] ✅ 日报发布成功")
    except Exception as e:
        print(f"[定时任务] ❌ 日报错误: {e}")

scheduler.start()

# ══════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════
class PostRequest(BaseModel):
    model:     str = "T5 EVO"
    market:    str = "Senegal"
    language:  str = "French"
    post_type: str = "product_intro"
    whatsapp:  str = "+86 134 3393 1311"

class FacebookPostRequest(BaseModel):
    message: str

class BulkPostRequest(BaseModel):
    items:        list
    whatsapp:     str  = "+86 134 3393 1311"
    auto_publish: bool = False

class ScheduleRequest(BaseModel):
    model:     str = "T5 EVO"
    market:    str = "Senegal"
    language:  str = "French"
    post_type: str = "product_intro"
    whatsapp:  str = "+86 134 3393 1311"
    hour:      int = 9
    minute:    int = 0
    days:      str = "mon,tue,wed,thu,fri,sat"
    post_mode: str = "text"    # text | image | video

class SettingsRequest(BaseModel):
    deepseek_api_key:    str = ""
    siliconflow_api_key: str = ""
    facebook_page_id:    str = ""
    facebook_page_token: str = ""
    kling_access_key:     str = ""
    kling_secret_key:     str = ""
    unsplash_access_key:  str = ""
    ai_model:            str = "deepseek-chat"
    whatsapp:            str = "+86 134 3393 1311"
    default_market:      str = "Senegal"
    default_language:    str = "French"

# ══════════════════════════════════════════════════════════════
# API 接口
# ══════════════════════════════════════════════════════════════
@app.get("/")
def root():
    return {
        "status": "运行中",
        "version": "3.0",
        "deepseek": bool(get_env("DEEPSEEK_API_KEY")),
        "facebook": bool(get_env("FACEBOOK_PAGE_TOKEN")),
        "siliconflow": bool(get_env("SILICONFLOW_API_KEY")),
        "total_posts_today": daily_stats.get(date.today().isoformat(), {}).get("success", 0),
        "total_posts_all_time": len(post_log),
        "active_schedules": len(scheduled_jobs),
    }

@app.get("/models")
def get_models():
    return {"models": [
        {"id": k, "full_name": v["full_name"],
         "type": v["type"], "price": v["price_usd"]}
        for k, v in VEHICLE_KB.items()
    ]}

@app.get("/post-types")
def get_post_types():
    return {"post_types": [
        {"id": k, "label": k.replace("_"," ").title()}
        for k in POST_TYPES
    ]}

# ── 文案生成 ──────────────────────────────────────────────────
@app.post("/generate-post")
def generate_post(data: PostRequest):
    try:
        prompt  = build_post_prompt(data.model, data.market,
                                    data.language, data.post_type, data.whatsapp)
        content = call_deepseek([
            {"role": "system", "content": "你是非洲市场汽车社交媒体营销专家。"},
            {"role": "user",   "content": prompt},
        ])
        return {"success": True, "content": content,
                "model": data.model, "post_type": data.post_type,
                "language": data.language, "market": data.market}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/publish-facebook")
def publish_facebook(data: FacebookPostRequest):
    try:
        result = post_to_facebook(data.message)
        print("FACEBOOK:", result)
        return {"success": True, "facebook_response": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── 批量发帖 ──────────────────────────────────────────────────
@app.post("/bulk-generate")
def bulk_generate(data: BulkPostRequest):
    results = []
    for item in data.items:
        try:
            prompt  = build_post_prompt(
                item.get("model","T5 EVO"), item.get("market","Senegal"),
                item.get("language","French"), item.get("post_type","product_intro"),
                data.whatsapp)
            content = call_deepseek([
                {"role":"system","content":"你是非洲市场汽车社交媒体营销专家。"},
                {"role":"user","content":prompt},
            ])
            fb_resp = None
            if data.auto_publish:
                fb_resp = post_to_facebook(content)
                log_post(item.get("model"), item.get("language"),
                         item.get("market"), item.get("post_type"),
                         content, fb_resp)
            results.append({
                "success": True, "model": item.get("model"),
                "content": content, "published": data.auto_publish,
                "fb_post_id": fb_resp.get("id") if fb_resp else None,
            })
        except Exception as e:
            results.append({"success":False,"model":item.get("model"),"error":str(e)})
    return {"results": results, "total": len(results),
            "published": sum(1 for r in results if r.get("published"))}

# ── 定时任务 ──────────────────────────────────────────────────
@app.post("/schedule/add")
def add_schedule(data: ScheduleRequest):
    job_id = f"{data.model}_{data.hour}_{data.minute}"
    scheduler.add_job(
        run_scheduled_post,
        trigger=CronTrigger(day_of_week=data.days,
                            hour=data.hour, minute=data.minute,
                            timezone=DAKAR_TZ),
        args=[data.model, data.market, data.language,
              data.post_type, data.whatsapp, data.post_mode],
        id=job_id, replace_existing=True,
    )
    scheduled_jobs[job_id] = {
        "model":data.model,"market":data.market,"language":data.language,
        "post_type":data.post_type,"time":f"{data.hour:02d}:{data.minute:02d}",
        "days":data.days,"post_mode":data.post_mode,
    }
    return {"success":True,"job_id":job_id}

@app.get("/schedule/list")
def list_schedules():
    return {"schedules":scheduled_jobs,"total":len(scheduled_jobs),
            "best_times":BEST_POST_TIMES}

@app.delete("/schedule/{job_id}")
def remove_schedule(job_id: str):
    if job_id in scheduled_jobs:
        try: scheduler.remove_job(job_id)
        except: pass
        del scheduled_jobs[job_id]
        return {"success":True}
    return {"success":False,"message":"任务不存在"}

@app.post("/schedule/setup-default")
def setup_default_schedule(whatsapp: str = "+86 134 3393 1311"):
    configs = [
        {"model":"T5 EVO", "hour":9,  "minute":0,  "post_type":"price_value",       "days":"mon,wed,fri"},
        {"model":"FRIDAY",  "hour":13, "minute":0,  "post_type":"lifestyle",          "days":"tue,thu"},
        {"model":"V9",      "hour":20, "minute":30, "post_type":"product_intro",      "days":"mon,wed"},
        {"model":"P6",      "hour":9,  "minute":0,  "post_type":"feature_spotlight",  "days":"tue,thu,sat"},
        {"model":"P8",      "hour":20, "minute":30, "post_type":"new_arrival",        "days":"fri,sat"},
    ]
    added = []
    for cfg in configs:
        req = ScheduleRequest(
            model=cfg["model"], market="Senegal", language="French",
            post_type=cfg["post_type"], whatsapp=whatsapp,
            hour=cfg["hour"], minute=cfg["minute"], days=cfg["days"])
        add_schedule(req)
        added.append(f"{cfg['model']}_{cfg['hour']}_{cfg['minute']}")
    scheduler.add_job(run_daily_report,
        CronTrigger(hour=23,minute=55,timezone=DAKAR_TZ),
        id="daily_report", replace_existing=True)
    return {"success":True,"jobs_added":added,
            "message":"已设置推荐时间表，09:00/13:00/20:30（达喀尔时间）自动发帖"}

# ── 日报 ──────────────────────────────────────────────────────
@app.get("/report/daily")
def get_daily_report(target_date: str = None):
    return generate_detailed_report(target_date)

@app.get("/report/all")
def get_all_stats():
    return {"total_posts":len(post_log),"daily_stats":daily_stats,"post_log":post_log}

# ── 图片提示词 ────────────────────────────────────────────────
@app.post("/generate-image-prompt")
def generate_image_prompt(model: str = "T5 EVO", style: str = "outdoor", market: str = "Senegal"):
    kb = VEHICLE_KB.get(model, VEHICLE_KB["T5 EVO"])
    try:
        prompt = call_deepseek([{"role":"user","content":
            f"生成一段专业的Midjourney图片提示词，用于{market}市场的{kb['full_name']}汽车广告。"
            f"风格：{style}，要求：写实商业摄影质量，4K超清，包含相机参数。"
            f"只输出提示词，不要其他内容。"}],
            temperature=0.9, max_tokens=300)
        return {"success":True,"image_prompt":prompt,"model":model}
    except Exception as e:
        return {"success":False,"error":str(e)}

@app.post("/generate-video-script")
def generate_video_script(data: PostRequest):
    kb = VEHICLE_KB.get(data.model, VEHICLE_KB["T5 EVO"])
    try:
        script = call_deepseek([
            {"role":"system","content":"你是专业的汽车品牌短视频脚本创作者。"},
            {"role":"user","content":
                f"为{kb['full_name']}写一个30秒短视频脚本，目标市场：{data.market}，语言：{data.language}。\n"
                f"格式：[0-3s] 开场/[3-10s] 痛点/[10-20s] 产品展示/[20-27s] 价格/[27-30s] CTA: {data.whatsapp}\n"
                f"每句台词不超过8个字，括号内写镜头说明。"},
        ], temperature=0.88, max_tokens=500)
        return {"success":True,"script":script,"model":data.model}
    except Exception as e:
        return {"success":False,"error":str(e)}

# ── 系统设置 ──────────────────────────────────────────────────
@app.get("/settings")
def get_settings():
    """获取当前设置（隐藏敏感信息后4位）"""
    def mask(val):
        if not val or len(val) < 8:
            return ""
        return val[:4] + "****" + val[-4:]
    return {
        "deepseek_api_key":    mask(get_env("DEEPSEEK_API_KEY")),
        "siliconflow_api_key": mask(get_env("SILICONFLOW_API_KEY")),
        "facebook_page_id":    get_env("FACEBOOK_PAGE_ID"),
        "facebook_page_token": mask(get_env("FACEBOOK_PAGE_TOKEN")),
        "kling_access_key":    mask(get_env("KLING_ACCESS_KEY")),
        "kling_secret_key":    mask(get_env("KLING_SECRET_KEY")),
        "kling_available":      bool(get_env("KLING_ACCESS_KEY") and get_env("KLING_SECRET_KEY")),
        "unsplash_access_key":  mask(get_env("UNSPLASH_ACCESS_KEY")),
        "unsplash_configured":  bool(get_env("UNSPLASH_ACCESS_KEY")),
        "ai_model":            get_env("AI_MODEL", "deepseek-chat"),
        "whatsapp":            get_env("WHATSAPP_NUMBER", "+86 134 3393 1311"),
        "default_market":      get_env("DEFAULT_MARKET", "Senegal"),
        "default_language":    get_env("DEFAULT_LANGUAGE", "French"),
        "available_models": [
            {"id":"deepseek-chat",       "label":"DeepSeek Chat（推荐）"},
            {"id":"deepseek-reasoner",   "label":"DeepSeek Reasoner（高质量）"},
            {"id":"Qwen/Qwen2.5-72B-Instruct","label":"通义千问 72B"},
            {"id":"THUDM/glm-4-9b-chat", "label":"GLM-4 9B（免费）"},
        ],
    }

@app.post("/settings")
def update_settings(data: SettingsRequest):
    """更新设置，写入.env文件"""
    env_path = ".env"
    updates = {
        "DEEPSEEK_API_KEY":    data.deepseek_api_key,
        "SILICONFLOW_API_KEY": data.siliconflow_api_key,
        "FACEBOOK_PAGE_ID":    data.facebook_page_id,
        "FACEBOOK_PAGE_TOKEN": data.facebook_page_token,
        "KLING_ACCESS_KEY":    data.kling_access_key,
        "KLING_SECRET_KEY":    data.kling_secret_key,
        "UNSPLASH_ACCESS_KEY": data.unsplash_access_key,
        "AI_MODEL":            data.ai_model,
        "WHATSAPP_NUMBER":     data.whatsapp,
        "DEFAULT_MARKET":      data.default_market,
        "DEFAULT_LANGUAGE":    data.default_language,
    }
    try:
        for key, val in updates.items():
            if val:  # 只更新非空值
                set_key(env_path, key, val)
                os.environ[key] = val  # 同时更新当前进程环境变量
        return {"success": True, "message": "设置已保存，部分设置需要重启后端生效"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── AI推荐时间表应用 ──────────────────────────────────────────
class AiScheduleApplyRequest(BaseModel):
    schedules: list
    whatsapp:  str = "+86 134 3393 1311"

@app.post("/schedule/apply-ai")
def apply_ai_schedule(data: AiScheduleApplyRequest):
    """一键应用AI推荐的定时时间表（先清空现有，再批量添加）"""
    # 清空现有任务
    for job_id in list(scheduled_jobs.keys()):
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    scheduled_jobs.clear()

    added = []
    errors = []
    for item in data.schedules:
        try:
            req = ScheduleRequest(
                model     = item.get("model",     "T5 EVO"),
                market    = item.get("market",    "Senegal"),
                language  = item.get("language",  "French"),
                post_type = item.get("post_type", "product_intro"),
                post_mode = item.get("post_mode", "image"),
                whatsapp  = data.whatsapp,
                hour      = int(item.get("hour",   9)),
                minute    = int(item.get("minute", 0)),
                days      = item.get("days", "mon,wed,fri"),
            )
            add_schedule(req)
            added.append(f"{item.get('model')} {item.get('hour')}:{str(item.get('minute','0')).zfill(2)}")
        except Exception as e:
            errors.append(str(e))

    return {
        "success": len(added) > 0,
        "added":   added,
        "errors":  errors,
        "total":   len(added),
        "message": f"已应用AI推荐时间表，共添加 {len(added)} 条定时任务",
    }

# ── 车型管理 ──────────────────────────────────────────────────
@app.get("/vehicles")
def get_vehicles():
    """返回所有车型详细信息"""
    return {"vehicles": [
        {
            "id":           k,
            "full_name":    v["full_name"],
            "type":         v["type"],
            "engine":       v.get("engine", "-"),
            "transmission": v.get("transmission", "-"),
            "seats":        v.get("seats", 5),
            "price_usd":    v["price_usd"],
            "usp":          v["usp"],
            "target_audience": v["target_audience"],
            "features":     v["key_features"],
            "hashtag_count": len(v["hashtags"]),
            "markets":      ["Senegal", "Algeria", "West Africa"],
        }
        for k, v in VEHICLE_KB.items()
    ]}

# 注册图片路由
from image_post    import router as image_router
from video_post    import router as video_router
from image_library import router as library_router
app.include_router(image_router)
app.include_router(video_router)
app.include_router(library_router)
# ── MWM 实验模块 ──────────────────────────────────────────
from experiment import router as experiment_router, init_db as init_experiment_db
from scheduler import start_scheduler
app.include_router(experiment_router)

@app.on_event("startup")
def _mwm_startup():
    try:
        init_experiment_db()
        start_scheduler()
    except Exception as e:
        print("MWM startup failed:", e)
