# -*- coding: utf-8 -*-
"""图片缩放端到端（真实 QTextBrowser 渲染 + 实测像素高度）。

⭐ 为什么这个测试很重要？
单元测试只验证 `_resolve_img_percent_to_pixels` 把字符串转对了
（width="50%" → height="217"），但**真正决定图片能不能按预期大小显示的
是 QTextBrowser 内部 layout**——而 Qt 在不同版本对 setHtml 后图片渲染
行为可能微调。这个测试用真实可见的 QTextBrowser 跑完整链路并测量
最终像素，**任何 Qt 升级 / 替换实现都会立即被发现**。

验证链路（与真实编辑器完全一致）：
  insert_image_markdown 源码  →  render_markdown  →  _resolve_img_percent_to_pixels
  →  _wrap_html  →  QTextBrowser.setHtml  →  实测 document 尺寸 + img block

⚠️ 必须 show() + 多轮 processEvents() 强制 layout 完成，否则
block.layout().boundingRect() 全是 0（这是上一轮踩坑的根因）。

预期（400x300 原图，579px 视口）：
  width=50%  → 高 = 579*0.5*300/400 ≈ 217px
  width=10/30/50/80/100% → 高度单调递增
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication, QTextBrowser
from PySide6.QtGui import QPixmap, QColor

_app = QApplication.instance() or QApplication(sys.argv)

from src.ui.note_editor import (
    render_markdown,
    _resolve_img_percent_to_pixels,
    _wrap_html,
)

VIEWPORT_W = 579  # 模拟 _preview.viewport().width()


def _flush_layout(browser: QTextBrowser, rounds: int = 8) -> None:
    """强制 QTextBrowser 完成 layout（show() 后要跑多轮才稳）。"""
    for _ in range(rounds):
        _app.processEvents()


def _measure(html: str) -> tuple[int, int, int]:
    """真实可见 QTextBrowser 渲染，返回 (文档宽, 文档高, 最大含图 block 高)。"""
    browser = QTextBrowser()
    browser.setSearchPaths([])  # 绝对路径不需要 searchPaths
    browser.setHtml(_wrap_html(html))
    browser.resize(VIEWPORT_W, 2000)
    browser.show()
    _flush_layout(browser)
    doc_size = browser.document().size().toSize()
    max_img_h = 0
    block = browser.document().begin()
    while block.isValid():
        layout = block.layout()
        if layout is not None:
            max_img_h = max(max_img_h, int(layout.boundingRect().height()))
        block = block.next()
    browser.close()
    return doc_size.width(), doc_size.height(), max_img_h


def _make_fixture_png(w: int = 400, h: int = 300) -> str:
    """生成真实 PNG（默认 400x300）。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, f"fixture{w}x{h}.png")
    pix = QPixmap(w, h)
    pix.fill(QColor("red"))
    assert pix.save(path), "fixture 生成失败"
    return path


# =============== 1. 转换链路各步正确 ===============

def test_resolve_converts_width_percent_to_pure_height():
    """width="X%" → height=N 纯数字（QTextBrowser 唯一认的形态）。"""
    img = _make_fixture_png()
    md = f'<img class="mindflow-img" src="{img}" alt="t" width="50%">'
    rendered = render_markdown(md)
    assert 'width="50%"' in rendered, f"render_markdown 丢失 width: {rendered!r}"
    resolved = _resolve_img_percent_to_pixels(rendered, VIEWPORT_W)
    # 50% of 579 ≈ 289px 宽 → 400x300 原图 → 289*300/400 ≈ 217 高
    assert 'height="217"' in resolved, f"应转 height=217: {resolved!r}"
    assert 'width="50%"' not in resolved, f"转换后不应残留百分比: {resolved!r}"
    print(f"[OK] 转换链路正确: width=50% → height=217")


# =============== 2. 真实像素测量（核心证据）===============

def test_real_render_height_matches_math():
    """实测 50% 渲染高度 ≈ 221px（数学 217px + Qt 边距 ~4px）。"""
    img = _make_fixture_png()
    md = f'<img class="mindflow-img" src="{img}" alt="t" width="50%">'
    resolved = _resolve_img_percent_to_pixels(render_markdown(md), VIEWPORT_W)
    _, _, img_h = _measure(resolved)
    assert 150 <= img_h <= 260, f"50% 高度异常: {img_h}px（期望 ~217）"
    assert abs(img_h - 217) <= 30, f"50% 高度偏离预期 217 太多: {img_h}px"
    print(f"[OK] 实测 50% 渲染: {img_h}px（数学 217px）")


def test_real_render_monotonic_increase():
    """10/30/50/80/100% 高度必须单调递增。"""
    img = _make_fixture_png()
    heights = {}
    for pct in (10, 30, 50, 80, 100):
        md = f'<img class="mindflow-img" src="{img}" alt="t" width="{pct}%">'
        resolved = _resolve_img_percent_to_pixels(render_markdown(md), VIEWPORT_W)
        _, _, hh = _measure(resolved)
        heights[pct] = hh
    assert heights[10] < heights[30] < heights[50] < heights[80] < heights[100], \
        f"高度不单调递增: {heights}"
    print(f"[OK] 单调递增: {heights}")


def test_real_render_100pct_full_width():
    """100% 应占满容器宽（579px）→ 高 = 579*300/400 ≈ 434px。"""
    img = _make_fixture_png()
    md = f'<img class="mindflow-img" src="{img}" alt="t" width="100%">'
    resolved = _resolve_img_percent_to_pixels(render_markdown(md), VIEWPORT_W)
    _, _, img_h = _measure(resolved)
    assert abs(img_h - 434) <= 40, f"100% 应≈434px，实测 {img_h}px"
    print(f"[OK] 100% 全宽 → 实测 {img_h}px（数学 434px）")


def test_real_render_resize_smaller():
    """80% → 30%：实测高度明显下降（验证用户拖 spinbox 真的有效）。"""
    img = _make_fixture_png()
    md80 = f'<img class="mindflow-img" src="{img}" alt="t" width="80%">'
    md30 = f'<img class="mindflow-img" src="{img}" alt="t" width="30%">'
    h80 = _measure(_resolve_img_percent_to_pixels(render_markdown(md80), VIEWPORT_W))[2]
    h30 = _measure(_resolve_img_percent_to_pixels(render_markdown(md30), VIEWPORT_W))[2]
    assert h30 < h80, f"30% ({h30}) 应小于 80% ({h80})"
    assert (h80 - h30) >= 150, f"差距应明显: {h80} vs {h30}"
    print(f"[OK] 拖动缩放有效: 80%={h80}px → 30%={h30}px（差 {h80 - h30}px）")


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("图片缩放端到端（真实 QTextBrowser 像素测量）")
    print("=" * 60)
    tests = [
        test_resolve_converts_width_percent_to_pure_height,
        test_real_render_height_matches_math,
        test_real_render_monotonic_increase,
        test_real_render_100pct_full_width,
        test_real_render_resize_smaller,
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
    print(f"\n[ALL PASS] 端到端真实像素测试 {passed}/{len(tests)} 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())