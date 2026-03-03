"""后台测试脚本 — 验证 LLM API 连通性。

用法:
    conda activate LLM-api
    python test_llm.py
"""

from llm import call_llm, call_llm_stream

MESSAGES = [
    {"role": "system", "content": "你是一个高中语文教师。"},
    {"role": "user", "content": "请用一句话评价这个作文开头：'在信息爆炸的时代，我们似乎什么都知道，却什么都不理解。'"},
]


def test_non_stream():
    print("=" * 60)
    print("测试 1: 非流式调用")
    print("=" * 60)
    try:
        result = call_llm(MESSAGES, json_mode=False)
        print(f"[成功] 返回 {len(result)} 字符")
        print(result)
    except Exception as e:
        print(f"[失败] {e}")


def test_stream():
    print("\n" + "=" * 60)
    print("测试 2: 流式调用")
    print("=" * 60)
    try:
        full = ""
        for chunk in call_llm_stream(MESSAGES, json_mode=False):
            print(chunk, end="", flush=True)
            full += chunk
        print(f"\n[成功] 流式输出共 {len(full)} 字符")
    except Exception as e:
        print(f"[失败] {e}")


def test_json_mode():
    print("\n" + "=" * 60)
    print("测试 3: JSON 模式")
    print("=" * 60)
    json_messages = [
        {"role": "system", "content": "你是一个高中语文教师。"},
        {"role": "user", "content": '请用 JSON 格式评价这个开头，格式为 {"score": 1-10, "comment": "评语"}。\n开头：在信息爆炸的时代，我们似乎什么都知道，却什么都不理解。'},
    ]
    try:
        result = call_llm(json_messages, json_mode=True)
        print(f"[成功] 返回 {len(result)} 字符")
        print(result)
    except Exception as e:
        print(f"[失败] {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    import os
    print(f"Provider: {os.getenv('LLM_PROVIDER')}")
    print(f"Model:    {os.getenv('LLM_MODEL')}")
    print(f"Base URL: {os.getenv('ANTHROPIC_BASE_URL', os.getenv('OPENAI_BASE_URL', 'N/A'))}")
    print()

    test_non_stream()
    test_stream()
    test_json_mode()

    print("\n" + "=" * 60)
    print("全部测试完成！")
    print("=" * 60)
