# image_library.py
# D:\AI\ChinaAutoAI\backend\image_library.py
#
# 图片来源优先级：
# 1. 本地上传图片（car_images/<MODEL>/）
# 2. Unsplash API（免费，无版权）
# 3. 硅基流动AI生成（最后备用）

import os, io, random, base64, requests, shutil
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

# ── 配置 ────────────────────────────────────────────────────
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

# 本地图片库根目录（相对于 main.py 所在目录）
CAR_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "car_images")

# Unsplash 搜索关键词（按车型）
UNSPLASH_QUERIES = {
    "T5 EVO":  ["silver SUV car road", "compact SUV city", "modern SUV driving"],
    "FRIDAY":  ["electric car city", "electric MPV", "EV family car"],
    "V9":      ["luxury MPV black", "executive van night", "business MPV"],
    "P6":      ["sporty sedan white", "fastback car coast", "sport sedan road"],
    "P8":      ["flagship SUV mountain", "luxury SUV dark", "premium SUV fog"],
}

# 支持的图片格式
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ══════════════════════════════════════════════════════════════
# 本地图片库操作
# ══════════════════════════════════════════════════════════════
def get_model_dir(model: str) -> str:
    """获取车型图片目录，不存在则创建"""
    model_key = model.replace(" ", "").upper().replace("EVO", "EVO")
    # 特殊映射
    mapping = {
        "T5EVO": "T5EVO",
        "FRIDAY": "FRIDAY",
        "V9": "V9",
        "P6": "P6",
        "P8": "P8",
    }
    folder = mapping.get(model_key, model_key)
    path = os.path.join(CAR_IMAGES_DIR, folder)
    os.makedirs(path, exist_ok=True)
    return path

def get_local_images(model: str) -> list:
    """获取本地图片路径列表"""
    model_dir = get_model_dir(model)
    images = []
    for f in sorted(os.listdir(model_dir)):
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            images.append(os.path.join(model_dir, f))
    return images

def read_image_bytes(path: str, size: tuple = (1088, 1088)) -> bytes:
    """读取并resize图片"""
    img = Image.open(path).convert("RGB").resize(size)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()

def get_local_image_bytes(model: str, index: int = None) -> bytes:
    """
    从本地库获取图片bytes
    index=None时随机选取
    """
    images = get_local_images(model)
    if not images:
        raise FileNotFoundError(f"本地图片库为空: {model}")
    if index is None:
        path = random.choice(images)
    else:
        path = images[index % len(images)]
    return read_image_bytes(path)

def get_local_image_sequence(model: str, count: int = 3) -> list:
    """
    获取一组本地图片（用于视频帧）
    尽量选不重复的图，数量不足时循环使用
    """
    images = get_local_images(model)
    if not images:
        raise FileNotFoundError(f"本地图片库为空: {model}")

    if len(images) >= count:
        selected = random.sample(images, count)
    else:
        selected = (images * (count // len(images) + 1))[:count]
        random.shuffle(selected)

    results = []
    for p in selected:
        try:
            results.append(read_image_bytes(p))
        except Exception as e:
            print(f"[图片库] 读取失败 {p}: {e}")
    if not results:
        raise Exception(f"图片读取全部失败: {model}")
    return results

def count_local_images(model: str) -> int:
    return len(get_local_images(model))

# ══════════════════════════════════════════════════════════════
# Unsplash API
# ══════════════════════════════════════════════════════════════
def get_unsplash_image(model: str, index: int = 0) -> bytes:
    """
    从Unsplash获取高质量免版权图片
    需要在 .env 里设置 UNSPLASH_ACCESS_KEY
    """
    if not UNSPLASH_ACCESS_KEY:
        raise Exception("未配置 UNSPLASH_ACCESS_KEY，请在系统设置中填写")

    queries = UNSPLASH_QUERIES.get(model, ["luxury car road"])
    query   = queries[index % len(queries)]

    resp = requests.get(
        "https://api.unsplash.com/photos/random",
        params={
            "query":       query,
            "orientation": "squarish",
            "content_filter": "high",
        },
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        timeout=15,
    )

    if resp.status_code != 200:
        raise Exception(f"Unsplash API错误: {resp.status_code} {resp.text[:100]}")

    data     = resp.json()
    img_url  = data["urls"]["regular"]  # 1080px宽
    img_resp = requests.get(img_url, timeout=30)
    img      = Image.open(io.BytesIO(img_resp.content)).convert("RGB").resize((1088, 1088))
    out      = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()

def get_unsplash_sequence(model: str, count: int = 3) -> list:
    """获取多张Unsplash图片"""
    results = []
    for i in range(count):
        try:
            results.append(get_unsplash_image(model, index=i))
        except Exception as e:
            print(f"[Unsplash] 第{i+1}张失败: {e}")
    return results

# ══════════════════════════════════════════════════════════════
# 智能图片获取（优先级：本地 → Unsplash → 报错）
# ══════════════════════════════════════════════════════════════
def get_image_bytes(model: str, index: int = None) -> bytes:
    """单张图片，自动选择来源"""
    # 1. 优先本地
    local = get_local_images(model)
    if local:
        return get_local_image_bytes(model, index)

    # 2. Unsplash
    if UNSPLASH_ACCESS_KEY:
        return get_unsplash_image(model, index or 0)

    raise Exception(f"无可用图片：{model} 本地库为空且未配置Unsplash Key")

def get_image_sequence(model: str, count: int = 3) -> list:
    """
    获取多张图片序列（用于视频帧）
    优先级：本地 → Unsplash
    """
    # 1. 本地图片
    local_count = count_local_images(model)
    if local_count > 0:
        print(f"[图片库] {model}: 使用本地图片 ({local_count}张可用)")
        return get_local_image_sequence(model, count)

    # 2. Unsplash
    if UNSPLASH_ACCESS_KEY:
        print(f"[图片库] {model}: 本地无图，使用Unsplash")
        imgs = get_unsplash_sequence(model, count)
        if imgs:
            return imgs

    raise Exception(
        f"{model} 暂无图片：请上传图片到图片库，或在系统设置中配置 Unsplash API Key"
    )

# ══════════════════════════════════════════════════════════════
# API 接口
# ══════════════════════════════════════════════════════════════

@router.get("/library/status")
def library_status():
    """查看各车型图片库状态"""
    models = ["T5 EVO", "FRIDAY", "V9", "P6", "P8"]
    result = {}
    for m in models:
        local = get_local_images(m)
        result[m] = {
            "local_count":    len(local),
            "unsplash_ready": bool(UNSPLASH_ACCESS_KEY),
            "source":         "本地图片" if local else ("Unsplash" if UNSPLASH_ACCESS_KEY else "❌ 无图片源"),
            "thumbnails":     [],
        }
        # 返回前3张缩略图base64
        for p in local[:3]:
            try:
                img  = Image.open(p).convert("RGB").resize((120, 120))
                buf  = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                result[m]["thumbnails"].append(
                    f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
                )
            except Exception:
                pass
    return {"status": result, "unsplash_configured": bool(UNSPLASH_ACCESS_KEY)}

@router.post("/library/upload")
async def upload_images(
    model: str             = Form(...),
    files: list[UploadFile] = File(...),
):
    """上传图片到对应车型图片库"""
    model_dir = get_model_dir(model)
    existing  = len(get_local_images(model))
    saved     = []
    errors    = []

    for i, f in enumerate(files):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{f.filename}: 不支持的格式（仅支持jpg/png/webp）")
            continue
        try:
            content  = await f.read()
            # 验证是否是有效图片
            img = Image.open(io.BytesIO(content))
            img.verify()
            # 保存
            idx      = existing + i + 1
            filename = f"{idx:02d}_{os.path.splitext(f.filename)[0][:20]}{ext}"
            save_path = os.path.join(model_dir, filename)
            with open(save_path, 'wb') as out:
                out.write(content)
            saved.append(filename)
        except Exception as e:
            errors.append(f"{f.filename}: {str(e)}")

    return {
        "success":    len(saved) > 0,
        "saved":      saved,
        "errors":     errors,
        "total_now":  count_local_images(model),
        "message":    f"成功上传 {len(saved)} 张，{model} 图片库共 {count_local_images(model)} 张",
    }

@router.delete("/library/clear/{model}")
def clear_model_images(model: str):
    """清空某车型的本地图片库"""
    model_dir = get_model_dir(model)
    count = 0
    for f in os.listdir(model_dir):
        if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
            os.remove(os.path.join(model_dir, f))
            count += 1
    return {"success": True, "deleted": count, "message": f"已清空 {model} 的 {count} 张图片"}

@router.get("/library/preview/{model}")
def preview_library(model: str, count: int = 2):
    """预览图片库中的图片（返回小缩略图base64）"""
    try:
        local_imgs = get_local_images(model)
        if not local_imgs:
            if UNSPLASH_ACCESS_KEY:
                source = "Unsplash"
                # Unsplash只取1张预览，避免卡住
                img_bytes = get_unsplash_image(model, 0)
                img = Image.open(io.BytesIO(img_bytes)).resize((300, 300))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                return {"success": True, "source": source, "images": [{
                    "index": 0,
                    "b64": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
                }]}
            return {"success": False, "error": "暂无图片，请上传或配置Unsplash Key"}

        # 本地图片：直接读文件，不做1088resize（预览用小图就够）
        source   = "本地图片"
        selected = local_imgs[:min(count, len(local_imgs))]
        previews = []
        for i, p in enumerate(selected):
            try:
                img = Image.open(p).convert("RGB").resize((300, 300))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                previews.append({
                    "index": i,
                    "b64": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
                })
            except Exception as e:
                print(f"[preview] 读取失败 {p}: {e}")
        if not previews:
            return {"success": False, "error": "图片读取失败"}
        return {"success": True, "images": previews, "source": source}
    except Exception as e:
        return {"success": False, "error": str(e)}
