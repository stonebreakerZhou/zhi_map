"""SQLAlchemy ORM 模型。

设计 4 张表：
- mindmaps: 思维导图元信息
- nodes:    思维导图节点（带父子层级、位置、颜色、笔记）
- edges:    节点之间的连线（虽然节点本身有 parent_id，但 edge 用于跨层级）
- search_history: AI 搜索历史（用于"最近搜索"功能）

P3 负责维护，P1 重构优化。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _gen_uuid() -> str:
    """生成节点/导图 ID。"""
    return str(uuid.uuid4())


class MindMap(Base):
    """思维导图元信息。"""

    __tablename__ = "mindmaps"

    id = Column(String, primary_key=True, default=_gen_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    root_node_id = Column(String, nullable=True)  # 缓存根节点，方便快速定位
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 关系：一对多导图→节点（级联删除）
    nodes = relationship(
        "Node",
        back_populates="mindmap",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<MindMap {self.id[:8]} {self.title!r}>"


class Node(Base):
    """思维导图节点。"""

    __tablename__ = "nodes"

    id = Column(String, primary_key=True, default=_gen_uuid)
    mindmap_id = Column(
        String,
        ForeignKey("mindmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id = Column(
        String,
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    text = Column(String, nullable=False, default="新节点")
    note = Column(Text, default="")  # 用户的笔记/备注
    color = Column(String, default="#4A90E2")

    pos_x = Column(Float, default=0.0)
    pos_y = Column(Float, default=0.0)

    is_expanded = Column(Boolean, default=True)
    search_source = Column(String, nullable=True)  # 'duckduckgo' | 'wikipedia' | None

    # ⭐ 新增：节点挂图（手写笔记图片）—— 核心功能
    image_path = Column(String, nullable=True)  # 相对路径：images/abc123.jpg
    image_caption = Column(String, nullable=True)  # 图片说明（可选）

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    mindmap = relationship("MindMap", back_populates="nodes")

    def __repr__(self) -> str:
        return f"<Node {self.id[:8]} {self.text!r}>"


class NodeAttachment(Base):
    """⭐ 节点附件（一对多：1 节点 → N 张图/文档）。

    替代老的 Node.image_path 单图字段。新增/查看附件走这里。
    旧的 image_path 在启动时由 migration 一次性搬到这里（_migration.py）。
    """

    __tablename__ = "node_attachments"

    id = Column(String, primary_key=True, default=_gen_uuid)
    node_id = Column(
        String,
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path = Column(
        String, nullable=False
    )  # 相对路径：images/abc.jpg 或 docs/abc.md
    file_type = Column(String, default="image")  # 'image' | 'document'
    caption = Column(String, nullable=True)  # 可选说明
    sort_order = Column(Integer, default=0)  # 用户排序（小的在前）
    is_cover = Column(Boolean, default=False)  # 是否主图（封面）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<NodeAttachment {self.id[:8]} {self.file_type} {self.file_path}>"


class Edge(Base):
    """节点间的额外连线（一般节点通过 parent_id 表达层级，Edge 用于跨分支）。"""

    __tablename__ = "edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mindmap_id = Column(
        String,
        ForeignKey("mindmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(
        String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id = Column(
        String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Edge {self.source_id[:8]} -> {self.target_id[:8]}>"


class SearchHistory(Base):
    """AI 搜索历史。"""

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String, nullable=False)
    source = Column(String, nullable=False)  # 'duckduckgo' | 'wikipedia'
    result_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<SearchHistory {self.source} {self.query!r}>"
