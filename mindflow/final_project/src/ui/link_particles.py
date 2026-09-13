"""⭐ 链接光点（Directional Particles，d3-force-graph 招牌效果）。

设计要点：
- 单一 QGraphicsItem，一次 paint() 画完所有链接上的光点（性能优于每边一个 item）
- 沿 EdgeItem 的同一条 cubicTo 曲线流动（保证视觉同步）
- 30fps 推进 _t（60fps 没必要，光点慢反而更"宇宙感"）
- 光点 z=0.5：在边(z=0)之上、节点(z=1)之下 → 像被节点遮挡，更真实
- 暗化（dimmed）边上的光点同步降透明度：与 focus mode 视觉一致
- 被 widget 已选中的边光点更亮
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsItem


class LinkParticlesItem(QGraphicsItem):
    """⭐ 沿链接流动的小光点（d3-force-graph 招牌效果）。"""

    # z 比边高（0.5 vs 0），比节点低（节点 1/10）→ 视觉上像节点遮挡
    Z_VALUE = 0.5
    # 星点大小（scene 坐标，半径）
    PARTICLE_RADIUS = 3.2
    # 推进速度（每帧 1.2%，约 1.4 秒走完一次）—— 慢于 d3-force-graph（10%），更"宇宙感"
    TICK_STEP = 0.012
    # 刷新频率（ms）—— 30fps 足够，太快反而像广告
    TICK_INTERVAL_MS = 33
    # 星点颜色（cyan，跟主色对齐）
    PARTICLE_COLOR = QColor(34, 211, 238)  # #22d3ee
    # ⭐⭐ comet trail：每条边 3 个粒子 + 渐淡（仿 d3-force-graph directional particles）
    # 第 0 个 = 头部（亮），第 1 个 = 1/3 周期后（中），第 2 个 = 2/3 周期后（淡）
    # 视觉上像"彗星拖尾"，更有"流动感"
    PARTICLES_PER_EDGE = 3
    # 每个粒子的相对偏移（沿 path 0..1）；用 0、-0.08、-0.16 让尾部紧跟头部
    PARTICLE_OFFSETS = (0.0, -0.08, -0.16)
    # 每个粒子的 alpha（0=全透，1=全不透）；头部最亮、尾部最暗
    PARTICLE_ALPHAS = (1.0, 0.55, 0.25)

    # 包围矩形（覆盖整个 scene extent，确保 pan 时不丢）
    SCENE_EXTENT = 8000

    def __init__(self, view, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._view = view
        # ⭐ 永远在边之上、节点之下（视觉层级）
        self.setZValue(self.Z_VALUE)
        # 不参与 hitTest（光点不该拦截点击）
        self.setAcceptedMouseButtons(Qt.NoButton)
        # 不接受 hover 事件
        self.setAcceptHoverEvents(False)

        # ⭐ 时钟驱动：单点更新 _t，避免每帧重算 sin
        # PySide6 6.x：QTimer 不接受 QGraphicsItem 作 parent，故用 None
        self._t: float = 0.0
        self._timer = QTimer()
        self._timer.setInterval(self.TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # ------- 内部状态 -------

    def _on_tick(self) -> None:
        """每帧推进 _t（30fps）。"""
        self._t += self.TICK_STEP
        if self._t >= 1.0:
            self._t -= 1.0
        self.update()  # 触发一次 paint

    # ------- QGraphicsItem 必需接口 -------

    def boundingRect(self) -> QRectF:
        """⭐ 覆盖整个 scene extent（pan 时光点永远不会"消失"）。"""
        return QRectF(
            -self.SCENE_EXTENT,
            -self.SCENE_EXTENT,
            self.SCENE_EXTENT * 2,
            self.SCENE_EXTENT * 2,
        )

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ) -> None:
        """⭐ 一次 paint 画完所有链接上的光点。"""
        aa_on = painter.testRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            painter.setPen(Qt.NoPen)
            t = self._t
            particle_color = self.PARTICLE_COLOR
            r = self.PARTICLE_RADIUS

            # ⭐ 遍历 view 的所有 edge（每帧重算 path，跟 EdgeItem.paint 一致）
            # 性能：200 边 × 3 光点 = 600 drawEllipse/帧 ≈ 2-4ms（GPU 加速下更少）
            for edge in self._view._edge_items:
                try:
                    src = edge.source
                    tgt = edge.target
                    if src is None or tgt is None:
                        continue
                    p1 = src.scenePos() + QPointF(src.width / 2, src.height / 2)
                    p2 = tgt.scenePos() + QPointF(tgt.width / 2, tgt.height / 2)

                    # ⭐ 复用 EdgeItem 的二次贝塞尔"细弧线"（保持视觉同步）
                    path = QPainterPath(p1)
                    length = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                    if length < 1.0:
                        path.lineTo(p2)
                    else:
                        arc = min(length * 0.08, 30.0)  # ⭐ 与 EdgeItem 一致
                        mid_x = (p1.x() + p2.x()) / 2
                        mid_y = (p1.y() + p2.y()) / 2
                        ctrl_x = mid_x - (p2.y() - p1.y()) / length * arc
                        ctrl_y = mid_y + (p2.x() - p1.x()) / length * arc
                        path.quadTo(ctrl_x, ctrl_y, p2.x(), p2.y())

                    # ⭐ 基础透明度：被 dimmed 的边 → 暗；选中端点的边 → 中等；默认中等
                    # nebula 模式下选中不暴亮（0.95 → 0.50），避免点击节点时全图粒子闪烁
                    is_nebula = getattr(edge, "is_nebula_mode", lambda: False)()
                    if getattr(edge, "is_dimmed", lambda: False)():
                        base_alpha = 0.10
                    elif getattr(edge, "_any_endpoint_selected", lambda: False)():
                        base_alpha = 0.50 if is_nebula else 0.95
                    else:
                        base_alpha = 0.60

                    # ⭐⭐ comet trail：每条边画 3 个粒子（头部亮、尾部淡）
                    for k, (offset, trail_alpha) in enumerate(
                        zip(self.PARTICLE_OFFSETS, self.PARTICLE_ALPHAS)
                    ):
                        # 粒子在 path 上的位置（环绕到 [0,1)）
                        trail_t = (t + offset) % 1.0
                        pos = path.pointAtPercent(trail_t)

                        # 透明度：基础 × 拖尾渐淡
                        alpha = base_alpha * trail_alpha
                        color = QColor(particle_color)
                        color.setAlphaF(max(0.0, min(1.0, alpha)))
                        painter.setBrush(QBrush(color))
                        # 尾部粒子略小（强化"拖尾衰减"感）
                        particle_r = r * (1.0 - 0.15 * k)
                        painter.drawEllipse(pos, particle_r, particle_r)
                except (RuntimeError, AttributeError):
                    # ⭐ 端点 C++ 已销毁（场景切换 / 删除中），跳过
                    continue
        finally:
            painter.setRenderHint(QPainter.Antialiasing, aa_on)


# ⚠️ 不用 QTimer 的 _t 在 widget 删除前清理——scene 销毁时 items 跟着 GC，
#    QTimer parent=None 不会阻止 Python 对象销毁，只是定时器回调会撞已死的 QGraphicsItem。
#    为安全：在 view.closeEvent / scene 销毁前调 self._timer.stop()（由 view 持有引用负责）。
