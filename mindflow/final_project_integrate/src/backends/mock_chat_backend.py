"""⭐ MockChatBackend：内存版 IChatBackend（满足 IChatBackend Protocol）。

zhi_map 状态机的本地实现，零依赖。可用：
- 离线演示 / 测试
- Track 2 默认 backend（无需 zhi_map FastAPI）

P3 负责维护。
"""

from __future__ import annotations

import uuid

from src.utils.logger import get_logger

logger = get_logger("mindflow.backends.mock_chat")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class MockChatBackend:
    """⭐ 内存版 chat backend（实现 IChatBackend）。"""

    def __init__(self) -> None:
        self._state: dict = {
            "version": 2,
            "sessions": [],
            "branches": [],
            "active": None,
        }
        # revision 是单调递增整数（zhi_map 用 int 模拟）
        self._revision: int = 0
        logger.info("MockChatBackend 初始化（内存版）")

    # ---- 状态查询 ----

    def get_state(self) -> dict:
        """返回深拷贝，防止外部修改污染内部。"""
        import copy

        return copy.deepcopy(self._state)

    def get_revision(self) -> int:
        return self._revision

    # ---- 会话 / 分支创建 ----

    def create_session(self, title: str) -> str:
        sid = _new_id()
        bid = _new_id()
        self._state["sessions"].append({"id": sid, "title": title})
        self._state["branches"].append(
            {
                "id": bid,
                "sessionId": sid,
                "title": title,
                "tags": [],
                "parent": None,
                "kept": False,
                "draft": None,
                "entries": [],
                "selection": None,
                "pendingPrompt": None,
                "awaiting": False,
                "metadataDone": True,
            }
        )
        self._state["active"] = bid
        self._revision += 1
        return sid

    def switch_branch(self, branch_id: str) -> None:
        if not any(b["id"] == branch_id for b in self._state["branches"]):
            raise ValueError(f"分支不存在：{branch_id}")
        self._state["active"] = branch_id
        self._revision += 1

    # ---- 对话动作 ----

    def send(self, branch_id: str, text: str) -> None:
        b = self._find_branch(branch_id)
        b["entries"].append(
            {
                "id": _new_id(),
                "kind": "message",
                "role": "user",
                "text": text,
                "inherited": False,
                "simulated": False,
                "createdAt": _now_iso(),
            }
        )
        b["awaiting"] = True
        b["pendingPrompt"] = text
        self._revision += 1

    def answer(self, branch_id: str, text: str) -> None:
        b = self._find_branch(branch_id)
        b["entries"].append(
            {
                "id": _new_id(),
                "kind": "message",
                "role": "assistant",
                "text": text,
                "inherited": False,
                "simulated": False,
                "createdAt": _now_iso(),
            }
        )
        b["awaiting"] = False
        b["pendingPrompt"] = None
        self._revision += 1

    def fork(self, branch_id: str, entry_id: str, title: str) -> str:
        b = self._find_branch(branch_id)
        new_id = _new_id()
        # 截断到 entry_id
        cut = (
            next((i for i, e in enumerate(b["entries"]) if e["id"] == entry_id), 0) + 1
        )
        self._state["branches"].append(
            {
                "id": new_id,
                "sessionId": b["sessionId"],
                "title": title,
                "tags": [],
                "parent": branch_id,
                "kept": False,
                "draft": None,
                "entries": list(b["entries"][:cut]),
                "selection": None,
                "pendingPrompt": None,
                "awaiting": False,
                "metadataDone": True,
            }
        )
        self._revision += 1
        return new_id

    def expand(
        self,
        branch_id: str,
        selection: dict,
        context_ids: list[str],
        text: str,
    ) -> str:
        b = self._find_branch(branch_id)
        new_id = _new_id()
        inherited = [e for e in b["entries"] if e["id"] in set(context_ids)]
        self._state["branches"].append(
            {
                "id": new_id,
                "sessionId": b["sessionId"],
                "title": "(展开)",
                "tags": [],
                "parent": branch_id,
                "kept": False,
                "draft": None,
                "entries": inherited,
                "selection": selection,
                "pendingPrompt": text,
                "awaiting": True,
                "metadataDone": False,
            }
        )
        self._revision += 1
        return new_id

    def keep(self, branch_id: str) -> None:
        b = self._find_branch(branch_id)
        b["kept"] = not b["kept"]
        self._revision += 1

    def add_tags(self, branch_id: str, tags: list[str]) -> None:
        b = self._find_branch(branch_id)
        existing = list(b.get("tags", []))
        merged = list(dict.fromkeys(existing + tags))
        b["tags"] = merged
        self._revision += 1

    def delete_branch(self, branch_id: str) -> None:
        before = len(self._state["branches"])
        self._state["branches"] = [
            b for b in self._state["branches"] if b["id"] != branch_id
        ]
        if len(self._state["branches"]) == before:
            raise ValueError(f"分支不存在：{branch_id}")
        if self._state["active"] == branch_id:
            self._state["active"] = (
                self._state["branches"][0]["id"] if self._state["branches"] else None
            )
        self._revision += 1

    # ---- 生命周期 ----

    def reset(self) -> None:
        self._state = {
            "version": 2,
            "sessions": [],
            "branches": [],
            "active": None,
        }
        self._revision += 1

    # ---- 内部 ----

    def _find_branch(self, branch_id: str) -> dict:
        b = next((x for x in self._state["branches"] if x["id"] == branch_id), None)
        if b is None:
            raise ValueError(f"分支不存在：{branch_id}")
        return b


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = ["MockChatBackend"]
