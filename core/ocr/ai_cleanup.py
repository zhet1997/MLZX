"""AI 智能清理 — 用 LLM 过滤 OCR 垃圾文本、修复断句。"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from loguru import logger

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "ocr_cleanup.md"


def _load_prompt(ocr_text: str) -> list[dict]:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    user_msg = template.replace("{ocr_text}", ocr_text)
    return [
        {"role": "system", "content": "你是一个专业的 OCR 文本清理助手。"},
        {"role": "user", "content": user_msg},
    ]


def cleanup_ocr_stream(ocr_text: str) -> Generator[str, None, None]:
    """流式调用 LLM 清理 OCR 文本，yield 文本 chunk。"""
    from llm import call_llm_stream

    messages = _load_prompt(ocr_text)
    logger.info("AI OCR 清理 | 输入字数={}", len(ocr_text))
    yield from call_llm_stream(messages, json_mode=False, temperature=0.3)
