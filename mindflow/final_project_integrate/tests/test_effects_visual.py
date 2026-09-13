# -*- coding: utf-8 -*-
"""⭐ 新特效冒烟测试：play_node_delete / play_edge_delete / play_cutting_trail / play_spark_effect。

不需要走完整 GUI 流程，直接构造 scene + item，验证：
1. 动画启动后不抛异常
2. 回调被触发
3. scene 自动清理（trail/spark 的 item 在 finish 时被移除）
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication, QGraphicsScene

from src.ui.delete_effect import (
    play_node_delete_animation,
    play_edge_delete_animation,
    play_cutting_trail,
    play_spark_effect,
    play_cut_release_effects,
)


def drain(app, ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def _make_rect_item(scene, x=0, y=0, w=80, h=30):
    """构造一个矩形 item（用 QGraphicsRectItem）。"""
    from PySide6.QtWidgets import QGraphicsRectItem
    item = QGraphicsRectItem(QRectF(x, y, w, h))
    scene.addItem(item)
    return item


def test_node_delete():
    app = QApplication.instance() or QApplication(sys.argv)
    scene = QGraphicsScene()
    item = _make_rect_item(scene)
    fired = [False]
    anim = play_node_delete_animation(item, on_finished=lambda: fired.__setitem__(0, True))
    drain(app, 400)
    assert fired[0], "on_finished 没触发"
    print("PASS: node_delete 动画结束回调触发")


def test_edge_delete():
    app = QApplication.instance() or QApplication(sys.argv)
    scene = QGraphicsScene()
    item = _make_rect_item(scene)
    fired = [False]
    anim = play_edge_delete_animation(item, on_finished=lambda: fired.__setitem__(0, True))
    drain(app, 400)
    assert fired[0]
    print("PASS: edge_delete 动画结束回调触发")


def test_cutting_trail():
    app = QApplication.instance() or QApplication(sys.argv)
    scene = QGraphicsScene()
    initial_count = len(scene.items())
    anim = play_cutting_trail(scene, QPointF(0, 0), QPointF(200, 100))
    # trail item 已加入 scene
    assert len(scene.items()) == initial_count + 1, "trail item 未加入"
    drain(app, 500)
    # 动画结束应自动移除
    assert len(scene.items()) == initial_count, f"trail 未清理，剩 {len(scene.items()) - initial_count}"
    print("PASS: cutting_trail 动画结束自动移除")


def test_spark_effect():
    app = QApplication.instance() or QApplication(sys.argv)
    scene = QGraphicsScene()
    initial = len(scene.items())
    anim = play_spark_effect(scene, QPointF(100, 100), radius=20)
    assert len(scene.items()) == initial + 1
    drain(app, 400)
    assert len(scene.items()) == initial, "spark 未清理"
    print("PASS: spark_effect 动画结束自动移除")


def test_cut_release_combined():
    """⭐ 整合测试：一次调用同时播残影 + 多个火花。"""
    from PySide6.QtGui import QColor
    app = QApplication.instance() or QApplication(sys.argv)
    scene = QGraphicsScene()
    initial = len(scene.items())
    collide = [QPointF(50, 50), QPointF(150, 50), QPointF(100, 100)]
    anims = play_cut_release_effects(
        scene, QPointF(0, 0), QPointF(200, 100), collide_points=collide,
    )
    # trail + 3 sparks = 4 个 item
    assert len(scene.items()) == initial + 4, f"expected 4 items, got {len(scene.items()) - initial}"
    drain(app, 500)
    assert len(scene.items()) == initial, f"残影/火花未清理，剩 {len(scene.items()) - initial}"
    print(f"PASS: cut_release 播放 1 trail + 3 sparks，全部自动清理")


if __name__ == "__main__":
    print("=== test_node_delete ==="); test_node_delete()
    print("=== test_edge_delete ==="); test_edge_delete()
    print("=== test_cutting_trail ==="); test_cutting_trail()
    print("=== test_spark_effect ==="); test_spark_effect()
    print("=== test_cut_release_combined ==="); test_cut_release_combined()
    print("\nALL EFFECTS PASS")