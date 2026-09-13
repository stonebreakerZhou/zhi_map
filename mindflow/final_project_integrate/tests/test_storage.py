# -*- coding: utf-8 -*-
"""数据层单元测试。

测试覆盖：
- MindMap CRUD
- Node CRUD（创建、读取、更新位置、删除）
- load_graph（图加载）
- 持久化（关→开 数据还在）

运行：python -m pytest tests/test_storage.py -v
或者：python tests/test_storage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让测试能 import src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage import db, mindmap_repo
from src.storage.db import init_db, reset_db, session_scope
from src.storage.schema import Node as NodeModel


def setup_test_db() -> None:
    """重置测试数据库。"""
    reset_db()
    init_db()


def test_mindmap_crud() -> bool:
    """测试 MindMap CRUD 全流程。"""
    setup_test_db()
    # Create
    mid = mindmap_repo.create_mindmap("Python 装饰器", "学习装饰器")
    assert mid, "创建导图失败"

    # List
    maps = mindmap_repo.list_mindmaps()
    assert len(maps) == 1, f"应有 1 个导图，实际 {len(maps)}"
    assert maps[0]["title"] == "Python 装饰器"

    # Get
    m = mindmap_repo.get_mindmap(mid)
    assert m is not None
    assert m["title"] == "Python 装饰器"

    # Update title
    mindmap_repo.update_mindmap_title(mid, "装饰器学习笔记")
    m = mindmap_repo.get_mindmap(mid)
    assert m["title"] == "装饰器学习笔记"

    # Delete
    mindmap_repo.delete_mindmap(mid)
    maps = mindmap_repo.list_mindmaps()
    assert len(maps) == 0, "删除后应为空"

    print("[OK] test_mindmap_crud")
    return True


def test_node_crud() -> bool:
    """测试 Node CRUD。"""
    setup_test_db()
    mid = mindmap_repo.create_mindmap("测试导图")

    # 添加根节点
    root_id = mindmap_repo.add_node(mid, "根节点", x=100, y=100)
    assert root_id

    # 添加子节点
    child_id = mindmap_repo.add_node(mid, "子节点1", parent_id=root_id, x=300, y=100)
    grand_id = mindmap_repo.add_node(mid, "孙节点", parent_id=child_id, x=500, y=100)

    # 验证根节点自动设置
    m = mindmap_repo.get_mindmap(mid)
    assert m["root_node_id"] == root_id, f"根节点应自动设为 {root_id[:8]}，实际 {m['root_node_id'][:8] if m['root_node_id'] else None}"

    # 读取所有节点
    nodes = mindmap_repo.get_nodes(mid)
    assert len(nodes) == 3, f"应有 3 个节点，实际 {len(nodes)}"

    # 更新文本
    mindmap_repo.update_node_text(child_id, "子节点（修改后）")
    nodes = mindmap_repo.get_nodes(mid)
    child = next(n for n in nodes if n.id == child_id)
    assert child.text == "子节点（修改后）"

    # 更新位置
    mindmap_repo.update_node_position(grand_id, 999.0, 888.0)
    nodes = mindmap_repo.get_nodes(mid)
    grand = next(n for n in nodes if n.id == grand_id)
    assert grand.pos_x == 999.0 and grand.pos_y == 888.0

    # 删除子树（删 child 应该级联删除 grand）
    mindmap_repo.delete_node(child_id)
    nodes = mindmap_repo.get_nodes(mid)
    assert len(nodes) == 1, f"删除 child 应级联删除 grand，剩 1 个，实际 {len(nodes)}"

    print("[OK] test_node_crud")
    return True


def test_persistence() -> bool:
    """测试持久化：关闭连接再打开数据还在。"""
    setup_test_db()
    mid = mindmap_repo.create_mindmap("持久化测试")
    mindmap_repo.add_node(mid, "节点 A", x=10, y=20)
    mindmap_repo.add_node(mid, "节点 B", x=30, y=40)

    # 模拟关闭+重新打开：重置 engine 缓存，重新 init
    db._engine = None
    db._SessionLocal = None

    # 重新读取
    maps = mindmap_repo.list_mindmaps()
    assert len(maps) == 1, "重新打开后导图应还在"
    nodes = mindmap_repo.get_nodes(mid)
    assert len(nodes) == 2, "重新打开后节点应还在"

    print("[OK] test_persistence")
    return True


def test_load_graph() -> bool:
    """测试图加载。"""
    setup_test_db()
    mid = mindmap_repo.create_mindmap("图测试")
    root = mindmap_repo.add_node(mid, "根")
    c1 = mindmap_repo.add_node(mid, "子1", parent_id=root)
    c2 = mindmap_repo.add_node(mid, "子2", parent_id=root)
    g1 = mindmap_repo.add_node(mid, "孙1", parent_id=c1)

    graph = mindmap_repo.load_graph(mid)
    assert graph.node_count == 4, f"应有 4 节点，实际 {graph.node_count}"
    assert graph.root_id == root

    # DFS 顺序
    dfs_order = graph.dfs()
    assert len(dfs_order) == 4
    assert dfs_order[0].id == root

    # 子节点
    children = graph.get_children(root)
    assert len(children) == 2

    print("[OK] test_load_graph")
    return True


def main() -> int:
    """运行所有测试。"""
    print("=" * 50)
    print("数据层测试")
    print("=" * 50)
    try:
        test_mindmap_crud()
        test_node_crud()
        test_persistence()
        test_load_graph()
        print()
        print("🎉 所有测试通过！")
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
