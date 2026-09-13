# -*- coding: utf-8 -*-
"""PDF 导出图片显示回归测试（关键：用真实 PDF 渲染验证图片是否真的出现）。

⭐ 为什么这个测试很重要？
之前 test_export_node_pdf 只检查「PDF 文件存在且 %PDF 头有效」，
**完全不能保证图片被显示**——曾经修过两次：
  1. setBaseUrl 修复：PDF 里"看似"有图片对象（实际是假阳性）
  2. 改用 QTextBrowser：PDF 里的红色像素才真的显示出来

这个测试用 QPdfDocument 渲染 PDF 第一页为 PNG，**数红色像素比例**——
只有图片真的显示了才会 >5%。任何回归都会立即发现。
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
from PySide6.QtGui import QPixmap, QColor, QImage

_app = QApplication.instance() or QApplication(sys.argv)

from src.utils.exporter import export_node_to_pdf
from src.config import DATA_DIR


def _make_fixture_png(rel_path: str, w: int = 400, h: int = 300) -> str:
    """在 DATA_DIR/rel_path 创建红色 PNG，返回相对路径（模拟 NoteEditor 插入格式）。"""
    abs_path = Path(DATA_DIR) / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    pix = QPixmap(w, h)
    pix.fill(QColor("red"))
    assert pix.save(str(abs_path)), f"fixture 生成失败: {abs_path}"
    return rel_path


def _render_pdf_first_page(pdf_path: str) -> str:
    """把 PDF 第一页转 PNG，返回 PNG 路径。"""
    from PySide6.QtPdf import QPdfDocument
    doc = QPdfDocument()
    doc.load(pdf_path)
    assert doc.pageCount() >= 1, f"PDF 无可渲染页: {pdf_path}"
    size = doc.pagePointSize(0).toSize()
    img = doc.render(0, size)
    out_png = pdf_path.replace(".pdf", "_render.png")
    assert img.save(out_png), "PDF 渲染 PNG 失败"
    return out_png


def _count_red_ratio(png_path: str) -> float:
    """读 PNG 抽样数红色像素比例（r>180, g<80, b<80）。"""
    img = QImage(png_path)
    assert not img.isNull(), f"PNG 读不出: {png_path}"
    w, h = img.width(), img.height()
    red, total = 0, 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = img.pixelColor(x, y)
            total += 1
            if c.red() > 180 and c.green() < 80 and c.blue() < 80:
                red += 1
    return red / max(total, 1)


# =============== 测试 ===============

def test_pdf_export_renders_relative_path_image():
    """相对路径图片（attachments/...）应在 PDF 里真实显示。"""
    rel = _make_fixture_png("attachments/test_pdf_export/pic.png")
    note = f'<img class="mindflow-img" src="{rel}" alt="t" width="80%">'
    node = SimpleNamespace(id="n", note=note)

    test_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(test_dir, "out.pdf")
    export_node_to_pdf(node, pdf_path)

    assert os.path.exists(pdf_path), f"PDF 未生成: {pdf_path}"
    assert os.path.getsize(pdf_path) > 1000, f"PDF 太小: {os.path.getsize(pdf_path)}"

    # 关键：渲染 PDF，数红色像素比例
    rendered = _render_pdf_first_page(pdf_path)
    red_ratio = _count_red_ratio(rendered)
    print(f"[OK] PDF 含相对路径图片: 红色像素占 {red_ratio:.1%}（阈值 >5%）")
    assert red_ratio > 0.05, (
        f"❌ PDF 没显示图片（红色像素仅 {red_ratio:.1%}）— "
        f"可能是 QTextDocument 不解析相对路径（已知坑，必须用 QTextBrowser）"
    )


def test_pdf_export_respects_width_percent():
    """不同 width% → 渲染出的红色像素比例应明显不同（图片大小变了）。"""
    ratios = {}
    for pct in (20, 50, 80):
        rel = _make_fixture_png(f"attachments/test_pdf_pct/pic_{pct}.png")
        note = f'<img class="mindflow-img" src="{rel}" width="{pct}%">'
        node = SimpleNamespace(id="n", note=note)

        test_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(test_dir, f"pct{pct}.pdf")
        export_node_to_pdf(node, pdf_path)
        rendered = _render_pdf_first_page(pdf_path)
        ratios[pct] = _count_red_ratio(rendered)

    print(f"[OK] 不同宽度 PDF 红色像素比例: {ratios}")
    # 20% < 80%（图片大小显著影响红色面积）
    assert ratios[20] < ratios[80], (
        f"❌ 宽度不影响 PDF 渲染: {ratios}（20% 应小于 80%）"
    )


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("PDF 导出图片显示回归测试（真实 PDF 渲染 + 像素验证）")
    print("=" * 60)
    tests = [
        test_pdf_export_renders_relative_path_image,
        test_pdf_export_respects_width_percent,
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
    print(f"\n[ALL PASS] PDF 图片显示测试 {passed}/{len(tests)} 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())