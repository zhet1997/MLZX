"""OCR 后处理 — 行合并、置信度过滤、常见错误修正。"""

from __future__ import annotations

import re

from . import OcrLine


def _top_y(line: OcrLine) -> float:
    """取文本框左上角 y 坐标用于排序。"""
    return line.box[0][1]


def merge_lines(lines: list[OcrLine], presorted: bool = False) -> str:
    """合并 OCR 行为连续文本。

    presorted=False（默认）: 按 y 坐标排序后合并，同行文本拼接。
    presorted=True: 保持输入顺序，每行直接换行拼接（用于三栏切分后已排好序的结果）。
    """
    if not lines:
        return ""

    if presorted:
        text = "\n".join(ln.text for ln in lines)
        return _fix_common_errors(text)

    sorted_lines = sorted(lines, key=_top_y)
    merged: list[str] = []
    prev_y = _top_y(sorted_lines[0])
    current_row: list[str] = []
    avg_height = _estimate_line_height(sorted_lines)
    threshold = avg_height * 0.5 if avg_height > 0 else 15

    for ln in sorted_lines:
        y = _top_y(ln)
        if abs(y - prev_y) > threshold and current_row:
            merged.append("".join(current_row))
            current_row = []
        current_row.append(ln.text)
        prev_y = y

    if current_row:
        merged.append("".join(current_row))

    text = "\n".join(merged)
    return _fix_common_errors(text)


def _estimate_line_height(lines: list[OcrLine]) -> float:
    if not lines:
        return 0
    heights = [abs(ln.box[2][1] - ln.box[0][1]) for ln in lines]
    return sum(heights) / len(heights)


def get_low_confidence_lines(lines: list[OcrLine], threshold: float = 0.8) -> list[OcrLine]:
    """返回置信度低于阈值的行。"""
    return [ln for ln in lines if ln.confidence < threshold]


def _fix_common_errors(text: str) -> str:
    """修正常见 OCR 错误（标点等）。"""
    replacements = {
        "，，": "，",
        "。。": "。",
        "、、": "、",
        "  ": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
