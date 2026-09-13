"""⭐ AI 服务接口（核心抽象 2/4）。

任何 AI 服务都要实现此 Protocol：
- AnthropicProvider（Anthropic Messages API）
- OpenAIProvider（OpenAI Chat Completions）
- MockProvider（无网络，固定回复）
- 本地 LLM provider（Ollama / llama.cpp 等）

Service 层（OrganizationService 等）只依赖此接口。

P3 负责维护。
"""

from __future__ import annotations

from typing import Protocol


class IAIProvider(Protocol):
    """⭐ AI 服务接口：对话 + 要点抽取 + 预留 rerank。"""

    def complete_chat(self, messages: list[dict]) -> str:
        """聊天补全。

        Args:
            messages: OpenAI 格式 [{"role": "user"|"assistant"|"system", "content": str}]

        Returns:
            AI 回答文本。

        Raises:
            RuntimeError: 调用失败。
        """
        ...

    def extract_keypoints(
        self,
        conversation: str,
        *,
        max_points: int = 5,
    ) -> list[str]:
        """⭐ 从一段对话里抽关键要点。

        Args:
            conversation: 完整对话文本
            max_points: 最多抽多少条

        Returns:
            要点字符串列表。
        """
        ...

    def rerank(self, query: str, candidates: list[dict]) -> list[str]:
        """⭐ 预留：对候选项按与 query 的相关性排序（用于跨分支搜索）。

        Returns:
            按相关性降序的 candidate id 列表。
        """
        ...

    # ---- 元信息 ----

    @property
    def provider_name(self) -> str:
        """AI 提供商标识（用于 UI 显示：'Anthropic' / 'OpenAI' / 'Mock'）。"""
        ...


__all__ = ["IAIProvider"]
