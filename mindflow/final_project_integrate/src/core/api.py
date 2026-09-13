"""⭐ MindFlowAPI：统一对外门面（Track 2 收口）。

新写的代码（导入器、脚本、插件、测试）应该只用 ``MindFlowAPI``，
而不是直接 import ``mindmap_repo`` 或 ``Container``。

示例::

    from src.core.api import api
    api.storage.create_mindmap("复习计划")
    api.organize(conversation, target_mindmap_id=mid)
    api.chat.send(branch_id, "你好")
    api.close()

设计原则：
- 单例（进程内只有一个）
- 所有方法代理到底层 service（MindMapService / ChatService / OrganizationService）
- 关闭时统一释放（关闭 HTTP client 等）

P3 负责维护。
"""

from __future__ import annotations

from src.core.container import Container
from src.core.services.chat_service import ChatService
from src.core.services.mindmap_service import MindMapService
from src.core.services.organization_service import OrganizationService


class MindFlowAPI:
    """⭐ 统一对外门面（包装 Container 的 services）。"""

    def __init__(self, container: Container | None = None) -> None:
        self._container: Container = container or Container.default()
        self.storage: MindMapService = self._container.mindmap_service
        self.chat: ChatService = self._container.chat_service
        self.organize_service: OrganizationService = (
            self._container.organization_service
        )

    @property
    def container(self) -> Container:
        """暴露底层 Container（高级用法，比如换 backend）。"""
        return self._container

    # ---- 便利方法（包一层，组织常用操作）----

    def create_mindmap_with_nodes(
        self,
        title: str,
        nodes: list[dict],
        description: str = "",
    ) -> str:
        """⭐ 一站式：建 MindMap + 批量加节点。

        Args:
            title: MindMap 标题
            nodes: 节点 spec 列表，每项 = ``{"text", "parent": idx_or_text, "x", "y", "color"}``
                - ``parent`` 可以是根（"root"）或同一批里前一个节点的 text
                - 没指定 ``parent`` 的当作根的子节点
            description: MindMap 描述

        Returns:
            新 MindMap id
        """
        mindmap_id = self.storage.create_mindmap(title, description)
        root = self.storage.get_root_node(mindmap_id)
        if root is None:
            root_id = self.storage.add_node(mindmap_id, "中心", x=0.0, y=0.0)
        else:
            root_id = root["id"]

        text_to_id: dict[str, str] = {"root": root_id}
        for spec in nodes:
            parent = spec.get("parent", "root")
            parent_id = text_to_id.get(
                parent if isinstance(parent, str) else "",
                root_id,
            )
            nid = self.storage.add_node(
                mindmap_id=mindmap_id,
                text=spec["text"],
                parent_id=parent_id,
                x=float(spec.get("x", 0.0)),
                y=float(spec.get("y", 0.0)),
                color=str(spec.get("color", "#4A90E2")),
            )
            text_to_id[spec["text"]] = nid
        return mindmap_id

    def organize_conversation(
        self,
        conversation: str,
        *,
        target_mindmap_id: str | None = None,
        max_points: int = 5,
    ) -> str:
        """⭐ 把对话整理成 MindMap 节点（包装 OrganizationService.organize）。"""
        return self.organize_service.organize(
            conversation,
            target_mindmap_id=target_mindmap_id,
            max_points=max_points,
        )

    # ---- 生命周期 ----

    def close(self) -> None:
        """⭐ 释放资源（关 HTTP client 等）。"""
        backend = self._container.chat_backend
        close = getattr(backend, "close", None)
        if callable(close):
            close()


# ⭐ 模块级单例（懒加载）
_api: MindFlowAPI | None = None


def api() -> MindFlowAPI:
    """⭐ 拿全局单例（懒加载，首次访问时构造）。"""
    global _api
    if _api is None:
        _api = MindFlowAPI()
    return _api


def reset_api() -> None:
    """重置（测试用：丢弃旧单例）。"""
    global _api
    _api = None


__all__ = ["MindFlowAPI", "api", "reset_api"]