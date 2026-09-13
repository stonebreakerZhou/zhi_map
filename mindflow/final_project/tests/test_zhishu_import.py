# -*- coding: utf-8 -*-
"""⭐ 知树 → MindFlow 桥接层测试。

覆盖：
1. 内嵌 domain 模块能 import + 跑 transition()
2. Loader 能读 /api/export 格式的 JSON（合法 / 非法 / 老版本）
3. Converter 把 state 转成正确数量的 MindMap + 节点
4. Importer 把转换结果写入 mindmap_repo，能 get_nodes 出来
5. 端到端：从 seed_state 生成 JSON → load → convert → import → 验证 DB
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

from PySide6.QtWidgets import QApplication

from src.integrations.zhishu import (
    LoaderError,
    convert_state,
    import_converted,
    load_export_file,
    load_export_text,
)
from src.integrations.zhishu._domain import seed_state, transition
from src.storage import mindmap_repo
from src.storage.db import init_db
from src.utils.logger import setup_logger


def drain(app, ms=60):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


# ============================================================
# 单元：内嵌 domain
# ============================================================

def test_embedded_domain_runs():
    """⭐ 内嵌的 zhi_map domain 模块能被 import + 跑。"""
    state = seed_state()
    assert state["version"] == 2
    assert len(state["sessions"]) == 2
    assert len(state["branches"]) == 2

    # 跑一个 mutation
    after = transition(state, {"type": "create", "title": "新会话"})
    assert len(after["sessions"]) == 3
    print("PASS: 内嵌 domain 模块运行正常")


# ============================================================
# 单元：Loader
# ============================================================

def test_loader_accepts_valid_export(tmp_path):
    """⭐ 合法 export 文件 → 加载成功。"""
    state = seed_state()
    export = {"schemaVersion": 2, "state": state}
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")

    loaded = load_export_file(path)
    assert loaded["schemaVersion"] == 2
    assert loaded["state"]["version"] == 2
    assert len(loaded["state"]["branches"]) == 2
    print("PASS: Loader 接受合法 export")


def test_loader_rejects_bad_schema_version(tmp_path):
    """⭐ schemaVersion=1 → LoaderError。"""
    path = tmp_path / "v1.json"
    path.write_text(json.dumps({"schemaVersion": 1, "state": {}}), encoding="utf-8")
    try:
        load_export_file(path)
        assert False, "应该抛 LoaderError"
    except LoaderError as exc:
        assert "schemaVersion" in str(exc)
        print("PASS: Loader 拒绝 schemaVersion=1")


def test_loader_rejects_invalid_state(tmp_path):
    """⭐ state schema 不合法 → LoaderError。"""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schemaVersion": 2, "state": {"version": 999}}), encoding="utf-8")
    try:
        load_export_file(path)
        assert False, "应该抛 LoaderError"
    except LoaderError as exc:
        assert "schema" in str(exc) or "state" in str(exc)
        print("PASS: Loader 拒绝非法 state")


def test_loader_accepts_text():
    """⭐ 字符串输入也能解析。"""
    state = seed_state()
    text = json.dumps({"schemaVersion": 2, "state": state}, ensure_ascii=False)
    loaded = load_export_text(text)
    assert loaded["state"]["version"] == 2
    print("PASS: load_export_text 字符串输入")


# ============================================================
# 单元：Converter
# ============================================================

def test_convert_produces_one_mindmap_per_session():
    """⭐ N 个 session → N 个 MindMap，每个 branch 一个 node。"""
    state = seed_state()  # 2 sessions, 2 branches
    # 多加一个 session 和分支
    after = transition(state, {"type": "create", "title": "测试"})
    after = transition(after, {"type": "send", "branchId": after["active"], "text": "hi"})
    result = convert_state(after)
    assert len(result.mindmaps) == 3, f"应有 3 个 mindmap，实际 {len(result.mindmaps)}"
    # 第一个 session 1 个 branch；第二个 session 1 个 branch；第三个 1 个
    total_nodes = sum(len(m.nodes) for m in result.mindmaps)
    assert total_nodes == len(after["branches"]), \
        f"节点总数不对：{total_nodes} vs {len(after['branches'])}"
    print(f"PASS: Converter 产出 {len(result.mindmaps)} 个 mindmap, {total_nodes} 个节点")


def test_convert_preserves_parent_links():
    """⭐ fork / expand 的父子关系保留。"""
    state = seed_state()
    # 在第一个 session 加一个 fork 分支
    root_branch = state["branches"][0]
    forked = transition(state, {
        "type": "fork",
        "branchId": root_branch["id"],
        "entryId": root_branch["entries"][1]["id"],
        "title": "从 AI 回答继续",
    })
    result = convert_state(forked)
    # 取第一个 session 的 mindmap
    mm0 = result.mindmaps[0]
    parent_of = {n["id"]: n["parent_id"] for n in mm0.nodes}
    text_of = {n["id"]: n["text"] for n in mm0.nodes}
    # root + forked（forked 的 id 是新的 uuid，text 是 "从 AI 回答继续"）
    assert len(mm0.nodes) == 2
    assert parent_of[root_branch["id"]] is None, "root 应无 parent"
    # 找 forked 的 id
    forked_ids = [nid for nid, t in text_of.items() if t == "从 AI 回答继续"]
    assert len(forked_ids) == 1, f"找不到 fork 出来的节点: {text_of}"
    assert parent_of[forked_ids[0]] == root_branch["id"], \
        f"forked 应挂在 root 下，实际 parent={parent_of[forked_ids[0]]}"
    print("PASS: 父子关系保留正确")


def test_convert_assigns_coordinates():
    """⭐ 每个节点都有非空坐标（自动布局生效）。"""
    state = seed_state()
    # 加几层分支让布局生效
    after = state
    for i in range(3):
        bid = after["branches"][0]["id"] if after["branches"] else None
        if not bid:
            break
        after = transition(after, {
            "type": "fork",
            "branchId": bid,
            "entryId": after["branches"][0]["entries"][-1]["id"],
            "title": f"分支{i}",
        })
    result = convert_state(after)
    all_have_coords = all(
        isinstance(n["x"], (int, float)) and isinstance(n["y"], (int, float))
        for m in result.mindmaps for n in m.nodes
    )
    assert all_have_coords, "节点缺坐标"
    # 至少有一个节点的 x != 0（说明展开了）
    any_x_nonzero = any(n["x"] != 0 for m in result.mindmaps for n in m.nodes)
    assert any_x_nonzero, "所有节点都在 x=0，布局没生效"
    print("PASS: 自动布局产出有效坐标")


def test_convert_note_contains_metadata():
    """⭐ note 头部包含 zhi_map 元数据（HTML 注释块）。"""
    state = seed_state()
    result = convert_state(state)
    mm0 = result.mindmaps[0]
    note = mm0.nodes[0]["note"]
    assert "<!-- zhi_map-meta" in note, f"note 缺少元数据 header: {note[:200]}"
    assert "branchId:" in note
    assert "tags:" in note
    print("PASS: note 含 zhi_map 元数据")


# ============================================================
# 端到端：导入到 DB
# ============================================================

def _cleanup_zhishu_mindmaps():
    for m in mindmap_repo.list_mindmaps():
        if "（知树）" in m["title"] or m["title"].startswith("二次函数") \
           or m["title"].startswith("完全平方") or m["title"].startswith("测试"):
            mindmap_repo.delete_mindmap(m["id"])


def test_e2e_import_seed_state_to_db():
    """⭐ 端到端：seed_state → JSON → load → convert → import → 验证 DB。"""
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()
    _cleanup_zhishu_mindmaps()
    drain(app, 50)

    # 1. 生成 export
    state = seed_state()
    # 加几个测试用分支
    state = transition(state, {"type": "create", "title": "（知树）测试会话"})
    state = transition(state, {"type": "send", "branchId": state["active"], "text": "你好 AI"})
    state = transition(state, {"type": "answer", "branchId": state["active"],
                                "text": "你好！这是 AI 的回答。"})
    export_text = json.dumps({"schemaVersion": 2, "state": state}, ensure_ascii=False)

    # 2. load + convert
    loaded = load_export_text(export_text)
    result = convert_state(loaded["state"])

    # 3. import
    import_result = import_converted(result)
    drain(app, 50)

    assert len(import_result.mindmap_ids) == 3, f"应有 3 个 mindmap 入库，实际 {len(import_result.mindmap_ids)}"
    assert import_result.total_nodes > 0
    assert not import_result.failures, f"导入失败：{import_result.failures}"

    # 4. 验证 DB
    listed = mindmap_repo.list_mindmaps()
    imported_titles = [m["title"] for m in listed if "知树" in m["title"] or m["title"].startswith("二次") or m["title"].startswith("完全")]
    assert len(imported_titles) >= 3, f"DB 找不到导入的 mindmap: {listed}"

    for mid in import_result.mindmap_ids:
        nodes = mindmap_repo.get_nodes(mid)
        assert len(nodes) >= 1, f"mindmap {mid} 没节点"

    _cleanup_zhishu_mindmaps()
    print(f"PASS: 端到端导入 {len(import_result.mindmap_ids)} 个 mindmap, "
          f"{import_result.total_nodes} 个节点")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    setup_logger()

    print("=== 内嵌 domain ===")
    test_embedded_domain_runs()

    print("\n=== Loader ===")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        test_loader_accepts_valid_export(tmp)
        test_loader_rejects_bad_schema_version(tmp)
        test_loader_rejects_invalid_state(tmp)
    test_loader_accepts_text()

    print("\n=== Converter ===")
    test_convert_produces_one_mindmap_per_session()
    test_convert_preserves_parent_links()
    test_convert_assigns_coordinates()
    test_convert_note_contains_metadata()

    print("\n=== 端到端 ===")
    test_e2e_import_seed_state_to_db()

    print("\n✅ ALL ZHISHU IMPORT TESTS PASS")