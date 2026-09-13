"""⭐ ChatService：对话业务服务（包装 ``IChatBackend``）。

职责：
- 把同步的 ``IChatBackend`` 调用暴露成同步 API（UI 直接调）
- 提供 ``send_and_wait`` 等组合动作
- 错误归一化（ConflictError / RuntimeError → 友好消息）

UI 用法::

    from src.core.container import Container
    chat = Container.default().chat_service

    sid = chat.create_session("复习计划")
    chat.send(chat.active_branch(), "你好")
    chat.answer(chat.active_branch(), "AI 答...")

P3 负责维护。
"""

from __future__ import annotations

from src.core.interfaces.chat import IChatBackend
from src.utils.logger import get_logger

logger = get_logger("mindflow.core.services.chat_service")


class ChatService:
    """⭐ 对话业务服务（薄包装 IChatBackend）。"""

    def __init__(self, backend: IChatBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> IChatBackend:
        return self._backend

    # ==================== 状态 ====================

    def get_state(self) -> dict:
        return self._backend.get_state()

    def active_branch(self) -> str | None:
        """当前 active branch id（zhi_map state.active）。"""
        state = self._backend.get_state()
        return state.get("active")

    # ==================== 会话 / 分支 ====================

    def create_session(self, title: str) -> str:
        sid = self._backend.create_session(title)
        logger.info(f"create_session: {title} → {sid}")
        return sid

    def switch_branch(self, branch_id: str) -> None:
        self._backend.switch_branch(branch_id)
        logger.info(f"switch_branch: {branch_id}")

    def delete_branch(self, branch_id: str) -> None:
        self._backend.delete_branch(branch_id)
        logger.info(f"delete_branch: {branch_id}")

    # ==================== 对话动作 ====================

    def send(self, branch_id: str, text: str) -> None:
        self._backend.send(branch_id, text)

    def answer(self, branch_id: str, text: str) -> None:
        self._backend.answer(branch_id, text)

    def fork(self, branch_id: str, entry_id: str, title: str) -> str:
        new_branch = self._backend.fork(branch_id, entry_id, title)
        logger.info(f"fork: {branch_id}/{entry_id} → {new_branch}")
        return new_branch

    def expand(
        self,
        branch_id: str,
        selection: dict,
        context_ids: list[str],
        text: str,
    ) -> str:
        new_branch = self._backend.expand(branch_id, selection, context_ids, text)
        logger.info(f"expand: {branch_id} → {new_branch}")
        return new_branch

    def keep(self, branch_id: str) -> None:
        self._backend.keep(branch_id)

    def add_tags(self, branch_id: str, tags: list[str]) -> None:
        self._backend.add_tags(branch_id, tags)

    # ==================== 生命周期 ====================

    def reset(self) -> None:
        self._backend.reset()
        logger.info("ChatService.reset")


__all__ = ["ChatService"]
