# -*- coding: utf-8 -*-
"""单节点导出（HTML / PDF）端到端测试。

⭐ 核心验证：
1. PDF 导出时，`<img class="mindflow-img" width="50%">` 的 50% 被解析为
   「PDF 可写区宽度的 50%」——转成 height=N 纯数字（QTextDocument 只认 height）
2. HTML 导出时保留百分比源（浏览器自适应窗口）
3. PDF 导出的文件确实生成且大小 > 0
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor

_app = QApplication.instance() or QApplication(sys.argv)

from src.utils.exporter import (
    _build_node_preview_html,
    export_node_to_html,
    export_node_to_pdf,
)


def _make_fixture_png(w: int = 400, h: int = 300) -> str:
    """生成真实图片（默认 400x300），返回绝对路径。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, f"fixture{w}x{h}.png")
    pix = QPixmap(w, h)
    pix.fill(QColor("red"))
    assert pix.save(path), "fixture 图片生成失败"
    return path


# =============== 1. _build_node_preview_html：target 解析百分比 ===============

def test_build_html_with_target_width_resolves_percent():
    """传 target_width_px=800 + 400x300 原图 → 50% 转成 height=300（纯数字）。"""
    img = _make_fixture_png(400, 300)
    node = SimpleNamespace(
        id="test-node",
        note=f'<img class="mindflow-img" src="{img}" width="50%">',
    )
    html = _build_node_preview_html(node, target_width_px=800)
    # 800 × 50% = 400px 宽；400x300 原图 → 高 = 400 × 300/400 = 300
    assert 'height="300"' in html, f"50% of 800 → height=300: {html[:400]!r}"
    assert 'width="50%"' not in html, f"PDF 模式不应残留百分比: {html[:400]!r}"
    print("[OK] _build_node_preview_html(target=800) → 50% → height=300")


def test_build_html_without_target_preserves_percent():
    """不传 target_width_px（HTML 导出）→ 保留百分比源。"""
    node = SimpleNamespace(
        id="test-node",
        note='<img class="mindflow-img" src="x.png" width="50%">',
    )
    html = _build_node_preview_html(node)
    assert 'width="50%"' in html, f"HTML 应保留百分比源: {html[:400]!r}"
    assert 'height=' not in html, f"HTML 导出不应转 height: {html[:400]!r}"
    print("[OK] _build_node_preview_html() 无参数 → 保留 50%")


# =============== 2. export_node_to_pdf 真的能生成 PDF ===============

def test_export_node_to_pdf_creates_file():
    """真实小图片 → PDF 导出 → 文件生成且 %PDF 头有效。"""
    test_dir = tempfile.mkdtemp()
    img_path = _make_fixture_png(40, 40)
    pdf_path = os.path.join(test_dir, "out.pdf")

    node = SimpleNamespace(
        id="pdf-test-node",
        note=f'# Title\n\n<img class="mindflow-img" src="{img_path}" width="60%">\n',
    )

    try:
        export_node_to_pdf(node, pdf_path)
    except Exception as e:
        raise AssertionError(f"export_node_to_pdf 抛异常: {e}")

    assert os.path.exists(pdf_path), f"PDF 未生成: {pdf_path}"
    size = os.path.getsize(pdf_path)
    assert size > 500, f"PDF 太小（可能空白）: {size} bytes"
    with open(pdf_path, "rb") as f:
        assert f.read(4) == b"%PDF", "文件头不是 PDF 魔数"
    print(f"[OK] export_node_to_pdf → {size} bytes, %PDF 头有效")


def test_export_node_to_pdf_resolves_img_percent():
    """PDF 导出链路：传给 _build_node_preview_html 的 target ≈ 509（A4 可写区）。"""
    test_dir = tempfile.mkdtemp()
    img_path = _make_fixture_png(40, 40)

    import src.utils.exporter as exporter_mod
    captured = {}
    original = exporter_mod._build_node_preview_html

    def spy(node, target_width_px=None):
        captured["target"] = target_width_px
        return original(node, target_width_px=target_width_px)

    exporter_mod._build_node_preview_html = spy

    pdf_path = os.path.join(test_dir, "out.pdf")
    node = SimpleNamespace(id="n", note=f'<img src="{img_path}" width="50%">')
    try:
        export_node_to_pdf(node, pdf_path)
    finally:
        exporter_mod._build_node_preview_html = original

    assert "target" in captured, "spy 未被调用"
    target = captured["target"]
    assert target is not None, "PDF 模式应传 target_width_px"
    assert 500 <= target <= 520, f"target 应≈509（PDF 可写区）, 实际 {target}"
    print(f"[OK] PDF 导出传 target_width_px={target}px")


# =============== 3. export_node_to_html 保留百分比 ===============

def test_export_node_to_html_preserves_percent():
    """HTML 导出：保留 <img width="X%"> 源（浏览器自适应窗口）。"""
    test_dir = tempfile.mkdtemp()
    html_path = os.path.join(test_dir, "out.html")
    node = SimpleNamespace(
        id="n",
        note='<img class="mindflow-img" src="x.png" width="50%">',
    )
    export_node_to_html(node, html_path)
    content = Path(html_path).read_text(encoding="utf-8")
    assert 'width="50%"' in content, f"HTML 应保留 50% 源: {content[:400]!r}"
    print("[OK] export_node_to_html → 保留 50%（浏览器自适应）")


# =============== 4. 渲染链路纯函数 ===============

def test_markdown_image_percent_passes_through_render():
    """HTML 源码 width="75%" → render_markdown 保留 → _resolve 转 height=225。"""
    from src.ui.note_editor import render_markdown, _resolve_img_percent_to_pixels

    img = _make_fixture_png(400, 300)
    md_text = f'<img class="mindflow-img" src="{img}" width="75%">'
    html = render_markdown(md_text)
    assert 'width="75%"' in html, f"render_markdown 应保留 width 属性: {html[:400]!r}"

    resolved = _resolve_img_percent_to_pixels(html, 400)
    # 75% of 400 = 300px 宽；400x300 原图 → 高 = 300 × 300/400 = 225
    assert 'height="225"' in resolved, f"75% of 400 → height=225: {resolved[:400]!r}"
    print("[OK] render_markdown → 75% 保留; _resolve → height=225")


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("单节点导出（HTML / PDF）端到端测试")
    print("=" * 60)
    tests = [
        test_build_html_with_target_width_resolves_percent,
        test_build_html_without_target_preserves_percent,
        test_export_node_to_pdf_creates_file,
        test_export_node_to_pdf_resolves_img_percent,
        test_export_node_to_html_preserves_percent,
        test_markdown_image_percent_passes_through_render,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"\n[FAIL] {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
    print(f"\n[ALL PASS] 单节点导出测试 {passed}/{len(tests)} 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())