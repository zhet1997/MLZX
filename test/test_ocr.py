"""百度云 OCR 在线测试脚本。

用法:
    conda activate LLM-api
    python test_ocr.py                       # 用内置测试（纯文本生成图片）
    python test_ocr.py  path/to/image.jpg    # 用你自己的图片
"""

from __future__ import annotations

import io
import sys

from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _make_test_image() -> bytes:
    """生成一张包含中文手写风格文字的测试图片。"""
    from PIL import Image, ImageDraw, ImageFont
    import io

    img = Image.new("RGB", (800, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("simhei.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((30, 30), "在信息爆炸的时代，我们似乎什么都知道，", fill="black", font=font)
    draw.text((30, 100), "却什么都不理解。这是一个值得深思的问题。", fill="black", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_token():
    """测试 1: 获取百度 access_token。"""
    print("=" * 60)
    print("测试 1: 获取百度 access_token")
    print("=" * 60)
    try:
        from core.ocr.baidu_ocr import _get_access_token
        token = _get_access_token()
        print(f"[成功] token = {token[:20]}...{token[-10:]}")
        return True
    except Exception as e:
        print(f"[失败] {e}")
        return False


def test_ocr(image_bytes: bytes, source: str):
    """测试 2: 调用百度手写文字识别。"""
    print("\n" + "=" * 60)
    print(f"测试 2: 百度手写 OCR（图片来源: {source}）")
    print("=" * 60)
    try:
        from core.ocr.baidu_ocr import ocr_image
        from core.ocr.postprocess import merge_lines, get_low_confidence_lines

        lines = ocr_image(image_bytes)
        print(f"[成功] 识别到 {len(lines)} 行")

        for i, ln in enumerate(lines):
            print(f"  行 {i+1}: {ln.text}")

        text = merge_lines(lines)
        print(f"\n合并后文本 ({len(text)} 字符):")
        print("-" * 40)
        print(text)
        print("-" * 40)

        low_conf = get_low_confidence_lines(lines)
        if low_conf:
            print(f"\n低置信度行: {len(low_conf)} 行")
        else:
            print("\n所有行置信度正常")

        return True
    except Exception as e:
        print(f"[失败] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import os
    print(f"OCR Provider: {os.getenv('OCR_PROVIDER', 'baidu')}")
    print(f"API Key:      {os.getenv('BAIDU_OCR_API_KEY', 'N/A')[:10]}...")
    print()

    ok = test_token()
    if not ok:
        print("\ntoken 获取失败，请检查 .env 中的 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY")
        sys.exit(1)

    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        if not os.path.exists(img_path):
            print(f"文件不存在: {img_path}")
            sys.exit(1)
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        source = img_path
    else:
        print("\n未指定图片，使用内置测试图片…")
        img_bytes = _make_test_image()
        source = "内置生成"

    test_ocr(img_bytes, source)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
