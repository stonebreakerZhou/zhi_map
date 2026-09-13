"""知树 (Zhishu) ↔ MindFlow 桥接层。

Phase 1：单向导入（zhishu → MindFlow）
- loader    : 读 /api/export JSON，校验 schema
- converter : state → MindMap 数据（自动布局 + Markdown 拼接）
- importer  : 写入 mindmap_repo

后续阶段可扩展：
- 双向导出（MindFlow → zhishu workspace JSON）
- AI 对话集成（直接调 transition() 状态机）
- 选区展开分支（用 Qt 重新实现 selection.ts 的 UX）

P3 负责维护。
"""

from __future__ import annotations

from src.integrations.zhishu.converter import (
    ConvertedMindMap,
    ConvertResult,
    convert_state,
)
from src.integrations.zhishu.importer import ImportResult, import_converted
from src.integrations.zhishu.loader import (
    SUPPORTED_SCHEMA_VERSION,
    LoaderError,
    load_export_file,
    load_export_text,
)

__all__ = [
    # loader
    "LoaderError",
    "load_export_file",
    "load_export_text",
    "SUPPORTED_SCHEMA_VERSION",
    # converter
    "convert_state",
    "ConvertResult",
    "ConvertedMindMap",
    # importer
    "import_converted",
    "ImportResult",
]
