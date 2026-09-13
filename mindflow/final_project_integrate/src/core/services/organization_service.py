"""⭐ OrganizationService：把对话整理成 MindMap 节点（实现 ``IOrganizationService``）。

策略：
- 用 ``IAIProvider.extract_keypoints()`` 抽要点（mock / anthropic / openai）
- 找目标 MindMap 根节点，新建则建空导图
- 每个要点 → 一个 MindMap 子节点（位置：root 右侧弧形分布）

P3 负责维护。
"""

from __future__ import annotations

from src.core.interfaces.ai import IAIProvider
from src.core.interfaces.organization import IOrganizationService
from src.core.services.mindmap_service import MindMapService
from src.utils.logger import get_logger

logger = get_logger("mindflow.core.services.organization_service")


class OrganizationService(IOrganizationService):
    """⭐ 默认组织服务：AI 抽要点 + MindMapService 批量落库。"""

    def __init__(
        self,
        ai_provider: IAIProvider,
        mindmap_service: MindMapService,
    ) -> None:
        self._ai = ai_provider
        self._mm = mindmap_service

    def organize(
        self,
        conversation: str,
        *,
        target_mindmap_id: str | None = None,
        max_points: int = 5,
    ) -> str:
        """⭐ 把一段对话整理成 MindMap 节点。

        Args:
            conversation: 完整对话文本
            target_mindmap_id: 目标 MindMap；None 表示新建
            max_points: 最多生成几个要点节点

        Returns:
            目标 MindMap 的 id（新建时返回新 id）
        """
        # 1) AI 抽要点
        try:
            keypoints = self._ai.extract_keypoints(conversation, max_points=max_points)
        except Exception as exc:
            logger.warning(f"AI extract_keypoints 失败：{exc}；回退到朴素切分")
            keypoints = _naive_split(conversation, max_points)

        if not keypoints:
            logger.warning("AI 没抽出要点；返回原 MindMap id")
            if target_mindmap_id is None:
                target_mindmap_id = self._mm.create_mindmap("（空）")
            return target_mindmap_id

        # 2) 找 / 建 MindMap
        if target_mindmap_id is None:
            target_mindmap_id = self._mm.create_mindmap("AI 整理")
        root = self._mm.get_root_node(target_mindmap_id)
        if root is None:
            # 导图存在但无根节点 → 补一个
            root_id = self._mm.add_node(
                target_mindmap_id,
                "中心",
                x=300.0,
                y=300.0,
            )
        else:
            root_id = root["id"]

        # 3) 批量落要点
        node_ids = self._mm.bulk_add_keypoints(target_mindmap_id, root_id, keypoints)
        logger.info(
            f"organize 完成：mindmap={target_mindmap_id}, "
            f"added {len(node_ids)} keypoints via {self._ai.provider_name}"
        )
        return target_mindmap_id


def _naive_split(text: str, max_points: int) -> list[str]:
    """⭐ 朴素切分回退（AI 不可用时）。"""
    import re

    sents = [s.strip() for s in re.split(r"[。！？!?\.\n]+", text) if s.strip()]
    if not sents:
        sents = [text[:50]] if text else []
    return sents[:max_points]


__all__ = ["OrganizationService"]
