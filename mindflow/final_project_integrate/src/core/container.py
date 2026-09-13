"""⭐ 依赖注入容器（Track 2 — 收口版）。

装配策略：
- ``IChatBackend`` → ``MockChatBackend``（默认，离线演示）
                  或 ``ZhishuHttpChatBackend(base_url=...)``（接 zhi_map FastAPI）
- ``IAIProvider`` → ``MockProvider``（默认，无网络）
- ``IMindMapStorage`` → ``SQLiteStorage``（包装现有 mindmap_repo）
- 派生：``MindMapService`` / ``ChatService`` / ``OrganizationService``

UI 启动时只调 ``Container.default()`` 拿到所有 service，不接触具体实现。
切换 zhi_map HTTP 后端通过环境变量：

    MINDFLOW_CHAT_BACKEND=http MINDFLOW_ZHI_MAP_URL=http://127.0.0.1:8000

P3 负责维护。
"""

from __future__ import annotations

import os

from src.backends import (
    MockChatBackend,
    MockProvider,
    SQLiteStorage,
    ZhishuHttpChatBackend,
)
from src.core.interfaces.ai import IAIProvider
from src.core.interfaces.chat import IChatBackend
from src.core.interfaces.organization import IOrganizationService
from src.core.interfaces.storage import IMindMapStorage
from src.core.services.chat_service import ChatService
from src.core.services.mindmap_service import MindMapService
from src.core.services.organization_service import OrganizationService
from src.utils.logger import get_logger

logger = get_logger("mindflow.core.container")


def _make_ai_provider() -> IAIProvider:
    """⭐ 选 AI provider：目前只 Mock（Anthropic/OpenAI HTTP 客户端留待未来 PR）。"""
    logger.info("AI Provider: MockProvider")
    return MockProvider()


def _make_chat_backend() -> IChatBackend:
    """⭐ 选对话后端：env MINDFLOW_CHAT_BACKEND=http 时走 HTTP，否则 Mock。"""
    backend = os.environ.get("MINDFLOW_CHAT_BACKEND", "mock").lower()
    if backend == "http":
        url = os.environ.get("MINDFLOW_ZHI_MAP_URL", "http://127.0.0.1:8000")
        logger.info(f"ChatBackend: ZhishuHttpChatBackend ({url})")
        return ZhishuHttpChatBackend(base_url=url)
    logger.info("ChatBackend: MockChatBackend（演示模式）")
    return MockChatBackend()


class Container:
    """⭐ 依赖注入容器（全局单例）。"""

    _instance: Container | None = None

    def __init__(
        self,
        *,
        chat_backend: IChatBackend | None = None,
        ai_provider: IAIProvider | None = None,
        storage: IMindMapStorage | None = None,
    ) -> None:
        self.ai_provider: IAIProvider = ai_provider or _make_ai_provider()
        self.chat_backend: IChatBackend = chat_backend or _make_chat_backend()
        self.storage: IMindMapStorage = storage or SQLiteStorage()

        # ⭐ 派生 services（按依赖链构造）
        self.mindmap_service: MindMapService = MindMapService(self.storage)
        self.chat_service: ChatService = ChatService(self.chat_backend)
        self.organization_service: IOrganizationService = OrganizationService(
            self.ai_provider,
            self.mindmap_service,
        )

        logger.info(
            f"Container 就绪：chat={type(self.chat_backend).__name__}, "
            f"ai={type(self.ai_provider).__name__}, "
            f"storage={type(self.storage).__name__}"
        )

    @classmethod
    def default(cls) -> Container:
        """⭐ 全局默认容器（单例）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置（重新创建实例）。测试时用。"""
        cls._instance = None


__all__ = ["Container"]
