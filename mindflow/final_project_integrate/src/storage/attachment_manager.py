"""附件管理器。

负责节点附件的文件 I/O（图片 + 文本文档）：
- 把用户选择的文件复制到 data/images/ 或 data/documents/（UUID 命名）
- 校验格式 + 大小
- 解析路径 / 删除文件
- 类型判断工具

为什么不直接用原文件路径？
- 用户可能改原文件位置/文件名
- 数据库只存相对路径，迁移/打包/换电脑都方便

向后兼容：
- ImageManager 仍然存在，新代码优先用 AttachmentManager
- 老代码（ImageManager）的所有方法仍然可用

P4 负责维护。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.config import DATA_DIR, DOCUMENTS_DIR, IMAGES_DIR
from src.utils.logger import get_logger

logger = get_logger("mindflow.storage.attachment_manager")


# ==================== 支持的文件格式 ====================

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
DOCUMENT_EXTS = {".txt", ".md"}  # 第一版只支持文本类

MAX_IMAGE_SIZE_MB = 20
MAX_DOCUMENT_SIZE_MB = 5

# 文件大小上限（对应 file_type）
MAX_SIZE_MB = {
    "image": MAX_IMAGE_SIZE_MB,
    "document": MAX_DOCUMENT_SIZE_MB,
}

# 文本文件编码检测顺序
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1")


def detect_file_type(file_path: str | Path) -> str | None:
    """根据扩展名判断文件类型：'image' / 'document' / None（不支持）。"""
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in DOCUMENT_EXTS:
        return "document"
    return None


def get_subdir(file_type: str) -> Path:
    """根据 file_type 返回对应的存储子目录。"""
    if file_type == "image":
        return IMAGES_DIR
    if file_type == "document":
        return DOCUMENTS_DIR
    raise ValueError(f"未知 file_type: {file_type}")


def read_text_file(relative_path: str, max_chars: int = 200_000) -> str | None:
    """读取文本附件的内容（自动尝试多种编码）。

    Returns:
        文件内容字符串，失败返回 None。
        文件超过 max_chars 时截断（防止大文件卡 UI）。
    """
    abs_path = DATA_DIR / relative_path
    if not abs_path.exists():
        return None
    try:
        raw = abs_path.read_bytes()
    except Exception as e:
        logger.error(f"读取文件失败 {relative_path}: {e}")
        return None
    if len(raw) > max_chars:
        raw = raw[:max_chars]
    for enc in TEXT_ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ==================== 管理器（单例）====================


class AttachmentManager:
    """附件文件管理单例。"""

    _instance: AttachmentManager | None = None

    def __new__(cls) -> AttachmentManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ==================== 导入 ====================

    def import_attachment(self, source_path: str | Path) -> str | None:
        """导入附件：自动识别类型 → 校验 → 复制 → 返回相对路径。

        Args:
            source_path: 用户选择的源文件路径

        Returns:
            相对路径，如 "images/abc123.jpg" 或 "documents/xyz.md"
            失败返回 None
        """
        source = Path(source_path)

        if not source.exists() or not source.is_file():
            logger.error(f"文件不存在或不是普通文件: {source}")
            return None

        file_type = detect_file_type(source)
        if file_type is None:
            ext = source.suffix.lower()
            logger.error(f"不支持的附件格式: {ext}")
            return None

        size_mb = source.stat().st_size / (1024 * 1024)
        max_mb = MAX_SIZE_MB[file_type]
        if size_mb > max_mb:
            logger.error(f"附件过大: {size_mb:.1f}MB > {max_mb}MB")
            return None

        subdir = get_subdir(file_type)
        new_name = f"{uuid.uuid4().hex}{source.suffix.lower()}"
        dest = subdir / new_name

        try:
            shutil.copy2(source, dest)
            logger.info(
                f"导入{file_type}: {source.name} -> {dest.name} ({size_mb:.2f}MB)"
            )
            # 相对路径 = 子目录名 / 文件名
            return f"{subdir.name}/{new_name}"
        except Exception as e:
            logger.error(f"复制附件失败: {e}")
            return None

    # ==================== 路径解析 ====================

    def resolve_path(self, relative_path: str | None) -> Path | None:
        """相对路径 -> 绝对路径（兼容旧 ImageManager 命名）。"""
        if not relative_path:
            return None
        return DATA_DIR / relative_path

    # ==================== 删除 ====================

    def delete_attachment(self, relative_path: str) -> bool:
        """删除附件文件（不检查引用计数 — 由 repo 层处理）。"""
        abs_path = self.resolve_path(relative_path)
        if not abs_path or not abs_path.exists():
            return False
        try:
            abs_path.unlink()
            logger.info(f"删除附件: {relative_path}")
            return True
        except Exception as e:
            logger.error(f"删除附件失败: {e}")
            return False

    # ==================== 工具 ====================

    def is_image(self, relative_path: str) -> bool:
        return Path(relative_path).suffix.lower() in IMAGE_EXTS

    def is_document(self, relative_path: str) -> bool:
        return Path(relative_path).suffix.lower() in DOCUMENT_EXTS

    def get_file_type(self, relative_path: str) -> str:
        """根据路径返回 'image' / 'document'（默认 document）。"""
        if self.is_image(relative_path):
            return "image"
        return "document"


# 全局单例
_manager = AttachmentManager()


def get_attachment_manager() -> AttachmentManager:
    """获取附件管理器单例。"""
    return _manager


__all__ = [
    "DOCUMENT_EXTS",
    "IMAGE_EXTS",
    "MAX_DOCUMENT_SIZE_MB",
    "MAX_IMAGE_SIZE_MB",
    "AttachmentManager",
    "detect_file_type",
    "get_attachment_manager",
    "read_text_file",
]
