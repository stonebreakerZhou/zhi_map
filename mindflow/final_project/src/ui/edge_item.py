"""⭐ 自定义思维导图边（QGraphicsItem，星座连线风格）。

设计：
- 默认：细灰白半透明（0.6px 视觉感），像夜空里的连线
- 选中端点（源或目标）：青色发光
- 切割高亮：红色
- 贝塞尔曲线（保留原体感）
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

# 默认星座线颜色（夜空深灰白，半透明）
DEFAULT_EDGE_COLOR = "#cbd5e1"  # slate-300（更亮，比 slate-400 在深色背景上清晰）
# 选中发光色（青色）
SELECT_EDGE_COLOR = "#22d3ee"
# 切割高亮（保留红色）
WARNING_EDGE_COLOR = "#ff3b30"


class EdgeItem(QGraphicsItem):
    """节点之间的连线。"""

    def __init__(
        self,
        source_node,
        target_node,
        color: str = DEFAULT_EDGE_COLOR,
    ) -> None:
        super().__init__()
        self.source = source_node
        self.target = target_node
        self.color = QColor(color)
        self._default_color = QColor(color)
        self._warning = False
        # ⭐ Focus mode 暗化标志（Browse 模式下非邻居连线 = True → opacity 0.15）
        self._dimmed: bool = False
        # ⭐ 星云模式（galaxy-view 风格）：边变成更细更淡的"filament"
        self._nebula_mode: bool = False
        # ⭐ 附加边对应的数据库主键 id（用于删除时同步落库；树形边可保持 None）
        self.db_id: int | None = None
        self.setZValue(0)  # 边在节点下面

    def set_warning(self, on: bool) -> None:
        """⭐ 切割高亮：被划线穿过时变红。"""
        self._warning = on
        self.color = QColor(WARNING_EDGE_COLOR) if on else self._default_color
        self.update()

    def is_warning(self) -> bool:
        return self._warning

    def boundingRect(self) -> QRectF:
        """包含两端点的矩形（含 padding）。"""
        try:
            if not self.source or not self.target:
                return QRectF()
            p1 = self.source.scenePos() + QPointF(
                self.source.width / 2, self.source.height / 2
            )
            p2 = self.target.scenePos() + QPointF(
                self.target.width / 2, self.target.height / 2
            )
            return QRectF(p1, p2).normalized().adjusted(-20, -20, 20, 20)
        except (RuntimeError, AttributeError):
            # ⭐ 端点 NodeItem C++ 对象已被销毁 → 返回空矩形，避免崩溃
            return QRectF()

    def _any_endpoint_selected(self) -> bool:
        """⭐ 判断任一端点是否被选中（用于连边发光）。"""
        try:
            return bool(
                (self.source and self.source.isSelected())
                or (self.target and self.target.isSelected())
            )
        except (RuntimeError, AttributeError):
            return False

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        try:
            if not self.source or not self.target:
                return
            p1 = self.source.scenePos() + QPointF(
                self.source.width / 2, self.source.height / 2
            )
            p2 = self.target.scenePos() + QPointF(
                self.target.width / 2, self.target.height / 2
            )
        except (RuntimeError, AttributeError):
            # ⭐ 端点 NodeItem C++ 对象已被销毁 → 安全退出
            return

        painter.setRenderHint(QPainter.Antialiasing)

        # ⭐ 二次贝塞尔"细弧线"：弧度大幅减小（之前 18% 看起来像飘带）
        # 短连线（<60px）几乎平直；长连线（≥300px）弧度封顶 30px
        # 比 cubicTo 的 S 形更"星座连线"感，比之前更克制更清晰
        path = QPainterPath(p1)
        length = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
        if length < 1.0:
            # 退化：两点重合 → 直线
            path.lineTo(p2)
        else:
            arc = min(length * 0.08, 30.0)  # ⭐ 8% 距离，封顶 30px（细弧线）
            mid_x = (p1.x() + p2.x()) / 2
            mid_y = (p1.y() + p2.y()) / 2
            # 垂直方向：(−dy, dx) 归一化 → 控制点
            ctrl_x = mid_x - (p2.y() - p1.y()) / length * arc
            ctrl_y = mid_y + (p2.x() - p1.x()) / length * arc
            path.quadTo(ctrl_x, ctrl_y, p2.x(), p2.y())

        # ⭐ 决定颜色 / 宽度：切割红 > 选中端点青光 > 默认细弧线
        # 星云模式下整体更细更淡（galaxy-view 的 "thin desaturated link filaments"）
        if self._warning:
            stroke = QColor(WARNING_EDGE_COLOR)
            width = 2.5
            alpha = 1.0
        elif self._nebula_mode:
            # ⭐⭐ nebula 模式：选中端点的边也保持 filament 风格（不亮成 cyan）
            # 否则点击节点时全图边缘闪 cyan，破坏沉浸感
            # 选中态的"边缘表达"完全交给节点白色脉冲 + 浮窗 label
            stroke = QColor(DEFAULT_EDGE_COLOR)
            if self._any_endpoint_selected():
                # ⭐ 选中端点 → 边略亮一点点（仍然细，仍然淡，仅作微弱呼应）
                width = 1.0
                alpha = 0.55
            else:
                width = 0.8  # 极细
                alpha = 0.35  # 更淡
        elif self._any_endpoint_selected():
            stroke = QColor(SELECT_EDGE_COLOR)
            width = 2.5
            alpha = 1.0
        else:
            stroke = QColor(DEFAULT_EDGE_COLOR)
            width = 1.8  # ⭐ 1.4 → 1.8（细而清晰）
            alpha = 0.70  # ⭐ 0.55 → 0.70（更深色背景下能看清）

        stroke.setAlphaF(alpha)
        pen = QPen(stroke, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

    # ==================== ⭐ 性能优化：节点移动通知 ====================

    def node_moved(self) -> None:
        """⭐ 当端点节点位置变化时调用。

        这是流畅拖动的关键——比依赖 itemChange 通知更可靠。
        """
        try:
            # 通知 Qt 几何变更（避免残影）
            self.prepareGeometryChange()
            # 重绘
            self.update()
        except RuntimeError:
            # ⭐ C++ 对象已销毁（场景切换/父对象被删）
            pass

    # ==================== Focus mode 暗化 ====================

    # ⭐ 暗化时比节点更"沉"——边是装饰，重要性最低
    DIMMED_OPACITY = 0.15
    NORMAL_OPACITY = 1.0

    def set_dimmed(self, dimmed: bool) -> None:
        """⭐ Browse 模式选中节点时调用：把"非邻居"边的 opacity 降到 0.15。"""
        self._dimmed = bool(dimmed)
        self.setOpacity(self.DIMMED_OPACITY if dimmed else self.NORMAL_OPACITY)

    def is_dimmed(self) -> bool:
        return self._dimmed

    # ==================== ⭐ 星云模式（galaxy-view 风格 filament）====================

    def set_nebula_mode(self, on: bool) -> None:
        """⭐ Browse 模式切换：边变成 galaxy-view 风格的"thin desaturated filaments"。

        on=True  → 更细更淡（width 0.8 / alpha 0.35）
        on=False → 默认细弧线（width 1.8 / alpha 0.70）
        """
        self._nebula_mode = bool(on)
        # 不调 update，由 view.set_nebula_mode 统一刷新

    def is_nebula_mode(self) -> bool:
        return self._nebula_mode
