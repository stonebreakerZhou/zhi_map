# -*- coding: utf-8 -*-
"""实测 GUI 实际删除路径（跳过 QMessageBox 直接调内部 API）。"""
from __future__ import annotations

import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow


def drain(app, ms=500):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def test_right_click_delete_cascade():
    """右键删除无后代节点 → 应立即级联删除。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == "diag_rc_del": mindmap_repo.delete_mindmap(m["id"])
    mid = mindmap_repo.create_mindmap("diag_rc_del")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    c = mindmap_repo.add_node(mid, "c", parent_id=p, x=300, y=150, color="#4A90E2")
    mindmap_repo.add_edge(mid, p, c)  # ⭐ 附加边

    win = MindFlowWindow()
    drain(app, 50)
    win._open_mindmap(mid)
    drain(app, 100)

    print("=== before delete ===")
    print(" graph:", len(win.current_graph), "view nodes:", len(win.view._node_items), "view edges:", len(win.view._edge_items))

    # 选 leaf 节点（无后代）→ 弹窗会跳过直接级联
    leaf = win.view.get_node_item(c)
    if leaf is None:
        print("FAIL: leaf not in view")
        return False
    desc = [n.id for n in win.current_graph.get_descendants(c)]
    print(" leaf descendants:", desc)

    # monkeypatch _ask_delete_mode → 跳过弹窗
    win._ask_delete_mode = lambda txt: "cascade"

    # 触发右键删除
    from src.ui.node_item import NodeItem
    NodeItem.delete_requested(leaf)
    drain(app, 800)  # 等动画

    print("=== after delete ===")
    print(" graph:", len(win.current_graph), "view nodes:", len(win.view._node_items), "view edges:", len(win.view._edge_items))
    print(" p in graph:", p in win.current_graph, "c in graph:", c in win.current_graph)
    extra_after = [e for e in win.view._edge_items if getattr(e, "db_id", None) is not None]
    print(" extra edges remaining:", len(extra_after))

    ok = (c not in win.current_graph) and (p in win.current_graph) and len(extra_after) == 0
    print(" RESULT:", "PASS" if ok else "FAIL")

    win.close()
    win.deleteLater()
    drain(app, 100)
    return ok


def test_cut_extra_edge():
    """划线只切附加边 → 该边消失。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == "diag_cut_extra": mindmap_repo.delete_mindmap(m["id"])
    mid = mindmap_repo.create_mindmap("diag_cut_extra")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    q = mindmap_repo.add_node(mid, "q", x=500, y=300, color="#4A90E2")
    eid = mindmap_repo.add_edge(mid, p, q)
    print("edge id in db:", eid)

    win = MindFlowWindow()
    drain(app, 50)
    win._open_mindmap(mid)
    drain(app, 100)

    print(" view edges:", len(win.view._edge_items))
    extra = [e for e in win.view._edge_items if getattr(e, "db_id", None) is not None]
    print(" extra edges in view:", len(extra))

    if not extra:
        print("FAIL: no extra edge in view")
        win.close(); return False

    target_edge = extra[0]

    # 直接调 _on_cut_confirmed 走内部 API（不模拟划线轨迹）
    win._on_cut_confirmed(nodes_to_delete=[], edges_to_delete=[target_edge])
    drain(app, 800)

    extra_after = [e for e in win.view._edge_items if getattr(e, "db_id", None) is not None]
    print(" extra edges after cut:", len(extra_after))
    remaining = mindmap_repo.get_edges(mid)
    in_db = any(e.get("id") == eid for e in remaining)
    print(" edge still in db:", in_db)

    ok = len(extra_after) == 0
    print(" RESULT:", "PASS" if ok else "FAIL")

    win.close(); win.deleteLater()
    drain(app, 100)
    return ok


def test_cut_tree_edge():
    """划线只切树形边 → 该边消失，子脱离为新根。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == "diag_cut_tree": mindmap_repo.delete_mindmap(m["id"])
    mid = mindmap_repo.create_mindmap("diag_cut_tree")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    c = mindmap_repo.add_node(mid, "c", parent_id=p, x=300, y=150, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 50)
    win._open_mindmap(mid)
    drain(app, 100)

    tree_edges = [e for e in win.view._edge_items if getattr(e, "db_id", None) is None]
    print(" tree edges:", len(tree_edges))
    if not tree_edges:
        print("FAIL: no tree edge")
        win.close(); return False

    win._on_cut_confirmed(nodes_to_delete=[], edges_to_delete=tree_edges)
    drain(app, 200)

    c_node = win.current_graph.get_node(c)
    tree_after = [e for e in win.view._edge_items if getattr(e, "db_id", None) is None]
    print(" after: c.parent_id =", c_node.parent_id if c_node else None)
    print(" tree edges after:", len(tree_after))

    ok = (c_node is not None) and (c_node.parent_id is None) and (len(tree_after) == 0)
    print(" RESULT:", "PASS" if ok else "FAIL")

    win.close(); win.deleteLater()
    drain(app, 100)
    return ok


if __name__ == "__main__":
    print("\n############ right-click delete leaf ############")
    r1 = test_right_click_delete_cascade()
    print("\n############ cut extra edge only ############")
    r2 = test_cut_extra_edge()
    print("\n############ cut tree edge only ############")
    r3 = test_cut_tree_edge()
    print()
    print("SUMMARY:", "PASS" if (r1 and r2 and r3) else "FAIL", f"(rc={r1}, extra={r2}, tree={r3})")
    sys.exit(0 if (r1 and r2 and r3) else 1)
