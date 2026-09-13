"""⭐ 具体后端实现。

每个文件实现 ``src.core.interfaces`` 里的一个 Protocol：
- ``zhishu_http_chat_backend.py`` → ``IChatBackend``（HTTP 调 zhi_map FastAPI）
- ``mock_chat_backend.py``       → ``IChatBackend``（内存版，无网络）
- ``mock_provider.py``           → ``IAIProvider``（本地固定回复）
- ``sqlite_storage.py``          → ``IMindMapStorage``（包装 mindmap_repo）

通过 DI 容器（``src.core.container``）按配置选择实现。
可以自由组合，例如：
- ZhishuHttpChatBackend + MockProvider + SQLiteStorage（接 zhi_map FastAPI）
- MockChatBackend + MockProvider + SQLiteStorage（纯本地演示）

未实现的 provider（Anthropic / OpenAI HTTP 客户端）暂留空，由未来 PR 补。
通过 DI 容器注入时如果 ``base_url`` 配 Anthropic / OpenAI 端点，会自动回退到 MockProvider。

P3 负责维护。
"""

from __future__ import annotations

from src.backends.mock_chat_backend import MockChatBackend
from src.backends.mock_provider import MockProvider
from src.backends.sqlite_storage import SQLiteStorage
from src.backends.zhishu_http_chat_backend import ZhishuHttpChatBackend

__all__ = [
    # Chat backends
    "MockChatBackend",
    "ZhishuHttpChatBackend",
    # AI providers
    "MockProvider",
    # Storage
    "SQLiteStorage",
]
