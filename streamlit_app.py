"""智能作文学习支持系统 — Streamlit 主入口。"""

from __future__ import annotations

import time

import streamlit as st
from loguru import logger

from core import context as ctx
from core.context import ChatMessage
from core.actions import dispatch_action_stream, parse_result
from core.render import render_result, render_self_check_rule_from_json
from core.schemas import MicrotaskResult
from core.self_check import QUESTIONS, evaluate_self_check, result_to_json, build_llm_rationale_prompt
from core.paragraphing import split_paragraphs, number_paragraphs, paragraphs_to_list

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="高中生议论文评改",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ctx.init_state()

_locked = ctx.get("focus_mode")

# ---------------------------------------------------------------------------
# 自定义样式
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .block-container { padding-top: 4rem; padding-bottom: 0.5rem; }
    .stChatMessage { font-size: 0.95rem; }
    section[data-testid="stSidebar"] { display: none; }
    .stButton > button { padding-top: 0.25rem; padding-bottom: 0.25rem; font-size: 0.85rem; }
    .stDivider { margin-top: 0.3rem; margin-bottom: 0.3rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _check_essay_ready() -> bool:
    """检查作文是否已输入。"""
    if not ctx.get("essay_text").strip():
        st.warning("请先在左栏输入或上传作文正文")
        return False
    return True


def _do_ocr() -> None:
    """执行三栏切分 OCR（百度云）。"""
    img_file = st.session_state.get("_uploaded_image")
    if img_file is None:
        st.warning("请先上传作文图片")
        return

    import os
    from core.ocr.postprocess import merge_lines, get_low_confidence_lines
    from core.ocr.column_split import ocr_columns
    from core.ocr.baidu_ocr import ocr_image
    from core.caching import cached_ocr, image_hash

    img_bytes = img_file.getvalue()
    h = image_hash(img_bytes)

    n_cols = int(os.getenv("OCR_COLUMNS", "3"))

    def _ocr_fn(data: bytes):
        if n_cols > 1:
            lines = ocr_columns(data, ocr_image, n_cols=n_cols)
            text = merge_lines(lines, presorted=True)
        else:
            lines = ocr_image(data)
            text = merge_lines(lines)
        low_conf = get_low_confidence_lines(lines)
        return text, low_conf

    with st.spinner("百度云 OCR 三栏识别中…"):
        text, low_conf = cached_ocr(h, _ocr_fn, img_bytes)

    ctx.set_val("essay_text", text)
    st.session_state["_ocr_just_ran"] = True

    if low_conf:
        st.warning(f"有 {len(low_conf)} 行置信度较低，建议手动校对")


def _do_ai_cleanup() -> None:
    """调用 LLM 智能清理 OCR 文本（去垃圾、修断句），后台静默执行。"""
    essay = ctx.get("essay_text")
    if not essay.strip():
        st.warning("请先进行 OCR 识别或输入作文正文")
        return

    from core.ocr.ai_cleanup import cleanup_ocr_stream

    collected: list[str] = []
    with st.spinner("AI 智能整理中…"):
        for chunk in cleanup_ocr_stream(essay):
            collected.append(chunk)
    cleaned = "".join(collected).strip()

    if cleaned:
        ctx.set_val("essay_text", cleaned)
        st.session_state["_ocr_just_ran"] = True
    else:
        st.warning("AI 整理未返回有效结果")


def _do_paragraph() -> None:
    """执行分段编号。"""
    essay = ctx.get("essay_text")
    if not essay.strip():
        st.warning("请先输入作文正文")
        return
    paras = split_paragraphs(essay)
    ctx.set_val("paragraphs", paragraphs_to_list(paras))
    numbered = number_paragraphs(paras)
    ctx.set_val("essay_text", numbered)
    st.session_state["_ocr_just_ran"] = True


_JSON_RETRY_MARKER = "\n__JSON_RETRY__\n"


def _try_extract_microtask_pool(raw_text: str, dimension: str | None) -> bool:
    """Fallback: try to extract a microtask pool from raw text using json_repair.

    Returns True if a usable pool was saved to session_state.
    """
    from json_repair import repair_json
    from core.schemas import _strip_code_fences, _extract_json_object

    cleaned = _strip_code_fences(raw_text)
    for candidate in (cleaned, _extract_json_object(cleaned)):
        try:
            data = repair_json(candidate, return_objects=True)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            continue
        pool_tasks = []
        for t in tasks:
            if not isinstance(t, dict) or "title" not in t:
                continue
            pool_tasks.append({
                "title": t.get("title", ""),
                "instruction": t.get("instruction", ""),
                "check_rule": t.get("check_rule", ""),
                "example": t.get("example", ""),
                "time_estimate": t.get("time_estimate", "10分钟"),
            })
        if pool_tasks:
            ctx.set_val("microtask_pool", {
                "dimension": dimension,
                "tasks": pool_tasks,
            })
            logger.info("microtask_pool 兜底提取成功: {} 道题", len(pool_tasks))
            return True
    return False


def _stream_and_save(
    action: str,
    dimension: str | None = None,
    user_input: str | None = None,
    extra_vars: dict | None = None,
) -> None:
    """在当前 st.chat_message 上下文中执行流式输出并保存结果。"""
    collected: list[str] = []
    with st.spinner("AI 正在分析…"):
        for chunk in dispatch_action_stream(
            action, dimension=dimension, user_input=user_input, extra_vars=extra_vars,
        ):
            collected.append(chunk)
    full_text = "".join(collected)

    if _JSON_RETRY_MARKER in full_text:
        full_text = full_text.split(_JSON_RETRY_MARKER)[-1].strip()

    parsed = parse_result(action, full_text)
    render_result(parsed)
    ctx.append_chat(ChatMessage(role="assistant", content=full_text, action_type=action))

    if hasattr(parsed, "chat_summary") and parsed.chat_summary:
        ctx.set_val("chat_summary", parsed.chat_summary)

    if action == "microtask_dim":
        if isinstance(parsed, MicrotaskResult):
            ctx.set_val("microtask_pool", {
                "dimension": dimension,
                "tasks": [t.model_dump() for t in parsed.tasks],
            })
        else:
            _try_extract_microtask_pool(full_text, dimension)


# ---------------------------------------------------------------------------
# 三栏布局
# ---------------------------------------------------------------------------

left_col, center_col, right_col = st.columns([1, 2, 1], gap="medium")

# ========================= 左栏：作文输入 =========================
with left_col:
    st.subheader("📄 作文输入")

    title = st.text_input("作文题目", value=ctx.get("title"), key="input_title")
    ctx.set_val("title", title)

    word_req = st.text_input(
        "字数要求",
        value=ctx.get("word_requirement"),
        placeholder="例如：不少于800字",
        key="input_word_req",
    )
    ctx.set_val("word_requirement", word_req)

    st.divider()

    uploaded = st.file_uploader("上传作文图片", type=["jpg", "png", "jpeg"], key="_uploaded_image")
    if uploaded:
        st.image(uploaded, caption="已上传的图片", width="stretch")

    ocr_c1, ocr_c2 = st.columns(2)
    with ocr_c1:
        if st.button("🔍 OCR 识别", use_container_width=True, disabled=_locked or uploaded is None):
            _do_ocr()
            st.rerun()
    with ocr_c2:
        if st.button("🤖 AI 智能整理", use_container_width=True, disabled=_locked):
            _do_ai_cleanup()
            st.rerun()

    st.divider()

    if "input_essay" not in st.session_state or st.session_state.get("_ocr_just_ran"):
        st.session_state["input_essay"] = ctx.get("essay_text")
        st.session_state["_ocr_just_ran"] = False

    essay_text = st.text_area(
        "作文正文（可编辑）",
        height=400,
        key="input_essay",
    )
    ctx.set_val("essay_text", essay_text)

    if st.button("📋 分段编号", use_container_width=True, disabled=_locked):
        _do_paragraph()
        st.rerun()

# ========================= 中栏：对话区 =========================
with center_col:
    st.subheader("💬 高中生议论文评改")

    chat_container = st.container(height=550)
    with chat_container:
        for _msg_idx, msg in enumerate(ctx.get_chat_history()):
            with st.chat_message(msg.role):
                if msg.action_type == "self_check_rule" and msg.role == "assistant":
                    render_self_check_rule_from_json(msg.content)
                elif msg.action_type and msg.role == "assistant":
                    parsed_msg = parse_result(msg.action_type, msg.content)
                    render_result(parsed_msg)
                    if msg.action_type == "microtask_dim" and not _locked:
                        pool = ctx.get("microtask_pool")
                        if isinstance(parsed_msg, MicrotaskResult):
                            task_list = [
                                {"title": t.title, "instruction": t.instruction,
                                 "check_rule": t.check_rule}
                                for t in parsed_msg.tasks
                            ]
                        elif pool and pool.get("tasks"):
                            task_list = pool["tasks"]
                        else:
                            task_list = []
                        pool_dim = pool["dimension"] if pool else None
                        for _ti, _task in enumerate(task_list):
                            if st.button(
                                f"开始作答: {_task['title']}",
                                key=f"btn_start_task_{_msg_idx}_{_ti}",
                                use_container_width=True,
                            ):
                                ctx.set_val("microtask_selection", {
                                    "index": _ti,
                                    "title": _task["title"],
                                    "instruction": _task.get("instruction", ""),
                                    "check_rule": _task.get("check_rule", ""),
                                    "dimension": pool_dim or "",
                                })
                                ctx.set_val("focus_mode", True)
                                ctx.set_val("focus_deadline_ts", time.time() + ctx.get("focus_duration_sec"))
                                ctx.set_val("focus_submitted", False)
                                st.rerun()
                else:
                    st.markdown(msg.content)

        # ---- 自评自查（渲染在对话框内部） ----
        _sc_active = ctx.get("self_check_active")
        _sc_result = ctx.get("self_check_result")

        if _sc_active and not _locked:
            st.divider()
            st.markdown("### 自评自查（16题）")

            if _sc_result is not None:
                from core.render import render_self_check_rule
                render_self_check_rule(_sc_result)
                final = _sc_result.get("final_dimension", "")
                st.info(f"自评结果：最需改进维度 = {final}。详细判定理由与各维度得分见上方。")
                sc_c1, sc_c2 = st.columns(2)
                with sc_c1:
                    if st.button("重新作答", key="btn_sc_reset", use_container_width=True):
                        ctx.set_val("self_check_active", True)
                        ctx.set_val("self_check_answers", None)
                        ctx.set_val("self_check_result", None)
                        st.rerun()
                with sc_c2:
                    if st.button("关闭自评", key="btn_sc_close", use_container_width=True):
                        ctx.set_val("self_check_active", False)
                        st.rerun()
            else:
                _SC_SENTINEL = "-"
                with st.form("self_check_form"):
                    sc_answers: dict[str, str] = {}
                    for q in QUESTIONS:
                        st.markdown(f"**{q.qid} {q.title}**")
                        st.caption(q.stem)
                        choice = st.radio(
                            q.qid,
                            options=[_SC_SENTINEL, "A", "B", "C"],
                            format_func=lambda x, _q=q: (
                                "-- 请选择 --" if x == "-"
                                else f"{x}  {_q.options[x]}"
                            ),
                            horizontal=True,
                            key=f"sc_radio_{q.qid}",
                            label_visibility="collapsed",
                        )
                        sc_answers[q.qid] = choice

                    submitted = st.form_submit_button("提交自评", use_container_width=True, type="primary")
                    if submitted:
                        unanswered = [qid for qid, v in sc_answers.items() if v == _SC_SENTINEL]
                        if unanswered:
                            st.warning(f"请完成所有题目后再提交。未作答：{', '.join(unanswered)}")
                        else:
                            result = evaluate_self_check(sc_answers)

                            from llm import call_llm
                            prompt_msgs = build_llm_rationale_prompt(result, sc_answers)
                            with st.spinner("正在生成分析..."):
                                try:
                                    rationale_text = call_llm(prompt_msgs, json_mode=False, temperature=0.7)
                                    result["rationale"] = rationale_text.strip()
                                except Exception as e:
                                    logger.warning("LLM rationale 生成失败，使用规则文本: {}", e)

                            result_json_str = result_to_json(result)
                            ctx.set_val("self_check_answers", sc_answers)
                            ctx.set_val("self_check_result", result)
                            ctx.append_chat(ChatMessage(
                                role="user",
                                content="[触发功能] 自评自查（16题已提交）",
                                action_type="self_check_rule",
                            ))
                            ctx.append_chat(ChatMessage(
                                role="assistant",
                                content=result_json_str,
                                action_type="self_check_rule",
                            ))
                            st.rerun()

    # ---- 专注作答模式 ----
    if _locked:
        sel = ctx.get("microtask_selection")
        if sel:
            st.divider()
            st.markdown(f"### 专注作答: {sel['title']}")
            st.markdown(f"**维度：** {sel['dimension']}")
            st.markdown(f"**任务说明：** {sel['instruction']}")
            st.markdown(f"**自检规则：** {sel['check_rule']}")

            deadline = ctx.get("focus_deadline_ts")
            remaining = max(0, int(deadline - time.time())) if deadline else 0
            mins, secs = divmod(remaining, 60)
            st.info(f"剩余时间: {mins}分{secs:02d}秒")

            answer = st.text_area(
                "请在此作答",
                height=200,
                key="focus_answer_area",
                placeholder="在这里写下你的答案…",
            )

            def _submit_answer(answer_text: str) -> None:
                """提交微任务答案并调用 AI 评分。"""
                ctx.set_val("focus_submitted", True)
                sel_data = ctx.get("microtask_selection")
                dim = sel_data.get("dimension", "")
                task_desc = (
                    f"任务: {sel_data['title']}\n"
                    f"说明: {sel_data['instruction']}\n"
                    f"自检规则: {sel_data['check_rule']}"
                )
                ctx.append_chat(ChatMessage(
                    role="user",
                    content=f"[微任务作答] {sel_data['title']}\n\n{answer_text}",
                    action_type="microtask_grade",
                ))
                with chat_container:
                    with st.chat_message("assistant"):
                        _stream_and_save(
                            "microtask_grade",
                            dimension=dim,
                            extra_vars={"task_text": task_desc, "answer_text": answer_text},
                        )
                ctx.set_val("focus_mode", False)
                ctx.set_val("focus_deadline_ts", None)
                ctx.set_val("microtask_selection", None)

            fc1, fc2 = st.columns(2)
            with fc1:
                if st.button("提交答案", key="btn_submit_answer", use_container_width=True, type="primary"):
                    if answer and answer.strip():
                        _submit_answer(answer.strip())
                        st.rerun()
                    else:
                        st.warning("请先输入答案再提交")
            with fc2:
                if st.button("放弃作答", key="btn_cancel_focus", use_container_width=True):
                    ctx.set_val("focus_mode", False)
                    ctx.set_val("focus_deadline_ts", None)
                    ctx.set_val("microtask_selection", None)
                    st.rerun()

            if remaining == 0 and not ctx.get("focus_submitted"):
                current_answer = answer.strip() if answer else ""
                if current_answer:
                    st.warning("时间到！正在自动提交…")
                    _submit_answer(current_answer)
                    st.rerun()
                else:
                    st.warning("时间到！未输入答案，已退出作答模式。")
                    ctx.set_val("focus_mode", False)
                    ctx.set_val("focus_deadline_ts", None)
                    ctx.set_val("microtask_selection", None)
                    st.rerun()

    if not _locked:
        user_input = st.chat_input("与AI对话…", key="chat_input")
        if user_input:
            ctx.append_chat(ChatMessage(role="user", content=user_input))

            if _check_essay_ready():
                if not ctx.get("paragraphs"):
                    _do_paragraph()
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(user_input)
                    with st.chat_message("assistant"):
                        _stream_and_save("chat_clarify", user_input=user_input)
                st.rerun()

# ========================= 右栏：功能按钮 =========================
with right_col:
    st.subheader("🛠️ 功能操作")

    def _run_action(action: str, dim: str | None, label: str) -> None:
        if _check_essay_ready():
            if not ctx.get("paragraphs"):
                _do_paragraph()
            ctx.append_chat(ChatMessage(role="user", content=f"[触发功能] {label}", action_type=action))
            with center_col:
                with st.chat_message("assistant"):
                    _stream_and_save(action, dimension=dim)
            st.rerun()

    if st.button("📊 自评自查", use_container_width=True, disabled=_locked):
        ctx.set_val("self_check_active", True)
        ctx.set_val("self_check_answers", None)
        ctx.set_val("self_check_result", None)
        st.rerun()

    st.divider()

    st.markdown("**作文点评**")
    if st.button("综合点评", key="btn_comm_all", use_container_width=True, disabled=_locked):
        _run_action("commentary_overall", None, "综合点评")
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        if st.button("立意", key="btn_comm_ly", use_container_width=True, disabled=_locked):
            _run_action("commentary_dim", "立意", "立意点评")
    with cc2:
        if st.button("结构", key="btn_comm_jg", use_container_width=True, disabled=_locked):
            _run_action("commentary_dim", "结构", "结构点评")
    with cc3:
        if st.button("论证", key="btn_comm_lz", use_container_width=True, disabled=_locked):
            _run_action("commentary_dim", "论证", "论证点评")
    with cc4:
        if st.button("语言", key="btn_comm_yy", use_container_width=True, disabled=_locked):
            _run_action("commentary_dim", "语言", "语言点评")

    st.divider()

    st.markdown("**修改处方**")
    if st.button("综合处方", key="btn_presc_all", use_container_width=True, disabled=_locked):
        _run_action("prescription_overall", None, "综合处方")
    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        if st.button("立意", key="btn_presc_ly", use_container_width=True, disabled=_locked):
            _run_action("prescription_dim", "立意", "立意处方")
    with pc2:
        if st.button("结构", key="btn_presc_jg", use_container_width=True, disabled=_locked):
            _run_action("prescription_dim", "结构", "结构处方")
    with pc3:
        if st.button("论证", key="btn_presc_lz", use_container_width=True, disabled=_locked):
            _run_action("prescription_dim", "论证", "论证处方")
    with pc4:
        if st.button("语言", key="btn_presc_yy", use_container_width=True, disabled=_locked):
            _run_action("prescription_dim", "语言", "语言处方")

    st.divider()

    st.markdown("**微任务训练**")
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        if st.button("立意", key="btn_micro_ly", use_container_width=True, disabled=_locked):
            _run_action("microtask_dim", "立意", "立意微任务")
    with mc2:
        if st.button("结构", key="btn_micro_jg", use_container_width=True, disabled=_locked):
            _run_action("microtask_dim", "结构", "结构微任务")
    with mc3:
        if st.button("论证", key="btn_micro_lz", use_container_width=True, disabled=_locked):
            _run_action("microtask_dim", "论证", "论证微任务")
    with mc4:
        if st.button("语言", key="btn_micro_yy", use_container_width=True, disabled=_locked):
            _run_action("microtask_dim", "语言", "语言微任务")
