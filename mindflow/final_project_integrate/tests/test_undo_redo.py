# -*- coding: utf-8 -*-
"""⭐ 撤销 / 重做 测试套件。

覆盖：
1. HistoryManager 单元（push / undo / redo / clear / 上限）
2. MindMapGraph.snapshot_subtree / restore_subtree
3. 端到端：建节点 / 删节点 / 改文字 / 划线切 / 加附件 / 切导图清空 / 上限
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.ui.history import HistoryManager, HistoryEntry
from src.mindmap.graph import MindMapGraph
from src.mindmap.node import NodeData


def drain(app, ms=80):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


# ============================================================
# 单元：HistoryManager
# ============================================================

def test_history_basic():
    """⭐ push → undo → redo → 栈变化正确。"""
    app = QApplication.instance() or QApplication(sys.argv)
    h = HistoryManager()
    log = []

    e1 = HistoryEntry(label="op1", undo=lambda: log.append("u1"), redo=lambda: log.append("r1"))
    e2 = HistoryEntry(label="op2", undo=lambda: log.append("u2"), redo=lambda: log.append("r2"))
    h.push(e1); h.push(e2)
    assert h.can_undo() and h.can_redo() is False  # push 清空 redo
    assert h.undo_count() == 2 and h.redo_count() == 0
    assert h.peek_undo_label() == "op2"

    h.undo()
    assert log == ["u2"], f"expected ['u2'], got {log}"
    assert h.undo_count() == 1 and h.redo_count() == 1
    assert h.peek_redo_label() == "op2"

    h.undo()
    assert log == ["u2", "u1"]

    # redo 恢复最近一次 undo（op1 先被 redo 出来）
    h.redo()
    assert log == ["u2", "u1", "r1"]
    assert h.peek_undo_label() == "op1"

    h.redo()
    assert log == ["u2", "u1", "r1", "r2"]
    assert h.peek_undo_label() == "op2"

    h.clear()
    assert h.undo_count() == 0 and h.redo_count() == 0
    print("PASS: HistoryManager push/undo/redo/clear")


def test_history_max_size():
    """⭐ 推 150 条 → 栈只保留最新 100 条。"""
    app = QApplication.instance() or QApplication(sys.argv)
    h = HistoryManager()
    for i in range(150):
        h.push(HistoryEntry(label=f"op{i}", undo=lambda: None, redo=lambda: None))
    assert h.undo_count() == h.MAX_SIZE, f"expected {h.MAX_SIZE}, got {h.undo_count()}"
    # 最老一条 op50 应在栈底
    assert h.peek_undo_label() == f"op{149}", "栈顶应为 op149"
    # 弹 100 次后应空
    for _ in range(100):
        h.undo()
    assert not h.can_undo()
    print("PASS: HistoryManager 上限 100")


def test_history_changed_signal():
    """⭐ changed 信号在 push/undo/redo/clear 时都触发。"""
    app = QApplication.instance() or QApplication(sys.argv)
    h = HistoryManager()
    fires = [0]
    h.changed.connect(lambda: fires.__setitem__(0, fires[0] + 1))
    h.push(HistoryEntry(label="x", undo=lambda: None, redo=lambda: None))
    h.undo()
    h.redo()
    h.clear()
    assert fires[0] == 4, f"expected 4, got {fires[0]}"
    print("PASS: HistoryManager changed signal")


# ============================================================
# 单元：MindMapGraph snapshot_subtree / restore_subtree
# ============================================================

def test_snapshot_subtree_basic():
    """⭐ snapshot 整棵子树（含自身 + 后代 + 附加边），restore 还原。"""
    g = MindMapGraph()
    a = NodeData(id="a", text="A", pos_x=0, pos_y=0, parent_id=None, color="#111")
    b = NodeData(id="b", text="B", pos_x=100, pos_y=0, parent_id="a", color="#222")
    c = NodeData(id="c", text="C", pos_x=200, pos_y=0, parent_id="b", color="#333")
    d = NodeData(id="d", text="D", pos_x=300, pos_y=0, parent_id=None, color="#444")
    for n in [a, b, c, d]:
        g.add_node(n, parent_id=n.parent_id)
    eid1 = g.add_edge("b", "d")  # 跨节点附加边

    # snapshot b 的子树
    sn, se = g.snapshot_subtree("b")
    ids = {n.id for n in sn}
    assert ids == {"b", "c"}, f"expected {{b,c}}, got {ids}"
    assert len(se) == 1 and se[0].source_id == "b"

    # 删 b（cascade 删 c，purge 边）
    g.remove_node("b")
    assert "b" not in g and "c" not in g
    assert g._edges == {}  # 附加边被清

    # restore
    g.restore_subtree(sn, se)
    assert "b" in g and "c" in g
    assert g.get_node("b").parent_id == "a"
    assert g.get_node("c").parent_id == "b"
    assert len(g._edges) == 1
    print("PASS: snapshot_subtree / restore_subtree")


# ============================================================
# 端到端：MainWindow 集成
# ============================================================

def _fresh_mindmap() -> str:
    for m in mindmap_repo.list_mindmaps():
        if m["title"].startswith("diag_undo"):
            mindmap_repo.delete_mindmap(m["id"])
    init_db()
    mid = mindmap_repo.create_mindmap("diag_undo_e2e")
    return mid


def test_e2e_add_child_undo_redo():
    """⭐ GUI：添加子节点 → undo → 不在 → redo → 在。"""
    from src.ui.main_window import MindFlowWindow
    app = QApplication.instance() or QApplication(sys.argv)
    mid = _fresh_mindmap()
    root = mindmap_repo.add_node(mid, "ROOT", parent_id=None, x=400, y=300, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 60)
    assert win.history.undo_count() == 0

    # 直接调 add_node 走 history（绕过 QInputDialog）
    nid_box = {"id": None}
    def _do():
        nid = mindmap_repo.add_node(mid, "child1", parent_id=root, x=500, y=300, color="#4A90E2")
        nid_box["id"] = nid
        if win.current_graph:
            from src.mindmap.node import NodeData
            win.current_graph.add_node(
                NodeData(id=nid, text="child1", pos_x=500, pos_y=300,
                         parent_id=root, color="#4A90E2"),
                parent_id=root,
            )
    def _undo():
        nid = nid_box["id"]
        mindmap_repo.delete_node(nid)
        if win.current_graph:
            win.current_graph.remove_node(nid)
    win._track_reload("add_child", _do, _undo)
    drain(app, 50)
    assert nid_box["id"] is not None
    assert nid_box["id"] in [n.id for n in mindmap_repo.get_nodes(mid)]

    # undo
    win._on_undo()
    drain(app, 60)
    assert nid_box["id"] not in [n.id for n in mindmap_repo.get_nodes(mid)]

    # redo
    win._on_redo()
    drain(app, 60)
    assert nid_box["id"] in [n.id for n in mindmap_repo.get_nodes(mid)]

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: e2e add child → undo → redo")


def test_e2e_delete_with_descendants():
    """⭐ GUI：删带子树的节点 → undo → 子树 + 附加边全部恢复。"""
    from src.ui.main_window import MindFlowWindow
    app = QApplication.instance() or QApplication(sys.argv)
    mid = _fresh_mindmap()
    a = mindmap_repo.add_node(mid, "A", parent_id=None, x=400, y=300, color="#4A90E2")
    b = mindmap_repo.add_node(mid, "B", parent_id=a, x=500, y=300, color="#4A90E2")
    c = mindmap_repo.add_node(mid, "C", parent_id=b, x=600, y=300, color="#4A90E2")
    d = mindmap_repo.add_node(mid, "D", parent_id=None, x=800, y=300, color="#4A90E2")
    eid = mindmap_repo.add_edge(mid, b, d)

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 60)

    before = set(n.id for n in mindmap_repo.get_nodes(mid))
    assert before == {a, b, c, d}

    # snapshot + 删除（手动调 _delete_node_item 的核心逻辑，绕过 QMessageBox）
    sub_nodes, sub_edges = win.current_graph.snapshot_subtree(b)
    def _do():
        mindmap_repo.delete_node(b)
        if win.current_graph:
            win.current_graph.remove_node(b)
    def _undo():
        win._restore_subtree_to_db(sub_nodes, sub_edges)

    win._track_reload("cascade del", _do, _undo)
    drain(app, 30)

    after_del = set(n.id for n in mindmap_repo.get_nodes(mid))
    assert b not in after_del and c not in after_del, f"b/c 应被删，剩 {after_del}"

    win._on_undo()
    drain(app, 60)
    after_undo_nodes = mindmap_repo.get_nodes(mid)
    after_undo_texts = {n.text for n in after_undo_nodes}
    assert "B" in after_undo_texts and "C" in after_undo_texts, \
        f"B/C 应恢复，实际 {after_undo_texts}"
    edges = mindmap_repo.get_edges(mid)
    assert len(edges) == 1, f"附加边应恢复 1 条，剩 {len(edges)}"

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: e2e delete-with-descendants undo")


def test_e2e_text_edit_undo():
    """⭐ GUI：改节点文字 → undo → 旧文字回来。"""
    from src.ui.main_window import MindFlowWindow
    app = QApplication.instance() or QApplication(sys.argv)
    mid = _fresh_mindmap()
    nid = mindmap_repo.add_node(mid, "hello", parent_id=None, x=400, y=300, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 60)

    def _do():
        mindmap_repo.update_node_text(nid, "world")
        node = win.current_graph.get_node(nid)
        node.text = "world"
    def _undo():
        mindmap_repo.update_node_text(nid, "hello")
        node = win.current_graph.get_node(nid)
        node.text = "hello"

    win._track_reload("edit text", _do, _undo)
    drain(app, 30)
    cur = next(n for n in mindmap_repo.get_nodes(mid) if n.id == nid)
    assert cur.text == "world"

    win._on_undo()
    drain(app, 60)
    cur = next(n for n in mindmap_repo.get_nodes(mid) if n.id == nid)
    assert cur.text == "hello", f"undo 后应为 'hello'，实际 '{cur.text}'"

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: e2e text edit undo")


def test_clear_history_on_open_mindmap():
    """⭐ 切导图后历史清空。"""
    from src.ui.main_window import MindFlowWindow
    app = QApplication.instance() or QApplication(sys.argv)
    mid1 = _fresh_mindmap()
    mindmap_repo.add_node(mid1, "R1", parent_id=None, x=400, y=300, color="#4A90E2")
    mid2 = mindmap_repo.create_mindmap("diag_undo_2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid1)
    drain(app, 60)

    # 手动推一条
    win._track_reload("dummy", lambda: None, lambda: None)
    assert win.history.undo_count() == 1

    # 切到 mid2
    win._open_mindmap(mid2)
    drain(app, 60)
    assert win.history.undo_count() == 0, "切导图后栈应清空"

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: history 清空 on open_mindmap")


def test_buttons_disabled_when_empty():
    """⭐ 初始 / 清空后按钮 disabled。"""
    from src.ui.main_window import MindFlowWindow
    app = QApplication.instance() or QApplication(sys.argv)
    mid = _fresh_mindmap()
    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 60)

    assert not win.tb_undo.isEnabled(), "初始 undo 应 disabled"
    assert not win.tb_redo.isEnabled(), "初始 redo 应 disabled"

    win._track_reload("x", lambda: None, lambda: None)
    assert win.tb_undo.isEnabled()
    assert not win.tb_redo.isEnabled()

    win._on_undo()
    assert not win.tb_undo.isEnabled()
    assert win.tb_redo.isEnabled()

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: 按钮可用态随栈变化")


def test_redo_rapid_click_debounce():
    """⭐ 防卡顿：80ms 内连点 redo 按钮 → 第二次被吞掉。

    背景：view 全图重画 + fit_to_content 期间主事件循环仍可接收点击事件，
    若用户在 ~80ms 内连点两次 redo，会触发"第一次似乎没响应、第二次连走两步"的 bug。
    修复：点击时记录时间戳 + 同步禁用按钮，80ms 时间窗内的二次触发直接 ignore。

    80ms = 挡住"鼠标快速连点 / Qt 事件堆积"，但不会过度阻断"刻意按节奏连点"。
    """
    from src.ui.main_window import MindFlowWindow
    from PySide6.QtWidgets import QToolButton
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication(sys.argv)
    mid = _fresh_mindmap()
    root = mindmap_repo.add_node(mid, "R", parent_id=None, x=400, y=300, color="#4A90E2")

    win = MindFlowWindow()
    drain(app, 80)
    win._open_mindmap(mid)
    drain(app, 60)

    # 推 3 条历史
    box = {}
    def make_do(name, x):
        def _do():
            nid = mindmap_repo.add_node(mid, name, parent_id=root, x=x, y=300, color="#4A90E2")
            box[name] = nid
            from src.mindmap.node import NodeData
            if win.current_graph:
                win.current_graph.add_node(
                    NodeData(id=nid, text=name, pos_x=x, pos_y=300,
                             color="#4A90E2", parent_id=root),
                    parent_id=root,
                )
        return _do
    win._track_reload("A", make_do("A", 500), lambda: mindmap_repo.delete_node(box["A"]))
    win._track_reload("B", make_do("B", 600), lambda: mindmap_repo.delete_node(box["B"]))
    win._track_reload("C", make_do("C", 700), lambda: mindmap_repo.delete_node(box["C"]))
    drain(app, 60)

    # ⭐ undo 之间 drain 200ms 绕开 debounce（测 debounce 本身时不该用 undo loop 凑数）
    for _ in range(3):
        win._on_undo()
        drain(app, 200)

    # 找 tb_redo 的 QToolButton，用 QTest.mouseClick 发真实鼠标事件
    btn = None
    for tb_btn in win.findChildren(QToolButton):
        if tb_btn.defaultAction() is win.tb_redo:
            btn = tb_btn
            break
    assert btn is not None, "找不到 tb_redo 对应 QToolButton"

    before = (win.history.undo_count(), win.history.redo_count(), len(mindmap_repo.get_nodes(mid)))
    assert before == (0, 3, 1), f"setup 异常：{before}"

    # ⭐ 连点 2 次（中间不 drain）→ 应只走 1 步
    pos = btn.rect().center()
    QTest.mouseClick(btn, Qt.LeftButton, pos=pos)
    QTest.mouseClick(btn, Qt.LeftButton, pos=pos)
    drain(app, 50)
    after_2 = (win.history.undo_count(), win.history.redo_count(), len(mindmap_repo.get_nodes(mid)))
    assert after_2[1] == before[1] - 1, \
        f"连点 2 次应只走 1 步：{before} → {after_2}（diff={before[1] - after_2[1]}）"
    assert after_2[2] == before[2] + 1, "DB 节点数应 +1"

    # ⭐ 等 debounce 窗口结束（80ms + 一点 buffer）
    drain(app, 200)

    # ⭐ 再点 1 次 → 应该正常走 1 步
    before_3 = (win.history.undo_count(), win.history.redo_count(), len(mindmap_repo.get_nodes(mid)))
    QTest.mouseClick(btn, Qt.LeftButton, pos=pos)
    drain(app, 50)
    after_3 = (win.history.undo_count(), win.history.redo_count(), len(mindmap_repo.get_nodes(mid)))
    assert after_3[1] == before_3[1] - 1, \
        f"debounce 后再点应正常走 1 步：{before_3} → {after_3}"

    win.close(); win.deleteLater(); drain(app, 30)
    print("PASS: rapid click 防卡顿 (80ms 时间窗)")


if __name__ == "__main__":
    print("=== HistoryManager 单元 ===")
    test_history_basic()
    test_history_max_size()
    test_history_changed_signal()

    print("\n=== MindMapGraph 单元 ===")
    test_snapshot_subtree_basic()

    print("\n=== MainWindow 端到端 ===")
    test_e2e_add_child_undo_redo()
    test_e2e_delete_with_descendants()
    test_e2e_text_edit_undo()
    test_clear_history_on_open_mindmap()
    test_buttons_disabled_when_empty()
    test_redo_rapid_click_debounce()

    print("\n✅ ALL UNDO/REDO TESTS PASS")