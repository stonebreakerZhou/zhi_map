"""⭐ 全局视觉 token（project-graph 深色 IDE 风）。

设计语言：
- 深色面板（IDE / Figma 风格）
- 青（cyan #22d3ee）作主强调色，紫 #a855f7 作次强调
- 紧凑 4-6px 圆角，无大圆角气泡
- 浅色文字 + 半透明分隔
- JetBrains Mono 等宽字体辅助
- 节点默认色 = cyan，selected / hover 也用 cyan（强烈视觉聚焦）

**不动的**：
- 节点切割高亮 `#ff3b30`（饱和红，在深色背景上识别度最高）
- 节点圆角 RADIUS_NODE = 10（节点本身的圆角和 chrome 圆角分开）

**只动**：chrome（toolbar / sidebar / statusbar / list / button / input）的配色
**不动**：节点 / 边 / 笔记编辑器的内部渲染（保持现有功能与之前调好的）
"""

from __future__ import annotations

# ==================== 品牌色（project-graph 调） ====================

# 主强调色 — 青
COLOR_PRIMARY = "#22d3ee"  # cyan-400
COLOR_PRIMARY_HOVER = "#67e8f9"  # cyan-300（hover 高亮）
COLOR_PRIMARY_TINT = "#164e63"  # cyan-900（active item bg，深色背景下用深 tint）

# 次强调色 — 紫
COLOR_ACCENT_PURPLE = "#a855f7"  # purple-500

# 节点默认色（替代原紫/蓝）
NODE_DEFAULT_COLOR = "#22d3ee"

# 节点选中 / hover 描边叠层色
NODE_SELECT_OVERLAY = "#22d3ee"

# ==================== 中性色（深色面板） ====================

COLOR_BG_BASE = "#0f0f0f"  # 主背景（最深）
COLOR_BG_PANEL = "#1a1a1a"  # 面板背景（dock / dialog）
COLOR_BG_SIDEBAR = "#171717"  # 侧栏 / toolbar
COLOR_BG_HOVER = "#262626"  # hover 态
COLOR_BG_ACTIVE = "#2f2f2f"  # pressed 态

COLOR_BG_CANVAS = "#0f0f0f"  # 画布背景（与 BASE 相同，沉浸感）
COLOR_BG_INPUT = "#0a0a0a"  # 输入框背景（比 panel 更深）

COLOR_BORDER = "#2a2a2a"  # 默认边框（深灰，半透明感）
COLOR_BORDER_HOVER = "#3f3f46"  # hover 边框
COLOR_BORDER_FOCUS = "#22d3ee"  # focus 边框（青色光晕）

COLOR_TEXT = "#e5e7eb"  # 主文字（浅灰）
COLOR_TEXT_MUTED = "#a3a3a3"  # 次文字
COLOR_TEXT_DIM = "#737373"  # 弱文字 / disabled

# ==================== 语义色 ====================

COLOR_DANGER = "#ef4444"  # red-500
COLOR_WARNING = "#ff3b30"  # 切割高亮（保留饱和红）
COLOR_SUCCESS = "#22c55e"  # green-500
COLOR_INFO = "#3b82f6"  # blue-500

# ==================== 字体 ====================

FONT_FAMILY = '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
FONT_FAMILY_MONO = '"JetBrains Mono", "Cascadia Mono", Consolas, monospace'

FONT_SIZE_XS = 9
FONT_SIZE_SM = 10
FONT_SIZE_BASE = 11
FONT_SIZE_LG = 13
FONT_SIZE_XL = 16

# ==================== 圆角 ====================

RADIUS_BUTTON = 6  # project-graph 紧凑圆角
RADIUS_BUBBLE = 8
RADIUS_INPUT = 6
RADIUS_NODE = 10  # 节点本身（保留原值，避免破坏已有节点视觉）

# ==================== 间距 ====================

SIDEBAR_WIDTH = 240
TOPBAR_HEIGHT = 56  # project-graph 偏紧凑
CHAT_MAX_WIDTH = 780

# ==================== 应用级 QSS（深色 IDE 风） ====================
# ⭐ 统一应用 QSS（project-graph 深色 IDE 风格）。
# 由 ``MindFlowWindow.__init__`` 一次性 setStyleSheet 应用。

APP_QSS = f"""
/* === 全局 === */
QMainWindow, QDialog {{
    background: {COLOR_BG_BASE};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BASE}pt;
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_PRIMARY_TINT};
    selection-color: {COLOR_PRIMARY_HOVER};
}}

/* === Dock Widget（左侧 / 右侧面板） === */
QDockWidget {{
    color: {COLOR_TEXT};
    titlebar-close-icon: none;
    font-weight: bold;
    font-size: {FONT_SIZE_SM}pt;
}}
QDockWidget::title {{
    background: {COLOR_BG_SIDEBAR};
    padding: 8px 12px;
    border-bottom: 1px solid {COLOR_BORDER};
    text-align: left;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: {COLOR_TEXT_MUTED};
}}

/* === 工具栏 === */
QToolBar {{
    background: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 4px 8px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: {COLOR_BORDER};
    width: 1px;
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS_BUTTON}px;
    padding: 5px 10px;
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BASE}pt;
}}
QToolButton:hover {{
    background: {COLOR_BG_HOVER};
    border: 1px solid {COLOR_BORDER_HOVER};
}}
QToolButton:pressed {{
    background: {COLOR_BG_ACTIVE};
    border: 1px solid {COLOR_PRIMARY};
}}
QToolButton:disabled {{
    color: {COLOR_TEXT_DIM};
}}

/* === 状态栏 === */
QStatusBar {{
    background: {COLOR_BG_SIDEBAR};
    color: {COLOR_TEXT_MUTED};
    border-top: 1px solid {COLOR_BORDER};
    font-size: {FONT_SIZE_SM}pt;
    font-family: {FONT_FAMILY_MONO};
}}
QStatusBar::item {{
    border: none;
}}

/* === 列表（侧栏导图列表） === */
QListWidget {{
    background: {COLOR_BG_BASE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_BUTTON}px;
    padding: 2px;
    outline: 0;
    color: {COLOR_TEXT};
}}
QListWidget::item {{
    padding: 7px 10px;
    border-radius: {RADIUS_BUTTON - 2}px;
    color: {COLOR_TEXT};
}}
QListWidget::item:hover {{
    background: {COLOR_BG_HOVER};
    color: {COLOR_TEXT};
}}
QListWidget::item:selected {{
    background: {COLOR_PRIMARY_TINT};
    color: {COLOR_PRIMARY_HOVER};
    border-left: 2px solid {COLOR_PRIMARY};
}}

/* === 按钮 === */
QPushButton {{
    background: {COLOR_BG_HOVER};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_BUTTON}px;
    padding: 6px 14px;
    font-family: {FONT_FAMILY};
}}
QPushButton:hover {{
    background: {COLOR_BG_ACTIVE};
    border: 1px solid {COLOR_BORDER_HOVER};
    color: {COLOR_PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background: {COLOR_PRIMARY_TINT};
    border: 1px solid {COLOR_PRIMARY};
}}
QPushButton:disabled {{
    color: {COLOR_TEXT_DIM};
    background: {COLOR_BG_BASE};
}}

/* === 输入框 === */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_INPUT}px;
    padding: 6px 10px;
    font-family: {FONT_FAMILY};
    selection-background-color: {COLOR_PRIMARY_TINT};
    selection-color: {COLOR_PRIMARY_HOVER};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {COLOR_BORDER_FOCUS};
}}

/* === Label === */
QLabel {{
    color: {COLOR_TEXT};
    background: transparent;
}}

/* === Splitter === */
QSplitter::handle {{
    background: {COLOR_BORDER};
}}

/* === ScrollBar === */
QScrollBar:vertical {{
    background: {COLOR_BG_BASE};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_BORDER_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {COLOR_BG_BASE};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLOR_BORDER_HOVER};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* === Menu / MenuBar === */
QMenuBar {{
    background: {COLOR_BG_SIDEBAR};
    color: {COLOR_TEXT};
    border-bottom: 1px solid {COLOR_BORDER};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
}}
QMenuBar::item:selected {{
    background: {COLOR_BG_HOVER};
    color: {COLOR_PRIMARY_HOVER};
}}
QMenu {{
    background: {COLOR_BG_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: {RADIUS_BUTTON - 2}px;
}}
QMenu::item:selected {{
    background: {COLOR_PRIMARY_TINT};
    color: {COLOR_PRIMARY_HOVER};
}}
QMenu::separator {{
    height: 1px;
    background: {COLOR_BORDER};
    margin: 4px 8px;
}}

/* === ToolTip === */
QToolTip {{
    background: {COLOR_BG_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_HOVER};
    padding: 4px 8px;
    border-radius: {RADIUS_BUTTON - 2}px;
    font-family: {FONT_FAMILY_MONO};
    font-size: {FONT_SIZE_SM}pt;
}}
"""

__all__ = [
    "APP_QSS",
    "CHAT_MAX_WIDTH",
    "COLOR_ACCENT_PURPLE",
    "COLOR_BG_ACTIVE",
    "COLOR_BG_BASE",
    "COLOR_BG_CANVAS",
    "COLOR_BG_HOVER",
    "COLOR_BG_INPUT",
    "COLOR_BG_PANEL",
    "COLOR_BG_SIDEBAR",
    "COLOR_BORDER",
    "COLOR_BORDER_FOCUS",
    "COLOR_BORDER_HOVER",
    "COLOR_DANGER",
    "COLOR_INFO",
    "COLOR_PRIMARY",
    "COLOR_PRIMARY_HOVER",
    "COLOR_PRIMARY_TINT",
    "COLOR_SUCCESS",
    "COLOR_TEXT",
    "COLOR_TEXT_DIM",
    "COLOR_TEXT_MUTED",
    "COLOR_WARNING",
    "FONT_FAMILY",
    "FONT_FAMILY_MONO",
    "FONT_SIZE_BASE",
    "FONT_SIZE_LG",
    "FONT_SIZE_SM",
    "FONT_SIZE_XL",
    "FONT_SIZE_XS",
    "NODE_DEFAULT_COLOR",
    "NODE_SELECT_OVERLAY",
    "RADIUS_BUBBLE",
    "RADIUS_BUTTON",
    "RADIUS_INPUT",
    "RADIUS_NODE",
    "SIDEBAR_WIDTH",
    "TOPBAR_HEIGHT",
]
