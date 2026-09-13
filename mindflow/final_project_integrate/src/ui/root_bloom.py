"""⭐ 根节点 bloom（"中心天体"暗示）。

借鉴 galaxy-view 的"中心天体"暗示 + Apple 主题演讲常用的"光源环"：
- 根节点（parent_id is None 且 children 最多）周围画一个极淡的圆环
- 暗示"这是整个思维星图的中心恒星"
- 仅在 Browse 模式启用（EDIT 模式不需要这种"宇宙感"）

为什么用独立 item 而不是改 NodeItem.paint：
- NodeItem.boundingRect 加大 → 根节点 hitTest 范围扩大到 200px 外（用户点远处会误中）
- 独立 item 单独控制可见性 + 跟随逻辑，不污染节点逻辑
- 渲染层级独立（z=-50：在 starfield 之上、节点之下）

技术：
- 单一 QGraphicsItem，独立 paint
- 跟随 root 节点 scenePos（root 移动时由 mindmap_view 调 update_position）
- 淡 cyan 圆环 + 极低 alpha (8%) → 不抢节点戏，但能感觉到"引力场"
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

# 根节点 bloom 配置
BLOOM_RADIUS = 200.0  # 圆环半径（scene 单位）
BLOOM_COLOR = QColor(34, 211, 238)  # cyan #22d3ee
BLOOM_ALPHA = 0.08  # 8%——极淡，仅作"引力场"暗示
BLOOM_STROKE_WIDTH = 1.5  # 描边粗细
BLOOM_Z_VALUE = -50  # 在 starfield(-100/-110)之上、节点(1)之下

# ⭐ 内部还画一个更小的内圈（12% alpha），双环营造"光晕层次"
BLOOM_INNER_RADIUS = 80.0
BLOOM_INNER_ALPHA = 0.12


class RootBloomItem(QGraphicsItem):
    """⭐ 根节点 bloom 环（中心天体暗示）。"""

    SCENE_EXTENT = 1500  # 包围矩形（覆盖 bloom 范围）

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.setZValue(BLOOM_Z_VALUE)
        # 不参与 hitTest（环不该拦截点击）
        self.setAcceptedMouseButtons(Qt.NoButton)
        # 不接受 hover 事件
        self.setAcceptHoverEvents(False)
        # 默认隐藏（直到 mindmap 加载 + 找到根节点）
        self.hide()
        # 当前跟随的 NodeItem（外部注入）
        self._target_node = None

    def set_target_node(self, node_item) -> None:
        """⭐ 设置要跟随的根节点。传入 None 隐藏 bloom。"""
        self._target_node = node_item
        if node_item is None:
            self.hide()
            return
        self.show()
        # 立即定位一次
        self.update_position()

    def update_position(self) -> None:
        """⭐ 重新从 _target_node 读 scenePos。节点移动后调用。"""
        node = self._target_node
        if node is None:
            return
        try:
            # bloom 中心对齐节点中心
            cx = node.scenePos().x() + node.width / 2
            cy = node.scenePos().y() + node.height / 2
            self.setPos(cx, cy)
        except RuntimeError:
            # ⭐ C++ 对象已销毁 → 隐藏
            self._target_node = None
            self.hide()

    def boundingRect(self) -> QRectF:
        """覆盖 bloom 范围（外环 + 内环 + padding）。"""
        r = BLOOM_RADIUS + BLOOM_STROKE_WIDTH + 4
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ) -> None:
        """⭐ 双环：外环（淡 8%）+ 内环（稍亮 12%），营造"光晕层次"。"""
        aa_on = painter.testRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            # ⭐ 外环：8% alpha cyan
            outer_color = QColor(BLOOM_COLOR)
            outer_color.setAlphaF(BLOOM_ALPHA)
            pen_outer = QPen(outer_color, BLOOM_STROKE_WIDTH)
            painter.setPen(pen_outer)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), BLOOM_RADIUS, BLOOM_RADIUS)

            # ⭐ 内环：12% alpha cyan（稍亮，营造"光晕中心"层次）
            inner_color = QColor(BLOOM_COLOR)
            inner_color.setAlphaF(BLOOM_INNER_ALPHA)
            pen_inner = QPen(inner_color, BLOOM_STROKE_WIDTH * 0.8)
            painter.setPen(pen_inner)
            painter.drawEllipse(QPointF(0, 0), BLOOM_INNER_RADIUS, BLOOM_INNER_RADIUS)
        finally:
            painter.setRenderHint(QPainter.Antialiasing, aa_on)
