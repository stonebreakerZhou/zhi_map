"""一次性数据迁移：把旧 Node.image_path 单图字段搬到 node_attachments 表。

触发条件：init_db() 后调用 ensure_attachment_migration()
- 扫描所有 node.image_path IS NOT NULL 的节点
- 为每个节点创建一条 NodeAttachment 记录（is_cover=True）
- 迁移成功后把 node.image_path 清空（但保留字段，向后兼容）
- 幂等：第二次运行什么都不做（image_path 已全清）

P4 负责维护。
"""

from __future__ import annotations

from src.storage.db import session_scope
from src.storage.schema import Node, NodeAttachment
from src.utils.logger import get_logger

logger = get_logger("mindflow.storage.migration")


def ensure_attachment_migration() -> int:
    """执行一次性迁移。

    Returns:
        迁移的附件数（首次为 0 表示已迁移或没有旧数据）。
    """
    migrated = 0
    with session_scope() as session:
        # 找出所有有 image_path 但还没迁的节点
        nodes_with_legacy = (
            session.query(Node)
            .filter(
                Node.image_path.isnot(None),
                Node.image_path != "",
            )
            .all()
        )

        if not nodes_with_legacy:
            logger.debug("无需迁移：没有遗留 image_path 数据")
            return 0

        for node in nodes_with_legacy:
            # 检查是否已经有同 file_path 的附件（避免重复）
            existing = (
                session.query(NodeAttachment)
                .filter_by(
                    node_id=node.id,
                    file_path=node.image_path,
                )
                .first()
            )

            if existing:
                # 已经迁移过了，清字段
                node.image_path = None
                node.image_caption = None
                continue

            # 创建附件（主图 = 封面）
            att = NodeAttachment(
                node_id=node.id,
                file_path=node.image_path,
                file_type="image",
                caption=node.image_caption,
                is_cover=True,
                sort_order=0,
            )
            session.add(att)

            # 清空旧字段（保留字段存在，但不再使用）
            node.image_path = None
            node.image_caption = None

            migrated += 1
            logger.info(
                f"迁移节点 {node.id[:8]} 的旧图 → node_attachments: {node.image_path}"
            )

    if migrated:
        logger.info(f"✅ 迁移完成，共迁移 {migrated} 个节点的旧图")
    return migrated


__all__ = ["ensure_attachment_migration"]
