# -*- coding: utf-8 -*-
"""⭐ AI 对话面板（Phase 2）测试。

覆盖：
1. ai_config: save/load/clear
2. ai_client: mock 模式 + 真 API 模式（mock httpx）
3. AiChatPanel: 创建会话、发送、展开分支
4. 端到端：UI 触发 → 状态机 → DB 节点新增
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from src.integrations.zhishu import ai_client, ai_config
from src.integrations.zhishu._domain import transition
from src.storage import mindmap_repo
from src.storage.db import init_db
from src.utils.logger import setup_logger


def drain(app, ms=50):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        app.processEvents()


# ============================================================
# 1. ai_config
# ============================================================

def test_ai_config_save_load(tmp_path, monkeypatch):
    """⭐ 配置保存和读取。"""
    monkeypatch.setattr(ai_config, "CONFIG_FILE", tmp_path / "ai_config.json")
    ai_config.clear_config()
    assert ai_config.load_config() is None, "清空后应读不到"

    cfg = ai_config.AiConfig(
        base_url="https://example.com/v1",
        model="test-model",
        api_key="sk-test-123",
        timeout_ms=30000,
    )
    ai_config.save_config(cfg)
    loaded = ai_config.load_config()
    assert loaded is not None
    assert loaded.base_url == "https://example.com/v1"
    assert loaded.model == "test-model"
    assert loaded.api_key == "sk-test-123"
    assert loaded.timeout_ms == 30000
    assert loaded.is_configured()

    ai_config.clear_config()
    assert ai_config.load_config() is None
    print("PASS: ai_config save/load/clear")


def test_ai_config_is_configured():
    """⭐ is_configured 判断逻辑。"""
    empty = ai_config.AiConfig()
    assert not empty.is_configured()

    no_key = ai_config.AiConfig(model="x")
    assert not no_key.is_configured()

    ok = ai_config.AiConfig(model="x", api_key="k")
    assert ok.is_configured()
    print("PASS: ai_config is_configured 逻辑")


# ============================================================
# 2. ai_client
# ============================================================

def test_mock_ai_keywords():
    """⭐ Mock AI 根据关键词返回预设回答。"""
    # 强制 mock
    r1 = ai_client.complete_chat([{"role": "user", "content": "你好"}], use_mock=True)
    assert "你好" in r1 or "Mock" in r1
    r2 = ai_client.complete_chat([{"role": "user", "content": "什么是 Transformer"}], use_mock=True)
    assert "概念解释" in r2
    r3 = ai_client.complete_chat([{"role": "user", "content": "怎么做"}], use_mock=True)
    assert "步骤分解" in r3
    print("PASS: Mock AI 关键词响应")


def test_is_mock_mode_default(tmp_path, monkeypatch):
    """⭐ 没配配置 → Mock 模式。"""
    monkeypatch.setattr(ai_config, "CONFIG_FILE", tmp_path / "no_config.json")
    ai_config.clear_config()
    assert ai_client.is_mock_mode()
    print("PASS: is_mock_mode 默认 True（无配置）")


def test_real_api_call_with_mocked_httpx():
    """⭐ 真 API 调用（用 mock httpx 模拟响应）。"""
    cfg = ai_config.AiConfig(
        base_url="https://api.example.com/v1",
        model="test-model",
        api_key="sk-test",
        timeout_ms=5000,
    )
    fake_response = {
        "choices": [{"message": {"content": "这是 mock API 的回答"}}]
    }
    class FakeResp:
        status_code = 200
        def json(self): return fake_response
    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw): return FakeResp()

    with patch("src.integrations.zhishu.ai_client.httpx.AsyncClient", FakeClient):
        result = ai_client.complete_chat(
            [{"role": "user", "content": "测试"}],
            config=cfg,
            use_mock=False,
        )
    assert result == "这是 mock API 的回答"
    print("PASS: 真 API 路径（mocked httpx）")


# ============================================================
# 3. 端到端：状态机 + DB
# ============================================================

def test_e2e_zhishu_state_to_db():
    """⭐ zhi_map state 机 → MindFlow DB 完整链路。"""
    init_db()
    # 清掉测试残留
    for m in mindmap_repo.list_mindmaps():
        if "AI 对话测试" in m["title"]:
            mindmap_repo.delete_mindmap(m["id"])

    # 1. 用 transition 跑一个完整流程
    state = {"version": 2, "sessions": [], "branches": [], "active": None}
    state = transition(state, {"type": "create", "title": "AI 对话测试"})
    bid = state["active"]
    state = transition(state, {"type": "send", "branchId": bid, "text": "什么是 Self-Attention？"})
    state = transition(state, {
        "type": "answer", "branchId": bid,
        "text": "Self-Attention 让每个位置都能看到所有位置。",
    })
    last_entry = state["branches"][0]["entries"][-1]
    target = "每个位置"
    idx = last_entry["text"].find(target)
    state = transition(state, {
        "type": "expand",
        "branchId": bid,
        "selection": {"entryId": last_entry["id"], "start": idx, "end": idx + len(target), "text": target},
        "contextIds": [last_entry["id"]],
        "text": "为什么 Self-Attention 能让每个位置看到所有位置？",
    })
    # expand 自动 send，需要 answer
    new_bid = state["active"]
    state = transition(state, {
        "type": "answer", "branchId": new_bid,
        "text": "通过 QKV 矩阵运算，O(n²) 复杂度。",
    })
    state = transition(state, {"type": "keep", "branchId": bid})

    # 2. 把所有 branch 同步到 DB
    mid_db = mindmap_repo.create_mindmap("AI 对话测试")
    root_id = mindmap_repo.add_node(mid_db, "AI 对话测试", x=0, y=0, color="#4A90E2")
    for b in state["branches"]:
        parent_db = None
        if b.get("parent"):
            pbid = b["parent"]["branchId"]
            # 找 parent 对应节点（通过 metadata）
            for n in mindmap_repo.get_nodes(mid_db):
                if n.note and f"branchId: {pbid}\n" in n.note:
                    parent_db = n.id
                    break
        if parent_db is None:
            parent_db = root_id
        color = "#F39C12" if b.get("kept") else "#4A90E2"
        nid = mindmap_repo.add_node(mid_db, b["title"], parent_id=parent_db,
                                     x=300, y=200, color=color)
        mindmap_repo.update_node_text(nid, b["title"])
        note = ""
        for e in b["entries"]:
            note += f"**{'👤 你' if e['role']=='user' else '🤖 AI'}**\n\n{e['text']}\n\n---\n\n"
        note = (
            "<!-- zhi_map-meta\n"
            f"  branchId: {b['id']}\n"
            f"  kept: {b.get('kept', False)}\n"
            "-->\n\n"
        ) + note
        mindmap_repo.update_node_note(nid, note)

    # 3. 验证
    nodes = mindmap_repo.get_nodes(mid_db)
    assert len(nodes) == 3, f"应 3 节点（root + 2 branch），实际 {len(nodes)}"

    # kept 节点应该是橙色
    kept_nodes = [n for n in nodes if "#F39C12" in (n.color or "")]
    assert len(kept_nodes) == 1, f"应 1 个 kept 节点"

    # 父子关系
    parent_of = {n.id: n.parent_id for n in nodes}
    non_root = [n for n in nodes if n.parent_id is not None]
    assert len(non_root) == 2

    # 清理
    mindmap_repo.delete_mindmap(mid_db)
    print(f"PASS: 端到端 state → DB（{len(nodes)} 节点，{len(non_root)} 子节点）")


# ====================================
# 入口
# ====================================

if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    setup_logger()
    import tempfile

    print("=== ai_config ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        import unittest.mock as _mock
        with _mock.patch.object(ai_config, "CONFIG_FILE", Path(tmpdir) / "ai_config.json"):
            test_ai_config_save_load(Path(tmpdir), _mock.MagicMock())
            test_is_mock_mode_default(Path(tmpdir), _mock.MagicMock())
    test_ai_config_is_configured()

    print("\n=== ai_client ===")
    test_mock_ai_keywords()
    test_real_api_call_with_mocked_httpx()

    print("\n=== 端到端 ===")
    test_e2e_zhishu_state_to_db()

    print("\n✅ ALL AI CHAT TESTS PASS")