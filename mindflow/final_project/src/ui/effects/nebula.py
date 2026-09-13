"""⭐ 星云（Nebula）背景：低饱和度径向渐变云团。

设计要点：
- 2-3 团不同色调的渐变云（紫 / 靛 / 青）
- opacity 极低（5-12%），仅作为"远方"背景的层次感
- 极大半径 → 边缘自然过渡为透明，不会看到硬边
- 静态，不参与交互
- z = -200：在 Starfield 之下

参考审美：project-graph 暗色 IDE / Linear Changelog 页 / Vercel 404
关键经验：用深紫 + 深青 + 高透明度，避免"迪士尼 / AI 默认渐变蓝紫"。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QGraphicsItem


class NebulaItem(QGraphicsItem):
    """星云背景（一个 item 画完所有云团）。"""

    # 星云铺开的 scene 范围（比 Starfield 还大，因为云团本身巨大）
    SCENE_EXTENT = 9000

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        # 比 Starfield 还低 → 永远在最底层
        self.setZValue(-200)
        self.setAcceptedMouseButtons(Qt.NoButton)

        # 三团云，每团独立色调。
        # 颜色都是 deep variant：避免浅色饱和 → 不会显"AI 味"
        # alpha 都是个位数百分比 → 极克制
        self._blobs: list[dict] = [
            {
                # 左上偏外：深紫 #4c1d95（violet-900）
                "x": -3500.0,
                "y": -2200.0,
                "radius": 4800.0,
                "core": QColor(76, 29, 149, 30),  # 中心 ~12%
                "edge": QColor(76, 29, 149, 0),
            },
            {
                # 右下偏外：深青 #155e75（cyan-800）
                "x": 3800.0,
                "y": 2400.0,
                "radius": 4400.0,
                "core": QColor(21, 94, 117, 26),  # 中心 ~10%
                "edge": QColor(21, 94, 117, 0),
            },
            {
                # 下方中央：深靛 #312e81（indigo-900），最小最淡
                "x": 200.0,
                "y": 4200.0,
                "radius": 3600.0,
                "core": QColor(49, 46, 129, 22),  # 中心 ~9%
                "edge": QColor(49, 46, 129, 0),
            },
        ]

    def boundingRect(self) -> QRectF:
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
        aa_on = painter.testRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            painter.setPen(Qt.NoPen)
            for blob in self._blobs:
                # 中心带色的渐变 → 边缘全透明 → 自然融入背景
                grad = QRadialGradient(
                    QPointF(blob["x"], blob["y"]),
                    blob["radius"],
                )
                grad.setColorAt(0.0, blob["core"])
                # 0.45 处再淡一档，避免云团中间"饱和"
                mid = QColor(blob["core"])
                mid.setAlpha(int(blob["core"].alpha() * 0.45))
                grad.setColorAt(0.45, mid)
                grad.setColorAt(1.0, blob["edge"])
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(
                    QPointF(blob["x"], blob["y"]),
                    blob["radius"],
                    blob["radius"],
                )
        finally:
            painter.setRenderHint(QPainter.Antialiasing, aa_on)
