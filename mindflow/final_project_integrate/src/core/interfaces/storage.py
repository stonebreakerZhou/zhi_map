"""⭐ 思维导图存储接口（核心抽象 3/4）。

任何 MindMap 存储都要实现此 Protocol：
- SQLiteStorage（包装 mindmap_repo / SQLite）
- JsonStorage（导出 / 备份）
- InMemoryStorage（测试用）

Service 层（MindMapService）只依赖此接口。

P3 负责维护。
"""

from __future__ import annotations

from typing import Protocol


class IMindMapStorage(Protocol):
    """⭐ 思维导图存储接口。"""

    # ---- MindMap CRUD ----

    def create_mindmap(self, title: str, description: str = "") -> str:
        """创建新 MindMap。

        Returns:
            mindmap_id
        """
        ...

    def list_mindmaps(self) -> list[dict]:
        """列出所有导图。

        Returns:
            [{"id", "title", "description", "updated_at", ...}, ...]
        """
        ...

    def get_mindmap(self, mindmap_id: str) -> dict | None:
        """获取单个 MindMap 元信息（含 root_node_id）。"""
        ...

    def update_mindmap_title(self, mindmap_id: str, title: str) -> None: ...

    def delete_mindmap(self, mindmap_id: str) -> None:
        """级联删除节点 + 边 + 附件。"""
        ...

    # ---- Node CRUD ----

    def add_node(
        self,
        mindmap_id: str,
        text: str,
        parent_id: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
        color: str = "#4A90E2",
    ) -> str:
        """添加节点。

        Returns:
            node_id
        """
        ...

    def get_nodes(self, mindmap_id: str) -> list[dict]:
        """获取 MindMap 的所有节点。

        Returns:
            [{"id", "text", "note", "color", "pos_x", "pos_y", "parent_id", "image_path", ...}, ...]
        """
        ...

    def update_node_text(self, node_id: str, text: str) -> None: ...

    def update_node_note(self, node_id: str, note: str) -> None: ...

    def update_node_position(self, node_id: str, x: float, y: float) -> None: ...

    def update_node_color(self, node_id: str, color: str) -> None: ...

    def delete_node(self, node_id: str) -> None: ...

    # ---- Edge CRUD（附加边）----

    def add_edge(self, mindmap_id: str, source_id: str, target_id: str) -> int | None:
        """添加附加边。

        Returns:
            edge_id（int），失败（自环/重复/节点不存在）返回 None
        """
        ...

    def delete_edge(self, edge_id: int) -> None: ...

    def get_edges(self, mindmap_id: str) -> list[dict]:
        """获取所有附加边。
        Returns:
            [{"id", "source_id", "target_id"}, ...]
        """
        ...


__all__ = ["IMindMapStorage"]
