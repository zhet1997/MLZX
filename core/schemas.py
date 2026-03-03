"""Pydantic 模型 — 定义所有 LLM 输出的 JSON 结构。

解析失败时统一回退为纯文本显示，保证 UI 不崩溃。

JSON 解析管线（按顺序尝试，任一步成功即返回）：
  1. 去除 markdown code fence 包裹
  2. 标准 json.loads
  3. 提取第一个 { ... } 对象（处理 LLM 在 JSON 前输出思考文字的情况）
  4. json_repair 修复常见 LLM JSON 错误（尾逗号、单引号、截断等）
  5. 全部失败 → 回退为纯文本
"""

from __future__ import annotations

import json
import re
from typing import Union

from json_repair import repair_json
from loguru import logger
from pydantic import BaseModel, Field

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$",
    re.DOTALL,
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap around JSON."""
    m = _CODE_FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _extract_json_object(text: str) -> str:
    """Extract the first complete JSON object from text that may contain preamble.

    Uses bracket-matching to find the outermost { ... }, correctly handling
    nested braces and escaped characters inside strings.
    """
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _try_parse(text: str) -> dict | list | None:
    """Try json.loads, then json_repair as fallback. Return parsed object or None."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, (dict, list)):
            return repaired
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 辅助基类
# ---------------------------------------------------------------------------

class _Parseable(BaseModel):
    """提供 parse_or_fallback 类方法的基类。"""

    @classmethod
    def parse_or_fallback(cls, raw_text: str) -> Union["_Parseable", str]:
        """Multi-stage JSON parsing with repair. Falls back to raw text."""
        cleaned = _strip_code_fences(raw_text)

        for candidate in (cleaned, _extract_json_object(cleaned)):
            data = _try_parse(candidate)
            if data is not None:
                try:
                    return cls.model_validate(data)
                except Exception:
                    continue

        logger.warning("JSON 解析失败，回退为纯文本")
        logger.debug("原始文本前300字符: {}", repr(raw_text[:300]))
        return raw_text


# ---------------------------------------------------------------------------
# 点评 (Commentary)
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    quote: str = Field(description="原文引用片段")
    para_id: str = Field(default="", description="段落编号，如 P1")
    why: str = Field(default="", description="为什么引用此处")


class Issue(BaseModel):
    dimension: str = Field(description="问题维度：立意/结构/论证/语言")
    description: str = Field(description="问题描述")
    severity: str = Field(default="medium", description="严重程度: high/medium/low")


class Diagnosis(BaseModel):
    main_problem_dimension: str = Field(description="最主要的问题维度")
    summary: str = Field(default="", description="诊断摘要")


class CommentaryResult(_Parseable):
    score_summary: str = Field(default="", description="总体评价摘要")
    issues: list[Issue] = Field(default_factory=list, description="问题列表（至少 2 条）")
    evidence: list[Evidence] = Field(default_factory=list, description="证据列表")
    highlights: list[str] = Field(default_factory=list, description="亮点")
    diagnosis: Diagnosis | None = Field(default=None, description="诊断")


# ---------------------------------------------------------------------------
# 修改处方 (Prescription)
# ---------------------------------------------------------------------------

class NextStep(BaseModel):
    action: str = Field(description="具体可执行的修改动作")
    reason: str = Field(default="", description="为什么要做这个修改")
    evidence_ref: str = Field(default="", description="对应的原文证据引用")


class PrescriptionResult(_Parseable):
    next_steps: list[NextStep] = Field(default_factory=list, description="修改步骤（3-5 条）")


# ---------------------------------------------------------------------------
# 微任务 (Microtask)
# ---------------------------------------------------------------------------

class Microtask(BaseModel):
    title: str = Field(description="微任务标题")
    instruction: str = Field(description="任务说明")
    check_rule: str = Field(description="自检规则")
    example: str = Field(default="", description="示例（简短）")
    time_estimate: str = Field(default="10分钟", description="预计耗时")


class MicrotaskResult(_Parseable):
    tasks: list[Microtask] = Field(default_factory=list, description="微任务列表")


class MicrotaskGradeResult(_Parseable):
    score: int = Field(default=0, description="10分制评分")
    comment: str = Field(default="", description="一句话点评")
    strengths: list[str] = Field(default_factory=list, description="优点")
    issues: list[str] = Field(default_factory=list, description="不足")
    next_steps: list[str] = Field(default_factory=list, description="改进建议")


# ---------------------------------------------------------------------------
# 自评自查 (SelfCheck)
# ---------------------------------------------------------------------------

class SelfCheckResult(_Parseable):
    dimension_scores: dict[str, int] = Field(
        default_factory=dict,
        description="各维度自评分数，如 {'立意': 7, '结构': 6}",
    )
    main_weakness: str = Field(default="", description="最大短板维度")
    explanation: str = Field(default="", description="解释说明")


# ---------------------------------------------------------------------------
# 对话追问 (ChatClarify)
# ---------------------------------------------------------------------------

class ClarifyQuestion(BaseModel):
    question: str = Field(description="追问问题")
    options: list[str] = Field(default_factory=list, description="可选项（选择题形式）")


class ChatClarifyResult(_Parseable):
    questions: list[ClarifyQuestion] = Field(default_factory=list, description="追问问题列表")
    chat_summary: str = Field(default="", description="对话摘要（压缩要点）")
