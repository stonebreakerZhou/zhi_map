# -*- coding: utf-8 -*-
"""⭐ 仅断开父子链接（不删节点、不动附加边）回归测试。

测试目标：
1. detach_parent_link 基本语义：parent 的 children 列表去掉 child；child 加入根
2. 调非父子关系无副作用
3. 断开后该子树涉及的附加边保留（不涉及原 parent 时）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mindmap.graph import MindMapGraph
from src.mindmap.node import NodeData


def test_detach_parent_link_basic():
    """基本语义：parent.children 移除 child；child 进入根；后代保留。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="p", text="P"), parent_id=None)
    g.add_node(NodeData(id="c", text="C"), parent_id="p")
    g.add_node(NodeData(id="gc", text="GC"), parent_id="c")
    # 验证初始
    assert "c" in [n.id for n in g.get_children("p")]
    assert g.get_node("c").parent_id == "p"
    # 断开
    g.detach_parent_link("p", "c")
    # c 不再是 p 的子节点
    assert "c" not in [n.id for n in g.get_children("p")]
    # c 的 parent_id 变为 None
    assert g.get_node("c").parent_id is None
    # gc 仍挂在 c 下（内部结构不变）
    assert g.get_node("gc").parent_id == "c"
    assert "gc" in [n.id for n in g.get_children("c")]
    # c 出现在根列表
    assert "c" in [n.id for n in g.get_children(None)]


def test_detach_parent_link_not_a_child():
    """非父子关系调用无副作用。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="p", text="P"), parent_id=None)
    g.add_node(NodeData(id="c", text="C"), parent_id="p")
    g.add_node(NodeData(id="x", text="X"), parent_id=None)
    # c 不是 x 的子节点，调用应被拒绝
    g.detach_parent_link("x", "c")
    # c 仍然是 p 的子节点
    assert g.get_node("c").parent_id == "p"
    assert "c" in [n.id for n in g.get_children("p")]


def test_detach_parent_link_keeps_edges():
    """断开父子后，不相关的附加边保留（仅清涉及被切割节点的边）。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="p", text="P"), parent_id=None)
    g.add_node(NodeData(id="c", text="C"), parent_id="p")
    g.add_node(NodeData(id="sibling", text="S"), parent_id="p")
    g.add_node(NodeData(id="gc", text="GC"), parent_id="c")
    # 附加边：p ↔ sibling（与 c 无关）、c ↔ gc（c 涉及）、p ↔ c（树形无关附加）
    g.add_edge("p", "sibling")
    g.add_edge("c", "gc")
    g.add_edge("p", "c")  # 附加边（虽然也是父子关系，但这里测的是图层）
    assert len(g.get_edges()) == 3

    # 仅断开 c 的 parent link（不动其他）
    g.detach_parent_link("p", "c")
    # 三条附加边全保留（detach_parent_link 不动 _edges）
    assert len(g.get_edges()) == 3


def test_detach_parent_link_missing_node_safe():
    """子节点不存在 → 安全无操作。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="p", text="P"), parent_id=None)
    g.detach_parent_link("p", "missing")  # 不报错
    assert g.get_children("p") == []


def test_detach_parent_link_missing_parent_safe():
    """父节点不在 _children 索引里 → 安全无操作。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="c", text="C"), parent_id=None)  # c 是根
    # c 实际不是 missing 的子节点；调用应拒绝（child.parent_id != missing）
    g.detach_parent_link("missing", "c")
    assert g.get_node("c").parent_id is None  # 仍为根


def main() -> int:
    tests = [
        test_detach_parent_link_basic,
        test_detach_parent_link_not_a_child,
        test_detach_parent_link_keeps_edges,
        test_detach_parent_link_missing_node_safe,
        test_detach_parent_link_missing_parent_safe,
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
    print(f"\n{'[ALL PASS]' if failed == 0 else f'[FAIL {failed}/{total}]'} 仅断父子链接回归测试")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
