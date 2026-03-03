"""LLM API 封装 — 支持 OpenAI 兼容接口 和 Anthropic 兼容接口（MiniMax 等）。

通过 .env 中的 LLM_PROVIDER 切换：
  - "openai"    → 使用 OpenAI SDK（兼容 DeepSeek / 智谱 / 通义千问等）
  - "anthropic" → 使用 Anthropic SDK（兼容 MiniMax 等）
"""

from __future__ import annotations

import json
import os
from typing import Generator
import streamlit as st

from dotenv import load_dotenv
from json_repair import repair_json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()


def get_secret(key: str, default: str | None = None) -> str:
    """优先从 st.secrets 读取，若无则从 os.environ 读取"""
    try:
        return st.secrets.get(key, os.environ.get(key, default))
    except FileNotFoundError:
        # 当不在 Streamlit 环境下运行（例如本地脚本测试）时，st.secrets 可能会报错
        return os.environ.get(key, default)


def _provider() -> str:
    return get_secret("LLM_PROVIDER", "anthropic").lower()


def _get_model() -> str:
    return get_secret("LLM_MODEL", "MiniMax-M2.5")


# =========================================================================
# Anthropic 后端
# =========================================================================

_anthropic_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        api_key = get_secret("ANTHROPIC_API_KEY", "")
        base_url = get_secret("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 未配置，请在 Streamlit Secrets 或 .env 文件中设置")
        _anthropic_client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    return _anthropic_client


_JSON_SYSTEM_SUFFIX = (
    "\n\n请严格以纯 JSON 格式输出。"
    "不要使用 ```json 代码块包裹，不要添加任何解释文字，"
    "直接以 { 开头输出合法 JSON。"
)


def _prepare_anthropic_kwargs(
    messages: list[dict], *, json_mode: bool, temperature: float
) -> dict:
    """Build kwargs for Anthropic API, applying json_mode prefill when needed."""
    system_msg, user_msgs = _split_system(messages)
    kwargs: dict = dict(
        model=_get_model(),
        max_tokens=4096,
        temperature=temperature,
        messages=list(user_msgs),
    )
    if system_msg:
        kwargs["system"] = system_msg
    if json_mode:
        kwargs["system"] = (kwargs.get("system", "") + _JSON_SYSTEM_SUFFIX).strip()
        kwargs["messages"].append({"role": "assistant", "content": "{"})
    return kwargs


def _anthropic_call(messages: list[dict], *, json_mode: bool, temperature: float) -> str:
    kwargs = _prepare_anthropic_kwargs(messages, json_mode=json_mode, temperature=temperature)
    logger.debug("Anthropic call | model={} msgs={} json={}", _get_model(), len(kwargs["messages"]), json_mode)
    resp = _get_anthropic().messages.create(**kwargs)
    text = _extract_text(resp.content)
    if json_mode:
        text = _ensure_json_prefix(text)
    logger.debug("Anthropic reply | chars={}", len(text))
    return text


def _anthropic_stream(messages: list[dict], *, json_mode: bool, temperature: float) -> Generator[str, None, None]:
    kwargs = _prepare_anthropic_kwargs(messages, json_mode=json_mode, temperature=temperature)
    logger.debug("Anthropic stream | model={} msgs={} json={}", _get_model(), len(kwargs["messages"]), json_mode)
    prefix_handled = False
    first_chunk = True
    with _get_anthropic().messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            if first_chunk:
                logger.debug("Anthropic stream first chunk: {}", repr(text[:100]))
                first_chunk = False
            if json_mode and not prefix_handled:
                prefix_handled = True
                lstripped = text.lstrip()
                if lstripped.startswith("{"):
                    yield text
                else:
                    yield "{" + text
                continue
            yield text


# =========================================================================
# OpenAI 后端
# =========================================================================

_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = get_secret("OPENAI_API_KEY", "")
        base_url = get_secret("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，请在 Streamlit Secrets 或 .env 文件中设置")
        _openai_client = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_client


def _openai_call(messages: list[dict], *, json_mode: bool, temperature: float) -> str:
    kwargs: dict = dict(
        model=_get_model(),
        messages=messages,
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug("OpenAI call | model={} msgs={} json={}", _get_model(), len(messages), json_mode)
    resp = _get_openai().chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    logger.debug("OpenAI reply | chars={}", len(text))
    return text


def _openai_stream(messages: list[dict], *, json_mode: bool, temperature: float) -> Generator[str, None, None]:
    kwargs: dict = dict(
        model=_get_model(),
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug("OpenAI stream | model={} msgs={} json={}", _get_model(), len(messages), json_mode)
    stream = _get_openai().chat.completions.create(**kwargs)
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


# =========================================================================
# 工具函数
# =========================================================================

def _ensure_json_prefix(text: str) -> str:
    """Ensure the text starts with '{'. Handles the case where some Anthropic-compatible
    APIs (like MiniMax) include the prefilled '{' in the response while others don't."""
    lstripped = text.lstrip()
    if lstripped.startswith("{"):
        return text
    return "{" + text


def _extract_text(content_blocks: list) -> str:
    """从 Anthropic 响应的 content blocks 中提取文本。

    MiniMax-M2.5 开启了 extended thinking，content 中会包含
    ThinkingBlock(type='thinking') 和 TextBlock(type='text')，
    只取 type='text' 的部分。
    """
    parts: list[str] = []
    for block in content_blocks:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts) if parts else ""


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """将 messages 中的 system 消息提取出来，其余作为 user/assistant 消息返回。
    Anthropic API 要求 system 单独传，不能放在 messages 列表中。
    """
    system_parts: list[str] = []
    other: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        else:
            other.append(m)
    return "\n\n".join(system_parts), other


_CODE_FENCE_RE = __import__("re").compile(
    r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$",
    __import__("re").DOTALL,
)


def _is_valid_json(text: str) -> bool:
    """Check if text can be parsed as JSON, after stripping code fences and repairing."""
    stripped = text.strip()
    if not stripped:
        return False
    m = _CODE_FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        result = repair_json(stripped, return_objects=True)
        return isinstance(result, (dict, list))
    except Exception:
        return False


def _json_retry_call(messages: list[dict], bad_output: str, temperature: float) -> str:
    """When json_mode streaming produces invalid JSON, retry once non-streaming
    with the bad output appended as context so the model can self-correct."""
    logger.warning("JSON 输出无效，自动重试一次 (non-stream)")
    retry_messages = list(messages)
    retry_messages.append({"role": "assistant", "content": bad_output})
    retry_messages.append({
        "role": "user",
        "content": (
            "你上一次的输出不是合法的 JSON，解析失败了。"
            "请重新输出，严格遵守以下规则：\n"
            "1. 直接以 { 开头\n"
            "2. 不要添加任何解释文字、markdown 代码块\n"
            "3. 所有字符串值中的换行用 \\n 表示\n"
            "4. 所有字符串值中的双引号用 \\\" 转义\n"
            "5. 确保 JSON 结构完整，所有括号正确闭合"
        ),
    })
    if _provider() == "anthropic":
        return _anthropic_call(retry_messages, json_mode=True, temperature=max(0.3, temperature - 0.2))
    return _openai_call(retry_messages, json_mode=True, temperature=max(0.3, temperature - 0.2))


# =========================================================================
# 统一对外接口
# =========================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.7,
) -> str:
    """非流式调用，返回完整文本。"""
    if _provider() == "anthropic":
        return _anthropic_call(messages, json_mode=json_mode, temperature=temperature)
    return _openai_call(messages, json_mode=json_mode, temperature=temperature)


def call_llm_stream(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.7,
) -> Generator[str, None, None]:
    """流式调用，逐 chunk yield 文本片段。

    When json_mode=True, if the streamed output is not valid JSON, automatically
    retries once with a non-streaming correction call and yields the corrected result.
    """
    collected: list[str] = []
    if _provider() == "anthropic":
        for chunk in _anthropic_stream(messages, json_mode=json_mode, temperature=temperature):
            collected.append(chunk)
            yield chunk
    else:
        for chunk in _openai_stream(messages, json_mode=json_mode, temperature=temperature):
            collected.append(chunk)
            yield chunk

    if json_mode and collected:
        full = "".join(collected)
        if not _is_valid_json(full):
            corrected = _json_retry_call(messages, full, temperature)
            if _is_valid_json(corrected):
                logger.info("JSON 重试成功，输出修正后的结果")
                yield "\n__JSON_RETRY__\n"
                yield corrected
