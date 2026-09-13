"""⭐ 节点/边删除特效（仿 project-graph EffectEngine）。

参照 graphif/project-graph 的几个核心特效：
- EntityShrinkEffect：节点缩到 0 消失（不用 opacity，纯几何收缩 + 中心点保持）
- CircleFlameEffect：圆形闪光（切线穿过节点瞬间在交点爆发）
- LineCuttingEffect：切线残影（划线松开后，画一条从起点向末端扫过的渐隐激光）

我们的简化版（PySide6 + QGraphicsScene/View 限制）：
- 节点：scale 1→0，250ms，OutCubic（不用 opacity，保留"被吞掉"的物理直觉）
- 切线残影：起点→末端逐段显示并淡出，400ms，OutCubic
- 火花闪光：圆形 QRadialGradient，从 0 半径扩散到目标半径，300ms

时间统一：所有特效 250-400ms（再短没存在感，再长显得卡）
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPointF,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QBrush, QColor, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsOpacityEffect,
    QGraphicsPathItem,
    QGraphicsScene,
)

DELETE_DURATION_MS = 250  # 节点删除
EDGE_FADE_DURATION_MS = 250  # 边淡出
CUT_TRAIL_DURATION_MS = 400  # 切线残影
SPARK_DURATION_MS = 300  # 火花闪光


# ============================================================
# 内部辅助：安全的 item 已删除检测（C++ RuntimeError 防御）
# ============================================================


def _safe_remove_from_scene(scene: QGraphicsScene | None, item) -> None:
    """⭐ 安全从 scene 移除 item（C++ 可能已 deleteLater）。"""
    if scene is None or item is None:
        return
    try:
        scene.removeItem(item)
    except RuntimeError:
        pass


# ============================================================
# 节点删除：纯收缩（scale 1→0），不动 opacity
# ============================================================


class _ShrinkAnimator(QVariantAnimation):
    """⭐ 节点删除：scale 1→0，中心点保持（仿 EntityShrinkEffect）。

    注意：scale=0 时节点仍然在 scene 里（paint 仍占位置但 rect→0），
    动画结束回调里把它彻底从 scene 移除即可。
    """

    def __init__(self, target: QGraphicsItem, duration_ms: int):
        super().__init__()
        self._target = target
        # 中心点保持：把 transform origin 设到节点中心
        rect = target.boundingRect()
        target.setTransformOriginPoint(rect.center())
        self.setDuration(duration_ms)
        self.setStartValue(1.0)
        self.setEndValue(0.0)
        self.setEasingCurve(QEasingCurve.OutCubic)

    def updateCurrentValue(self, value) -> None:  # type: ignore[override]
        try:
            self._target.setScale(value)
        except RuntimeError:
            pass


def play_node_delete_animation(
    node_item: QGraphicsItem,
    on_finished: Callable[[], None],
    duration_ms: int = DELETE_DURATION_MS,
) -> QParallelAnimationGroup:
    """⭐ 节点删除特效：scale 1→0（仿 project-graph EntityShrinkEffect）。

    Returns:
        QParallelAnimationGroup（外部可保存引用防止 GC）
    """
    group = QParallelAnimationGroup()
    group.addAnimation(_ShrinkAnimator(node_item, duration_ms))
    group.finished.connect(on_finished)
    group.start()
    return group


# ============================================================
# 边淡出（保留旧 API：opacity 1→0）
# ============================================================


def _animate_opacity(
    item: QGraphicsItem, end: float, duration_ms: int
) -> QPropertyAnimation:
    """⭐ 给 QGraphicsItem 装 QGraphicsOpacityEffect 并动画 opacity。"""
    eff = QGraphicsOpacityEffect()
    eff.setOpacity(1.0)
    item.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity")
    anim.setDuration(duration_ms)
    anim.setStartValue(1.0)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    return anim


def play_edge_delete_animation(
    edge_item: QGraphicsItem,
    on_finished: Callable[[], None] | None = None,
    duration_ms: int = EDGE_FADE_DURATION_MS,
) -> QParallelAnimationGroup:
    """⭐ 边删除特效：opacity 1→0（淡出，不缩以避免端点跳动）。"""
    group = QParallelAnimationGroup()
    group.addAnimation(_animate_opacity(edge_item, 0.0, duration_ms))
    if on_finished is not None:
        group.finished.connect(on_finished)
    group.start()
    return group


# ============================================================
# ⭐ 切割线残影（仿 LineCuttingEffect）
# ============================================================


class _CuttingTrailItem(QGraphicsPathItem):
    """⭐ 切割线残影：起点→末端，颜色随 rate 从"红"渐变到"黄"再淡出。

    仿 LineCuttingEffect：起点的 alpha=1，颜色为 fromColor；
    末端 alpha=0，颜色为 toColor。整体宽 = lineWidth * (1 - rate)。
    """

    def __init__(
        self, start: QPointF, end: QPointF, from_color: QColor, to_color: QColor
    ):
        super().__init__()
        self._start = QPointF(start)
        self._end = QPointF(end)
        self._from = QColor(from_color)
        self._to = QColor(to_color)
        self.setZValue(1000)  # 顶层
        self._update_path(0.0)

    def _update_path(self, rate: float) -> None:
        """rate=0: 整条线满；rate=1: 末端 0%；rate 中间: 从 start 移到 start+(end-start)*rate。"""
        from PySide6.QtGui import QPainterPath

        head = QPointF(
            self._start.x() + (self._end.x() - self._start.x()) * rate,
            self._start.y() + (self._end.y() - self._start.y()) * rate,
        )
        path = QPainterPath(self._start)
        path.lineTo(head)
        self.setPath(path)
        # 渐变笔刷：start 端红，end 端透明（rate 控制长度）
        self.setPen(
            QPen(self._from, max(1.5, 4 * (1 - rate)), Qt.SolidLine, Qt.RoundCap)
        )


def play_cutting_trail(
    scene: QGraphicsScene,
    start: QPointF,
    end: QPointF,
    on_finished: Callable[[], None] | None = None,
    duration_ms: int = CUT_TRAIL_DURATION_MS,
) -> QVariantAnimation:
    """⭐ 在 scene 上画一条从 start 向 end 扫过的渐隐激光。

    Args:
        scene: 目标 scene（必须非 None）
        start: 起点（scene 坐标）
        end: 终点（scene 坐标）
        on_finished: 动画结束回调（通常用于把残影 item 从 scene 移除）
        duration_ms: 时长，默认 400ms

    Returns:
        QVariantAnimation（外部可保存引用防止 GC）
    """
    from_color = QColor(255, 80, 80)  # 起点：鲜红
    to_color = QColor(255, 200, 100)  # 末端：金黄
    trail = _CuttingTrailItem(start, end, from_color, to_color)
    scene.addItem(trail)

    anim = QVariantAnimation()
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _on_value(v):
        try:
            trail._update_path(v)
            trail.setOpacity(1.0 - v)
        except RuntimeError:
            pass

    anim.valueChanged.connect(_on_value)
    if on_finished is not None:
        anim.finished.connect(lambda: on_finished())
    anim.finished.connect(lambda: _safe_remove_from_scene(scene, trail))
    anim.start()
    return anim


# ============================================================
# ⭐ 火花闪光（仿 CircleFlameEffect）
# ============================================================


class _SparkItem(QGraphicsEllipseItem):
    """⭐ 圆形闪光特效：QRadialGradient 中心亮、边缘透明，半径随 rate 扩散。"""

    def __init__(self, center: QPointF, radius: float, color: QColor):
        from PySide6.QtCore import QRectF

        super().__init__(QRectF(-radius, -radius, radius * 2, radius * 2))
        self._radius = radius
        self._color = QColor(color)
        self.setPos(center)
        self.setZValue(999)
        self._refresh(1.0)

    def _refresh(self, alpha: float) -> None:
        """alpha: 中心透明度（0-1）。"""
        c = QColor(self._color)
        c.setAlphaF(max(0.0, min(1.0, alpha)))
        grad = QRadialGradient(0, 0, self._radius)
        grad.setColorAt(0.0, c)
        c2 = QColor(c)
        c2.setAlphaF(0.0)
        grad.setColorAt(1.0, c2)
        self.setBrush(QBrush(grad))
        self.setPen(QPen(Qt.NoPen))


def play_spark_effect(
    scene: QGraphicsScene,
    center: QPointF,
    radius: float = 18.0,
    color: QColor | None = None,
    on_finished: Callable[[], None] | None = None,
    duration_ms: int = SPARK_DURATION_MS,
) -> QVariantAnimation:
    """⭐ 圆形火花闪光：在 center 点爆发出一个 radius 范围的渐变圆。

    Args:
        scene: 目标 scene
        center: 闪光中心（scene 坐标）
        radius: 最大半径
        color: 主色（默认暖黄白）
        on_finished: 结束回调
        duration_ms: 时长，默认 300ms

    Returns:
        QVariantAnimation（外部可保存引用）
    """
    if color is None:
        color = QColor(255, 220, 120)
    spark = _SparkItem(center, radius, color)
    scene.addItem(spark)

    anim = QVariantAnimation()
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _on_value(rate):
        try:
            # 半径扩散 + 中心 alpha 1→0
            scale = 0.3 + 0.7 * rate
            spark.setScale(scale)
            spark._refresh(1.0 - rate)
        except RuntimeError:
            pass

    anim.valueChanged.connect(_on_value)
    if on_finished is not None:
        anim.finished.connect(lambda: on_finished())
    anim.finished.connect(lambda: _safe_remove_from_scene(scene, spark))
    anim.start()
    return anim


# ============================================================
# ⭐ 整合：划线切割结束时一次性播放"残影 + 火花"
# ============================================================


def play_cut_release_effects(
    scene: QGraphicsScene,
    start: QPointF,
    end: QPointF,
    collide_points: list[QPointF] | None = None,
    on_finished: Callable[[], None] | None = None,
) -> list:
    """⭐ 划线松开后播放：1) 切线残影 2) 每个碰撞点的火花闪光。

    Args:
        scene: 目标 scene
        start: 划线起点
        end: 划线末端
        collide_points: 切线与节点矩形边的交点列表（用于火花）
        on_finished: 全部特效结束后回调（可选）

    Returns:
        list[QVariantAnimation]（外部需保存引用防 GC）
    """
    anims = []
    # 1) 切线残影
    anims.append(play_cutting_trail(scene, start, end))
    # 2) 火花（每个交点一个）
    if collide_points:
        for pt in collide_points:
            anims.append(play_spark_effect(scene, pt))
    if on_finished is not None:
        # 监听最后一个结束
        if anims:
            anims[-1].finished.connect(lambda: on_finished())
    return anims
