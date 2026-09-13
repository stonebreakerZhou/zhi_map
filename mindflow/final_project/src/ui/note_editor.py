"""节点笔记编辑器（多行 Markdown + 实时预览）。

设计目标：
- 替换旧的 QLineEdit 单行备注
- 支持 Markdown 语法（粗体/斜体/标题/列表/代码/链接/图片）
- 左侧编辑源码，右侧实时预览渲染结果
- 工具栏一键插入常用 Markdown 语法（不破坏光标位置）
- 文本变化 → 自动保存（防抖 2 秒后发出 save_requested 信号）
- 不引入重依赖：仅 `markdown`（~50KB）+ PySide6 自带 QTextBrowser

P4 负责维护。
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import markdown as _markdown
from PySide6.QtCore import QEvent, QMimeData, QRegularExpression, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPixmap,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.config import DATA_DIR
from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.note_editor")


# ==================== Markdown 渲染（轻量封装）====================

_MD = _markdown.Markdown(
    extensions=[
        "fenced_code",  # ```代码块
        "tables",  # 表格
        "nl2br",  # 换行变 <br>
        "sane_lists",  # 列表更智能
    ]
)


def render_markdown(text: str) -> str:
    """把 Markdown 文本渲染成 HTML 片段。

    性能：单次 < 5ms（500 字以内），用 reset 复用同一个 Markdown 实例。
    """
    try:
        _MD.reset()
        html = _MD.convert(text or "")
        return html
    except Exception as e:
        logger.error(f"Markdown 渲染失败: {e}")
        return f"<p style='color:red'>渲染错误：{e}</p>"


# ==================== HTML 包装（让 QTextBrowser 渲染好看）====================

_BASE_HTML = """\
<html><head><style>
body {{ font-family: 'Microsoft YaHei', sans-serif; line-height: 1.6; color: #222; }}
h1 {{ color: #1976d2; border-bottom: 2px solid #1976d2; padding-bottom: 4px; }}
h2 {{ color: #2196f3; border-bottom: 1px solid #90caf9; padding-bottom: 2px; }}
h3 {{ color: #42a5f5; }}
code {{ background: #f5f5f5; padding: 2px 5px; border-radius: 3px;
       font-family: Consolas, monospace; color: #c2185b; font-size: 90%; }}
pre {{ background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px;
       padding: 8px; overflow-x: auto; }}
pre code {{ background: transparent; padding: 0; color: #333; }}
blockquote {{ border-left: 4px solid #90caf9; margin: 8px 0; padding: 4px 12px;
              color: #555; background: #f5f9ff; }}
table {{ border-collapse: collapse; margin: 8px 0; }}
th, td {{ border: 1px solid #ddd; padding: 4px 8px; }}
th {{ background: #f0f0f0; }}
/* ⭐ img: 不强制 max-width（QTextBrowser 默认就是容器宽）
   真实尺寸由 HTML height 属性控制（Qt 唯一认的尺寸属性）
   不加 height 的图片按原图尺寸渲染（可能溢出容器） */
img, .mindflow-img {{ display: block; margin: 8px auto; border-radius: 4px; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 16px 0; }}
ul, ol {{ padding-left: 24px; }}
a {{ color: #1976d2; }}
</style></head><body>{body}</body></html>
"""


def _wrap_html(body: str) -> str:
    return _BASE_HTML.format(body=body or "<p style='color:#999'>（空）</p>")


# ⭐⭐ 关键设计：图片尺寸控制（实测驱动）
#
# 实测结论（基于 PySide6 6.11.2 + QTextBrowser 逐像素测量 block 高度）：
#   ❌ `<img style="width:Npx">`   QTextBrowser 完全忽略 inline style
#   ❌ `<img width="N">`           width 属性失效（被容器拉伸到 100%）
#   ❌ `<img height="Npx">`        带 px 后缀 → 被解析为 -2（图片直接消失）
#   ✅ `<img height="N">`          **唯一生效**：纯数字 height，Qt 按原图比例反算宽度
#
# 用户体验语义：「width=X%」= 图片占容器宽的 X%（Typst 风格）
#   实现：源码永远存 `width="X%"`（用户可读、可改、可持续）
#         渲染前用原图尺寸反算：height = viewport_w × X% × (img_h / img_w)
#         输出 `<img height="N">`（纯数字，无 px），Qt 渲染出正确大小
#
# 唯一额外开销：解析 HTML 时用 QPixmap 读原图尺寸（每个图 < 1ms）

# 匹配 <img ... class="...mindflow-img..." ... width="X%">
# 抓取：prefix（含 class 到 width="）+ percent数字（含%）+ 后缀（"...>）
# 注意：HTML attr 是 width="50%"，百分号在引号**内**
_IMG_WIDTH_PERCENT_RE = re.compile(
    r'(<img\b[^>]*?\bclass="[^"]*mindflow-img[^"]*"[^>]*?\bwidth=")(\d+%)("[^>]*>)',
    flags=re.IGNORECASE,
)


def _get_src_attr(img_tag: str) -> str | None:
    """从 <img> 标签里取 src="..." 的值（不反转义 — QPixmap 直接读文件系统）。"""
    m = re.search(r'\bsrc="([^"]+)"', img_tag, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _load_pixmap_size(src: str) -> tuple[int, int] | None:
    """加载 src 路径的图片，返回 (width, height)。失败返回 None。

    支持相对路径（相对 DATA_DIR，markdown 标准约定）和绝对路径。
    """
    if not src:
        return None
    candidates = []
    if os.path.isabs(src):
        candidates.append(src)
    else:
        candidates.append(str(Path(DATA_DIR) / src))
        # 兼容 data/ 前缀（早期代码用过）
        if src.startswith("data/"):
            candidates.append(str(Path(src)))
    for path in candidates:
        try:
            if os.path.exists(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    return (pix.width(), pix.height())
        except Exception:
            continue
    return None


def _resolve_img_percent_to_pixels(html: str, viewport_width: int) -> str:
    """⭐⭐ 把 `<img class="mindflow-img" width="X%">` 转成 `<img ... height="N">`（纯数字）。

    为什么用 height 而不是 width？
      Qt 的 QTextBrowser 渲染 HTML 4 富文本时，**只识别纯数字 height 属性**：
      width 属性 / inline style 会被容器强制拉伸；height 带 px 后缀会被解析为 -2。

    工作流程：
    1. 扫描所有 class 含 mindflow-img 的 <img width="X%">
    2. 加载原图尺寸 (src_w, src_h)
    3. desired_width = viewport_width × X / 100
       new_height = desired_width × src_h / src_w
    4. 重组：去掉 width="X%"，插入 height="N"（纯数字，无 px）

    Args:
        html:           markdown 渲染后的 HTML
        viewport_width: 预览区视口宽度 / PDF 可写区宽度（像素）

    Returns:
        新 HTML：mindflow-img 的 width% 已替换为 height=N；找不到原图则原样保留
    """

    def _replace(m: re.Match) -> str:
        full_tag = m.group(0)
        # m.group(2) = '50%' (含百分号)
        percent_str = m.group(2)
        try:
            percent = int(percent_str.rstrip("%"))
        except ValueError:
            return full_tag
        percent = max(1, min(100, percent))

        # 读原图尺寸
        src = _get_src_attr(full_tag)
        size = _load_pixmap_size(src) if src else None

        if not size:
            # 找不到原图 → 保留原 width="X%"（Qt 会拉满容器，但不会崩）
            return full_tag

        src_w, src_h = size
        desired_w = viewport_width * percent / 100.0
        new_h = max(1, int(round(desired_w * src_h / src_w)))

        # m.group(1) = '<img ... class="...mindflow-img..." ... width="'
        # m.group(2) = '50%'
        # m.group(3) = '" ... >'（width attr 闭合引号 + 剩余属性 + '>'）
        # 重组：prefix (去掉 width=") + height="N"（纯数字）+ 后缀
        # ⭐ 注意：QTextBrowser 的 height 属性只接纯数字（"217"），带 "px" 会被解析为 -2
        # 实测验证：height="217" → 渲染 217px 高；height="217px" → 渲染为 -2（消失）
        prefix_no_width = m.group(1)[: -len('width="')]
        # group 3 以 '"' 开头 → 去掉它，合并到 height attr 的闭合引号
        suffix = m.group(3)
        suffix = suffix.removeprefix('"')
        return f'{prefix_no_width}height="{new_h}"{suffix}'

    return _IMG_WIDTH_PERCENT_RE.sub(_replace, html)


# ==================== Markdown 源码语法高亮 ====================


class _MarkdownHighlighter(QSyntaxHighlighter):
    """⭐ 给左侧源码区上色（让用户编辑时像 IDE 一样看清结构）。

    配色对齐 _BASE_HTML 预览风格：
        - 标题（# / ## / ###）  → 蓝（#1976d2 / #2196f3 / #42a5f5）+ 粗
        - **粗体**              → 粗 + 橙（#ff9800）
        - *斜体*                → 斜 + 绿（#4caf50）
        - `行内代码`            → 粉（#c2185b）+ 灰底（#f5f5f5）
        - ```代码块```           → 整段粉 + 等宽字体 + 跨行状态保持
        - [链接](url) / ![图片]  → 蓝下划线
        - > 引用                → 灰 + 斜
        - - / * / 1. 列表        → 标记符橙色
        - --- 分割线             → 浅灰

    实现要点（不踩之前 zoom 翻车的坑）：
        - 只读取当前块文本 + 用 setFormat 上色 → 不动 QTextDocument 内部结构
        - 不重写渲染管线 → 不影响 _render_preview 的 setHtml 流程
        - QSyntaxHighlighter 是 Qt 20 年稳定的官方 API，无黑魔法
    """

    # 块状态：``` 代码块是否处于打开状态
    _STATE_CODE_BLOCK = 1

    def __init__(self, document) -> None:
        super().__init__(document)
        # 预编译所有正则（性能：每次 highlightBlock 复用，不重复编译）
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # ---- 标题 # / ## / ### ----
        for level, color_hex in [(1, "#1976d2"), (2, "#2196f3"), (3, "#42a5f5")]:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_hex))
            fmt.setFontWeight(QFont.Bold)
            # 至少一个 # 后跟空格 + 标题文字（限制 1-6 个 #）
            self._rules.append(
                (
                    QRegularExpression(rf"^#{{{level}}}\s+[^\n]+$"),
                    fmt,
                )
            )

        # ---- **粗体** ----
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmt.setForeground(QColor("#ff9800"))
        self._rules.append(
            (
                QRegularExpression(r"\*\*[^*\n]+\*\*"),
                fmt,
            )
        )

        # ---- *斜体*（必须前后不是 *，避免误吃 **粗体**） ----
        fmt = QTextCharFormat()
        fmt.setFontItalic(True)
        fmt.setForeground(QColor("#4caf50"))
        self._rules.append(
            (
                QRegularExpression(r"(?<!\*)\*[^*\n]+\*(?!\*)"),
                fmt,
            )
        )

        # ---- `行内代码` ----
        fmt = QTextCharFormat()
        fmt.setFontFamily("Consolas, monospace")
        fmt.setForeground(QColor("#c2185b"))
        fmt.setBackground(QColor("#f5f5f5"))
        self._rules.append(
            (
                QRegularExpression(r"`[^`\n]+`"),
                fmt,
            )
        )

        # ---- [链接](url) / ![图片](url) ----
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#1976d2"))
        fmt.setFontUnderline(True)
        self._rules.append(
            (
                QRegularExpression(r"!?\[[^\]\n]+\]\([^)\n]+\)"),
                fmt,
            )
        )

        # ---- > 引用整行 ----
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#888"))
        fmt.setFontItalic(True)
        self._rules.append(
            (
                QRegularExpression(r"^\s*>.*$"),
                fmt,
            )
        )

        # ---- - / * / + / 1. 列表标记 ----
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#ff5722"))
        fmt.setFontWeight(QFont.Bold)
        self._rules.append(
            (
                QRegularExpression(r"^\s*(?:[-*+]|\d+\.)\s"),
                fmt,
            )
        )

        # ---- --- / *** 分割线 ----
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#bbb"))
        self._rules.append(
            (
                QRegularExpression(r"^[-*]{3,}\s*$"),
                fmt,
            )
        )

        # ```代码块``` 围栏行格式（整行粉）
        self._fence_fmt = QTextCharFormat()
        self._fence_fmt.setForeground(QColor("#9e9e9e"))
        self._fence_fmt.setFontFamily("Consolas, monospace")

        # 代码块内容格式（整段粉 + 等宽 + 灰底）
        self._code_block_fmt = QTextCharFormat()
        self._code_block_fmt.setFontFamily("Consolas, monospace")
        self._code_block_fmt.setForeground(QColor("#c2185b"))
        self._code_block_fmt.setBackground(QColor("#fafafa"))

    # ------------------------------------------------------------------
    # Qt 回调：每行文本触发一次
    # ------------------------------------------------------------------

    def highlightBlock(self, text: str) -> None:
        in_code = self.previousBlockState() == self._STATE_CODE_BLOCK

        # ``` 围栏行：切换状态
        if text.lstrip().startswith("```"):
            self.setCurrentBlockState(0 if in_code else self._STATE_CODE_BLOCK)
            self.setFormat(0, len(text), self._fence_fmt)
            return

        # 在代码块内：整段按代码格式上色 + 维持状态
        if in_code:
            self.setFormat(0, len(text), self._code_block_fmt)
            self.setCurrentBlockState(self._STATE_CODE_BLOCK)
            return

        # 普通行：按顺序应用所有规则
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ==================== 编辑器组件 ====================


class NoteEditor(QWidget):
    """节点笔记编辑器。

    用法：
        editor = NoteEditor()
        editor.set_note("# 标题\\n正文...")
        editor.save_requested.connect(lambda text: repo.update_node_note(node_id, text))

    Signals:
        note_changed(str)   — 编辑时实时触发（含每次按键）
        save_requested(str) — 防抖 2 秒后触发，提示调用方入库
        import_attachment_requested()  — 用户点了「📥 导入附件」按钮，请求主窗口弹出选择器
        export_requested(str)         — ⭐ 用户点了「📤 导出」按钮，参数是格式名 "Markdown"/"HTML"/"PDF"
    """

    note_changed = Signal(str)
    save_requested = Signal(str)
    import_attachment_requested = Signal()
    export_requested = Signal(str)
    # ⭐ 新增：点「🖼 图片」时发出，由主窗口弹选择器列出当前节点的图片附件
    insert_image_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_text: str = ""
        self._suppress_signals: bool = False  # 程序设置文本时屏蔽信号
        # ⭐ 图片默认宽度（百分比）— 硬编码 80%，用户可在源码改 width="X%"
        self._default_img_width: int = 80

        self._init_ui()
        self._init_debounce_timer()

    # ==================== UI ====================

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ========== 工具栏 ==========
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())  # 默认 16x16
        toolbar.setStyleSheet(
            "QToolBar { border: none; padding: 4px; background: #1e293b; }"
            "QToolButton { padding: 3px 6px; font-size: 10pt; }"
            # ⭐ 关键修复（2026-09-13）：深色背景下默认 QPushButton 文字看不清
            " QPushButton {"
            "   background: #334155; color: #f1f5f9; border: 1px solid #475569;"
            "   border-radius: 4px; padding: 4px 8px; font-size: 10pt;"
            " }"
            " QPushButton:hover { background: #475569; }"
            " QPushButton:pressed { background: #22d3ee; color: #0f172a; }"
        )
        layout.addWidget(toolbar)

        # ⭐ 导入附件按钮（最高频操作：把原始 .md 附件加载进来二次创作）
        btn_import = QPushButton("📥 导入附件")
        btn_import.setToolTip(
            "从当前节点的 .md 文档附件里选择一份，内容会加载到编辑器\n"
            "（已存在内容时，会在末尾追加分隔线和附件内容，便于拼接多个原始资料）"
        )
        btn_import.clicked.connect(self.import_attachment_requested.emit)
        toolbar.addWidget(btn_import)

        toolbar.addSeparator()

        # 粗体 / 斜体
        tb = QPushButton("B")
        tb.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        tb.setToolTip("粗体 **文字**")
        tb.setFixedWidth(28)
        tb.clicked.connect(lambda: self._wrap_selection("**", "**"))
        toolbar.addWidget(tb)

        ti = QPushButton("I")
        ti.setFont(QFont("Microsoft YaHei", 9, -1, italic=True))
        ti.setToolTip("斜体 *文字*")
        ti.setFixedWidth(28)
        ti.clicked.connect(lambda: self._wrap_selection("*", "*"))
        toolbar.addWidget(ti)

        toolbar.addSeparator()

        # 标题
        for level, label in [(1, "H1"), (2, "H2"), (3, "H3")]:
            btn = QPushButton(label)
            btn.setToolTip(f"标题 {'#' * level} 文字")
            btn.setFixedWidth(36)
            btn.clicked.connect(lambda _=False, lv=level: self._insert_heading(lv))
            toolbar.addWidget(btn)

        toolbar.addSeparator()

        # 列表 / 引用 / 代码
        for marker, label, tip in [
            ("- ", "• 列表", "无序列表"),
            ("1. ", "1. 列表", "有序列表"),
            ("> ", "❝ 引用", "引用块"),
            ("```\n", "</> 代码", "代码块（围栏）"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, m=marker: self._insert_at_line_start(m))
            toolbar.addWidget(btn)

        toolbar.addSeparator()

        # 链接 / 图片 / 分割线
        btn_link = QPushButton("🔗 链接")
        btn_link.setToolTip("链接 [文字](url)")
        btn_link.clicked.connect(self._insert_link)
        toolbar.addWidget(btn_link)

        btn_img = QPushButton("🖼 图片")
        btn_img.setToolTip('图片（默认宽度 80%，插入后可在源码改 width="X%"）')
        btn_img.clicked.connect(self._insert_image)
        toolbar.addWidget(btn_img)

        btn_hr = QPushButton("— 分割")
        btn_hr.setToolTip("分割线 ---")
        btn_hr.clicked.connect(self._insert_hr)
        toolbar.addWidget(btn_hr)

        toolbar.addSeparator()

        # 视图切换：编辑/预览/分栏
        self._btn_edit_only = QPushButton("📝 仅编辑")
        self._btn_edit_only.setCheckable(True)
        self._btn_edit_only.clicked.connect(lambda: self._set_view_mode("edit"))
        toolbar.addWidget(self._btn_edit_only)

        self._btn_split = QPushButton("⬌ 分栏")
        self._btn_split.setCheckable(True)
        self._btn_split.setChecked(True)
        self._btn_split.clicked.connect(lambda: self._set_view_mode("split"))
        toolbar.addWidget(self._btn_split)

        self._btn_preview_only = QPushButton("👁 仅预览")
        self._btn_preview_only.setCheckable(True)
        self._btn_preview_only.clicked.connect(lambda: self._set_view_mode("preview"))
        toolbar.addWidget(self._btn_preview_only)

        toolbar.addSeparator()

        # ⭐ VSCode 风格：「预览」旁直接挂「导出」按钮 — 不必再跑去文件菜单
        # 改用 QPushButton + 弹出 QMenu（QToolButton.InstantPopup 在 Windows 上
        # 即便 ToolButtonTextOnly 也会给菜单箭头留 padding → 文字右边出现两个空格）
        self._btn_export = QPushButton("📤 导出")
        self._btn_export.setToolTip(
            "导出当前节点的最终整理笔记\n（仅输出预览面板内容 — 等同 node.note）"
        )
        export_menu = QMenu(self._btn_export)
        for fmt in ("Markdown", "HTML", "PDF"):
            act = export_menu.addAction(f"导出为 {fmt}")
            act.triggered.connect(
                lambda checked=False, f=fmt: self.export_requested.emit(f)
            )
        self._btn_export.setMenu(export_menu)
        self._btn_export.clicked.connect(
            lambda: export_menu.exec_(
                self._btn_export.mapToGlobal(self._btn_export.rect().bottomLeft())
            )
        )
        toolbar.addWidget(self._btn_export)

        # ========== 编辑区 + 预览区 ==========
        self._splitter = QSplitter()
        layout.addWidget(self._splitter, 1)

        # 左侧：编辑
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "📝 在此输入节点笔记...\n\n"
            "支持 Markdown 语法：\n"
            "  **粗体** *斜体* `代码`\n"
            "  # H1 / ## H2 / ### H3\n"
            "  - 列表项 / 1. 有序列表\n"
            "  > 引用\n"
            "  ```代码块```\n"
            "  [链接](url) ![图片](路径)\n"
            "  --- 分割线"
        )
        self._editor.setFont(QFont("Consolas, Microsoft YaHei", 10))
        self._editor.textChanged.connect(self._on_text_changed)
        # ⭐ 光标移动（之前用于 spinbox 同步，已删除 spinbox 后不再需要此回调）
        self._splitter.addWidget(self._editor)

        # ⭐ 源码区语法高亮（让 # / ** / ` 等一眼能看清）
        self._highlighter = _MarkdownHighlighter(self._editor.document())

        # 右侧：预览（标准 QTextBrowser，不用任何自定义子类）
        self._preview = QTextBrowser()
        # ⭐ 让 QTextBrowser 能解析相对路径图片（DATA_DIR 是附件的根目录，
        # 比如 ![alt](attachments/abc/pic.jpg) → DATA_DIR/attachments/abc/pic.jpg）
        self._preview.setSearchPaths([str(DATA_DIR)])
        # ⭐ 确保垂直滚动条按需显示（默认是 AsNeeded，但显式声明避免某些主题下被吞掉）
        self._preview.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 外链走系统浏览器打开
        self._preview.setOpenExternalLinks(True)
        self._preview.setOpenLinks(True)
        self._preview.setFont(QFont("Microsoft YaHei", 10))
        self._preview.setStyleSheet(
            "QTextBrowser {"
            "  background: #fafafa;"
            "  border: 1px solid #e0e0e0;"
            "  border-radius: 4px;"
            "  padding: 8px;"
            "}"
            # ⭐ 关键：让滚动条明显可见 + 加宽到 14px（默认 8-10px 太细容易找不到）
            "QScrollBar:vertical {"
            "  background: #f0f0f0;"
            "  width: 14px;"
            "  margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #c0c0c0;"
            "  border-radius: 4px;"
            "  min-height: 30px;"
            "}"
            "QScrollBar::handle:vertical:hover {"
            "  background: #a0a0a0;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0; background: none; border: none;"
            "}"
        )
        self._splitter.addWidget(self._preview)

        self._splitter.setSizes([300, 300])
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        # ========== 底部状态栏 ==========
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(4, 0, 4, 0)
        self._status_label = QLabel("字数: 0")
        self._status_label.setStyleSheet("color: #888; font-size: 9pt;")
        status_layout.addWidget(self._status_label)

        status_layout.addStretch()

        self._save_hint = QLabel("✓ 已同步")
        self._save_hint.setStyleSheet("color: #4caf50; font-size: 9pt;")
        status_layout.addWidget(self._save_hint)
        layout.addLayout(status_layout)

        self._set_view_mode("split")

        # ⭐ 进阶便利功能（全部走 Qt 标准 API）：
        # - 快捷键（Ctrl+B/I/K/Shift+I/S/F + F3/Shift+F3）
        # - 查找浮层（QPlainTextEdit.find() + ExtraSelection）
        # - Ctrl+滚轮缩放源码字号
        # - 拖文件到编辑器
        self._init_shortcuts()
        self._init_find_bar()
        self._init_drop()

    def _init_debounce_timer(self) -> None:
        """防抖：停止输入 2 秒后才发 save_requested。"""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(2000)
        self._debounce.timeout.connect(self._on_save_timeout)

    # ==================== 快捷键（全部走 QShortcut + QKeySequence 标准 API）====================

    def _init_shortcuts(self) -> None:
        """绑定编辑器所有标准快捷键。

        ⭐ 关键原则：用的全是 Qt 官方 API（QShortcut + QKeySequence.StandardKey）。
        QPlainTextEdit 默认已经绑了 Ctrl+Z/Y/X/C/V/A —— **不重复绑**避免冲突。
        我们只补 QPlainTextEdit 默认没有的：
          - Ctrl+B / Ctrl+I            粗体 / 斜体（VSCode / Typora / Word 同款）
          - Ctrl+K                     插入链接（VSCode 同款）
          - Ctrl+Shift+I               插入图片
          - Ctrl+S                     立即保存（跳过防抖）
          - Ctrl+F                     弹出查找条
          - F3 / Shift+F3              找下一个 / 上一个（Qt 标准 StandardKey）
          - Ctrl+滚轮                  源码字号缩放（QPlainTextEdit.zoomIn/zoomOut）

        所有 QShortcut 的 context 是 WindowShortcut：在主窗口内任意位置按都生效。
        """
        # --- 文本格式（调用现有工具栏方法，保证行为一致）---
        sc = QShortcut(QKeySequence("Ctrl+B"), self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(lambda: self._wrap_selection("**", "**"))

        sc = QShortcut(QKeySequence("Ctrl+I"), self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(lambda: self._wrap_selection("*", "*"))

        # --- 插入链接 / 图片 ---
        sc = QShortcut(QKeySequence("Ctrl+K"), self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._insert_link)

        sc = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._insert_image)

        # --- 立即保存 ---
        sc = QShortcut(QKeySequence.Save, self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self.save_now)

        # --- 查找（用 Qt 标准 StandardKey，跨平台自动正确：macOS 是 Cmd+F）---
        sc = QShortcut(QKeySequence.Find, self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._show_find_bar)

        sc = QShortcut(QKeySequence.FindNext, self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._find_next)

        sc = QShortcut(QKeySequence.FindPrevious, self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._find_prev)

        # --- Ctrl+滚轮缩放（源码 + 预览都装 eventFilter）---
        # ⭐ QPlainTextEdit.zoomIn/zoomOut 是 Qt 自带的字号缩放 API
        # （Qt Creator / KDevelop / Spyder 都在用），我们只需捕获 Ctrl+wheel 触发它
        # 预览也装上 → Ctrl+wheel 在预览区缩整体（含图片）
        self._editor.viewport().installEventFilter(self)
        self._preview.viewport().installEventFilter(self)

        # --- 撤销/重做按钮已移除（2026-09-13）---
        # 原因：页面左上角已有全局 ↶/↷ 按钮（思维导图级 history），
        # 右侧 note 编辑器的工具栏再放一对会重复 / 让用户搞不清作用域。
        # 文本框自身的 Ctrl+Z / Ctrl+Y 保留 Qt 默认行为（局部文本撤销）。

    # ==================== 查找浮层（用 QPlainTextEdit.find() 标准 API）====================

    def _init_find_bar(self) -> None:
        """构造顶部查找条（默认隐藏，Ctrl+F 弹出）。

        组件：QLineEdit + 上下按钮 + 匹配计数 + 关闭按钮。
        查找逻辑走 QPlainTextEdit.find() —— Qt 标准的"找下一个"实现。
        所有匹配项用 QTextEdit.ExtraSelection 高亮（Qt 标准的"标记区间"做法）。
        """
        self._find_bar = QWidget(self)
        bar_layout = QHBoxLayout(self._find_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(4)

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("查找...")
        self._find_input.setFixedWidth(220)
        self._find_input.setClearButtonEnabled(True)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._find_next)
        bar_layout.addWidget(self._find_input)

        btn_prev = QPushButton("▲")
        btn_prev.setFixedSize(28, 24)
        btn_prev.setToolTip("Shift+F3 上一个")
        btn_prev.clicked.connect(self._find_prev)
        bar_layout.addWidget(btn_prev)

        btn_next = QPushButton("▼")
        btn_next.setFixedSize(28, 24)
        btn_next.setToolTip("F3 下一个")
        btn_next.clicked.connect(self._find_next)
        bar_layout.addWidget(btn_next)

        self._find_count = QLabel("")
        self._find_count.setStyleSheet("color: #888; font-size: 9pt;")
        self._find_count.setMinimumWidth(60)
        bar_layout.addWidget(self._find_count)

        bar_layout.addStretch()

        btn_close = QPushButton("×")
        btn_close.setFixedSize(24, 24)
        btn_close.setToolTip("Esc 关闭")
        btn_close.clicked.connect(self._close_find_bar)
        bar_layout.addWidget(btn_close)

        # 浮动定位在编辑器右上角
        self._find_bar.setStyleSheet(
            "QWidget { background: #fff8dc; border: 1px solid #d4a017;"
            "         border-radius: 4px; }"
        )
        self._find_bar.hide()

    def _show_find_bar(self) -> None:
        """Ctrl+F：弹出查找条 + 焦点给输入框 + 预填选中文字。"""
        # 如果已选中文本，把它填进查找框（VSCode 行为）
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            self._find_input.setText(cursor.selectedText())

        self._find_bar.show()
        self._position_find_bar()
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _position_find_bar(self) -> None:
        """把查找条放到编辑器右上角（在编辑器坐标系内，不是整个 NoteEditor）。"""
        if not self._find_bar.isVisible():
            return
        self._find_bar.adjustSize()
        # ⭐ 关键：self._find_bar 的 parent 是 NoteEditor，所以 move() 用 NoteEditor 坐标
        # 但我们想贴在 _editor（QPlainTextEdit）右上角 → 取 _editor 的全局坐标转 NoteEditor 局部
        from PySide6.QtCore import QPoint

        editor_top_left = self._editor.mapTo(self, QPoint(0, 0))
        x = editor_top_left.x() + self._editor.width() - self._find_bar.width() - 8
        y = editor_top_left.y() + 8
        self._find_bar.move(max(0, x), max(0, y))
        # 提升到最上层（确保不被编辑器遮挡）
        self._find_bar.raise_()

    def _close_find_bar(self) -> None:
        """Esc / 关闭按钮：隐藏查找条 + 清空高亮 + 焦点回编辑器。"""
        self._find_bar.hide()
        self._find_input.clear()
        self._clear_find_highlights()
        self._editor.setFocus(Qt.OtherFocusReason)

    def _on_find_text_changed(self, text: str) -> None:
        """查找内容变 → 从光标位置找下一个 + 全部高亮。"""
        if not text:
            self._clear_find_highlights()
            self._find_count.setText("")
            return
        # 从头开始找一遍（统计 + 高亮）
        cursor = self._editor.textCursor()
        cursor.setPosition(0)
        self._editor.setTextCursor(cursor)
        self._find_next()  # 这个也会刷新高亮 + 计数

    def _find_next(self) -> bool:
        """F3 / Enter：往下找一个。返回是否找到。"""
        return self._find(direction=1)

    def _find_prev(self) -> bool:
        """Shift+F3：往上一个。返回是否找到。"""
        return self._find(direction=-1)

    def _find(self, direction: int) -> bool:
        """共用查找逻辑。

        关键点：
        - QPlainTextEdit.find(text, flags) 是 Qt 自带 API（Qt Creator 同款）
        - flags 决定方向（FindBackward / FindCaseSensitively）
        - 每次 find 后用 ExtraSelection 高亮所有匹配项
        """
        text = self._find_input.text()
        if not text:
            return False

        flags = QTextDocument.FindFlag(0)
        if direction < 0:
            flags |= QTextDocument.FindBackward
        if self._editor.textCursor().hasSelection() and direction > 0:
            # 向下找：从当前选区末尾开始（避免原地不动）
            pass

        # QPlainTextEdit 自带的 find()：会修改 textCursor 到匹配位置 + 滚到可见
        found = self._editor.find(text, flags)

        # 更新所有匹配项高亮 + 计数
        self._highlight_all_find_matches(text)

        # 显示计数（"3/12" 格式：当前 3，共 12）
        match_count = self._count_find_matches(text)
        if match_count == 0:
            self._find_count.setText("无匹配")
            self._find_count.setStyleSheet("color: #d32f2f; font-size: 9pt;")
        else:
            current = self._current_find_index(text) + 1
            self._find_count.setText(f"{current}/{match_count}")
            self._find_count.setStyleSheet("color: #555; font-size: 9pt;")

        if not found:
            # 找不到 → 从头再找（VSCode 行为）
            cursor = self._editor.textCursor()
            if direction > 0:
                cursor.movePosition(QTextCursor.Start)
            else:
                cursor.movePosition(QTextCursor.End)
            self._editor.setTextCursor(cursor)
            # 再试一次
            return self._editor.find(text, flags)
        return found

    def _count_find_matches(self, text: str) -> int:
        """统计 text 在文档中出现的次数（从头扫一遍）。"""
        if not text:
            return 0
        full_text = self._editor.toPlainText()
        return full_text.count(text)

    def _current_find_index(self, text: str) -> int:
        """当前匹配是第几个（0-based）：从文首统计到光标位置之前。"""
        if not text:
            return 0
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            # 用 selectionStart 作为当前位置（光标在选区尾部）
            pos = cursor.selectionStart()
        else:
            pos = cursor.position()
        full_text = self._editor.toPlainText()[:pos]
        return full_text.count(text)

    def _highlight_all_find_matches(self, text: str) -> None:
        """⭐ 用 QTextEdit.ExtraSelection 高亮所有匹配项（Qt 标准做法）。

        为什么用 ExtraSelection 而不是 QSyntaxHighlighter？
        - ExtraSelection 是 QTextEdit 自带的"临时标记"机制，不污染文档
        - 查找完成后调用 _clear_find_highlights 一键清除
        """
        if not text:
            self._clear_find_highlights()
            return
        extra = []
        highlight = QTextEdit.ExtraSelection()
        highlight.format.setBackground(QColor("#fff59d"))  # 浅黄
        cursor = self._editor.textCursor()
        cursor.setPosition(0)
        while True:
            found = self._editor.document().find(text, cursor)
            if found.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = found
            sel.format.setBackground(QColor("#fff59d"))
            extra.append(sel)
            cursor = found
        self._editor.setExtraSelections(extra)

    def _clear_find_highlights(self) -> None:
        """清除所有查找高亮。"""
        self._editor.setExtraSelections([])

    # ==================== 拖拽文件（dragEnterEvent / dropEvent Qt 标准事件）====================

    def _init_drop(self) -> None:
        """让 NoteEditor 接受文件拖入。"""
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        """拖拽进入：检查 mimeData 是否含 URL（文件路径）→ accept。"""
        md: QMimeData = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """⭐ 放下文件 → 分类处理：图片自动拷贝+插入 / .md 自动追加内容。

        路径设计：
        - 图片：拷贝到 DATA_DIR/attachments/<时间戳子目录>/<原文件名>
                → 调 insert_image_markdown(相对路径, alt)
        - .md 文件：读文件内容 → append_text
        - 其他文件：忽略（不报错）
        """
        md: QMimeData = event.mimeData()
        if not md.hasUrls():
            event.ignore()
            return

        event.acceptProposedAction()

        for url in md.urls():
            if not url.isLocalFile():
                continue
            local_path = url.toLocalFile()
            if not os.path.exists(local_path):
                continue

            ext = Path(local_path).suffix.lower()
            # 图片：拷贝 + 插入
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                self._handle_dropped_image(local_path)
            # Markdown 文档：导入内容
            elif ext in (".md", ".markdown", ".txt"):
                self._handle_dropped_markdown(local_path)

    def _handle_dropped_image(self, local_path: str) -> None:
        """拖入的图片：拷贝到 DATA_DIR/attachments/ → 插入到光标位置。

        拷贝到 attachments/ 是为了让图片随项目数据一起管理
        （即便用户把原图从桌面删了，项目里仍能看到）。
        """
        try:
            src = Path(local_path)
            # 子目录用时间戳命名（避免文件名冲突）
            import time

            sub = time.strftime("dropped_%Y%m%d_%H%M%S")
            target_dir = Path(DATA_DIR) / "attachments" / sub
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / src.name
            shutil.copy2(str(src), str(target_path))
            # 相对路径（跟 ImagePickerDialog 一致）
            rel_path = f"attachments/{sub}/{src.name}"
            alt = src.stem
            self.insert_image_markdown(rel_path, alt)
            logger.info(f"拖入图片已拷贝并插入: {rel_path}")
        except Exception as e:
            logger.error(f"拖入图片处理失败: {e}")

    def _handle_dropped_markdown(self, local_path: str) -> None:
        """拖入的 .md 文件：读内容 → append 到编辑器。"""
        try:
            text = Path(local_path).read_text(encoding="utf-8")
            if not text.strip():
                return
            # ⭐ 用 append_text 而不是 set_note：保留当前内容 + 加 --- 分隔
            self.append_text(text)
            logger.info(f"拖入 Markdown 已追加: {local_path}")
        except UnicodeDecodeError:
            # 试 GBK（兼容老 .md）
            try:
                text = Path(local_path).read_text(encoding="gbk")
                self.append_text(text)
            except Exception as e:
                logger.error(f"拖入 .md 解码失败: {e}")
        except Exception as e:
            logger.error(f"拖入 .md 读取失败: {e}")

    # ==================== 事件过滤器（Ctrl+滚轮 + Resize）====================

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        """⭐ Ctrl+滚轮缩放：

        - 在源码区 viewport：QPlainTextEdit.zoomIn/zoomOut（缩字号）
        - 在预览区 viewport：QTextBrowser.zoomIn/zoomOut（缩字号 + 图片）

        ⭐ 关键：QAbstractScrollArea 的 wheel 事件先发到 viewport()，所以
        过滤器必须装在 viewport() 上（之前 zoom 那次的根因就是装错对象）。
        """
        if obj in (self._editor.viewport(), self._preview.viewport()):
            if event.type() == QEvent.Type.Wheel:
                if event.modifiers() & Qt.ControlModifier:
                    delta = event.angleDelta().y()
                    if obj is self._editor.viewport():
                        # 源码：只缩字号（图片是 HTML 字符串，不存在）
                        if delta > 0:
                            self._editor.zoomIn(1)
                        elif delta < 0:
                            self._editor.zoomOut(1)
                    else:
                        # 预览：缩整体（含图片，让用户感觉"图片也跟着缩"）
                        if delta > 0:
                            self._preview.zoomIn(1)
                        elif delta < 0:
                            self._preview.zoomOut(1)
                    event.accept()
                    return True  # 拦截，不让默认滚动
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        """窗口大小变 → 重新定位查找条 + 重新渲染预览（图片按新容器宽度算）。

        ⭐ 关键：图片 width: X% 是按 _preview 视口宽度算像素的，
        容器尺寸变了 → 必须重新渲染才能让图片跟着缩。
        """
        super().resizeEvent(event)
        self._position_find_bar()
        # 重新渲染预览（用新 viewport 宽度重新算图片像素宽度）
        if hasattr(self, "_preview") and self._preview is not None:
            self._render_preview(self._editor.toPlainText())

    # ==================== 工具栏操作 ====================

    def _wrap_selection(self, before: str, after: str) -> None:
        """把选中的文本用 before/after 包裹（没选中则插入空模板）。"""
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"{before}{text}{after}")
            # 选中新插入的部分
            new_pos = cursor.position()
            cursor.setPosition(new_pos - len(text) - len(before) - len(after))
            cursor.setPosition(new_pos, QTextCursor.KeepAnchor)
            self._editor.setTextCursor(cursor)
        else:
            cursor.insertText(f"{before}文字{after}")
            # 选中"文字"
            new_pos = cursor.position()
            cursor.setPosition(new_pos - len("文字") - len(after))
            cursor.setPosition(new_pos - len(after), QTextCursor.KeepAnchor)
            self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    def _insert_at_line_start(self, marker: str) -> None:
        """在光标所在行的开头插入 marker。"""
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.insertText(marker)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    def _insert_heading(self, level: int) -> None:
        """插入 N 级标题（在行首）。"""
        prefix = "#" * level + " "
        self._insert_at_line_start(prefix)

    def _insert_link(self) -> None:
        """插入 [文字](url) 模板。"""
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"[{text}](url)")
        else:
            cursor.insertText("[文字](url)")
            new_pos = cursor.position()
            cursor.setPosition(new_pos - len("(url)"))
            cursor.setPosition(new_pos - len("url)") - 1, QTextCursor.KeepAnchor)
            self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    def _insert_image(self) -> None:
        """⭐ 请求插入图片：发出 insert_image_requested 信号让主窗口弹选择器。

        主窗口从当前节点的附件面板拿到所有图片附件，弹 ImagePickerDialog，
        用户选完一张后回调本组件的 insert_image_markdown(relative_path, alt)。

        没连信号（独立使用）时，fallback 插入通用模板。
        """
        # ⭐ PySide6 的 receivers() 需要 signal 名字符串（"2" 前缀 + "()"）
        if self.receivers("2insert_image_requested()") > 0:
            self.insert_image_requested.emit()
            return
        # fallback：没人监听时插个通用模板
        cursor = self._editor.textCursor()
        cursor.insertText("![说明](images/xxx.jpg)")
        self._editor.setFocus(Qt.OtherFocusReason)

    def _insert_hr(self) -> None:
        """插入分割线 ---。"""
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText("\n\n---\n\n")
        self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    # ==================== 视图模式 ====================

    def _set_view_mode(self, mode: str) -> None:
        """切换编辑/预览/分栏。"""
        self._btn_edit_only.setChecked(mode == "edit")
        self._btn_split.setChecked(mode == "split")
        self._btn_preview_only.setChecked(mode == "preview")

        if mode == "edit":
            self._editor.setVisible(True)
            self._preview.setVisible(False)
        elif mode == "preview":
            self._editor.setVisible(False)
            self._preview.setVisible(True)
        else:  # split
            self._editor.setVisible(True)
            self._preview.setVisible(True)

    # ==================== 信号 ====================

    def _on_text_changed(self) -> None:
        """文本变化：实时预览 + 通知变化 + 重置防抖。"""
        if self._suppress_signals:
            return

        text = self._editor.toPlainText()
        self._current_text = text

        # 实时预览（同步执行，markdown 渲染 < 5ms）
        self._render_preview(text)

        # 状态栏
        self._status_label.setText(f"字数: {len(text)}")
        self._save_hint.setText("● 编辑中…")
        self._save_hint.setStyleSheet("color: #ff9800; font-size: 9pt;")

        # 信号
        self.note_changed.emit(text)
        self._debounce.start()  # 重置 2 秒倒计时

    def _on_save_timeout(self) -> None:
        """防抖到期，触发保存信号。"""
        self._save_hint.setText("✓ 已同步")
        self._save_hint.setStyleSheet("color: #4caf50; font-size: 9pt;")
        self.save_requested.emit(self._current_text)

    # ==================== 预览渲染 ====================

    def _render_preview(self, text: str) -> None:
        """渲染预览：markdown → HTML → 解析 img 百分比 → QTextBrowser.setHtml。

        ⭐ 关键：QTextBrowser 只识别 `<img height="N">` 纯数字属性
        （实测：width 属性 / inline style 都会被容器强制拉伸覆盖）。
        所以我们在 setHtml 前把所有 `<img class="mindflow-img" width="X%">` 转成
        `height="N"`（N = viewport_w × X% × 原图高/原图宽），让 QTextBrowser
        按比例渲染出「占容器 X% 宽」的图片。resize 时重新计算 → 图片跟着容器伸缩。

        这就是 Typst 风格的"按容器百分比"实现。
        """
        html = render_markdown(text or "")
        # ⭐ 解析所有 <img width="X%"> → 按 _preview 当前视口宽度反算 height
        viewport_w = max(self._preview.viewport().width(), 100)  # 至少 100px 防呆
        html = _resolve_img_percent_to_pixels(html, viewport_w)
        self._suppress_signals = True
        self._preview.setHtml(_wrap_html(html))
        self._suppress_signals = False

    # ==================== 公开 API ====================

    def set_note(self, text: str) -> None:
        """程序化设置文本（不触发保存信号）。"""
        self._suppress_signals = True
        self._editor.setPlainText(text or "")
        self._current_text = text or ""
        # 手动更新预览
        self._render_preview(text or "")
        self._status_label.setText(f"字数: {len(text or '')}")
        self._save_hint.setText("✓ 已同步")
        self._save_hint.setStyleSheet("color: #4caf50; font-size: 9pt;")
        self._suppress_signals = False

    def get_note(self) -> str:
        """获取当前文本。"""
        return self._editor.toPlainText()

    def insert_image_markdown(self, relative_path: str, alt: str = "图片") -> None:
        """⭐ 公开 API：在光标位置插入带默认宽度的 HTML <img>。

        参数:
            relative_path: 附件相对路径（attachment.file_path），如
                           "attachments/<subdir>/<file>.jpg"
            alt:          图片替代文字（默认 "图片"，可用 caption 覆盖）

        插入格式（class + width 属性）：
            <img class="mindflow-img" src="path" alt="alt" width="X%">

        - 渲染时 _resolve_img_percent_to_pixels 把 width="X%" 转成 height="N"
          （QTextBrowser 唯一能控制图片尺寸的属性）
        - 用户单图精调：直接改源码里的 width="X%" 数字即可
        """
        # 把 alt 里的 " < > [ ] 和换行去掉（破坏 HTML 属性语法）
        safe_alt = (
            (alt or "图片")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("[", "【")
            .replace("]", "】")
            .replace("\n", " ")
            .strip()
        ) or "图片"
        cursor = self._editor.textCursor()
        # ⭐ class + width 属性形式（用户语义：图片占容器宽的 X%）
        # 渲染时 _resolve_img_percent_to_pixels 会把 width% 转成 height=px
        # （QTextBrowser 唯一能控制图片尺寸的属性）
        md = (
            f'<img class="mindflow-img" src="{relative_path}" alt="{safe_alt}" '
            f'width="{self._default_img_width}%">'
        )
        cursor.insertText(md)
        cursor.insertText("\n")
        self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    def append_text(self, text: str, separator: str = "\n\n---\n\n") -> None:
        """⭐ 追加内容到当前文本末尾（用于「📥 导入附件」按钮）。

        - 如果当前已有内容，先插入分隔符
        - 把光标移到末尾 + 触发 textChanged（让预览刷新 + 启动防抖保存）
        - 不绕过 _suppress_signals（这次编辑是真实编辑，应当触发保存）
        - ⭐ 主动把焦点放回编辑器 + 光标移到末尾，确保用户可立即继续编辑
          （否则从文件选择器 / 对话框返回后焦点可能丢失，看起来"无法编辑"）
        """
        if not text:
            return
        cur = self._editor.toPlainText()
        if cur.strip():
            new_text = cur.rstrip() + separator + text.lstrip()
        else:
            new_text = text.lstrip()
        self.set_note(new_text)  # 先 set_note（避免在 textChanged 循环里反复触发）
        # 显式触发 textChanged — 让预览刷新 + 启动防抖
        self._on_text_changed()

        # ⭐⭐ 关键修复：把光标移到末尾并把焦点还给编辑器
        # 现象：从「导入附件」对话框返回后，焦点可能留在主窗口或工具栏上，
        #      导致用户点击/按键看似无效。
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus(Qt.OtherFocusReason)

    def save_now(self) -> None:
        """立即触发保存（不等待防抖）。"""
        self._debounce.stop()
        self._on_save_timeout()

    def clear(self) -> None:
        """清空编辑器。"""
        self.set_note("")

    def set_save_status(self, ok: bool, message: str = "") -> None:
        """外部可调用以显示保存状态。"""
        if ok:
            self._save_hint.setText(f"✓ {message or '已同步'}")
            self._save_hint.setStyleSheet("color: #4caf50; font-size: 9pt;")
        else:
            self._save_hint.setText(f"✗ {message or '保存失败'}")
            self._save_hint.setStyleSheet("color: #f44336; font-size: 9pt;")


__all__ = [
    "NoteEditor",
    "_MarkdownHighlighter",
    "_wrap_html",
    "render_markdown",
]
