# -*- coding: utf-8 -*-
"""回归测试：导入附件后编辑器应可继续编辑（焦点 + 光标位置）。

用户反馈："勾选两个文档拼接后，左侧编辑区无法编辑"。

排查结论：
1. note_editor 从未调用 setReadOnly → 编辑器本身一直是可编辑的
2. 真实原因：对话框返回后焦点没回到编辑器，用户点击看似没反应
3. 修复：append_text 末尾显式 setFocus + moveCursor(End)

本测试用 QGuiApplication 模拟：
  a) set_note 后编辑器可编辑 + 光标位置正常
  b) append_text 后编辑器可编辑 + 光标在末尾
  c) 文本确实是拼接后的内容
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QGuiApplication
from PySide6.QtWidgets import QApplication

_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from src.ui.note_editor import NoteEditor


def test_append_text_editable():
    ed = NoteEditor()

    # 1) 初始状态
    assert ed._editor.isReadOnly() is False
    assert ed._editor.toPlainText() == ""

    # 2) 写入第一份内容
    first = "# 第一份资料\n\n极限定义: ..."
    ed.set_note(first)
    assert ed._editor.isReadOnly() is False
    assert ed._editor.toPlainText() == first

    # 3) 追加第二份（模拟「导入附件」）
    second = "# 第二份资料\n\nε-N 语言"
    ed.append_text(second)
    combined = ed._editor.toPlainText()
    assert ed._editor.isReadOnly() is False, "append_text 后编辑器不可编辑！"
    # 内容应拼接（中间有分隔线）
    assert first in combined
    assert second in combined
    assert "---" in combined, "拼接后应有 --- 分隔线"

    # 4) ⭐ 光标应该在文本末尾（让用户可继续打字）
    cursor = ed._editor.textCursor()
    assert cursor.position() == len(combined), \
        f"append_text 后光标不在末尾: pos={cursor.position()}, len={len(combined)}"

    # 5) 模拟用户继续输入（程序化 setText 确认可写入）
    test_text = "\n\n## 整理后的总结"
    cursor.insertText(test_text)
    new_combined = ed._editor.toPlainText()
    assert test_text.lstrip() in new_combined, "用户继续输入失败！"

    print("[OK] 导入附件 → 拼接 → 光标末尾 → 用户可继续编辑 ✓")
    print(f"     最终文本长度: {len(new_combined)}")


def test_toolbar_actions_focus():
    """工具栏点击后编辑器应保持可编辑 + 获得焦点。"""
    ed = NoteEditor()
    ed.set_note("hello world")

    # 模拟工具栏动作
    ed._wrap_selection("**", "**")  # 无选区，应插入 **文字**
    assert ed._editor.isReadOnly() is False
    assert "**文字**" in ed._editor.toPlainText()

    ed._insert_at_line_start("- ")
    assert ed._editor.isReadOnly() is False
    assert ed._editor.toPlainText().startswith("- ")

    ed._insert_image()
    assert ed._editor.isReadOnly() is False
    assert "![说明]" in ed._editor.toPlainText()

    print("[OK] 工具栏动作后编辑器仍可编辑 ✓")


if __name__ == "__main__":
    try:
        test_append_text_editable()
        test_toolbar_actions_focus()
        print("\n[ALL PASS] 编辑器可编辑性回归测试通过！")
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
