"""百度云 OCR 封装 — 手写文字识别（在线 API，无需本地模型）。"""

from __future__ import annotations

import base64
import io
import os

import requests
from dotenv import load_dotenv
from loguru import logger
from PIL import Image

from . import OcrLine

load_dotenv()

_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting"
_MAX_BASE64_SIZE = 3 * 1024 * 1024  # 百度 API 限制 4MB，留余量取 3MB

_cached_token: str | None = None


def _get_access_token() -> str:
    """通过 client_id + client_secret 获取百度 API access_token。"""
    global _cached_token
    if _cached_token:
        return _cached_token

    client_id = os.getenv("BAIDU_OCR_API_KEY", "")
    client_secret = os.getenv("BAIDU_OCR_SECRET_KEY", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "BAIDU_OCR_API_KEY 或 BAIDU_OCR_SECRET_KEY 未配置，请在 .env 文件中设置"
        )

    resp = requests.post(
        _TOKEN_URL,
        params={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        raise RuntimeError(f"获取百度 access_token 失败: {data}")

    _cached_token = data["access_token"]
    logger.info("百度 OCR access_token 获取成功")
    return _cached_token


def _compress_image(image_bytes: bytes) -> bytes:
    """将图片压缩到百度 API 可接受的大小（base64 后 < 3MB）。"""
    img = Image.open(io.BytesIO(image_bytes))

    # 如果原图 base64 已经够小，直接返回
    if len(base64.b64encode(image_bytes)) <= _MAX_BASE64_SIZE:
        return image_bytes

    logger.info("图片过大 ({:.1f}MB)，正在压缩…", len(image_bytes) / 1024 / 1024)

    # 先缩小分辨率：长边不超过 2000px
    max_side = 2000
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # 逐步降低 JPEG 质量直到满足大小限制
    for quality in (85, 70, 55, 40):
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(base64.b64encode(data)) <= _MAX_BASE64_SIZE:
            logger.info("压缩完成: quality={} size={:.1f}KB", quality, len(data) / 1024)
            return data

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=30)
    return buf.getvalue()


def ocr_image(image_bytes: bytes) -> list[OcrLine]:
    """调用百度手写文字识别 API，返回 OcrLine 列表。"""
    token = _get_access_token()
    compressed = _compress_image(image_bytes)
    img_b64 = base64.b64encode(compressed).decode("utf-8")

    resp = requests.post(
        _OCR_URL,
        params={"access_token": token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"image": img_b64, "recognize_granularity": "big"},
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()

    if "error_code" in result:
        raise RuntimeError(
            f"百度 OCR 错误 [{result['error_code']}]: {result.get('error_msg', '')}"
        )

    words_result = result.get("words_result", [])
    lines: list[OcrLine] = []

    for idx, item in enumerate(words_result):
        text = item.get("words", "")
        loc = item.get("location")
        if loc:
            left = loc.get("left", 0)
            top = loc.get("top", 0)
            width = loc.get("width", 100)
            height = loc.get("height", 30)
        else:
            top = idx * 40
            left, width, height = 0, 800, 30
        box = [
            [left, top],
            [left + width, top],
            [left + width, top + height],
            [left, top + height],
        ]
        lines.append(OcrLine(text=text, confidence=1.0, box=box))

    logger.info("百度 OCR 识别到 {} 行文本", len(lines))
    return lines
