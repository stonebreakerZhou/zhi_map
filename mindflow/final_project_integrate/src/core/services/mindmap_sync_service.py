"""⭐ MindMapSyncService：跨设备同步占位（留待未来 PR）。

Phase 1 暂不实现 — 接口占位，让 DI 容器可以正常 import。
未来可通过 IMindMapStorage 替换 + 远端 WebDAV / S3 后端。

P3 负责维护。
"""

from __future__ import annotations

from src.utils.logger import get_logger

logger = get_logger("mindflow.core.services.mindmap_sync_service")


class MindMapSyncService:
    """⭐ 同步占位（no-op）。"""

    def __init__(self) -> None:
        logger.warning("MindMapSyncService 是占位实现，跨设备同步未启用")

    def push(self, mindmap_id: str) -> None:
        """⭐ push 占位 — 当前实现 no-op。"""
        logger.debug(f"push({mindmap_id}) noop")

    def pull(self, mindmap_id: str) -> str | None:
        """⭐ pull 占位 — 返回 None 表示没有可拉的远端版本。"""
        logger.debug(f"pull({mindmap_id}) noop")
        return None


__all__ = ["MindMapSyncService"]
