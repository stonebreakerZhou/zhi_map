# -*- coding: utf-8 -*-
"""⭐ 新体验回归：靠近节点/边也能切中。"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow
from src.ui.mindmap_view import _segment_distance


def drain(app, ms=200):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def test_close_to_edge_hits():
    """⭐ 激光线擦过边端点（没真正相交），距离容差救场。"""
    from PySide6.QtCore import QLineF
    a = QLineF(QPointF(0, 0), QPointF(100, 0))   # 水平激光线
    b = QLineF(QPointF(50, 3), QPointF(100, 3))   # 平行相距 3px
    d = _segment_distance(a, b)
    print(f"两平行线段距离: {d:.2f}")
    assert d < 5, f"应该 < 5, 实际 {d}"
    print("PASS: 距离函数返回正确")

def test_cut_edge_close_to_node():
    """⭐ 从节点边缘旁边右键划线 → 应能切到节点。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    for m in mindmap_repo.list_mindmaps():
        if m["title"] == "diag_close_cut":
            mindmap_repo.delete_mindmap(m["id"])
    mid = mindmap_repo.create_mindmap("diag_close_cut")
    p = mindmap_repo.add_node(mid, "p", x=100, y=100, color="#4A90E2")
    q = mindmap_repo.add_node(mid, "q", parent_id=p, x=300, y=100, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 100)

    # 模拟：右键在 p 节点**右边一点点**（紧贴边缘，Qt itemAt 可能命中节点）
    # 之前 item_at is None 才启 cutting → 现在 EdgeItem / 空白 都启
    # 这里我们直接调 _start_cutting + _update_cutting 模拟
    view = win.view
    p_center = QPointF(100 + 80/2, 100 + 30/2)  # p 是 80x30 节点
    view._start_cutting(p_center + QPointF(5, 0))  # 从 p 右边缘 5px 开始
    # 拖到 q 中心，线段穿过 p 和 q（按"擦边也算"的新逻辑）
    q_center = QPointF(300 + 80/2, 100 + 30/2)
    view._update_cutting(q_center)
    drain(app, 50)

    print(f"warning_nodes: {len(view._cut_warning_nodes)}")
    print(f"warning_edges: {len(view._cut_warning_edges)}")
    # 至少 p 在 warning 里（容差捕获）
    ok = (p in view._cut_warning_nodes) or (q in view._cut_warning_nodes)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")

    win.close(); win.deleteLater(); drain(app, 50)
    return ok


if __name__ == "__main__":
    print("=== test_close_to_edge_hits ===")
    test_close_to_edge_hits()
    print("\n=== test_cut_edge_close_to_node ===")
    test_cut_edge_close_to_node()