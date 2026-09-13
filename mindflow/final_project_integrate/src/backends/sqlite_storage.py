"""⭐ SQLiteStorage：把 ``mindmap_repo`` 包成 ``IMindMapStorage``。

薄包装：UI / Service 通过这个接口调存储，``mindmap_repo`` 的具体实现（SQLite + SQLAlchemy）
可以随时替换（JSON 文件 / 内存 / 远端 HTTP）。

P3 负责维护。
"""

from __future__ import annotations

from src.storage import mindmap_repo


class SQLiteStorage:
    """⭐ SQLite 实现 ``IMindMapStorage``（包装现有 mindmap_repo）。"""

    # ==================== MindMap CRUD ====================

    def create_mindmap(self, title: str, description: str = "") -> str:
        return mindmap_repo.create_mindmap(title, description)

    def list_mindmaps(self) -> list[dict]:
        return mindmap_repo.list_mindmaps()

    def get_mindmap(self, mindmap_id: str) -> dict | None:
        return mindmap_repo.get_mindmap(mindmap_id)

    def update_mindmap_title(self, mindmap_id: str, title: str) -> None:
        mindmap_repo.update_mindmap_title(mindmap_id, title)

    def delete_mindmap(self, mindmap_id: str) -> None:
        mindmap_repo.delete_mindmap(mindmap_id)

    # ==================== Node CRUD ====================

    def add_node(
        self,
        mindmap_id: str,
        text: str,
        parent_id: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
        color: str = "#4A90E2",
    ) -> str:
        return mindmap_repo.add_node(
            mindmap_id=mindmap_id,
            text=text,
            parent_id=parent_id,
            x=x,
            y=y,
            color=color,
        )

    def get_nodes(self, mindmap_id: str) -> list[dict]:
        """返回 dict 列表（兼容 IMindMapStorage 接口）。"""
        nodes = mindmap_repo.get_nodes(mindmap_id)
        result: list[dict] = []
        for n in nodes:
            result.append(
                {
                    "id": n.id,
                    "mindmap_id": n.mindmap_id,
                    "parent_id": n.parent_id,
                    "text": n.text,
                    "note": n.note,
                    "color": n.color,
                    "pos_x": n.pos_x,
                    "pos_y": n.pos_y,
                    "image_path": n.image_path,
                    "image_caption": n.image_caption,
                    "is_expanded": n.is_expanded,
                    "search_source": n.search_source,
                }
            )
        return result

    def update_node_text(self, node_id: str, text: str) -> None:
        mindmap_repo.update_node_text(node_id, text)

    def update_node_note(self, node_id: str, note: str) -> None:
        mindmap_repo.update_node_note(node_id, note)

    def update_node_position(self, node_id: str, x: float, y: float) -> None:
        mindmap_repo.update_node_position(node_id, x, y)

    def update_node_color(self, node_id: str, color: str) -> None:
        mindmap_repo.update_node_color(node_id, color)

    def delete_node(self, node_id: str) -> None:
        mindmap_repo.delete_node(node_id)

    # ==================== Edge CRUD ====================

    def add_edge(self, mindmap_id: str, source_id: str, target_id: str) -> int | None:
        return mindmap_repo.add_edge(mindmap_id, source_id, target_id)

    def delete_edge(self, edge_id: int) -> None:
        mindmap_repo.delete_edge(edge_id)

    def get_edges(self, mindmap_id: str) -> list[dict]:
        return mindmap_repo.get_edges(mindmap_id)


__all__ = ["SQLiteStorage"]
