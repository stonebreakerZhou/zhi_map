# -*- coding: utf-8 -*-
"""模拟真实 user 操作：右键 NodeItem → 弹 QMenu → 触发删除 action → 走完整流程。"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication, QMenu, QGraphicsSceneContextMenuEvent
from PySide6.QtGui import QContextMenuEvent

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow


def drain(app, ms=300):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def test_user_scenario_real_contextmenu():
    """⭐ 真实模拟：NodeItem.contextMenuEvent 接收 QGraphicsSceneContextMenuEvent。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    mid = mindmap_repo.create_mindmap("diag_real_ctx")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    leaf = win.view.get_node_item(p)
    assert leaf is not None

    # 拦截 QMenu.exec_（PySide6 实际是 exec_）：模拟点"删除节点"
    from PySide6.QtCore import QEvent
    captured_menu = []
    real_exec = getattr(QMenu, "exec_", None) or QMenu.exec
    def fake_exec(self_menu, *args, **kw):
        captured_menu.append([a.text() for a in self_menu.actions()])
        # 找删除 action 触发
        for a in self_menu.actions():
            if "删除" in a.text():
                a.trigger()
                return a
        return None
    QMenu.exec_ = fake_exec
    QMenu.exec = fake_exec
    win._ask_delete_mode = lambda txt: "cascade"

    # ⭐ 真实构造 QGraphicsSceneContextMenuEvent（Qt 会识别 event 类型）
    scene_pos = QPointF(leaf.pos().x() + leaf.width/2, leaf.pos().y() + leaf.height/2)
    screen_pos = leaf.mapToScene(scene_pos)
    # screenPos in widget coords for menu.exec
    view_widget_pos = win.view.mapFromScene(screen_pos)
    global_pos = win.view.mapToGlobal(view_widget_pos)

    event = QGraphicsSceneContextMenuEvent(QEvent.ContextMenu)
    event.setScenePos(screen_pos)
    event.setScreenPos(global_pos)
    event.setPos(leaf.mapFromScene(screen_pos))
    # 触发 NodeItem.contextMenuEvent
    leaf.contextMenuEvent(event)

    drain(app, 600)

    QMenu.exec = real_exec
    if hasattr(QMenu, "exec_"):
        QMenu.exec_ = real_exec

    print("captured_menu:", captured_menu)
    print("BEFORE: graph=%d" % len(win.current_graph))
    print("AFTER: graph=%d view_nodes=%d" % (len(win.current_graph), len(win.view._node_items)))
    ok = p not in win.current_graph
    print("RESULT:", "PASS" if ok else "FAIL")

    win.close(); win.deleteLater(); drain(app, 100)
    return ok


if __name__ == "__main__":
    test_user_scenario_real_contextmenu()
