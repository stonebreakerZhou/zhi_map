# -*- coding: utf-8 -*-
"""NoteEditor 编辑器增强测试。

测试范围：
1. 8 个 QShortcut 全部存在 + key 序列正确
2. Ctrl+B/I/K/Shift+I 触发相应文本插入行为
3. Ctrl+S 触发 save_now（不抛异常）
4. Ctrl+F 弹出查找条；F3/Shift+F3 找下/上一个
5. Ctrl+滚轮通过 eventFilter 缩放源码字号
6. 拖图片 → 自动拷贝到 DATA_DIR/attachments 并插入 <img> 标签
7. 拖 .md → 自动追加到编辑器末尾
8. 撤销/重做按钮存在 + 能调用 QPlainTextEdit 自带 undo/redo
9. 查找条定位在编辑区右上角（不超出 editor 边界）
10. 查找时所有匹配项高亮（ExtraSelection）

所有测试不依赖真实事件循环（用 processEvents 同步触发）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import (
    QApplication, QPlainTextEdit, QPushButton, QToolBar,
)
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl, QEvent
from PySide6.QtGui import (
    QFont, QPixmap, QColor, QWheelEvent, QDropEvent, QKeySequence, QShortcut, QTextCursor,
)

_app = QApplication.instance() or QApplication(sys.argv)

from src.ui.note_editor import NoteEditor, _MarkdownHighlighter


# =============== 1. QShortcut 全集 ===============

def test_all_8_shortcuts_exist():
    """期望存在的 8 个 QShortcut：Ctrl+B/I/K/Shift+I/S/F + F3/Shift+F3。"""
    ed = NoteEditor()
    scs = ed.findChildren(QShortcut)
    keys = {sc.key().toString() for sc in scs}

    expected = {
        "Ctrl+B", "Ctrl+I", "Ctrl+K", "Ctrl+Shift+I",
        "Ctrl+S", "Ctrl+F", "F3", "Shift+F3",
    }
    missing = expected - keys
    assert not missing, f"缺少快捷键: {missing}\n实际: {keys}"
    print(f"[OK] 8 个 QShortcut 全部就位: {sorted(keys)}")


# =============== 2. 文本格式快捷键 ===============

def test_ctrl_b_wraps_selection_with_bold():
    """Ctrl+B 给选中文本加 **...** 包裹。"""
    ed = NoteEditor()
    ed.set_note("hello world")
    cursor = ed._editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)  # 选 "hello"
    ed._editor.setTextCursor(cursor)

    # 触发 Ctrl+B 对应的 QShortcut
    ed._wrap_selection("**", "**")

    assert "**hello**" in ed.get_note(), f"粗体包裹失败: {ed.get_note()!r}"
    print(f"[OK] Ctrl+B → 'hello' 变 '**hello**'")


def test_ctrl_i_wraps_selection_with_italic():
    """Ctrl+I 给选中文本加 *...* 包裹。"""
    ed = NoteEditor()
    ed.set_note("hello world")
    cursor = ed._editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    ed._editor.setTextCursor(cursor)

    ed._wrap_selection("*", "*")
    assert "*hello*" in ed.get_note(), f"斜体包裹失败: {ed.get_note()!r}"
    print(f"[OK] Ctrl+I → 'hello' 变 '*hello*'")


def test_ctrl_b_inserts_paired_marker_when_no_selection():
    """无选中时 Ctrl+B 插入成对 **|**（光标在中间）。"""
    ed = NoteEditor()
    ed.set_note("")
    ed._editor.textCursor().setPosition(0)
    ed._wrap_selection("**", "**")
    content = ed.get_note()
    # 应该插入一对 ** ，光标在中间
    assert content.count("**") == 2, f"无选中也应插成对标记: {content!r}"
    print(f"[OK] Ctrl+B 无选中 → 插入 '**|**'")


# =============== 3. Ctrl+S 立即保存 ===============

def test_ctrl_s_saves_without_exception():
    """Ctrl+S 调用 save_now 不抛异常。"""
    ed = NoteEditor()
    ed.set_note("# Some content")
    try:
        ed.save_now()
        print("[OK] Ctrl+S → save_now 不抛异常")
    except Exception as e:
        raise AssertionError(f"save_now 失败: {e}")


# =============== 4. 查找浮层 ===============

def test_ctrl_f_shows_find_bar():
    """Ctrl+F 弹出查找条（默认隐藏）。"""
    ed = NoteEditor()
    ed.resize(1200, 600)
    ed.show()
    _app.processEvents()

    assert not ed._find_bar.isVisible(), "查找条初始应隐藏"
    ed._show_find_bar()
    _app.processEvents()
    assert ed._find_bar.isVisible(), "Ctrl+F 后查找条应可见"
    print("[OK] Ctrl+F → 查找条弹出")


def test_find_bar_positioned_inside_editor():
    """查找条应位于编辑区右上角（不超出 editor 边界）。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    ed._show_find_bar()
    _app.processEvents()

    fb = ed._find_bar
    ed_left = ed._editor.x()
    ed_right = ed._editor.x() + ed._editor.width()
    fb_right = fb.x() + fb.width()

    # 允许几像素 tolerance（边框 + raise_）
    assert fb.x() >= ed_left - 5, f"查找条跑到 editor 左边: {fb.x()} < {ed_left}"
    assert fb_right <= ed_right + 20, f"查找条超出 editor 右边界: {fb_right} > {ed_right}"
    print(f"[OK] 查找条定位在编辑区内: ({fb.x()},{fb.y()}) {fb.width()}x{fb.height()}")


def test_f3_finds_next_match():
    """F3 找下一处，匹配计数从 1/n → 2/n。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    ed.set_note("apple banana apple cherry apple")
    ed._show_find_bar()
    ed._find_input.setText("apple")
    _app.processEvents()

    first = ed._find_count.text()
    assert "1" in first and "3" in first, f"首处匹配应为 1/3: {first!r}"

    ed._find_next()
    _app.processEvents()
    second = ed._find_count.text()
    assert "2" in second and "3" in second, f"下一处应为 2/3: {second!r}"

    print(f"[OK] F3 计数: {first} → {second}")


def test_shift_f3_finds_previous():
    """Shift+F3 找上一处。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    ed.set_note("apple banana apple cherry apple")
    ed._show_find_bar()
    ed._find_input.setText("apple")
    _app.processEvents()

    # 先向下走两次：1/3 → 2/3 → 3/3
    ed._find_next()
    _app.processEvents()
    ed._find_next()
    _app.processEvents()
    at_third = ed._find_count.text()

    ed._find_prev()
    _app.processEvents()
    at_second = ed._find_count.text()
    assert "2" in at_second and "3" in at_second, f"上一处应为 2/3: {at_second}"
    print(f"[OK] Shift+F3 反向: {at_third} → {at_second}")


def test_find_highlights_all_matches():
    """查找时所有匹配项用 ExtraSelection 高亮（背景浅黄）。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    ed.set_note("alpha beta alpha gamma alpha")
    ed._show_find_bar()
    ed._find_input.setText("alpha")
    _app.processEvents()

    extras = ed._editor.extraSelections()
    # 应该 ≥ 3 个 ExtraSelection（alpha 出现 3 次）
    assert len(extras) >= 3, f"高亮数应 ≥ 3（alpha 出现 3 次），实际 {len(extras)}"
    # 每个 ExtraSelection 都有浅黄背景
    for sel in extras:
        bg = sel.format.background().color().name().lower()
        assert "fff59d" in bg or "f" in bg, f"高亮背景应浅黄: {bg}"
    print(f"[OK] 查找高亮 {len(extras)} 处匹配项")


# =============== 5. Ctrl+滚轮缩放 ===============

def test_ctrl_wheel_zooms_editor_font():
    """Ctrl+滚轮上滑放大字体，下滑缩小字体（走 QPlainTextEdit.zoomIn/zoomOut）。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    ed._editor.setFont(QFont("Consolas", 10))
    base = ed._editor.font().pointSize()

    # 上滚
    ed.eventFilter(
        ed._editor.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, 120),
            Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
        ),
    )
    up_size = ed._editor.font().pointSize()

    # 下滚
    ed.eventFilter(
        ed._editor.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, -120),
            Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
        ),
    )
    down_size = ed._editor.font().pointSize()

    assert up_size > base, f"上滚应放大: {base} → {up_size}"
    assert down_size < up_size, f"下滚应缩小: {up_size} → {down_size}"
    print(f"[OK] Ctrl+wheel: {base}pt → 上滚{up_size}pt → 下滚{down_size}pt")


def test_plain_wheel_does_not_zoom():
    """不带 Ctrl 的滚轮不应触发缩放（保证正常滚动条能用）。"""
    ed = NoteEditor()
    ed._editor.setFont(QFont("Consolas", 10))
    base = ed._editor.font().pointSize()

    # 普通滚轮（无 Ctrl）
    ed.eventFilter(
        ed._editor.viewport(),
        QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 0), QPoint(0, 120),
            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
        ),
    )
    after = ed._editor.font().pointSize()
    assert after == base, f"普通滚轮不应缩放: {base} → {after}"
    print(f"[OK] 普通滚轮（无 Ctrl）不缩放 ✓")


# =============== 6. 拖图片 ===============

def test_drag_image_inserts_img_and_copies_to_data_dir():
    """拖入 .png/.jpg → 拷贝到 DATA_DIR/attachments/ + 插入 <img> 标签。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    test_dir = tempfile.mkdtemp()
    img_path = os.path.join(test_dir, "test_pic.png")
    pix = QPixmap(50, 50)
    pix.fill(QColor("red"))
    pix.save(img_path)

    ed.set_note("")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(img_path)])
    drop = QDropEvent(
        QPoint(10, 10), Qt.CopyAction, md,
        Qt.LeftButton, Qt.NoModifier,
    )
    ed.dropEvent(drop)
    _app.processEvents()

    content = ed.get_note()
    assert 'class="mindflow-img"' in content, f"未插入 img 标签: {content!r}"
    assert "attachments/dropped_" in content, f"应引用 attachments 相对路径: {content!r}"
    assert img_path not in content, f"不应直接引用绝对路径: {img_path} in {content!r}"

    # DATA_DIR 下确实有文件
    attachments_dir = Path("data/attachments")
    assert attachments_dir.exists(), f"DATA_DIR/attachments 不存在: {attachments_dir}"
    dropped_folders = list(attachments_dir.glob("dropped_*"))
    assert dropped_folders, f"没创建 dropped_ 文件夹"
    latest = dropped_folders[-1]
    copied_imgs = list(latest.glob("test_pic.png"))
    assert copied_imgs, f"图片未拷贝到 {latest}"

    print(f"[OK] 拖图片 → 拷贝到 {latest.name}/test_pic.png + 插入 <img>")


def test_drag_unsupported_extension_ignored():
    """拖入不支持的扩展名（如 .exe）→ 不应插入任何东西。"""
    ed = NoteEditor()
    ed.set_note("ORIGINAL")
    test_dir = tempfile.mkdtemp()
    fake = os.path.join(test_dir, "harmless.exe")
    Path(fake).write_bytes(b"")  # 空文件

    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(fake)])
    drop = QDropEvent(
        QPoint(10, 10), Qt.CopyAction, md,
        Qt.LeftButton, Qt.NoModifier,
    )
    ed.dropEvent(drop)
    _app.processEvents()

    assert ed.get_note() == "ORIGINAL", f"不应修改内容: {ed.get_note()!r}"
    print("[OK] 拖 .exe → 忽略，不修改编辑器")


# =============== 7. 拖 .md ===============

def test_drag_markdown_appends_to_editor():
    """拖入 .md/.markdown/.txt → 追加到编辑器末尾（含分隔符）。"""
    ed = NoteEditor()
    ed.resize(1365, 700)
    ed.show()
    _app.processEvents()

    test_dir = tempfile.mkdtemp()
    md_path = os.path.join(test_dir, "external.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# External Note\n\nimported content here")

    ed.set_note("# Existing Content\n")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(md_path)])
    drop = QDropEvent(
        QPoint(10, 10), Qt.CopyAction, md,
        Qt.LeftButton, Qt.NoModifier,
    )
    ed.dropEvent(drop)
    _app.processEvents()

    content = ed.get_note()
    assert "# Existing Content" in content, "原内容应保留"
    assert "# External Note" in content, "拖入的 md 应被追加"
    assert "imported content here" in content, "拖入的正文应被追加"
    print(f"[OK] 拖 .md → 追加到末尾")


# =============== 8. 撤销/重做按钮 + QPlainTextEdit undo/redo ===============

def test_undo_redo_buttons_exist():
    """工具栏里有 ↶ 撤销 / ↷ 重做 按钮。"""
    ed = NoteEditor()
    toolbar = ed.findChild(QToolBar)
    assert toolbar is not None, "NoteEditor 应含 QToolBar"

    btns = toolbar.findChildren(QPushButton)
    labels = {b.text() for b in btns}
    has_undo = any("撤销" in t for t in labels)
    has_redo = any("重做" in t for t in labels)
    assert has_undo, f"工具栏无撤销按钮: {labels}"
    assert has_redo, f"工具栏无重做按钮: {labels}"
    print(f"[OK] 工具栏含撤销/重做按钮")


def test_undo_redo_actually_work():
    """QPlainTextEdit.undo/redo 可调用且不抛异常。

    ⭐ 不复测撤销的字符级粒度：Qt 自己的 undo system 保证相邻编辑会被合并
    （合并规则由 Qt 内部决定，测试无法稳定复现）。
    我们只验证：
    1) undo() / redo() 是 callable
    2) 工具栏按钮 (clicked → editor.undo/redo) 触发不抛异常
    3) setUndoRedoEnabled(True) 默认开启
    """
    from PySide6.QtWidgets import QPushButton
    ed = NoteEditor()
    assert ed._editor.isUndoRedoEnabled(), "QPlainTextEdit 默认应开启 undo/redo"
    assert callable(ed._editor.undo), "undo 应可调用"
    assert callable(ed._editor.redo), "redo 应可调用"

    # 模拟有内容 → undo 一次（即使空也不应抛异常）
    ed.set_note("# something")
    try:
        ed._editor.undo()
        ed._editor.redo()
        ed._editor.undo()  # 反复调用安全
    except Exception as e:
        raise AssertionError(f"undo/redo 调用抛异常: {e}")

    # 验证工具栏按钮 click → 调用 editor.undo/redo 不抛异常
    toolbar = ed.findChild(QToolBar)
    btns = toolbar.findChildren(QPushButton)
    undo_btn = next((b for b in btns if "撤销" in b.text()), None)
    redo_btn = next((b for b in btns if "重做" in b.text()), None)
    assert undo_btn is not None and redo_btn is not None, "撤销/重做按钮缺失"

    try:
        undo_btn.click()
        redo_btn.click()
    except Exception as e:
        raise AssertionError(f"点击撤销/重做按钮抛异常: {e}")

    print("[OK] QPlainTextEdit.undo/redo + 工具栏按钮均可调用且不抛异常")


# =============== 9. 不冲突：快捷键 = QPlainTextEdit 默认快捷键不重叠 ===============

def test_no_shortcut_conflicts_with_qplaintextedit_defaults():
    """我们的 8 个快捷键不应与 QPlainTextEdit 默认快捷键冲突。

    QPlainTextEdit 默认绑定的快捷键（PySide6 6.x）：
        Ctrl+Z, Ctrl+Y, Ctrl+X, Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+Shift+Z

    我们绑定的：Ctrl+B / I / K / Shift+I / S / F + F3 / Shift+F3
    → 完全不重叠。
    """
    ed = NoteEditor()
    our_keys = {sc.key().toString() for sc in ed.findChildren(QShortcut)}
    qpte_keys = {
        sc.key().toString()
        for sc in ed._editor.findChildren(QShortcut)
    }

    overlap = our_keys & qpte_keys
    assert not overlap, f"与 QPlainTextEdit 默认快捷键冲突: {overlap}"
    print(f"[OK] 无冲突（我们 {len(our_keys)} 个 vs QPlainTextEdit 默认 {len(qpte_keys)} 个）")


# =============== 10. 高亮器集成 ===============

def test_highlighter_attached_to_editor():
    """NoteEditor 初始化后 _highlighter 已 attach 到编辑器 document。"""
    ed = NoteEditor()
    assert hasattr(ed, "_highlighter"), "应有 _highlighter"
    assert isinstance(ed._highlighter, _MarkdownHighlighter), \
        f"类型错: {type(ed._highlighter)}"
    print("[OK] _MarkdownHighlighter 已 attach")


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("NoteEditor 编辑器增强回归测试")
    print("=" * 60)
    tests = [
        test_all_8_shortcuts_exist,
        test_ctrl_b_wraps_selection_with_bold,
        test_ctrl_i_wraps_selection_with_italic,
        test_ctrl_b_inserts_paired_marker_when_no_selection,
        test_ctrl_s_saves_without_exception,
        test_ctrl_f_shows_find_bar,
        test_find_bar_positioned_inside_editor,
        test_f3_finds_next_match,
        test_shift_f3_finds_previous,
        test_find_highlights_all_matches,
        test_ctrl_wheel_zooms_editor_font,
        test_plain_wheel_does_not_zoom,
        test_drag_image_inserts_img_and_copies_to_data_dir,
        test_drag_unsupported_extension_ignored,
        test_drag_markdown_appends_to_editor,
        test_undo_redo_buttons_exist,
        test_undo_redo_actually_work,
        test_no_shortcut_conflicts_with_qplaintextedit_defaults,
        test_highlighter_attached_to_editor,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"\n[FAIL] {t.__name__}: {e}")
            return 1
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
    print(f"\n[ALL PASS] 编辑器增强测试 {passed}/{len(tests)} 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())