# video_post.py
# D:\AI\ChinaAutoAI\backend\video_post.py

import os, io, time, base64, requests, jwt, tempfile, wave, subprocess, asyncio
from image_library import get_image_sequence, get_image_bytes, count_local_images
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import imageio.v3 as iio
import imageio_ffmpeg

load_dotenv()
router = APIRouter()

KLING_ACCESS_KEY    = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY    = os.getenv("KLING_SECRET_KEY", "")
FACEBOOK_PAGE_ID    = os.getenv("FACEBOOK_PAGE_ID", "")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
print(f"[video_post] ffmpeg: {FFMPEG_PATH}")

# ══════════════════════════════════════════════════════════════
# 车型图片提示词（精准匹配车型）
# ══════════════════════════════════════════════════════════════
VEHICLE_PROMPTS = {
    "T5 EVO": [
        "silver grey compact SUV side view, modern Dakar street, golden hour, palm trees, photorealistic automotive photography, 4K",
        "silver SUV front three-quarter, African city boulevard, dramatic sky, professional car photography, 4K",
        "interior dashboard 12 inch touchscreen premium leather seats, modern luxury, 4K",
    ],
    "FRIDAY": [
        "electric MPV teal mint color side profile, clean African city road, blue sky, futuristic, photorealistic, 4K",
        "EV MPV rear three-quarter view, night city lights background, electric vehicle ad, 4K",
        "7-seat interior spacious cabin sliding door open, family lifestyle, bright lighting, 4K",
    ],
    "V9": [
        "black luxury MPV front three-quarter, grand hotel entrance Algiers night, red carpet, dramatic spotlights, photorealistic, 4K",
        "executive MPV interior captain seats massage, ambient lighting, business class luxury, 4K",
        "black MPV side view motion blur, luxury urban boulevard, cinematic, 4K",
    ],
    "P6": [
        "white fastback sedan sporty side profile, Mediterranean coastal road Algeria, blue ocean, cinematic, 4K",
        "sedan front view aggressive grille LED headlights, night urban wet road, dramatic, 4K",
        "interior sport cockpit digital instrument cluster steering wheel ambient lighting, 4K",
    ],
    "P8": [
        "dark grey flagship SUV front view, misty mountain road North Africa, fog, luxury cinematic, 4K",
        "SUV side profile panoramic sunroof, upscale neighborhood Algiers, golden hour, prestige, 4K",
        "interior dual 12.3 inch screens premium leather head-up display glow, executive luxury, 4K",
    ],
}

BGM_STYLE = {
    "T5 EVO": "modern",
    "FRIDAY": "upbeat",
    "V9":     "business",
    "P6":     "modern",
    "P8":     "business",
}

VEHICLE_COLORS = {
    "T5 EVO": (200, 134, 10),
    "FRIDAY": (0,   180, 200),
    "V9":     (220, 180, 60),
    "P6":     (255,  90,  0),
    "P8":     (160, 100, 220),
}

# ══════════════════════════════════════════════════════════════
# 生成BGM（纯Python合成）
# ══════════════════════════════════════════════════════════════
def _make_drum(sr, dur, beat_interval, freq=75, decay=6):
    """合成鼓点轨道"""
    n   = int(sr * dur)
    out = np.zeros(n)
    hit_len = int(0.09 * sr)
    for bt in np.arange(0, dur, beat_interval):
        s = int(bt * sr)
        e = min(s + hit_len, n)
        if s >= n: break
        tt  = np.linspace(0, 0.09, e - s)
        env = np.exp(-decay * tt / 0.09)
        out[s:e] += np.sin(2 * np.pi * freq * tt) * env
    return out

def _make_melody(sr, dur, notes, note_dur=0.25, decay=4):
    """合成简单旋律轨道"""
    n   = int(sr * dur)
    out = np.zeros(n)
    idx = 0
    while True:
        nt    = notes[idx % len(notes)]
        start = int(idx * note_dur * sr)
        end   = min(start + int(note_dur * sr * 0.75), n)
        if start >= n: break
        tt  = np.linspace(0, note_dur * 0.75, end - start)
        env = np.exp(-decay * tt / (note_dur * 0.75))
        out[start:end] += np.sin(2 * np.pi * nt * tt) * env * 0.3
        idx += 1
    return out

def _make_bass(sr, dur, root, beat_interval):
    """合成低音轨道"""
    n   = int(sr * dur)
    out = np.zeros(n)
    hit_len = int(0.18 * sr)
    for bt in np.arange(0, dur, beat_interval * 2):
        s = int(bt * sr)
        e = min(s + hit_len, n)
        if s >= n: break
        tt  = np.linspace(0, 0.18, e - s)
        env = np.exp(-3 * tt / 0.18)
        out[s:e] += np.sin(2 * np.pi * root * tt) * env * 0.5
    return out

def generate_bgm_wav(style: str, duration_sec: float = 15.0) -> bytes:
    """
    合成背景音乐
    modern   → 电子鼓点 + 现代旋律（C大调五声）
    upbeat   → 快节拍 + 活泼高音旋律
    business → 慢节拍 + 低沉庄重旋律
    """
    sr = 44100
    n  = int(sr * duration_sec)

    if style == "modern":
        # 电子感：四四拍每0.5s一鼓，C大调旋律
        drum   = _make_drum(sr, duration_sec, 0.5, freq=75, decay=8)
        melody = _make_melody(sr, duration_sec,
                              [261,293,329,392,440,392,329,293], 0.25)
        bass   = _make_bass(sr, duration_sec, 65, 0.5)
        audio  = drum * 0.55 + melody * 0.30 + bass * 0.15

    elif style == "upbeat":
        # 轻快：快节拍0.375s，高音旋律
        drum   = _make_drum(sr, duration_sec, 0.375, freq=90, decay=10)
        melody = _make_melody(sr, duration_sec,
                              [392,440,494,523,494,440,392,349], 0.1875)
        bass   = _make_bass(sr, duration_sec, 98, 0.375)
        audio  = drum * 0.45 + melody * 0.40 + bass * 0.15

    else:  # business
        # 商务：慢节拍0.75s，低沉旋律
        drum   = _make_drum(sr, duration_sec, 0.75, freq=55, decay=5)
        melody = _make_melody(sr, duration_sec,
                              [174,195,220,261,220,195,174,155], 0.375)
        bass   = _make_bass(sr, duration_sec, 43, 0.75)
        audio  = drum * 0.50 + melody * 0.25 + bass * 0.25

    # 淡入淡出
    fade = min(int(sr * 1.5), n // 4)
    audio[:fade]  *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)

    # 归一化
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.72

    pcm = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════
# 图片叠加文案
# ══════════════════════════════════════════════════════════════
def overlay_caption(img_bytes: bytes, caption: str, model: str,
                    frame_num: int = 0, total_frames: int = 1) -> bytes:
    import textwrap
    color = VEHICLE_COLORS.get(model, (200, 134, 10))
    dark  = (10, 15, 25)

    img  = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((1088, 1088))
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype("arial.ttf", 38)
        font_md = ImageFont.truetype("arial.ttf", 24)
        font_sm = ImageFont.truetype("arial.ttf", 18)
        font_bd = ImageFont.truetype("arialbd.ttf", 22)
    except Exception:
        font_lg = ImageFont.load_default()
        font_md = font_sm = font_bd = font_lg

    # 顶部品牌条
    draw.rectangle([(0,0),(1088,56)], fill=(*dark,))
    draw.rectangle([(0,54),(1088,57)], fill=color)
    draw.text((16, 12), "FORTHING · 东风柳州汽车", font=font_bd, fill=color)
    draw.text((16, 34), "Official Export Partner", font=font_sm, fill=(180,180,180))
    draw.rectangle([(1088-120,8),(1088-8,48)], fill=color)
    draw.text((1088-114, 14), model.upper(), font=font_sm, fill=(255,255,255))

    # 底部渐变
    overlay = Image.new("RGBA", (1088,1088), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    grad_h = 380
    for i in range(grad_h):
        alpha = int(200 * (i / grad_h))
        od.rectangle([(0, 1088-grad_h+i),(1088, 1088-grad_h+i+1)], fill=(*dark, alpha))
    img  = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 车型大标题
    draw.text((20, 660), model.upper(), font=font_lg, fill=color)
    draw.rectangle([(20,700),(180,703)], fill=color)

    # 文案正文
    lines_raw  = [l.strip() for l in caption.split("\n") if l.strip()]
    body_lines = [l for l in lines_raw if not l.startswith("#") and "WhatsApp" not in l]
    wrapped    = textwrap.wrap(" ".join(body_lines), width=42)[:4]
    y = 712
    for line in wrapped:
        draw.text((20, y), line, font=font_md, fill=(240,240,240))
        y += 30

    wa = next((l for l in lines_raw if "WhatsApp" in l or "+86" in l), "")
    if wa:
        draw.text((20, 1048), wa, font=font_sm, fill=(100,255,150))
    tags = next((l for l in lines_raw if l.startswith("#")), "")
    if tags:
        draw.text((20, 1066), " ".join(tags.split()[:5]), font=font_sm, fill=(*color,))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()

# ══════════════════════════════════════════════════════════════
# 图片序列 → MP4 + BGM
# ══════════════════════════════════════════════════════════════
def images_to_mp4(frames_bytes: list, bgm_wav: bytes,
                  fps: int = 24, sec_per_frame: int = 8) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")
        audio_path = os.path.join(tmpdir, "bgm.wav")
        final_path = os.path.join(tmpdir, "final.mp4")

        with open(audio_path, 'wb') as f:
            f.write(bgm_wav)

        all_frames = []
        for fb in frames_bytes:
            arr = np.array(Image.open(io.BytesIO(fb)).convert("RGB").resize((1088,1088)))
            for _ in range(fps * sec_per_frame):
                all_frames.append(arr)

        iio.imwrite(video_path, all_frames, fps=fps, codec="libx264",
                    pixelformat="yuv420p",
                    macro_block_size=16,
                    output_params=["-crf","20","-preset","medium","-b:v","1500k"])

        cmd = [FFMPEG_PATH, "-y",
               "-i", video_path, "-i", audio_path,
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
               "-shortest", "-movflags", "+faststart", final_path]
        result = subprocess.run(cmd, capture_output=True, timeout=120)

        target = final_path if result.returncode == 0 else video_path
        with open(target, 'rb') as f:
            return f.read()

# ══════════════════════════════════════════════════════════════
# 硅基流动 + 可灵
# ══════════════════════════════════════════════════════════════
def generate_sf_image(model: str, prompt_idx: int = 0) -> bytes:
    # 优先使用 Cloudinary 图片库
    try:
        from image_library import get_image_bytes, count_local_images
        if count_local_images(model) > 0:
            print(f"[video_post] {model}: 使用 Cloudinary 图片库")
            return get_image_bytes(model, prompt_idx)
    except Exception as e:
        print(f"[video_post] 图片库读取失败，降级AI生成: {e}")

    # 降级：硅基流动 AI 生成
    print(f"[video_post] {model}: 降级到 AI 生成图片")
    prompts = VEHICLE_PROMPTS.get(model, VEHICLE_PROMPTS["T5 EVO"])
    prompt  = prompts[prompt_idx % len(prompts)]
    resp = requests.post(
        "https://api.siliconflow.cn/v1/images/generations",
        headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": "Kwai-Kolors/Kolors", "prompt": prompt,
              "image_size": "1024x1024", "batch_size": 1,
              "negative_prompt": "blurry, text watermark, wrong car brand, distorted, cartoon"},
        timeout=120,
    )
    data = resp.json()
    if "images" in data and data["images"]:
        url = data["images"][0].get("url", "")
        if url:
            raw = requests.get(url, timeout=30).content
            img = Image.open(io.BytesIO(raw)).convert("RGB").resize((1088, 1088))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=92)
            return out.getvalue()
    raise Exception(f"硅基流动失败: {data}")

def get_kling_token() -> str:
    payload = {"iss": KLING_ACCESS_KEY,
               "exp": int(time.time()) + 1800,
               "nbf": int(time.time()) - 5}
    return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256")

def kling_available() -> bool:
    return bool(KLING_ACCESS_KEY and KLING_SECRET_KEY)

class KlingQuotaError(Exception):
    pass

def kling_image_to_video(image_bytes: bytes, prompt: str, duration: str = "5") -> str:
    token   = get_kling_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    img_b64 = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
    resp    = requests.post(
        "https://api.klingai.com/v1/videos/image2video", headers=headers,
        json={"model_name":"kling-v1","image":img_b64,"prompt":prompt,
              "duration":duration,"mode":"std","cfg_scale":0.5},
        timeout=30,
    )
    if resp.status_code == 402:
        raise KlingQuotaError("可灵API资源包余额不足，请前往 app.klingai.com 充值。")
    data = resp.json()
    if data.get("code") != 0:
        code = data.get("code", 0)
        if code in (1101, 1102):
            raise KlingQuotaError(f"可灵额度不足[{code}]")
        raise Exception(f"可灵错误[{code}]: {data.get('message', data)}")
    task_id = data["data"]["task_id"]
    for _ in range(60):
        time.sleep(5)
        pd = requests.get(
            f"https://api.klingai.com/v1/videos/image2video/{task_id}",
            headers={"Authorization": f"Bearer {get_kling_token()}"},
            timeout=15,
        ).json()
        status = pd.get("data", {}).get("task_status", "")
        if status == "succeed":
            return pd["data"]["task_result"]["videos"][0]["url"]
        elif status == "failed":
            raise Exception(f"可灵失败: {pd.get('data',{}).get('task_status_msg','未知')}")
    raise Exception("可灵超时（>5分钟）")

# ══════════════════════════════════════════════════════════════
# Facebook 发布
# ══════════════════════════════════════════════════════════════
def publish_photo_fb(img_bytes: bytes, caption: str) -> dict:
    upload = requests.post(
        f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/photos",
        data={"access_token": FACEBOOK_PAGE_TOKEN, "published": "false"},
        files={"source": ("car.jpg", img_bytes, "image/jpeg")}, timeout=60,
    ).json()
    if "id" not in upload:
        raise Exception(f"图片上传失败: {upload}")
    return requests.post(
        f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/feed",
        data={"message": caption,
              "attached_media[0]": f'{{"media_fbid":"{upload["id"]}"}}',
              "access_token": FACEBOOK_PAGE_TOKEN}, timeout=60,
    ).json()

def publish_video_fb(video_bytes: bytes, caption: str) -> dict:
    """上传MP4视频到Facebook并发布到Feed"""
    resp = requests.post(
        f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/videos",
        data={
            "description":  caption,
            "published":    "true",
            "no_story":     "false",
            "access_token": FACEBOOK_PAGE_TOKEN,
        },
        files={"source": ("video.mp4", video_bytes, "video/mp4")},
        timeout=300,
    )
    print(f"[Facebook Video] status={resp.status_code} resp={resp.text[:200]}")
    return resp.json()

def publish_video_url_fb(video_url: str, caption: str) -> dict:
    resp = requests.post(
        f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/videos",
        data={
            "file_url":     video_url,
            "description":  caption,
            "published":    "true",
            "no_story":     "false",
            "access_token": FACEBOOK_PAGE_TOKEN,
        },
        timeout=60,
    )
    print(f"[Facebook Video URL] status={resp.status_code} resp={resp.text[:200]}")
    return resp.json()

# ══════════════════════════════════════════════════════════════
# API 接口
# ══════════════════════════════════════════════════════════════
@router.get("/video/kling-available")
def check_kling():
    return {"available": kling_available(),
            "message": "可灵API已配置" if kling_available() else "未配置可灵Key，将使用本地MP4幻灯片"}

@router.post("/video/preview-images")
async def preview_images(
    model:      str              = Form("T5 EVO"),
    num_images: int              = Form(2),
    files:      list[UploadFile] = File(default=[]),
):
    """预览图片（含品牌叠加），用户确认后再发布视频"""
    try:
        raw_frames = [await f.read() for f in files]
        # 上传图片不足时，从图片库补充
        needed = max(0, num_images - len(raw_frames))
        if needed > 0:
            try:
                lib_imgs = get_image_sequence(model, needed)
                raw_frames.extend(lib_imgs)
                print(f"[preview] 从图片库获取 {len(lib_imgs)} 张")
            except Exception as e:
                print(f"[preview] 图片库获取失败: {e}")
                # 最后才用硅基流动
                for i in range(needed):
                    try:
                        if i > 0:
                            await asyncio.sleep(8)
                        raw_frames.append(generate_sf_image(model, prompt_idx=i))
                    except Exception as e2:
                        print(f"[preview] AI生成失败: {e2}")
        if not raw_frames:
            local_count = count_local_images(model)
            hint = "请先在「图片库」页面上传该车型图片" if local_count == 0 else "图片获取失败，请重试"
            return {"success": False, "error": hint}
        previews = []
        for i, fb in enumerate(raw_frames):
            styled = overlay_caption(fb, "", model, i, len(raw_frames))
            previews.append({
                "index": i,
                "b64": f"data:image/jpeg;base64,{base64.b64encode(styled).decode()}",
                "ai_generated": i >= len(files),
            })
        return {"success": True, "images": previews, "total": len(previews)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/video/generate-and-publish")
async def generate_and_publish_video(
    model:      str              = Form("T5 EVO"),
    caption:    str              = Form(""),
    use_kling:  str              = Form("false"),
    duration:   str              = Form("5"),
    num_images: int              = Form(3),
    files:      list[UploadFile] = File(default=[]),
):
    """生成MP4视频（含BGM）或可灵AI视频，发布到Facebook"""
    use_kling_bool = use_kling.lower() == "true"
    fallback_reason = None

    raw_frames = [await f.read() for f in files]
    needed = max(0, num_images - len(raw_frames))
    if needed > 0:
        try:
            lib_imgs = get_image_sequence(model, needed)
            raw_frames.extend(lib_imgs)
            print(f"[video] 从图片库获取 {len(lib_imgs)} 张")
        except Exception as e:
            print(f"[video] 图片库失败，尝试AI生成: {e}")
            for i in range(needed):
                try:
                    if i > 0:
                        await asyncio.sleep(8)
                    raw_frames.append(generate_sf_image(model, prompt_idx=i))
                except Exception as e2:
                    print(f"[video] AI生成失败: {e2}")

    if not raw_frames:
        local_count = count_local_images(model)
        hint = "请先在「图片库」页面上传该车型图片" if local_count == 0 else "图片获取失败，请重试"
        return {"success": False, "error": hint}

    # 可灵模式
    if use_kling_bool and kling_available():
        try:
            video_url = kling_image_to_video(
                raw_frames[0],
                prompt=f"Smooth cinematic car ad, {model}, dynamic motion, professional commercial",
                duration=duration,
            )
            fb_resp = publish_video_url_fb(video_url, caption)
            return {"success":True,"mode":"kling",
                    "fb_post_id":fb_resp.get("id",""),
                    "message":"✅ 可灵AI视频已发布到 Facebook！","warning":None}
        except KlingQuotaError as e:
            fallback_reason = str(e)
        except Exception as e:
            fallback_reason = f"可灵失败（{str(e)[:60]}），已切换到MP4"

    # 本地MP4幻灯片 + BGM
    try:
        styled_frames = [overlay_caption(fb, caption, model, i, len(raw_frames))
                         for i, fb in enumerate(raw_frames)]
        style    = BGM_STYLE.get(model, "modern")
        bgm      = generate_bgm_wav(style, len(styled_frames)*8 + 2.0)
        mp4      = images_to_mp4(styled_frames, bgm, fps=24, sec_per_frame=8)
        fb_resp  = publish_video_fb(mp4, caption)

        result = {
            "success":     True,
            "mode":        "mp4_slideshow",
            "frames":      len(styled_frames),
            "bgm_style":   style,
            "fb_post_id":  fb_resp.get("id",""),
            "message":     f"✅ MP4视频（{len(styled_frames)}帧+BGM）已发布！",
            "warning":     fallback_reason,
            "quota_alert": bool(fallback_reason and ("额度" in fallback_reason or "quota" in fallback_reason.lower())),
        }
        if fallback_reason:
            result["message"] = f"⚠️ 已切换MP4幻灯片模式发布（{len(styled_frames)}帧）"
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/video/preview-slideshow")
async def preview_slideshow(
    model:   str              = Form("T5 EVO"),
    caption: str              = Form(""),
    files:   list[UploadFile] = File(default=[]),
):
    """GIF预览（轻量，仅供查看效果，不发布）"""
    try:
        raw_frames = [await f.read() for f in files]
        if len(raw_frames) < 3:
            try:
                lib_imgs = get_image_sequence(model, 3 - len(raw_frames))
                raw_frames.extend(lib_imgs)
            except Exception:
                while len(raw_frames) < 3:
                    try:
                        if len(raw_frames) > 0:
                            await asyncio.sleep(8)
                        raw_frames.append(generate_sf_image(model, prompt_idx=len(raw_frames)))
                    except Exception:
                        break
        styled = [overlay_caption(fb, caption, model, i, len(raw_frames))
                  for i, fb in enumerate(raw_frames)]
        pil_frames = [Image.open(io.BytesIO(fb)).resize((544,544)) for fb in styled]
        out = io.BytesIO()
        pil_frames[0].save(out, format="GIF", save_all=True,
                           append_images=pil_frames[1:], duration=2000, loop=0)
        return {"success":True,"gif_b64":base64.b64encode(out.getvalue()).decode(),"frames":len(styled)}
    except Exception as e:
        return {"success": False, "error": str(e)}
