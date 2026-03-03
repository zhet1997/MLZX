"""调试脚本：测试 microtask_dim 的 LLM 输出，检查 JSON 是否合法。"""
import sys
import io
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from llm import call_llm_stream, call_llm

test_messages = [
    {
        "role": "system",
        "content": (
            "你是一个经验丰富的高中语文教师。\n"
            "当前作文信息：\n- 题目：论信息时代的理解\n- 字数要求：不少于800字"
        ),
    },
    {
        "role": "user",
        "content": (
            "请根据学生作文中在立意维度上的具体问题，设计 2 个微任务。\n\n"
            "请以 JSON 格式输出，结构如下：\n"
            '{\n  "tasks": [\n    {\n'
            '      "title": "微任务标题",\n'
            '      "instruction": "详细的任务说明",\n'
            '      "check_rule": "自检规则",\n'
            '      "example": "简短示例",\n'
            '      "time_estimate": "预计耗时"\n'
            "    }\n  ]\n}"
        ),
    },
]

print("=" * 60)
print("测试1: 流式调用 (json_mode=True)")
print("=" * 60)
collected = []
for chunk in call_llm_stream(test_messages, json_mode=True):
    collected.append(chunk)
    print(chunk, end="", flush=True)
print()

raw = "".join(collected)
print("\n--- 原始文本长度:", len(raw))
print("--- 前100字符:", repr(raw[:100]))

try:
    obj = json.loads(raw)
    print("--- JSON 解析成功!")
    print(json.dumps(obj, ensure_ascii=False, indent=2)[:500])
except json.JSONDecodeError as e:
    print(f"--- JSON 解析失败: {e}")
    print(f"--- 错误位置附近: ...{repr(raw[max(0,e.pos-20):e.pos+20])}...")

    start = raw.find("{")
    if start > 0:
        print(f"\n--- JSON 前有 {start} 个字符的前缀:")
        print(repr(raw[:start]))

print("\n" + "=" * 60)
print("测试2: 非流式调用 (json_mode=True)")
print("=" * 60)
result = call_llm(test_messages, json_mode=True)
print("--- 原始文本长度:", len(result))
print("--- 前100字符:", repr(result[:100]))
try:
    obj = json.loads(result)
    print("--- JSON 解析成功!")
except json.JSONDecodeError as e:
    print(f"--- JSON 解析失败: {e}")
    print(f"--- 错误位置附近: ...{repr(result[max(0,e.pos-20):e.pos+20])}...")
