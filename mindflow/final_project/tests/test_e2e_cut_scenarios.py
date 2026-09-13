# -*- coding: utf-8 -*-
"""⭐ 划线切割 + 右键删除 端到端关键路径回归。

覆盖 plan 中 1-10 场景的核心断言（场景 11 是 GUI 手动 5min 内存观察）。
offscreen 跑真实 MindMapView + MindFlowWindow。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPointF, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.main_window import MindFlowWindow


def setup_app():
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    for m in mindmap_repo.list_mindmaps():
        if m["title"].startswith("e2e_cut_"):
            mindmap_repo.delete_mindmap(m["id"])
    return app


def _drain_events(app, ms: int = 400):
    """把队列里的 Qt 事件全部处理掉（避免动画/信号悬挂）。"""
    # 跑够时间让 250ms 删除动画结束
    end_at = QTimer()
    end_at.singleShot(ms, lambda: None)
    deadline = ms
    import time
    t0 = time.time()
    while (time.time() - t0) * 1000 < deadline:
        app.processEvents()


def _cleanup_win(win, app):
    """每个场景结束：清 view 状态 + 抽干事件 + 删窗口。"""
    try:
        if win is not None:
            win.view.clear()
            win.close()
            win.deleteLater()
    except Exception:
        pass
    _drain_events(app)


def _make_mid(label: str):
    """p(根) - c1, c2 ; gc 是 c1 的子"""
    mid = mindmap_repo.create_mindmap(f"e2e_cut_{label}")
    p = mindmap_repo.add_node(mid, label, x=100, y=100, color="#4A90E2")
    c1 = mindmap_repo.add_node(mid, f"{label}-c1", parent_id=p, x=300, y=150, color="#4A90E2")
    c2 = mindmap_repo.add_node(mid, f"{label}-c2", parent_id=p, x=300, y=250, color="#4A90E2")
    gc = mindmap_repo.add_node(mid, f"{label}-gc", parent_id=c1, x=500, y=150, color="#4A90E2")
    return mid, p, c1, c2, gc


def _find_edge(v, **kw):
    """根据属性过滤 EdgeItem 列表。"""
    for e in v._edge_items:
        if all(getattr(e, k, None) == val for k, val in kw.items()):
            return e
    return None


def _find_tree_edge_to(v, child_id):
    """找一条 db_id is None 且指向 child_id 的边。"""
    for e in v._edge_items:
        if getattr(e, "db_id", None) is None:
            if getattr(e.target, "node_id", None) == child_id:
                return e
    return None


def scenario1_cut_tree_edge_detach_child_as_new_root(app):
    """场景 1：划线只切到树形边 → child.parent_id=None，child 成新根"""
    mid, p, c1, c2, gc = _make_mid("s1")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    tree_edge = _find_tree_edge_to(v, c1)
    assert tree_edge is not None, "s1 setup FAIL: 没找到 p→c1 的树形边"
    win._on_cut_confirmed(nodes_to_delete=[], edges_to_delete=[tree_edge])
    c1_node = next(n for n in mindmap_repo.get_nodes(mid) if n.id == c1)
    gc_node = next(n for n in mindmap_repo.get_nodes(mid) if n.id == gc)
    assert c1_node.parent_id is None, f"s1 FAIL: c1.parent_id={c1_node.parent_id}"
    assert gc_node.parent_id == c1, f"s1 FAIL: gc.parent_id={gc_node.parent_id}"
    # 拓扑：p-c2 保留 + c1-gc 保留（c1 已 detach 成新根，但 gc 仍挂在 c1 下）
    # 数据层只剩 2 条 parent-child 关系
    remaining_tree = [e for e in v._edge_items if getattr(e, "db_id", None) is None]
    assert len(remaining_tree) == 2, f"s1 FAIL: 树形边应剩 2 (p-c2 + c1-gc), 实际 {len(remaining_tree)}"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario1_cut_tree_edge_detach_child_as_new_root")


def scenario2_cut_extra_edge_only(app):
    """场景 2：划线只切到附加边 → 该边消失"""
    mid, p, c1, c2, gc = _make_mid("s2")
    eid = mindmap_repo.add_edge(mid, c1, c2)
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    extra_edge = _find_edge(v, db_id=eid)
    assert extra_edge is not None, "s2 setup FAIL: 没找到附加边 EdgeItem"
    initial = len(v._edge_items)
    win._on_cut_confirmed(nodes_to_delete=[], edges_to_delete=[extra_edge])
    remaining = [e for e in mindmap_repo.get_edges(mid) if e["id"] == eid]
    assert len(remaining) == 0, f"s2 FAIL: 附加边未删 db={remaining}"
    assert len(v._edge_items) == initial - 1, f"s2 FAIL: view {initial} → {len(v._edge_items)}"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario2_cut_extra_edge_only")


def scenario3_cut_tree_plus_extra(app):
    """场景 3：同时切树形 + 附加 → 都消失"""
    mid, p, c1, c2, gc = _make_mid("s3")
    eid = mindmap_repo.add_edge(mid, c1, c2)
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    tree_edge = _find_tree_edge_to(v, c1)
    extra_edge = _find_edge(v, db_id=eid)
    win._on_cut_confirmed(nodes_to_delete=[], edges_to_delete=[tree_edge, extra_edge])
    c1_node = next(n for n in mindmap_repo.get_nodes(mid) if n.id == c1)
    assert c1_node.parent_id is None, "s3 FAIL: c1 未 detach"
    assert len([e for e in mindmap_repo.get_edges(mid) if e["id"] == eid]) == 0, "s3 FAIL: 附加边未删"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario3_cut_tree_plus_extra")


def scenario4_cut_node_only_keeps_descendants(app):
    """场景 4：切节点 → 节点删，后代保留"""
    mid, p, c1, c2, gc = _make_mid("s4")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    c1_item = v._node_items[c1]
    win._on_cut_confirmed(nodes_to_delete=[c1_item], edges_to_delete=[])
    c1_db = next((n for n in mindmap_repo.get_nodes(mid) if n.id == c1), None)
    assert c1_db is None, "s4 FAIL: c1 应已 detach 删"
    gc_db = next(n for n in mindmap_repo.get_nodes(mid) if n.id == gc)
    # detach_node 把 c1 的直接子 (gc) parent_id 改 None
    assert gc_db.parent_id is None, f"s4 FAIL: gc.parent_id={gc_db.parent_id}, 应为 None"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario4_cut_node_only_keeps_descendants")


def scenario5_cut_node_plus_edges_no_animation_crash(app):
    """场景 5：切节点 + 边（验证不撞动画）"""
    mid, p, c1, c2, gc = _make_mid("s5")
    eid = mindmap_repo.add_edge(mid, c1, c2)
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    c1_item = v._node_items[c1]
    extra_edge = _find_edge(v, db_id=eid)
    win._on_cut_confirmed(nodes_to_delete=[c1_item], edges_to_delete=[extra_edge])
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario5_cut_node_plus_edges_no_animation_crash")


def scenario6_leave_event_finishes_cut(app):
    """场景 6：leaveEvent → _is_cutting 被清掉"""
    mid = mindmap_repo.create_mindmap("e2e_cut_s6")
    p = mindmap_repo.add_node(mid, "p", x=0, y=0, color="#4A90E2")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    v._is_cutting = True
    v._cut_start = QPointF(0, 0)
    v._cut_current = QPointF(50, 50)
    v._cut_warning_nodes = {v._node_items[p]}
    # leaveEvent 接受 QEvent
    v.leaveEvent(QEvent(QEvent.Leave))
    assert not v._is_cutting, "s6 FAIL: leaveEvent 未清切割态"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario6_leave_event_finishes_cut")


def scenario7_right_click_delete_no_children(app):
    """场景 7：右键删无子节点 → 直接级联删（无差别，UI 无弹窗）"""
    mid = mindmap_repo.create_mindmap("e2e_cut_s7")
    p = mindmap_repo.add_node(mid, "root", x=0, y=0, color="#4A90E2")
    leaf = mindmap_repo.add_node(mid, "leaf", parent_id=p, x=200, y=200, color="#4A90E2")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    leaf_item = v._node_items[leaf]
    win._delete_node_item(leaf_item)
    # DB 立刻删了
    assert next((n for n in mindmap_repo.get_nodes(mid) if n.id == leaf), None) is None, (
        "s7 FAIL: leaf DB 未删"
    )
    # view 端走动画，drain events 等动画结束
    _drain_events(app, ms=400)
    assert leaf not in v._node_items, "s7 FAIL: leaf_item 未从 view 移除"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario7_right_click_delete_no_children")


def scenario8_right_click_delete_with_children_detach(app):
    """场景 8：右键删有子节点 → 走 detach 路径"""
    mid, p, c1, c2, gc = _make_mid("s8")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    p_item = v._node_items[p]
    win._ask_delete_mode = lambda text: "detach"  # 绕过弹窗
    win._delete_node_item(p_item)
    p_db = next((n for n in mindmap_repo.get_nodes(mid) if n.id == p), None)
    assert p_db is None, "s8 FAIL: p 未 detach 删"
    remaining = {n.id for n in mindmap_repo.get_nodes(mid)}
    assert remaining == {c1, c2, gc}, f"s8 FAIL: 残留={remaining}"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario8_right_click_delete_with_children_detach")


def scenario9_create_node_via_signal(app):
    """场景 9（回归）：双击空白 → 节点创建（直接调下层方法，绕过 QInputDialog）"""
    mid = mindmap_repo.create_mindmap("e2e_cut_s9")
    p = mindmap_repo.add_node(mid, "root", x=200, y=200, color="#4A90E2")
    win = MindFlowWindow()
    win._open_mindmap(mid)
    v = win.view
    initial = len(mindmap_repo.get_nodes(mid))
    # 验证 signal handler 入口能调通——用 monkey patch 绕开 QInputDialog 模态
    orig_handler = win._on_create_node_at
    def fake_handler(x, y):
        win._create_node_no_parent("新测试节点", x, y)
    win._on_create_node_at = fake_handler
    v.node_create_at_requested.emit(400.0, 400.0)
    win._on_create_node_at = orig_handler
    after = len(mindmap_repo.get_nodes(mid))
    assert after == initial + 1, f"s9 FAIL: {initial} → {after}"
    mindmap_repo.delete_mindmap(mid)
    print("  [OK] scenario9_create_node_via_signal")


def scenario10_clear_full_cleanup_on_switch(app):
    """场景 10：清空 view 后再加载另一个 → 不崩"""
    mid1 = mindmap_repo.create_mindmap("e2e_cut_s10a")
    p1 = mindmap_repo.add_node(mid1, "p1", x=0, y=0, color="#4A90E2")
    win = MindFlowWindow()
    win._open_mindmap(mid1)
    win.view._is_cutting = True
    win.view._is_connecting = True
    mid2 = mindmap_repo.create_mindmap("e2e_cut_s10b")
    p2 = mindmap_repo.add_node(mid2, "p2", x=100, y=100, color="#4A90E2")
    win._open_mindmap(mid2)
    assert not win.view._is_cutting, "s10 FAIL: clear 未清 _is_cutting"
    assert not win.view._is_connecting, "s10 FAIL: clear 未清 _is_connecting"
    assert len(win.view._node_items) == 1, "s10 FAIL: 切换后节点数不对"
    mindmap_repo.delete_mindmap(mid1)
    mindmap_repo.delete_mindmap(mid2)
    print("  [OK] scenario10_clear_full_cleanup_on_switch")


def main() -> int:
    app = setup_app()
    fns = [
        scenario1_cut_tree_edge_detach_child_as_new_root,
        scenario2_cut_extra_edge_only,
        scenario3_cut_tree_plus_extra,
        scenario4_cut_node_only_keeps_descendants,
        scenario5_cut_node_plus_edges_no_animation_crash,
        scenario6_leave_event_finishes_cut,
        scenario7_right_click_delete_no_children,
        scenario8_right_click_delete_with_children_detach,
        scenario9_create_node_via_signal,
        scenario10_clear_full_cleanup_on_switch,
    ]
    failed = 0
    for fn in fns:
        try:
            fn(app)
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  [ERROR] {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            # 每个场景结束抽干所有 Qt 事件 + 关掉残留窗口
            for w in app.topLevelWidgets():
                try:
                    w.close()
                    w.deleteLater()
                except Exception:
                    pass
            _drain_events(app)
            # 清残留 mindmap
            for m in mindmap_repo.list_mindmaps():
                if m["title"].startswith("e2e_cut_"):
                    mindmap_repo.delete_mindmap(m["id"])
    total = len(fns)
    print(f"\n{'[ALL PASS]' if failed == 0 else f'[FAIL {failed}/{total}]'} 划线切割端到端关键路径")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
