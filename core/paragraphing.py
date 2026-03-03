"""分段编号 — 将作文正文切分为自然段并编号。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Paragraph:
    para_id: str  # "P1", "P2", ...
    text: str
    start_char: int
    end_char: int


def split_paragraphs(text: str) -> list[Paragraph]:
    """按空行或首行缩进切分自然段，过滤空白段。"""
    raw_parts = re.split(r"\n\s*\n|\n(?=\u3000{2}|\s{2,})", text)
    paragraphs: list[Paragraph] = []
    offset = 0

    for part in raw_parts:
        stripped = part.strip()
        if not stripped:
            offset += len(part)
            continue
        start = text.index(stripped, offset)
        end = start + len(stripped)
        para_id = f"P{len(paragraphs) + 1}"
        paragraphs.append(Paragraph(para_id=para_id, text=stripped, start_char=start, end_char=end))
        offset = end

    return paragraphs


def number_paragraphs(paragraphs: list[Paragraph]) -> str:
    """生成带编号的段落文本。"""
    return "\n\n".join(f"【{p.para_id}】{p.text}" for p in paragraphs)


def paragraphs_to_list(paragraphs: list[Paragraph]) -> list[str]:
    """返回纯文本列表，用于存入 session_state。"""
    return [p.text for p in paragraphs]
