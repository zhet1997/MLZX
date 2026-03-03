"""Session 上下文管理 — 统一管理 st.session_state 中的所有状态。"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


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
