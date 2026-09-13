"""验证「期末复习计划」结构正确，可被 repo / graph 正确加载。

用法：
    PYTHONIOENCODING=utf-8 python tools/verify_kaoshi_mindmap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# mindmap_repo 内部用 ``from src.X``，所以 path 要放到 final_project/（src/ 父级）
sys.path.insert(0, str(ROOT))

from src.storage import mindmap_repo  # noqa: E402
from src.storage.db import init_db  # noqa: E402


def main() -> None:
    engine = init_db()  # 走默认 URL（MINDFLOW_DB_URL 或 config.ini）

    # 1. 列导图
    mms = mindmap_repo.list_mindmaps()
    print("=== 所有 mindmap ===")
    for m in mms:
        nodes = mindmap_repo.get_nodes(m["id"])
        print(f"  {m['title']}: {len(nodes)} nodes")

    print()

    # 2. 找到 期末复习计划
    target = next((m for m in mms if m["title"] == "期末复习计划"), None)
    assert target, "!!! 找不到 期末复习计划"
    print(f"=== 验证 {target['title']} ===")
    print(f"  id: {target['id']}")
    print(f"  description: {target['description']}")
    print(f"  root_node_id: {target['root_node_id']}")

    nodes = mindmap_repo.get_nodes(target["id"])
    assert len(nodes) == 28, f"!!! 节点数错误：{len(nodes)} != 28"
    root = next(n for n in nodes if n.parent_id is None)
    print(f"  Root: {root.text}")
    print(f"  Root color: {root.color}")

    branches = [n for n in nodes if n.parent_id == root.id]
    leaves = [n for n in nodes if n.parent_id in {b.id for b in branches}]
    print(f"  Branches ({len(branches)}): {[b.text for b in branches]}")
    print(f"  Leaves ({len(leaves)})")
    for b in branches:
        bs = [n for n in leaves if n.parent_id == b.id]
        print(f"    {b.text} ({len(bs)}): {', '.join(n.text for n in bs[:3])}...")
    assert len(branches) == 3
    assert len(leaves) == 24

    # 3. 测加载为 MindMapGraph
    graph = mindmap_repo.load_graph(target["id"])
    print()
    print("=== MindMapGraph ===")
    print(f"  root: {graph.root_id[:8] if graph.root_id else None}")
    print(f"  children of root: {len(graph.get_children(graph.root_id))}")
    # 递归数总节点数（graph 用 parent 指针而非 list 存储）
    total = 0

    def _walk(nid: str) -> None:
        nonlocal total
        total += 1
        for cid in graph.get_children(nid):
            _walk(cid)

    _walk(graph.root_id)
    print(f"  total nodes: {total}")
    assert total == 28, f"!!! graph 节点数 {total} != 28"

    # 4. 测 undo 快照
    snap = mindmap_repo.take_snapshot(target["id"])
    print()
    print("=== Snapshot ===")
    print(f"  nodes: {len(snap.get('nodes', []))}")
    print(f"  edges: {len(snap.get('edges', []))}")
    print(f"  mindmap_id: {snap.get('mindmap_id')}")

    print()
    print("OK ✓")


if __name__ == "__main__":
    main()