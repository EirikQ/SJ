# image_library.py — Cloudinary 云存储版
# 图片永久存储在 Cloudinary，Railway 重新部署不丢失
# 图片来源优先级：Cloudinary云库 → Unsplash → 报错

import os, io, random, base64, requests
from fastapi import APIRouter, UploadFile, File, Form
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

# ── 配置 ─────────────────────────────────────────────────────
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY    = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
UNSPLASH_ACCESS_KEY   = os.getenv("UNSPLASH_ACCESS_KEY", "")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

UNSPLASH_QUERIES = {
    "T5 EVO":  ["silver SUV car road", "compact SUV city", "modern SUV driving"],
    "FRIDAY":  ["electric car city", "electric MPV", "EV family car"],
    "V9":      ["luxury MPV black", "executive van night", "business MPV"],
    "P6":      ["sporty sedan white", "fastback car coast", "sport sedan road"],
    "P8":      ["flagship SUV mountain", "luxury SUV dark", "premium SUV fog"],
}

# Cloudinary 文件夹前缀
FOLDER = "forthing_cars"


# ══════════════════════════════════════════════════════════════
# Cloudinary 工具函数
# ══════════════════════════════════════════════════════════════
def _cloudinary_configured() -> bool:
    return bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)


def _model_folder(model: str) -> str:
    """把车型名转为 Cloudinary 文件夹路径"""
    key = model.replace(" ", "_").upper()
    return f"{FOLDER}/{key}"


def _upload_to_cloudinary(image_bytes: bytes, model: str, filename: str) -> dict:
    """上传图片到 Cloudinary，返回 {url, public_id}"""
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
    )
    folder = _model_folder(model)
    # public_id 去掉扩展名
    pub_id = f"{folder}/{os.path.splitext(filename)[0]}"
    result = cloudinary.uploader.upload(
        image_bytes,
        public_id=pub_id,
        overwrite=False,
        resource_type="image",
        transformation=[{"width": 1088, "height": 1088, "crop": "fill", "quality": "auto"}],
    )
    return {"url": result["secure_url"], "public_id": result["public_id"]}


def _list_cloudinary_images(model: str) -> list:
    """列出某车型在 Cloudinary 的所有图片 URL"""
    if not _cloudinary_configured():
        return []
    try:
        import cloudinary
        import cloudinary.api
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
        )
        folder = _model_folder(model)
        result = cloudinary.api.resources(
            type="upload",
            prefix=folder,
            max_results=50,
        )
        return [r["secure_url"] for r in result.get("resources", [])]
    except Exception as e:
        print(f"[Cloudinary] 列出图片失败 {model}: {e}")
        return []


def _delete_cloudinary_folder(model: str) -> int:
    """清空某车型的 Cloudinary 图片"""
    if not _cloudinary_configured():
        return 0
    try:
        import cloudinary
        import cloudinary.api
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
        )
        folder = _model_folder(model)
        result = cloudinary.api.resources(type="upload", prefix=folder, max_results=100)
        ids = [r["public_id"] for r in result.get("resources", [])]
        if ids:
            cloudinary.api.delete_resources(ids)
        return len(ids)
    except Exception as e:
        print(f"[Cloudinary] 清空失败 {model}: {e}")
        return 0


def _url_to_bytes(url: str, size: tuple = (1088, 1088)) -> bytes:
    """从 URL 下载图片并 resize"""
    resp = requests.get(url, timeout=30)
    img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize(size)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()


# ══════════════════════════════════════════════════════════════
# 智能图片获取（优先 Cloudinary → Unsplash）
# ══════════════════════════════════════════════════════════════
def get_image_bytes(model: str, index: int = None) -> bytes:
    """获取单张图片"""
    urls = _list_cloudinary_images(model)
    if urls:
        url = random.choice(urls) if index is None else urls[index % len(urls)]
        return _url_to_bytes(url)
    if UNSPLASH_ACCESS_KEY:
        return _get_unsplash_image(model, index or 0)
    raise Exception(f"无可用图片：{model} 云库为空且未配置 Unsplash Key")


def get_image_sequence(model: str, count: int = 3) -> list:
    """获取多张图片（用于视频帧）"""
    urls = _list_cloudinary_images(model)
    if urls:
        print(f"[图片库] {model}: Cloudinary {len(urls)}张")
        selected = random.sample(urls, min(count, len(urls)))
        if len(selected) < count:
            selected = (selected * (count // len(selected) + 1))[:count]
        results = []
        for url in selected:
            try:
                results.append(_url_to_bytes(url))
            except Exception as e:
                print(f"[图片库] 下载失败 {url}: {e}")
        if results:
            return results

    if UNSPLASH_ACCESS_KEY:
        print(f"[图片库] {model}: 使用 Unsplash")
        return _get_unsplash_sequence(model, count)

    raise Exception(f"{model} 暂无图片：请上传图片到图片库")


# 兼容旧调用
def get_local_image_bytes(model: str, index: int = None) -> bytes:
    return get_image_bytes(model, index)

def get_local_image_sequence(model: str, count: int = 3) -> list:
    return get_image_sequence(model, count)

def count_local_images(model: str) -> int:
    return len(_list_cloudinary_images(model))


# ══════════════════════════════════════════════════════════════
# Unsplash 备用
# ══════════════════════════════════════════════════════════════
def _get_unsplash_image(model: str, index: int = 0) -> bytes:
    if not UNSPLASH_ACCESS_KEY:
        raise Exception("未配置 UNSPLASH_ACCESS_KEY")
    queries = UNSPLASH_QUERIES.get(model, ["luxury car road"])
    query = queries[index % len(queries)]
    resp = requests.get("https://api.unsplash.com/photos/random",
        params={"query": query, "orientation": "squarish", "content_filter": "high"},
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Unsplash错误: {resp.status_code}")
    img_url = resp.json()["urls"]["regular"]
    return _url_to_bytes(img_url)


def _get_unsplash_sequence(model: str, count: int = 3) -> list:
    results = []
    for i in range(count):
        try:
            results.append(_get_unsplash_image(model, index=i))
        except Exception as e:
            print(f"[Unsplash] 第{i+1}张失败: {e}")
    return results


# ══════════════════════════════════════════════════════════════
# API 接口
# ══════════════════════════════════════════════════════════════
@router.get("/library/status")
def library_status():
    models = ["T5 EVO", "FRIDAY", "V9", "P6", "P8"]
    result = {}
    for m in models:
        urls = _list_cloudinary_images(m)
        count = len(urls)
        source = "Cloudinary ☁️" if count > 0 else ("Unsplash" if UNSPLASH_ACCESS_KEY else "❌ 无图片源")
        thumbnails = []
        for url in urls[:3]:
            try:
                resp = requests.get(url, timeout=10)
                img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((120, 120))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                thumbnails.append(f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}")
            except:
                pass
        result[m] = {
            "local_count": count,
            "unsplash_ready": bool(UNSPLASH_ACCESS_KEY),
            "source": source,
            "thumbnails": thumbnails,
        }
    return {
        "status": result,
        "cloudinary_configured": _cloudinary_configured(),
        "unsplash_configured": bool(UNSPLASH_ACCESS_KEY),
    }


@router.post("/library/upload")
async def upload_images(
    model: str              = Form(...),
    files: list[UploadFile] = File(...),
):
    if not _cloudinary_configured():
        return {"success": False, "errors": ["未配置 Cloudinary，请检查环境变量"],
                "saved": [], "total_now": 0}

    saved, errors = [], []
    existing_count = count_local_images(model)

    for i, f in enumerate(files):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{f.filename}: 不支持的格式（仅 jpg/png/webp）")
            continue
        try:
            content = await f.read()
            # 验证图片有效性
            Image.open(io.BytesIO(content)).verify()
            # 重新读取（verify 会关闭文件）
            content = await f.read() if len(content) == 0 else content
            idx = existing_count + i + 1
            filename = f"{idx:02d}_{os.path.splitext(f.filename)[0][:20]}{ext}"
            r = _upload_to_cloudinary(content, model, filename)
            saved.append(r["url"])
        except Exception as e:
            errors.append(f"{f.filename}: {str(e)}")

    total = count_local_images(model)
    return {
        "success": len(saved) > 0,
        "saved": saved,
        "errors": errors,
        "total_now": total,
        "message": f"成功上传 {len(saved)} 张到 Cloudinary，{model} 共 {total} 张",
    }


@router.delete("/library/clear/{model}")
def clear_model_images(model: str):
    count = _delete_cloudinary_folder(model)
    return {"success": True, "deleted": count, "message": f"已从 Cloudinary 清空 {model} 的 {count} 张图片"}


@router.get("/library/preview/{model}")
def preview_library(model: str, count: int = 2):
    try:
        urls = _list_cloudinary_images(model)
        if urls:
            previews = []
            for i, url in enumerate(urls[:count]):
                try:
                    resp = requests.get(url, timeout=15)
                    img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((300, 300))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    previews.append({
                        "index": i,
                        "b64": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}",
                        "ai_generated": False,
                    })
                except Exception as e:
                    print(f"[preview] 下载失败: {e}")
            if previews:
                return {"success": True, "images": previews, "source": "Cloudinary ☁️"}

        if UNSPLASH_ACCESS_KEY:
            img_bytes = _get_unsplash_image(model, 0)
            img = Image.open(io.BytesIO(img_bytes)).resize((300, 300))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            return {"success": True, "source": "Unsplash", "images": [{
                "index": 0,
                "b64": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}",
                "ai_generated": False,
            }]}
        return {"success": False, "error": "暂无图片，请上传图片到图片库"}
    except Exception as e:
        return {"success": False, "error": str(e)}
