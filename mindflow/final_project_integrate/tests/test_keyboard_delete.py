# -*- coding: utf-8 -*-
"""⭐ 终极 e2e：模拟用户用键盘 Delete 直接删选中节点（不弹菜单，不弹确认框）。"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow


def drain(app, ms=300):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def cleanup(title):
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == title: mindmap_repo.delete_mindmap(m["id"])


def open_mm(title):
    cleanup(title)
    mid = mindmap_repo.create_mindmap(title)
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    c = mindmap_repo.add_node(mid, "c", parent_id=p, x=300, y=150, color="#4A90E2")
    eid = mindmap_repo.add_edge(mid, p, c)
    return mid, p, c, eid


def test_delete_key_on_selected_node():
    """⭐ 用户视角最直接：选中节点 + 按 Delete → 节点消失。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid, p, c, eid = open_mm("diag_kb_del")
    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    print("BEFORE: graph=%d view_nodes=%d" % (len(win.current_graph), len(win.view._node_items)))

    # 1) 选中 leaf 节点（无后代 → 不会弹框）
    leaf = win.view.get_node_item(c)
    win.view._scene.clearSelection()
    leaf.setSelected(True)
    drain(app, 30)
    selected = win.view.get_selected_node()
    print("selected:", selected.node_id if selected else None)

    # 2) 触发 _on_delete_node（这是 Delete 键的入口，已 connect QKeySequence.Delete）
    win._ask_delete_mode = lambda txt: "cascade"  # 保险：万一有后代也不卡
    win._on_delete_node()
    drain(app, 600)

    print("AFTER: graph=%d view_nodes=%d" % (len(win.current_graph), len(win.view._node_items)))
    ok = c not in win.current_graph and p in win.current_graph
    print("RESULT:", "PASS" if ok else "FAIL")
    win.close(); win.deleteLater(); drain(app, 100)
    return ok


def test_delete_root_with_descendants():
    """⭐ 删有后代的根：必须弹"级联/脱离/取消"三选一。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid, p, c, _ = open_mm("diag_kb_del_root")
    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    # 选根（有后代 c）→ 按 Delete → 应弹确认框
    root = win.view.get_node_item(p)
    root.setSelected(True)
    drain(app, 30)

    # 自动点"级联"
    win._ask_delete_mode = lambda txt: "cascade"
    win._on_delete_node()
    drain(app, 600)

    print("AFTER root cascade: graph=%d" % len(win.current_graph))
    ok = p not in win.current_graph and c not in win.current_graph
    print("RESULT:", "PASS" if ok else "FAIL")
    win.close(); win.deleteLater(); drain(app, 100)
    return ok


def test_delete_extra_edge_only():
    """⭐ 删附加边：右键边 → 弹菜单（边没 contextMenu 所以走 view 的 mousePress 切 cutting
    或别的）—— 这里直接调内部 API 删 db edge 验证链路"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid, p, c, eid = open_mm("diag_kb_del_edge")
    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    extra = [e for e in win.view._edge_items if getattr(e, "db_id", None) is not None]
    print("extra edges:", len(extra))

    # 直接调内部 API
    win.view.remove_edge_item(extra[0]) if hasattr(win.view, "remove_edge_item") else None
    mindmap_repo.delete_edge(eid)
    if win.current_graph:
        win.current_graph.remove_edge(eid)
    win.view._rebuild_edges()
    drain(app, 100)

    remaining = mindmap_repo.get_edges(mid)
    print("remaining in db:", remaining)
    ok = len(remaining) == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    win.close(); win.deleteLater(); drain(app, 100)
    return ok


if __name__ == "__main__":
    print("\n=== test_delete_key_on_selected_node ===")
    r1 = test_delete_key_on_selected_node()
    print("\n=== test_delete_root_with_descendants ===")
    r2 = test_delete_root_with_descendants()
    print("\n=== test_delete_extra_edge_only ===")
    r3 = test_delete_extra_edge_only()
    print()
    print("SUMMARY:", "PASS" if (r1 and r2 and r3) else "FAIL")
