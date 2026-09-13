# -*- coding: utf-8 -*-
"""⭐ 划线切割删除（swipe-to-cut）回归测试。

测试目标：
1. _segments_intersect / _line_intersects_rect：几何相交检测
2. graph.detach_node：后代脱离为新根，子树结构保留
3. set_warning：节点和边的切割高亮标记

不测的部分（需要真实鼠标事件）：
- mousePressEvent / mouseMoveEvent / mouseReleaseEvent 集成
- cut_confirmed 信号全链路

这些集成路径在 GUI 启动时手动验证。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QLineF, QPointF, QRectF
from PySide6.QtGui import QGuiApplication

_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from src.mindmap.graph import MindMapGraph
from src.mindmap.node import NodeData
from src.ui.edge_item import EdgeItem
from src.ui.mindmap_view import _line_intersects_rect, _segments_intersect
from src.ui.node_item import NodeItem


# ==================== 几何相交 ====================

def test_segments_intersect_cross():
    """X 型交叉 → True"""
    a = QLineF(QPointF(0, 0), QPointF(10, 10))
    b = QLineF(QPointF(0, 10), QPointF(10, 0))
    assert _segments_intersect(a, b) is True


def test_segments_intersect_parallel():
    """平行线 → False（延长不算相交）"""
    a = QLineF(QPointF(0, 0), QPointF(10, 0))
    b = QLineF(QPointF(0, 5), QPointF(10, 5))
    assert _segments_intersect(a, b) is False


def test_segments_intersect_disjoint():
    """完全分离 → False"""
    a = QLineF(QPointF(0, 0), QPointF(5, 5))
    b = QLineF(QPointF(20, 20), QPointF(25, 25))
    assert _segments_intersect(a, b) is False


def test_line_intersects_rect_horizontal_cross():
    """横线穿过矩形 → True"""
    line = QLineF(QPointF(0, 5), QPointF(20, 5))
    rect = QRectF(8, 0, 10, 10)
    assert _line_intersects_rect(line, rect) is True


def test_line_intersects_rect_far_away():
    """远离矩形的线 → False（不算延长相交）"""
    line = QLineF(QPointF(0, 50), QPointF(20, 50))
    rect = QRectF(8, 0, 10, 10)
    assert _line_intersects_rect(line, rect) is False


def test_line_intersects_rect_endpoint_inside():
    """线段一端在矩形内 → True"""
    line = QLineF(QPointF(10, 5), QPointF(100, 5))
    rect = QRectF(8, 0, 10, 10)
    assert _line_intersects_rect(line, rect) is True


# ==================== graph.detach_node 语义 ====================

def test_detach_node_basic():
    """切割中间节点：直接子节点脱离为根，间接后代保留父子关系。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="root", text="Root"), parent_id=None)
    g.add_node(NodeData(id="mid", text="Mid"), parent_id="root")
    g.add_node(NodeData(id="child1", text="C1"), parent_id="mid")
    g.add_node(NodeData(id="child2", text="C2"), parent_id="mid")
    g.add_node(NodeData(id="grand", text="G"), parent_id="child1")

    g.detach_node("mid")

    # mid 已删
    assert "mid" not in g
    # child1 / child2 已脱离（parent_id=None）
    assert g.get_node("child1").parent_id is None
    assert g.get_node("child2").parent_id is None
    # grand 仍属于 child1（子树结构保留）
    assert g.get_node("grand").parent_id == "child1"
    # root 不再有 mid 这个孩子
    assert "mid" not in [c.id for c in g.get_children("root")]
    # 长度：5 - 1（mid 删除）= 4
    assert len(g) == 4


def test_detach_root():
    """切割根节点：直接子节点成为新根（成为新森林）。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="root", text="Root"), parent_id=None)
    g.add_node(NodeData(id="c1", text="C1"), parent_id="root")
    g.add_node(NodeData(id="c2", text="C2"), parent_id="root")

    g.detach_node("root")

    assert "root" not in g
    assert g.get_node("c1").parent_id is None
    assert g.get_node("c2").parent_id is None
    # root_id 被重新指向其中一个还存在的节点
    assert g.root_id in ("c1", "c2")


def test_detach_leaf():
    """切割叶子节点：等于普通删除（无后代需要脱离）。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="root", text="Root"), parent_id=None)
    g.add_node(NodeData(id="leaf", text="Leaf"), parent_id="root")

    g.detach_node("leaf")

    assert "leaf" not in g
    assert "leaf" not in [c.id for c in g.get_children("root")]
    assert len(g) == 1


# ==================== set_warning 标记 ====================

def test_node_warning_flag():
    """NodeItem.set_warning 切换并保留状态。"""
    node = NodeItem(node_id="n1", text="T")
    assert node.is_warning() is False
    node.set_warning(True)
    assert node.is_warning() is True
    node.set_warning(False)
    assert node.is_warning() is False


def test_edge_warning_color():
    """EdgeItem.set_warning 切换颜色（默认灰 → 警告红）。"""
    src = NodeItem(node_id="s", text="S")
    tgt = NodeItem(node_id="t", text="T")
    edge = EdgeItem(src, tgt, color="#888888")

    assert edge.is_warning() is False
    edge.set_warning(True)
    assert edge.is_warning() is True
    assert edge.color.name() == "#ff3b30"
    edge.set_warning(False)
    assert edge.is_warning() is False
    assert edge.color.name() == "#888888"


# ==================== 入口 ====================

def main() -> int:
    tests = [
        test_segments_intersect_cross,
        test_segments_intersect_parallel,
        test_segments_intersect_disjoint,
        test_line_intersects_rect_horizontal_cross,
        test_line_intersects_rect_far_away,
        test_line_intersects_rect_endpoint_inside,
        test_detach_node_basic,
        test_detach_root,
        test_detach_leaf,
        test_node_warning_flag,
        test_edge_warning_color,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  [OK]   {fn.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    total = len(tests)
    print(f"\n{'[ALL PASS]' if failed == 0 else f'[FAIL {failed}/{total}]'} 划线切割删除回归测试")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
