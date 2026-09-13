"""⭐ MindMapService：思维导图 CRUD 包装 + 批量同步工具。

封装 ``IMindMapStorage`` 的常用操作，给 Service 层（OrganizationService）用。
UI 层（MindMapView）继续直接用底层 ``mindmap_repo``（不强制迁移）。

P3 负责维护。
"""

from __future__ import annotations

from src.core.interfaces.storage import IMindMapStorage


class MindMapService:
    """⭐ 思维导图业务服务。"""

    def __init__(self, storage: IMindMapStorage):
        self._storage = storage

    # ==================== MindMap CRUD ====================

    def create_mindmap(self, title: str, description: str = "") -> str:
        return self._storage.create_mindmap(title, description)

    def list_mindmaps(self) -> list[dict]:
        return self._storage.list_mindmaps()

    def get_mindmap(self, mindmap_id: str) -> dict | None:
        return self._storage.get_mindmap(mindmap_id)

    def delete_mindmap(self, mindmap_id: str) -> None:
        self._storage.delete_mindmap(mindmap_id)

    # ==================== Node 操作 ====================

    def add_node(
        self,
        mindmap_id: str,
        text: str,
        parent_id: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
        color: str = "#4A90E2",
    ) -> str:
        return self._storage.add_node(mindmap_id, text, parent_id, x, y, color)

    def get_nodes(self, mindmap_id: str) -> list[dict]:
        return self._storage.get_nodes(mindmap_id)

    def get_root_node(self, mindmap_id: str) -> dict | None:
        """获取 MindMap 的根节点（parent_id is None 的第一个）。"""
        return next(
            (n for n in self._storage.get_nodes(mindmap_id) if n["parent_id"] is None),
            None,
        )

    def update_node_text(self, node_id: str, text: str) -> None:
        self._storage.update_node_text(node_id, text)

    def update_node_note(self, node_id: str, note: str) -> None:
        self._storage.update_node_note(node_id, note)

    def delete_node(self, node_id: str) -> None:
        self._storage.delete_node(node_id)

    # ==================== Edge 操作 ====================

    def add_edge(self, mindmap_id: str, source_id: str, target_id: str) -> int | None:
        return self._storage.add_edge(mindmap_id, source_id, target_id)

    def delete_edge(self, edge_id: int) -> None:
        self._storage.delete_edge(edge_id)

    def get_edges(self, mindmap_id: str) -> list[dict]:
        return self._storage.get_edges(mindmap_id)

    # ==================== 批量同步 ====================

    def bulk_add_keypoints(
        self,
        mindmap_id: str,
        root_id: str,
        points: list[str],
        colors: list[str] | None = None,
    ) -> list[str]:
        """⭐ 批量加要点节点（用于 OrganizationService）。

        默认布局：弧形 / 扇形分布在 root 节点右侧。
        Returns: 节点 id 列表（与 points 一一对应）。
        """
        if not points:
            return []
        default_colors = [
            "#4A90E2",
            "#E74C3C",
            "#F39C12",
            "#27AE60",
            "#8E44AD",
            "#3498DB",
        ]
        if colors is None:
            colors = [
                default_colors[i % len(default_colors)] for i in range(len(points))
            ]

        # 找到 root 的位置
        root_node = self.get_root_node(mindmap_id)
        if root_node is None:
            base_x, base_y = 300.0, 300.0
        else:
            base_x = root_node["pos_x"] + 300.0
            base_y = root_node["pos_y"]

        n = len(points)
        node_ids: list[str] = []
        for i, (point, color) in enumerate(zip(points, colors)):
            # 扇形布局：第 i 个在 (base_x + 250, base_y + (i - n/2) * 120)
            x = base_x + 250.0
            y = base_y + (i - n / 2) * 120
            nid = self._storage.add_node(
                mindmap_id=mindmap_id,
                text=point,
                parent_id=root_id,
                x=x,
                y=y,
                color=color,
            )
            node_ids.append(nid)
        return node_ids


__all__ = ["MindMapService"]
