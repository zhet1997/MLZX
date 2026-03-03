"""结果渲染 — 将结构化 JSON 结果渲染为 Streamlit 组件。"""

from __future__ import annotations

import streamlit as st

from core.schemas import (
    CommentaryResult,
    MicrotaskGradeResult,
    MicrotaskResult,
    PrescriptionResult,
    SelfCheckResult,
    ChatClarifyResult,
    _Parseable,
)


def render_result(result: _Parseable | str) -> None:
    """根据结果类型分发到对应的渲染函数。"""
    if isinstance(result, str):
        render_fallback(result)
    elif isinstance(result, CommentaryResult):
        render_commentary(result)
    elif isinstance(result, PrescriptionResult):
        render_prescription(result)
    elif isinstance(result, MicrotaskResult):
        render_microtask(result)
    elif isinstance(result, MicrotaskGradeResult):
        render_microtask_grade(result)
    elif isinstance(result, SelfCheckResult):
        render_self_check(result)
    elif isinstance(result, ChatClarifyResult):
        render_chat_clarify(result)
    else:
        render_fallback(str(result))


def render_commentary(r: CommentaryResult) -> None:
    if r.score_summary:
        st.markdown(f"**总评：** {r.score_summary}")

    if r.diagnosis and r.diagnosis.summary:
        st.info(f"**核心诊断 — {r.diagnosis.main_problem_dimension}：** {r.diagnosis.summary}")

    if r.issues:
        st.markdown("#### 问题")
        for i, issue in enumerate(r.issues, 1):
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue.severity, "⚪")
            st.markdown(f"{severity_icon} **{i}. [{issue.dimension}]** {issue.description}")

    if r.evidence:
        st.markdown("#### 证据")
        for ev in r.evidence:
            st.markdown(f"> **{ev.para_id}** \"{ev.quote}\"")
            if ev.why:
                st.caption(f"↳ {ev.why}")

    if r.highlights:
        st.markdown("#### 亮点")
        for h in r.highlights:
            st.markdown(f"✨ {h}")


def render_prescription(r: PrescriptionResult) -> None:
    if not r.next_steps:
        st.warning("未生成修改建议")
        return

    st.markdown("#### 修改处方")
    for i, step in enumerate(r.next_steps, 1):
        with st.expander(f"步骤 {i}: {step.action[:50]}", expanded=True):
            st.markdown(step.action)
            if step.reason:
                st.caption(f"**原因：** {step.reason}")
            if step.evidence_ref:
                st.caption(f"**证据：** {step.evidence_ref}")


def render_microtask(r: MicrotaskResult) -> None:
    if not r.tasks:
        st.warning("未生成微任务")
        return

    st.markdown("#### 微任务训练")
    for i, task in enumerate(r.tasks, 1):
        with st.expander(f"任务 {i}: {task.title} ({task.time_estimate})", expanded=True):
            st.markdown(f"**说明：** {task.instruction}")
            st.markdown(f"**自检规则：** {task.check_rule}")
            if task.example:
                st.markdown(f"**示例：** {task.example}")


def render_microtask_grade(r: MicrotaskGradeResult) -> None:
    st.markdown("#### 微任务评分")
    col_score, col_comment = st.columns([1, 3])
    with col_score:
        st.metric("评分", f"{r.score}/10")
    with col_comment:
        if r.comment:
            st.markdown(f"**点评：** {r.comment}")

    if r.strengths:
        st.markdown("**优点**")
        for s in r.strengths:
            st.markdown(f"- {s}")

    if r.issues:
        st.markdown("**不足**")
        for issue in r.issues:
            st.markdown(f"- {issue}")

    if r.next_steps:
        st.markdown("**改进建议**")
        for step in r.next_steps:
            st.markdown(f"- {step}")


def render_self_check(r: SelfCheckResult) -> None:
    st.markdown("#### 自评报告")

    if r.dimension_scores:
        cols = st.columns(len(r.dimension_scores))
        for col, (dim, score) in zip(cols, r.dimension_scores.items()):
            col.metric(dim, f"{score}/10")

    if r.main_weakness:
        st.warning(f"**最大短板：** {r.main_weakness}")

    if r.explanation:
        st.markdown(r.explanation)


def render_chat_clarify(r: ChatClarifyResult) -> None:
    if r.questions:
        for q in r.questions:
            st.markdown(f"**{q.question}**")
            if q.options:
                for opt in q.options:
                    st.markdown(f"- {opt}")


def render_fallback(text: str) -> None:
    """纯文本 Markdown 渲染（JSON 解析失败时的回退）。

    如果文本看起来像 JSON（以 { 或 [ 开头），用 st.code 展示以保持可读性，
    避免原始 JSON 被 Markdown 引擎错误渲染。
    """
    import re
    stripped = text.strip()
    stripped = re.sub(r"^\s*```(?:json)?\s*\n?", "", stripped)
    stripped = re.sub(r"\n?\s*```\s*$", "", stripped)
    stripped = stripped.strip()

    if stripped.startswith(("{", "[")):
        try:
            import json
            obj = json.loads(stripped)
            st.code(json.dumps(obj, ensure_ascii=False, indent=2), language="json")
        except Exception:
            st.code(stripped, language="json")
    else:
        st.markdown(text)
