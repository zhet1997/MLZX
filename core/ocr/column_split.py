"""三栏图片切分 OCR — 将答题卡式三栏作文图片切成三列分别识别，再按栏序拼接。"""

from __future__ import annotations

import io
from typing import Callable

from loguru import logger
from PIL import Image

from . import OcrLine


def _top_y(line: OcrLine) -> float:
    return line.box[0][1]


def split_columns(
    image_bytes: bytes,
    n_cols: int = 3,
    overlap_px: int = 20,
) -> list[bytes]:
    """将图片按宽度均分为 n_cols 列，每列左右各加 overlap_px 像素防止切到字。

    返回每列的 JPEG bytes 列表（从左到右）。
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    col_w = w // n_cols

    crops: list[bytes] = []
    for i in range(n_cols):
        left = max(0, i * col_w - overlap_px)
        right = min(w, (i + 1) * col_w + overlap_px)
        crop = img.crop((left, 0, right, h))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=90)
        crops.append(buf.getvalue())
        logger.debug("列 {} 裁切: x=[{}, {}] size={}x{}", i + 1, left, right, right - left, h)

    return crops


def ocr_columns(
    image_bytes: bytes,
    ocr_fn: Callable[[bytes], list[OcrLine]],
    n_cols: int = 3,
    overlap_px: int = 20,
) -> list[OcrLine]:
    """切分图片为多列，对每列分别调用 ocr_fn，最终按 栏序→y坐标 排列。

    ocr_fn 签名: (image_bytes) -> list[OcrLine]
    返回合并后的 OcrLine 列表（已按阅读顺序排列）。
    """
    crops = split_columns(image_bytes, n_cols=n_cols, overlap_px=overlap_px)

    img = Image.open(io.BytesIO(image_bytes))
    full_w = img.size[0]
    col_w = full_w // n_cols

    all_lines: list[OcrLine] = []

    for col_idx, crop_bytes in enumerate(crops):
        logger.info("正在 OCR 第 {}/{} 栏…", col_idx + 1, n_cols)
        lines = ocr_fn(crop_bytes)

        x_offset = max(0, col_idx * col_w - overlap_px)
        for ln in lines:
            ln.box = [[pt[0] + x_offset, pt[1]] for pt in ln.box]

        lines_sorted = sorted(lines, key=_top_y)
        all_lines.extend(lines_sorted)
        logger.info("第 {} 栏识别到 {} 行", col_idx + 1, len(lines_sorted))

    logger.info("三栏 OCR 合计 {} 行", len(all_lines))
    return all_lines
