"""MindFlow 主窗口。

整合所有组件：
- 菜单栏：文件 / 编辑 / 视图 / 帮助
- 工具栏：撤销 / 重做 / 新建节点 / 删除节点 / 复习模式
- 侧边栏：导图列表
- 中央：MindMapView 画布
- 右侧：节点详情面板
- 状态栏：节点数 / 当前操作

注：AI 搜索功能已删除——队友模块负责 AI 对话与自动整理，
   本模块只负责思维导图的绘制与编辑。

P4 负责维护。
"""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.config import (
    APP_NAME,
    APP_VERSION,
    NODE_DEFAULT_COLOR,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
)

# ⭐ 知树 (Zhishu) → MindFlow 桥接（导入入口）
from src.integrations.zhishu import (
    LoaderError as ZhishuLoaderError,
)
from src.integrations.zhishu import (
    convert_state as zhishu_convert_state,
)
from src.integrations.zhishu import (
    import_converted as zhishu_import_converted,
)
from src.integrations.zhishu import (
    load_export_file as zhishu_load_export_file,
)
from src.mindmap.graph import MindMapGraph
from src.storage import mindmap_repo
from src.storage.attachment_manager import get_attachment_manager  # ⭐ 多附件管理
from src.storage.db import init_db
from src.ui.attachment_panel import AttachmentPanel
from src.ui.history import HistoryManager  # ⭐ 撤销/重做
from src.ui.image_fullscreen_viewer import ImageFullscreenViewer
from src.ui.image_picker_dialog import ImagePickerDialog
from src.ui.mindmap_view import MindMapView
from src.ui.node_item import NodeItem
from src.ui.note_editor import NoteEditor
from src.ui.theme import APP_QSS, FONT_FAMILY
from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.main_window")


class ViewMode(Enum):
    """⭐ 双模式：浏览（Browse）↔ 编辑（Edit）。

    Browse — 默认进入，沉浸式星空画布，只看不动
    Edit  — 完整 chrome（菜单栏/工具栏/侧栏/详情面板/状态栏）
    """

    BROWSE = "browse"
    EDIT = "edit"


class MindFlowWindow(QMainWindow):
    """MindFlow 主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # 当前打开的导图
        self.current_mindmap_id: str | None = None
        self.current_graph: MindMapGraph | None = None

        # ⭐ 全屏图片浏览器（懒创建）
        self._fullscreen_viewer: ImageFullscreenViewer | None = None

        # ⭐ 撤销/重做历史管理器（独立于具体业务）
        self.history = HistoryManager(self)
        self.history.changed.connect(self._refresh_history_buttons)
        self.history.undo_failed.connect(self._on_history_failure)
        self.history.redo_failed.connect(self._on_history_failure)
        # ⭐ 防卡顿：undo/redo 期间禁止再次触发（同帧内的双击/双 trigger 防御）
        self._undo_busy: bool = False
        self._redo_busy: bool = False
        # ⭐ 防卡顿：最近一次 undo/redo 的时间戳（用于 _HISTORY_DEBOUNCE_MS 时间窗去重）
        self._last_undo_ts: float = 0.0
        self._last_redo_ts: float = 0.0
        # ⭐ 防卡顿：view 全图重画 + fit_to_content 在节点多时耗时，80ms 内点第二次会丢
        # 80ms 既能挡住"用户快速连点两次"，又不会阻断"刻意按节奏连点几次"的合法用例
        self._HISTORY_DEBOUNCE_MS = 80

        # ⭐ 双模式状态（默认 EDIT，初始化完成后切到 BROWSE）
        self._view_mode: ViewMode = ViewMode.EDIT
        self._mode_anim = None  # 模式切换动画引用（防 GC）

        # 初始化数据库
        init_db()

        # ⭐ 应用统一 QSS（对齐 zhi_map 视觉 token）
        self.setStyleSheet(APP_QSS)

        # 初始化 UI
        self._init_central_view()
        self._init_side_panel()
        self._init_detail_panel()  # ⭐ 新增：右侧详情面板（图片预览）
        self._init_menu_bar()
        self._init_toolbar()
        self._init_status_bar()
        self._connect_signals()

        # 刷新导图列表
        self._refresh_mindmap_list()

        # ⭐ 双模式：先建好 browse chrome，再切到 BROWSE（默认进入态）
        self._init_browse_bar()
        self._init_floating_edit_btn()
        self._shortcut_f2 = QShortcut(
            QKeySequence("F2"), self, activated=self._toggle_view_mode
        )
        self._shortcut_esc = QShortcut(
            QKeySequence("Escape"), self, activated=self._on_escape_to_browse
        )

        # ⭐ 启动逻辑（2026-09-13 用户拍板）：
        # 1) 不自动加载第一个 mindmap —— 用户进入 app 看到的是「选择页」
        #    （空星空 + 中央明显「📂 选择导图」提示 / Browse bar 上的「选择导图」按钮是唯一入口）
        # 2) 点 Browse bar 上的「选择导图」→ 选一个 → 才进入该导图的沉浸式 BROWSE
        # （_open_mindmap_by_id 已自动切回 BROWSE + fit_to_content）
        self._set_view_mode(ViewMode.BROWSE)
        self._refresh_browse_bar_menu()

        logger.info("MindFlowWindow 初始化完成")

    # ==================== UI 初始化 ====================

    def _init_central_view(self) -> None:
        """初始化中央画布。"""
        self.view = MindMapView(self)
        self.setCentralWidget(self.view)

    def _init_side_panel(self) -> None:
        """初始化左侧导图列表面板。"""
        self.side_dock = QDockWidget("我的导图", self)
        self.side_dock.setMinimumWidth(220)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题
        title = QLabel("导图列表")
        title.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        layout.addWidget(title)

        # 列表
        self.mindmap_list = QListWidget()
        self.mindmap_list.itemDoubleClicked.connect(self._on_open_mindmap)
        layout.addWidget(self.mindmap_list)

        # 按钮
        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建导图")
        self.btn_new.clicked.connect(self._on_new_mindmap)
        self.btn_delete = QPushButton("删除")
        self.btn_delete.clicked.connect(self._on_delete_mindmap)
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.side_dock.setWidget(container)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.side_dock)

    def _init_detail_panel(self) -> None:
        """⭐ 初始化右侧详情面板（⭐ 节点资料 + 笔记）。"""
        self.detail_dock = QDockWidget("节点详情", self)
        self.detail_dock.setMinimumWidth(320)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题
        title = QLabel("📚 节点资料 · 笔记")
        title.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        layout.addWidget(title)

        # 当前节点名
        self.detail_node_label = QLabel("未选中节点")
        self.detail_node_label.setStyleSheet(
            "color: #a3a3a3; font-size: 10pt; padding: 4px 8px;"
            "background: #1a1a1a; border-radius: 6px;"
            "border: 1px solid #2a2a2a;"
        )
        layout.addWidget(self.detail_node_label)

        # ⭐ 附件面板（紧凑缩略图 — 仅做目录浏览，不再占大头空间）
        self.attachment_panel = AttachmentPanel()
        self.attachment_panel.fullscreen_requested.connect(self._open_image_fullscreen)
        # ⭐ 修复：信号现在带 node_id，连接到新入口
        self.attachment_panel.add_requested.connect(self._on_add_attachment_by_id)
        layout.addWidget(self.attachment_panel, 1)  # ⭐ 拉伸比 1（小）

        # ⭐ 笔记编辑器（⭐ 主战场 — 实时编写最终复习资料）
        # 拉伸比 5，编辑器占大头（约 80% 高度）
        self.note_edit = NoteEditor()
        self.note_edit.save_requested.connect(self._on_save_note)
        # ⭐ 导入附件按钮 → 弹选择器列 .md 附件 → 内容追加到 NoteEditor
        self.note_edit.import_attachment_requested.connect(
            self._on_import_attachment_to_note
        )
        # ⭐ NoteEditor 内的「📤 导出 ▼」按钮（VSCode 风格）— 不必再去文件菜单
        self.note_edit.export_requested.connect(self._on_export_node_from_editor)
        # ⭐ 图片快捷插入 — 点 🖼 按钮弹图片选择器，列出当前节点所有图片附件
        self.note_edit.insert_image_requested.connect(self._on_note_insert_image)
        layout.addWidget(self.note_edit, 5)  # ⭐ 拉伸比 5（大）

        # ⭐ 跟踪当前正在编辑笔记的节点 id（用于 NoteEditor 的「导出」按钮）
        self._current_note_node_id: str | None = None

        self.detail_dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.detail_dock)

    def _init_menu_bar(self) -> None:
        """初始化菜单栏。"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        new_action = QAction("新建导图(&N)", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._on_new_mindmap)
        file_menu.addAction(new_action)

        # ⭐ 从知树 (Zhishu) 导出文件导入
        import_zhishu_action = QAction("📥 从知树导入...(&I)", self)
        import_zhishu_action.setToolTip(
            "从知树 (Zhishu) /api/export 导出的 JSON 文件批量导入为 MindMap"
        )
        import_zhishu_action.triggered.connect(self._on_import_zhishu)
        file_menu.addAction(import_zhishu_action)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("导出(&E)")

        # ⭐ 子菜单 1：整个导图（PNG/JSON/Markdown/HTML/PDF — 5 种格式都保留）
        whole_menu = export_menu.addMenu("整个导图(&W)")
        for fmt in ["PNG", "JSON", "Markdown", "HTML", "PDF"]:
            act = QAction(f"导出为 {fmt}", self)
            act.triggered.connect(lambda checked=False, f=fmt: self._on_export(f))
            whole_menu.addAction(act)

        # ⭐ 子菜单 2：当前节点笔记（仅 Markdown / HTML / PDF — 不含 PNG/JSON）
        node_menu = export_menu.addMenu("当前节点笔记(&N)")
        for fmt in ["Markdown", "HTML", "PDF"]:
            act = QAction(f"导出为 {fmt}", self)
            act.triggered.connect(lambda checked=False, f=fmt: self._on_export_node(f))
            node_menu.addAction(act)

        file_menu.addSeparator()
        quit_action = QAction("退出(&Q)", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")

        # ⭐ 撤销 / 重做（菜单 + 快捷键；工具栏按钮也能触发）
        self.undo_action = QAction("撤销(&U)", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("重做(&R)", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        add_child_action = QAction("添加子节点(&C)", self)
        add_child_action.setShortcut(QKeySequence("Tab"))
        add_child_action.triggered.connect(self._on_add_child_node)
        edit_menu.addAction(add_child_action)

        add_sibling_action = QAction("添加同级节点(&S)", self)
        add_sibling_action.setShortcut(QKeySequence("Return"))
        add_sibling_action.triggered.connect(self._on_add_sibling_node)
        edit_menu.addAction(add_sibling_action)

        delete_node_action = QAction("删除节点(&D)", self)
        delete_node_action.setShortcut(QKeySequence.Delete)
        delete_node_action.triggered.connect(self._on_delete_node)
        edit_menu.addAction(delete_node_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        view_menu.addAction(self.side_dock.toggleViewAction())
        view_menu.addAction(self.detail_dock.toggleViewAction())  # ⭐ 新增

        fit_action = QAction("适应窗口(&F)", self)
        fit_action.setShortcut(QKeySequence("Ctrl+0"))
        fit_action.triggered.connect(self.view.fit_to_content)
        view_menu.addAction(fit_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _init_toolbar(self) -> None:
        """⭐ 工具栏：拆成 2 行（Row 1: 历史/编辑，Row 2: 视图/模式）。

        QMainWindow 默认垂直堆叠多个 QToolBar → 自然形成 2 行。
        """
        # ========== Row 1: 历史 + 节点编辑 ==========
        self._tb_row1 = QToolBar("编辑工具栏")
        self._tb_row1.setMovable(False)
        self._tb_row1.setObjectName("editToolBar")
        self.addToolBar(self._tb_row1)

        # ⭐⭐ 撤销 / 重做 —— 放在最左
        self.tb_undo = QAction("↶ 撤销", self)
        self.tb_undo.setShortcut(QKeySequence.Undo)  # Ctrl+Z（Win/Linux）/ Cmd+Z（Mac）
        self.tb_undo.setToolTip("撤销 (Ctrl+Z)")
        self.tb_undo.setEnabled(False)  # 初始无历史
        self.tb_undo.triggered.connect(self._on_undo)
        self._tb_row1.addAction(self.tb_undo)

        self.tb_redo = QAction("↷ 重做", self)
        self.tb_redo.setShortcut(
            QKeySequence.Redo
        )  # Ctrl+Y（Win/Linux）/ Cmd+Shift+Z（Mac）
        self.tb_redo.setToolTip("重做 (Ctrl+Y)")
        self.tb_redo.setEnabled(False)
        self.tb_redo.triggered.connect(self._on_redo)
        self._tb_row1.addAction(self.tb_redo)

        self._tb_row1.addSeparator()

        # ⭐ 节点编辑
        self.tb_new_node = QAction("📍 新建节点", self)
        self.tb_new_node.triggered.connect(self._on_create_node_no_parent)
        self._tb_row1.addAction(self.tb_new_node)

        self.tb_add_child = QAction("➕ 添加子节点", self)
        self.tb_add_child.triggered.connect(self._on_add_child_node)
        self._tb_row1.addAction(self.tb_add_child)

        self.tb_delete_node = QAction("🗑 删除节点", self)
        self.tb_delete_node.triggered.connect(self._on_delete_node)
        self._tb_row1.addAction(self.tb_delete_node)

        # ========== Row 2: 视图 / 模式切换 ==========
        self._tb_row2 = QToolBar("视图工具栏")
        self._tb_row2.setMovable(False)
        self._tb_row2.setObjectName("viewToolBar")
        self.addToolBar(self._tb_row2)

        self.tb_fullscreen = QAction("🔍 全屏浏览 (F)", self)
        self.tb_fullscreen.setShortcut("F")
        self.tb_fullscreen.setToolTip("全屏查看当前选中节点的图片（F 键）")
        self.tb_fullscreen.triggered.connect(self._open_image_fullscreen)
        self._tb_row2.addAction(self.tb_fullscreen)

        self._tb_row2.addSeparator()

        # ⭐ EDIT 模式下回 BROWSE 的快捷按钮（图标用 emoji + 文字）
        self.tb_back_to_browse = QAction("🌌 浏览导图", self)
        self.tb_back_to_browse.setToolTip("回浏览模式（沉浸看星空）\n快捷键：Esc / F2")
        self.tb_back_to_browse.triggered.connect(
            lambda: self._set_view_mode(ViewMode.BROWSE)
        )
        self._tb_row2.addAction(self.tb_back_to_browse)

    def _init_status_bar(self) -> None:
        """初始化状态栏。"""
        self.setStatusBar(QStatusBar())
        self.status_label = QLabel(f"🟢 就绪 | {APP_NAME} v{APP_VERSION}")
        self.statusBar().addPermanentWidget(self.status_label)
        self._update_status("欢迎使用 MindFlow！请新建或打开导图")

    # ==================== ⭐ Browse / Edit 双模式 chrome ====================

    def _init_browse_bar(self) -> None:
        """⭐ Browse 模式顶部条：logo + 导图下拉 + 编辑按钮（右上角统一一处）。"""
        self._browse_bar = QWidget(self)
        self._browse_bar.setObjectName("browseBar")
        self._browse_bar.setFixedHeight(48)

        layout = QHBoxLayout(self._browse_bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        # Logo（左）
        self._logo_label = QLabel("🪐 MindFlow")
        self._logo_label.setStyleSheet(
            "color: #e5e7eb;"
            " font-size: 14pt;"
            " font-weight: bold;"
            " background: transparent;"
            " border: none;"
            " padding: 0;"
        )
        layout.addWidget(self._logo_label)

        layout.addStretch()

        # 导图下拉（右上角；编辑入口也放这里，跟「选择导图」并列）
        self._mindmap_selector = QToolButton(self._browse_bar)
        self._mindmap_selector.setText("选择导图")
        self._mindmap_selector.setPopupMode(QToolButton.InstantPopup)
        self._mindmap_selector.setCursor(Qt.PointingHandCursor)
        self._mindmap_selector.setStyleSheet(
            "QToolButton {"
            "  background: rgba(255,255,255,0.04);"
            "  color: #e5e7eb;"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  border-radius: 6px;"
            "  padding: 6px 14px;"
            "  font-size: 11pt;"
            "}"
            "QToolButton:hover {"
            "  background: rgba(34,211,238,0.12);"
            "  border: 1px solid rgba(34,211,238,0.5);"
            "  color: #67e8f9;"
            "}"
            "QToolButton::menu-indicator { image: none; }"
        )
        layout.addWidget(self._mindmap_selector)

        # ⭐⭐ 星云视图切换按钮（Browse 内可切换的视图风格）
        # 借鉴 galaxy-view：节点变发光圆点，hover 时浮出 tooltip 显示节点名
        # 沉浸式浏览大图，看不清细节时像星图星系
        self._nebula_btn_in_bar = QToolButton(self._browse_bar)
        self._nebula_btn_in_bar.setText("🌌 星云")
        self._nebula_btn_in_bar.setCursor(Qt.PointingHandCursor)
        self._nebula_btn_in_bar.setCheckable(True)  # ⭐ 切换按钮（按下 = 星云模式）
        self._nebula_btn_in_bar.toggled.connect(self._on_nebula_toggled)
        # 初始非选中（默认 mindmap 视图）
        self._nebula_btn_in_bar.setChecked(False)
        self._nebula_btn_in_bar.setToolTip(
            "切换为星云视图：节点变发光圆点，hover 时显示节点名"
        )
        self._nebula_btn_in_bar.setStyleSheet(
            "QToolButton {"
            "  background: rgba(255,255,255,0.04);"
            "  color: #e5e7eb;"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  border-radius: 6px;"
            "  padding: 6px 14px;"
            "  font-size: 11pt;"
            "}"
            "QToolButton:hover {"
            "  background: rgba(34,211,238,0.12);"
            "  border: 1px solid rgba(34,211,238,0.5);"
            "  color: #67e8f9;"
            "}"
            "QToolButton:checked {"
            "  background: rgba(34,211,238,0.20);"  # ⭐ 选中时 cyan 高亮
            "  border: 1px solid rgba(34,211,238,0.6);"
            "  color: #67e8f9;"
            "  font-weight: bold;"
            "}"
        )
        layout.addWidget(self._nebula_btn_in_bar)

        # 编辑按钮（右上角，「选择导图」旁边）
        self._edit_btn_in_bar = QToolButton(self._browse_bar)
        self._edit_btn_in_bar.setText("✏️ 编辑")
        self._edit_btn_in_bar.setCursor(Qt.PointingHandCursor)
        self._edit_btn_in_bar.clicked.connect(
            lambda: self._set_view_mode(ViewMode.EDIT)
        )
        self._edit_btn_in_bar.setStyleSheet(
            "QToolButton {"
            "  background: #22d3ee;"
            "  color: #0f0f0f;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 6px 16px;"
            "  font-size: 11pt;"
            "  font-weight: bold;"
            "}"
            "QToolButton:hover { background: #67e8f9; }"
            "QToolButton:pressed { background: #155e75; color: #ffffff; }"
        )
        layout.addWidget(self._edit_btn_in_bar)

    def _on_nebula_toggled(self, checked: bool) -> None:
        """⭐ Browse bar 的「🌌 星云」按钮 toggle 时调用：切换视图风格。

        checked=True  → view.set_nebula_mode(True)（节点变发光圆点）
        checked=False → view.set_nebula_mode(False)（恢复 mindmap 视图）

        只在 Browse 模式下生效；切到 Edit 时强制关闭（保持按钮状态同步）。
        """
        # ⭐ Edit 模式不应该进 nebula（编辑时用户需要看清文字）
        # 如果当前是 EDIT 且用户点了按钮 → 切回 BROWSE 再开启
        from src.ui.main_window import ViewMode  # 本地 import 避免循环

        if self._view_mode != ViewMode.BROWSE:
            # 强制同步按钮状态为未选中
            self._nebula_btn_in_bar.blockSignals(True)
            self._nebula_btn_in_bar.setChecked(False)
            self._nebula_btn_in_bar.blockSignals(False)
            return

        # 应用星云模式
        if hasattr(self, "view") and self.view is not None:
            self.view.set_nebula_mode(checked)
        # ⭐ 同步按钮文字（让用户清楚当前状态）
        if checked:
            self._nebula_btn_in_bar.setText("📋 导图")
            self._nebula_btn_in_bar.setToolTip(
                "当前：星云视图（hover 节点查看名字）。点击切换回导图视图"
            )
        else:
            self._nebula_btn_in_bar.setText("🌌 星云")
            self._nebula_btn_in_bar.setToolTip(
                "切换为星云视图：节点变发光圆点，hover 时显示节点名"
            )

    def _refresh_browse_bar_menu(self) -> None:
        """⭐ 重建 browse bar 的导图下拉菜单（在导图列表变更时调用）。"""
        if not hasattr(self, "_mindmap_selector"):
            return
        menu = QMenu(self._mindmap_selector)
        # 复用 dark QSS（与 menuBar 风格一致）
        menu.setStyleSheet(
            "QMenu {"
            "  background: #1a1a1a; color: #e5e7eb;"
            "  border: 1px solid #2a2a2a; padding: 4px;"
            "}"
            "QMenu::item { padding: 6px 24px 6px 12px; border-radius: 4px; }"
            "QMenu::item:selected { background: #164e63; color: #67e8f9; }"
            "QMenu::separator { height: 1px; background: #2a2a2a; margin: 4px 8px; }"
        )

        # 当前导图名（无打开时显示"无"）
        current_title = self._current_mindmap_title()
        header = menu.addAction(
            f"📍 当前：{current_title}" if current_title else "📍 当前：未选择"
        )
        header.setEnabled(False)
        menu.addSeparator()

        # 列出所有导图
        try:
            mindmaps = mindmap_repo.list_mindmaps()
        except Exception:
            mindmaps = []
        if mindmaps:
            for mm in mindmaps:
                title = mm.get("title", "未命名")
                mid = mm.get("id")
                act = menu.addAction(f"   {title}")
                act.triggered.connect(
                    lambda checked=False, m=mid: self._open_mindmap_by_id(m)
                )
        else:
            empty = menu.addAction("   （暂无导图）")
            empty.setEnabled(False)

        menu.addSeparator()
        menu.addAction("➕ 新建导图").triggered.connect(self._on_new_mindmap)
        if self.current_mindmap_id:
            menu.addAction("🗑 删除当前导图").triggered.connect(self._on_delete_mindmap)

        self._mindmap_selector.setMenu(menu)
        # selector 显示当前导图名（或提示）
        if current_title:
            self._mindmap_selector.setText(f"📄 {current_title}  ▼")
            # ⭐ 有当前导图 → 低调样式（避免抢星空的戏）
            self._mindmap_selector.setStyleSheet(
                "QToolButton {"
                "  background: rgba(255,255,255,0.04);"
                "  color: #e5e7eb;"
                "  border: 1px solid rgba(255,255,255,0.08);"
                "  border-radius: 6px;"
                "  padding: 6px 14px;"
                "  font-size: 11pt;"
                "}"
                "QToolButton:hover {"
                "  background: rgba(34,211,238,0.12);"
                "  border: 1px solid rgba(34,211,238,0.5);"
                "  color: #67e8f9;"
                "}"
                "QToolButton::menu-indicator { image: none; }"
            )
        else:
            # ⭐⭐ 没当前导图 → 高亮 cyan + 强调「📂 选导图」（空星空下唯一入口）
            self._mindmap_selector.setText("📂 选导图  ▼")
            self._mindmap_selector.setStyleSheet(
                "QToolButton {"
                "  background: #22d3ee;"
                "  color: #0f0f0f;"
                "  border: none;"
                "  border-radius: 6px;"
                "  padding: 6px 18px;"
                "  font-size: 12pt;"
                "  font-weight: bold;"
                "}"
                "QToolButton:hover { background: #67e8f9; }"
                "QToolButton:pressed { background: #155e75; color: #ffffff; }"
                "QToolButton::menu-indicator { image: none; }"
            )

    def _current_mindmap_title(self) -> str | None:
        """返回当前打开导图的标题（None 表示未选）。"""
        if not self.current_mindmap_id:
            return None
        try:
            mm = mindmap_repo.get_mindmap(self.current_mindmap_id)
            return mm.get("title") if mm else None
        except Exception:
            return None

    def _open_mindmap_by_id(self, mid: str) -> None:
        """通过 id 打开导图（供 browse bar 菜单调用）。"""
        # 复用 _on_open_mindmap 的查找逻辑：mindmap_list 里找对应 item 然后激活
        for i in range(self.mindmap_list.count()):
            it = self.mindmap_list.item(i)
            if it.data(Qt.UserRole) == mid:
                self.mindmap_list.setCurrentItem(it)
                self._on_open_mindmap(it)
                # ⭐ 切完导图后强制回 BROWSE（用户从 Browse bar 选的入口，期望沉浸）
                if self._view_mode != ViewMode.BROWSE:
                    self._set_view_mode(ViewMode.BROWSE)
                return

    def _auto_open_first_mindmap(self) -> None:
        """⭐⭐ 启动时自动加载第一个 mindmap（沉浸式入口）。

        - 有 mindmap：选中列表第一个 + _open_mindmap，让画布默认就铺满图
        - 没有 mindmap：什么都不做（保持空画布 + 「请新建导图」提示）
        """
        try:
            if self.mindmap_list.count() == 0:
                return
            first = self.mindmap_list.item(0)
            mid = first.data(Qt.UserRole)
            if not mid:
                return
            # ⭐ 用 _open_mindmap 直接加载（不走 _on_open_mindmap，
            # 避免它跟列表选中状态纠缠 + 触发侧栏高亮滚动等额外副作用）
            self._open_mindmap(mid, clear_history=True, auto_fit=True)
        except Exception as ex:
            logger.warning(f"启动时自动加载第一个 mindmap 失败: {ex}")

    def _init_floating_edit_btn(self) -> None:
        """⭐ Browse 模式悬浮编辑入口已移除（2026-09-13）。

        原因：右下角悬浮 pill 与右上角 Browse bar 内的「✏️ 编辑」重复，
        留一个就够。统一走 `_edit_btn_in_bar`（Browse bar 右上角，跟
        「选择导图」并列）。此处保留方法（_init_floating_edit_btn /
        resizeEvent 里的引用）以免改外部调用——floating_btn 永远不创建。
        """
        self._floating_edit_btn = None  # 不再创建悬浮 pill

    def resizeEvent(self, event) -> None:
        """⭐ Browse 模式下重新定位 browse bar 顶部拉伸。"""
        super().resizeEvent(event)
        bar = getattr(self, "_browse_bar", None)
        if bar is not None and bar.isVisible():
            bar.setGeometry(0, 0, self.width(), 48)
            bar.raise_()

    def _set_view_mode(self, mode: ViewMode) -> None:
        """⭐ 切换 Browse ↔ Edit。"""
        if self._view_mode == mode:
            return
        self._view_mode = mode

        # 收集所有 chrome：menubar / toolbars / statusbar / docks
        menu = self.menuBar()
        toolbars = self.findChildren(QToolBar)
        status = self.statusBar()
        docks = self.findChildren(QDockWidget)

        if mode == ViewMode.BROWSE:
            # 隐藏所有 chrome
            menu.hide()
            for tb in toolbars:
                tb.hide()
            status.hide()
            for d in docks:
                d.hide()
            # ⭐ browse bar 作为顶层 widget 浮在顶部（不用 setMenuWidget，避免销毁 menubar）
            self._browse_bar.setGeometry(0, 0, self.width(), 48)
            self._browse_bar.show()
            self._browse_bar.raise_()
            # 刷新下拉
            self._refresh_browse_bar_menu()
            # ⭐ Focus mode：进入 Browse 时启用沉浸式聚焦（选中节点自动暗化非邻居）
            self.view.set_focus_mode(True)
            # ⭐⭐ Reveal animation：从 EDIT 切回 BROWSE 时也重放（"重新进入银河"）
            # 仅当画布已有内容时才播放（空状态不播放，避免空页面缩放闪烁）
            if self.view._node_items:
                self.view.play_reveal_animation()
            # ⭐ 编辑入口已统一走 Browse bar 右上角的 _edit_btn_in_bar（2026-09-13）
            # 右下角悬浮 pill 已删除，避免重复
        else:
            # EDIT：卸下 browse bar → 还原所有 chrome
            self._browse_bar.hide()
            menu.show()
            for tb in toolbars:
                tb.show()
            status.show()
            for d in docks:
                d.show()
            # ⭐ Focus mode：进入 Edit 时关闭（用户需要完整视野编辑）
            self.view.set_focus_mode(False)
            # ⭐⭐ 星云模式：进入 Edit 时强制关闭（编辑时需要看清文字）
            self.view.set_nebula_mode(False)
            # ⭐ 同步按钮状态为未选中（避免下次进 Browse 时还在 nebula）
            if hasattr(self, "_nebula_btn_in_bar"):
                self._nebula_btn_in_bar.blockSignals(True)
                self._nebula_btn_in_bar.setChecked(False)
                self._nebula_btn_in_bar.setText("🌌 星云")
                self._nebula_btn_in_bar.blockSignals(False)
            # ⭐ 右下角悬浮 pill 已删除，无须 hide

        self._animate_mode_transition()

    def _toggle_view_mode(self) -> None:
        """F2 触发：在 Browse / Edit 之间切换。"""
        new_mode = (
            ViewMode.EDIT if self._view_mode == ViewMode.BROWSE else ViewMode.BROWSE
        )
        self._set_view_mode(new_mode)

    def _on_escape_to_browse(self) -> None:
        """Esc：EDIT → Browse（Browse 模式按 Esc 不做任何事）。"""
        if self._view_mode == ViewMode.EDIT:
            self._set_view_mode(ViewMode.BROWSE)

    def _animate_mode_transition(self) -> None:
        """⭐ 200ms 渐变（深空感"切换镜头"效果）。"""
        # 清掉上一个 effect（避免叠加）
        old = self.view.graphicsEffect()
        if old is not None:
            self.view.setGraphicsEffect(None)
            try:
                old.deleteLater()
            except RuntimeError:
                pass
        effect = QGraphicsOpacityEffect(self.view)
        self.view.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        if self._view_mode == ViewMode.EDIT:
            anim.setStartValue(0.55)
            anim.setEndValue(1.0)
        else:
            anim.setStartValue(1.0)
            anim.setEndValue(0.85)
        # 动画结束后清理 effect（避免持续占用渲染）
        anim.finished.connect(lambda: self._clear_mode_anim_effect())
        anim.start()
        self._mode_anim = anim

    def _clear_mode_anim_effect(self) -> None:
        try:
            if self.view.graphicsEffect() is not None:
                self.view.setGraphicsEffect(None)
        except RuntimeError:
            pass

    # ==================== ⭐ 撤销 / 重做（TimeEfficient 快照式）====================

    def _refresh_history_buttons(self) -> None:
        """⭐ history.changed 信号回调：刷新工具栏 / 菜单按钮的可用态 + tooltip。"""
        can_u = self.history.can_undo()
        can_r = self.history.can_redo()
        self.tb_undo.setEnabled(can_u)
        self.tb_redo.setEnabled(can_r)
        self.undo_action.setEnabled(can_u)
        self.redo_action.setEnabled(can_r)
        u_label = self.history.peek_undo_label()
        r_label = self.history.peek_redo_label()
        if u_label:
            self.tb_undo.setToolTip(f"撤销 (Ctrl+Z): {u_label}")
        if r_label:
            self.tb_redo.setToolTip(f"重做 (Ctrl+Y): {r_label}")

    def _on_history_failure(self, label: str, error: str) -> None:
        """⭐ undo / redo 失败时的用户可见反馈（status bar + 不阻塞按钮）。"""
        # ⭐ 不弹 modal 框，避免打断操作流；状态栏短期提示即可
        short = error if len(error) <= 80 else error[:77] + "…"
        self._update_status(f"⚠️ {label} 失败：{short}")

    def _on_undo(self) -> None:
        """⭐ 工具栏/菜单/Ctrl+Z 触发：移动 current_index 指针并 restore_snapshot + 重画视图。

        ⭐ 防卡顿策略：80ms 内的重复点击直接 ignore（详见 _HISTORY_DEBOUNCE_MS）。
        原因：view 全图重画期间，主事件循环仍可接收按键/点击事件，
        若用户在 ~100ms 内连点两次，会导致"第一次似乎没响应、第二次连走两步"的体验。
        80ms 时间窗口 + 同步禁用按钮 = 让堆积的 mouseRelease / keyPress 直接被吞掉。
        """
        if not self.current_mindmap_id or self._undo_busy:
            return
        now_ms = time.monotonic() * 1000
        if now_ms - self._last_undo_ts < self._HISTORY_DEBOUNCE_MS:
            return
        self._last_undo_ts = now_ms
        self._undo_busy = True
        self.tb_undo.setEnabled(False)
        self.undo_action.setEnabled(False)
        try:
            entry = self.history.undo()
            if entry is None:
                return
            # ⭐ 走快照式回放：restore_snapshot 完整重写 DB（事务），再 reload view
            try:
                mindmap_repo.restore_snapshot(entry.snapshot)
            except Exception as ex:
                logger.exception(f"restore_snapshot 失败: {entry.label}")
                self.history.undo_failed.emit(entry.label, str(ex))
                return
            self._open_mindmap(
                self.current_mindmap_id, clear_history=False, auto_fit=False
            )
            self._update_status(f"↶ 已撤销：{entry.label}")
        finally:
            self._undo_busy = False
            from PySide6.QtCore import QTimer

            QTimer.singleShot(self._HISTORY_DEBOUNCE_MS, self._refresh_history_buttons)

    def _on_redo(self) -> None:
        """⭐ 工具栏/菜单/Ctrl+Y 触发：移动 current_index 指针并 restore_snapshot + 重画视图。

        ⭐ 防卡顿策略同 _on_undo。
        """
        if not self.current_mindmap_id or self._redo_busy:
            return
        now_ms = time.monotonic() * 1000
        if now_ms - self._last_redo_ts < self._HISTORY_DEBOUNCE_MS:
            return
        self._last_redo_ts = now_ms
        self._redo_busy = True
        self.tb_redo.setEnabled(False)
        self.redo_action.setEnabled(False)
        try:
            entry = self.history.redo()
            if entry is None:
                return
            try:
                mindmap_repo.restore_snapshot(entry.snapshot)
            except Exception as ex:
                logger.exception(f"restore_snapshot 失败: {entry.label}")
                self.history.redo_failed.emit(entry.label, str(ex))
                return
            self._open_mindmap(
                self.current_mindmap_id, clear_history=False, auto_fit=False
            )
            self._update_status(f"↷ 已重做：{entry.label}")
        finally:
            self._redo_busy = False
            from PySide6.QtCore import QTimer

            QTimer.singleShot(self._HISTORY_DEBOUNCE_MS, self._refresh_history_buttons)

    def _track_reload(self, label: str, do_fn) -> None:
        """⭐⭐ 通用 mutation tracker（TimeEfficient 快照式）。

        Args:
            label: 操作描述（用于 tooltip / 状态栏）
            do_fn: 立即执行的 callback（落 DB 即可——do 完后 _open_mindmap 会从 DB reload 整图，
                   无需手动同步 graph / view）。

        流程：do_fn → _open_mindmap(无 history 影响) → take_snapshot → record_step
        """
        try:
            do_fn()
        except Exception:
            logger.exception(f"mutation 执行失败: {label}")
            raise
        if self.current_mindmap_id:
            self._open_mindmap(
                self.current_mindmap_id, clear_history=False, auto_fit=False
            )
            try:
                snap = mindmap_repo.take_snapshot(self.current_mindmap_id)
                self.history.record_step(label, snap)
            except Exception as ex:
                logger.exception(f"record_step 快照失败: {label}")
                self._update_status(f"⚠️ {label} 完成，但未入撤销栈：{ex}")

    def _connect_signals(self) -> None:
        """连接信号槽。"""
        # 节点位置变化
        self.view.node_position_changed.connect(self._on_node_moved)
        # 节点双击编辑
        self.view.node_text_edit_requested.connect(self._on_node_edit)
        # ⭐ 新增：节点选中变化时同步详情面板
        self.view._scene.selectionChanged.connect(self._on_selection_changed)
        # ⭐ 节点右键请求
        # attachment_panel 信号在 _init_detail_panel 里连接
        # - add_requested → _on_add_attachment_by_id
        # - fullscreen_requested → _open_image_fullscreen
        self.view.node_add_child_requested.connect(self._on_add_child_node_for_node)
        self.view.node_add_image_requested.connect(self._on_add_attachment_for_node)
        self.view.node_remove_image_requested.connect(
            self._on_remove_attachment_for_node
        )
        # ⭐ 修复右键删除节点：之前漏接 node_delete_requested，导致右键菜单删除按钮无响应
        self.view.node_delete_requested.connect(self._on_delete_node_for_node)
        # ⭐ 右键改颜色
        self.view.node_color_change_requested.connect(self._on_node_color_change)
        # ⭐ 划线切割删除
        self.view.cut_confirmed.connect(self._on_cut_confirmed)
        # ⭐ 节点图升级：双击空白处创建 / 拖线连接
        self.view.node_create_at_requested.connect(self._on_create_node_at)
        self.view.node_connect_requested.connect(self._on_connect_nodes)

    def _update_status(self, msg: str) -> None:
        """更新状态栏消息。"""
        if self.current_graph:
            count = self.current_graph.node_count
            self.status_label.setText(f"🟢 节点: {count} | {msg}")
        else:
            self.status_label.setText(f"🟢 {msg}")

    # ==================== 导图操作 ====================

    def _refresh_mindmap_list(self) -> None:
        """刷新侧边栏导图列表。"""
        self.mindmap_list.clear()
        maps = mindmap_repo.list_mindmaps()
        for m in maps:
            item = QListWidgetItem(m["title"])
            item.setData(Qt.UserRole, m["id"])
            self.mindmap_list.addItem(item)
        # ⭐ 同步刷新 browse bar 下拉
        self._refresh_browse_bar_menu()
        logger.debug(f"刷新导图列表，共 {len(maps)} 个")

    def _on_new_mindmap(self) -> None:
        """新建导图。"""
        title, ok = QInputDialog.getText(self, "新建导图", "请输入导图标题：")
        if not ok or not title.strip():
            return

        mid = mindmap_repo.create_mindmap(title.strip())
        # 自动创建一个根节点
        root_id = mindmap_repo.add_node(
            mid, title.strip(), x=400, y=300, color=NODE_DEFAULT_COLOR
        )
        mindmap_repo.update_mindmap_title(mid, title.strip())  # 触发 updated_at

        self._refresh_mindmap_list()
        self._open_mindmap(mid)
        self._update_status(f"已创建导图：{title}")

    def _on_import_zhishu(self) -> None:
        """⭐ 从知树 (Zhishu) 导出文件批量导入为 MindMap。

        流程：
        1. 弹文件选择框选 .json（默认路径 = 上次导出位置）
        2. loader 校验 schema
        3. converter 转 MindMap 数据（自动布局）
        4. importer 入库
        5. 弹结果对话框，刷新 sidebar
        """
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择知树导出文件",
            "",
            "知树导出 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            export = zhishu_load_export_file(path)
        except ZhishuLoaderError as exc:
            QMessageBox.critical(self, "导入失败", f"无法读取文件：\n{exc}")
            return
        except Exception as exc:
            logger.exception("知树导入异常")
            QMessageBox.critical(self, "导入失败", f"未知错误：\n{exc}")
            return

        state = export["state"]
        n_session = len(state.get("sessions", []))
        n_branch = len(state.get("branches", []))
        if n_session == 0:
            QMessageBox.warning(
                self, "无内容", "该导出文件不含任何会话，没有可导入的内容。"
            )
            return

        # 二次确认
        reply = QMessageBox.question(
            self,
            "确认导入",
            f"将导入 {n_session} 个会话 / {n_branch} 个分支，"
            f"生成 {n_session} 个 MindMap。\n\n确定继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            result = zhishu_convert_state(state)
            import_result = zhishu_import_converted(result)
        except Exception as exc:
            logger.exception("知树导入转换/入库异常")
            QMessageBox.critical(self, "导入失败", f"转换或入库时出错：\n{exc}")
            return

        self._refresh_mindmap_list()
        # 自动打开第一个新增的 MindMap（如果有）
        if import_result.mindmap_ids:
            first_mid = import_result.mindmap_ids[0]
            self._open_mindmap(first_mid)

        # 报告
        msg = (
            f"✅ 成功导入 {len(import_result.mindmap_ids)} / "
            f"{len(result.mindmaps)} 个 MindMap\n"
            f"   总节点数：{import_result.total_nodes}"
        )
        if import_result.failures:
            msg += f"\n⚠️ 失败 {len(import_result.failures)} 个：\n"
            msg += "\n".join(f"   - {f}" for f in import_result.failures[:5])
            if len(import_result.failures) > 5:
                msg += f"\n   ... (还有 {len(import_result.failures) - 5} 个)"
            QMessageBox.warning(self, "部分导入成功", msg)
        else:
            QMessageBox.information(self, "导入完成", msg)

        self._update_status(f"已从知树导入 {len(import_result.mindmap_ids)} 个 MindMap")

    def _on_delete_mindmap(self) -> None:
        """删除选中的导图。"""
        item = self.mindmap_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先在列表中选择要删除的导图")
            return

        mid = item.data(Qt.UserRole)
        title = item.text()
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除导图「{title}」吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # ⭐ 删导图前清历史（如果删的就是当前打开的）
            self.history.clear()
            mindmap_repo.delete_mindmap(mid)
            self._refresh_mindmap_list()
            self.view.clear()
            self.current_mindmap_id = None
            self.current_graph = None
            self._update_status(f"已删除导图：{title}")

    def _on_open_mindmap(self, item: QListWidgetItem) -> None:
        """打开选中的导图。"""
        mid = item.data(Qt.UserRole)
        self._open_mindmap(mid)

    def _open_mindmap(
        self, mindmap_id: str, clear_history: bool = True, auto_fit: bool = True
    ) -> None:
        """打开导图（核心逻辑）。

        Args:
            mindmap_id: 导图 ID
            clear_history: 是否清空撤销栈（undo/redo 触发的重载必须传 False，
                           否则重画本身会把刚 pop 出去的 entry 给清掉）
            auto_fit: 是否自动调整视图（centerOn / fit_to_content）。
                      用户主动打开（双击列表 / 创建 / 导入）传 True（默认）；
                      内部重载（undo / redo / mutation 后全图重画）必须传 False，
                      否则每改一个节点就把视角强行拉回中央 + 自动缩放——
                      用户的视角就被破坏掉了，体验上就是"画面一直抖"。
        """
        # 加载图（先做存在性检查，避免 view.clear() 之后留下空画布）
        m = mindmap_repo.get_mindmap(mindmap_id)
        if not m:
            QMessageBox.warning(self, "错误", "导图不存在")
            # ⭐ 重置状态：避免 current_mindmap_id 指向已删除的导图
            self.current_mindmap_id = None
            self.current_graph = None
            self.view.clear()
            self.history.clear()
            self._refresh_history_buttons()
            self.setWindowTitle(APP_NAME)
            return

        try:
            graph = mindmap_repo.load_graph(mindmap_id)
        except Exception:
            logger.exception(f"load_graph 失败: {mindmap_id}")
            QMessageBox.warning(self, "错误", "加载导图失败")
            return

        # ⭐⭐ 修复 #2026-09-13：添加附件/节点/边等 mutation 后全图重建会丢选中态。
        # 在 view.clear() 之前记录所有选中节点的 node_id，重建后找回并恢复选中。
        # 这是用户反馈的核心痛点（"我添加一张照片后选中态消失，要重新选一次"）。
        selected_node_ids: list[str] = []
        try:
            for item in self.view._scene.selectedItems():
                if isinstance(item, NodeItem):
                    selected_node_ids.append(item.node_id)
        except RuntimeError:
            pass  # view 已析构（罕见的快速切导图场景）
        # 同时记录 nebula 浮窗 label 状态（如果节点被选中并展开了 label）
        label_node_id: str | None = None
        try:
            for nid, node in self.view._node_items.items():
                try:
                    if node._nebula_label_visible:
                        label_node_id = nid
                        break
                except RuntimeError:
                    pass
        except RuntimeError:
            pass

        # 清空画布
        self.view.clear()

        # 添加所有节点
        for node in graph.all_nodes():
            self.view.add_node_item(
                node_id=node.id,
                text=node.text,
                x=node.pos_x,
                y=node.pos_y,
                color=node.color,
                parent_id=node.parent_id,
                image_path=node.image_path,  # 兼容旧字段
            )

        # ⭐ 加载完后刷新所有节点的附件徽章
        for node in graph.all_nodes():
            count = mindmap_repo.count_attachments(node.id)
            self.view.update_node_attachment_count(node.id, count)

        # ⭐ 重建附加边（任意两节点关系，独立于 parent_id 树）
        extra = [(e.source_id, e.target_id, e.id) for e in graph.get_edges()]
        self.view.set_extra_edges(extra)

        # ⭐⭐ 恢复选中态 + 浮窗 label（用户反馈：添加附件后选中态消失）
        if selected_node_ids:
            try:
                self.view.restore_selection(selected_node_ids)
            except RuntimeError:
                pass
        if label_node_id is not None:
            try:
                new_node = self.view._node_items.get(label_node_id)
                if new_node is not None:
                    new_node.set_nebula_label_visible(True)
            except RuntimeError:
                pass

        self.current_mindmap_id = mindmap_id
        self.current_graph = graph
        self.setWindowTitle(f"{APP_NAME} - {m['title']} v{APP_VERSION}")

        # ⭐ 只有"用户主动打开"时才自动调整视图——后续操作严禁动视角
        if auto_fit:
            # ⭐⭐（2026-09-13 用户拍板）：BROWSE 不再做"星图重排"，直接用 EDIT 手绘位置
            # → 用户在 EDIT 调好的布局 = BROWSE 看到的布局，所见即所得
            if graph.node_count == 1 and graph.root_id:
                # 新建导图：只有一个根节点 → 居中显示（放大到合适大小）
                root_item = self.view._node_items.get(graph.root_id)
                if root_item:
                    self.view.centerOn(root_item)
                    self.view.fit_to_content()
            elif graph.node_count > 1:
                if self._view_mode == ViewMode.BROWSE:
                    # ⭐⭐ BROWSE 模式：节点尽量大 + 全部可见 + 居中
                    self.view.fit_to_content_for_browse(padding=80)
                else:
                    # EDIT 模式：自适应缩放到全部可见
                    self.view.fit_to_content(padding=40)
            else:
                # 空导图 → 重置视图到原点
                self.view.resetTransform()
                self.view.centerOn(0, 0)

            # ⭐⭐ Reveal animation（"星系浮现"开场）：仅 BROWSE 模式播放
            # 借鉴 galaxy-view：scale 从 0.4 缓动到 fit 后的目标值，400ms ease-out
            # EDIT 模式不播放（用户已经看到原貌，不需要"浮现"）
            if self._view_mode == ViewMode.BROWSE:
                self.view.play_reveal_animation()
                # ⭐⭐ 切导图后保留 nebula 模式（用户偏好跨导图一致）
                if (
                    hasattr(self, "_nebula_btn_in_bar")
                    and self._nebula_btn_in_bar.isChecked()
                ):
                    self.view.set_nebula_mode(True)

        self._update_status(f"已打开导图：{m['title']}（{graph.node_count} 个节点）")
        # ⭐ 切导图即清空历史 + bind 新 mindmap（防止跨导图 redo 误回放）
        if clear_history:
            try:
                initial_snap = mindmap_repo.take_snapshot(mindmap_id)
                self.history.bind_mindmap(mindmap_id, initial_snap)
            except Exception:
                logger.exception("bind_mindmap 失败")
                self.history.clear()
        # ⭐ 同步刷新 browse bar 的当前导图名
        self._refresh_browse_bar_menu()
        logger.info(f"打开导图: {m['title']} ({graph.node_count} nodes)")

    # ==================== 节点操作 ====================

    def _on_add_child_node(self) -> None:
        """给选中节点添加子节点。"""
        if not self.current_mindmap_id:
            QMessageBox.warning(self, "提示", "请先打开一个导图")
            return

        selected = self.view.get_selected_node()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中一个节点")
            return

        text, ok = QInputDialog.getText(
            self, "添加子节点", "子节点文本：", text="新节点"
        )
        if not ok or not text.strip():
            return

        # ⭐ closure cell：do 阶段把新建的 nid 写到 box，undo 阶段读出来删
        text_clean = text.strip()
        parent_id = selected.node_id
        new_x = selected.pos().x() + 250
        new_y = selected.pos().y() + 100
        box = {"nid": None}

        def _do():
            mindmap_repo.add_node(
                self.current_mindmap_id,
                text_clean,
                parent_id=parent_id,
                x=new_x,
                y=new_y,
                color=NODE_DEFAULT_COLOR,
            )

        self._track_reload(
            label=f"添加子节点「{text_clean}」",
            do_fn=_do,
        )
        self._update_status(f"已添加子节点：{text_clean}")

    def _on_add_sibling_node(self) -> None:
        """给选中节点添加同级节点。"""
        if not self.current_mindmap_id:
            return

        selected = self.view.get_selected_node()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中一个节点")
            return

        text, ok = QInputDialog.getText(
            self, "添加同级节点", "同级节点文本：", text="新节点"
        )
        if not ok or not text.strip():
            return

        # 找父节点
        parent_id = selected.parent_id if hasattr(selected, "parent_id") else None
        if hasattr(self.current_graph, "get_node"):
            node = self.current_graph.get_node(selected.node_id)
            if node:
                parent_id = node.parent_id

        text_clean = text.strip()
        new_x = selected.pos().x()
        new_y = selected.pos().y() + 120

        def _do():
            mindmap_repo.add_node(
                self.current_mindmap_id,
                text_clean,
                parent_id=parent_id,
                x=new_x,
                y=new_y,
                color=NODE_DEFAULT_COLOR,
            )

        self._track_reload(
            label=f"添加同级节点「{text_clean}」",
            do_fn=_do,
        )

    def _on_delete_node(self) -> None:
        """删除选中节点。"""
        if not self.current_mindmap_id:
            return
        selected = self.view.get_selected_node()
        if not selected:
            return
        self._delete_node_item(selected)

    def _on_delete_node_for_node(self, node_item: NodeItem) -> None:
        """⭐ 右键菜单触发的删除（不依赖 view 选中状态）。"""
        if not self.current_mindmap_id:
            return
        if node_item is None:
            return
        self._delete_node_item(node_item)

    def _delete_node_item(self, node_item: NodeItem) -> None:
        """⭐ 统一的节点删除逻辑（菜单 / 工具栏 / 右键共用）。

        有后代时弹对话框让用户选：
        - 级联删除（连子节点一起删）
        - 仅脱离（子节点保留为新根）
        - 取消
        无后代时直接级联删除（两种模式等价，省一次弹窗）。

        所有路径都进 undo 栈：redo = 删除；undo = 完整子树回写。
        """
        if not self.current_mindmap_id:
            return

        nid = node_item.node_id
        descendant_ids = (
            [n.id for n in self.current_graph.get_descendants(nid)]
            if self.current_graph
            else []
        )
        has_descendants = bool(descendant_ids)

        mode = self._ask_delete_mode(node_item.text) if has_descendants else "cascade"
        if mode == "cancel":
            return

        if mode == "detach":

            def _do_detach():
                self._detach_node_with_descendants(nid)

            label = (
                f"脱离节点「{node_item.text}」（{len(descendant_ids)} 个后代保留为新根）"
                if has_descendants
                else f"删除节点「{node_item.text}」"
            )
            self._track_reload(label, _do_detach)
            self._update_status(label)
            return

        # ⭐ 级联删除模式
        def _do_cascade():
            mindmap_repo.delete_node(nid)

        label = (
            f"级联删除节点「{node_item.text}」及其 {len(descendant_ids)} 个后代"
            if has_descendants
            else f"删除节点「{node_item.text}」"
        )
        self._track_reload(label, _do_cascade)
        self._update_status(label)

    def _ask_delete_mode(self, node_text: str) -> str:
        """⭐ 弹对话框让用户选级联删除 / 仅脱离 / 取消。

        Returns:
            "cascade" | "detach" | "cancel"
        """
        box = QMessageBox(self)
        box.setWindowTitle("删除节点")
        box.setText(f"节点「{node_text}」有子节点。\n请选择删除方式：")
        box.setInformativeText(
            "• 级联删除：连子节点一起删（不可恢复）\n"
            "• 仅脱离：子节点保留为新根（推荐用于剪枝）"
        )
        btn_cascade = box.addButton("级联删除", QMessageBox.DestructiveRole)
        btn_detach = box.addButton("仅脱离（保留子节点）", QMessageBox.AcceptRole)
        btn_cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(btn_detach)  # ⭐ 默认推荐更安全的 detach
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_cascade:
            return "cascade"
        if clicked is btn_detach:
            return "detach"
        return "cancel"

    # ==================== ⭐ 划线切割删除 ====================

    def _on_cut_confirmed(self, nodes_to_delete: list, edges_to_delete: list) -> None:
        """⭐ 处理 view 发来的切割信号。

        与普通删除的关键区别：**后代脱离为根**，而不是级联删除。
        - 划线穿过的节点 → detach（带动画，后代脱离为新根）
        - ⭐ 划线只穿过树形边（db_id=None）→ 调 detach_parent_link（断开父子，子成为新根）
        - ⭐ 划线只穿过附加边（db_id=int）→ 删该边
        - 划线同时穿过节点和边 → 节点 detach 删除 + 边各自处理（不再撞动画）

        ⭐ 整次切割作为**单条**历史（composite entry），一次 undo 全部回滚。
        """
        if not self.current_mindmap_id:
            return

        # 拆分边
        tree_edges: list = []
        extra_edges: list = []
        for edge_item in edges_to_delete:
            eid = getattr(edge_item, "db_id", None)
            if eid is None:
                tree_edges.append(edge_item)
            else:
                extra_edges.append(edge_item)

        # 树形边的 detach 信息（parent_id, child_id）—— 切线切割后 child 重挂 root
        tree_link_snapshots: list[tuple[str, str]] = []
        graph = self.current_graph
        for edge_item in tree_edges:
            try:
                src_id = edge_item.source.node_id
                tgt_id = edge_item.target.node_id
            except (RuntimeError, AttributeError):
                continue
            if graph is None:
                continue
            src_node, tgt_node = graph.get_node(src_id), graph.get_node(tgt_id)
            if not src_node or not tgt_node:
                continue
            if src_node.parent_id == tgt_id:
                tree_link_snapshots.append((tgt_id, src_id))
            elif tgt_node.parent_id == src_id:
                tree_link_snapshots.append((src_id, tgt_id))

        total = len(nodes_to_delete) + len(tree_edges) + len(extra_edges)
        if total == 0:
            return  # 没东西可切

        label = f"划线切割：{len(nodes_to_delete)} 节点 + {len(tree_edges) + len(extra_edges)} 边"

        def _do():
            # 1) detach 节点（带动画）
            for node_item in nodes_to_delete:
                self._detach_node_with_descendants(node_item.node_id)
            # 2) detach 树形边
            for parent_id, child_id in tree_link_snapshots:
                mindmap_repo.detach_parent_link(parent_id, child_id)
            if tree_link_snapshots:
                self.view._rebuild_tree_edges()
            # 3) 删附加边
            for edge_item in extra_edges:
                mindmap_repo.delete_edge(edge_item.db_id)
            self._animate_cut_edges(extra_edges)

        self._track_reload(label, _do)
        self._update_status(label)

    def _detach_node_with_descendants(self, node_id: str) -> None:
        """⭐ detach 节点（仅 DB；graph / view 由 _track_reload → _open_mindmap 重建）。

        detach 语义：删节点本身，后代（直接子）的 parent_id 置 None 成为新根。
        """
        mindmap_repo.detach_node(node_id)

    def _animate_cut_edges(self, edges: list) -> None:
        """⭐ 给划线切掉的边播放淡出动画。

        view 层立即从索引和 scene 中移除（避免残留 EdgeItem 被 hit-test 命中），
        同时启动独立的 QGraphicsOpacityEffect 动画播淡出。动画结束仅清 effect，
        不再尝试 removeItem（已 remove）。
        """
        from src.ui.delete_effect import play_edge_delete_animation

        for edge_item in edges:
            try:
                self.view.remove_edge_item(edge_item)
                anim = play_edge_delete_animation(edge_item, on_finished=None)
                if anim is not None:
                    pool = self.view._active_delete_anims
                    pool.append(anim)
                    anim.finished.connect(
                        lambda a=anim: pool.remove(a) if a in pool else None
                    )
            except RuntimeError:
                pass  # Qt 对象可能已被销毁

    # ==================== ⭐ 图升级：任意节点创建 / 任意两节点连线 ====================

    def _on_create_node_no_parent(self) -> None:
        """⭐ 工具栏"新建节点"按钮（始终可用，不要求选中父节点）。"""
        if not self.current_mindmap_id:
            QMessageBox.warning(self, "提示", "请先打开一个导图")
            return
        text, ok = QInputDialog.getText(self, "新建节点", "节点文本：", text="新节点")
        if not ok or not text.strip():
            return
        # 默认在视图中央偏右创建
        center = self.view.mapToScene(self.view.viewport().rect().center())
        new_x = center.x() + 50
        new_y = center.y() - 20
        try:
            self._create_node_no_parent(text.strip(), new_x, new_y)
        except Exception as e:
            logger.exception("新建节点失败")
            QMessageBox.critical(self, "新建失败", str(e))

    def _on_create_node_at(self, x: float, y: float) -> None:
        """⭐ 双击空白处：在 (x, y) 创建无父节点。"""
        if not self.current_mindmap_id:
            self._update_status("⚠️ 双击空白前请先打开一个导图")
            return
        text, ok = QInputDialog.getText(self, "新建节点", "节点文本：", text="新节点")
        if not ok or not text.strip():
            return
        try:
            self._create_node_no_parent(text.strip(), x, y)
        except Exception as e:
            logger.exception("双击空白创建节点失败")
            QMessageBox.critical(self, "新建失败", str(e))

    def _create_node_no_parent(self, text: str, x: float, y: float) -> None:
        """⭐ 创建无父节点（仅 DB；graph / view 由 _track_reload 重建）。"""

        def _do():
            mindmap_repo.add_node(
                self.current_mindmap_id,
                text,
                parent_id=None,
                x=x,
                y=y,
                color=NODE_DEFAULT_COLOR,
            )

        self._track_reload(
            label=f"新建节点「{text}」",
            do_fn=_do,
        )
        self._update_status(f"已新建节点：{text}")

    def _on_connect_nodes(self, source_id: str, target_id: str) -> None:
        """⭐ 处理 view 发来的拖线连接请求（仅 DB；view 由 _track_reload 重建）。"""
        if not self.current_mindmap_id:
            return

        def _do():
            eid = mindmap_repo.add_edge(self.current_mindmap_id, source_id, target_id)
            if eid is None:
                self._update_status("⚠️ 节点之间已存在连线或自环")
                return
            self._update_status(f"已创建连线：{source_id[:6]} → {target_id[:6]}")

        self._track_reload(
            label=f"创建连线 {source_id[:6]}↔{target_id[:6]}",
            do_fn=_do,
        )

    def _on_node_edit(self, node_item: NodeItem) -> None:
        """双击节点编辑。"""
        new_text, ok = QInputDialog.getText(
            self, "编辑节点", "节点文本：", text=node_item.text
        )
        if not ok or not new_text.strip():
            return

        new_text_clean = new_text.strip()
        nid = node_item.node_id
        # 拿旧文字（仅用于 label / status bar 显示）
        old_text = node_item.text
        if self.current_graph:
            n = self.current_graph.get_node(nid)
            if n:
                old_text = n.text

        def _do():
            mindmap_repo.update_node_text(nid, new_text_clean)
            self._update_status(f"已更新节点：{new_text_clean}")

        self._track_reload(
            label=f"改文字「{old_text[:8]}…」→「{new_text_clean[:8]}…」",
            do_fn=_do,
        )

    def _on_node_color_change(self, node_item: NodeItem, hex_color: str) -> None:
        """⭐ 右键改节点颜色（来自 NodeItem.color_change_requested）。"""
        if not self.current_mindmap_id:
            return
        nid = node_item.node_id
        # 拿旧颜色（仅用于 label / status bar 显示）
        old_color = node_item.color.name() if node_item.color else NODE_DEFAULT_COLOR
        if self.current_graph:
            n = self.current_graph.get_node(nid)
            if n and n.color:
                old_color = n.color

        def _do():
            mindmap_repo.update_node_color(nid, hex_color)
            self._update_status(f"已改颜色：{old_color} → {hex_color}")

        self._track_reload(
            label=f"改颜色「{old_color}」→「{hex_color}」",
            do_fn=_do,
        )

    def _on_node_moved(self, node_id: str, x: float, y: float) -> None:
        """节点拖动后保存位置（snapshot 模式下无需 graph 同步：undo/redo 走全图 reload）。"""
        if not self.current_mindmap_id:
            return
        # ⭐ 跳过微小抖动
        if self.current_graph:
            n = self.current_graph.get_node(node_id)
            if n and abs(n.pos_x - x) < 0.5 and abs(n.pos_y - y) < 0.5:
                return

        def _do():
            mindmap_repo.update_node_position(node_id, x, y)
            logger.debug(f"节点位置保存: {node_id[:8]} -> ({x:.0f}, {y:.0f})")

        self._track_reload(
            label=f"移动节点 → ({x:.0f},{y:.0f})",
            do_fn=_do,
        )

    # ==================== ⭐ 详情面板（节点图片 + 备注）====================
    #
    # 单一职责拆分：
    #   _on_selection_changed → _refresh_detail_panel（信号转发）
    #   _refresh_detail_panel → 同步右栏 + 切换前落库（核心逻辑）
    #   _save_current_note_to → 落库一个节点（DB + graph + history）
    #   _on_save_note         → NoteEditor 防抖信号 → _save_current_note_to
    #   _record_history       → take_snapshot + record_step 共用
    #
    # 关键不变式：note_edit 当前展示的文本 ↔ ``_current_note_node_id``。
    # 任何要修改编辑器文本的路径，都必须先更新 ``_current_note_node_id``；
    # 反之，在修改 ``_current_note_node_id`` 之前，必须先把旧节点的编辑落库。

    def _on_selection_changed(self) -> None:
        """scene.selectionChanged 信号槽（薄封装）。"""
        self._refresh_detail_panel()

    def _refresh_detail_panel(self) -> None:
        """⭐⭐ 单一入口：把右侧详情面板同步到当前选中节点。

        触发场景：scene.selectionChanged 信号 → 可能是用户点击 / focus mode
        暗化刷新 / restore_selection 重建选中 / 节点 hover 等。

        关键设计：仅在 ``selected.node_id`` 与 ``_current_note_node_id`` 不
        一致时才执行——避免 set_note() 把光标重置、覆盖未保存编辑。
        """
        selected = self.view.get_selected_node()
        new_id = selected.node_id if selected else None
        old_id = self._current_note_node_id

        # ⭐⭐ 同节点重复触发 → 直接 return，不碰 note_edit
        if new_id == old_id:
            return

        # 切换前先把上一个节点的未保存编辑立即落库
        if old_id is not None:
            self._save_current_note_to(old_id)

        if selected is None:
            self.detail_node_label.setText("未选中节点")
            self.attachment_panel.clear()
            self.note_edit.clear()
            self._current_note_node_id = None
            return

        self.detail_node_label.setText(f"📌 {selected.text}")
        self.attachment_panel.set_node(selected.node_id)
        self.note_edit.set_note(self._load_note_text_for(selected.node_id))
        self._current_note_node_id = selected.node_id

    def _load_note_text_for(self, node_id: str) -> str:
        """从 graph 读节点的 note（权威来源，与 DB 同步）。"""
        if self.current_graph:
            node = self.current_graph.get_node(node_id)
            if node is not None:
                return node.note or ""
        return ""

    def _save_current_note_to(self, node_id: str) -> None:
        """⭐ 把编辑器当前文本写入指定节点（不等防抖）。

        落库链路：内容比对（避免无意义写）→ DB 更新 → graph 同步 → history 快照。

        应用场景：
        - 切换选中节点前（避免 set_note 覆盖丢内容）
        - NoteEditor 2s 防抖到期（自动保存）
        - view.clear() / _open_mindmap 重建前兜底落库

        注意：**不**触发整图重建（避免 selectionChanged → set_note 把光标重置）。
        """
        note_text = self.note_edit.get_note()
        if self._is_note_text_unchanged(node_id, note_text):
            return

        try:
            mindmap_repo.update_node_note(node_id, note_text)
            # 同步内存 graph（切回该节点能读到最新文本）
            if self.current_graph:
                n = self.current_graph.get_node(node_id)
                if n is not None:
                    n.note = note_text
            self.note_edit.set_save_status(True, "已保存")
            logger.debug(f"节点 {node_id[:8]} 笔记已保存 ({len(note_text)} 字)")
            self._record_history(f"保存笔记 ({len(note_text)} 字)")
        except Exception as e:
            self.note_edit.set_save_status(False, f"保存失败: {e}")
            logger.error(f"节点 {node_id[:8]} 笔记保存失败: {e}")

    def _is_note_text_unchanged(self, node_id: str, text: str) -> bool:
        """text 与 graph 中 node_id 的 note 是否一致（True → 无需写）。"""
        if self.current_graph:
            n = self.current_graph.get_node(node_id)
            if n is not None:
                return (n.note or "") == text
        return False

    def _record_history(self, label: str) -> None:
        """⭐ 推一条撤销栈快照（take_snapshot + record_step 共用）。"""
        if not self.current_mindmap_id:
            return
        try:
            snap = mindmap_repo.take_snapshot(self.current_mindmap_id)
            self.history.record_step(label, snap)
        except Exception as ex:
            logger.exception(f"record_step 快照失败：{label}")
            self._update_status(f"⚠️ {label} 完成，但未入撤销栈：{ex}")

    def _on_save_note(self, note_text: str | None = None) -> None:
        """⭐ NoteEditor.save_requested 信号槽：自动保存（防抖 2 秒后触发）。

        用 ``_current_note_node_id`` 作权威（编辑器文本所属的节点），而不是
        「当前 selected node」——切换瞬间两者会不一致，写到 selected 会写错节点。

        ``note_text`` 参数保留兼容 ``NoteEditor.save_requested`` 信号签名；
        实际文本统一从 ``note_edit`` 读取（与防抖触发时的 ``_current_text`` 同源）。
        """
        del note_text  # 不使用：从 note_edit 读取是权威来源
        nid = self._current_note_node_id
        if nid is None:
            return
        self._save_current_note_to(nid)

    def _on_add_attachment_for_node(self, node_item: NodeItem) -> None:
        """⭐ 右键菜单入口（NodeItem → node_id 适配器）。"""
        self._on_add_attachment_by_id(node_item.node_id)

    def _on_add_attachment_by_id(self, node_id: str) -> None:
        """⭐⭐ 统一入口：给指定节点添加资料附件（图片 + 文档，可多选）。

        调用方：
        - 附件面板 ➕ 按钮 → 信号 add_requested(node_id)
        - 右键菜单"添加资料附件" → _on_add_attachment_for_node → node_id
        """
        if not node_id:
            QMessageBox.warning(self, "提示", "节点 ID 无效")
            return
        from PySide6.QtWidgets import QFileDialog

        from src.storage.attachment_manager import (
            DOCUMENT_EXTS,
            IMAGE_EXTS,
            get_attachment_manager,
        )

        # 文件过滤器：图片 + 文本
        img_filter = " ".join(f"*{ext}" for ext in IMAGE_EXTS)
        doc_filter = " ".join(f"*{ext}" for ext in DOCUMENT_EXTS)
        all_filter = f"所有支持的文件 ({img_filter} {doc_filter});;图片 ({img_filter});;文档 ({doc_filter})"

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择资料附件（可多选）",
            "",
            all_filter,
        )
        if not file_paths:
            return

        mgr = get_attachment_manager()
        added_records: list[
            dict
        ] = []  # ⭐ 给 undo 用：[{aid, file_path, file_type, ...}]
        failed = []

        for fp in file_paths:
            rel = mgr.import_attachment(fp)
            if not rel:
                failed.append(Path(fp).name)
                continue

            file_type = "image" if mgr.is_image(rel) else "document"
            aid = mindmap_repo.add_attachment(
                node_id=node_id,
                file_path=rel,
                file_type=file_type,
            )
            added_records.append({"aid": aid, "file_path": rel, "file_type": file_type})

        if not added_records:
            if failed:
                QMessageBox.warning(self, "全部失败", "\n".join(failed))
            return

        # ⭐⭐ 推一条历史（批量一次 push）。文件已 import + DB 已写，
        # snapshot 模式：undo 时 restore_snapshot 会把 DB 恢复到 add 之前的状态
        def _do():
            self.attachment_panel.set_node(node_id)
            self._refresh_node_badge(node_id)

        self._track_reload(
            label=f"添加 {len(added_records)} 个附件",
            do_fn=_do,
        )

        if failed:
            QMessageBox.warning(
                self,
                "部分失败",
                f"成功添加 {len(added_records)} 个，失败 {len(failed)} 个（格式不支持或过大）：\n"
                + "\n".join(failed),
            )
        else:
            self._update_status(f"✅ 已添加 {len(added_records)} 个附件")
        logger.info(f"节点 {node_id[:8]} 添加 {len(added_records)} 个附件")

    def _on_remove_attachment_for_node(self, node_item: NodeItem) -> None:
        """⭐ 右键菜单：管理节点的资料附件（删除整个节点的所有附件）。

        注意：snapshot 模式下 undo/redo 走 restore_snapshot 全图重建，
        所以 _do 不需要写任何 DB 操作——直接由 _track_reload snapshot 即可。
        """
        count = mindmap_repo.count_attachments(node_item.node_id)
        if count == 0:
            QMessageBox.information(self, "提示", "该节点暂无附件")
            return
        reply = QMessageBox.question(
            self,
            "删除附件",
            f'删除节点「{node_item.text}」的所有 {count} 个附件？\n（请改用详情面板的"🗑 删除"按钮逐个删除）',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        nid = node_item.node_id
        # ⭐ snapshot 模式：直接在这里执行真实删除（snapshot 会在 _do 之后
        # 抓取"已删除"状态）。undo 时 restore_snapshot 会把 DB 恢复到删除前。
        # ⚠️ 文件删除不可恢复（undo 后 row 还在但图片/文档打不开），
        # v1 接受这个 trade-off。
        for att in mindmap_repo.list_attachments(nid):
            mindmap_repo.delete_attachment(att["id"], delete_file=True)

        def _do():
            self.attachment_panel.set_node(nid)
            self._refresh_node_badge(nid)

        self._track_reload(
            label=f"删除 {count} 个附件",
            do_fn=_do,
        )
        self._update_status(f"已清空节点「{node_item.text}」的 {count} 个附件")

    def _refresh_node_badge(self, node_id: str) -> None:
        """⭐ 刷新节点上的附件数徽章（📷N）。"""
        item = self.view.get_node_item(node_id)
        if not item:
            return
        count = mindmap_repo.count_attachments(node_id)
        self.view.update_node_attachment_count(node_id, count)

    def _on_import_attachment_to_note(self) -> None:
        """⭐ NoteEditor 「📥 导入附件」按钮 → 弹文件选择器列 .md 附件 → 内容追加。

        工作流：
            选中节点 → 上传 N 个 .md / .txt 资料附件
              → 在 NoteEditor 里点 📥 导入附件
              → 弹出文件选择器（只列当前节点的 .md/.txt 附件）
              → 选择一份 → 内容追加到 NoteEditor 末尾（已有内容则加分隔线）
              → 用户在编辑器里二次创作整理 → 防抖自动保存到 node.note
        """
        selected = self.view.get_selected_node()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中一个节点")
            return

        # 列出当前节点的 .md / .txt 附件
        all_atts = mindmap_repo.list_attachments(selected.node_id)
        doc_atts = [a for a in all_atts if a["file_type"] == "document"]
        if not doc_atts:
            QMessageBox.information(
                self,
                "导入附件",
                "当前节点没有 .md / .txt 文档附件\n"
                "请先通过 ➕ 按钮或右键菜单「添加资料附件」上传",
            )
            return

        # 弹文件选择器（多选，方便拼接多份原始资料）

        from src.storage.attachment_manager import get_attachment_manager

        am = get_attachment_manager()
        # 把绝对路径拼出来作为 QFileDialog 的可选项
        items = []
        for a in doc_atts:
            abs_path = am.resolve_path(a["file_path"])
            if abs_path and abs_path.exists():
                caption = a.get("caption") or ""
                items.append((str(abs_path), a["file_path"], caption))

        if not items:
            QMessageBox.warning(self, "导入附件", "附件文件在磁盘上找不到")
            return

        # 自定义 dialog：让用户看到 caption 而不只是 hash 名
        chosen = self._pick_doc_attachment_dialog(items)
        if not chosen:
            return

        # 拼接所有选中附件的内容（用分隔线分隔）
        parts: list[str] = []
        for abs_path, rel_path, caption in chosen:
            text = Path(abs_path).read_text(encoding="utf-8")
            header = f"<!-- 导入自附件: {caption or Path(rel_path).name} -->\n\n"
            parts.append(header + text)

        combined = "\n\n---\n\n".join(parts)
        self.note_edit.append_text(combined)
        self.statusBar().showMessage(
            f"已导入 {len(chosen)} 份附件到笔记（待 2 秒自动保存）", 3000
        )
        logger.info(f"节点 {selected.node_id[:8]} 导入 {len(chosen)} 份附件到 note")

    # ==================== 图片快捷插入（NoteEditor 🖼 按钮）====================

    def _on_note_insert_image(self) -> None:
        """⭐ 处理 NoteEditor 「🖼 图片」按钮的回调：
        1. 没选节点 → 提示
        2. 节点没图片附件 → 提示（指引去附件面板 ➕ 添加）
        3. 弹 ImagePickerDialog → 用户选一张 → 插入到光标位置
        """
        from PySide6.QtWidgets import QMessageBox

        if not self._current_note_node_id:
            QMessageBox.information(self, "提示", "请先选中一个节点，然后再插入图片。")
            return

        # ⭐ 从附件面板拿当前节点的图片附件（封面 + 其它图）
        images = self.attachment_panel.get_image_attachments()
        dlg = ImagePickerDialog(images, parent=self)
        # 把窗口置中到主窗口
        dlg.move(self.geometry().center() - dlg.rect().center())
        if dlg.exec() and dlg.picked:
            rel_path, alt = dlg.picked
            self.note_edit.insert_image_markdown(rel_path, alt)
            self.statusBar().showMessage(f"已插入图片: ![{alt}]({rel_path})", 3000)
            logger.info(f"节点 {self._current_note_node_id[:8]} 插入图片: {rel_path}")

    def _pick_doc_attachment_dialog(self, items: list) -> list | None:
        """⭐ 自定义对话框：拼接顺序 = 用户勾选的先后顺序。

        设计原则：
            - 拼接顺序**不是**列表位置，而是**用户勾选的先后顺序**
            - 先勾选的 → 出现在前面；后勾选的 → 出现在后面
            - 取消勾选 → 从顺序中移除
            - 默认全部不勾选，让用户主动选择（避免误操作）

        视觉提示：
            - 每个 item 显示勾选序号（① ② ③ ...），让用户清楚知道当前顺序
            - 列表里也展示原始位置编号，方便识别附件

        Args:
            items: [(abs_path, rel_path, caption), ...]

        Returns:
            按勾选先后顺序排列的 [(abs_path, rel_path, caption), ...]，None 表示取消
        """
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("选择要导入的附件（按勾选顺序拼接）")
        dlg.resize(640, 380)
        root = QVBoxLayout(dlg)

        hint = QLabel(
            "📌 拼接顺序 = 你的勾选顺序\n"
            "   先勾选的放在前面，后勾选的放在后面；取消勾选会从拼接中移除\n"
            "   （列表里每个 item 前的 ① ② ③ 显示当前的拼接顺序）"
        )
        hint.setStyleSheet(
            "color: #727680; font-size: 9pt; padding: 4px; background: transparent;"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ⭐ 跟踪勾选顺序的列表（存 item data，便于快速查重）
        selection_order: list = []  # 每个元素 = (abs_path, rel_path, caption)

        order_label = QLabel("顺序：空")
        order_label.setStyleSheet(
            "color: #22d3ee; font-weight: bold; background: transparent;"
        )

        def _update_order_label() -> None:
            if not selection_order:
                order_label.setText("顺序：空")
            else:
                names = [(d[2] or Path(d[0]).name)[:10] for d in selection_order]
                order_label.setText("顺序： " + " → ".join(names))

        def _refresh_labels() -> None:
            """刷新每个 item 的顺序标签 ① ② ③。"""
            for i in range(list_widget.count()):
                it = list_widget.item(i)
                d = it.data(Qt.UserRole)
                if not d:
                    continue
                seq = selection_order.index(d) + 1 if d in selection_order else None
                marker = f"{seq}" if seq else " "
                prefix_marker = f"[{marker}]"
                base_name = Path(d[0]).name
                if d[2]:
                    text = f"{prefix_marker} {d[2]}    ({base_name})"
                else:
                    text = f"{prefix_marker} 📄 {base_name}"
                it.setText(text)
            _update_order_label()

        def _on_check_changed(it: QListWidgetItem) -> None:
            """勾选状态变化 → 更新 selection_order。"""
            d = it.data(Qt.UserRole)
            if not d:
                return
            if it.checkState() == Qt.Checked:
                if d not in selection_order:
                    selection_order.append(d)
            else:
                if d in selection_order:
                    selection_order.remove(d)
            _refresh_labels()

        def _set_all(state: Qt.CheckState) -> None:
            """全选/全不选 — 全选时按列表顺序追加。"""
            selection_order.clear()
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(state)
                if state == Qt.Checked:
                    d = list_widget.item(i).data(Qt.UserRole)
                    if d:
                        selection_order.append(d)
            _refresh_labels()

        # ---- 中间：列表 ----
        list_widget = QListWidget()
        list_widget.setStyleSheet(
            "QListWidget { font-size: 10pt; outline: 0;"
            " border: 1px solid #2a2a2a; border-radius: 6px;"
            " background: #0f0f0f; color: #e5e7eb; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #1a1a1a;"
            " color: #e5e7eb; border-radius: 0; }"
            "QListWidget::item:hover { background: #262626; color: #e5e7eb; }"
            # ⭐ 关键：选中时必须显式指定文字色，否则系统会把它渲成白色
            "QListWidget::item:selected { background: #164e63; color: #67e8f9;"
            " font-weight: bold; border-left: 2px solid #22d3ee; }"
            "QListWidget::item:selected:hover { background: #155e75; color: #67e8f9; }"
        )
        for abs_path, rel_path, caption in items:
            base_name = Path(abs_path).name
            if caption:
                text = f"📄 {caption}    ({base_name})"
            else:
                text = f"📄 {base_name}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, (abs_path, rel_path, caption))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)  # ⭐ 默认全部不勾选
            list_widget.addItem(it)

        list_widget.itemChanged.connect(_on_check_changed)
        root.addWidget(list_widget, 1)

        # ---- 底部：快捷按钮 + 顺序标签 + OK/Cancel ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        btn_all = QPushButton("☑ 全选")
        btn_all.setToolTip("按列表顺序勾选全部附件")
        btn_all.clicked.connect(lambda: _set_all(Qt.Checked))
        btn_row.addWidget(btn_all)

        btn_none = QPushButton("☐ 全不选")
        btn_none.setToolTip("清空所有勾选")
        btn_none.clicked.connect(lambda: _set_all(Qt.Unchecked))
        btn_row.addWidget(btn_none)

        btn_row.addStretch()
        btn_row.addWidget(order_label)
        root.addLayout(btn_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        root.addWidget(btn_box)

        if dlg.exec() != QDialog.Accepted:
            return None

        # ⭐ 按勾选顺序返回
        return list(selection_order)

    def _on_add_child_node_for_node(self, node_item: NodeItem) -> None:
        """⭐ 右键添加子节点（先选中目标节点，再复用现有逻辑）。"""
        node_item.setSelected(True)
        self._on_add_child_node()

    # ==================== ⭐ 全屏图片浏览 ====================

    def _open_image_fullscreen(self) -> None:
        """打开全屏图片浏览器（⭐ 核心浏览体验）。

        触发方式：
        - 选中节点 + 按 F 键
        - 详情面板「全屏浏览」按钮
        - 详情面板图片双击

        ⭐ 多附件：优先使用附件面板当前选中的图；否则取该节点第一张图。
        """
        selected = self.view.get_selected_node()
        if not selected:
            QMessageBox.information(self, "提示", "请先选中一个节点")
            return

        # ⭐ 优先用附件面板当前选中
        att = (
            self.attachment_panel.get_current_attachment()
            if self.attachment_panel
            else None
        )
        if not att or att.get("file_type") != "image":
            atts = [
                a
                for a in mindmap_repo.list_attachments(selected.node_id)
                if a.get("file_type") == "image"
            ]
            if not atts:
                QMessageBox.information(self, "提示", "该节点没有图片附件")
                return
            att = atts[0]

        mgr = get_attachment_manager()
        abs_path = mgr.resolve_path(att["file_path"])
        if not abs_path or not abs_path.exists():
            QMessageBox.warning(self, "错误", f"图片文件不存在：\n{abs_path}")
            return

        # 找当前附件在「该节点图片列表」中的位置
        node_images = self.attachment_panel.get_image_attachments()
        if not node_images:
            return
        try:
            current_index = next(
                i for i, a in enumerate(node_images) if a["id"] == att["id"]
            )
        except StopIteration:
            current_index = 0

        # 创建/复用全屏浏览器
        if self._fullscreen_viewer is None:
            self._fullscreen_viewer = ImageFullscreenViewer(
                image_path=abs_path,
                title=selected.text,
                caption=att.get("caption") or "",
            )
            self._fullscreen_viewer.set_navigation(
                on_prev=self._get_prev_image_path,
                on_next=self._get_next_image_path,
            )
        else:
            self._fullscreen_viewer.update_image(
                abs_path,
                new_title=selected.text,
                new_caption=att.get("caption") or "",
            )

        total = len(node_images)
        self._fullscreen_viewer.update_context(
            f"📑 当前节点第 {current_index + 1} / {total} 张"
        )
        self._fullscreen_viewer.show_fullscreen()
        logger.info(f"全屏浏览图片: {selected.text} - {att['file_path']}")

    def _get_image_nodes(self) -> list[str]:
        """⭐ 获取当前导图中所有有图片附件的节点 ID（DFS 顺序）。"""
        if not self.current_graph:
            return []
        return [
            n.id
            for n in self.current_graph.dfs()
            if any(
                a["file_type"] == "image" for a in mindmap_repo.list_attachments(n.id)
            )
        ]

    def _get_prev_image_path(self) -> Path | None:
        """⭐ 获取上一张图片：节点内 prev → 否则上一节点的图。"""
        if not self._fullscreen_viewer:
            return None
        selected = self.view.get_selected_node()
        if not selected:
            return None

        current = (
            self.attachment_panel.get_current_attachment()
            if self.attachment_panel
            else None
        )
        if not current:
            return None

        node_images = self.attachment_panel.get_image_attachments()
        if current in node_images:
            idx = node_images.index(current)
            if idx > 0:
                prev_att = node_images[idx - 1]
                abs_path = get_attachment_manager().resolve_path(prev_att["file_path"])
                self.attachment_panel._current_attachment = prev_att
                self.attachment_panel._render_preview(prev_att)
                self._fullscreen_viewer.update_image(
                    abs_path,
                    new_title=selected.text,
                    new_caption=prev_att.get("caption") or "",
                )
                self._fullscreen_viewer.update_context(
                    f"📑 当前节点第 {idx} / {len(node_images)} 张"
                )
                return abs_path

        image_nodes = self._get_image_nodes()
        if selected.node_id not in image_nodes:
            return None
        nidx = image_nodes.index(selected.node_id)
        if nidx == 0:
            return None
        prev_node_id = image_nodes[nidx - 1]
        prev_atts = [
            a
            for a in mindmap_repo.list_attachments(prev_node_id)
            if a["file_type"] == "image"
        ]
        if not prev_atts:
            return None
        prev_att = prev_atts[-1]
        prev_node = self.view.get_node_item(prev_node_id)
        if prev_node:
            prev_node.setSelected(True)
            self.attachment_panel.set_node(prev_node_id)
            self.attachment_panel._current_attachment = prev_att
            self.attachment_panel._render_preview(prev_att)
        abs_path = get_attachment_manager().resolve_path(prev_att["file_path"])
        self._fullscreen_viewer.update_image(
            abs_path,
            new_title=prev_node.text if prev_node else "",
            new_caption=prev_att.get("caption") or "",
        )
        return abs_path

    def _get_next_image_path(self) -> Path | None:
        """⭐ 获取下一张图片：节点内 next → 否则下一节点的图。"""
        if not self._fullscreen_viewer:
            return None
        selected = self.view.get_selected_node()
        if not selected:
            return None

        current = (
            self.attachment_panel.get_current_attachment()
            if self.attachment_panel
            else None
        )
        if not current:
            return None

        node_images = self.attachment_panel.get_image_attachments()
        if current in node_images:
            idx = node_images.index(current)
            if idx < len(node_images) - 1:
                next_att = node_images[idx + 1]
                abs_path = get_attachment_manager().resolve_path(next_att["file_path"])
                self.attachment_panel._current_attachment = next_att
                self.attachment_panel._render_preview(next_att)
                self._fullscreen_viewer.update_image(
                    abs_path,
                    new_title=selected.text,
                    new_caption=next_att.get("caption") or "",
                )
                self._fullscreen_viewer.update_context(
                    f"📑 当前节点第 {idx + 2} / {len(node_images)} 张"
                )
                return abs_path

        image_nodes = self._get_image_nodes()
        if selected.node_id not in image_nodes:
            return None
        nidx = image_nodes.index(selected.node_id)
        if nidx >= len(image_nodes) - 1:
            return None
        next_node_id = image_nodes[nidx + 1]
        next_atts = [
            a
            for a in mindmap_repo.list_attachments(next_node_id)
            if a["file_type"] == "image"
        ]
        if not next_atts:
            return None
        next_att = next_atts[0]
        next_node = self.view.get_node_item(next_node_id)
        if next_node:
            next_node.setSelected(True)
            self.attachment_panel.set_node(next_node_id)
            self.attachment_panel._current_attachment = next_att
            self.attachment_panel._render_preview(next_att)
        abs_path = get_attachment_manager().resolve_path(next_att["file_path"])
        self._fullscreen_viewer.update_image(
            abs_path,
            new_title=next_node.text if next_node else "",
            new_caption=next_att.get("caption") or "",
        )
        return abs_path

    # ==================== 导出（占位）====================

    def _on_export(self, fmt: str) -> None:
        """导出整个导图菜单回调（PNG / JSON / Markdown / HTML / PDF）。"""
        if not self.current_graph or not self.current_mindmap_id:
            QMessageBox.warning(self, "提示", "请先打开一个导图")
            return

        from PySide6.QtWidgets import QFileDialog

        from src.utils.exporter import (
            export_to_html,
            export_to_json,
            export_to_markdown,
            export_to_pdf,
            export_to_png,
        )

        m = mindmap_repo.get_mindmap(self.current_mindmap_id)
        title = m["title"] if m else "mindmap"

        # 选择文件路径
        ext_map = {
            "PNG": ("png", "PNG 图片 (*.png)"),
            "JSON": ("json", "JSON 文件 (*.json)"),
            "Markdown": ("md", "Markdown 文件 (*.md)"),
            "HTML": ("html", "HTML 文件 (*.html)"),
            "PDF": ("pdf", "PDF 文件 (*.pdf)"),
        }
        ext, filt = ext_map[fmt]
        default_name = f"{title}.{ext}"
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"导出为 {fmt}", default_name, filt
        )
        if not file_path:
            return

        try:
            if fmt == "PNG":
                export_to_png(self.view, file_path)
            elif fmt == "JSON":
                export_to_json(
                    title, self.current_graph, file_path, m["description"] if m else ""
                )
            elif fmt == "Markdown":
                export_to_markdown(
                    title,
                    self.current_graph,
                    file_path,
                    m["description"] if m else "",
                    mindmap_id=self.current_mindmap_id,
                )
            elif fmt == "HTML":
                export_to_html(
                    title,
                    self.current_graph,
                    file_path,
                    m["description"] if m else "",
                    mindmap_id=self.current_mindmap_id,
                )
            elif fmt == "PDF":
                # ⭐ PDF 走 Qt 原生 QPrinter（需要 QApplication 在场，调用前确认）
                export_to_pdf(
                    title,
                    self.current_graph,
                    file_path,
                    m["description"] if m else "",
                    mindmap_id=self.current_mindmap_id,
                )
            self._update_status(f"✅ 已导出为 {fmt}：{Path(file_path).name}")
            QMessageBox.information(self, "导出成功", f"已导出到：\n{file_path}")
        except Exception as e:
            logger.exception("导出失败")
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_export_node(self, fmt: str) -> None:
        """⭐⭐ 文件菜单 → 当前节点笔记 菜单的回调（Markdown / HTML / PDF）。

        通过画布选中的节点来定位。
        """
        if not self.current_graph or not self.current_mindmap_id:
            QMessageBox.warning(self, "提示", "请先打开一个导图")
            return

        selected = self.view.get_selected_node()
        if not selected:
            QMessageBox.warning(
                self,
                "提示",
                "请先在画布上选中一个节点（要导出的最终整理笔记所在的节点）",
            )
            return

        node = self.current_graph.get_node(selected.node_id)
        if not node:
            QMessageBox.warning(self, "提示", "选中的节点数据加载失败")
            return

        self._do_export_node(node, fmt)

    def _on_export_node_from_editor(self, fmt: str) -> None:
        """⭐⭐⭐ NoteEditor 内「📤 导出 ▼」按钮的回调（VSCode 风格入口）。

        通过 _current_note_node_id 定位（用户在右侧详情面板正在编辑的节点）。
        不必再去画布上点节点。
        """
        if not self.current_graph or not self.current_mindmap_id:
            QMessageBox.warning(self, "提示", "请先打开一个导图")
            return
        if not self._current_note_node_id:
            QMessageBox.warning(
                self,
                "提示",
                "当前没有正在编辑笔记的节点。\n请先在画布上选中一个节点，"
                "然后在笔记编辑器里点「📤 导出」。",
            )
            return

        node = self.current_graph.get_node(self._current_note_node_id)
        if not node:
            QMessageBox.warning(self, "提示", "节点数据加载失败")
            return

        self._do_export_node(node, fmt)

    def _do_export_node(self, node, fmt: str) -> None:
        """⭐ 公共导出节点笔记逻辑 — 文件菜单入口和 NoteEditor 按钮入口都走这里。"""
        # ⭐ 友善提示：如果 note 为空，导出文件基本是空的
        if not node.note or not node.note.strip():
            reply = QMessageBox.question(
                self,
                "笔记为空",
                f"节点「{node.text}」还没有整理笔记（note 为空）。\n"
                "是否继续导出（将生成空文件 / 仅显示「(空)」）？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        from PySide6.QtWidgets import QFileDialog

        from src.utils.exporter import (
            export_node_to_html,
            export_node_to_markdown,
            export_node_to_pdf,
        )

        ext_map = {
            "Markdown": ("md", "Markdown 文件 (*.md)"),
            "HTML": ("html", "HTML 文件 (*.html)"),
            "PDF": ("pdf", "PDF 文件 (*.pdf)"),
        }
        ext, filt = ext_map[fmt]
        # 用节点名做默认文件名（过滤非法字符）
        safe_name = (
            "".join(c for c in node.text if c not in r'\/:*?"<>|').strip() or "node"
        )
        default_name = f"{safe_name}.{ext}"
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"导出节点笔记为 {fmt}", default_name, filt
        )
        if not file_path:
            return

        try:
            if fmt == "Markdown":
                export_node_to_markdown(node, file_path)
            elif fmt == "HTML":
                export_node_to_html(node, file_path)
            elif fmt == "PDF":
                export_node_to_pdf(node, file_path)
            self._update_status(f"✅ 已导出节点笔记 {fmt}：{Path(file_path).name}")
            QMessageBox.information(
                self,
                "导出成功",
                f"节点「{node.text}」的整理笔记已导出到：\n{file_path}",
            )
        except Exception as e:
            logger.exception("导出节点笔记失败")
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_about(self) -> None:
        """关于对话框。"""
        QMessageBox.about(
            self,
            "关于 MindFlow",
            f"<h2>{APP_NAME}</h2>"
            f"<p>版本：{APP_VERSION}</p>"
            "<p>思维导图编辑器</p>"
            "<p>Python + PySide6 + SQLite</p>",
        )
