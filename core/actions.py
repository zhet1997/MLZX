"""按钮路由 — 将 UI 按钮动作映射到 prompt 构建 → LLM 调用 → 结果解析。"""

from __future__ import annotations

from typing import Generator, Union

from loguru import logger

from llm import call_llm_stream
from core import context as ctx
from core.prompts import build_messages
from core.schemas import (
    ChatClarifyResult,
    CommentaryResult,
    MicrotaskGradeResult,
    MicrotaskResult,
    PrescriptionResult,
    _Parseable,
)

# action -> (schema_class, json_mode)
# 注意: self_check 已改为确定性规则引擎，不再通过 LLM，见 core/self_check.py
ACTION_SCHEMA: dict[str, tuple[type[_Parseable], bool]] = {
    "commentary_overall": (CommentaryResult, True),
    "commentary_dim": (CommentaryResult, True),
    "prescription_overall": (PrescriptionResult, True),
    "prescription_dim": (PrescriptionResult, True),
    "microtask_dim": (MicrotaskResult, True),
    "microtask_grade": (MicrotaskGradeResult, True),
    "chat_clarify": (ChatClarifyResult, True),
}

# 按钮显示名 -> (action, dimension)
BUTTON_ACTIONS: dict[str, tuple[str, str | None]] = {
    "综合点评": ("commentary_overall", None),
    "立意点评": ("commentary_dim", "立意"),
    "结构点评": ("commentary_dim", "结构"),
    "论证点评": ("commentary_dim", "论证"),
    "语言点评": ("commentary_dim", "语言"),
    "综合处方": ("prescription_overall", None),
    "立意处方": ("prescription_dim", "立意"),
    "结构处方": ("prescription_dim", "结构"),
    "论证处方": ("prescription_dim", "论证"),
    "语言处方": ("prescription_dim", "语言"),
    "立意微任务": ("microtask_dim", "立意"),
    "结构微任务": ("microtask_dim", "结构"),
    "论证微任务": ("microtask_dim", "论证"),
    "语言微任务": ("microtask_dim", "语言"),
}


def dispatch_action_stream(
    action: str,
    *,
    dimension: str | None = None,
    user_input: str | None = None,
    extra_vars: dict | None = None,
) -> Generator[str, None, None]:
    """流式执行动作，yield 文本 chunk。完整文本由调用方拼接后解析。"""
    context_vars = ctx.get_context_for_prompt()
    messages = build_messages(
        action, context_vars,
        dimension=dimension, user_input=user_input, extra_vars=extra_vars,
    )

    _, json_mode = ACTION_SCHEMA.get(action, (None, False))
    logger.info("dispatch | action={} dim={} json_mode={}", action, dimension, json_mode)

    temperature = 0.4 if json_mode else 0.7
    yield from call_llm_stream(messages, json_mode=json_mode, temperature=temperature)


def parse_result(action: str, full_text: str) -> Union[_Parseable, str]:
    """将完整的 LLM 输出解析为结构化对象，失败则返回原文本。"""
    schema_cls, _ = ACTION_SCHEMA.get(action, (None, False))
    if schema_cls is None:
        return full_text
    return schema_cls.parse_or_fallback(full_text)
