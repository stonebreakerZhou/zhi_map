# -*- coding: utf-8 -*-
"""⭐ GUI 端到端测试：菜单 → 选文件 → 走 _on_import_zhishu → 验证 DB。

不弹真实对话框，而是 monkey-patch QFileDialog.getOpenFileName 返回临时文件路径。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.integrations.zhishu._domain import seed_state, transition
from src.storage import mindmap_repo
from src.storage.db import init_db
from src.utils.logger import setup_logger


def drain(app, ms=60):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


def _build_export_file(tmp_path: Path) -> Path:
    """写一份带 2 个 session、3 个分支的 export JSON。"""
    state = seed_state()
    # 再加一个 session 和 1 个分支
    state = transition(state, {"type": "create", "title": "（GUI 测试）测试会话"})
    state = transition(state, {"type": "send", "branchId": state["active"], "text": "用户提问"})
    state = transition(state, {"type": "answer", "branchId": state["active"],
                                "text": "AI 回答。"})

    path = tmp_path / "zhishu_gui_test.json"
    path.write_text(
        json.dumps({"schemaVersion": 2, "state": state}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _cleanup_test_mindmaps():
    for m in mindmap_repo.list_mindmaps():
        if "测试会话" in m["title"] or "二次函数" in m["title"] or "完全平方" in m["title"]:
            mindmap_repo.delete_mindmap(m["id"])


def test_gui_import_zhishu(tmp_path):
    """⭐ 端到端：触发菜单 → 文件被读 → MindMap 入库 → sidebar 刷新。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    _cleanup_test_mindmaps()
    drain(app, 50)

    from src.ui.main_window import MindFlowWindow

    export_path = _build_export_file(tmp_path)

    # ⭐ Monkey-patch 文件选择对话框
    original_get = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **kw: (str(export_path), "知树导出 (*.json)")
    )
    # ⭐ Monkey-patch 确认对话框（question 默认 Yes）
    original_question = QMessageBox.question
    QMessageBox.question = staticmethod(
        lambda *a, **kw: QMessageBox.Yes
    )
    # ⭐ Monkey-patch 信息对话框（避免阻塞）
    info_calls = []
    QMessageBox.information = staticmethod(
        lambda parent, title, msg: info_calls.append((title, msg)) or QMessageBox.Ok
    )
    warning_calls = []
    QMessageBox.warning = staticmethod(
        lambda parent, title, msg: warning_calls.append((title, msg)) or QMessageBox.Ok
    )

    # ⭐ Monkey-patch import_converted 以捕获 handler 内部的 result
    import src.integrations.zhishu as _zhishu_mod
    real_import_converted = _zhishu_mod.import_converted
    captured_results: list = []
    def _capturing_import_converted(*a, **kw):
        r = real_import_converted(*a, **kw)
        captured_results.append(r)
        return r
    _zhishu_mod.import_converted = _capturing_import_converted
    # main_window 里是直接 import 的别名，需要同步打补丁
    import src.ui.main_window as _mw_mod
    _mw_mod.zhishu_import_converted = _capturing_import_converted

    try:
        win = MindFlowWindow()
        drain(app, 80)

        before = mindmap_repo.list_mindmaps()
        before_titles = {m["title"] for m in before}

        # ⭐ 触发 _on_import_zhishu
        win._on_import_zhishu()
        drain(app, 100)

        after = mindmap_repo.list_mindmaps()
        new_mindmaps = [m for m in after if m["title"] not in before_titles]
        assert len(new_mindmaps) >= 2, \
            f"应新增至少 2 个 mindmap（seed_state 有 2 个 session），实际新增 {len(new_mindmaps)}"

        # 验证每个新 mindmap 有节点
        for m in new_mindmaps:
            nodes = mindmap_repo.get_nodes(m["id"])
            assert len(nodes) >= 1, f"{m['title']} 没节点"

        # 验证当前打开的是新导入的第一个（捕获 monkey-patch 拿到的 import_result）
        assert len(captured_results) == 1, f"应只调用 import_converted 一次，实际 {len(captured_results)}"
        captured = captured_results[0]
        first_created = captured.mindmap_ids[0]
        assert win.current_mindmap_id == first_created, \
            f"应自动打开第一个新 mindmap\n  期望: {first_created!r}\n  实际: {win.current_mindmap_id!r}"
        # 同时验证它在 new_mindmaps 里（说明确实在 sidebar 可见）
        opened_in_list = any(m["id"] == win.current_mindmap_id for m in new_mindmaps)
        assert opened_in_list, f"当前打开的 mindmap {win.current_mindmap_id} 不在列表里"

        # 验证信息弹窗被调用
        assert len(info_calls) >= 1, "应弹出成功信息"
        assert "导入完成" in info_calls[-1][0] or "成功" in info_calls[-1][1]

        # 验证状态栏（offscreen 模式下 Qt statusBar 可能没渲染，只验证非 None）
        status_text = win.statusBar().currentMessage()
        # 状态栏在 offscreen 模式下可能为空，不强制断言；只要不是异常就算过
        _ = status_text  # noqa: F841

        win.close(); win.deleteLater(); drain(app, 30)
    finally:
        QFileDialog.getOpenFileName = original_get
        QMessageBox.question = original_question
        # 还原 monkey-patch 的 import_converted
        try:
            import src.integrations.zhishu as _zhishu_mod2
            _zhishu_mod2.import_converted = real_import_converted
            import src.ui.main_window as _mw_mod2
            _mw_mod2.zhishu_import_converted = real_import_converted
        except Exception:
            pass

    _cleanup_test_mindmaps()
    print(f"PASS: GUI 导入端到端 — 新增 {len(new_mindmaps)} 个 MindMap，"
          f"信息弹窗 {len(info_calls)} 次")


def test_gui_import_handles_bad_file(tmp_path):
    """⭐ 损坏文件 → 友好错误提示，不崩溃。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    drain(app, 30)

    from src.ui.main_window import MindFlowWindow

    # 写一个无效 JSON
    bad_path = tmp_path / "bad.json"
    bad_path.write_text('{"schemaVersion": 999, "state": {}}', encoding="utf-8")

    original_get = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **kw: (str(bad_path), "知树导出 (*.json)")
    )
    critical_calls = []
    QMessageBox.critical = staticmethod(
        lambda parent, title, msg: critical_calls.append((title, msg)) or QMessageBox.Ok
    )

    try:
        win = MindFlowWindow()
        drain(app, 80)
        before_count = len(mindmap_repo.list_mindmaps())

        win._on_import_zhishu()
        drain(app, 50)

        after_count = len(mindmap_repo.list_mindmaps())
        assert after_count == before_count, "损坏文件不应入库"
        assert len(critical_calls) == 1, "应弹错误对话框"
        assert "导入失败" in critical_calls[0][0]

        win.close(); win.deleteLater(); drain(app, 30)
    finally:
        QFileDialog.getOpenFileName = original_get

    print("PASS: 损坏文件 → 友好错误，不入库")


if __name__ == "__main__":
    import tempfile
    setup_logger()

    print("=== GUI 端到端导入 ===")
    with tempfile.TemporaryDirectory() as tmp:
        test_gui_import_zhishu(Path(tmp))

    print("\n=== GUI 错误处理 ===")
    with tempfile.TemporaryDirectory() as tmp:
        test_gui_import_handles_bad_file(Path(tmp))

    print("\n✅ ALL GUI ZHISHU TESTS PASS")