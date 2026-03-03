"""缓存工具 — OCR 结果按图片 hash 缓存，LLM 结果可选缓存。"""

from __future__ import annotations

import hashlib

import streamlit as st


def image_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False)
def cached_ocr(img_hash: str, _ocr_fn, image_bytes: bytes) -> tuple[str, list]:
    """按图片 hash 缓存 OCR 结果。_ocr_fn 接收 image_bytes 返回 (text, low_conf_lines)。"""
    return _ocr_fn(image_bytes)
