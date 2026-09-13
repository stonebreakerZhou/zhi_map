"""⭐ 静态星点背景（project-graph / Obsidian 风格）。

设计要点：
- 单 paint() 调用画完所有星点（性能优于每个星一个 item）
- 默认 220 颗星，3 档大小，2-3 种微调色（白 / 微黄 / 微蓝 / 微紫）
- twinkle 由低频 QTimer（80ms）驱动，单星相位不同 → 看起来像真在闪
- z = -100：永远在节点和边之下
- SCENE_EXTENT 拉到 8000，pan 时不会"跑出"星图
- ⭐ 2026-09-13：支持 layer 配置（"near" / "far"），配合 view.scrollContentsBy
  实现星空视差效果。near 层 z=-90 / 慢 twinkle / 粗星；far 层 z=-110 / 快 twinkle / 细星。

注意：seed 固定 → 每次启动星图布局一样，便于体感稳定。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem

# ⭐ 不同 layer 的配置预设（key=layer 名称，value=星图参数）
LAYER_PRESETS = {
    "default": {
        "star_count": 220,
        "size_ranges": [(0.7, 1.0), (1.1, 1.7), (1.9, 2.6)],
        "size_weights": [0.55, 0.37, 0.08],  # 细:中:粗 = 7:5:1
        "twinkle_speed_range": (0.5, 1.4),
        "z_value": -100,
        "twinkle_interval_ms": 80,
    },
    "near": {
        # 近层：少而粗，慢 twinkle，跟 view 完全同步移动（无视差差速）
        "star_count": 60,
        "size_ranges": [(1.3, 1.8), (2.0, 2.8)],  # 偏粗
        "size_weights": [0.40, 0.60],
        "twinkle_speed_range": (0.3, 0.7),  # 慢
        "z_value": -90,
        "twinkle_interval_ms": 100,
    },
    "far": {
        # 远层：多而细，快 twinkle，只跟 view 50% 移动（视差明显）
        "star_count": 180,
        "size_ranges": [(0.5, 0.8), (0.9, 1.2)],  # 偏细
        "size_weights": [0.65, 0.35],
        "twinkle_speed_range": (0.8, 1.6),  # 快
        "z_value": -110,
        "twinkle_interval_ms": 60,
    },
}


class StarfieldItem(QGraphicsItem):
    """星空：所有星点在一个 item 里画完。"""

    # 星点铺开的 scene 范围（中心 ± EXTENT）。pan 时永远有星可看
    SCENE_EXTENT = 8000
    # 默认 twinkle 间隔（layer="default" 用）
    TWINKLE_INTERVAL_MS = 80

    def __init__(
        self,
        parent: QGraphicsItem | None = None,
        layer: str = "default",
    ) -> None:
        super().__init__(parent)
        # ⭐ 读 preset（layer 不存在则退回 default）
        preset = LAYER_PRESETS.get(layer, LAYER_PRESETS["default"])
        self._layer = layer
        self._star_count = preset["star_count"]
        self._size_ranges = preset["size_ranges"]
        self._size_weights = preset["size_weights"]
        self._twinkle_speed_range = preset["twinkle_speed_range"]
        self._z_value = preset["z_value"]
        self._twinkle_interval_ms = preset["twinkle_interval_ms"]

        # ⭐ 永远在画布底层（不同 layer 不同 z，确保视差正确）
        self.setZValue(self._z_value)
        # 不参与 hitTest（星星不该拦截点击）
        self.setAcceptedMouseButtons(Qt.NoButton)

        # 固定 seed → 每次启动星图布局一样，体感稳定
        # ⭐ 注意：near/far 共用 seed=42 会有"对齐"问题（视差时星点刚好重叠）。
        # 用 layer 派生 seed → near/far 布局错开，更像真星空
        seed = 42 + (hash(layer) & 0xFF)
        random.seed(seed)
        self._stars: list[dict] = []
        for _ in range(self._star_count):
            size_roll = random.random()
            size = self._pick_size(size_roll)
            twinkle_speed_lo, twinkle_speed_hi = self._twinkle_speed_range
            self._stars.append(
                {
                    "x": random.uniform(-self.SCENE_EXTENT, self.SCENE_EXTENT),
                    "y": random.uniform(-self.SCENE_EXTENT, self.SCENE_EXTENT),
                    "size": size,
                    # base_opacity 越低越"暗"，0.3~0.95 之间分布出层次
                    "base_opacity": random.uniform(0.35, 0.95),
                    # twinkle 相位（每颗星独立的 sin 相位，避免同步闪）
                    "phase": random.uniform(0.0, math.tau),
                    # twinkle 频率（部分星闪得慢，部分星闪得快）
                    "speed": random.uniform(twinkle_speed_lo, twinkle_speed_hi),
                    # 微调色：白 / 暖白 / 冷白 / 微紫
                    "color": random.choice(
                        [
                            QColor(255, 255, 255),
                            QColor(255, 250, 232),  # pale yellow
                            QColor(220, 232, 255),  # pale blue
                            QColor(232, 222, 255),  # pale violet
                        ]
                    ),
                }
            )

        # ⭐ twinkle 驱动：用 QTimer 单点更新 _t，避免每帧重算 sin
        # PySide6 6.x：QTimer 不接受 QGraphicsItem 作 parent，故用 None
        self._t = 0.0
        self._timer = QTimer()
        self._timer.setInterval(self._twinkle_interval_ms)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _pick_size(self, roll: float) -> float:
        """⭐ 根据 roll[0,1) 在 size_ranges + size_weights 中选一个 size 区间。"""
        acc = 0.0
        for w, (lo, hi) in zip(self._size_weights, self._size_ranges):
            acc += w
            if roll < acc:
                return random.uniform(lo, hi)
        # 兜底：最后一档
        lo, hi = self._size_ranges[-1]
        return random.uniform(lo, hi)

    @property
    def layer(self) -> str:
        return self._layer

    # ------- 内部状态 -------

    def _on_tick(self) -> None:
        self._t += 0.16
        self.update()  # 触发一次全画布的 view 局部重绘

    # ------- QGraphicsItem 必需接口 -------

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
        # 抗锯齿开（星点是圆的，关 AA 会变方块）
        aa_on = painter.testRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            painter.setPen(Qt.NoPen)
            for s in self._stars:
                # twinkle：sin 函数让 opacity 在 85%~115% base_opacity 之间漂
                twinkle = 0.85 + 0.30 * math.sin(self._t * s["speed"] + s["phase"])
                alpha = s["base_opacity"] * twinkle
                color = QColor(s["color"])
                color.setAlphaF(max(0.0, min(1.0, alpha)))
                painter.setBrush(QBrush(color))
                r = s["size"]
                painter.drawEllipse(QPointF(s["x"], s["y"]), r, r)
        finally:
            painter.setRenderHint(QPainter.Antialiasing, aa_on)
