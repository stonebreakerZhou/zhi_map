"""Node 纯数据类。

不依赖 SQLAlchemy 和 Qt，可在以下场景使用：
- 图遍历算法（graph.py）
- 数据传输（to_dict/from_dict）
- 单元测试

UI 显示用 src/ui/node_item.py（QGraphicsItem）。

P3 负责维护。
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime


def _gen_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class NodeData:
    """思维导图节点（UI 无关的纯数据）。"""

    text: str = "新节点"
    color: str = "#4A90E2"
    pos_x: float = 0.0
    pos_y: float = 0.0
    note: str = ""
    is_expanded: bool = True
    search_source: str | None = None
    parent_id: str | None = None
    mindmap_id: str | None = None
    id: str = field(default_factory=_gen_uuid)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # ⭐ 新增：节点挂图字段
    image_path: str | None = None  # 相对于 data/ 目录的路径，如 "images/abc123.jpg"
    image_caption: str | None = None  # 图片说明

    def to_dict(self) -> dict:
        """转字典（用于序列化/JSON 导出）。"""
        d = asdict(self)
        # datetime 转为 ISO 字符串
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> NodeData:
        """从字典反序列化。"""
        kwargs = dict(d)
        # 解析 datetime
        for key in ("created_at", "updated_at"):
            if key in kwargs and isinstance(kwargs[key], str):
                try:
                    kwargs[key] = datetime.fromisoformat(kwargs[key])
                except (ValueError, TypeError):
                    kwargs[key] = datetime.utcnow()
        # 过滤掉不在 dataclass 字段中的 key
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return cls(**kwargs)

    def __repr__(self) -> str:
        return f"NodeData(id={self.id[:8]} text={self.text!r})"


@dataclass
class EdgeData:
    """思维导图边（连线）纯数据。"""

    source_id: str
    target_id: str
    mindmap_id: str | None = None
    id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def __repr__(self) -> str:
        return f"EdgeData({self.source_id[:8]} -> {self.target_id[:8]})"
