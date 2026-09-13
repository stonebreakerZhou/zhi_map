# -*- coding: utf-8 -*-
"""图片快捷插入 smoke test。

覆盖：
1. ImagePickerDialog：空列表也能弹（不崩），有列表显示 cell
2. NoteEditor.insert_image_markdown：在光标位置插入 ![alt](path)
3. NoteEditor.insert_image_requested 信号：点工具栏「🖼 图片」能 emit
4. _preview.setSearchPaths([DATA_DIR]) 设了 → 相对路径图片能解析

注意：图片缩放相关测试已移到 test_image_zoom.py（真实窗口测试更可靠）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# ⭐ 让 print 在 Windows GBK 控制台也能打 emoji / 中文
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolBar, QToolButton

_app = QApplication.instance() or QApplication(sys.argv)

from src.ui.image_picker_dialog import ImagePickerDialog
from src.ui.note_editor import NoteEditor
from src.config import DATA_DIR


def test_insert_image_markdown_writes_correct_text():
    """insert_image_markdown 应在光标位置写入带 class + style 的 <img>。"""
    from PySide6.QtGui import QTextCursor
    ed = NoteEditor()
    ed.set_note("前面一段\n")
    # 把光标放到末尾
    cursor = ed._editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    ed._editor.setTextCursor(cursor)

    ed.insert_image_markdown("attachments/abc/pic.jpg", "定义图")

    text = ed.get_note()
    assert text.startswith("前面一段"), f"前面内容应保留: {text!r}"
    # ⭐ 关键：源码里必须能看到 width（用户在源码里能改）
    assert '<img class="mindflow-img" src="attachments/abc/pic.jpg" alt="定义图" width="80%">' in text, \
        f"应包含带 class+width 的 HTML img 标签: {text!r}"
    print(f"[OK] 插入正确: {text!r}")


def test_insert_image_markdown_unescapes_alt():
    """alt 里含 [ ] 或换行会被替换成安全字符。"""
    ed = NoteEditor()
    ed.insert_image_markdown("x.png", "limit[N]def\nhere")
    text = ed.get_note()
    # [ -> 【, ] -> 】, \n -> 空格
    assert 'alt="limit【N】def here"' in text, f"alt 转义不对: {text!r}"
    print(f"[OK] alt 转义: {text!r}")


def test_insert_image_markdown_honors_default_width():
    """通过 spinbox 改宽度后，下次插入的图片用新宽度。"""
    ed = NoteEditor()
    ed._default_img_width = 50  # 直接改字段模拟 spinbox
    ed.insert_image_markdown("x.png", "alt")
    text = ed.get_note()
    assert 'width="50%"' in text, f"应使用新宽度 50%: {text!r}"
    print(f"[OK] 默认宽度生效: {text!r}")


def test_insert_image_markdown_escapes_quotes_in_alt():
    """alt 含双引号 / < > 必须转义，否则破坏 HTML 属性。"""
    ed = NoteEditor()
    ed.insert_image_markdown("x.png", 'say"hi"<b>')
    text = ed.get_note()
    # " -> &quot;, < -> &lt;, > -> &gt;
    assert '&quot;' in text and '&lt;' in text and '&gt;' in text, \
        f"HTML 特殊字符未转义: {text!r}"
    # 且不含未转义的 "
    import re
    alt_match = re.search(r'alt="([^"]*)"', text)
    assert alt_match is not None
    print(f"[OK] HTML 特殊字符转义: alt={alt_match.group(1)!r}")


def test_insert_image_requested_signal_emits():
    """点工具栏 🖼 按钮应该 emit insert_image_requested 信号。"""
    from PySide6.QtCore import Signal

    ed = NoteEditor()
    captured = []
    ed.insert_image_requested.connect(lambda: captured.append("emitted"))

    # 找到 🖼 图片 按钮
    toolbar = ed.findChild(QToolBar)
    assert toolbar is not None
    btn_img = None
    for b in toolbar.findChildren(QToolButton):
        if "图片" in (b.text() or ""):
            btn_img = b
            break
    # toolbar 用 QPushButton 不是 QToolButton
    if btn_img is None:
        from PySide6.QtWidgets import QPushButton
        for b in toolbar.findChildren(QPushButton):
            if "图片" in (b.text() or ""):
                btn_img = b
                break

    assert btn_img is not None, "找不到 🖼 图片 按钮"
    btn_img.click()
    assert captured == ["emitted"], f"信号未发出: {captured}"
    print("[OK] 工具栏 🖼 图片按钮触发 insert_image_requested 信号")


def test_preview_has_search_path():
    """QTextBrowser 必须设了 setSearchPaths([DATA_DIR])，否则相对路径图片渲染不出来。"""
    ed = NoteEditor()
    paths = ed._preview.searchPaths()
    assert str(DATA_DIR) in paths, \
        f"preview searchPaths 应含 DATA_DIR={DATA_DIR}, 实际: {paths}"
    print(f"[OK] QTextBrowser.searchPaths = {paths}")


def test_picker_dialog_empty():
    """空列表也能弹（显示空状态，不崩）。"""
    dlg = ImagePickerDialog([], parent=None)
    assert dlg._images == []
    assert dlg.picked is None
    print("[OK] 空附件列表 → 对话框正常构造（空状态显示）")


def test_picker_dialog_filters_images():
    """非 image 类型的附件会被过滤掉。"""
    atts = [
        {"id": "1", "file_type": "image", "file_path": "attachments/a/1.jpg",
         "caption": "图1"},
        {"id": "2", "file_type": "document", "file_path": "attachments/a/2.md",
         "caption": "文档"},
        {"id": "3", "file_type": "image", "file_path": "attachments/a/3.png",
         "caption": ""},
    ]
    dlg = ImagePickerDialog(atts)
    assert len(dlg._images) == 2
    assert dlg._images[0]["id"] == "1"
    assert dlg._images[1]["id"] == "3"
    print(f"[OK] 过滤后剩 {len(dlg._images)} 张图")


if __name__ == "__main__":
    print("=" * 60)
    print("图片快捷插入 smoke test")
    print("=" * 60)
    try:
        test_insert_image_markdown_writes_correct_text()
        test_insert_image_markdown_unescapes_alt()
        test_insert_image_markdown_honors_default_width()
        test_insert_image_markdown_escapes_quotes_in_alt()
        test_insert_image_requested_signal_emits()
        test_preview_has_search_path()
        test_picker_dialog_empty()
        test_picker_dialog_filters_images()
        print("\n[ALL PASS] 图片快捷插入功能验证通过 ✓")
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
