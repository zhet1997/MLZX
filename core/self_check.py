"""自评自查 — 确定性规则引擎（不调用 LLM）。

题目来源: doc/self_check_questions.md
规则来源: doc/self_check_rules.md

计分:  A=0  B=1  C=2
维度:  立意(Q1-Q4)  结构(Q5-Q8)  论证(Q9-Q14)  语言(Q15-Q16)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 题库（文本与 doc/self_check_questions.md 完全一致）
# ---------------------------------------------------------------------------

@dataclass
class Question:
    qid: str          # "Q1" .. "Q16"
    title: str        # 短标题，如 "任务对齐"
    stem: str         # 题干描述
    options: dict[str, str]  # {"A": "...", "B": "...", "C": "..."}
    keyword: str      # 用于 rationale 引用的关键词


QUESTIONS: list[Question] = [
    Question(
        "Q1", "任务对齐",
        '我的中心论点直接回应题目关键词与限定条件（对象/情境/范围）。',
        {"A": "完全对齐", "B": "基本对齐但有空泛",
         "C": '可能偏题或泛化成万能正确'},
        "任务对齐"),
    Question(
        "Q2", "可一句话说清",
        '我能用一句话明确清晰地写出中心论点。',
        {"A": "能", "B": "勉强", "C": "不能"},
        "论点清晰度"),
    Question(
        "Q3", "边界清楚",
        '我在论点中写清在什么情况下/满足什么条件，某论点能够成立。',
        {"A": "清楚", "B": "有但弱", "C": "没有"},
        "论点边界"),
    Question(
        "Q4", "可展开性",
        '我的中心论点能自然拆出 23 个互补角度/分论点（不是同义反复）。',
        {"A": "能", "B": "勉强", "C": "不能"},
        "可展开性"),
    Question(
        "Q5", "开头功能明确",
        '开头完成引题立场论点的交代，而不是绕远或堆材料。',
        {"A": "明确", "B": "部分做到", "C": "不明确"},
        "开头功能"),
    Question(
        "Q6", "主体段功能完整",
        '主体段基本呈现分论点论述回扣的段落功能，不是想到哪写到哪。',
        {"A": "完整", "B": "偶有缺失", "C": "经常缺失"},
        "主体段功能"),
    Question(
        "Q7", "段落顺序有逻辑",
        '三段主体的先后顺序是可解释的（递进/并列/对照），不是随机排列。',
        {"A": "清晰", "B": "大致有", "C": "看不出逻辑"},
        "段落逻辑"),
    Question(
        "Q8", "结尾有效收束",
        '结尾能回扣中心论点并给出收束方式（总结/提升/呼应/倡议），不只是口号堆叠。',
        {"A": "有效", "B": "一般", "C": "无力或跑偏"},
        "结尾收束"),
    Question(
        "Q9", '每段都能回答我凭什么',
        '每个主体段都有明确支撑（事实/例子/引用/对比/数据/经验），不是纯观点堆叠。',
        {"A": "都有", "B": "有的段有", "C": "多数段没有"},
        "论据支撑"),
    Question(
        "Q10", "推理链清晰",
        '我能在关键位置写出这说明因此的推理句，让读者看见从材料到观点的桥。',
        {"A": "常有", "B": "偶尔", "C": "几乎没有"},
        "推理链"),
    Question(
        "Q11", "材料与论点对齐",
        '我的例子/事实确实在证明该段分论点，而不是例子很好但证明不了。',
        {"A": "对齐", "B": "部分对齐", "C": "经常不对齐"},
        "材料对齐"),
    Question(
        "Q12", "论证深度",
        '我至少有一处做到了条件/代价/边界的讨论（例如：什么时候成立、什么时候不成立）。',
        {"A": "有且清楚", "B": "有但浅", "C": "没有"},
        "论证深度"),
    Question(
        "Q13", "反方处理",
        '我呈现过可能的反对意见，并进行了回应（反驳/让步/限定），而非假装不存在。',
        {"A": "有并回应", "B": "提到但没回应", "C": "没有"},
        "反方处理"),
    Question(
        "Q14", "段内不自相矛盾",
        '同一段里没有出现前一句强调 A、后一句又否定 A的推理冲突。',
        {"A": "基本无", "B": "偶有", "C": "明显有"},
        "段内一致性"),
    Question(
        "Q15", "表达清晰具体",
        '抽象词（需要、意义、提升、促进）不过量，能落到具体对象与动作。',
        {"A": "较具体", "B": "时具体时空泛", "C": "经常空泛"},
        "表达具体"),
    Question(
        "Q16", "句式与衔接",
        '有基本的衔接词与指代清晰（这/它/其指向明确），读起来不跳。',
        {"A": "顺畅", "B": "偶尔跳", "C": "经常跳"},
        "衔接顺畅"),
]

QUESTION_MAP: dict[str, Question] = {q.qid: q for q in QUESTIONS}

# ---------------------------------------------------------------------------
# 维度 → 题号映射
# ---------------------------------------------------------------------------

DIMENSION_QIDS: dict[str, list[str]] = {
    "立意": ["Q1", "Q2", "Q3", "Q4"],
    "结构": ["Q5", "Q6", "Q7", "Q8"],
    "论证": ["Q9", "Q10", "Q11", "Q12", "Q13", "Q14"],
    "语言": ["Q15", "Q16"],
}

# 并列时的优先级（越小越优先）
_TIEBREAK_WITH_POOL = {"论证": 0, "结构": 1, "语言": 2}
_TIEBREAK_NO_POOL = {"立意": 0, "论证": 1, "结构": 2, "语言": 3}

_SCORE_MAP = {"A": 0, "B": 1, "C": 2}


# ---------------------------------------------------------------------------
# 核心评分与判定
# ---------------------------------------------------------------------------

def evaluate_self_check(answers: dict[str, str]) -> dict:
    """根据 16 道自评题的作答计算四维度得分与最需改进维度。

    Parameters
    ----------
    answers : dict
        键为 "Q1".."Q16"，值为 "A"/"B"/"C"。

    Returns
    -------
    dict  包含 final_dimension, scores, red_flags, rationale
    """

    # ── 1. 计算每个维度的 raw / norm / ccount ──
    scores: dict[str, dict] = {}
    for dim, qids in DIMENSION_QIDS.items():
        raw = sum(_SCORE_MAP[answers[q]] for q in qids)
        max_possible = 2 * len(qids)
        norm = round(raw / max_possible, 4) if max_possible else 0
        ccount = sum(1 for q in qids if answers[q] == "C")
        scores[dim] = {"raw": raw, "norm": norm, "ccount": ccount}

    # ── 2. 红灯规则 ──
    ideation_red = answers["Q1"] == "C" or answers["Q2"] == "C"
    pool = [dim for dim, s in scores.items() if s["ccount"] >= 1]
    triggered: list[str] = []
    if answers["Q1"] == "C":
        triggered.append("Q1=C（任务对齐：可能偏题）")
    if answers["Q2"] == "C":
        triggered.append("Q2=C（论点清晰度：不能一句话说清）")

    red_flags = {
        "ideation_red": ideation_red,
        "pool": pool,
        "triggered": triggered,
    }

    # ── 3. 选出最需改进维度 ──
    all_zero = all(s["raw"] == 0 for s in scores.values())

    if ideation_red:
        # 规则 1: Q1 或 Q2 选 C → 直接判定立意
        final_dimension = "立意"
    elif all_zero:
        # 特殊情况: 全选 A → 输出"论证"
        final_dimension = "论证"
    elif pool:
        # 规则 2: 红灯池非空 → 在池内比较
        final_dimension = _pick_dimension(scores, pool, _TIEBREAK_WITH_POOL)
    else:
        # 规则 3: 红灯池为空 → 在全部四维度中比较
        all_dims = list(DIMENSION_QIDS.keys())
        final_dimension = _pick_dimension(scores, all_dims, _TIEBREAK_NO_POOL)

    # ── 4. 生成 rationale ──
    rationale = _build_rationale(answers, final_dimension, red_flags, scores)

    return {
        "final_dimension": final_dimension,
        "scores": scores,
        "red_flags": red_flags,
        "rationale": rationale,
    }


def _pick_dimension(
    scores: dict[str, dict],
    candidates: list[str],
    tiebreak: dict[str, int],
) -> str:
    """在 candidates 中选出最需改进维度。

    排序键（降序比较，选最大者）:
      1. norm（归一化得分越高 = 问题越严重）
      2. ccount（C 越多 = 问题越严重）
      3. tiebreak 优先级（数字越小越优先 → 取反后降序）
    """
    return max(
        candidates,
        key=lambda d: (
            scores[d]["norm"],
            scores[d]["ccount"],
            -tiebreak.get(d, 99),
        ),
    )


def _build_rationale(
    answers: dict[str, str],
    final_dim: str,
    red_flags: dict,
    scores: dict[str, dict],
) -> str:
    """生成判定理由文本（只引用作答者选择，不评价原文）。"""
    parts: list[str] = []

    # 红灯触发说明
    if red_flags["ideation_red"]:
        clauses = "；".join(red_flags["triggered"])
        parts.append(f"触发立意红灯条款：{clauses}，直接判定最需改进维度=立意。")

    # 列出该维度所有选 C 的题
    dim_qids = DIMENSION_QIDS[final_dim]
    c_items = [
        f"{q}（{QUESTION_MAP[q].keyword}）"
        for q in dim_qids if answers[q] == "C"
    ]
    if c_items:
        parts.append(f"{final_dim}维度选C的题目：{'、'.join(c_items)}。")

    # 列出该维度所有选 B 的题
    b_items = [
        f"{q}（{QUESTION_MAP[q].keyword}）"
        for q in dim_qids if answers[q] == "B"
    ]
    if b_items:
        parts.append(f"{final_dim}维度选B的题目：{'、'.join(b_items)}。")

    # 补充得分信息
    s = scores[final_dim]
    parts.append(
        f"{final_dim}维度得分: raw={s['raw']}, norm={s['norm']}, "
        f"C题数={s['ccount']}。"
    )

    return "\n".join(parts)


DIMENSION_MAX: dict[str, int] = {
    dim: 2 * len(qids) for dim, qids in DIMENSION_QIDS.items()
}


def build_llm_rationale_prompt(result: dict, answers: dict[str, str]) -> list[dict]:
    """组装用于 LLM 生成自然语言判定理由的 messages。

    读取 prompts/self_check_rationale.md 作为 system prompt，
    填入判定结果数据后返回 [{"role": "system", ...}, {"role": "user", ...}]。
    """
    import os

    final = result["final_dimension"]
    scores = result["scores"]

    scores_lines = []
    for dim, s in scores.items():
        mx = DIMENSION_MAX.get(dim, 0)
        scores_lines.append(f"- {dim}：{s['raw']}/{mx}（选C {s['ccount']} 题）")
    scores_summary = "\n".join(scores_lines)

    bc_lines = []
    for dim, qids in DIMENSION_QIDS.items():
        for qid in qids:
            ans = answers.get(qid, "A")
            if ans in ("B", "C"):
                q = QUESTION_MAP[qid]
                bc_lines.append(f"- {qid}（{q.keyword}）选{ans}：{q.options[ans]}")
    bc_details = "\n".join(bc_lines) if bc_lines else "（全部选A，无B/C题目）"

    red_flags = result.get("red_flags", {})
    if red_flags.get("ideation_red"):
        triggered = "；".join(red_flags.get("triggered", []))
        red_flag_note = f"**立意红灯已触发：** {triggered}"
    else:
        red_flag_note = ""

    template_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "self_check_rationale.md")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    system_content = template.format(
        final_dimension=final,
        scores_summary=scores_summary,
        bc_details=bc_details,
        red_flag_note=red_flag_note,
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "请根据以上信息生成判定理由。"},
    ]


def result_to_json(result: dict) -> str:
    """将评估结果序列化为 JSON 字符串。"""
    return json.dumps(result, ensure_ascii=False, indent=2)
