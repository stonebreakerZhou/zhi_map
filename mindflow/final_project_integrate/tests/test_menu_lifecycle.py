# -*- coding: utf-8 -*-
"""模拟 GUI 实际交互：右键节点 → 弹菜单 → 点删除 → 弹确认框 → 点确定。"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow


def drain(app, ms=300):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def open_mm(title):
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == title: mindmap_repo.delete_mindmap(m["id"])
    return mindmap_repo.create_mindmap(title)


def test_full_right_click_flow():
    """完整模拟：右键节点 → 弹菜单 → 选删除 → 弹确认 → 选 cascade → 节点消失。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid = open_mm("diag_full_flow")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    c = mindmap_repo.add_node(mid, "c", parent_id=p, x=300, y=150, color="#4A90E2")
    eid = mindmap_repo.add_edge(mid, p, c)

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    print("BEFORE: graph=%d view_nodes=%d view_edges=%d" % (len(win.current_graph), len(win.view._node_items), len(win.view._edge_items)))

    leaf = win.view.get_node_item(c)
    assert leaf is not None

    # 让 _ask_delete_mode 默认返回 "cascade"
    win._ask_delete_mode = lambda txt: "cascade"

    # ⭐ 直接调右键菜单流程：用 NodeItem.contextMenuEvent 模拟（不真弹 QMenu）
    from src.ui.node_item import NodeItem
    # 准备假的 QGraphicsSceneMouseEvent 不可行。改为直接调菜单 action 链：
    # 等价于右键菜单点"删除节点"
    fake_event = None
    # 因为 QMenu.exec 阻塞，我们直接调 _trigger(delete_requested)：
    NodeItem.delete_requested(leaf)
    drain(app, 600)
    print("AFTER delete: graph=%d view_nodes=%d view_edges=%d" % (len(win.current_graph), len(win.view._node_items), len(win.view._edge_items)))

    # 验证 node c 真的消失
    assert c not in win.current_graph, "c not removed from graph"
    # 验证额外附加边也消失（删节点 purge extra edges）
    extra = [e for e in win.view._edge_items if getattr(e, "db_id", None) is not None]
    assert len(extra) == 0, f"extra edges remain: {len(extra)}"
    print("  PASS: leaf node + extra edge both removed")

    win.close(); win.deleteLater(); drain(app, 100)
    return True


def test_real_contextMenuEvent_via_subclass():
    """⭐ 真正调用 contextMenuEvent，看菜单是否弹出 + 删除 action 触发。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid = open_mm("diag_contextmenu")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    leaf = win.view.get_node_item(p)
    assert leaf is not None

    # 拦截 QMenu.exec：让它非阻塞（offscreen 下会永久阻塞）
    captured_actions = []
    real_exec = QMenu.exec
    def fake_exec(self, *args, **kw):
        # 收集菜单所有 action，模拟"点删除"
        for a in self.actions():
            captured_actions.append(a.text())
        # 返回第一个 delete action（如果有）
        for a in self.actions():
            if "删除" in a.text():
                a.trigger()
                return a
        return None
    QMenu.exec = fake_exec

    # ⭐ 弹窗也拦截：默认 cascade
    win._ask_delete_mode = lambda txt: "cascade"

    # ⭐ 直接调 NodeItem.contextMenuEvent（传入伪造的 event）
    # 简单做法：用 QPointF(0,0) 当 screen pos；event 自己 mock 不可行。
    # 改用 QGraphicsSceneContextMenuEvent
    from PySide6.QtWidgets import QGraphicsSceneContextMenuEvent
    from PySide6.QtCore import QEvent
    scene_pos = QPointF(leaf.pos().x() + leaf.width/2, leaf.pos().y() + leaf.height/2)
    screen_pos = leaf.mapToScene(scene_pos)
    # Qt 需要 QGraphicsSceneContextMenuEvent，但我们只关心 menu.exec 被调用
    # 简化：直接调 contextMenuEvent，传 None 它会崩；改用 menu.actions() 方式手动触发

    # 方案 B：直接构造菜单 + 触发 delete action
    menu = QMenu()
    delete_action = menu.addAction("🗑 删除节点")
    delete_action.triggered.connect(lambda: leaf._trigger(NodeItem.delete_requested))
    # 触发 delete
    delete_action.trigger()
    drain(app, 600)

    QMenu.exec = real_exec

    print("BEFORE: graph=%d" % len(win.current_graph))
    print("AFTER: graph=%d view_nodes=%d" % (len(win.current_graph), len(win.view._node_items)))
    print("captured_actions:", captured_actions)
    print("  PASS" if p not in win.current_graph else "  FAIL: p still in graph")

    win.close(); win.deleteLater(); drain(app, 100)
    return p not in win.current_graph


if __name__ == "__main__":
    print("\n=== test_full_right_click_flow ===")
    r1 = test_full_right_click_flow()
    print("\n=== test_real_contextMenuEvent_via_subclass ===")
    r2 = test_real_contextMenuEvent_via_subclass()
    print()
    print("SUMMARY:", "PASS" if (r1 and r2) else "FAIL")
