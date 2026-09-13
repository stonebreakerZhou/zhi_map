"""AI 节点建议生成器。

输入：用户搜索词
输出：候选节点关键词列表

当前为骨架实现（本地规则），P2 会替换为 DuckDuckGo + Wikipedia 真实搜索。

P2 负责维护。
"""

from __future__ import annotations

from src.utils.logger import get_logger

logger = get_logger("mindflow.ai_search.node_suggester")


def suggest_nodes(query: str, max_count: int = 5) -> list[str]:
    """根据搜索词返回候选节点列表。

    Args:
        query: 搜索关键词
        max_count: 最多返回几个候选

    Returns:
        候选节点文本列表
    """
    logger.info(f"AI 搜索: {query}")

    # 骨架实现：把 query 拆词 + 简单联想
    # 真实实现（P2 完成）：
    # - DuckDuckGo 搜索 query → 抓取 related topics
    # - Wikipedia API 获取摘要 → 抽取关键词
    # - 合并去重，返回 top N

    suggestions = _local_suggest(query, max_count)
    logger.info(f"AI 搜索返回 {len(suggestions)} 个候选")
    return suggestions


def _local_suggest(query: str, max_count: int) -> list[str]:
    """本地规则建议（骨架版本）。

    简单策略：
    1. 查询词本身
    2. 常见后缀联想（定义、用法、原理、例子、优缺点）
    3. 常见前缀（什么是、如何理解、为什么需要）
    """
    base = query.strip()
    if not base:
        return []

    candidates = [
        f"{base} 是什么",
        f"{base} 的定义",
        f"{base} 的用法",
        f"{base} 的原理",
        f"{base} 的例子",
        f"{base} 与其他概念的区别",
        f"为什么需要 {base}",
        f"{base} 的优缺点",
        f"{base} 的应用场景",
        f"{base} 学习路线",
    ]
    return candidates[:max_count]


# ==================== 真实实现接口（占位）====================
# P2 完成后启用：

# def suggest_nodes(query: str, max_count: int = 5) -> List[str]:
#     """真实 AI 搜索版本。"""
#     from src.ai_search.search_engine import SearchEngine
#     engine = SearchEngine()
#     results = engine.search(query, max_count)
#     return [r.title for r in results]
