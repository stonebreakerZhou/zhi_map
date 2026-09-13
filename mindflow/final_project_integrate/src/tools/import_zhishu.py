"""命令行工具：从知树 (Zhishu) 导出文件导入到 MindFlow 数据库。

用法::

    PYTHONIOENCODING=utf-8 python -m src.tools.import_zhishu <export.json>
    PYTHONIOENCODING=utf-8 python -m src.tools.import_zhishu --from-seed   # 演示：用 zhi_map seed_state 测试

退出码：0 = 全部成功；1 = 部分失败；2 = 输入错误。

P3 负责维护。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 把项目根加到 sys.path，确保 python -m 调用能找到模块
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.integrations.zhishu import (
    LoaderError,
    convert_state,
    import_converted,
    load_export_text,
)
from src.integrations.zhishu._domain import seed_state
from src.storage.db import init_db
from src.utils.logger import get_logger, setup_logger


def _build_demo_export() -> str:
    """生成一份演示用的 zhi_map export 字符串（不依赖外部文件）。"""
    state = seed_state()
    return json.dumps({"schemaVersion": 2, "state": state}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从知树 (Zhishu) 导出文件导入到 MindFlow 数据库"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="知树 /api/export 导出的 JSON 文件路径；省略则用 --from-seed 演示",
    )
    parser.add_argument(
        "--from-seed",
        action="store_true",
        help="忽略 path 参数，用 zhi_map seed_state() 内置演示数据",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只输出最终统计",
    )
    args = parser.parse_args(argv)

    setup_logger()
    logger = get_logger("mindflow.tools.import_zhishu")

    # 1. 准备输入
    if args.from_seed or not args.path:
        if not args.quiet:
            print("▶ 用 zhi_map 内置 seed_state 演示数据生成 export ...")
        export_text = _build_demo_export()
    else:
        path = Path(args.path)
        if not path.is_file():
            print(f"✗ 文件不存在：{path}", file=sys.stderr)
            return 2
        if not args.quiet:
            print(f"▶ 读取：{path}")
        export_text = path.read_text(encoding="utf-8")

    # 2. 校验 + 转换
    try:
        loaded = load_export_text(export_text)
    except LoaderError as exc:
        print(f"✗ 文件解析失败：{exc}", file=sys.stderr)
        return 2

    state = loaded["state"]
    if not args.quiet:
        print(f"  sessions={len(state['sessions'])}, branches={len(state['branches'])}")

    result = convert_state(state)
    if not args.quiet:
        print(f"  → 转换出 {len(result.mindmaps)} 个 MindMap")

    # 3. 入库
    init_db()
    progress_lines: list[str] = []

    def on_progress(idx, total, title):
        progress_lines.append(f"  [{idx}/{total}] {title}")

    import_result = import_converted(result, on_progress=on_progress)
    if not args.quiet:
        for line in progress_lines:
            print(line)

    # 4. 报告
    print()
    print("=" * 50)
    print(
        f"✅ 成功导入 {len(import_result.mindmap_ids)} / {len(result.mindmaps)} 个 MindMap"
    )
    print(f"   总节点数：{import_result.total_nodes}")
    if import_result.failures:
        print(f"⚠️ 失败 {len(import_result.failures)} 个：")
        for f in import_result.failures:
            print(f"   - {f}")
        return 1

    if import_result.mindmap_ids:
        print("\n新增 MindMap ID：")
        for mid in import_result.mindmap_ids:
            print(f"  - {mid}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
