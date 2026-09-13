"""MindFlow 核心接口层（Protocol 抽象基类）。

所有具体实现（zhi_map_chat_backend / anthropic_provider / sqlite_storage 等）
必须实现这里的 Protocol。UI / Service 层只依赖接口，不接触实现。

P3 负责维护。
"""

from src.core.interfaces.ai import IAIProvider
from src.core.interfaces.chat import IChatBackend
from src.core.interfaces.organization import IOrganizationService
from src.core.interfaces.storage import IMindMapStorage

__all__ = [
    "IAIProvider",
    "IChatBackend",
    "IMindMapStorage",
    "IOrganizationService",
]
