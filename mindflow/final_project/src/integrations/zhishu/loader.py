"""读取并校验知树 (Zhishu) 导出的 workspace JSON 文件。

输入格式（来自 zhi_map 后端 ``GET /api/export``）::

    {
        "schemaVersion": 2,
        "state": {
            "version": 2,
            "sessions": [{"id": "...", "title": "..."}, ...],
            "branches": [Branch, ...],
            "active": "<branch_id>" | null
        }
    }

约定：
- 只接受 schemaVersion=2；老版本（v1）或未来版本抛 ``LoaderError``。
- 用 ``app.domain.validate_state`` 做权威 schema 校验（zhi_map 的强校验）。
- 不修改输入字典（深拷贝后操作）。

P3 负责维护。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.integrations.zhishu._domain import validate_state
from src.utils.logger import get_logger

logger = get_logger("mindflow.zhishu.loader")


class LoaderError(ValueError):
    """加载 / 校验知树导出文件失败。"""


SUPPORTED_SCHEMA_VERSION = 2


def load_export_file(path: str | Path) -> dict[str, Any]:
    """读取 JSON 导出文件并校验 schema。

    Args:
        path: 知树 ``/api/export`` 导出的 JSON 文件路径。

    Returns:
        深拷贝后的导出字典 ``{"schemaVersion": int, "state": {...}}``。

    Raises:
        LoaderError: 文件不存在 / 不是 JSON / schema 不匹配 / state 不合法。
    """
    p = Path(path)
    if not p.is_file():
        raise LoaderError(f"文件不存在：{p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"不是合法 JSON：{exc}") from exc
    except UnicodeDecodeError as exc:
        raise LoaderError(f"不是 UTF-8 文本：{exc}") from exc

    if not isinstance(raw, dict):
        raise LoaderError(f"顶层不是 dict，实际 {type(raw).__name__}")

    version = raw.get("schemaVersion")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise LoaderError(
            f"schemaVersion={version} 不受支持，当前仅支持 {SUPPORTED_SCHEMA_VERSION}"
        )

    state = raw.get("state")
    if not isinstance(state, dict):
        raise LoaderError("缺少 state 字段或不是 dict")

    # ⭐ 用 zhi_map 自带的 validate_state 做权威 schema 校验
    #    失败时 DomainError(ValueError) 会被抛出
    try:
        state = validate_state(state)
    except (ValueError, TypeError) as exc:
        raise LoaderError(f"state schema 不合法：{exc}") from exc

    # 二次校验：sessions / branches 至少要有 1 个
    if not state["sessions"]:
        raise LoaderError("state.sessions 为空，没有可导入的内容")

    logger.info(
        f"知树导出已校验通过: schemaVersion={version}, "
        f"sessions={len(state['sessions'])}, branches={len(state['branches'])}"
    )
    return copy.deepcopy({"schemaVersion": version, "state": state})


def load_export_text(text: str) -> dict[str, Any]:
    """从字符串解析（用于测试 / 粘贴导入场景）。"""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LoaderError(f"不是合法 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise LoaderError(f"顶层不是 dict，实际 {type(raw).__name__}")
    version = raw.get("schemaVersion")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise LoaderError(
            f"schemaVersion={version} 不受支持，当前仅支持 {SUPPORTED_SCHEMA_VERSION}"
        )
    state = raw.get("state")
    if not isinstance(state, dict):
        raise LoaderError("缺少 state 字段或不是 dict")
    try:
        state = validate_state(state)
    except (ValueError, TypeError) as exc:
        raise LoaderError(f"state schema 不合法：{exc}") from exc
    if not state["sessions"]:
        raise LoaderError("state.sessions 为空")
    return copy.deepcopy({"schemaVersion": version, "state": state})


__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "LoaderError",
    "load_export_file",
    "load_export_text",
]
