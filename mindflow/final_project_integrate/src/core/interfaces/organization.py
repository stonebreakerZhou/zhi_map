"""⭐ 对话 → 思维导图 组织服务接口（核心抽象 4/4）。

任何"把对话整理成导图"的策略都要实现此 Protocol：
- LLMOrganizationService（用 AI 抽要点）
- KeywordOrganizationService（用关键词抽取 / 启发式）
- HybridOrganizationService（LLM + 启发式结合）

P3 负责维护。
"""

from __future__ import annotations

from typing import Protocol


class IOrganizationService(Protocol):
    """⭐ 对话 → 思维导图 组织服务。"""

    def organize(
        self,
        conversation: str,
        *,
        target_mindmap_id: str | None = None,
        max_points: int = 5,
    ) -> str:
        """⭐ 把一段对话整理成 MindMap 节点。

        流程（实现方定义）：
        1. 用某种策略从 conversation 抽取 N 个要点（max_points 上限）
        2. 找 target_mindmap（或新建）的根节点
        3. 每个要点 → 一个 MindMap 子节点（颜色 / 位置可自定）

        Args:
            conversation: 完整对话文本
            target_mindmap_id: 目标 MindMap；None 表示新建
            max_points: 最多生成几个要点节点

        Returns:
            目标 MindMap 的 id（新建时返回新 id）
        """
        ...


__all__ = ["IOrganizationService"]
