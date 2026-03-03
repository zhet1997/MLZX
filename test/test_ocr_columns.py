"""三栏切分 OCR 测试脚本。

用法:
    conda activate LLM-api
    python test_ocr_columns.py                        # 用内置三栏测试图片
    python test_ocr_columns.py  path/to/image.jpg     # 用你自己的三栏答题卡图片
    python test_ocr_columns.py  path/to/image.jpg 3   # 指定栏数（默认 3）
"""

from __future__ import annotations

import io
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _make_three_column_image() -> bytes:
    """生成一张模拟三栏答题卡的测试图片。"""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2400, 800
    COL_W = W // 3
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("simhei.ttf", 28)
        small_font = ImageFont.truetype("simhei.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    col_texts = [
        [
            "请在各题目的答题区域作答",
            "超出黑色矩形边框限定区域的答案无效",
            "作文.(70分)",
            "在信息爆炸的时代，我们似乎",
            "什么都知道，却什么都不理解。",
            "信息的便捷性为我们搭建了与",
            "世界沟通的桥梁，但我们也逐",
        ],
        [
            '渐发现，人们往往满足于\u201c知道\u201d，',
            '却鲜少追问\u201c为何\u201d。这种浮于',
            "表面的认知，就像纸糊的窗户，",
            "看似完整，实则一击即破。",
            "当我们打开手机，各种信息扑面",
            "而来，我们以为自己了解了世界，",
            "但实际上只是触摸了冰山一角。",
        ],
        [
            "真正的理解需要深度思考，需要",
            "我们在信息洪流中锚定自己选择",
            '的方向，需要我们不仅\u201c知其然\u201d，',
            '更要\u201c知其所以然\u201d。唯有如此，',
            "我们才能在信息时代中保持清醒",
            "的头脑，做出正确的判断。",
            "166",
        ],
    ]

    for col_idx, texts in enumerate(col_texts):
        x_base = col_idx * COL_W + 20
        draw.line([(col_idx * COL_W, 0), (col_idx * COL_W, H)], fill="gray", width=2)
        for row_idx, text in enumerate(texts):
            y = 30 + row_idx * 100
            f = small_font if row_idx < 3 and col_idx == 0 else font
            draw.text((x_base, y), text, fill="black", font=f)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_column_split(image_bytes: bytes, n_cols: int):
    """测试图片切分。"""
    print("=" * 60)
    print(f"测试 1: 图片切分为 {n_cols} 栏")
    print("=" * 60)
    from core.ocr.column_split import split_columns
    from PIL import Image

    crops = split_columns(image_bytes, n_cols=n_cols)
    print(f"[成功] 切分为 {len(crops)} 列")
    for i, crop_bytes in enumerate(crops):
        crop_img = Image.open(io.BytesIO(crop_bytes))
        print(f"  列 {i+1}: {crop_img.size[0]}x{crop_img.size[1]} ({len(crop_bytes)} bytes)")
    return crops


def test_column_ocr(image_bytes: bytes, n_cols: int):
    """测试三栏 OCR 完整流程。"""
    print("\n" + "=" * 60)
    print(f"测试 2: 三栏 OCR（{n_cols} 栏）")
    print("=" * 60)

    from core.ocr.baidu_ocr import ocr_image
    from core.ocr.column_split import ocr_columns
    from core.ocr.postprocess import merge_lines

    lines = ocr_columns(image_bytes, ocr_image, n_cols=n_cols)
    print(f"\n[成功] 合计识别到 {len(lines)} 行")

    print("\n--- 逐行结果 ---")
    for i, ln in enumerate(lines):
        print(f"  {i+1:3d}. {ln.text}")

    text = merge_lines(lines, presorted=True)
    print(f"\n--- 合并后文本 ({len(text)} 字符) ---")
    print(text)
    return text


def test_single_ocr(image_bytes: bytes):
    """对比：不切分直接 OCR 整张图。"""
    print("\n" + "=" * 60)
    print("测试 3: 对比 — 不切分直接 OCR 整张图")
    print("=" * 60)

    from core.ocr.baidu_ocr import ocr_image
    from core.ocr.postprocess import merge_lines

    lines = ocr_image(image_bytes)
    text = merge_lines(lines)
    print(f"[成功] 识别到 {len(lines)} 行, {len(text)} 字符")
    print("\n--- 不切分结果 ---")
    print(text)
    return text


if __name__ == "__main__":
    print("OCR Provider: baidu")
    print()

    n_cols = 3
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        if not os.path.exists(img_path):
            print(f"文件不存在: {img_path}")
            sys.exit(1)
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        if len(sys.argv) > 2:
            n_cols = int(sys.argv[2])
        print(f"使用图片: {img_path} ({len(img_bytes)} bytes)")
    else:
        print("未指定图片，使用内置三栏测试图片…")
        img_bytes = _make_three_column_image()

    test_column_split(img_bytes, n_cols)
    col_text = test_column_ocr(img_bytes, n_cols)
    single_text = test_single_ocr(img_bytes)

    print("\n" + "=" * 60)
    print("对比总结")
    print("=" * 60)
    print(f"  三栏切分 OCR: {len(col_text)} 字符")
    print(f"  直接整图 OCR: {len(single_text)} 字符")
    print("=" * 60)
    print("测试完成！")
