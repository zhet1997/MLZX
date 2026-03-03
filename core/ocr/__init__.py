"""OCR 模块 — 百度云 OCR + 后处理。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: list  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
