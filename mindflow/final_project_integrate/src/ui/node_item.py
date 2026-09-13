"""自定义思维导图节点（QGraphicsItem，⭐ 星空 / 星球风格）。

特性：
- 星球视觉（深色填充 + 青色光晕 + 顶部高光）
- 选中态：青色脉冲光晕 + 高亮描边
- 根节点：金黄色光晕（更醒目，标识中心）
- 切割高亮：被划线穿过时变红
- 拖拽、选中、双击编辑、右键菜单、附件徽章、连接点
- 多附件：📷N / 📷 / 📄N
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from src.config import (
    NODE_DEFAULT_COLOR,
    NODE_DEFAULT_HEIGHT,
    NODE_DEFAULT_WIDTH,
)
from src.ui.theme import (
    COLOR_PRIMARY,
    FONT_FAMILY,
    NODE_SELECT_OVERLAY,
)

# 根节点的金色 halo
ROOT_HALO_COLOR = "#fcd34d"  # amber-300
ROOT_HALO_GLOW = "#f59e0b"  # amber-500


class NodeItem(QGraphicsItem):
    """⭐ 思维导图节点（星球风格）。"""

    # 自定义信号（Qt 信号不能在 QGraphicsItem 子类中直接定义，要用元类或父类）
    # 这里我们把信号放外面，通过回调实现
    text_edit_requested = None  # type: ignore[assignment]
    delete_requested = None
    add_child_requested = None  # ⭐ 右键添加子节点
    add_image_requested = None  # ⭐ 右键添加图片
    remove_image_requested = None  # ⭐ 右键删除图片
    color_change_requested = None  # ⭐ 右键改颜色
    port_drag_started = None  # ⭐ 连接点拖拽开始（NodeItem, port_index）
    nebula_label_toggle_requested = (
        None  # ⭐⭐ nebula 模式：点击节点切换浮窗 label（view 注册）
    )

    # ⭐ 4 个连接点位置（item 局部坐标）：top / right / bottom / left
    PORT_RADIUS = 6

    # ⭐ halo 描边 padding：halo 半径 = 节点宽 + 2 * HALO_PAD
    HALO_PAD = 8

    def __init__(
        self,
        node_id: str,
        text: str = "新节点",
        color: str = NODE_DEFAULT_COLOR,
        x: float = 0.0,
        y: float = 0.0,
        width: float = NODE_DEFAULT_WIDTH,
        height: float = NODE_DEFAULT_HEIGHT,
        parent_id: str | None = None,
        image_path: str | None = None,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.text = text
        self.color = QColor(color)
        self.width = width
        self.height = height
        self._parent_id: str | None = parent_id
        self._image_path: str | None = image_path
        # ⭐ 多附件计数（由 main_window._refresh_node_badge 调用）
        self._attachment_count: int = 0

        # 标志位
        self._dragging = False
        self._press_pos: QPointF | None = None
        self._view_callback: callable | None = None
        # ⭐ 切割高亮标志（被划线穿过时变红）
        self._warning: bool = False
        # ⭐ hover 标志（鼠标悬停但未选中时显示微高亮）
        self._hovered: bool = False
        # ⭐ 根节点标志（由 mindmap_view 在 _rebuild_graph 时设 True/False）
        self._is_root: bool = False
        # ⭐ Focus mode 暗化标志（Browse 模式下选中某节点时，非邻居节点 = True → opacity 0.3）
        self._dimmed: bool = False
        # ⭐ 星云模式（galaxy-view 风格）：节点变发光圆点，无文字，hover 显示 tooltip
        self._nebula_mode: bool = False
        # ⭐ 子树节点数（由 mindmap_view 计算后注入；用于 nebula 模式按度数缩放圆点大小）
        # 默认 1 = 叶子节点；根节点 = 全图节点数
        self._subtree_size: int = 1
        # ⭐⭐ nebula 模式持久 label 状态：被点击后浮窗显示文字，直到下次点击/拖动消失
        self._nebula_label_visible: bool = False
        # ⭐ 选中脉冲相位（0..2π），由 _pulse_timer 推进
        self._pulse_t: float = 0.0

        # 交互标志
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # 设置位置
        self.setPos(x, y)

        # Z 值（选中节点在最上层）
        self.setZValue(1)

        # ⭐ 脉冲定时器：仅选中时启动，省 CPU
        # PySide6 6.x：QTimer 不接受 QGraphicsItem 作 parent，故用 None
        self._pulse_timer = QTimer()
        self._pulse_timer.setInterval(60)  # 16fps 对脉冲足够
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

    # ==================== Qt 必须实现的接口 ====================

    def boundingRect(self) -> QRectF:
        """节点边界矩形（含 halo padding + 图片图标区域 + nebula 浮窗 label）。"""
        pad = self.HALO_PAD + 4
        # ⭐⭐ nebula 模式需要为浮窗 label 预留更大区域（防止 label 被裁剪）
        if self._nebula_mode:
            # label 在节点下方，最大预估 200×40
            label_extra_bottom = 50
            label_extra_sides = 60
            return QRectF(
                -label_extra_sides,
                -pad,
                self.width + label_extra_sides * 2,
                self.height + pad + label_extra_bottom,
            )
        return QRectF(-pad, -pad, self.width + pad * 2, self.height + pad * 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """⭐ 绘制星球节点。"""
        painter.setRenderHint(QPainter.Antialiasing, True)

        # ⭐⭐ 星云模式（nebula）：画发光圆点 → 立刻返回，跳过 body/halo/text/port/badge
        # 借鉴 galaxy-view：节点 = luminous dot，文字靠 hover tooltip 展示
        if self._nebula_mode:
            self._paint_nebula_dot(painter)
            return

        show_overlay = self.isSelected() and not self._dragging
        # 决定 halo 主色：根节点金色 > 选中青色 > hover 青色 > 默认青
        if self._is_root:
            halo_rgb = ROOT_HALO_COLOR
        elif show_overlay:
            halo_rgb = NODE_SELECT_OVERLAY
        else:
            halo_rgb = COLOR_PRIMARY

        # ===========================================================
        # 1) 外层 halo（"星球大气层"）
        # ===========================================================
        # halo 由两层渐变圆角矩形组成：
        #   外层：超大半透明模糊感
        #   内层：略深稍亮，紧贴节点
        halo_outer = QColor(halo_rgb)
        halo_inner = QColor(halo_rgb)

        if show_overlay and self._is_root:
            # 根节点被选中：金色脉冲
            pulse = 0.55 + 0.35 * _sin01(self._pulse_t * 1.6)
            halo_outer.setAlphaF(0.18 * pulse)
            halo_inner.setAlphaF(0.45 * pulse)
        elif show_overlay:
            # 普通选中：青色脉冲
            pulse = 0.55 + 0.40 * _sin01(self._pulse_t * 1.4)
            halo_outer.setAlphaF(0.20 * pulse)
            halo_inner.setAlphaF(0.50 * pulse)
        elif self._is_root:
            # 根节点未选中：金色常驻微光
            halo_outer.setAlphaF(0.20)
            halo_inner.setAlphaF(0.45)
        elif self._hovered:
            # hover：淡青微光
            halo_outer.setAlphaF(0.12)
            halo_inner.setAlphaF(0.30)
        else:
            # 默认：很淡的光晕（暗示"这是一颗星球"，但不抢戏）
            halo_outer.setAlphaF(0.08)
            halo_inner.setAlphaF(0.18)

        # 外层 halo（更大更柔）
        painter.setBrush(QBrush(halo_outer))
        painter.setPen(Qt.NoPen)
        outer_pad = self.HALO_PAD + 6
        painter.drawRoundedRect(
            QRectF(
                -outer_pad,
                -outer_pad,
                self.width + outer_pad * 2,
                self.height + outer_pad * 2,
            ),
            18,
            18,
        )
        # 内层 halo（紧贴节点边）
        painter.setBrush(QBrush(halo_inner))
        painter.drawRoundedRect(
            QRectF(
                -self.HALO_PAD,
                -self.HALO_PAD,
                self.width + self.HALO_PAD * 2,
                self.height + self.HALO_PAD * 2,
            ),
            14,
            14,
        )

        # ===========================================================
        # 2) 节点主体（深色填充 + 自有颜色描边）
        # ===========================================================
        # 切割高亮：红色覆盖
        if self._warning:
            body_fill = QColor(60, 12, 12)  # 极深红
            stroke = QColor("#ff3b30")
            stroke_w = 3
        elif self._is_root:
            # 根节点：暖深色 + 金色描边
            body_fill = QColor(48, 32, 8)  # 深棕暖色
            stroke = QColor(ROOT_HALO_COLOR)
            stroke_w = 2
        else:
            # 普通：保留自有色相，亮度压到 ~18%，让白字可读
            body_fill = _darken_keep_hue(self.color, target_l=18)
            stroke = QColor(self.color)
            stroke_w = 2

        painter.setBrush(QBrush(body_fill))
        pen = QPen(stroke, stroke_w)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawRoundedRect(
            QRectF(0, 0, self.width, self.height),
            10,
            10,
        )

        # ===========================================================
        # 3) 顶部高光（"星球被太阳照亮的那一面"）— 削弱让文字更清晰
        # ===========================================================
        # 之前 alpha 38 偏亮 + halo alpha 叠加 → 文字边缘发糊
        # 现在 alpha 16 + 中段提早归零 → 文字区无干扰
        grad = QLinearGradient(0, 0, 0, self.height)
        grad.setColorAt(0.0, QColor(255, 255, 255, 16))
        grad.setColorAt(0.40, QColor(255, 255, 255, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 18))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(0, 0, self.width, self.height),
            10,
            10,
        )

        # ===========================================================
        # 4) 选中高亮描边（在 body 上叠一圈亮色，告诉用户"点中了"）
        # ===========================================================
        if show_overlay:
            highlight = (
                QColor(NODE_SELECT_OVERLAY)
                if not self._is_root
                else QColor(ROOT_HALO_GLOW)
            )
            highlight.setAlphaF(0.95)
            pen2 = QPen(highlight, 3)
            pen2.setJoinStyle(Qt.RoundJoin)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(pen2)
            painter.drawRoundedRect(
                QRectF(0, 0, self.width, self.height),
                10,
                10,
            )

        # ===========================================================
        # 5) 文字（白色加粗，居中）— 微阴影让字"压"在 body 上
        # ===========================================================
        if self.has_image():
            text_rect = QRectF(28, 0, self.width - 36, self.height)
        else:
            text_rect = QRectF(8, 0, self.width - 16, self.height)
        font = QFont(FONT_FAMILY, 12, QFont.Bold)
        # 阴影：偏下 + 偏右 + 半透明黑 → 让白字"浮"在 body 上
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(text_rect.adjusted(0, 1, 0, 1), Qt.AlignCenter, self.text)
        # 正式白字
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(text_rect, Qt.AlignCenter, self.text)

        # ===========================================================
        # 6) 附件徽章（左上角）
        # ===========================================================
        if self.has_image():
            icon_size = 22
            icon_rect = QRectF(4, 4, icon_size, icon_size)
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.setPen(QPen(QColor(COLOR_PRIMARY), 1))
            painter.drawEllipse(icon_rect)
            painter.setPen(QColor(COLOR_PRIMARY))
            emoji_font = QFont("Segoe UI Emoji", 9)
            painter.setFont(emoji_font)
            if self._attachment_count > 1:
                badge = f"📷{self._attachment_count}"
                painter.drawText(icon_rect, Qt.AlignCenter, badge)
            else:
                painter.drawText(icon_rect, Qt.AlignCenter, "📷")

        # ===========================================================
        # 7) 连接点（仅选中时显示）
        # ===========================================================
        if show_overlay:
            painter.setBrush(QBrush(QColor(COLOR_PRIMARY)))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            r = self.PORT_RADIUS
            for cx, cy in self._port_centers():
                painter.drawEllipse(QPointF(cx, cy), r, r)

    # ==================== 脉冲定时器 ====================

    def _on_pulse_tick(self) -> None:
        """⭐ 选中时由 QTimer 推进 _pulse_t，触发 paint 重算 halo。"""
        self._pulse_t += 0.18
        self.update()

    def _paint_nebula_dot(self, painter: QPainter) -> None:
        """⭐ 星云模式圆点绘制（取代 body + halo + text + port + badge）。

        借鉴 galaxy-view 的"colored by your graph groups"：
        - 节点颜色 = self.color（用户右键设置或默认 cyan）→ 不同分组立即可辨
        - 节点大小 = base × (1 + 0.4 × √subtree_size)→ 重要节点显著大
        - 选中：白色脉冲（被选中的"恒星"）
        - 根节点：金黄 + 最大（中心天体）
        - 被点击后：浮窗显示文字（_paint_nebula_label）
        """
        cx = self.width / 2
        cy = self.height / 2

        # ⭐ 基础半径：按子树节点数缩放（galaxy-view 公式）
        base_r = self.get_nebula_radius()

        # ⭐⭐ 节点自身颜色（用户设置或默认）
        # 如果用户没设置（color 无效），用 cyan 兜底
        node_color = self.color if self.color.isValid() else QColor(COLOR_PRIMARY)

        # ⭐ 决定颜色 + 大小
        show_overlay = self.isSelected() and not self._dragging
        if show_overlay:
            dot_color = QColor("#FFFFFF")  # 选中 → 白色
            glow_color = QColor(NODE_SELECT_OVERLAY)
            r = base_r * 1.4
            pulse = 0.85 + 0.20 * _sin01(self._pulse_t * 1.4)
            r = r * pulse
        elif self._is_root:
            # ⭐ 根节点 = 金黄（不被节点颜色覆盖，"中心天体"语义稳定）
            dot_color = QColor(ROOT_HALO_COLOR)
            glow_color = QColor(ROOT_HALO_GLOW)
            r = base_r * 1.3
        elif self._nebula_label_visible:
            # ⭐⭐ 被点击展开 label 的节点：稍亮 + 更大（强调"我被选中"）
            dot_color = node_color.lighter(120)
            glow_color = QColor(node_color)
            r = base_r * 1.25
        elif self._hovered:
            dot_color = node_color.lighter(115)
            glow_color = QColor(node_color)
            r = base_r * 1.1
        else:
            # ⭐⭐ 默认：节点自身颜色（galaxy-view "colored by your graph groups"）
            dot_color = QColor(node_color)
            glow_color = QColor(node_color)
            r = base_r

        # ⭐ 外圈柔光晕（"恒星辐射"）
        glow_r = r * self.NEBULA_DOT_GLOW_RATIO
        glow_color.setAlphaF(self.NEBULA_DOT_GLOW_ALPHA)
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ⭐ 圆点本体
        dot_color.setAlphaF(self.NEBULA_DOT_BODY_ALPHA)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # ⭐⭐ 浮窗 label（被点击后持续显示；不依赖 tooltip，移动鼠标不消失）
        if self._nebula_label_visible:
            self._paint_nebula_label(painter, r, cx, cy)

    def _paint_nebula_label(
        self,
        painter: QPainter,
        dot_radius: float,
        cx: float,
        cy: float,
    ) -> None:
        """⭐⭐ nebula 模式点击浮窗：节点下方画"带圆角背景的标签"。

        借鉴 galaxy-view 的"selected note shows name persistently"：
        用户探索时可以随便移动鼠标，文字始终显示在节点旁边。
        """
        text = self.text
        if not text:
            return

        # ⭐ 字体设置（项目统一字体 + 略大以提升可读性）
        font = QFont(FONT_FAMILY, 10)
        font.setBold(False)
        painter.setFont(font)

        # ⭐ 测量文字宽度
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()

        # ⭐ label 框：圆角矩形 + padding
        pad_x = 8
        pad_y = 4
        box_w = text_w + pad_x * 2
        box_h = text_h + pad_y * 2
        # 位置：节点下方 8px 间隔，水平居中
        box_x = cx - box_w / 2
        box_y = cy + dot_radius + 8

        # ⭐ 背景：深色 + cyan 边（跟 tooltip 风格统一，但 alpha 更低，不抢戏）
        bg_color = QColor(15, 23, 42)  # slate-900
        bg_color.setAlphaF(0.85)
        border_color = QColor(COLOR_PRIMARY)
        border_color.setAlphaF(0.7)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.0))
        painter.drawRoundedRect(
            QRectF(box_x, box_y, box_w, box_h), 4.0, 4.0, Qt.RelativeSize
        )

        # ⭐ 文字：白色
        text_color = QColor("#ffffff")
        painter.setPen(QPen(text_color, 1.0))
        # 文字在背景框内居中
        painter.drawText(
            QRectF(box_x + pad_x, box_y + pad_y, text_w, text_h),
            Qt.AlignCenter,
            text,
        )

    def _start_pulse(self) -> None:
        if not self._pulse_timer.isActive():
            self._pulse_t = 0.0
            self._pulse_timer.start()

    def _stop_pulse(self) -> None:
        self._pulse_timer.stop()
        self._pulse_t = 0.0

    # ==================== 内部工具 ====================

    def _port_centers(self):
        """⭐ 返回 4 个连接点的中心坐标（item 局部）。"""
        w, h = self.width, self.height
        return [
            (w / 2, 0),  # 0: top
            (w, h / 2),  # 1: right
            (w / 2, h),  # 2: bottom
            (0, h / 2),  # 3: left
        ]

    def port_scene_pos(self, port_index: int):
        """⭐ 返回指定连接点的 scene 坐标（用于拖拽预览线起点）。"""
        cx, cy = self._port_centers()[port_index]
        return self.scenePos() + QPointF(cx, cy)

    def port_at(self, local_pos):
        """⭐ 判断 local_pos（item 局部坐标）是否在某个连接点上。

        返回 port_index (0-3)；不在任何连接点上则返回 None。
        """
        r = self.PORT_RADIUS + 3  # 命中范围略大于视觉半径
        for idx, (cx, cy) in enumerate(self._port_centers()):
            dx = local_pos.x() - cx
            dy = local_pos.y() - cy
            if dx * dx + dy * dy <= r * r:
                return idx
        return None

    # ==================== 鼠标交互 ====================

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """双击 → 请求编辑文本（EDIT 模式）；NEBULA 模式被 mousePressEvent 拦截不走到这。"""
        # ⭐⭐ nebula 模式被 mousePressEvent 提前 accept，不会触发双击
        if self._nebula_mode:
            return
        if event.button() == Qt.LeftButton:
            if NodeItem.text_edit_requested:
                NodeItem.text_edit_requested(self)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """记录按下的位置（用于区分点击和拖拽）。"""
        # ⭐⭐ nebula 模式：左键点击 → 切换浮窗 label（让用户探索时文字持续显示）
        if event.button() == Qt.LeftButton and self._nebula_mode:
            # 先通知 view 切换 label 状态（view 负责关闭其他节点的 label）
            if NodeItem.nebula_label_toggle_requested:
                NodeItem.nebula_label_toggle_requested(self)
            event.accept()
            return
        # ⭐ 连接点按下 → 进入拖线模式（不触发节点拖动）
        if event.button() == Qt.LeftButton and self.isSelected():
            port = self.port_at(event.pos())
            if port is not None:
                if NodeItem.port_drag_started:
                    NodeItem.port_drag_started(self, port)
                event.accept()
                return
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._press_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """释放时如果位置变了，发位置变化信号。"""
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            # ⭐ 恢复选中描边叠层 + 连接点（拖动期间被隐藏，松开时重画）
            self.update()
            new_pos = self.pos()
            # 通过 scene 找回调（hack 但简单）
            scene = self.scene()
            if scene and hasattr(scene, "on_node_moved"):
                scene.on_node_moved(self, new_pos.x(), new_pos.y())
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """⭐ 右键菜单（参考 project-graph：非阻塞 popup，避免阻塞事件循环导致动画卡顿）。"""
        menu = QMenu()

        edit_action = menu.addAction("✏️ 编辑文本")
        edit_action.triggered.connect(
            lambda: self._trigger(NodeItem.text_edit_requested)
        )

        menu.addSeparator()
        add_child_action = menu.addAction("➕ 添加子节点")
        add_child_action.triggered.connect(
            lambda: self._trigger(NodeItem.add_child_requested)
        )

        menu.addSeparator()
        # ⭐ 改颜色（弹 QColorDialog 调色板，选完回调 color_change_requested）
        color_action = menu.addAction("🎨 改颜色…")

        def _open_color_dialog():
            initial = (
                QColor(self.color) if self.color.isValid() else QColor(COLOR_PRIMARY)
            )
            chosen = QColorDialog.getColor(initial, None, "选择节点颜色")
            if chosen.isValid() and NodeItem.color_change_requested:
                NodeItem.color_change_requested(self, chosen.name())

        color_action.triggered.connect(_open_color_dialog)

        menu.addSeparator()
        # ⭐ 始终显示"添加资料附件"（可多选，不替换已有）
        add_attach_action = menu.addAction("🖼 添加资料附件")
        add_attach_action.triggered.connect(
            lambda: self._trigger(NodeItem.add_image_requested)
        )

        menu.addSeparator()
        delete_action = menu.addAction("🗑 删除节点")
        delete_action.triggered.connect(
            lambda: self._trigger(NodeItem.delete_requested)
        )

        # ⭐ project-graph 思路：用 popup 非阻塞弹菜单，避免阻塞事件循环
        # menu.exec 会卡死事件队列，导致后台动画回调堆积，菜单关闭后回调风暴
        # popup 异步显示 + aboutToHide 信号清理，更稳
        sp = event.screenPos()
        menu.popup(QPoint(int(sp.x()), int(sp.y())))
        menu.aboutToHide.connect(lambda m=menu: m.deleteLater())

    def _trigger(self, callback) -> None:
        """触发回调（统一处理）。"""
        if callback:
            callback(self)

    def itemChange(self, change, value):
        """节点被选中时提升 Z 值 / 移动时通知边。"""
        if change == QGraphicsItem.ItemSelectedHasChanged:
            if self.isSelected():
                self.setZValue(10)
                self._start_pulse()
            else:
                self.setZValue(1)
                self._stop_pulse()
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # ⭐ 节点位置变化时主动通知（边实时跟随）
            # 这是流畅拖动的核心——不再依赖 Qt 的隐式更新
            if self._view_callback:
                self._view_callback(self)
        return super().itemChange(change, value)

    # ==================== 工具方法 ====================

    def set_text(self, text: str) -> None:
        """修改文本并重绘。"""
        self.text = text
        self.update()

    def set_color(self, color: str) -> None:
        """修改颜色并重绘。"""
        self.color = QColor(color)
        self.update()

    def set_image_path(self, image_path: str | None) -> None:
        """⭐ 设置图片路径并重绘。"""
        self._image_path = image_path
        self.update()

    def set_attachment_count(self, count: int) -> None:
        """⭐ 设置附件计数（用于徽章显示）。"""
        self._attachment_count = max(0, int(count))
        self.update()

    def set_is_root(self, is_root: bool) -> None:
        """⭐ 由 mindmap_view 调用，标记根节点（用于金色 halo）。"""
        self._is_root = bool(is_root)
        self.update()

    def is_root(self) -> bool:
        return self._is_root

    def attachment_count(self) -> int:
        """⭐ 获取附件数。"""
        return self._attachment_count

    def has_image(self) -> bool:
        """⭐ 是否有图片（兼容旧 API）。"""
        return bool(self._image_path)

    def image_path(self) -> str | None:
        """⭐ 获取图片相对路径。"""
        return self._image_path

    def parent_id(self) -> str | None:
        """⭐ 获取父节点 ID（mindmap_view.py 调用）。"""
        return self._parent_id

    def set_parent_id(self, parent_id: str | None) -> None:
        """⭐ 设置父节点 ID。"""
        self._parent_id = parent_id

    def set_view_callback(self, callback) -> None:
        """⭐ 设置视图回调（位置变化时调用）。"""
        self._view_callback = callback

    def set_warning(self, on: bool) -> None:
        """⭐ 切割高亮：被划线穿过时变红。"""
        self._warning = bool(on)
        self.update()

    def is_warning(self) -> bool:
        return self._warning

    # ==================== hover 状态 ====================

    def hoverEnterEvent(self, event) -> None:
        """⭐ 鼠标进入节点 → 显示主色描边（视觉提示可点击/可拖）。"""
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        """⭐ 鼠标离开节点 → 取消 hover 描边。"""
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def is_hovered(self) -> bool:
        return self._hovered

    # ==================== Focus mode 暗化 ====================

    # 暗化时的目标 opacity（⭐ galaxy-view 风格：其他节点 0.3 = "沉到背景"）
    DIMMED_OPACITY = 0.3
    NORMAL_OPACITY = 1.0

    def set_dimmed(self, dimmed: bool) -> None:
        """⭐ Browse 模式选中节点时调用：把"非邻居"节点的 opacity 降到 0.3。

        用 QGraphicsItem.setOpacity 而不是逐 paint 控制，避免每次 paint 都判 flag。
        邻居 = 选中节点 + 1-hop 相邻（由 view 计算后传入）。
        """
        self._dimmed = bool(dimmed)
        self.setOpacity(self.DIMMED_OPACITY if dimmed else self.NORMAL_OPACITY)

    def is_dimmed(self) -> bool:
        return self._dimmed

    # ==================== ⭐ 星云模式（galaxy-view 风格）====================
    #
    # Browse 模式可切换：节点变成发光圆点，hover 时显示 tooltip 展示节点文字。
    # 借鉴 galaxy-view 的"luminous nodes colored by your graph groups"，
    # 沉浸式浏览——大图看不清细节，但视觉上像星图星系。

    NEBULA_DOT_RADIUS = 5.0  # 圆点基础半径（scene 坐标）
    NEBULA_DOT_GLOW_RATIO = 2.4  # 外圈光晕相对圆点的倍数
    NEBULA_DOT_GLOW_ALPHA = 0.30  # 外圈光晕透明度
    NEBULA_DOT_BODY_ALPHA = 0.95  # 圆点本体透明度
    # ⭐⭐ 借鉴 galaxy-view computeSize：base × (1 + 0.4 × √degree)
    # 子树越大 → 圆点越大；上限封顶避免巨型节点吞画面
    NEBULA_SIZE_DEGREE_FACTOR = 0.4
    NEBULA_SIZE_MIN = 3.5
    NEBULA_SIZE_MAX = 12.0

    def set_nebula_mode(self, on: bool) -> None:
        """⭐ Browse 模式切换：节点变发光圆点 + hover tooltip 显示文字。

        on=True  → nebula mode（圆点 + setToolTip(text)）
        on=False → 默认（body + halo + text）
        """
        self._nebula_mode = bool(on)
        if on:
            # ⭐ Qt 原生 tooltip：hover 时自动弹出，移开自动隐藏
            # 样式由全局 APP_QSS 的 QToolTip 规则控制（深色 + cyan 边）
            self.setToolTip(self.text)
            # 关闭 pulse timer（圆点不需要脉冲，省 CPU）
            self._stop_pulse()
        else:
            self.setToolTip("")
            # ⭐ 退出 nebula 时清掉持久浮窗 label（不然切回 mindmap 视图还有 label 残留）
            self._nebula_label_visible = False
            # 恢复选中态 pulse（如果是 selected 状态）
            if self.isSelected():
                self._start_pulse()
        # ⭐ nebula 模式下需要更新渲染（不调 update 让 view 一次性刷）
        self.prepareGeometryChange()
        # 不调 update：由 view.set_nebula_mode 遍历时统一触发 update

    def is_nebula_mode(self) -> bool:
        return self._nebula_mode

    def set_subtree_size(self, size: int) -> None:
        """⭐ mindmap_view 在重建图时调用：注入子树节点数（用于 nebula 模式按 degree 缩放）。

        借鉴 galaxy-view 的 computeSize：
        base × (1 + 0.4 × √degree)，但有 NEBULA_SIZE_MIN/MAX 封顶。
        """
        self._subtree_size = max(1, int(size))

    def get_nebula_radius(self) -> float:
        """⭐ nebula 模式下当前节点的圆点半径（供 link_particles / label 计算距离用）。"""
        import math

        r = self.NEBULA_DOT_RADIUS * (
            1.0 + self.NEBULA_SIZE_DEGREE_FACTOR * math.sqrt(self._subtree_size)
        )
        return max(self.NEBULA_SIZE_MIN, min(self.NEBULA_SIZE_MAX, r))

    def set_nebula_label_visible(self, visible: bool) -> None:
        """⭐⭐ nebula 模式：被点击后浮窗显示文字。

        True  → 在节点上方/下方浮一个 label（不是 tooltip，移动鼠标不会消失）
        False → 隐藏 label
        """
        self._nebula_label_visible = bool(visible)
        self.update()  # 触发 paint 重画（label 由 node 自己画）

    def center(self) -> QPointF:
        """返回节点中心点（用于连边）。"""
        return QPointF(
            self.pos().x() + self.width / 2, self.pos().y() + self.height / 2
        )


# ==================== 模块级辅助函数 ====================


def _sin01(t: float) -> float:
    """sin → 0..1 区间（用于脉冲强度系数）。"""
    import math

    return 0.5 + 0.5 * math.sin(t)


def _ensure_visible_dark(c: QColor) -> QColor:
    """确保深色填充至少有最小亮度，避免节点全黑看不见文字。"""
    if c.value() < 22:
        c.setHsv(c.hue(), c.saturation(), 28)
    return c


def _darken_keep_hue(c: QColor, target_l: int = 18) -> QColor:
    """⭐ 按目标亮度取色（HSL 思路），保留色相 + 高饱和。

    比 QColor.darker() 更可控：darker 是按 ratio 缩三通道，
    对高饱和色会把色相拉偏。这里直接改 lightness 到 18%，白字可读。
    """
    h, s, _l, a = c.getHsl()
    if h == -1:  # 灰/无色相
        return QColor(target_l, target_l, target_l, a if a else 255)
    # 保留原饱和（s 可能为 -1），clamp 一下
    sat = max(0, s) if s >= 0 else 0
    return QColor.fromHsl(h, sat, target_l, a if a else 255)
