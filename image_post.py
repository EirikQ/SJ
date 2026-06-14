# image_post.py
# 把这个文件放到 D:\AI\ChinaAutoAI\backend\image_post.py
# 然后在 main.py 顶部加一行: from image_post import router as image_router
# 以及在 app 定义后加一行: app.include_router(image_router)

import os, io, requests, textwrap, base64
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

SILICONFLOW_API_KEY  = os.getenv("SILICONFLOW_API_KEY")
FACEBOOK_PAGE_ID     = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_TOKEN  = os.getenv("FACEBOOK_PAGE_TOKEN")

# ── 车型视觉风格映射 ─────────────────────────────────────────
VEHICLE_VISUALS = {
    "T5 EVO": {
        "prompt": "Forthing T5 EVO silver SUV parked on modern Dakar street, golden hour sunlight, African city background, palm trees, photorealistic, commercial automotive photography, Canon EOS R5, 35mm lens, 4K",
        "neg":    "cartoon, illustration, blurry, text, watermark, people blocking car",
        "color":  (200, 134, 10),   # 金色主题
        "bg":     (15, 25, 35),     # 深蓝底
    },
    "FRIDAY": {
        "prompt": "Forthing Friday electric MPV teal color on clean Dakar boulevard, modern African city, blue sky, futuristic mood, photorealistic, commercial photography, 4K ultra detailed",
        "neg":    "cartoon, blurry, text, watermark, dirty street",
        "color":  (0, 180, 200),
        "bg":     (5, 15, 25),
    },
    "V9": {
        "prompt": "Forthing V9 black luxury MPV at night outside luxury hotel Algiers, dramatic lighting, red carpet, polished marble, cinematic, photorealistic, 4K",
        "neg":    "cartoon, blurry, text, watermark, low quality",
        "color":  (220, 180, 60),
        "bg":     (10, 10, 15),
    },
    "P6": {
        "prompt": "Forthing P6 white sporty sedan on coastal road Algeria Mediterranean sea background, motion blur, cinematic wide angle, photorealistic, 4K",
        "neg":    "cartoon, blurry, text, watermark",
        "color":  (255, 90, 0),
        "bg":     (10, 20, 40),
    },
    "P8": {
        "prompt": "Forthing P8 dark flagship SUV on misty mountain road North Africa, dramatic fog, luxury mood, cinematic color grade, photorealistic, 4K",
        "neg":    "cartoon, blurry, text, watermark, low quality",
        "color":  (180, 120, 220),
        "bg":     (8, 8, 12),
    },
}

# ── 数据模型 ─────────────────────────────────────────────────
class ImagePostRequest(BaseModel):
    model:    str = "T5 EVO"
    caption:  str = ""          # AI生成的文案
    market:   str = "Senegal"
    language: str = "French"

# ── 1. 调用硅基流动生成图片 ──────────────────────────────────
def generate_image_sf(model: str) -> bytes:
    vis = VEHICLE_VISUALS.get(model, VEHICLE_VISUALS["T5 EVO"])
    resp = requests.post(
        "https://api.siliconflow.cn/v1/images/generations",
        headers={
            "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
            "Content-Type": "application/json",
        },
       json={
    "model":               "Kwai-Kolors/Kolors",
    "prompt":              vis["prompt"],
    "negative_prompt":     vis["neg"],
    "image_size":          "1024x1024",
    "num_inference_steps": 20,
    "guidance_scale":      7.5,
    "batch_size":          1,
},
        timeout=120,
    )
    data = resp.json()
    # 返回 base64 或 url
    if "images" in data and data["images"]:
        img_data = data["images"][0]
        if "url" in img_data:
            img_resp = requests.get(img_data["url"], timeout=30)
            return img_resp.content
        elif "b64_json" in img_data:
            return base64.b64decode(img_data["b64_json"])
    raise Exception(f"SiliconFlow error: {data}")

# ── 2. 文字叠加到图片 ────────────────────────────────────────
def overlay_text(img_bytes: bytes, caption: str, model: str) -> bytes:
    vis   = VEHICLE_VISUALS.get(model, VEHICLE_VISUALS["T5 EVO"])
    gold  = vis["color"]
    dark  = vis["bg"]

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    W, H = img.size  # 1024x1024

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # 底部渐变遮罩（纯色半透明）
    grad_h = int(H * 0.45)
    for i in range(grad_h):
        alpha = int(210 * (i / grad_h))
        draw.rectangle(
            [(0, H - grad_h + i), (W, H - grad_h + i + 1)],
            fill=(*dark, alpha),
        )

    # 顶部品牌条
    draw.rectangle([(0, 0), (W, 52)], fill=(*dark, 210))
    draw.rectangle([(0, 50), (W, 53)], fill=(*gold, 255))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 尝试加载字体，失败用默认
    try:
        font_title  = ImageFont.truetype("arial.ttf", 36)
        font_body   = ImageFont.truetype("arial.ttf", 22)
        font_brand  = ImageFont.truetype("arialbd.ttf", 20)
        font_small  = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_title  = ImageFont.load_default()
        font_body   = font_title
        font_brand  = font_title
        font_small  = font_title

    # 品牌名（顶部）
    draw.text((18, 14), "FORTHING · 东风柳州  |  China Auto", 
              font=font_brand, fill=(*gold, 255))

    # 文案分行处理
    lines_raw = caption.split("\n")
    # 找hashtag行（最后一行以#开头）
    hashtag_line = ""
    text_lines   = []
    for line in lines_raw:
        stripped = line.strip()
        if stripped.startswith("#"):
            hashtag_line = stripped
        elif stripped:
            text_lines.append(stripped)

    # 合并正文，每行最多30字符
    full_text = " ".join(text_lines)
    wrapped   = textwrap.wrap(full_text, width=38)[:5]  # 最多5行

    # 从底部往上画文字
    bottom_pad = 70
    line_h     = 32

    # WhatsApp行
    wa_line = next((l for l in text_lines if "WhatsApp" in l or "+86" in l), "")
    if wa_line:
        draw.text((18, H - bottom_pad),
                  wa_line, font=font_small,
                  fill=(100, 255, 150, 255))
        bottom_pad += line_h

    # hashtag
    if hashtag_line:
        tags_short = " ".join(hashtag_line.split()[:5])
        draw.text((18, H - bottom_pad),
                  tags_short, font=font_small,
                  fill=(*gold, 200))
        bottom_pad += line_h + 4

    # 正文从下往上
    for line in reversed(wrapped):
        draw.text((18, H - bottom_pad),
                  line, font=font_body,
                  fill=(255, 255, 255, 245))
        bottom_pad += line_h

    # 金色分割线
    draw.rectangle(
        [(18, H - bottom_pad - 4), (W - 18, H - bottom_pad - 2)],
        fill=(*gold, 180),
    )

    # 车型名称（大标题）
    draw.text((18, H - bottom_pad - 52),
              model.upper(), font=font_title,
              fill=(*gold, 255))

    # 转回 bytes
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=92)
    return out.getvalue()

# ── 3. 上传图片到 Facebook 并发帖 ───────────────────────────
def publish_photo_to_facebook(img_bytes: bytes, caption: str) -> dict:
    # Step 1: 上传图片（不立即发布）
    upload_url = f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/photos"
    upload_resp = requests.post(
        upload_url,
        data={"access_token": FACEBOOK_PAGE_TOKEN, "published": "false"},
        files={"source": ("car.jpg", img_bytes, "image/jpeg")},
        timeout=60,
    )
    upload_data = upload_resp.json()
    if "id" not in upload_data:
        raise Exception(f"Photo upload failed: {upload_data}")
    photo_id = upload_data["id"]

    # Step 2: 发布帖子附带图片
    post_url  = f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/feed"
    post_resp = requests.post(
        post_url,
        data={
            "message":         caption,
            "attached_media[0]": f'{{"media_fbid":"{photo_id}"}}',
            "access_token":    FACEBOOK_PAGE_TOKEN,
        },
        timeout=60,
    )
    return post_resp.json()

# ═══════════════════════════════════════════════════════════════
# API 接口
# ═══════════════════════════════════════════════════════════════

@router.post("/generate-image")
def generate_image(data: ImagePostRequest):
    """只生成图片，返回 base64 预览"""
    try:
        img_bytes = generate_image_sf(data.model)
        if data.caption:
            img_bytes = overlay_text(img_bytes, data.caption, data.model)
        b64 = base64.b64encode(img_bytes).decode()
        return {"success": True, "image_b64": b64,
                "format": "jpeg", "model": data.model}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/publish-image-post")
def publish_image_post(data: ImagePostRequest):
    """生成图片 + 叠加文案 + 一键发布到 Facebook"""
    try:
        # 1. 生成图片
        img_bytes = generate_image_sf(data.model)
        # 2. 叠加文案
        img_bytes = overlay_text(img_bytes, data.caption, data.model)
        # 3. 发布
        fb_resp = publish_photo_to_facebook(img_bytes, data.caption)
        if "id" in fb_resp:
            return {"success": True, "fb_post_id": fb_resp["id"],
                    "message": "图文帖子已成功发布到 Facebook！"}
        else:
            return {"success": False, "error": fb_resp}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/preview-image-post")
def preview_image_post(data: ImagePostRequest):
    """生成图片预览（含文案叠加），不发布"""
    try:
        img_bytes = generate_image_sf(data.model)
        img_bytes = overlay_text(img_bytes, data.caption, data.model)
        b64 = base64.b64encode(img_bytes).decode()
        return {"success": True, "image_b64": b64}
    except Exception as e:
        return {"success": False, "error": str(e)}
