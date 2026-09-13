"""思维导图画布（QGraphicsView）。

特性：
- 鼠标滚轮缩放
- 拖拽平移
- 添加/删除节点和边
- 节点位置变化回调

P4 负责维护。
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
)

# PySide6 坑：DontSavePainterState/DontAdjustForAntialiasing 这两个名字在
# QGraphicsView.ViewportCacheModeFlag 和 QGraphicsView.OptimizationFlag 两个枚举里都有，
# 未限定查找会拿到 CacheModeFlag 的成员（与 setOptimizationFlag 不兼容）。
# 另外本版本 PySide6 的 OptimizationFlag 只有这三个值：
#   DontSavePainterState / DontAdjustForAntialiasing / IndirectPainting
# 没有 CacheBackground（Qt 5.13+ 才有，但绑定可能缺失）。
_GV_OPT_FLAG = QGraphicsView.OptimizationFlag

from src.config import (
    NODE_DEFAULT_COLOR,
    NODE_DEFAULT_HEIGHT,
    NODE_DEFAULT_WIDTH,
)
from src.ui.delete_effect import play_edge_delete_animation, play_node_delete_animation
from src.ui.edge_item import EdgeItem
from src.ui.effects import NebulaItem, StarfieldItem
from src.ui.link_particles import LinkParticlesItem  # ⭐ 链接光点
from src.ui.node_item import NodeItem
from src.ui.root_bloom import RootBloomItem  # ⭐ 根节点 bloom 环
from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.mindmap_view")

# ⭐ 划线切割体感参数（让"靠近"也能切中，不用画很长）
CUT_NODE_HIT_INFLATE = 6.0  # 节点命中矩形向外膨胀的像素（点到节点边缘也算穿过）
CUT_EDGE_HIT_TOLERANCE = 6.0  # 边线距离容差：激光线离边 ≤ 此值就算"切到"
CUT_MIN_LENGTH = 10.0  # 最小划线长度（scene 坐标），太短不触发切割


def _segments_intersect(a: QLineF, b: QLineF) -> bool:
    """⭐ 两个线段（端到端）是否真的相交（不算延长线交点）。

    PySide6 的 QLineF.intersects() 返回 (IntersectionType, QPointF) 元组。
    - BoundedIntersection：两段线段端到端真正相交 ✅
    - UnboundedIntersection：延长线相交（端点接触 / 平行延伸相交）❌
        例如水平线 y=50 与矩形的垂直边（x=8 和 x=18）会在延长后相交，
        但物理线段不相交，这种情况不应算"被划线穿过"。
    - NoIntersection：完全不相交 ❌
    """
    try:
        result_tuple = a.intersects(b)
        # PySide6 返回 (enum, QPointF)；纯 enum 的版本（老 PyQt5）也兼容
        intersect_type = (
            result_tuple[0] if isinstance(result_tuple, tuple) else result_tuple
        )
    except Exception:
        return False
    return intersect_type == QLineF.BoundedIntersection


def _segments_intersect_touch_endpoint(a: QLineF, b: QLineF) -> bool:
    """⭐ 端点接触也算相交（用于端点紧贴边角的特殊情况）。"""
    if _segments_intersect(a, b):
        return True
    # 额外：任一线段端点落在另一线段上
    for p in (a.p1(), a.p2()):
        if _point_on_segment(p, b):
            return True
    for p in (b.p1(), b.p2()):
        if _point_on_segment(p, a):
            return True
    return False


def _point_on_segment(p: QPointF, seg: QLineF) -> bool:
    """⭐ 点 p 是否在线段 seg 上（含端点）。"""
    # 用 QPointF 与 QLineF 的角度关系判断 + 距离容差
    # 简化：用 toLine 返回 p-p1 是否与 p2-p1 共线且距离为 0
    if p == seg.p1() or p == seg.p2():
        return True
    # 向量叉积 ≈ 0 表示共线
    v1x = seg.p2().x() - seg.p1().x()
    v1y = seg.p2().y() - seg.p1().y()
    v2x = p.x() - seg.p1().x()
    v2y = p.y() - seg.p1().y()
    cross = abs(v1x * v2y - v1y * v2x)
    if cross > 0.01:
        return False
    # 检查投影是否落在 seg 内（参数 t∈[0,1]）
    len_sq = v1x * v1x + v1y * v1y
    if len_sq < 0.0001:
        return False
    t = (v2x * v1x + v2y * v1y) / len_sq
    return 0.0 <= t <= 1.0


def _point_to_segment_distance(p: QPointF, seg: QLineF) -> float:
    """⭐ 点 p 到线段 seg 的最短距离（端点也算 0）。"""
    # 用 QLineF 内置的 pointAt 反投影
    # p 在 seg 上的投影参数 t∈[0,1]
    v1x = seg.p2().x() - seg.p1().x()
    v1y = seg.p2().y() - seg.p1().y()
    v2x = p.x() - seg.p1().x()
    v2y = p.y() - seg.p1().y()
    len_sq = v1x * v1x + v1y * v1y
    if len_sq < 0.0001:
        # 退化线段（两点重合）→ 距离就是 p 到 p1
        return ((p.x() - seg.p1().x()) ** 2 + (p.y() - seg.p1().y()) ** 2) ** 0.5
    t = max(0.0, min(1.0, (v2x * v1x + v2y * v1y) / len_sq))
    proj_x = seg.p1().x() + t * v1x
    proj_y = seg.p1().y() + t * v1y
    return ((p.x() - proj_x) ** 2 + (p.y() - proj_y) ** 2) ** 0.5


def _segment_distance(a: QLineF, b: QLineF) -> float:
    """⭐ 两线段之间的最短距离（任一端点到另一线段的最小距离）。"""
    return min(
        _point_to_segment_distance(a.p1(), b),
        _point_to_segment_distance(a.p2(), b),
        _point_to_segment_distance(b.p1(), a),
        _point_to_segment_distance(b.p2(), a),
    )


def _line_length(a: QPointF, b: QPointF) -> float:
    """⭐ 两点之间的直线长度。"""
    return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5


def _line_intersects_rect(line: QLineF, rect) -> bool:
    """⭐ 线段是否与矩形相交（端点接触也算）。

    实现：线段端点都在矩形内 → true；否则用矩形 4 条边与线段求交（端到端 + 端点接触）。
    """
    from PySide6.QtCore import QRectF

    if not isinstance(rect, QRectF):
        # 兼容传入 sceneBoundingRect() 的 QRectF
        return False
    # 端点在矩形内
    if rect.contains(line.p1()) or rect.contains(line.p2()):
        return True
    # 矩形四条边
    edges = [
        QLineF(rect.topLeft(), rect.topRight()),
        QLineF(rect.topRight(), rect.bottomRight()),
        QLineF(rect.bottomRight(), rect.bottomLeft()),
        QLineF(rect.bottomLeft(), rect.topLeft()),
    ]
    return any(_segments_intersect_touch_endpoint(line, e) for e in edges)


class MindMapView(QGraphicsView):
    """思维导图画布。"""

    # 自定义信号
    node_position_changed = Signal(str, float, float)  # (node_id, x, y)
    node_text_edit_requested = Signal(object)  # NodeItem
    node_add_child_requested = Signal(object)  # ⭐ 右键添加子节点
    node_add_image_requested = Signal(object)  # ⭐ 右键添加图片
    node_remove_image_requested = Signal(object)  # ⭐ 右键删除图片
    node_delete_requested = Signal(object)  # ⭐ 右键删除节点
    node_color_change_requested = Signal(object, str)  # ⭐ 右键改颜色 (NodeItem, hex)
    cut_confirmed = Signal(list, list)  # ⭐ (nodes_to_delete, edges_to_delete) 切割确认
    node_create_at_requested = Signal(
        float, float
    )  # ⭐ 双击空白处创建节点 (scene_x, scene_y)
    node_connect_requested = Signal(str, str)  # ⭐ 拖线连接 (source_id, target_id)

    def _safe_remove_item(self, item) -> None:
        """⭐ scene.removeItem 安全包装（item 可能已被 deleteLater，C++ 抛 Internal error）。"""
        try:
            self._scene.removeItem(item)
        except RuntimeError:
            pass

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # 创建 scene
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-2000, -2000, 4000, 4000)
        # ⭐ 星空底色：深空蓝黑（比 #0f0f0f 更"冷"，让星点和星云自然浮现）
        self._scene.setBackgroundBrush(QBrush(QColor("#050810")))
        self.setScene(self._scene)

        # ⭐ 星空背景层：星云（最底）+ 星点（拆 near/far 两层做视差）
        # 三者均为 QGraphicsItem，统一走 scene 渲染管线和 z 排序
        self._nebula = NebulaItem()
        self._scene.addItem(self._nebula)
        # ⭐ 视差星空：near 层 z=-90 跟 view 同步移动，far 层 z=-110 只跟 50%
        # 拖动画布时两层相对运动 → 真"宇宙纵深"感
        self._starfield_near = StarfieldItem(layer="near")
        self._starfield_far = StarfieldItem(layer="far")
        # 兼容旧代码：保留 _starfield 引用为 _starfield_near
        self._starfield = self._starfield_near
        self._scene.addItem(self._starfield_near)
        self._scene.addItem(self._starfield_far)

        # ⭐ 链接光点层：沿每条边流动的小光点（d3-force-graph 招牌效果）
        # z=0.5：在边(0)之上、节点(1/10)之下 → 视觉上像被节点遮挡
        self._link_particles = LinkParticlesItem(self)
        self._scene.addItem(self._link_particles)

        # ⭐ 根节点 bloom 环（"中心天体"暗示）—— 仅 Browse 模式可见
        # z=-50：在 starfield(-100/-110)之上、节点(1)之下
        self._root_bloom = RootBloomItem()
        self._scene.addItem(self._root_bloom)

        # ⭐ 性能优化 1：智能视口更新（避免不必要的全场景重绘）
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)

        # ⭐ 性能优化 2：启用 Qt 提供的缓存/优化标志（绑定里只暴露了这两个）
        self.setOptimizationFlag(_GV_OPT_FLAG.DontSavePainterState, True)
        self.setOptimizationFlag(_GV_OPT_FLAG.DontAdjustForAntialiasing, True)

        # ⭐ 性能优化 3：场景的 BSP 索引（节点多时大幅提升 hitTest）
        self._scene.setItemIndexMethod(QGraphicsScene.BspTreeIndex)

        # 视图属性
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        # 注意：不要开启 SmoothPixmapTransform，拖动时严重影响性能
        self.setDragMode(QGraphicsView.ScrollHandDrag)  # 中键/空格+拖动平移
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setMinimumSize(400, 300)

        # 缓存
        self._node_items: dict[str, NodeItem] = {}  # node_id -> NodeItem
        self._edge_items: list[EdgeItem] = []

        # ⭐ 性能优化 5：每个节点关联它作为源/目标的边（O(1) 查找）
        self._node_to_edges: dict[str, list[EdgeItem]] = {}

        # 缩放范围
        self._zoom_min = 0.2
        self._zoom_max = 3.0
        self._zoom_factor = 1.15

        # ⭐ 缩放缓动（project-graph 风格）：Ctrl+滚轮不再直接 scale()，
        #     而是更新 _target_scale，由定时器每帧把 current_scale 拉近 30%，
        #     视觉上"快速起步、缓慢到位"，silky smooth。
        self._target_scale: float = 1.0
        self._zoom_anim_timer = QTimer(self)
        self._zoom_anim_timer.setInterval(16)  # ~60fps
        self._zoom_anim_timer.timeout.connect(self._tick_zoom_anim)

        # ⭐ Reveal animation：进入 Browse 时 scale 从 0.4 缓动到 fit 后的目标值（"星系浮现"）
        # 借鉴 galaxy-view 的 reveal animation：bloom galaxy out of the center on open
        self._reveal_phase: float = 0.0
        self._reveal_phase_step: float = 0.0
        self._reveal_target_scale: float = 1.0
        self._reveal_active: bool = False
        self._reveal_anchor: QPointF | None = (
            None  # ⭐ 视口中心的场景锚点（scale 时保持不动）
        )
        self._reveal_anim_timer = QTimer(self)
        self._reveal_anim_timer.setInterval(16)  # 60fps
        self._reveal_anim_timer.timeout.connect(self._tick_reveal_anim)

        # ⭐ 性能优化 6：拖动状态（动态开关抗锯齿）
        self._is_dragging = False
        # ⭐ 删除动画引用池（防止 Python GC 回收进行中的 QParallelAnimationGroup）
        self._active_delete_anims: list = []

        # ⭐ 切割控制器状态（右键拖拽空白处触发）
        self._is_cutting = False
        self._cut_start: QPointF | None = None
        self._cut_line_item: QGraphicsLineItem | None = None
        self._cut_warning_nodes: set[str] = set()
        self._cut_warning_edges: set[int] = set()  # 用 id(edge) 去重
        self._cut_warning_last_pos: QPointF | None = (
            None  # ⭐ 末次鼠标位置（计算划线总长用）
        )

        # ⭐ 拖线连接状态（从节点连接点拖到目标）
        self._is_connecting = False
        self._connect_source_node: NodeItem | None = None
        self._connect_line_item: QGraphicsLineItem | None = None
        # ⭐ 附加边缓存（重建边时使用）：[(source_id, target_id, db_id), ...]
        self._extra_edges_to_rebuild: list[tuple[str, str, int]] = []

        # 绑定 NodeItem 静态信号到实例方法
        NodeItem.text_edit_requested = self._on_node_edit_requested
        NodeItem.add_child_requested = self._on_node_add_child
        NodeItem.add_image_requested = self._on_node_add_image
        NodeItem.remove_image_requested = self._on_node_remove_image
        NodeItem.delete_requested = self._on_node_delete  # ⭐ 修复：右键删除节点
        NodeItem.color_change_requested = self._on_node_color_change  # ⭐ 右键改颜色
        NodeItem.port_drag_started = self._on_port_drag_started  # ⭐ 连接点拖线
        NodeItem.nebula_label_toggle_requested = (
            self._on_nebula_label_toggle
        )  # ⭐⭐ nebula 模式点击切换 label

        # ⭐ Focus mode（Browse 沉浸式体验）：监听选中变化 → 自动暗化非邻居节点/边
        # 默认 False；由 main_window._set_view_mode 进入 BROWSE 时打开
        self._focus_mode_enabled: bool = False

        # ⭐ 星云模式（Browse 内可切换的视图风格）：节点变发光圆点 + hover tooltip
        # 默认 False；由 main_window 的"🌌 星云视图"按钮切换
        self._nebula_mode: bool = False
        self._scene.selectionChanged.connect(self._on_selection_changed_for_focus)

        logger.info("MindMapView 初始化完成")

    # ==================== ⭐ 星空背景（替代原 project-graph 点阵）====================
    #
    # 设计变更（2026-09-13）：
    # - 原本的"自适应点阵网格"在星空视觉里喧宾夺主（点 vs 星星质感冲突）
    # - 现在：背景填充交给 super().drawBackground（深空蓝黑 #050810），
    #   星点和星云通过两个 QGraphicsItem（NebulaItem z=-200 / StarfieldItem z=-100）
    #   加进 scene，由 scene 渲染管线自然处理层级
    # - drawBackground 不再做点阵，只负责底色填充

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """⭐ 星空底色填充（深空蓝黑），星点/星云由独立 scene item 处理。"""
        super().drawBackground(painter, rect)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """⭐⭐ 没 mindmap 时在画布中央显示「📂 点击右上角「选导图」」占位提示（2026-09-13）。

        不引外部资源、不抢星空的戏，仅在「画布空 + 没节点」时画一段半透明文字。
        用户进入 app 一眼就知道下一步该点哪儿。
        """
        super().drawForeground(painter, rect)
        if self._node_items:
            return  # 有节点就不显示占位
        painter.save()
        painter.resetTransform()
        # 视口中心
        viewport_rect = self.viewport().rect()
        cx = viewport_rect.width() / 2
        cy = viewport_rect.height() / 2
        # 文字两行（emoji 用稍大字号，颜色 cyan 提示）
        font_big = QFont("Segoe UI Emoji", 28)
        painter.setFont(font_big)
        painter.setPen(QColor(255, 255, 255, 70))
        painter.drawText(
            QRectF(0, cy - 60, viewport_rect.width(), 50),
            Qt.AlignCenter,
            "📂",
        )
        font_text = QFont("Microsoft YaHei", 14)
        painter.setFont(font_text)
        painter.setPen(QColor(229, 231, 235, 200))
        painter.drawText(
            QRectF(0, cy + 0, viewport_rect.width(), 30),
            Qt.AlignCenter,
            "点击右上角「选导图」开始",
        )
        font_small = QFont("Microsoft YaHei", 10)
        painter.setFont(font_small)
        painter.setPen(QColor(148, 163, 184, 160))
        painter.drawText(
            QRectF(0, cy + 32, viewport_rect.width(), 24),
            Qt.AlignCenter,
            "或按 F2 进入编辑模式新建导图",
        )
        painter.restore()

    # ==================== 鼠标交互 ====================

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """⭐ 拖动开始时关闭抗锯齿（性能优化）。"""
        # ⭐ 切割启动：右键按下
        # 命中 NodeItem → 不 accept，让 Qt 派发 contextMenuEvent（弹右键菜单）
        # 命中 EdgeItem 或空白 → 启 cutting（用户想划线切割）
        if event.button() == Qt.RightButton:
            scene_pos = self.mapToScene(event.pos())
            item_at = self._scene.itemAt(scene_pos, self.transform())
            if item_at is None or isinstance(item_at, EdgeItem):
                # 空白或边上 → 启动 cutting
                self._start_cutting(scene_pos)
                event.accept()
                return
            # 节点上 → super() 让 NodeItem.contextMenuEvent 接管
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            # 关闭抗锯齿，拖动流畅度提升 30-50%
            self.setRenderHint(QPainter.Antialiasing, False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """⭐ 切割时实时更新激光线 + 高亮。"""
        if self._is_cutting:
            scene_pos = self.mapToScene(event.pos())
            self._update_cutting(scene_pos)
            event.accept()
            return
        if self._is_connecting:
            self._update_connecting(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """⭐ 拖动结束后恢复抗锯齿。"""
        if self._is_cutting and event.button() == Qt.RightButton:
            self._finish_cutting()
            event.accept()
            return
        if self._is_connecting and event.button() == Qt.LeftButton:
            self._finish_connecting(event.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            # 恢复抗锯齿，让画面看起来精致
            self.setRenderHint(QPainter.Antialiasing, True)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """⭐ 双击空白处 → 创建独立节点（无父）。"""
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            item_at = self._scene.itemAt(scene_pos, self.transform())
            if item_at is None:
                # 空白处：通知主窗口在 scene_pos 创建新节点
                self.node_create_at_requested.emit(scene_pos.x(), scene_pos.y())
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """滚轮缩放（带缓动）。"""
        # Ctrl + 滚轮才缩放，普通滚轮平移
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = self._zoom_factor if delta > 0 else 1 / self._zoom_factor

            # ⭐ 不再直接 scale()，改为更新 target 让定时器每帧 lerp
            cur = self.transform().m11()
            target = max(self._zoom_min, min(self._zoom_max, cur * factor))
            if abs(target - cur) > 1e-4:
                self._target_scale = target
                if not self._zoom_anim_timer.isActive():
                    self._zoom_anim_timer.start()
        else:
            super().wheelEvent(event)

    def _tick_zoom_anim(self) -> None:
        """⭐ 缩放缓动：每帧把 current_scale 拉近 target_scale 的 30%。

        指数趋近：每帧剩 70%，所以大约 10 帧（~170ms）到位。
        用户中途再滚轮：target 更新，lerp 平滑切到新目标，不会跳变。
        """
        cur = self.transform().m11()
        diff = self._target_scale - cur
        if abs(diff) < 1e-3:
            # 已到达目标，把当前值 snap 到 target 并停定时器
            if cur != self._target_scale:
                snap = self._target_scale / cur
                self.scale(snap, snap)
            self._zoom_anim_timer.stop()
            return
        # 每帧拉近 30%（project-graph 风格的 ease-out 体感）
        factor = 1.0 + (diff / cur) * 0.30
        self.scale(factor, factor)

    # ==================== ⭐ Reveal animation（"星系浮现"开场）====================
    #
    # 借鉴 galaxy-view 的 reveal animation: bloom the galaxy out of the center on open.
    # 进入 Browse / 打开新导图时调用：scale 从 0.4 缓动到当前 fit 后的目标值，
    # 视觉上"星系从远处放大浮现"——这是沉浸式开场最有冲击力的效果。
    #
    # 用 lerp 定时器（与 _zoom_anim 同模式）实现，不用 QPropertyAnimation，
    # 因为 QGraphicsView.transform() 没有 Q_PROPERTY 可以绑定。

    REVEAL_START_SCALE = 0.4  # 起始缩放（远）
    REVEAL_DURATION_MS = 400  # 总时长

    def play_reveal_animation(self, duration_ms: int = REVEAL_DURATION_MS) -> None:
        """⭐ 播放 reveal 动画：scale 从 0.4 缓动到当前 fit 后的目标值。

        调用时机：进入 Browse 模式 / 打开新导图（fit 完成后）。
        重复调用会重启动画（取消上一次，从当前 scale 重新开始）。

        关键不变式：动画全程让「视口中心的场景点」保持在视口中心。
        因为 ``self.scale()`` 是围绕场景原点缩放，会让视口中心的场景点偏离；
        所以每帧缩放后立即 ``centerOn(anchor)`` 回正——视觉上节点从视口中心
        "绽放"出来，而不是从角落飞过来。
        """
        # 取消上一次（防止叠加）
        if self._reveal_active:
            self._reveal_anim_timer.stop()
        # ⭐⭐ 锚点 = 当前视口中心映射到场景的坐标。整个动画过程让它一直停在视口中心。
        try:
            self._reveal_anchor = self.mapToScene(self.viewport().rect().center())
        except RuntimeError:
            self._reveal_anchor = None
        target = self.transform().m11()
        # 防御：极端值保护（避免被 0 除）
        if target < 0.05:
            target = 1.0
        self._reveal_target_scale = target
        # 60fps 下每帧推进量 = 1.0 / (总时长 / 16ms)
        self._reveal_phase_step = 1.0 / max(1, duration_ms / 16.0)
        self._reveal_phase = 0.0
        # 立刻 shrink 到 0.4（视觉上"跳远"），再 centerOn 回正
        try:
            shrink = self.REVEAL_START_SCALE / target
            self.scale(shrink, shrink)
            if self._reveal_anchor is not None:
                self.centerOn(self._reveal_anchor)
        except (RuntimeError, ZeroDivisionError):
            return  # view 已析构
        self._reveal_active = True
        self._reveal_anim_timer.start()

    def is_reveal_active(self) -> bool:
        return self._reveal_active

    def stop_reveal_animation(self) -> None:
        """⭐ 主动停止 reveal（切导图 / 切模式时防御性调用）。"""
        if self._reveal_active:
            self._reveal_anim_timer.stop()
            self._reveal_active = False
            self._reveal_phase = 0.0

    def _tick_reveal_anim(self) -> None:
        """⭐ Reveal 动画每帧推进：scale 从 0.4 lerp 到 target（ease-out 三次方）。

        ease-out: t'=1-(1-t)³ —— 开局快、结尾慢，符合"浮现"的物理感。
        每帧缩放后立即 ``centerOn(anchor)`` 保持视口中心点不动，节点像
        从视口中心"绽放"出来。
        """
        self._reveal_phase += self._reveal_phase_step
        if self._reveal_phase >= 1.0:
            # 完成：snap 到 target，停定时器
            try:
                cur = self.transform().m11()
                if abs(cur - self._reveal_target_scale) > 1e-4:
                    snap = self._reveal_target_scale / cur
                    self.scale(snap, snap)
            except RuntimeError:
                pass
            # ⭐⭐ 最终再 centerOn 一次（防御 floating drift）
            if self._reveal_anchor is not None:
                try:
                    self.centerOn(self._reveal_anchor)
                except RuntimeError:
                    pass
            self._reveal_anim_timer.stop()
            self._reveal_active = False
            self._reveal_phase = 0.0
            return
        # ease-out cubic
        t = self._reveal_phase
        eased = 1.0 - (1.0 - t) ** 3
        try:
            cur = self.transform().m11()
            target_now = (
                self.REVEAL_START_SCALE
                + (self._reveal_target_scale - self.REVEAL_START_SCALE) * eased
            )
            if abs(cur - target_now) > 1e-4:
                factor = target_now / cur
                self.scale(factor, factor)
                # ⭐⭐ self.scale 会让 anchor 偏离视口中心，立即回正
                if self._reveal_anchor is not None:
                    self.centerOn(self._reveal_anchor)
        except RuntimeError:
            self._reveal_anim_timer.stop()
            self._reveal_active = False

    def leaveEvent(self, event) -> None:
        """⭐ 鼠标移出 view 窗口时：强制完成切割（project-graph mouseMoveOutWindowForcedShutdown）。"""
        if self._is_cutting:
            self._finish_cutting()
        super().leaveEvent(event)

    # ==================== ⭐ 星空视差（pan 时两层错速移动）====================
    #
    # 借鉴 galaxy-view 的 "drifting field stars with parallax"：
    # - near 层（粗星）跟 view 同步移动 → 视觉上"贴近相机"
    # - far 层（细星）只跟 view 50% 移动 → 视觉上"远方星空"更"沉"
    # - 公式：item.moveBy(+dx * ratio, +dy * ratio)（正号抵消 view transform 的负平移）
    #
    # 注意：scrollContentsBy 是 QGraphicsView 内部 pan 调用的回调。
    # super() 会更新 view transform（让 scene 内容在屏幕上平移）。

    PARALLAX_NEAR_RATIO = 1.0  # 近层完全跟 view 同步
    PARALLAX_FAR_RATIO = 0.45  # 远层只跟 45%（越大差异越明显，但太大会"飞走"）

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """⭐ view pan 时调用：叠加星空视差。"""
        super().scrollContentsBy(dx, dy)
        # ⭐ 用 moveBy 累加：每次 pan 让两层按各自 ratio 跟动
        try:
            self._starfield_near.moveBy(
                dx * self.PARALLAX_NEAR_RATIO,
                dy * self.PARALLAX_NEAR_RATIO,
            )
            self._starfield_far.moveBy(
                dx * self.PARALLAX_FAR_RATIO,
                dy * self.PARALLAX_FAR_RATIO,
            )
        except RuntimeError:
            # ⭐ view/scene 已销毁（关闭中），跳过
            pass

    # ==================== 节点管理 ====================

    def add_node_item(
        self,
        node_id: str,
        text: str,
        x: float = 0.0,
        y: float = 0.0,
        color: str = NODE_DEFAULT_COLOR,
        parent_id: str | None = None,
        image_path: str | None = None,  # ⭐ 新增
    ) -> NodeItem:
        """添加节点到画布。

        Args:
            node_id: 节点唯一 ID
            text: 节点文本
            x, y: 位置
            color: 颜色
            parent_id: 父节点 ID（如果是 None 则为根节点）
            image_path: ⭐ 图片相对路径

        Returns:
            创建的 NodeItem 实例
        """
        node_item = NodeItem(
            node_id=node_id,
            text=text,
            color=color,
            x=x,
            y=y,
            width=NODE_DEFAULT_WIDTH,
            height=NODE_DEFAULT_HEIGHT,
            parent_id=parent_id,
            image_path=image_path,
        )
        # ⭐ 性能优化：注册节点移动回调（边会自动跟随）
        node_item.set_view_callback(self._on_node_position_changed)
        self._scene.addItem(node_item)
        self._node_items[node_id] = node_item
        # 初始化边的索引
        self._node_to_edges.setdefault(node_id, [])

        # 如果有父节点，创建连线
        if parent_id and parent_id in self._node_items:
            self._add_edge_between(parent_id, node_id)

        # 节点移动时通知数据库
        node_item.mouseReleaseEvent = self._wrap_mouse_release(node_item)

        # ⭐ 刷新根节点标记（金色 halo 用）
        self._refresh_root_flags()

        logger.debug(f"添加节点: {text} at ({x}, {y})")
        return node_item

    def _refresh_root_flags(self) -> None:
        """⭐ 根据 parent_id 刷新所有节点的根节点标记 + 更新 bloom 跟随。

        根节点 = parent_id is None。切割后被脱离的子节点变为新的根。
        多根时取"主根"（children 最多）作为 bloom 目标。
        """
        roots: list[NodeItem] = []
        for node in self._node_items.values():
            try:
                is_root = node.parent_id() is None
                node.set_is_root(is_root)
                if is_root:
                    roots.append(node)
            except RuntimeError:
                pass

        # ⭐ 找"主根"（children 最多）—— bloom 跟随这个节点
        main_root: NodeItem | None = None
        if roots:
            # children 数 = 出边数（edge.source == root）
            def child_count(n: NodeItem) -> int:
                cnt = 0
                for e in self._node_to_edges.get(n.node_id, []):
                    try:
                        if e.source.node_id == n.node_id:
                            cnt += 1
                    except (RuntimeError, AttributeError):
                        pass
                return cnt

            main_root = max(roots, key=child_count)

        try:
            self._root_bloom.set_target_node(main_root)
        except RuntimeError:
            pass

        # ⭐⭐ 计算每个节点的子树节点数（nebula 模式按 degree 缩放圆点大小）
        # 用 BFS 沿 parent_id 反向建树后，对每个节点累加子树大小
        self._compute_subtree_sizes()

    def _compute_subtree_sizes(self) -> None:
        """⭐⭐ 计算每个节点的子树节点数（含自身），写入 NodeItem._subtree_size。

        借鉴 galaxy-view computeSize：base × (1 + 0.4 × √degree)
        degree 越大 = 节点越"重要" = 圆点越大 = "星系中心"
        """
        # ⭐ 1. 建 parent → children 索引（只算树形边，不含附加边，避免重复）
        children_of: dict[str, list[str]] = {}
        for nid, node in self._node_items.items():
            try:
                pid = node.parent_id()
            except RuntimeError:
                pid = None
            if pid is not None:
                children_of.setdefault(pid, []).append(nid)
        # ⭐ 2. 自底向上 DFS 计算子树大小（后序）
        subtree_size: dict[str, int] = {}

        def dfs(nid: str) -> int:
            if nid in subtree_size:
                return subtree_size[nid]
            kids = children_of.get(nid, [])
            total = 1  # 自身
            for k in kids:
                total += dfs(k)
            subtree_size[nid] = total
            return total

        for nid in self._node_items.keys():
            try:
                dfs(nid)
            except RuntimeError:
                # 节点 C++ 已销毁（场景切换中），跳过
                pass

        # ⭐ 3. 写入 NodeItem
        for nid, size in subtree_size.items():
            node = self._node_items.get(nid)
            if node is not None:
                try:
                    node.set_subtree_size(size)
                except RuntimeError:
                    pass

    def _on_node_position_changed(self, node_item: NodeItem) -> None:
        """⭐ 节点位置变化时通知所有相邻的边更新。

        这是流畅拖动的关键——边要跟着节点实时重绘。
        """
        node_id = node_item.node_id
        edges = self._node_to_edges.get(node_id, [])
        for edge in edges:
            edge.node_moved()
        # ⭐ 根节点移动时 → bloom 跟随（场景里其他节点拖动不影响 bloom）
        try:
            if self._root_bloom._target_node is node_item:
                self._root_bloom.update_position()
        except RuntimeError:
            pass

    def _wrap_mouse_release(self, node_item: NodeItem):
        """包装 mouseReleaseEvent，在原事件后发位置变化信号。"""
        original = node_item.mouseReleaseEvent

        def wrapped(event):
            original(event)
            if event.button() == Qt.LeftButton:
                pos = node_item.pos()
                self.node_position_changed.emit(node_item.node_id, pos.x(), pos.y())

        return wrapped

    def remove_node_item(self, node_id: str, animate: bool = False) -> None:
        """删除节点（同时清理连边）。

        Args:
            node_id: 节点 ID
            animate: True=播放淡出+缩小动画后再删；False=立即删除（默认）
        """
        if node_id not in self._node_items:
            return
        node_item = self._node_items[node_id]

        if not animate:
            self._instant_remove_node(node_id)
            return

        # ⭐ 动画路径：相关边淡出 + 节点淡出+缩，结束后才真正从 scene 移除
        related_edges = [
            e
            for e in self._edge_items
            if e.source.node_id == node_id or e.target.node_id == node_id
        ]

        def _on_edge_done(edge: EdgeItem) -> None:
            self._safe_remove_item(edge)
            try:
                self._edge_items.remove(edge)
            except ValueError:
                pass

        def _on_node_done() -> None:
            self._safe_remove_item(node_item)
            self._node_items.pop(node_id, None)
            self._node_to_edges.pop(node_id, None)

        for edge in related_edges:
            anim = play_edge_delete_animation(edge, lambda e=edge: _on_edge_done(e))
            self._active_delete_anims.append(anim)
            anim.finished.connect(
                lambda a=anim: (
                    self._active_delete_anims.remove(a)
                    if a in self._active_delete_anims
                    else None
                )
            )
        node_anim = play_node_delete_animation(node_item, _on_node_done)
        self._active_delete_anims.append(node_anim)
        node_anim.finished.connect(
            lambda a=node_anim: (
                self._active_delete_anims.remove(a)
                if a in self._active_delete_anims
                else None
            )
        )

    def _instant_remove_node(self, node_id: str) -> None:
        """⭐ 立即删除节点（无动画，兼容旧调用）。"""
        node_item = self._node_items[node_id]
        self._safe_remove_item(node_item)
        del self._node_items[node_id]

        related_edges = [
            e
            for e in self._edge_items
            if e.source.node_id == node_id or e.target.node_id == node_id
        ]
        for edge in related_edges:
            self._safe_remove_item(edge)
        self._edge_items = [
            e
            for e in self._edge_items
            if e.source.node_id != node_id and e.target.node_id != node_id
        ]
        self._node_to_edges.pop(node_id, None)
        self._rebuild_edges()

    def update_node_text(self, node_id: str, text: str) -> None:
        """更新节点文本。"""
        if node_id in self._node_items:
            self._node_items[node_id].set_text(text)

    def update_node_image(self, node_id: str, image_path: str | None) -> None:
        """⭐ 更新节点图片（兼容旧 API）。"""
        if node_id in self._node_items:
            self._node_items[node_id].set_image_path(image_path)

    def update_node_attachment_count(self, node_id: str, count: int) -> None:
        """⭐ 更新节点附件数（用于 📷N 徽章）。"""
        if node_id in self._node_items:
            item = self._node_items[node_id]
            item.set_attachment_count(count)
            # 兼容：同步 image_path（让 has_image() 返回正确值）
            item.set_image_path("cover" if count > 0 else None)

    def get_selected_node(self) -> NodeItem | None:
        """获取当前选中的节点。"""
        selected = [
            item for item in self._scene.selectedItems() if isinstance(item, NodeItem)
        ]
        return selected[0] if selected else None

    def get_node_item(self, node_id: str) -> NodeItem | None:
        """根据 node_id 获取节点项。"""
        return self._node_items.get(node_id)

    # ==================== ⭐ Focus mode（沉浸式聚焦）====================
    #
    # 借鉴 galaxy-view 的 Focus mode：选中某节点后，其他节点的 opacity 降到 0.3，
    # 邻居（1-hop）保持 1.0，让用户立刻看清"这个点在整个思维星图里的位置"。
    # 仅在 Browse 模式启用；EDIT 模式关闭（用户需要完整视野编辑）。

    def set_focus_mode(self, enabled: bool) -> None:
        """⭐ main_window 在切到 Browse/Edit 时调用。

        enabled=True  → 启用 focus mode（之后选中节点会自动暗化非邻居）+ 显示根节点 bloom
        enabled=False → 关闭 focus mode，所有节点/边恢复全 opacity + 隐藏 bloom
        """
        self._focus_mode_enabled = bool(enabled)
        if not enabled:
            # 退出 focus mode：把所有 item 的 dimmed 状态清掉
            for node in self._node_items.values():
                try:
                    node.set_dimmed(False)
                except RuntimeError:
                    pass
            for edge in self._edge_items:
                try:
                    edge.set_dimmed(False)
                except RuntimeError:
                    pass
            # ⭐ 隐藏根节点 bloom（EDIT 模式不需要"中心天体"暗示）
            try:
                self._root_bloom.hide()
            except RuntimeError:
                pass
        else:
            # ⭐ 进入 focus mode（Browse）：如果已有根节点 → 显示 bloom
            try:
                if self._root_bloom._target_node is not None:
                    self._root_bloom.show()
            except RuntimeError:
                pass

    def is_focus_mode(self) -> bool:
        return self._focus_mode_enabled

    # ==================== ⭐ 星云模式（galaxy-view 风格） ====================
    #
    # 借鉴 galaxy-view + Obsidian：
    # 节点变成发光圆点（无文字），边变成细 filament（极细极淡），
    # hover 节点时通过 Qt 原生 tooltip 显示节点文字。
    # 沉浸式浏览大图，看不清细节时像星图星系。
    # 切换瞬间触发，主线程无延迟。

    def set_nebula_mode(self, enabled: bool) -> None:
        """⭐ main_window 的"🌌 星云视图"按钮调用。

        enabled=True  → 所有 NodeItem 进入 nebula（圆点 + tooltip）
                      → 所有 EdgeItem 变 filament（width 0.8 / alpha 0.35）
        enabled=False → 恢复默认（body + halo + text + 标准边）
        """
        self._nebula_mode = bool(enabled)
        # 遍历所有节点
        for node in self._node_items.values():
            try:
                node.set_nebula_mode(enabled)
            except RuntimeError:
                pass
        # 遍历所有边
        for edge in self._edge_items:
            try:
                edge.set_nebula_mode(enabled)
            except RuntimeError:
                pass
        # 通知 link_particles（如果存在，让光点也跟着调整透明度）
        try:
            if self._link_particles is not None:
                self._link_particles.update()
        except (RuntimeError, AttributeError):
            pass
        # 整体 scene 重绘（确保 z-order 等场景级状态同步）
        self._scene.update()
        logger.info(f"nebula mode → {enabled}")

    def is_nebula_mode(self) -> bool:
        return self._nebula_mode

    def restore_selection(self, node_ids: List[str]) -> None:
        """⭐⭐ main_window._open_mindmap 重建后调用：恢复选中态。

        用户反馈修复（2026-09-13）：添加附件/节点等 mutation 后整图重建会丢选中态。
        现在 _open_mindmap 会记录选中 node_id → 重建 → restore_selection 找回并 setSelected。

        找回不存在的节点（mutation 期间被删除）静默跳过。
        """
        if not node_ids:
            return
        for nid in node_ids:
            try:
                node = self._node_items.get(nid)
                if node is not None:
                    node.setSelected(True)
            except RuntimeError:
                # 节点 C++ 已销毁（场景切换中）
                pass
        # 同步 focus mode 的暗化（如果启用）
        if self._focus_mode_enabled:
            self._refresh_focus_dim()
        # 同步信号（让详情面板 / sidebar 等立即刷新到新选中的节点）
        self._scene.selectionChanged.emit()

    def _on_selection_changed_for_focus(self) -> None:
        """⭐ scene.selectionChanged 信号槽：focus mode 启用时刷新暗化。"""
        if not self._focus_mode_enabled:
            return
        self._refresh_focus_dim()

    def _refresh_focus_dim(self) -> None:
        """⭐ 计算 focus 集合（所有选中节点 + 1-hop 邻居），暗化其它所有 item。

        用 id(edge) 做集合（EdgeItem 没有稳定哈希，用对象 id 避免 hash 抖动）。
        """
        # ⭐ 多选支持：所有选中节点都进入 focus 集合（shift+click 多选也能正确处理）
        all_selected = [
            item for item in self._scene.selectedItems() if isinstance(item, NodeItem)
        ]
        if not all_selected:
            # 没有选中节点：清掉所有暗化
            for node in self._node_items.values():
                try:
                    node.set_dimmed(False)
                except RuntimeError:
                    pass
            for edge in self._edge_items:
                try:
                    edge.set_dimmed(False)
                except RuntimeError:
                    pass
            return

        # ⭐ focus 集合：所有选中节点 + 它们的 1-hop 邻居
        focus_nodes: set[str] = {n.node_id for n in all_selected}
        focus_edges: set[int] = set()
        for sel in all_selected:
            for edge in self._node_to_edges.get(sel.node_id, []):
                try:
                    other_id = (
                        edge.target.node_id
                        if edge.source.node_id == sel.node_id
                        else edge.source.node_id
                    )
                    focus_nodes.add(other_id)
                    focus_edges.add(id(edge))
                except (RuntimeError, AttributeError):
                    # ⭐ 端点 C++ 已销毁（场景切换中），跳过
                    continue

        # 应用暗化
        for nid, node in self._node_items.items():
            try:
                node.set_dimmed(nid not in focus_nodes)
            except RuntimeError:
                pass
        for edge in self._edge_items:
            try:
                edge.set_dimmed(id(edge) not in focus_edges)
            except RuntimeError:
                pass

    # ==================== 边管理 ====================

    def _add_edge_between(self, source_id: str, target_id: str) -> None:
        """在两个节点之间添加边。"""
        source = self._node_items.get(source_id)
        target = self._node_items.get(target_id)
        if not source or not target:
            return
        try:
            edge = EdgeItem(source, target)
            self._scene.addItem(edge)
            self._edge_items.append(edge)
            # 性能优化：注册到索引（节点移动时 O(1) 找边）
            self._node_to_edges.setdefault(source_id, []).append(edge)
            self._node_to_edges.setdefault(target_id, []).append(edge)
        except RuntimeError:
            pass  # view/scene 已析构（动画 finished 延迟回调）

    def _rebuild_edges(self) -> None:
        """重建所有边（树形 + 附加）。打开导图 / 切换导图后调用。"""
        # 清掉所有旧边
        for edge in self._edge_items:
            self._safe_remove_item(edge)
        self._edge_items.clear()
        self._node_to_edges.clear()

        # 1) 树形边：根据 parent_id 重建（无 db_id）
        for node_id, node_item in self._node_items.items():
            parent_id = node_item.parent_id()
            if parent_id and parent_id in self._node_items:
                self._add_edge_between(parent_id, node_id)

        # 2) ⭐ 附加边：从缓存重建（带 db_id）
        for sid, tid, eid in self._extra_edges_to_rebuild:
            if sid in self._node_items and tid in self._node_items:
                self._add_edge_view(sid, tid, edge_id=eid)

    def _rebuild_tree_edges(self) -> None:
        """⭐ 仅重建树形边（parent_id 推导），保留附加边。

        用于切割/脱离后：某些 child.parent_id 已被置 None，需要重新画树。
        附加边不动（db_id 非空），避免与 _animate_cut_edges 的 on_finished 撞。
        """
        # 1) 移除所有 db_id is None 的边（树形边），保留 db_id 非空的（附加边）
        kept = [e for e in self._edge_items if e.db_id is not None]
        for e in self._edge_items:
            if e.db_id is None:
                self._safe_remove_item(e)
        self._edge_items = kept
        # 2) 重建 _node_to_edges 索引
        self._rebuild_edge_index()
        # 3) 重建树形边
        for node_id, node_item in self._node_items.items():
            parent_id = node_item.parent_id()
            if parent_id and parent_id in self._node_items:
                self._add_edge_between(parent_id, node_id)

    def _rebuild_edge_index(self) -> None:
        """⭐ 根据当前 _edge_items 重建 _node_to_edges 索引。"""
        self._node_to_edges.clear()
        for nid in self._node_items:
            self._node_to_edges[nid] = []
        for e in self._edge_items:
            try:
                self._node_to_edges.setdefault(e.source.node_id, []).append(e)
                self._node_to_edges.setdefault(e.target.node_id, []).append(e)
            except (RuntimeError, AttributeError):
                continue

    def set_extra_edges(self, edges: list[tuple[str, str, int]]) -> None:
        """⭐ 注入附加边列表 [(source_id, target_id, db_id), ...] 并刷新边。

        通常在打开导图后由 main_window 调用一次。
        """
        self._extra_edges_to_rebuild = list(edges)
        self._rebuild_edges()

    def clear_extra_edges(self) -> None:
        """⭐ 清空附加边缓存（切换导图时调用）。"""
        self._extra_edges_to_rebuild = []

    def clear(self) -> None:
        """清空画布（⭐ 完整清理所有状态，防止切导图崩溃）。

        ⭐ 星空背景层（NebulaItem / StarfieldItem）保留：不要 scene.clear()，
        否则会把 z=-200/-100 的两个背景 item 也清掉，星空就消失了。
        """
        # 0) ⭐ 停 reveal 动画（切导图时如果动画还在跑，会和新动画叠加导致抖动）
        self.stop_reveal_animation()
        # 0.5) ⭐ 停 link particles 定时器（防御 view 销毁后定时器撞已死 item）
        try:
            self._link_particles._timer.stop()
        except RuntimeError:
            pass
        # 0.6) ⭐ 停 starfield 视差累加器（如果加了的话——目前只是定时器，关掉保险）
        # starfield 本身没运行状态需要重置，只是确保 timer 不会撞已死对象
        # （timer parent=None，会自己停，但主动 stop 更稳）
        # 1) 停所有在飞的删除动画（否则切导图时旧 anim 还在跑会 RuntimeError）
        for anim in list(self._active_delete_anims):
            try:
                anim.stop()
            except RuntimeError:
                pass
        self._active_delete_anims.clear()
        # 2) 取消切割 / 连接态（避免幽灵状态）
        if self._is_cutting:
            self.cancel_cutting()
        if self._is_connecting:
            self.cancel_connecting()
        # 3) 选择性移除：节点 + 边（保留星空背景）
        for node_id in list(self._node_items.keys()):
            self._safe_remove_item(self._node_items[node_id])
        for edge in list(self._edge_items):
            self._safe_remove_item(edge)
        self._node_items.clear()
        self._edge_items.clear()
        self._node_to_edges.clear()
        self._extra_edges_to_rebuild = []

    # ==================== ⭐ 切割控制器（划线删除） ====================

    def detach_and_remove_node(self, node_id: str, descendant_ids: list[str]) -> None:
        """⭐ 切割语义：仅删除节点本身，后代脱离为新根。

        与 remove_node_item 的区别：
        - remove_node_item：纯删一个节点（用于后代已经在外面被级联删）
        - detach_and_remove_node：删一个节点，同时把它的直接子节点 parent_id 置 None（保持后代可见）

        Args:
            node_id: 要删除的节点 ID
            descendant_ids: 该节点的全部后代 ID 列表（主窗口已从 graph 取过）
        """
        if node_id not in self._node_items:
            return
        node_item = self._node_items[node_id]

        # 1) 把后代的 parent_id 在 view 侧置 None（不删除后代节点本身）
        for did in descendant_ids:
            d = self._node_items.get(did)
            if d:
                d.set_parent_id(None)

        # 2) 播放删除动画（仅对被切割的节点本身）
        # 先解除后代到该节点的边（避免动画期间边指向"消失中"的节点）
        related_edges = [
            e
            for e in self._edge_items
            if e.source.node_id == node_id or e.target.node_id == node_id
        ]

        def _on_edge_done(edge: EdgeItem) -> None:
            self._safe_remove_item(edge)
            try:
                self._edge_items.remove(edge)
            except ValueError:
                pass

        def _on_node_done() -> None:
            self._safe_remove_item(node_item)
            self._node_items.pop(node_id, None)
            self._node_to_edges.pop(node_id, None)
            # ⭐ 只重建树形边（附加边由 _animate_cut_edges 走自己的 on_finished 路径）
            # 避免与同时在跑的边淡出动画撞车导致 RuntimeError
            self._rebuild_tree_edges()

        for edge in related_edges:
            anim = play_edge_delete_animation(edge, lambda e=edge: _on_edge_done(e))
            self._active_delete_anims.append(anim)
            anim.finished.connect(
                lambda a=anim: (
                    self._active_delete_anims.remove(a)
                    if a in self._active_delete_anims
                    else None
                )
            )
        node_anim = play_node_delete_animation(node_item, _on_node_done)
        self._active_delete_anims.append(node_anim)
        node_anim.finished.connect(
            lambda a=node_anim: (
                self._active_delete_anims.remove(a)
                if a in self._active_delete_anims
                else None
            )
        )

        # ⭐ 切割后被脱离的后代变成新的根 → 刷新根节点标记（金色 halo）
        self._refresh_root_flags()

    def _start_cutting(self, scene_pos: QPointF) -> None:
        """⭐ 启动切割：右键在空白处按下时进入划线状态。"""
        self._is_cutting = True
        self._cut_start = scene_pos
        self._cut_warning_last_pos = scene_pos  # ⭐ 重置末次位置
        self._cut_warning_nodes.clear()
        self._cut_warning_edges.clear()

        # 创建激光线（红色半透明，叠在节点之上）
        line = QGraphicsLineItem(QLineF(scene_pos, scene_pos))
        pen = QPen(QColor("#ff3b30"), 3)
        pen.setCosmetic(True)  # 不受缩放影响（视觉上始终 3px）
        pen.setCapStyle(Qt.RoundCap)
        line.setPen(pen)
        line.setZValue(999)  # 顶层
        line.setOpacity(0.85)
        self._scene.addItem(line)
        self._cut_line_item = line

    def _update_cutting(self, scene_pos: QPointF) -> None:
        """⭐ 切割中：实时更新激光线 + 计算被穿过的节点/边（高亮红色）。"""
        if self._cut_line_item is None or self._cut_start is None:
            return
        self._cut_line_item.setLine(QLineF(self._cut_start, scene_pos))
        self._cut_warning_last_pos = scene_pos  # ⭐ 记录末次位置（松开时算总长）

        # 计算当前线段穿过的所有节点 + 边
        line = QLineF(self._cut_start, scene_pos)
        new_warn_nodes: set[str] = set()
        new_warn_edges: set[int] = set()

        # 节点：膨胀后的矩形（scene 坐标）是否与线段相交
        # ⭐ 6px 容差：激光线擦过节点边缘就算"切到"
        for nid, node in self._node_items.items():
            rect = node.sceneBoundingRect().adjusted(
                -CUT_NODE_HIT_INFLATE,
                -CUT_NODE_HIT_INFLATE,
                CUT_NODE_HIT_INFLATE,
                CUT_NODE_HIT_INFLATE,
            )
            if _line_intersects_rect(line, rect):
                new_warn_nodes.add(nid)

        # 边：起点-终点线段与切割线段相交，或距离 ≤ 容差
        for edge in self._edge_items:
            try:
                if not edge.source or not edge.target:
                    continue
                p1 = edge.source.scenePos() + QPointF(
                    edge.source.width / 2, edge.source.height / 2
                )
                p2 = edge.target.scenePos() + QPointF(
                    edge.target.width / 2, edge.target.height / 2
                )
                edge_line = QLineF(p1, p2)
                # ⭐ 真相交 OR 距离 ≤ 容差
                if (
                    _segments_intersect(line, edge_line)
                    or _segment_distance(line, edge_line) <= CUT_EDGE_HIT_TOLERANCE
                ):
                    new_warn_edges.add(id(edge))
            except (RuntimeError, AttributeError):
                # ⭐ 边端点 NodeItem 已 C++ 销毁 → 跳过
                continue

        # 差异更新：去掉旧的高亮，加新的高亮
        for nid in self._cut_warning_nodes - new_warn_nodes:
            n = self._node_items.get(nid)
            if n:
                n.set_warning(False)
        for nid in new_warn_nodes - self._cut_warning_nodes:
            n = self._node_items.get(nid)
            if n:
                n.set_warning(True)

        for eid in self._cut_warning_edges - new_warn_edges:
            self._set_edge_warning_by_id(eid, False)
        for eid in new_warn_edges - self._cut_warning_edges:
            self._set_edge_warning_by_id(eid, True)

        self._cut_warning_nodes = new_warn_nodes
        self._cut_warning_edges = new_warn_edges

    def _set_edge_warning_by_id(self, eid: int, on: bool) -> None:
        """通过 id(edge) 找到对应的 EdgeItem 切换 warning。"""
        for e in self._edge_items:
            if id(e) == eid:
                e.set_warning(on)
                return

    def _finish_cutting(self) -> None:
        """⭐ 切割结束：清理激光线 + 发出 cut_confirmed 信号。"""
        self._is_cutting = False
        # 移除激光线
        if self._cut_line_item is not None:
            try:
                self._scene.removeItem(self._cut_line_item)
            except RuntimeError:
                pass
            self._cut_line_item = None

        # ⭐ 最小长度检查：太短的线段视为抖动误触，不切
        if self._cut_start is None:
            return
        last_pos = self._cut_warning_last_pos or self._cut_start
        if _line_length(self._cut_start, last_pos) < CUT_MIN_LENGTH and not (
            self._cut_warning_nodes or self._cut_warning_edges
        ):
            # 啥也没碰到 + 线太短 → 直接放弃，不发信号
            self._cut_start = None
            return

        # 局部保存起点和末端（后面会被清掉，特效播放要用）
        start_pos = QPointF(self._cut_start)
        end_pos = QPointF(last_pos)
        # 收集碰撞点（用于火花特效）
        collide_pts = [
            self._node_items[nid].sceneBoundingRect().center()
            for nid in self._cut_warning_nodes
            if nid in self._node_items
        ]

        # 收集要删除的节点 + 边（取快照，因为信号处理中 view 会变化）
        nodes_to_delete = [
            self._node_items[nid]
            for nid in self._cut_warning_nodes
            if nid in self._node_items
        ]
        edges_to_delete = []
        for e in self._edge_items:
            if id(e) in self._cut_warning_edges:
                edges_to_delete.append(e)

        # 清除所有高亮（让 view 立刻干净）
        for nid in self._cut_warning_nodes:
            n = self._node_items.get(nid)
            if n:
                n.set_warning(False)
        for e in self._edge_items:
            if id(e) in self._cut_warning_edges:
                e.set_warning(False)
        self._cut_warning_nodes.clear()
        self._cut_warning_edges.clear()
        self._cut_start = None

        if not nodes_to_delete and not edges_to_delete:
            return

        # ⭐ 播放切割松开特效：切线残影 + 每个碰撞节点的火花闪光
        from src.ui.delete_effect import play_cut_release_effects

        anims = play_cut_release_effects(
            self._scene,
            start_pos,
            end_pos,
            collide_points=collide_pts if collide_pts else None,
        )
        self._active_delete_anims.extend(anims)

        # 通知主窗口处理（带 descendant detach 语义）
        self.cut_confirmed.emit(nodes_to_delete, edges_to_delete)

    def cancel_cutting(self) -> None:
        """⭐ 外部强行中断切割（例如切到其他窗口）。"""
        if not self._is_cutting:
            return
        if self._cut_line_item is not None:
            try:
                self._scene.removeItem(self._cut_line_item)
            except RuntimeError:
                pass
            self._cut_line_item = None
        for nid in list(self._cut_warning_nodes):
            n = self._node_items.get(nid)
            if n:
                n.set_warning(False)
        for e in self._edge_items:
            if id(e) in self._cut_warning_edges:
                e.set_warning(False)
        self._cut_warning_nodes.clear()
        self._cut_warning_edges.clear()
        self._cut_start = None
        self._is_cutting = False

    # ==================== ⭐ 节点连接点拖线（任意两节点关系） ====================

    def _on_port_drag_started(self, node_item: NodeItem, port_index: int) -> None:
        """⭐ 节点上的连接点被按下：进入拖线模式。"""
        self._is_connecting = True
        self._connect_source_node = node_item
        # 用节点的连接点 scene 坐标作为起点
        start = node_item.port_scene_pos(port_index)
        line = QGraphicsLineItem(QLineF(start, start))
        pen = QPen(QColor("#4A90E2"), 2)
        pen.setCosmetic(True)
        pen.setDashPattern([4, 3])
        pen.setCapStyle(Qt.RoundCap)
        line.setPen(pen)
        line.setZValue(998)
        line.setOpacity(0.85)
        self._scene.addItem(line)
        self._connect_line_item = line

    def _on_nebula_label_toggle(self, node_item: NodeItem) -> None:
        """⭐⭐ nebula 模式：点击节点切换持久浮窗 label。

        - 只在 nebula 模式生效（EDIT 模式不响应）
        - 同一时刻只允许一个节点的 label 显示（避免画面太杂）
        - 点击同一个节点 → 关闭；点击另一个节点 → 切换
        """
        if not self._nebula_mode:
            return
        try:
            was_visible = node_item._nebula_label_visible
            # 关闭所有节点的 label（互斥：同一时刻只一个）
            for n in self._node_items.values():
                try:
                    if n._nebula_label_visible:
                        n.set_nebula_label_visible(False)
                except RuntimeError:
                    pass
            # 如果之前不是显示状态 → 打开新节点的 label
            if not was_visible:
                node_item.set_nebula_label_visible(True)
        except RuntimeError:
            pass

    def _update_connecting(self, view_pos) -> None:
        """⭐ 拖线过程中更新预览线终点。"""
        if self._connect_line_item is None or self._connect_source_node is None:
            return
        scene_pos = self.mapToScene(view_pos)
        start = self._connect_line_item.line().p1()
        self._connect_line_item.setLine(QLineF(start, scene_pos))

    def _finish_connecting(self, view_pos) -> None:
        """⭐ 拖线结束：检测目标 → 触发 node_connect_requested。"""
        self._is_connecting = False
        # 移除预览线
        if self._connect_line_item is not None:
            try:
                self._scene.removeItem(self._connect_line_item)
            except RuntimeError:
                pass
            self._connect_line_item = None

        if self._connect_source_node is None:
            return
        scene_pos = self.mapToScene(view_pos)
        item_at = self._scene.itemAt(scene_pos, self.transform())
        # 只接受落在 NodeItem 上的释放
        target_node = item_at if isinstance(item_at, NodeItem) else None
        # 兜底：如果释放点在另一个节点的连接点上但 itemAt 没拿到（hitTest 边界），尝试最近节点
        if target_node is None:
            target_node = self._nearest_node_at(scene_pos)

        source_node = self._connect_source_node
        self._connect_source_node = None
        if target_node is None or target_node is source_node:
            return  # 拖回自己 / 拖到空白 → 取消
        self.node_connect_requested.emit(source_node.node_id, target_node.node_id)

    def _nearest_node_at(self, scene_pos: QPointF, max_dist: float = 30.0):
        """⭐ 当 itemAt 没命中时，找离 scene_pos 最近的节点（兜底）。"""
        best: NodeItem | None = None
        best_d2 = max_dist * max_dist
        for n in self._node_items.values():
            c = n.center()  # scene 坐标
            dx = c.x() - scene_pos.x()
            dy = c.y() - scene_pos.y()
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best = n
                best_d2 = d2
        return best

    def cancel_connecting(self) -> None:
        """⭐ 外部中断拖线（备用）。"""
        if self._connect_line_item is not None:
            try:
                self._scene.removeItem(self._connect_line_item)
            except RuntimeError:
                pass
            self._connect_line_item = None
        self._connect_source_node = None
        self._is_connecting = False

    def add_edge_between(self, source_id: str, target_id: str) -> bool:
        """⭐ 创建两节点间的附加边（DB + graph + view 三层同步）。

        返回 True 成功；False 表示自环/重复边/节点不存在。
        """
        if source_id == target_id:
            return False
        if source_id not in self._node_items or target_id not in self._node_items:
            return False
        # 去重：同一对节点（不论方向）已有边则拒绝
        for e in self._edge_items:
            if (e.source.node_id == source_id and e.target.node_id == target_id) or (
                e.source.node_id == target_id and e.target.node_id == source_id
            ):
                return False
        # 创建（DB 优先拿 id，再插 view）
        edge_id = None
        # 由 main_window 在调用前/后落库；此处负责 view + graph 同步
        # 但为保证闭环，这里也允许 view 自己落库（main_window 决定策略）
        return True

    def _add_edge_view(
        self, source_id: str, target_id: str, edge_id: int | None = None
    ) -> EdgeItem | None:
        """⭐ 内部：在 view 上创建一条 EdgeItem + 注册到 graph（不落库）。

        Returns:
            创建的 EdgeItem；若任一端点不在场景中则返回 None（防御：脏数据）。
        """
        source = self._node_items.get(source_id)
        target = self._node_items.get(target_id)
        if source is None or target is None:
            logger.warning(
                f"_add_edge_view 跳过：端点缺失 {source_id[:8]} -> {target_id[:8]}"
            )
            return None
        edge = EdgeItem(source, target)
        if edge_id is not None:
            edge.db_id = edge_id  # 用于后续删除同步
        self._scene.addItem(edge)
        self._edge_items.append(edge)
        self._node_to_edges.setdefault(source_id, []).append(edge)
        self._node_to_edges.setdefault(target_id, []).append(edge)
        return edge

    def remove_edge_item(self, edge_item: EdgeItem) -> None:
        """⭐ 删除一条边（不落库，由 main_window 决定）。"""
        self._safe_remove_item(edge_item)
        try:
            self._edge_items.remove(edge_item)
        except ValueError:
            pass
        # 只清涉及的两个 nid 的索引（边端点是 source/target，不需要遍历全表）
        try:
            s_id = edge_item.source.node_id
            t_id = edge_item.target.node_id
            for nid in (s_id, t_id):
                lst = self._node_to_edges.get(nid)
                if lst:
                    self._node_to_edges[nid] = [e for e in lst if e is not edge_item]
        except (RuntimeError, AttributeError):
            pass

    # ==================== 信号回调 ====================

    def _on_node_edit_requested(self, node_item: NodeItem) -> None:
        """节点双击请求编辑。"""
        self.node_text_edit_requested.emit(node_item)

    def _on_node_add_child(self, node_item: NodeItem) -> None:
        """⭐ 节点右键请求添加子节点。"""
        self.node_add_child_requested.emit(node_item)

    def _on_node_add_image(self, node_item: NodeItem) -> None:
        """⭐ 节点右键请求添加图片。"""
        self.node_add_image_requested.emit(node_item)

    def _on_node_delete(self, node_item: NodeItem) -> None:
        """⭐ 节点右键请求删除。"""
        self.node_delete_requested.emit(node_item)

    def _on_node_color_change(self, node_item: NodeItem, hex_color: str) -> None:
        """⭐ 节点右键请求改颜色（弹完 QColorDialog 回调到这里）。"""
        self.node_color_change_requested.emit(node_item, hex_color)

    def _on_node_remove_image(self, node_item: NodeItem) -> None:
        """⭐ 节点右键请求删除图片。"""
        self.node_remove_image_requested.emit(node_item)

    # ==================== 工具 ====================

    def fit_to_content(self, padding: int = 60) -> None:
        """缩放到适合内容。"""
        # ⭐ fitInView 会直接改 transform，必须停掉缓动定时器，否则它会继续把视图拉回旧 target
        if self._zoom_anim_timer.isActive():
            self._zoom_anim_timer.stop()
        if not self._node_items:
            return
        rect = self._scene.itemsBoundingRect().adjusted(
            -padding, -padding, padding, padding
        )
        self.fitInView(rect, Qt.KeepAspectRatio)
        # ⭐ fit 后把 target 同步到 current，避免下次滚轮从错误的目标开始 lerp
        self._target_scale = self.transform().m11()

    def fit_to_content_for_browse(self, padding: int = 40) -> None:
        """⭐⭐ BROWSE 模式专属 fit：所有节点全部框住 + 居中 + 尽量大。

        用户反馈 2026-09-13：进入导图应能直接浏览整个图，不需要手动滚轮找节点。
        思路：直接复用 ``fit_to_content`` 的实现（itemsBoundingRect + fitInView），
        只是 padding 偏小一点（BROWSE 全屏沉浸，希望节点尽量占满视口）。
        """
        self.fit_to_content(padding=padding)

    def apply_browse_starfield_layout(self) -> None:
        """⭐⭐ BROWSE 模式「星图坐标」临时布局（2026-09-13 重写）。

        设计目标（重写 v2）：
        - 每张导图进入 BROWSE 时，根节点固定在 (0, 0)
        - 子节点沿**根节点的"辐射方向"**均匀分布在一个圆周上 → 行星轨道
        - 第 2 层子节点在父节点的"外侧"扇区中再向外推 → 链式辐射
        - 不会重叠：每层节点之间的角度 = 360 / 子节点数（保证均匀铺开）
        - **不动数据库**（只 setPos 到临时位置）

        关键修复（v2）：
        - v1 算法把 angle_start/angle_end 错传成同一个值 → 子节点重叠
        - v2 显式传「扇区角度区间」(0, 360) / (扇区左, 扇区右)
        - v2 计算节点"占位角度"时考虑节点宽高 + 间距 → 不重叠
        """
        import math

        if not self._node_items:
            return

        # ⭐ 节点占位大小（和 NodeItem 实际尺寸一致）
        NODE_W = NODE_DEFAULT_WIDTH  # 180
        NODE_H = NODE_DEFAULT_HEIGHT  # 80
        GAP = 40.0  # 节点间最小间距
        R1 = 360.0  # 第 1 层距根
        R2 = 280.0  # 第 2 层距父节点

        # 1) 构建树（id → 子 id 列表 + 父 id）
        children_map: dict[str, list] = {}
        root_ids: list = []
        for nid, item in self._node_items.items():
            pid = item.parent_id()
            if pid is None or pid not in self._node_items:
                root_ids.append(nid)
            else:
                children_map.setdefault(pid, []).append(nid)

        # ⭐⭐ 数据修复兜底（2026-09-13）：导入/旧数据可能让多个节点 parent_id=None
        # 取「子节点数最多」的当主根，其余孤立 root 临时挂到主根下当第 1 层子节点
        # （不动数据库，只在 BROWSE 展示层临时改 parent_id）
        if len(root_ids) > 1:
            # 按"已挂的子节点数 + 是否带子节点"选主根
            def score(rid: str) -> int:
                return len(children_map.get(rid, []))

            main_root_id = max(root_ids, key=score)
            # 把其它孤立 root 当成 main_root 的临时第 1 层子节点
            extra = [r for r in root_ids if r != main_root_id]
            children_map.setdefault(main_root_id, []).extend(extra)
            # ⭐ 关键：临时改 parent_id，触发布局算法走"非根"路径
            for r in extra:
                self._node_items[r].set_parent_id(main_root_id)
            root_ids = [main_root_id]

        def node_angle_span(n: int) -> float:
            """一个节点在半径 R 的圆周上占的角度（弧度）。

            ≈ (节点宽度 + GAP) / R，让兄弟之间不重叠。
            """
            if n <= 1:
                return 2 * math.pi
            arc = (NODE_W + GAP) / R1
            return min(arc, 2 * math.pi / n)

        def layout_subtree(
            node_id: str, cx: float, cy: float, parent_angle: float
        ) -> None:
            """在父节点 (cx, cy)、方向 parent_angle 上，向外辐射子树。

            - 第 1 层：父节点是根 → 子节点均匀分布在 0..2π 上（每个子节点一个角度区间）
            - 第 2 层：父节点是第 1 层子节点 → 子节点都在父节点外侧扇区
            """
            kids = children_map.get(node_id, [])
            if not kids:
                return
            n = len(kids)
            # ⭐ 决定每个子节点的"外侧方向"
            if node_id in root_ids or parent_angle is None:
                # 第 1 层：在根四周均匀分布
                base_angles = [2 * math.pi * (i + 0.5) / n for i in range(n)]
            else:
                # 第 2+ 层：所有子节点都朝向父节点的"外侧"方向（小扇区展开）
                spread = 2 * math.pi / max(n, 4)  # 扇区宽
                if n == 1:
                    base_angles = [parent_angle]
                else:
                    base_angles = [
                        parent_angle - spread / 2 + spread * i / (n - 1)
                        for i in range(n)
                    ]

            # 第 1 层用 R1，第 2+ 层用 R2
            R = R1 if (node_id in root_ids or parent_angle is None) else R2

            for ang, kid in zip(base_angles, kids):
                kx = cx + R * math.cos(ang)
                ky = cy + R * math.sin(ang)
                self._node_items[kid].setPos(kx, ky)
                # ⭐ 递归：把当前节点的位置 + 当前方向往下传
                layout_subtree(kid, kx, ky, ang)

        # ⭐ 从根节点开始（只处理第一个根，多根退化）
        if not root_ids:
            return
        root_id = root_ids[0]
        root_item = self._node_items[root_id]
        root_item.setPos(0.0, 0.0)

        kids = children_map.get(root_id, [])
        n = len(kids)
        if n == 0:
            return

        # ⭐⭐ 第 1 层：均分 0..2π（每个子节点一个方向）
        first_layer_angles = [2 * math.pi * (i + 0.5) / n for i in range(n)]
        for ang, kid in zip(first_layer_angles, kids):
            kx = R1 * math.cos(ang)
            ky = R1 * math.sin(ang)
            self._node_items[kid].setPos(kx, ky)
            layout_subtree(kid, kx, ky, ang)

        # 多根时把其余根摆在一行（兜底，正常 1 个根）
        if len(root_ids) > 1:
            spacing_x = R1 * 2.5
            for i, rid in enumerate(root_ids[1:], start=1):
                self._node_items[rid].setPos(i * spacing_x, 0.0)
                kids2 = children_map.get(rid, [])
                for ang, kid in zip(
                    [
                        2 * math.pi * (j + 0.5) / max(len(kids2), 1)
                        for j in range(len(kids2))
                    ],
                    kids2,
                ):
                    kx = i * spacing_x + R1 * math.cos(ang)
                    ky = R1 * math.sin(ang)
                    self._node_items[kid].setPos(kx, ky)
                    layout_subtree(kid, kx, ky, ang)

        # ⭐ 通知所有边（节点位置变了，边要跟着重画）
        for nid, item in self._node_items.items():
            if item._view_callback:
                item._view_callback(item)
