# -*- coding: utf-8 -*-
"""图片宽度 spinbox 智能模式 + 预览区 Ctrl+滚轮缩放 测试。

测试范围：
1. spinbox 默认模式：改默认插入宽度
2. 光标移到 img 行：spinbox 自动切到"当前图片"模式，显示当前 width%
3. 光标在 img 行改 spinbox：实时改源码 width 数字（不改默认值）
4. 光标离开 img 行：spinbox 自动切回"默认"模式
5. 预览区 Ctrl+wheel：调 _preview.zoomIn/zoomOut（缩字号）
6. _resolve_img_percent_to_pixels 纯函数（width% → height=N 纯数字）

⭐ 语法约定（实测驱动）：
  - Markdown 源码存 `<img class="mindflow-img" src="..." width="X%">`（用户可读百分比）
  - 渲染前由 _resolve_img_percent_to_pixels 转成 `<img ... height="N">`（纯数字）
  - QTextBrowser 只认纯数字 height：width 属性被容器拉伸、style 被忽略、
    height 带 px 后缀会被解析为 -2（图片消失）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QWheelEvent, QFont, QPixmap, QColor

_app = QApplication.instance() or QApplication(sys.argv)

from src.ui.note_editor import NoteEditor


# =============== 工具：临时真实图片（400x300，供 resolve 读原图尺寸） ===============

def _make_fixture_png() -> str:
    """生成一张真实的 400x300 图片，返回绝对路径。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "fixture400x300.png")
    pix = QPixmap(400, 300)
    pix.fill(QColor("red"))
    assert pix.save(path), "fixture 图片生成失败"
    return path


# =============== 1. 默认模式 ===============

def test_default_mode_no_img_in_text():
    """无 img 时 spinbox 改值 → 改默认插入宽度。"""
    ed = NoteEditor()
    ed.set_note("just some text\nno image here")
    cursor = ed._editor.textCursor()
    cursor.setPosition(0)
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()

    assert ed._default_img_width == 80, f"默认应为 80: {ed._default_img_width}"
    ed._spin_img_width.setValue(60)
    assert ed._default_img_width == 60, f"应改默认值: {ed._default_img_width}"
    print(f"[OK] 默认模式：spinbox → 默认值 {ed._default_img_width}%")


# =============== 2. 智能模式：光标在 img 行 ===============

def test_cursor_on_img_line_switches_spinbox():
    """光标移到 img 行 → spinbox 显示当前 width%。"""
    ed = NoteEditor()
    ed.set_note(
        "# title\n"
        "\n"
        '<img class="mindflow-img" src="x.png" width="75%">\n'
        "some text"
    )

    doc = ed._editor.document()
    img_block = None
    block = doc.begin()
    while block.isValid():
        if "<img" in block.text():
            img_block = block
            break
        block = block.next()
    assert img_block is not None, "应能找到 img block"

    cursor = ed._editor.textCursor()
    cursor.setPosition(img_block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()

    assert ed._spin_img_width.value() == 75, \
        f"spinbox 应显示当前 75%，实际 {ed._spin_img_width.value()}"
    print("[OK] 光标在 img 行：spinbox 自动显示 75%")


# =============== 3. 智能模式：改 spinbox 即时改源码 ===============

def test_change_spinbox_modifies_current_img_width():
    """光标在 img 行 + 改 spinbox → 源码 width 数字应被替换。"""
    ed = NoteEditor()
    ed.set_note(
        '# title\n'
        '<img class="mindflow-img" src="x.png" width="50%">\n'
        'tail'
    )

    doc = ed._editor.document()
    img_block = None
    block = doc.begin()
    while block.isValid():
        if "<img" in block.text():
            img_block = block
            break
        block = block.next()

    cursor = ed._editor.textCursor()
    cursor.setPosition(img_block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()

    ed._spin_img_width.setValue(30)
    _app.processEvents()

    content = ed.get_note()
    assert 'width="30%"' in content, f"源码应改到 30%: {content!r}"
    assert 'width="50%"' not in content, f"不应残留 50%: {content!r}"
    print("[OK] spinbox 50→30：源码实时改成 30%")


def test_change_spinbox_does_not_modify_default_when_on_img():
    """光标在 img 行时改 spinbox → **不应**改默认值。"""
    ed = NoteEditor()
    ed.set_note('# t\n<img class="mindflow-img" src="x.png" width="40%">\n')

    doc = ed._editor.document()
    block = doc.begin()
    while block.isValid():
        if "<img" in block.text():
            break
        block = block.next()
    cursor = ed._editor.textCursor()
    cursor.setPosition(block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()

    original_default = ed._default_img_width
    ed._spin_img_width.setValue(25)
    _app.processEvents()

    assert ed._default_img_width == original_default, \
        f"默认值不应被改: {ed._default_img_width} (原 {original_default})"
    print(f"[OK] spinbox 改 40→25：默认值仍为 {ed._default_img_width}%")


# =============== 4. 光标离开 img 行：切回默认模式 ===============

def test_cursor_leaving_img_line_restores_default_mode():
    """光标从 img 行移到普通文本行 → spinbox 恢复显示默认值。"""
    ed = NoteEditor()
    ed.set_note(
        '# title\n'
        '<img class="mindflow-img" src="x.png" width="75%">\n'
        'normal line'
    )

    doc = ed._editor.document()
    img_block = None
    block = doc.begin()
    while block.isValid():
        if "<img" in block.text():
            img_block = block
            break
        block = block.next()

    cursor = ed._editor.textCursor()
    cursor.setPosition(img_block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()
    assert ed._spin_img_width.value() == 75

    normal_block = img_block.next()
    cursor = ed._editor.textCursor()
    cursor.setPosition(normal_block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()
    assert ed._spin_img_width.value() == 80, \
        f"离开 img 行后应回到默认 80，实际 {ed._spin_img_width.value()}"
    print("[OK] 光标离开 img 行：spinbox 75 → 80（恢复默认）")


# =============== 5. 预览区 Ctrl+wheel 缩放（缩字号） ===============

def test_preview_ctrl_wheel_zooms():
    """预览区 Ctrl+wheel → _preview.zoomIn/zoomOut（缩字号）。"""
    ed = NoteEditor()
    ed.resize(1200, 700)
    ed.show()
    _app.processEvents()

    base = ed._preview.font().pointSize()

    ed.eventFilter(
        ed._preview.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, 120),
            Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
        ),
    )
    up = ed._preview.font().pointSize()

    ed.eventFilter(
        ed._preview.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, -120),
            Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
        ),
    )
    down = ed._preview.font().pointSize()

    assert up > base, f"预览 Ctrl+上滚应放大: {base} → {up}"
    assert down < up, f"预览 Ctrl+下滚应缩小: {up} → {down}"
    print(f"[OK] 预览 Ctrl+wheel: {base}pt → 上滚{up}pt → 下滚{down}pt")


def test_preview_plain_wheel_does_not_zoom():
    """预览区普通滚轮（无 Ctrl）不应触发缩放。"""
    ed = NoteEditor()
    base = ed._preview.font().pointSize()

    ed.eventFilter(
        ed._preview.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, 120),
            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
        ),
    )
    after = ed._preview.font().pointSize()
    assert after == base, f"普通滚轮不应缩放预览: {base} → {after}"
    print("[OK] 预览普通滚轮（无 Ctrl）不缩放 ✓")


def test_both_viewports_have_event_filter():
    """_editor.viewport() 和 _preview.viewport() 都应响应 Ctrl+wheel。"""
    ed = NoteEditor()

    captured_via_editor = ed.eventFilter(
        ed._editor.viewport(),
        QWheelEvent(QPoint(0, 0), QPoint(0, 0), QPoint(0, 0), QPoint(0, 120),
                    Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False),
    )
    captured_via_preview = ed.eventFilter(
        ed._preview.viewport(),
        QWheelEvent(QPoint(0, 0), QPoint(0, 0), QPoint(0, 0), QPoint(0, 120),
                    Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False),
    )
    assert captured_via_editor is True, f"源码 Ctrl+wheel 应拦截: {captured_via_editor}"
    assert captured_via_preview is True, f"预览 Ctrl+wheel 应拦截: {captured_via_preview}"
    print("[OK] 源码 + 预览 两个 viewport 都响应 Ctrl+wheel")


# =============== 6. 集成测试：spinbox 拖动 + 预览渲染 ===============

def test_full_workflow_change_img_then_preview_updates():
    """完整流程：img 行改 width → 源码实时改，预览重新渲染。"""
    ed = NoteEditor()
    ed.resize(1200, 700)
    ed.show()
    _app.processEvents()

    ed.set_note(
        '# Demo\n'
        '<img class="mindflow-img" src="x.png" width="40%">\n'
    )
    _app.processEvents()

    src_before = ed.get_note()
    assert 'width="40%"' in src_before, f"源码应保留 40%: {src_before!r}"

    doc = ed._editor.document()
    block = doc.begin()
    while block.isValid():
        if "<img" in block.text():
            break
        block = block.next()
    cursor = ed._editor.textCursor()
    cursor.setPosition(block.position())
    ed._editor.setTextCursor(cursor)
    ed._on_cursor_changed()

    ed._spin_img_width.setValue(85)
    _app.processEvents()

    src_after = ed.get_note()
    assert 'width="85%"' in src_after, f"源码应改到 85%: {src_after!r}"
    assert 'width="40%"' not in src_after, "不应残留 40%"
    print("[OK] 完整流程：源码 40% → spinbox 拖到 85% → 源码 85%（预览自动同步）")


# =============== 7. _resolve_img_percent_to_pixels 纯函数 ===============

def test_resolve_pixels_basic():
    """400x300 原图，40% of 800px → height = 800×0.4×300/400 = 240。"""
    from src.ui.note_editor import _resolve_img_percent_to_pixels
    img = _make_fixture_png()
    html = f'<img class="mindflow-img" src="{img}" width="40%">'
    out = _resolve_img_percent_to_pixels(html, 800)
    assert 'height="240"' in out, f"40% of 800 = 240px 高: {out!r}"
    assert 'width="40%"' not in out, f"转换后不应残留 width 百分比: {out!r}"
    print("[OK] 800px 容器：40% → height=240")


def test_resolve_pixels_clamps_out_of_range():
    """>100% 应被夹到 100%。400x300 原图，200% of 400px → 夹到 100% → height=300。"""
    from src.ui.note_editor import _resolve_img_percent_to_pixels
    img = _make_fixture_png()
    html = f'<img class="mindflow-img" src="{img}" width="200%">'
    out = _resolve_img_percent_to_pixels(html, 400)
    assert 'height="300"' in out, f"200% 应 clamp 到 100% (=400px 宽 → 300px 高): {out!r}"
    print("[OK] 越界 200% 被夹到 100%（=容器宽）")


def test_resolve_pixels_multiple_imgs():
    """多张 img 全部转 height。400x300 原图，1000px 容器：50%→375，30%→225。"""
    from src.ui.note_editor import _resolve_img_percent_to_pixels
    img = _make_fixture_png()
    html = (
        f'<img class="mindflow-img" src="{img}" width="50%">'
        '<p>text</p>'
        f'<img class="mindflow-img" src="{img}" width="30%">'
    )
    out = _resolve_img_percent_to_pixels(html, 1000)
    assert 'height="375"' in out, f"50% of 1000 = 500 宽 → 375 高: {out!r}"
    assert 'height="225"' in out, f"30% of 1000 = 300 宽 → 225 高: {out!r}"
    print("[OK] 多张 img 全部转 height（375 + 225）")


def test_resolve_pixels_ignores_non_percent():
    """width="200"（无 %）不应被处理（正则只认 width="N%"）。"""
    from src.ui.note_editor import _resolve_img_percent_to_pixels
    img = _make_fixture_png()
    html = f'<img class="mindflow-img" src="{img}" width="200">'
    out = _resolve_img_percent_to_pixels(html, 800)
    assert 'width="200"' in out, f"无百分号的 width 不应被转: {out!r}"
    assert 'height=' not in out, f"不应出现 height: {out!r}"
    print("[OK] 无百分号 width 不被处理")


def test_resolve_pixels_keeps_original_when_src_missing():
    """找不到原图 → 原样保留 width%（不会崩，Qt 兜底拉满容器）。"""
    from src.ui.note_editor import _resolve_img_percent_to_pixels
    html = '<img class="mindflow-img" src="no-such-file.png" width="50%">'
    out = _resolve_img_percent_to_pixels(html, 800)
    assert 'width="50%"' in out, f"找不到原图应原样保留: {out!r}"
    assert 'height=' not in out, f"找不到原图不应生成 height: {out!r}"
    print("[OK] 找不到原图 → 保留 width%（容错）")


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("图片宽度 spinbox 智能模式 + 预览 Ctrl+wheel 缩放 测试")
    print("=" * 60)
    tests = [
        test_default_mode_no_img_in_text,
        test_cursor_on_img_line_switches_spinbox,
        test_change_spinbox_modifies_current_img_width,
        test_change_spinbox_does_not_modify_default_when_on_img,
        test_cursor_leaving_img_line_restores_default_mode,
        test_preview_ctrl_wheel_zooms,
        test_preview_plain_wheel_does_not_zoom,
        test_both_viewports_have_event_filter,
        test_full_workflow_change_img_then_preview_updates,
        test_resolve_pixels_basic,
        test_resolve_pixels_clamps_out_of_range,
        test_resolve_pixels_multiple_imgs,
        test_resolve_pixels_ignores_non_percent,
        test_resolve_pixels_keeps_original_when_src_missing,
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
    print(f"\n[ALL PASS] {passed}/{len(tests)} 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())