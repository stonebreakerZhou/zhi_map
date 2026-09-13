# -*- coding: utf-8 -*-
"""⭐ 任意两节点互连（EdgeData / MindMapGraph.add_edge）回归测试。

测试目标：
1. add_edge / remove_edge / get_edges / has_edge 语义正确
2. 自环拒绝
3. 重复边拒绝（不论方向 A→B / B→A）
4. 删节点时级联清附加边
5. detach_node 不影响无关附加边（仅清理涉及被切割节点本身的边）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mindmap.graph import EdgeData, MindMapGraph
from src.mindmap.node import NodeData


def test_edge_data_dataclass():
    """EdgeData 是简单数据类。"""
    e = EdgeData(id=42, source_id="a", target_id="b")
    assert e.id == 42
    assert e.source_id == "a"
    assert e.target_id == "b"


def test_add_edge_basic():
    """基本加边：返回单调递增的 id。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    g.add_node(NodeData(id="b", text="B"), parent_id=None)
    g.add_node(NodeData(id="c", text="C"), parent_id=None)
    eid1 = g.add_edge("a", "b")
    eid2 = g.add_edge("a", "c")  # 不同 pair 允许
    eid3 = g.add_edge("b", "c")  # 又一个不同 pair
    assert eid1 is not None and eid2 is not None and eid3 is not None
    assert eid1 != eid2 != eid3


def test_add_edge_self_loop_rejected():
    """自环拒绝。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    assert g.add_edge("a", "a") is None


def test_add_edge_duplicate_rejected():
    """重复边拒绝（不论方向）。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    g.add_node(NodeData(id="b", text="B"), parent_id=None)
    assert g.add_edge("a", "b") == 1
    # 重复（不论方向）
    assert g.add_edge("a", "b") is None
    assert g.add_edge("b", "a") is None


def test_add_edge_nonexistent_node_rejected():
    """不存在的节点拒绝。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    assert g.add_edge("a", "missing") is None
    assert g.add_edge("missing", "a") is None


def test_has_edge_bidirectional():
    """has_edge 双向都识别。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    g.add_node(NodeData(id="b", text="B"), parent_id=None)
    g.add_edge("a", "b")
    assert g.has_edge("a", "b") is True
    assert g.has_edge("b", "a") is True
    assert g.has_edge("a", "a") is False
    assert g.has_edge("a", "missing") is False


def test_remove_edge_then_readd():
    """删边后能重新加同对边。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    g.add_node(NodeData(id="b", text="B"), parent_id=None)
    eid = g.add_edge("a", "b")
    assert eid is not None
    g.remove_edge(eid)
    assert g.has_edge("a", "b") is False
    new_eid = g.add_edge("a", "b")
    assert new_eid is not None
    assert new_eid != eid  # 新 id


def test_remove_edge_missing_id_safe():
    """删不存在的 edge_id 不抛异常。"""
    g = MindMapGraph()
    g.remove_edge(999)  # 不报错
    assert g.get_edges() == []


def test_remove_node_purges_edges():
    """⭐ 删节点时级联清涉及该节点的附加边。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="r", text="R"), parent_id=None)
    g.add_node(NodeData(id="a", text="A"), parent_id=None)
    g.add_node(NodeData(id="b", text="B"), parent_id=None)
    g.add_node(NodeData(id="c", text="C"), parent_id=None)
    g.add_edge("r", "a")
    g.add_edge("r", "b")
    g.add_edge("a", "b")
    g.add_edge("a", "c")
    assert len(g.get_edges()) == 4

    g.remove_node("a")  # 级联删 a, 同时清涉及 a 的所有边
    # 剩余：r-b 还在（a 不在）；其他都涉及 a，应被清
    assert len(g.get_edges()) == 1
    edges = g.get_edges()
    assert (edges[0].source_id, edges[0].target_id) in (("r", "b"), ("b", "r"))


def test_detach_node_keeps_unrelated_edges():
    """⭐ detach_node 不影响无关附加边（仅清涉及被切割节点的边）。"""
    g = MindMapGraph()
    g.add_node(NodeData(id="r", text="R"), parent_id=None)
    g.add_node(NodeData(id="m", text="M"), parent_id="r")
    g.add_node(NodeData(id="c1", text="C1"), parent_id="m")
    g.add_edge("r", "c1")  # 涉及被切割节点的后代（c1），应保留（r 和 c1 都还活着）
    g.add_edge("r", "m")   # 涉及被切割节点（m），应被清
    assert len(g.get_edges()) == 2

    g.detach_node("m")
    # m 被清；r→c1 保留（r 和 c1 都还活着）
    remaining = [(e.source_id, e.target_id) for e in g.get_edges()]
    assert len(remaining) == 1
    assert remaining[0] in (("r", "c1"), ("c1", "r"))


def test_load_graph_preserves_edges():
    """load_graph 从 DB 加载附加边到 graph。"""
    from src.storage import mindmap_repo
    from src.storage.db import init_db

    init_db()
    mm_id = mindmap_repo.create_mindmap("edge_test")
    n1 = mindmap_repo.add_node(mm_id, "n1", parent_id=None, x=0, y=0)
    n2 = mindmap_repo.add_node(mm_id, "n2", parent_id=None, x=100, y=0)
    eid = mindmap_repo.add_edge(mm_id, n1, n2)
    assert eid is not None

    g = mindmap_repo.load_graph(mm_id)
    edges = g.get_edges()
    assert len(edges) == 1
    pair = (edges[0].source_id, edges[0].target_id)
    assert pair in ((n1, n2), (n2, n1))


def main() -> int:
    tests = [
        test_edge_data_dataclass,
        test_add_edge_basic,
        test_add_edge_self_loop_rejected,
        test_add_edge_duplicate_rejected,
        test_add_edge_nonexistent_node_rejected,
        test_has_edge_bidirectional,
        test_remove_edge_then_readd,
        test_remove_edge_missing_id_safe,
        test_remove_node_purges_edges,
        test_detach_node_keeps_unrelated_edges,
        test_load_graph_preserves_edges,
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
    print(f"\n{'[ALL PASS]' if failed == 0 else f'[FAIL {failed}/{total}]'} 任意两节点互连回归测试")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
