"""节点图片选择器 — NoteEditor 「🖼 图片」按钮弹出的对话框。

用法：
    dlg = ImagePickerDialog(attachments, parent=self)
    if dlg.exec() == QDialog.Accepted and dlg.picked:
        path, alt = dlg.picked
        note_editor.insert_image_markdown(path, alt)

设计：
- 网格布局：每个图片一张缩略图 + caption，鼠标点一下就选中 + accept
- 空列表友好提示：「去附件面板 ➕ 添加图片」（不是冷冰冰的「无数据」）
- 复用 AttachmentPanel 的 _build_thumbnail，保证视觉一致
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# 复用附件面板的缩略图渲染（保持视觉一致）
from src.ui.attachment_panel import _build_thumbnail

# ==================== 常量 ====================

THUMB_SIZE = QSize(110, 110)  # 比附件面板的 96 略大 — 对话框里要看得清
GRID_COLUMNS = 4
CELL_PADDING = 8


# ==================== 单元格 ====================


class _ImageCell(QToolButton):
    """单个图片按钮：缩略图在上，文件名在下。

    单击 → 通知对话框选中（relative_path, alt）
    """

    def __init__(self, att: dict, on_clicked) -> None:
        super().__init__()
        self._att = att
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(THUMB_SIZE)
        self.setFixedSize(140, 160)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._build_tooltip(att))
        self.setStyleSheet(
            "QToolButton {"
            "  background: #fafafa;"
            "  border: 1px solid #e0e0e0;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "}"
            "QToolButton:hover {"
            "  background: #e8f1fc;"
            "  border: 1px solid #4A90E2;"
            "}"
            "QToolButton:pressed {"
            "  background: #d0e4f7;"
            "}"
        )
        pix = _build_thumbnail(att)
        self.setIcon(QIcon(pix))
        # 按钮文字：优先 caption，否则文件名
        label = att.get("caption") or Path(att["file_path"]).stem
        self.setText(label)
        self.clicked.connect(lambda: on_clicked(att))

    @staticmethod
    def _build_tooltip(att: dict) -> str:
        caption = att.get("caption") or Path(att["file_path"]).name
        return f"{caption}\n路径：{att['file_path']}\n点击插入"


# ==================== 对话框 ====================


class ImagePickerDialog(QDialog):
    """节点图片选择器。"""

    def __init__(self, attachments: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        # 只保留 image 类型（防御性，正常情况下外面已经过滤）
        self._images: list[dict] = [
            a for a in attachments if a.get("file_type") == "image"
        ]
        self.picked: tuple[str, str] | None = None  # (relative_path, alt)

        self.setWindowTitle("🖼 选择要插入的图片")
        self.setMinimumSize(640, 480)
        self._init_ui()

    # ==================== UI ====================

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部说明
        if self._images:
            hint = QLabel(f"共 {len(self._images)} 张图片，点击即可插入到光标位置：")
            hint.setStyleSheet("color: #555; font-size: 10pt;")
        else:
            hint = QLabel("⚠ 当前节点还没有图片附件。")
            hint.setStyleSheet(
                "color: #d97706; font-size: 10pt; font-weight: bold;"
                "background: #fffbeb; border: 1px solid #fde68a;"
                "border-radius: 4px; padding: 8px;"
            )
        layout.addWidget(hint)

        # 主体：网格 OR 空状态
        if not self._images:
            layout.addWidget(self._build_empty_state())
        else:
            layout.addWidget(self._build_grid(), 1)

        # 底部按钮
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def _build_grid(self) -> QWidget:
        """缩略图网格（外层 QScrollArea 防止图片太多溢出）。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: #ffffff; border: 1px solid #e0e0e0;"
            "              border-radius: 4px; }"
        )

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(12)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        for i, att in enumerate(self._images):
            row, col = divmod(i, GRID_COLUMNS)
            cell = _ImageCell(att, on_clicked=self._on_pick)
            grid.addWidget(cell, row, col)

        # 补齐最后一行（让最后一行靠左不居中）
        remainder = len(self._images) % GRID_COLUMNS
        if remainder and remainder < GRID_COLUMNS:
            spacer = QWidget()
            spacer.setFixedSize(0, 0)
            last_row = (len(self._images) - 1) // GRID_COLUMNS
            grid.addWidget(spacer, last_row, GRID_COLUMNS - 1)

        scroll.setWidget(inner)
        return scroll

    def _build_empty_state(self) -> QWidget:
        """空状态：友好的引导 + 一键打开附件面板按钮。"""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #f9f9f9; border: 1px dashed #ccc;"
            "         border-radius: 8px; padding: 24px; }"
        )
        v = QVBoxLayout(frame)
        v.setSpacing(12)
        v.setAlignment(Qt.AlignCenter)

        icon = QLabel("🖼")
        icon_font = icon.font()
        icon_font.setPointSize(48)
        icon.setFont(icon_font)
        icon.setAlignment(Qt.AlignCenter)
        v.addWidget(icon)

        title = QLabel("当前节点还没有图片附件")
        title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #555;")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)

        tip = QLabel(
            "请先到右侧详情面板的「📚 节点资料」区\n"
            "点击 ➕ 添加 上传图片，然后再回这里插入。"
        )
        tip.setStyleSheet("color: #888; font-size: 10pt;")
        tip.setAlignment(Qt.AlignCenter)
        v.addWidget(tip)

        return frame

    # ==================== 选择回调 ====================

    def _on_pick(self, att: dict) -> None:
        rel_path = att["file_path"]
        alt = att.get("caption") or Path(att["file_path"]).stem
        self.picked = (rel_path, alt)
        self.accept()


__all__ = ["ImagePickerDialog"]
