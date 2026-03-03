"""Prompt 模板加载与渲染 — 从 prompts/ 目录加载 .md 并填充变量。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# ---------------------------------------------------------------------------
# 各维度的评判标准（用于 commentary_dim / prescription_dim 模板）
# ---------------------------------------------------------------------------

CRITERIA: dict[str, str] = {
    "立意": """（一）审题准确性
1.题干关键词抓取是否完整：核心概念有没有被遗漏/偷换。
2.限制条件是否被遵守：时间、对象、范围、关系词有没有被忽略。
3.任务类型是否匹配：要求"谈看法/论证观点/权衡利弊/提出对策"，文章有没有用对写法。
（二）立意清晰度
1.中心论点是否明确可复述。
2.论点是否可争辩（有判断）。
3.立意是否一贯：前后观点有没有漂移。
（三）立意深度与边界
1.概念界定能力。2.问题意识。3.条件意识。4.避免绝对化。
（四）价值取向与合理性
1.价值判断是否自洽。2.常识与事实底线。3.立意是否有现实触点。""",

    "结构": """（一）整体结构完整性
1.开头是否完成"定位任务"：引题→亮观点→铺路线。
2.主体是否有分论点。
3.结尾是否完成"收束与提升"。
（二）分论点设计质量
1.分论点是否互相独立。2.分论点是否覆盖中心论点。3.分论点排序是否有逻辑。
（三）段内结构与推进
1.主题句是否明确。2.展开是否"有步骤"。3.例证/分析比例是否合理。
（四）衔接与连贯
1.段与段之间是否有桥。2.逻辑连接词使用是否恰当。3.指代是否清楚。
（五）论述节奏与篇幅控制
1.重点是否突出。2.不必要的铺陈是否过多。""",

    "论证": """（一）论证链是否完整
1.论点→理由→证据→结论是否齐全。2.是否存在跳步。3.是否有反向检验。
（二）论证方式的使用与匹配
1.举例论证。2.对比论证。3.因果论证。4.类比论证。5.引用论证。6.归纳/演绎。7.条件论证。
（三）论据质量
1.真实性/可核查性。2.权威性。3.具体性。4.多样性。
（四）论据与论点的贴合度
1.是否直接支撑分论点。2.是否存在"借题发挥"。3.是否存在"以偏概全"。
（五）分析深度
1.是否只是复述论点。2.是否解释机制。3.是否处理反例/反驳。4.是否做权衡。
（六）逻辑严密性
1.概念偷换。2.以偏概全。3.循环论证。4.诉诸情绪。5.错误二分。6.稻草人。7.因果倒置。
（七）论证的可读性
1.论证结构是否显性。2.每段是否有小结回扣。""",

    "语言": """（一）准确性与规范性
1.用字是否规范：没有错别字。2.用词是否精准。3.语法与标点。
（二）清晰度与可读性
1.句子长度控制。2.信息密度。3.重复控制。
（三）论证型表达能力
1.判断句干净利落。2.逻辑连接自然。3.抽象与具体切换。
（四）文采与风格
1.语体得体。2.修辞服务论证。3.避免口号化。4.引用节制。
（五）个性与辨识度
1.有自己的精彩句子。2.表达有锋利度。""",
}

# 各维度处方的额外指令
PRESCRIPTION_EXTRA: dict[str, str] = {
    "立意": "另外，请注意，作文的立意是可以多种多样的，并不能简单判定一个学生的作文立意是好是坏，关键要看他是否具有思辨思维，判定一定要谨慎。",
    "结构": "另外，请注意，作文的结构不仅要清晰，更要重点突出、层次分明，段落应起到应有的作用。",
    "论证": "另外，请注意，作文的论证并非一定要包含特定的论据和驳论的过程，只要是能够有效证明论点，哪怕只是单一的说理论证，都是可取的。",
    "语言": "另外，请不要忽略学生作文中具有个性色彩的金句，这些句子也许并不完全契合议论文的风格，但是只要凝聚了学生深沉的思考，也应被看见。",
}


def _load_template(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt 模板不存在: {path}")
    return path.read_text(encoding="utf-8")


def _safe_format(template: str, variables: dict) -> str:
    """使用 format_map 填充变量，未提供的变量保留原占位符。"""

    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(SafeDict(variables))


def build_messages(
    action: str,
    context: dict,
    *,
    dimension: str | None = None,
    user_input: str | None = None,
    extra_vars: dict | None = None,
) -> list[dict]:
    """组装 system + user messages。

    Parameters
    ----------
    action : 动作类型，如 "commentary_overall", "commentary_dim" 等
    context : 由 context.get_context_for_prompt() 返回的变量字典
    dimension : 维度名称（仅 *_dim 动作需要）
    user_input : 用户在对话框中的输入（仅 chat_clarify 需要）
    extra_vars : 额外模板变量（如 microtask_grade 的 task_text / answer_text）
    """
    system_tpl = _load_template("system_base.md")
    system_msg = _safe_format(system_tpl, context)

    template_map: dict[str, str] = {
        "self_check": "self_check.md",
        "commentary_overall": "commentary_overall.md",
        "commentary_dim": "commentary_dim.md",
        "prescription_overall": "prescription_overall.md",
        "prescription_dim": "prescription_dim.md",
        "microtask_dim": "microtask_dim.md",
        "microtask_grade": "microtask_grade.md",
        "chat_clarify": "chat_clarify.md",
    }

    tpl_file = template_map.get(action)
    if not tpl_file:
        raise ValueError(f"未知的 action: {action}")

    user_tpl = _load_template(tpl_file)

    variables = {**context}
    if dimension:
        variables["dimension"] = dimension
        variables["criteria"] = CRITERIA.get(dimension, "")
        variables["extra_instruction"] = PRESCRIPTION_EXTRA.get(dimension, "")
    if extra_vars:
        variables.update(extra_vars)

    user_msg = _safe_format(user_tpl, variables)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    if user_input and action == "chat_clarify":
        messages.append({"role": "user", "content": user_input})

    logger.debug("build_messages | action={} dim={} msgs={}", action, dimension, len(messages))
    return messages
