"""节点附件面板 — 仿 Swapy 拖拽换位。

参考：https://github.com/TahaSh/swapy

Swapy 原生架构（移植到 Qt/PySide6）：
    ┌─────────────────────────────────────────────────────┐
    │  Slot 在 DOM 中位置不变（CSS flex/grid 静态布局）    │
    │  Item 是被 swap 的元素 — `slot.appendChild(item)`    │
    │  FLIP: 记录 item 当前 rect → 切 parent →              │
    │         记录 final rect → CSS transform 拉回旧位置   │
    │         → animation 过渡到 identity                  │
    └─────────────────────────────────────────────────────┘

Qt 移植关键（避免踩坑）：
    1. Slot 是固定位置的 QFrame（手动 setGeometry，不参与 layout）
    2. Item 是 grid 的直接子节点 — 绝对定位（手动 move），
       ⭐ 永远不 setParent 到 slot —— 否则 pos() 坐标系切换，
       FLIP 的 initial/final 在不同坐标系下 → 图片飞走。
    3. Item 的视觉位置始终等于某个 slot 的"内部中心点"（grid 坐标）
    4. swap：把两个 item 在 grid 内的 pos 互相交换（FLIP）
       - items[i] 从 slot_i 中心 → slot_j 中心
       - items[j] 从 slot_j 中心 → slot_i 中心
       - 两个独立的 QPropertyAnimation 同时跑
    5. slot 的视觉内容用 "iindex 映射" 维护：item_idx → slot_idx
       swap 后只需交换 _slot_index[i] 和 _slot_index[j]

UI 结构：
    ┌────────────────────────────────────────┐
    │ [+添加] [💬说明] [🗑删除] | [🔍全屏(F)] │
    ├────────────────────────────────────────┤
    │ [s0] [s1] [s2] [s3]   ← slot 固定位置  │
    │  📷   📷   📄   📷    ← item 浮在 grid │
    │                         上，跟着 move   │
    ├────────────────────────────────────────┤
    │ 📷 文件名.jpg · 💬 说明文字             │
    └────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.storage import mindmap_repo
from src.storage.attachment_manager import get_attachment_manager
from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.attachment_panel")


# ==================== 常量 ====================

THUMB_SIZE = QSize(112, 112)
SLOT_W = 144
SLOT_H = 156
SLOT_GAP = 8
SLOT_PADDING = 6
LONG_PRESS_MS = 180
SWAP_DURATION_MS = 250
DRAG_START_PX = 6
GHOST_ALPHA = 0.72

# item 缩略图在 slot 内的左上角偏移（slot 144×156，item 112×112 → 居中偏上）
ITEM_OFFSET_IN_SLOT = QPoint(
    (SLOT_W - THUMB_SIZE.width()) // 2,
    6,  # 顶留 6px 间距
)

CAPTION_OFFSET = QPoint(
    (SLOT_W - THUMB_SIZE.width()) // 2,
    THUMB_SIZE.height() + 8,
)

SLOT_STYLE = (
    "QFrame { background: #fafafa; border: 1px solid #e0e0e0;"
    "         border-radius: 6px; }"
)
SLOT_HIGHLIGHT_STYLE = (
    "QFrame { background: #e8f1fc; border: 2px dashed #4A90E2;"
    "         border-radius: 6px; }"
)
GRID_STYLE = (
    "QWidget { background: #ffffff; border: 1px solid #e0e0e0;"
    "          border-radius: 6px; }"
)
INFO_PLACEHOLDER_STYLE = "color: #888; font-size: 9pt; padding: 2px 4px;"
INFO_ACTIVE_STYLE = "color: #e5e7eb; font-size: 9pt; padding: 2px 4px;"


# ==================== 缩略图渲染（公用） ====================


def _build_thumbnail(att: dict) -> QPixmap:
    """生成缩略图 QPixmap。优先真实图片，否则生成占位。"""
    if att["file_type"] == "image":
        abs_path = get_attachment_manager().resolve_path(att["file_path"])
        if abs_path and abs_path.exists():
            src = QPixmap(str(abs_path))
            if not src.isNull():
                return src.scaled(
                    THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
    placeholder = QPixmap(THUMB_SIZE)
    placeholder.fill(QColor("#e8e8e8"))
    p = QPainter(placeholder)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#888"))
    f = QFont()
    f.setPointSize(28)
    p.setFont(f)
    icon = "🖼" if att["file_type"] == "image" else "📄"
    p.drawText(placeholder.rect(), Qt.AlignCenter, icon)
    p.end()
    return placeholder


def _make_translucent(pix: QPixmap, alpha: float) -> QPixmap:
    """把 QPixmap 整体降低 alpha（覆盖白色层 = 视觉上变淡）。"""
    out = pix.copy()
    if out.isNull():
        return out
    overlay = QPixmap(out.size())
    overlay.fill(QColor(255, 255, 255, int((1.0 - alpha) * 255)))
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(0, 0, overlay)
    p.end()
    return out


def _build_caption(att: dict) -> str:
    caption = att.get("caption") or Path(att["file_path"]).name
    prefix = "📷" if att["file_type"] == "image" else "📄"
    return f"{prefix} {caption[:12]}"


def _build_tooltip(att: dict, is_cover: bool) -> str:
    caption = att.get("caption") or Path(att["file_path"]).name
    return f"{caption}\n路径：{att['file_path']}\n类型：{att['file_type']}" + (
        "\n（封面）" if is_cover else ""
    )


# ==================== Item（被拖动的元素，对应 Swapy 的 item）====================


class _AttachmentItem(QLabel):
    """⭐ Swapy 的 data-swapy-item：被 swap / 被拖动的元素。

    - 始终是 _SwapyGrid 的直接子节点（绝不被 setParent 到 slot！）
    - 绝对定位（手动 move）
    - 携带 attachment 数据和"视觉状态"（normal / ghost / caption 文字）
    """

    def __init__(self, att: dict, grid: _SwapyGrid) -> None:
        super().__init__(grid)
        self._attachment: dict = att
        self._grid = grid

        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(THUMB_SIZE)
        self.setStyleSheet("QLabel { background: transparent; border: none; }")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._normal_pix: QPixmap = _build_thumbnail(att)
        self.setPixmap(self._normal_pix)
        self.raise_()

    def get_attachment(self) -> dict:
        return self._attachment

    def set_attachment(self, att: dict) -> None:
        self._attachment = att
        self._normal_pix = _build_thumbnail(att)
        self.setPixmap(self._normal_pix)

    def make_ghost(self) -> None:
        """切换到 ghost 视觉（拖拽中）。"""
        self.setPixmap(_make_translucent(self._normal_pix, GHOST_ALPHA))

    def restore_normal(self) -> None:
        """恢复普通视觉。"""
        self.setPixmap(self._normal_pix)


# ==================== Slot（固定位置容器，对应 Swapy 的 slot）====================


class _AttachmentSlot(QFrame):
    """⭐ Swapy 的 data-swapy-slot：固定位置容器（无 item 子节点）。

    - setGeometry 由 _SwapyGrid 手动管理
    - 不持有 item（item 由 grid 单独管理）
    - 显示高亮效果（hover / drag 时）
    - 把鼠标事件转发给 grid 处理
    """

    def __init__(self, index: int, parent: _SwapyGrid) -> None:
        super().__init__(parent)
        self._grid = parent
        self.index: int = index
        self._highlighted: bool = False
        self._attachment: dict | None = None  # 当前 slot 承载的附件（虚拟）

        self.setFixedSize(SLOT_W, SLOT_H)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(SLOT_STYLE)

    # ==================== 数据 ====================

    def set_attachment(self, att: dict | None) -> None:
        self._attachment = att
        self.refresh_tooltip()

    def get_attachment(self) -> dict | None:
        return self._attachment

    def refresh_tooltip(self) -> None:
        if self._attachment is None:
            self.setToolTip("")
            return
        is_cover = self.index == 0
        self.setToolTip(_build_tooltip(self._attachment, is_cover))

    # ==================== 几何计算 ====================

    def item_top_left_global(self) -> QPoint:
        """item 在 grid 坐标系下的左上角 = slot 内的固定偏移。"""
        return self.geometry().topLeft() + ITEM_OFFSET_IN_SLOT

    # ==================== 高亮 ====================

    def set_highlighted(self, on: bool) -> None:
        if self._highlighted == on:
            return
        self._highlighted = on
        self.setStyleSheet(SLOT_HIGHLIGHT_STYLE if on else SLOT_STYLE)

    def is_highlighted(self) -> bool:
        return self._highlighted

    # ==================== 鼠标 ====================

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._grid._on_slot_press(self, event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton:
            self._grid._on_slot_move(self, event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._grid._on_slot_release(self, event)
        super().mouseReleaseEvent(event)


# ==================== Swapy 网格（手动布局 slots + items）====================


class _SwapyGrid(QWidget):
    """⭐ Swapy 主容器。

    状态：
        - _slots:    List[_AttachmentSlot]  固定位置，不动
        - _items:    List[_AttachmentItem]  grid 的直接子，绝对定位
        - _slot_for_item: Dict[item_idx, slot_idx]  item i 当前视觉上属于哪个 slot
                          初始 = {0:0, 1:1, 2:2, ...}
                          swap(i,j) 后 = {..., i:j, j:i, ...}

    拖拽流程：
        1. press on slot[i]：记录 _press_slot_index = i，启动 180ms 长按定时器
        2. hold timeout 或 move > 6px → _begin_drag：
           - item i 切到 ghost 视觉
           - 跟踪鼠标，item.move(following cursor)
           - 原 slot[i] 保持高亮（视觉上空 slot）
        3. mouseMove 期间检测 hover：
           - 鼠标命中 slot[j] → _animate_swap(i, j)
           - FLIP: item_i 当前位置 → slot_j 的 item 位置；item_j 当前位置 → slot_i 的 item 位置
           - 交换 _slot_for_item 映射（先交换再启动动画 —— 但动画的 final pos
             用的是 slot 几何，不依赖映射，所以顺序无所谓）
           - 两个独立 QPropertyAnimation 同时跑
           - 更新 _press_slot_index = j（让下一次 hover 用新源 slot 编号）
        4. release → _end_drag：取消高亮，恢复 ghost → normal，持久化
    """

    def __init__(self, panel: AttachmentPanel) -> None:
        super().__init__(panel)
        self._panel = panel
        self._slots: list[_AttachmentSlot] = []
        self._items: list[_AttachmentItem] = []
        # ⭐ item_idx → 当前 slot_idx（item 视觉上属于哪个 slot）
        self._slot_for_item: dict[int, int] = {}
        # 反向：slot_idx → item_idx
        self._item_for_slot: dict[int, int] = {}

        # 不用任何 layout —— slots / items 全部手动 setGeometry / move
        self.setStyleSheet(GRID_STYLE)
        self.setMouseTracking(True)
        self.setMinimumHeight(SLOT_H + SLOT_PADDING * 2 + 2)

        # 拖拽状态
        self._press_slot_index: int = -1
        self._press_global_pos: QPoint = QPoint()
        self._drag_active: bool = False
        self._drag_item_index: int = -1  # 正在被拖的 item idx
        self._drag_offset: QPoint = QPoint()

        # 长按定时器
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_timeout)

        # 进行中的 swap 动画（用 set 防止重复 add）
        self._active_animations: list[QPropertyAnimation] = []

    # ==================== 槽位管理 ====================

    def clear_slots(self) -> None:
        # 清理 items
        for it in self._items:
            it.setParent(None)
            it.deleteLater()
        # 清理 slots
        for s in self._slots:
            s.setParent(None)
            s.deleteLater()
        self._slots.clear()
        self._items.clear()
        self._slot_for_item.clear()
        self._item_for_slot.clear()
        # 取消进行中的动画
        for a in self._active_animations:
            if a.state() == QAbstractAnimation.Running:
                a.stop()
        self._active_animations.clear()

    def rebuild_slots(self, attachments: list[dict]) -> None:
        """根据 attachments 重建槽位（一对一）。"""
        self.clear_slots()
        total_w = (
            SLOT_PADDING * 2
            + len(attachments) * SLOT_W
            + max(0, len(attachments) - 1) * SLOT_GAP
        )
        self.setMinimumWidth(total_w)

        for i, att in enumerate(attachments):
            # slot
            slot = _AttachmentSlot(i, self)
            x = SLOT_PADDING + i * (SLOT_W + SLOT_GAP)
            y = SLOT_PADDING + 1
            slot.setGeometry(x, y, SLOT_W, SLOT_H)
            slot.set_attachment(att)
            slot.show()
            self._slots.append(slot)

            # item（grid 的直接子）
            item = _AttachmentItem(att, self)
            item.move(slot.item_top_left_global())
            item.show()
            self._items.append(item)

            # 双向映射
            self._slot_for_item[i] = i
            self._item_for_slot[i] = i

    def get_attachments_in_order(self) -> list[dict]:
        """按 slot 顺序返回 attachments。"""
        result: list[dict] = []
        for slot_idx in range(len(self._slots)):
            item_idx = self._item_for_slot.get(slot_idx)
            if item_idx is None:
                continue
            att = self._items[item_idx].get_attachment()
            if att is not None:
                result.append(att)
        return result

    def get_attachment_at_slot(self, slot_idx: int) -> dict | None:
        item_idx = self._item_for_slot.get(slot_idx)
        if item_idx is None:
            return None
        return self._items[item_idx].get_attachment()

    def slot_at_global_pos(self, global_pos: QPoint) -> _AttachmentSlot | None:
        local = self.mapFromGlobal(global_pos)
        for s in self._slots:
            if s.geometry().contains(local):
                return s
        return None

    # ==================== 鼠标事件（slot 转发）====================

    def _on_slot_press(self, slot: _AttachmentSlot, event: QMouseEvent) -> None:
        self._press_slot_index = slot.index
        self._press_global_pos = event.globalPosition().toPoint()
        self._drag_active = False
        self._drag_item_index = -1
        self._hold_timer.start(LONG_PRESS_MS)

    def _on_slot_move(self, slot: _AttachmentSlot, event: QMouseEvent) -> None:
        if self._press_slot_index < 0 or self._press_slot_index != slot.index:
            return

        global_pos = event.globalPosition().toPoint()

        if not self._drag_active:
            moved = (global_pos - self._press_global_pos).manhattanLength()
            if moved < DRAG_START_PX:
                return
            self._hold_timer.stop()
            self._begin_drag(global_pos)
            return

        # 拖拽中：跟手
        self._follow_cursor(global_pos)

        # hover 检测：鼠标命中其他 slot → 触发 swap
        tgt_slot = self.slot_at_global_pos(global_pos)
        if tgt_slot is None or tgt_slot.index == self._press_slot_index:
            return

        # ⭐ 切换高亮：tgt_slot 高亮，其它不高亮
        for s in self._slots:
            s.set_highlighted(s is tgt_slot)

        # 触发 swap
        self._animate_swap(self._press_slot_index, tgt_slot.index)

    def _on_slot_release(self, slot: _AttachmentSlot, event: QMouseEvent) -> None:
        self._hold_timer.stop()
        if self._drag_active:
            self._end_drag()
        else:
            # 未触发拖拽 → 当作"选中"
            att = self.get_attachment_at_slot(slot.index)
            if att is not None:
                self._panel._on_slot_clicked(slot.index)

    # ==================== 长按触发 ====================

    def _on_hold_timeout(self) -> None:
        if self._press_slot_index < 0:
            return
        self._begin_drag(QCursor.pos())

    # ==================== 拖拽生命周期 ====================

    def _begin_drag(self, global_pos: QPoint) -> None:
        if self._press_slot_index < 0:
            return
        # 找到 press slot 当前承载的 item
        item_idx = self._item_for_slot.get(self._press_slot_index)
        if item_idx is None:
            return

        # item 切到 ghost
        self._items[item_idx].make_ghost()
        self._drag_item_index = item_idx

        # 计算鼠标相对 item 左上角的偏移（让 item 中心对齐鼠标）
        item = self._items[item_idx]
        item_w = item.width()
        item_h = item.height()
        local_pos = self.mapFromGlobal(global_pos)
        # 偏移 = item 左上角相对鼠标的差
        self._drag_offset = QPoint(local_pos.x() - item.x(), local_pos.y() - item.y())

        # 第一次对齐鼠标（保证用户手指在 item 中心）
        self._follow_cursor(global_pos)

        # 高亮 press slot（视觉上它"空"了）
        for s in self._slots:
            s.set_highlighted(s.index == self._press_slot_index)

        self._drag_active = True

    def _follow_cursor(self, global_pos: QPoint) -> None:
        """让 drag item 跟随鼠标（始终在 grid 坐标系下）。"""
        if self._drag_item_index < 0:
            return
        item = self._items[self._drag_item_index]
        local_pos = self.mapFromGlobal(global_pos)
        item.move(local_pos - self._drag_offset)
        item.raise_()

    # ==================== Swap（FLIP 双向飞入）====================

    def _animate_swap(self, src_slot_idx: int, tgt_slot_idx: int) -> None:
        """⭐ Swapy 核心 FLIP swap。

        把被拖的 item（src）从 src_slot 飞到 tgt_slot 的位置；
        tgt_slot 当前的 item 飞到 src_slot 的位置。
        两个独立 QPropertyAnimation 同时跑。
        """
        if src_slot_idx == tgt_slot_idx:
            return
        # ⭐ 被拖的 item 始终是 src（不再基于 src_slot_idx 查映射，
        # 因为 swap 后 src_slot_idx 仍可能引用已经被换走的 item）
        src_item_idx = self._drag_item_index
        tgt_item_idx = self._item_for_slot.get(tgt_slot_idx)
        if src_item_idx < 0:
            return

        # 取消进行中的 swap 动画
        self._cancel_pending_animations()

        # ⭐ readInitial: 两个 item 当前 pos（都在 grid 坐标系）
        src_item = self._items[src_item_idx]
        src_initial = QPoint(src_item.pos())

        tgt_item = None
        tgt_initial = None
        if tgt_item_idx is not None and tgt_item_idx != src_item_idx:
            tgt_item = self._items[tgt_item_idx]
            tgt_initial = QPoint(tgt_item.pos())

        # ⭐ 交换映射
        self._slot_for_item[src_item_idx] = tgt_slot_idx
        if tgt_item is not None:
            self._slot_for_item[tgt_item_idx] = src_slot_idx
        self._item_for_slot[src_slot_idx] = tgt_item_idx if tgt_item is not None else -1
        if tgt_item is not None:
            self._item_for_slot[tgt_slot_idx] = src_item_idx
        # 同步 slot 的虚拟 attachment（用于 tooltip）
        self._slots[src_slot_idx].set_attachment(
            self._slots[tgt_slot_idx].get_attachment()
        )
        if tgt_item is not None:
            self._slots[tgt_slot_idx].set_attachment(src_item.get_attachment())

        # ⭐ readFinalAndReverse: 立即 move 回 initial（FLIP 反置）
        src_target_slot = self._slots[tgt_slot_idx]
        src_final = src_target_slot.item_top_left_global()
        src_item.move(src_initial)

        # z-order: drag item 永远在最上
        src_item.raise_()
        if tgt_item is not None:
            tgt_item.raise_()
        src_item.raise_()

        anim_src = QPropertyAnimation(src_item, b"pos", self)
        anim_src.setDuration(SWAP_DURATION_MS)
        anim_src.setEasingCurve(QEasingCurve.OutCubic)
        anim_src.setStartValue(QPointF(src_initial))
        anim_src.setEndValue(QPointF(src_final))
        anim_src.finished.connect(lambda: self._on_anim_finished(anim_src))
        self._active_animations.append(anim_src)
        anim_src.start()

        # 同步动画另一个 item
        if tgt_item is not None and tgt_initial is not None:
            tgt_target_slot = self._slots[src_slot_idx]
            tgt_final = tgt_target_slot.item_top_left_global()
            tgt_item.move(tgt_initial)

            anim_tgt = QPropertyAnimation(tgt_item, b"pos", self)
            anim_tgt.setDuration(SWAP_DURATION_MS)
            anim_tgt.setEasingCurve(QEasingCurve.OutCubic)
            anim_tgt.setStartValue(QPointF(tgt_initial))
            anim_tgt.setEndValue(QPointF(tgt_final))
            anim_tgt.finished.connect(lambda: self._on_anim_finished(anim_tgt))
            self._active_animations.append(anim_tgt)
            anim_tgt.start()

        # ⭐ 拖拽源更新到 tgt_slot（用户拖到的位置）
        self._press_slot_index = tgt_slot_idx
        # drag_item_index 不变（src_item 仍是拖动对象）

        # 通知 panel 同步数据缓存 + tooltip
        self._panel._on_swap_animated()

    def _cancel_pending_animations(self) -> None:
        """取消所有进行中的 swap 动画。

        注意：QAbstractAnimation.stop() 不会触发 finished 信号 — stop 后的 anim
        不会被 _on_anim_finished 移除。所以这里在 stop 后主动清空整个 list。
        """
        for a in self._active_animations:
            try:
                if a.state() == QAbstractAnimation.Running:
                    a.stop()
            except RuntimeError:
                # C++ 对象已失效，跳过
                pass
        # 清空 — stop 后的 anim 不会再影响 widget（下一对 anim 会接管）
        self._active_animations.clear()

    def _on_anim_finished(self, anim: QPropertyAnimation) -> None:
        """⭐ 动画自然完成回调：从 list 移除自己。"""
        if anim in self._active_animations:
            self._active_animations.remove(anim)
        # 刷新 tooltip（cover 标记）
        for s in self._slots:
            s.refresh_tooltip()

    def _end_drag(self) -> None:
        """拖拽结束 — 取消高亮、恢复 drag item 为正常视觉、持久化。"""
        # 取消高亮
        for s in self._slots:
            s.set_highlighted(False)

        # 恢复 drag item 的视觉（从 ghost → normal）
        if self._drag_item_index >= 0:
            self._items[self._drag_item_index].restore_normal()
            # 确保它在正确的 slot 视觉位置上（如果当前不在）
            slot_idx = self._slot_for_item.get(self._drag_item_index)
            if slot_idx is not None:
                target_pos = self._slots[slot_idx].item_top_left_global()
                self._items[self._drag_item_index].move(target_pos)

        # 持久化
        self._panel._persist_current_order()

        self._drag_active = False
        self._drag_item_index = -1
        self._press_slot_index = -1
        self._press_global_pos = QPoint()


# ==================== 主组件 ====================


class AttachmentPanel(QWidget):
    """节点附件面板（仿 Swapy 拖拽版）。

    Signals:
        attachment_selected(dict)  — 用户选中某个附件
        fullscreen_requested()     — 用户请求全屏浏览当前选中图片
        attachment_changed()       — 附件列表增删改后发出
        add_requested(str)         — 携带 node_id，请求主窗口弹文件选择器
    """

    attachment_selected = Signal(dict)
    fullscreen_requested = Signal()
    attachment_changed = Signal()
    add_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_id: str | None = None
        self._current_attachment: dict | None = None
        self._attachments: list[dict] = []

        self._init_ui()

    # ==================== UI ====================

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setStyleSheet(
            "QToolBar { border: none; padding: 1px; }"
            "QToolButton { padding: 2px 6px; font-size: 9pt; }"
        )
        layout.addWidget(toolbar)

        self._btn_add = QPushButton("➕ 添加")
        self._btn_add.setToolTip("添加图片或文档附件（可多选）")
        self._btn_add.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self._btn_add)

        self._btn_caption = QPushButton("💬 说明")
        self._btn_caption.setToolTip("编辑选中附件的说明")
        self._btn_caption.clicked.connect(self._on_edit_caption)
        toolbar.addWidget(self._btn_caption)

        self._btn_delete = QPushButton("🗑 删除")
        self._btn_delete.setToolTip("删除选中附件")
        self._btn_delete.clicked.connect(self._on_delete)
        toolbar.addWidget(self._btn_delete)

        toolbar.addSeparator()

        self._btn_fullscreen = QPushButton("🔍 全屏 (F)")
        self._btn_fullscreen.setToolTip("全屏查看当前选中图片（F 键）")
        self._btn_fullscreen.clicked.connect(self._on_fullscreen)
        toolbar.addWidget(self._btn_fullscreen)

        QShortcut(QKeySequence("F"), self, activated=self._on_fullscreen)

        self._grid = _SwapyGrid(self)
        layout.addWidget(self._grid)

        self._info_label = QLabel()
        self._reset_info_label_placeholder()
        # ⭐ 换行（最多 2 行）：解决"文字显示不完全"
        self._info_label.setWordWrap(True)
        self._info_label.setMaximumHeight(48)  # 8pt × 2 行 ≈ 32px，再留 padding
        self._info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._info_label)

        self._update_buttons_state()

    # ==================== 公开 API ====================

    def set_node(self, node_id: str | None) -> None:
        self._node_id = node_id
        self._current_attachment = None
        self._refresh_list()
        if not self._attachments:
            self._reset_info_label_placeholder()
        else:
            self._select_attachment(self._attachments[0])

    def clear(self) -> None:
        self._node_id = None
        self._current_attachment = None
        self._attachments = []
        self._grid.clear_slots()
        self._reset_info_label_placeholder()
        self._update_buttons_state()

    def get_current_attachment(self) -> dict | None:
        return self._current_attachment

    def get_all_attachments(self) -> list[dict]:
        return list(self._attachments)

    def get_image_attachments(self) -> list[dict]:
        return [a for a in self._attachments if a["file_type"] == "image"]

    def get_cover_attachment(self) -> dict | None:
        if not self._attachments:
            return None
        for a in self._attachments:
            if a["file_type"] == "image":
                return a
        return self._attachments[0]

    # ==================== 内部：刷新列表 ====================

    def _refresh_list(self) -> None:
        self._grid.clear_slots()
        self._attachments = []
        if not self._node_id:
            self._update_buttons_state()
            return
        self._attachments = mindmap_repo.list_attachments(self._node_id)
        self._grid.rebuild_slots(self._attachments)
        self._update_buttons_state()
        self.attachment_changed.emit()

    # ==================== 槽位交互 ====================

    def _on_slot_clicked(self, idx: int) -> None:
        att = self._grid.get_attachment_at_slot(idx)
        if att is not None:
            self._select_attachment(att)

    def _select_attachment(self, att: dict) -> None:
        self._current_attachment = att
        self._render_preview(att)
        self._update_buttons_state()
        self.attachment_selected.emit(att)

    def _on_swap_animated(self) -> None:
        """⭐ 每次 swap 后同步内存缓存 + 刷新 slot tooltip。"""
        self._attachments = self._grid.get_attachments_in_order()
        for s in self._grid._slots:
            s.refresh_tooltip()
        if self._current_attachment is not None:
            current_id = self._current_attachment["id"]
            for s in self._grid._slots:
                att = s.get_attachment()
                if att and att["id"] == current_id:
                    self._current_attachment = att
                    break
        self.attachment_changed.emit()

    def _persist_current_order(self) -> None:
        if not self._node_id:
            return
        ordered_ids = [att["id"] for att in self._grid.get_attachments_in_order()]
        try:
            mindmap_repo.reorder_attachments(self._node_id, ordered_ids)
            logger.info(f"附件已重排（Swapy swap）: {ordered_ids}")
        except Exception as e:
            logger.error(f"持久化附件顺序失败: {e}")

    # ==================== 操作按钮 ====================

    def _on_add_clicked(self) -> None:
        if not self._node_id:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "提示", "请先选中一个节点")
            return
        self.add_requested.emit(self._node_id)

    def _on_edit_caption(self) -> None:
        if not self._current_attachment:
            return
        from PySide6.QtWidgets import QInputDialog

        new_caption, ok = QInputDialog.getText(
            self,
            "编辑说明",
            "附件说明（可空）：",
            text=self._current_attachment.get("caption") or "",
        )
        if ok:
            mindmap_repo.update_attachment_caption(
                self._current_attachment["id"], new_caption or None
            )
            self._refresh_list()

    def _on_delete(self) -> None:
        if not self._current_attachment:
            return
        from PySide6.QtWidgets import QMessageBox

        att = self._current_attachment
        att_name = att.get("caption") or Path(att["file_path"]).name
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"删除附件「{att_name}」？\n（图片/文档文件也会被删除）",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        mindmap_repo.delete_attachment(att["id"], delete_file=True)
        self._refresh_list()

    def _on_fullscreen(self) -> None:
        if (
            self._current_attachment
            and self._current_attachment["file_type"] == "image"
        ):
            self.fullscreen_requested.emit()

    def _render_preview(self, att: dict) -> None:
        type_icon = "📷" if att.get("file_type") == "image" else "📄"
        filename = Path(att["file_path"]).name
        # ⭐ 换行显示：第 1 行 文件名；第 2 行 caption（如果有）
        lines = [f"{type_icon} {filename}"]
        if att.get("caption"):
            lines.append(f"💬 {att['caption']}")
        self._info_label.setText("\n".join(lines))
        self._info_label.setStyleSheet(INFO_ACTIVE_STYLE)

    def _reset_info_label_placeholder(self) -> None:
        self._info_label.setText("（点 ➕ 添加 / 右键节点 → 添加资料附件）")
        self._info_label.setStyleSheet(INFO_PLACEHOLDER_STYLE)

    def _update_buttons_state(self) -> None:
        has_node = self._node_id is not None
        has_att = self._current_attachment is not None
        is_image = has_att and self._current_attachment["file_type"] == "image"

        self._btn_add.setEnabled(has_node)
        self._btn_fullscreen.setEnabled(is_image)
        self._btn_caption.setEnabled(has_att)
        self._btn_delete.setEnabled(has_att)


__all__ = ["AttachmentPanel"]
