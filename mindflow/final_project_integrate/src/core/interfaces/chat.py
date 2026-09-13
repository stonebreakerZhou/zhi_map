"""⭐ 对话状态机后端接口（核心抽象 1/4）。

任何对话后端都要实现这个 Protocol：
- ZhiMapChatBackend（内嵌 zhi_map domain）
- MockChatBackend（内存）
- WebChatBackend（HTTP 调用 zhi_map FastAPI / Zhishu.exe）
- 其他自定义后端

UI 层只依赖此接口，永远不直接调 ``transition()``。

P3 负责维护。
"""

from __future__ import annotations

from typing import Protocol


class IChatBackend(Protocol):
    """⭐ 对话状态机后端（zhi_map / Mock / Web 等都可实现此接口）。

    所有方法都是**同步**的（不阻塞 UI 的事交给 Service 层用 QThread）。
    返回 dict 即 zhi_map workspace state；返回 str 即 UUID。
    """

    # ---- 状态查询 ----

    def get_state(self) -> dict:
        """返回当前完整 workspace state（zhi_map 格式：sessions/branches/active）。

        实现方保证返回的 state 通过 ``validate_state()`` 强校验。
        """
        ...

    # ---- 会话 / 分支创建 ----

    def create_session(self, title: str) -> str:
        """创建新会话（= 新 MindMap）。

        Returns:
            session_id
        """
        ...

    def switch_branch(self, branch_id: str) -> None:
        """切换当前活动分支。"""
        ...

    # ---- 对话动作 ----

    def send(self, branch_id: str, text: str) -> None:
        """用户提问：append 到 branch.entries，设置 awaiting=True。"""
        ...

    def answer(self, branch_id: str, text: str) -> None:
        """AI 回答落地：append 一条 assistant entry，清 awaiting。"""
        ...

    def fork(self, branch_id: str, entry_id: str, title: str) -> str:
        """从一条 entry 整体 fork 一个新分支。

        Returns:
            新 branch_id
        """
        ...

    def expand(
        self,
        branch_id: str,
        selection: dict,
        context_ids: list[str],
        text: str,
    ) -> str:
        """⭐ zhi_map 灵魂 UX：从一条消息的某段选区展开独立分支。

        Args:
            branch_id: 当前活动分支
            selection: {"entryId": str, "start": int, "end": int, "text": str}
            context_ids: 要继承的 entry id 列表
            text: 用户的新问题

        Returns:
            新 branch_id
        """
        ...

    def keep(self, branch_id: str) -> None:
        """切换收藏状态（kept ↔ unkept）。"""
        ...

    def add_tags(self, branch_id: str, tags: list[str]) -> None:
        """给分支加 tag。"""
        ...

    def delete_branch(self, branch_id: str) -> None:
        """删除分支（级联 / detach 取决于实现）。"""
        ...

    # ---- 生命周期 ----

    def reset(self) -> None:
        """清空整个 state（回到空 workspace）。"""
        ...


__all__ = ["IChatBackend"]
