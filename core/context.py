"""Session 上下文管理 — 统一管理 st.session_state 中的所有状态。"""

from __future__ import annotations

import json
from dataclasses import dataclass

import streamlit as st
from loguru import logger


# ---------------------------------------------------------------------------
# 对话消息结构
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    action_type: str = ""  # 空字符串表示普通对话


# ---------------------------------------------------------------------------
# 初始化 / 读写 session_state
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "title": "",
    "word_requirement": "",
    "essay_text": "",
    "paragraphs": [],
    "chat_history": [],
    "chat_summary": "",
    "microtask_pool": None,
    "microtask_selection": None,
    "focus_mode": False,
    "focus_deadline_ts": None,
    "focus_duration_sec": 600,
    "focus_submitted": False,
    "microtask_grade_result": None,
    "self_check_active": False,
    "self_check_answers": None,
    "self_check_result": None,
}


def init_state() -> None:
    """确保所有 key 存在于 session_state 中。"""
    for k, v in _DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()


def get(key: str):
    init_state()
    return st.session_state[key]


def set_val(key: str, value) -> None:
    st.session_state[key] = value


def append_chat(msg: ChatMessage) -> None:
    init_state()
    st.session_state["chat_history"].append(msg)


def get_chat_history() -> list[ChatMessage]:
    init_state()
    return st.session_state["chat_history"]


# ---------------------------------------------------------------------------
# 组装 prompt 上下文
# ---------------------------------------------------------------------------

def get_context_for_prompt() -> dict:
    """返回可用于 prompt 模板渲染的变量字典。"""
    init_state()
    paragraphs = st.session_state["paragraphs"]
    para_text = ""
    if paragraphs:
        para_text = "\n".join(f"P{i+1}: {p}" for i, p in enumerate(paragraphs))

    return {
        "title": st.session_state["title"],
        "word_requirement": st.session_state["word_requirement"],
        "essay": st.session_state["essay_text"],
        "paragraphs": para_text,
        "chat_summary": st.session_state["chat_summary"],
    }


# ---------------------------------------------------------------------------
# 多轮对话记忆
# ---------------------------------------------------------------------------

_DIALOGUE_ACTION_TYPES = {"", "chat_clarify"}

_MAX_PRIOR_ANALYSIS_CHARS = 500


def get_recent_dialogue(max_messages: int = 10) -> list[dict]:
    """提取最近的自由对话消息，用于注入 chat_clarify 的多轮上下文。

    只包含 action_type 为空（普通对话）或 chat_clarify 的消息。
    assistant 消息若为 JSON（ChatClarifyResult），提取 questions 的纯文本。
    """
    history: list[ChatMessage] = get_chat_history()
    filtered: list[ChatMessage] = [
        m for m in history if m.action_type in _DIALOGUE_ACTION_TYPES
    ]
    recent = filtered[-max_messages:]

    result: list[dict] = []
    for msg in recent:
        content = msg.content
        if msg.role == "assistant" and msg.action_type == "chat_clarify":
            content = _extract_clarify_text(content)
        result.append({"role": msg.role, "content": content})
    return result


def _extract_clarify_text(raw: str) -> str:
    """从 ChatClarifyResult JSON 中提取可读的追问文本。"""
    try:
        data = json.loads(raw)
        questions = data.get("questions", [])
        if questions:
            lines = []
            for q in questions:
                text = q.get("question", "")
                opts = q.get("options", [])
                if opts:
                    text += "（" + " / ".join(opts) + "）"
                lines.append(text)
            return "\n".join(lines)
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw


def build_prior_analysis() -> str:
    """扫描聊天历史中的 assistant action 消息，构建之前的分析摘要。

    用于 {chat_summary} / {prior_analysis} 模板变量，
    让后续 LLM 调用了解此前已完成的分析。
    """
    history: list[ChatMessage] = get_chat_history()
    parts: list[str] = []

    for msg in history:
        if msg.role != "assistant" or not msg.action_type:
            continue
        summary = _extract_action_summary(msg)
        if summary:
            parts.append(summary)

    text = "\n".join(parts)
    if len(text) > _MAX_PRIOR_ANALYSIS_CHARS:
        text = text[-_MAX_PRIOR_ANALYSIS_CHARS:]
        cut = text.find("。")
        if cut != -1:
            text = text[cut + 1:]
    return text


def _extract_action_summary(msg: ChatMessage) -> str:
    """从单条 assistant action 消息中提取关键摘要。"""
    at = msg.action_type
    try:
        data = json.loads(msg.content)
    except (json.JSONDecodeError, TypeError):
        return ""

    if at in ("commentary_overall", "commentary_dim"):
        score = data.get("score_summary", "")
        diag = data.get("diagnosis", {})
        dim = diag.get("main_problem_dimension", "")
        diag_summary = diag.get("summary", "")
        label = "综合点评" if at == "commentary_overall" else f"{dim}维度点评"
        pieces = [f"[{label}]"]
        if score:
            pieces.append(score[:120])
        if diag_summary:
            pieces.append(f"主要问题维度={dim}：{diag_summary[:80]}")
        return " ".join(pieces)

    if at in ("prescription_overall", "prescription_dim"):
        steps = data.get("next_steps", [])
        actions = [s.get("action", "") for s in steps[:3] if s.get("action")]
        if actions:
            return "[修改处方] " + "；".join(actions)

    if at == "microtask_grade":
        score = data.get("score", "")
        comment = data.get("comment", "")
        if score or comment:
            return f"[微任务评分] {score}/10 {comment[:60]}"

    if at == "self_check_rule":
        final = data.get("final_dimension", "")
        if final:
            return f"[自评自查] 最需改进维度={final}"

    if at == "chat_clarify":
        summary = data.get("chat_summary", "")
        if summary:
            return f"[对话摘要] {summary[:120]}"

    return ""
