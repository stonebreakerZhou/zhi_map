# -*- coding: utf-8 -*-
"""PDF 导出 smoke test (需要 QGuiApplication)。

- 创建导图 + 节点（含 Markdown 笔记 + 图片附件 + 文档附件）
- 调用 export_to_pdf 输出 PDF
- 验证：1) 文件存在  2) PDF 魔数正确  3) 大小合理（>5KB 表示真渲染了内容）

PySide6 启动一次 QGuiApplication 即可满足 QPrinter 的运行需求。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import zlib
import struct
from pathlib import Path

# 让脚本从 tests/ 运行时也能找到 src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 临时切换数据目录避免污染现有 DB
TEST_DIR = Path(tempfile.mkdtemp(prefix="mindflow_pdf_test_"))
print(f"[INFO] Using temp dir: {TEST_DIR}")

# 必须在 import src 前修改 DATA_DIR
import src.config as cfg
cfg.DATA_DIR = TEST_DIR / "data"
cfg.IMAGES_DIR = cfg.DATA_DIR / "images"
cfg.DOCUMENTS_DIR = cfg.DATA_DIR / "documents"
cfg.DATABASE_PATH = cfg.DATA_DIR / "mindflow.db"
for d in (cfg.DATA_DIR, cfg.IMAGES_DIR, cfg.DOCUMENTS_DIR, TEST_DIR / "logs"):
    d.mkdir(parents=True, exist_ok=True)

# ⭐ PDF 导出需要 Qt 在场（QPrinter 依赖 Qt GUI 栈）
from PySide6.QtGui import QGuiApplication
_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from src.storage import mindmap_repo
from src.storage.attachment_manager import get_attachment_manager
from src.utils.exporter import export_to_pdf
from src.mindmap.graph import MindMapGraph


def _make_test_image(path: Path, color: tuple = (255, 100, 50)) -> None:
    """生成一张最小有效 PNG（不依赖 PIL）。"""
    r, g, b = color
    raw = b''
    raw += struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    raw += struct.pack('>I', zlib.crc32(raw[4:]) & 0xffffffff)
    pixel_data = b'\x00' + bytes([r, g, b])
    compressed = zlib.compress(pixel_data)
    raw += struct.pack('>I', len(compressed)) + b'IDAT' + compressed
    raw += struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    raw += struct.pack('>I', 0) + b'IEND'
    raw += struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    path.write_bytes(raw)


def test_pdf_export():
    mgr = get_attachment_manager()

    # 1) 准备源文件：1 图 + 1 markdown 文档
    src_img = TEST_DIR / "test.png"
    src_md = TEST_DIR / "test.md"
    _make_test_image(src_img, (200, 80, 60))
    src_md.write_text(
        "# 第一章\n\n- 极限\n- 连续\n- 导数\n\n```python\nprint('hi')\n```",
        encoding="utf-8",
    )

    # 2) 创建导图 + 节点
    mid = mindmap_repo.create_mindmap("PDF 测试", "smoke")
    nid_root = mindmap_repo.add_node(mid, "根节点")
    nid_child = mindmap_repo.add_node(mid, "子节点", parent_id=nid_root)

    # 3) 设置 note（Markdown 源码）
    note_md = """# 极限基础

> 摘录：极限不是终点，而是看世界的新角度。

## $\\varepsilon$-$N$ 语言

**定义**：$\\forall \\varepsilon > 0, \\exists N, n > N$ 时 $|a_n - L| < \\varepsilon$。

| $n$ | $a_n$ |
|----:|------:|
|   1 |  1.00 |
|  10 |  0.10 |

### 思考题

请证明 $\\lim_{n \\to \\infty} \\frac{1}{n} = 0$。
"""
    mindmap_repo.update_node_note(nid_child, note_md)

    # 4) 添加附件
    rel_img = mgr.import_attachment(src_img)
    rel_doc = mgr.import_attachment(src_md)
    assert rel_img and rel_doc
    mindmap_repo.add_attachment(nid_child, rel_img, "image", caption="测试图")
    mindmap_repo.add_attachment(nid_child, rel_doc, "document", caption="原始笔记")

    print(f"[OK] 测试数据就绪: mindmap={mid} nodes=2 atts=2")

    # 5) 加载图 + 导出 PDF
    g = mindmap_repo.load_graph(mid)
    out_pdf = TEST_DIR / "out.pdf"
    export_to_pdf("PDF 测试", g, out_pdf, "smoke description", mindmap_id=mid)

    # 6) 验证
    assert out_pdf.exists(), f"PDF 文件未生成: {out_pdf}"
    size = out_pdf.stat().st_size
    print(f"[OK] PDF 文件已生成: {out_pdf} ({size} bytes)")

    # 魔数检查：PDF 文件以 "%PDF-" 开头
    with open(out_pdf, "rb") as f:
        magic = f.read(5)
    assert magic == b"%PDF-", f"PDF 魔数错误，应为 %PDF-，实得 {magic!r}"
    print(f"[OK] PDF 魔数正确: {magic!r}")

    # 大小检查：> 5KB 表示确实渲染了内容（空 HTML 渲染通常 < 1KB）
    assert size > 5_000, f"PDF 太小 ({size} bytes)，可能没渲染内容"
    print(f"[OK] PDF 大小合理: {size} bytes (>5KB)")

    # 文件末尾检查：标准 PDF 以 %%EOF 结尾
    with open(out_pdf, "rb") as f:
        f.seek(-32, 2)  # 最后 32 字节
        tail = f.read()
    assert b"%%EOF" in tail, "PDF 应以 %%EOF 结尾（Qt 输出通常会带）"
    print(f"[OK] PDF 结尾标记正确: 含 %%EOF")

    print(f"\n[ALL PASS] PDF 导出 smoke test 通过！")
    print(f"[INFO] 生成的 PDF: {out_pdf}")
    print(f"[INFO] 临时目录保留: {TEST_DIR}")


if __name__ == "__main__":
    try:
        test_pdf_export()
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)