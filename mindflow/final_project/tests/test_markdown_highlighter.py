# -*- coding: utf-8 -*-
"""_MarkdownHighlighter 语法高亮单元测试。

覆盖所有规则：
1. 标题 # / ## / ###
2. **粗体**
3. *斜体*（不能误吃 **）
4. `行内代码`
5. ```代码块```（跨行状态保持）
6. [链接](url) 和 ![图片](url)
7. > 引用
8. - 列表 / 1. 有序列表
9. --- 分割线
10. 集成到 NoteEditor 后不破坏现有功能
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QFont, QColor
from PySide6.QtWidgets import QApplication, QPlainTextDocumentLayout

_app = QApplication.instance() or QApplication(sys.argv)

from src.ui.note_editor import _MarkdownHighlighter, NoteEditor


# =============== 工具函数 ===============

def find_format_for(doc: QTextDocument, line_text: str, target_substr: str):
    """在一行里找到 target_substr，返回那块字符的 QTextCharFormat。

    ⭐ 关键：QSyntaxHighlighter.setFormat() 存的是 AdditionalFormats（布局级），
    而不是字符的默认 charFormat。QTextCursor.charFormat() 读不到。
    必须从 block.layout().formats() 找 FormatRange。

    返回 None 表示该字符没被任何高亮规则碰过（默认 format）。
    """
    blocks = []
    block = doc.begin()
    while block.isValid():
        blocks.append(block.text())
        block = block.next()

    for bnum, text in enumerate(blocks):
        if text == line_text and target_substr in text:
            char_start = text.index(target_substr)
            return get_format_at(doc, bnum, char_start)
    raise AssertionError(
        f"找不到 line={line_text!r} 含 substring={target_substr!r}\n"
        f"实际 blocks: {blocks}"
    )


def get_format_at(doc: QTextDocument, block_num: int, char_in_block: int):
    """读某位置处的高亮属性（返回 dict 而非 QTextCharFormat）。

    ⭐ 关键：FormatRange.format 是临时对象（PyShiboken 包装的 C++ 对象），
    FormatRange 离开作用域后 format 就被 delete → 直接返回会被 RuntimeError。
    测试场景下我们只需要几个属性，所以这里转成 dict 返回。
    """
    block = doc.findBlockByNumber(block_num)
    layout = block.layout()
    if layout is None:
        return None
    for fr in layout.formats():
        if fr.start <= char_in_block < fr.start + fr.length:
            fmt = fr.format
            color = fmt.foreground().color()
            # 只读用得到的几个属性；fontFamily() 在 PySide6 6.11 deprecated + 易崩
            return {
                "color": color.name().lower() if color.isValid() else None,
                "weight": int(fmt.fontWeight()),
                "italic": bool(fmt.fontItalic()),
                "underline": bool(fmt.fontUnderline()),
            }
    return None


def color_hex(fmt) -> str | None:
    """读前景色（hex）。"""
    if fmt is None:
        return None
    return fmt.get("color")


def font_weight(fmt) -> int | None:
    """读字重（int，QFont.Bold = 700）。"""
    if fmt is None:
        return None
    return fmt.get("weight")


# =============== 单条规则测试 ===============

def _make_doc(text: str) -> QTextDocument:
    """构造一个装填文本的 QTextDocument + 高亮器。

    ⭐ 三个细节：
    1) 先 setDocumentLayout → 否则 block.layout() 为 None → 测试读不到 FormatRange
    2) 先 attach 高亮器，再 setPlainText → 高亮才会跑
    3) rehighlight() 强制同步跑完（避免依赖事件循环）
    """
    doc = QTextDocument()
    doc.setDocumentLayout(QPlainTextDocumentLayout(doc))
    hl = _MarkdownHighlighter(doc)
    doc.setPlainText(text)
    hl.rehighlight()
    QApplication.processEvents()
    return doc


def test_h1_is_blue_and_bold():
    """# H1 标题整行蓝色 + 粗体。"""
    doc = _make_doc("# Title\nbody")
    fmt = find_format_for(doc, "# Title", "# Title")
    assert color_hex(fmt) == "#1976d2", f"H1 应蓝 #1976d2，实际 {color_hex(fmt)}"
    assert font_weight(fmt) == QFont.Bold, f"H1 应粗体，实际 weight={font_weight(fmt)}"
    print(f"[OK] # H1: 颜色 {color_hex(fmt)} + 粗体")


def test_h2_is_blue_lighter():
    """## H2 用 #2196f3（浅一档）。"""
    doc = _make_doc("## Sub\nbody")
    fmt = find_format_for(doc, "## Sub", "## Sub")
    assert color_hex(fmt) == "#2196f3", f"H2 应 #2196f3，实际 {color_hex(fmt)}"
    print(f"[OK] ## H2: 颜色 {color_hex(fmt)}")


def test_h3_is_lightest_blue():
    """### H3 用 #42a5f5。"""
    doc = _make_doc("### Tiny\nbody")
    fmt = find_format_for(doc, "### Tiny", "### Tiny")
    assert color_hex(fmt) == "#42a5f5", f"H3 应 #42a5f5，实际 {color_hex(fmt)}"
    print(f"[OK] ### H3: 颜色 {color_hex(fmt)}")


def test_bold_is_orange_and_bold():
    """**text** 应被上橙色 + 粗体。"""
    doc = _make_doc("**important**")
    fmt = find_format_for(doc, "**important**", "**important**")
    assert color_hex(fmt) == "#ff9800", f"粗体应橙 #ff9800，实际 {color_hex(fmt)}"
    assert font_weight(fmt) == QFont.Bold, f"粗体应粗，实际 weight={font_weight(fmt)}"
    print(f"[OK] **粗体**: {color_hex(fmt)} + 粗体")


def test_italic_is_green_and_italic():
    """*text*（前后不是 *）应被上绿色 + 斜体。"""
    doc = _make_doc("*em*")
    fmt = find_format_for(doc, "*em*", "*em*")
    assert color_hex(fmt) == "#4caf50", f"斜体应绿 #4caf50，实际 {color_hex(fmt)}"
    assert fmt.get("italic") is True, "斜体应斜"
    print(f"[OK] *斜体*: {color_hex(fmt)} + 斜体")


def test_bold_and_italic_dont_collide():
    """**粗体** 中的 * 不应被斜体规则误吃。"""
    doc = _make_doc("**not italic**")
    # 第一个 * 之前应该没颜色（普通文本）
    fmt_star = get_format_at(doc, 0, 0)
    # 整个 **...** 应该是粗体橙
    fmt_bold = find_format_for(doc, "**not italic**", "**not italic**")
    assert color_hex(fmt_bold) == "#ff9800", f"**...** 应橙，实际 {color_hex(fmt_bold)}"
    # 第一个 * 的颜色应该不是绿色（不应被斜体误抓）
    star_color = color_hex(fmt_star)
    assert star_color != "#4caf50", \
        f"** 第一个 * 不应被斜体规则吃掉（绿），实际 {star_color}"
    print(f"[OK] **粗体** 不被 *斜体* 误吃")


def test_inline_code_pink():
    """`code` 应被粉红。"""
    doc = _make_doc("`foo()`")
    fmt = find_format_for(doc, "`foo()`", "`foo()`")
    assert color_hex(fmt) == "#c2185b", f"行内代码应粉 #c2185b，实际 {color_hex(fmt)}"
    print(f"[OK] `行内代码`: 颜色 {color_hex(fmt)}")


def test_code_block_state_persists():
    """```python ... ``` 跨行代码块，整段粉色 + 维持状态。"""
    doc = _make_doc("```python\ndef foo():\n    return 1\n```\nafter")
    # 第 2 行（def foo():）应被代码块格式上色
    fmt = find_format_for(doc, "def foo():", "def foo():")
    assert color_hex(fmt) == "#c2185b", \
        f"代码块内容应粉 #c2185b，实际 {color_hex(fmt)}"
    # 第 5 行（after）应是普通文本（无代码块格式）
    fmt_after = get_format_at(doc, 4, 0)
    assert color_hex(fmt_after) != "#c2185b", \
        f"代码块结束后 'after' 不应是粉色，实际 {color_hex(fmt_after)}"
    print(f"[OK] ```代码块``` 跨行状态正常保持 + 正确关闭")


def test_link_blue_underline():
    """[text](url) 应蓝下划线。"""
    doc = _make_doc("[click](https://example.com)")
    fmt = find_format_for(doc, "[click](https://example.com)", "[click](https://example.com)")
    assert color_hex(fmt) == "#1976d2", f"链接应蓝，实际 {color_hex(fmt)}"
    assert fmt.get("underline") is True, "链接应下划线"
    print(f"[OK] [链接]: 蓝下划线")


def test_image_blue_underline():
    """![alt](path) 也走同一条链接规则（蓝下划线）。"""
    doc = _make_doc("![cat](cat.jpg)")
    fmt = find_format_for(doc, "![cat](cat.jpg)", "![cat](cat.jpg)")
    assert color_hex(fmt) == "#1976d2", f"图片应蓝，实际 {color_hex(fmt)}"
    print(f"[OK] ![图片]: 蓝下划线")


def test_blockquote_gray_italic():
    """> 引用应灰 + 斜。"""
    doc = _make_doc("> quoted text")
    fmt = find_format_for(doc, "> quoted text", "> quoted text")
    assert color_hex(fmt) == "#888888", f"引用应灰 #888，实际 {color_hex(fmt)}"
    assert fmt.get("italic") is True, "引用应斜"
    print(f"[OK] > 引用: 灰 + 斜")


def test_unordered_list_marker_orange():
    """- item 的 '-' 标记应橙色 + 粗。"""
    doc = _make_doc("- bullet item")
    fmt = find_format_for(doc, "- bullet item", "- ")
    assert color_hex(fmt) == "#ff5722", f"列表标记应橙 #ff5722，实际 {color_hex(fmt)}"
    assert font_weight(fmt) == QFont.Bold, f"列表标记应粗，实际 weight={font_weight(fmt)}"
    print(f"[OK] - 列表标记: 橙色粗体")


def test_ordered_list_marker_orange():
    """1. item 的 '1.' 也应橙色。"""
    doc = _make_doc("1. first")
    fmt = find_format_for(doc, "1. first", "1. ")
    assert color_hex(fmt) == "#ff5722", f"有序列表标记应橙，实际 {color_hex(fmt)}"
    print(f"[OK] 1. 有序列表标记: 橙色")


def test_horizontal_rule_gray():
    """--- 应浅灰。"""
    doc = _make_doc("---")
    fmt = find_format_for(doc, "---", "---")
    assert color_hex(fmt) == "#bbbbbb", f"分割线应灰 #bbb，实际 {color_hex(fmt)}"
    print(f"[OK] --- 分割线: 浅灰")


# =============== 集成测试 ===============

def test_integration_with_note_editor():
    """集成进 NoteEditor 后：高亮器被实例化 + 不影响图片插入 / spinbox。"""
    ed = NoteEditor()
    # 1) 高亮器存在
    assert hasattr(ed, '_highlighter'), "NoteEditor 应有 _highlighter"
    assert isinstance(ed._highlighter, _MarkdownHighlighter)

    # 2) 图片插入仍然工作（之前已测过的高频功能）
    ed.set_note("")
    ed.insert_image_markdown("attachments/x.png", "test")
    assert 'class="mindflow-img"' in ed.get_note()

    # 3) spinbox 仍然工作
    ed._spin_img_width.setValue(30)
    assert ed._default_img_width == 30

    # 4) 渲染预览不崩
    ed.set_note("# Title\n\n**bold**\n\n`code`\n\n> quote\n\n- item\n\n![pic](x.png)\n\n---\n\n```python\nfoo()\n```")
    QApplication.processEvents()
    assert "<h1>Title</h1>" in ed._preview.toPlainText() or \
           ed._preview.document().toPlainText(), "预览渲染应不崩"

    print(f"[OK] NoteEditor 集成高亮器 + 图片/spinbox/预览 全部正常")


# =============== 运行 ===============

def main():
    print("=" * 60)
    print("_MarkdownHighlighter 语法高亮测试")
    print("=" * 60)
    try:
        test_h1_is_blue_and_bold()
        test_h2_is_blue_lighter()
        test_h3_is_lightest_blue()
        test_bold_is_orange_and_bold()
        test_italic_is_green_and_italic()
        test_bold_and_italic_dont_collide()
        test_inline_code_pink()
        test_code_block_state_persists()
        test_link_blue_underline()
        test_image_blue_underline()
        test_blockquote_gray_italic()
        test_unordered_list_marker_orange()
        test_ordered_list_marker_orange()
        test_horizontal_rule_gray()
        test_integration_with_note_editor()
        print("\n[ALL PASS] 语法高亮测试 15/15 通过 ✓")
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()