"""⭐ MockProvider：本地内存 AI 实现（无网络，固定回复）。

满足 ``IAIProvider`` Protocol。用于：
- 默认无 AI key 时
- 离线演示
- 测试

P3 负责维护。
"""

from __future__ import annotations

from src.utils.logger import get_logger

logger = get_logger("mindflow.backends.mock_provider")


class MockProvider:
    """⭐ 内存 AI provider（满足 IAIProvider）。"""

    @property
    def provider_name(self) -> str:
        return "Mock"

    def complete_chat(self, messages: list[dict]) -> str:
        """固定回复：回显最后一条 user 消息 + 装饰。"""
        if not messages:
            return "(空对话)"
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return f"（Mock AI）你刚才说：{last_user}"

    def extract_keypoints(
        self,
        conversation: str,
        *,
        max_points: int = 5,
    ) -> list[str]:
        """按句号 / 换行切，凑够 max_points 条占位要点。"""
        if not conversation:
            return []
        # 朴素切分：以句末标点 / 换行
        import re

        sentences = [
            s.strip() for s in re.split(r"[。！？!?\.\n]+", conversation) if s.strip()
        ]
        if not sentences:
            sentences = [conversation[:50]]
        return [f"要点{i + 1}：{s[:40]}" for i, s in enumerate(sentences[:max_points])]

    def rerank(self, query: str, candidates: list[dict]) -> list[str]:
        """朴素 rerank：原序返回。"""
        return [c.get("id", "") for c in candidates]


__all__ = ["MockProvider"]
