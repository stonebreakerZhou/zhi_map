"""图片文件管理器。

负责：
- 把用户拖入/选中的图片复制到 data/images/（用 UUID 命名）
- 校验图片格式
- 删除图片（引用计数=0 时才删）

为什么不直接用原文件路径？
- 用户可能改原文件位置/文件名
- 多个节点可能想用同一张图（共享 vs 复制）
- 数据库只存相对路径，迁移/打包/换电脑都方便

P3 负责维护。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.config import DATA_DIR, IMAGES_DIR
from src.utils.logger import get_logger

logger = get_logger("mindflow.storage.image_manager")


# 支持的图片格式
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
MAX_IMAGE_SIZE_MB = 20  # 单张图最大 20MB


class ImageManager:
    """图片文件管理单例。"""

    _instance: ImageManager | None = None

    def __new__(cls) -> ImageManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ==================== 图片导入 ====================

    def import_image(self, source_path: str | Path) -> str | None:
        """导入图片：复制到 data/images/，返回相对路径。

        Args:
            source_path: 用户选择的源图片路径

        Returns:
            相对路径（相对于 data/），如 "images/abc123.jpg"
            失败返回 None
        """
        source = Path(source_path)

        if not source.exists():
            logger.error(f"图片不存在: {source}")
            return None

        if not source.is_file():
            logger.error(f"不是文件: {source}")
            return None

        ext = source.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            logger.error(f"不支持的图片格式: {ext}")
            return None

        size_mb = source.stat().st_size / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            logger.error(f"图片过大: {size_mb:.1f}MB > {MAX_IMAGE_SIZE_MB}MB")
            return None

        # 用 UUID 命名，避免冲突
        new_name = f"{uuid.uuid4().hex}{ext}"
        dest = IMAGES_DIR / new_name

        try:
            shutil.copy2(source, dest)
            logger.info(f"导入图片: {source.name} -> {new_name} ({size_mb:.2f}MB)")
            return f"images/{new_name}"  # 相对路径存数据库
        except Exception as e:
            logger.error(f"复制图片失败: {e}")
            return None

    # ==================== 路径解析 ====================

    def resolve_path(self, relative_path: str | None) -> Path | None:
        """相对路径 -> 绝对路径。"""
        if not relative_path:
            return None
        return DATA_DIR / relative_path

    # ==================== 删除图片 ====================

    def delete_image(self, relative_path: str) -> bool:
        """删除图片文件。

        Returns:
            是否成功删除
        """
        abs_path = self.resolve_path(relative_path)
        if not abs_path or not abs_path.exists():
            return False

        try:
            abs_path.unlink()
            logger.info(f"删除图片: {relative_path}")
            return True
        except Exception as e:
            logger.error(f"删除图片失败: {e}")
            return False

    # ==================== 工具 ====================

    def get_absolute_path(self, relative_path: str | None) -> Path | None:
        """供 UI 层使用：拿到绝对路径用于 QPixmap 加载。"""
        return self.resolve_path(relative_path)


# 全局单例
_manager = ImageManager()


def get_image_manager() -> ImageManager:
    """获取图片管理器单例。"""
    return _manager


__all__ = ["MAX_IMAGE_SIZE_MB", "SUPPORTED_EXTS", "ImageManager", "get_image_manager"]
