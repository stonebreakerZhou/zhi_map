"""全屏图片浏览器。

专为"手写笔记图片复习"设计的大屏浏览体验：

特性：
- 全屏无边框（按 ESC 退出）
- 顶部悬浮工具栏：缩放控制、还原、旋转、关闭
- 底部状态栏：文件名 + 节点上下文
- 鼠标拖动平移
- 滚轮缩放（Ctrl+wheel 精细缩放，普通 wheel 上下滚动浏览大图）
- 双击切换：适应窗口 ↔ 100% 原图
- 键盘快捷键：
  - ESC        退出
  - + / =      放大
  - -          缩小
  - 0          还原到当前 fit
  - 1          100% 原图
  - F          适应窗口
  - R          顺时针旋转 90°
  - ← →        切换上一个/下一个有图的节点
- 平滑缩放动画（QPropertyAnimation）

P4 负责维护。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.image_fullscreen_viewer")


# ==================== 图片视图（带缩放/拖动）====================


class _ImageGraphicsView(QGraphicsView):
    """图片视图：支持 Ctrl+wheel 缩放、拖动平移、双击切换模式。"""

    double_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QColor("#1e1e1e"))
        self.setScene(self._scene)

        # 图片 item
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._original_pixmap: QPixmap | None = None
        self._scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 10.0

        # 视图设置
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #1e1e1e; border: none;")
        self.setFrameShape(QFrame.NoFrame)

        # 旋转
        self._rotation = 0

    def set_image(self, pixmap: QPixmap) -> None:
        """设置图片。"""
        self._scene.clear()
        self._original_pixmap = pixmap
        self._rotation = 0
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fit_to_view()

    def fit_to_view(self) -> None:
        """适应窗口。"""
        if not self._original_pixmap:
            return
        self.resetTransform()
        self._scale = 1.0
        if self._rotation != 0:
            self.rotate(self._rotation)
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        # 同步 scale
        self._scale = self.transform().m11()
        if abs(self._scale) < 1e-6:
            self._scale = 1.0

    def actual_size(self) -> None:
        """100% 原图大小。"""
        if not self._original_pixmap:
            return
        self.resetTransform()
        self._scale = 1.0
        if self._rotation != 0:
            self.rotate(self._rotation)

    def zoom(self, factor: float) -> None:
        """按因子缩放（带范围限制）。"""
        if not self._original_pixmap:
            return
        new_scale = self._scale * factor
        if self._min_scale <= new_scale <= self._max_scale:
            self._scale = new_scale
            self.scale(factor, factor)

    def zoom_to(self, target_scale: float) -> None:
        """缩放到指定比例（用于动画）。"""
        if not self._original_pixmap or self._scale == 0:
            return
        factor = target_scale / self._scale
        self._scale = target_scale
        self.scale(factor, factor)

    def current_scale(self) -> float:
        return self._scale

    def rotate_image(self, degrees: int = 90) -> None:
        """旋转图片。"""
        if not self._original_pixmap:
            return
        self._rotation = (self._rotation + degrees) % 360
        rotated = self._original_pixmap.transformed(
            __import__("PySide6").QtGui.QTransform().rotate(degrees),
            Qt.SmoothTransformation,
        )
        # 累加旋转
        new_pixmap = self._original_pixmap.transformed(
            __import__("PySide6").QtGui.QTransform().rotate(self._rotation),
            Qt.SmoothTransformation,
        )
        self._original_pixmap = new_pixmap
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(new_pixmap)
        self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.setSceneRect(QRectF(new_pixmap.rect()))
        self.fit_to_view()

    # ==================== 鼠标交互 ====================

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ctrl + wheel 缩放，普通 wheel 上下平移浏览大图。"""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.zoom(factor)
            event.accept()
        else:
            # 普通滚轮：上下滚动（适合查看超出屏幕的大图）
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """双击切换：适应窗口 ↔ 100%。"""
        if event.button() == Qt.LeftButton:
            if self._scale > 1.05:  # 当前放大了，切回适应
                self.fit_to_view()
            else:
                self.actual_size()
            self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


# ==================== 主组件 ====================


class ImageFullscreenViewer(QWidget):
    """全屏图片浏览器。

    用法：
        viewer = ImageFullscreenViewer(image_path, title="极限的定义", caption="...")
        viewer.show_fullscreen()
    """

    closed = Signal()  # 关闭信号

    def __init__(
        self,
        image_path: Path,
        title: str = "",
        caption: str = "",
        context: str = "",
    ) -> None:
        super().__init__()
        self._image_path = Path(image_path)
        self._title = title
        self._caption = caption
        self._context = context  # 例如 "节点 3 / 共 8 个有图"

        # 切换回调（注入到 main_window 来切换其他节点）
        self._on_prev: Callable[[], Path | None] | None = None
        self._on_next: Callable[[], Path | None] | None = None

        self._init_ui()
        self._load_image()

        # 动画
        self._zoom_animation: QPropertyAnimation | None = None

    # ==================== UI ====================

    def _init_ui(self) -> None:
        """初始化 UI。"""
        # 无边框 + 置顶
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("background: #1e1e1e; color: #eee;")

        # 全屏
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏（半透明悬浮）
        self._top_bar = QFrame()
        self._top_bar.setStyleSheet(
            "background: rgba(30, 30, 30, 220);"
            "border-bottom: 1px solid #444;"
            "color: white;"
        )
        self._top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(self._top_bar)
        top_layout.setContentsMargins(16, 8, 16, 8)

        # 标题
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet(
            "font-size: 14pt; font-weight: bold; color: white; padding: 0 16px;"
        )
        top_layout.addWidget(self._title_label)

        # 上下文
        if self._context:
            self._ctx_label = QLabel(self._context)
            self._ctx_label.setStyleSheet(
                "color: #aaa; font-size: 10pt; padding: 0 16px;"
            )
            top_layout.addWidget(self._ctx_label)

        top_layout.addStretch()

        # 工具按钮
        btn_style = (
            "QPushButton {"
            "  background: rgba(255,255,255,0.1);"
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,0.2);"
            "  border-radius: 4px;"
            "  padding: 6px 14px;"
            "  font-size: 11pt;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.2); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.3); }"
        )

        self._btn_prev = QPushButton("◀ 上一张")
        self._btn_prev.setStyleSheet(btn_style)
        self._btn_prev.clicked.connect(self._go_prev)
        top_layout.addWidget(self._btn_prev)

        self._btn_zoom_out = QPushButton("➖")
        self._btn_zoom_out.setStyleSheet(btn_style)
        self._btn_zoom_out.setFixedWidth(44)
        top_layout.addWidget(self._btn_zoom_out)

        self._btn_zoom_in = QPushButton("➕")
        self._btn_zoom_in.setStyleSheet(btn_style)
        self._btn_zoom_in.setFixedWidth(44)
        top_layout.addWidget(self._btn_zoom_in)

        self._btn_fit = QPushButton("适应窗口")
        self._btn_fit.setStyleSheet(btn_style)
        top_layout.addWidget(self._btn_fit)

        self._btn_actual = QPushButton("100%")
        self._btn_actual.setStyleSheet(btn_style)
        top_layout.addWidget(self._btn_actual)

        self._btn_rotate = QPushButton("🔄 旋转")
        self._btn_rotate.setStyleSheet(btn_style)
        top_layout.addWidget(self._btn_rotate)

        self._btn_close = QPushButton("✕ 关闭 (ESC)")
        self._btn_close.setStyleSheet(
            btn_style.replace("rgba(255,255,255,0.1)", "rgba(220,80,80,0.3)").replace(
                "rgba(255,255,255,0.2)", "rgba(220,80,80,0.5)"
            )
        )
        self._btn_close.clicked.connect(self.close)
        top_layout.addWidget(self._btn_close)

        layout.addWidget(self._top_bar)

        # ⭐ 先创建图片视图（按钮的 connect 需要它）
        self._view = _ImageGraphicsView()
        # 现在再连接（之前是空引用）
        self._btn_zoom_out.clicked.connect(lambda: self._view.zoom(1 / 1.25))
        self._btn_zoom_in.clicked.connect(lambda: self._view.zoom(1.25))
        self._btn_fit.clicked.connect(self._view.fit_to_view)
        self._btn_actual.clicked.connect(self._view.actual_size)
        self._btn_rotate.clicked.connect(lambda: self._view.rotate_image(90))
        # 缩放变化后更新百分比（用 transform 变化监听）
        # 缩放通过 wheelEvent 和按钮触发，scale() 调用会改变 transform
        # 我们在 zoom/fit/actual 后手动调用 _update_zoom_label
        self._view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        layout.addWidget(self._view, 1)

        # 底部状态栏
        self._bottom_bar = QFrame()
        self._bottom_bar.setStyleSheet(
            "background: rgba(30, 30, 30, 220);"
            "border-top: 1px solid #444;"
            "color: #ccc;"
            "padding: 4px 16px;"
        )
        self._bottom_bar.setFixedHeight(36)
        bottom_layout = QHBoxLayout(self._bottom_bar)
        bottom_layout.setContentsMargins(16, 4, 16, 4)

        self._status_label = QLabel(self._make_status_text())
        self._status_label.setStyleSheet("color: #ccc; font-size: 10pt;")
        bottom_layout.addWidget(self._status_label)

        bottom_layout.addStretch()

        # 缩放百分比
        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color: #ccc; font-size: 10pt; padding: 0 16px;")
        bottom_layout.addWidget(self._zoom_label)

        layout.addWidget(self._bottom_bar)

    def _make_status_text(self) -> str:
        """生成状态文本。"""
        parts = []
        if self._title:
            parts.append(f"📌 {self._title}")
        if self._caption:
            parts.append(f"📝 {self._caption}")
        parts.append(f"🖼 {self._image_path.name}")
        return "   |   ".join(parts)

    def _load_image(self) -> None:
        """加载图片。"""
        if not self._image_path.exists():
            logger.error(f"图片不存在: {self._image_path}")
            return
        pixmap = QPixmap(str(self._image_path))
        if pixmap.isNull():
            logger.error(f"图片加载失败: {self._image_path}")
            return
        self._view.set_image(pixmap)

    # ==================== 公开 API ====================

    def show_fullscreen(self) -> None:
        """全屏显示。"""
        self.show()
        self.raise_()
        self.activateWindow()

    def set_navigation(
        self,
        on_prev: Callable[[], Path | None] | None = None,
        on_next: Callable[[], Path | None] | None = None,
    ) -> None:
        """设置上下张切换回调。

        Args:
            on_prev: 返回上一张图片路径（或 None）
            on_next: 返回下一张图片路径（或 None）
        """
        self._on_prev = on_prev
        self._on_next = on_next
        self._btn_prev.setEnabled(on_prev is not None)
        # 加一个下一张按钮（如果还没加）
        if on_next is not None:
            self._btn_next = QPushButton("下一张 ▶")
            self._btn_next.setStyleSheet(self._btn_prev.styleSheet())
            self._btn_next.clicked.connect(self._go_next)
            # 插到"上一张"后面

    def update_context(self, context: str) -> None:
        """更新上下文信息（页码/总张数）。"""
        self._context = context
        if hasattr(self, "_ctx_label"):
            self._ctx_label.setText(context)

    def update_image(
        self, new_path: Path, new_title: str = "", new_caption: str = ""
    ) -> None:
        """切换图片（不关闭窗口）。"""
        self._image_path = Path(new_path)
        if new_title:
            self._title = new_title
            self._title_label.setText(new_title)
        if new_caption:
            self._caption = new_caption
        self._status_label.setText(self._make_status_text())
        self._load_image()

    def current_path(self) -> Path | None:
        """⭐ 获取当前显示的图片路径。"""
        return self._image_path

    # ==================== 切换 ====================

    def _go_prev(self) -> None:
        if self._on_prev:
            new_path = self._on_prev()
            if new_path:
                self.update_image(new_path)

    def _go_next(self) -> None:
        if self._on_next:
            new_path = self._on_next()
            if new_path:
                self.update_image(new_path)

    # ==================== 键盘 ====================

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self._view.zoom(1.25)
            self._update_zoom_label()
        elif event.key() == Qt.Key_Minus:
            self._view.zoom(1 / 1.25)
            self._update_zoom_label()
        elif event.key() == Qt.Key_0:
            self._view.fit_to_view()
            self._update_zoom_label()
        elif event.key() == Qt.Key_1:
            self._view.actual_size()
            self._update_zoom_label()
        elif event.key() == Qt.Key_F:
            self._view.fit_to_view()
            self._update_zoom_label()
        elif event.key() == Qt.Key_R:
            self._view.rotate_image(90)
            self._update_zoom_label()
        elif event.key() == Qt.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key_Right:
            self._go_next()
        else:
            super().keyPressEvent(event)

    def _update_zoom_label(self) -> None:
        """更新缩放百分比。"""
        scale = self._view.current_scale()
        self._zoom_label.setText(f"{int(scale * 100)}%")

    # ==================== 关闭 ====================

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)


__all__ = ["ImageFullscreenViewer"]
