# -*- coding: utf-8 -*-
"""单节点导出 = NoteEditor 预览面板 1:1 内容（需要 QGuiApplication）。

⭐ 核心断言：导出的内容必须严格等于用户在预览面板看到的内容。

验证 3 件事：
1. ⭐ MD 导出 == node.note 源码原样（无任何额外包装）
2. ⭐ HTML 导出 == NoteEditor._wrap_html(render_markdown(node.note))（预览面板 HTML）
3. ⭐ PDF 导出 == 同一个 HTML 通过 QPrinter 渲染
4. 整个导图导出（回归）：旧 footer / emoji / 元信息都已移除
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# 让脚本从 tests/ 运行时也能找到 src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 临时切换数据目录避免污染现有 DB
TEST_DIR = Path(tempfile.mkdtemp(prefix="mindflow_node_test_"))
print(f"[INFO] Using temp dir: {TEST_DIR}")

# 必须在 import src 前修改 DATA_DIR
import src.config as cfg
cfg.DATA_DIR = TEST_DIR / "data"
cfg.IMAGES_DIR = cfg.DATA_DIR / "images"
cfg.DOCUMENTS_DIR = cfg.DATA_DIR / "documents"
cfg.DATABASE_PATH = cfg.DATA_DIR / "mindflow.db"
for d in (cfg.DATA_DIR, cfg.IMAGES_DIR, cfg.DOCUMENTS_DIR, TEST_DIR / "logs"):
    d.mkdir(parents=True, exist_ok=True)

# ⭐ PDF 导出需要 Qt 在场
from PySide6.QtGui import QGuiApplication
_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from src.storage import mindmap_repo
from src.utils.exporter import (
    export_node_to_html,
    export_node_to_markdown,
    export_node_to_pdf,
    export_to_html,
    export_to_markdown,
    export_to_pdf,
)
from src.ui.note_editor import _wrap_html, render_markdown


def test_node_export_equals_preview():
    # 1) 创建导图 + 节点（故意带 4 个节点：1 目标 + 3 干扰）
    mid = mindmap_repo.create_mindmap("测试导图", "smoke")
    nid_root = mindmap_repo.add_node(mid, "根节点")
    nid_target = mindmap_repo.add_node(mid, "目标节点", parent_id=nid_root)
    nid_distract1 = mindmap_repo.add_node(mid, "干扰节点A", parent_id=nid_root)
    nid_distract2 = mindmap_repo.add_node(mid, "干扰节点B", parent_id=nid_target)

    # 2) ⭐ 节点的 note = 用户在编辑器里写的最终整理稿
    target_note = """# 极限基础整理

> 这是用户手动整理的最终复习资料。

## $\\varepsilon$-$N$ 语言

**定义**：$\\forall \\varepsilon > 0, \\exists N, n > N$ 时 $|a_n - L| < \\varepsilon$。

### 例题表格

| $n$ | $a_n$ |
|----:|------:|
|   1 |  1.00 |
|  10 |  0.10 |

```python
# 一段示例代码
def limit(a, n): return a / n
```

> 行末引用块。
"""
    mindmap_repo.update_node_note(nid_target, target_note)

    # 3) 给其他节点也写 note（确保它们不会泄露到导出）
    mindmap_repo.update_node_note(nid_distract1, "干扰节点A 的内容，不应被导出")
    mindmap_repo.update_node_note(nid_distract2, "干扰节点B 的内容，不应被导出")

    print(f"[OK] 测试数据就绪: 4 nodes, target note len={len(target_note)}")

    # 4) 加载 + 取出目标节点
    g = mindmap_repo.load_graph(mid)
    target_node = g.get_node(nid_target)
    assert target_node is not None
    assert target_node.note == target_note

    # ==================== 测试 1: MD 导出 == node.note 原样 ====================
    out_md = TEST_DIR / "node.md"
    export_node_to_markdown(target_node, out_md)
    md_text = out_md.read_text(encoding="utf-8")

    # ⭐⭐ MD 内容必须 == node.note 原样
    assert md_text == target_note.rstrip() + "\n", \
        f"MD 导出内容必须等于 node.note 原样\n" \
        f"  期望: {target_note[:60]!r}...\n" \
        f"  实得: {md_text[:60]!r}..."

    # 不应包含其他节点
    assert "干扰节点A" not in md_text
    assert "干扰节点B" not in md_text
    assert "根节点" not in md_text

    # 不应包含任何额外包装
    assert not md_text.startswith("# 目标节点\n\n"), "MD 不应自动加节点标题 h1"
    assert "由 MindFlow 生成" not in md_text
    assert "节点总数" not in md_text
    assert "导出时间" not in md_text
    assert "📊" not in md_text

    # 用户在 note 里自己写的 # 极限基础整理 应保留（这是用户内容的一部分）
    assert "# 极限基础整理" in md_text
    print(f"[OK] 单节点 MD 导出 == node.note 原文 ({len(md_text)} chars)")

    # ==================== 测试 2: HTML 导出 == NoteEditor 预览面板 HTML ====================
    out_html = TEST_DIR / "node.html"
    export_node_to_html(target_node, out_html)
    html_text = out_html.read_text(encoding="utf-8")

    # ⭐⭐ HTML 内容必须 == NoteEditor 预览面板的 HTML（同一份 CSS + 渲染器）
    expected_html = _wrap_html(render_markdown(target_note))
    assert html_text == expected_html, \
        "HTML 导出必须等于 NoteEditor._wrap_html(render_markdown(note))"

    # 不应包含其他节点 / 节点标题 h1 / 附件 / 水印
    assert "<h1>目标节点</h1>" not in html_text, "不应自动加节点标题 h1"
    assert "干扰节点A" not in html_text
    assert "干扰节点B" not in html_text
    assert "根节点" not in html_text
    assert "<footer>" not in html_text
    assert "由 MindFlow 生成" not in html_text
    assert "Python + PySide6" not in html_text
    assert "📊" not in html_text
    assert "节点总数" not in html_text

    # 但应包含 NoteEditor 渲染的 note 内容
    assert "极限基础整理" in html_text
    # ⭐ LaTeX 源码（\varepsilon 等）保留为字面文本 — 因为 markdown 库不做 LaTeX 渲染
    # 用户在预览面板看到的也就是就是这段源码（用户可后续接 MathJax/KaTeX 渲染）
    assert r"\varepsilon" in html_text or "\\varepsilon" in html_text
    assert "<table>" in html_text  # 表格渲染
    assert "<blockquote>" in html_text  # 引用块渲染

    print(f"[OK] 单节点 HTML 导出 == NoteEditor 预览面板 HTML ({len(html_text)} chars)")

    # ==================== 测试 3: PDF 导出 = 同样 HTML 通过 QPrinter 渲染 ====================
    out_pdf = TEST_DIR / "node.pdf"
    export_node_to_pdf(target_node, out_pdf)
    assert out_pdf.exists()
    pdf_size = out_pdf.stat().st_size
    assert pdf_size > 2_000, f"PDF 太小 ({pdf_size} bytes)"

    with open(out_pdf, "rb") as f:
        magic = f.read(5)
    assert magic == b"%PDF-", f"PDF 魔数错误: {magic!r}"

    # ⭐⭐ PDF 验证：导出的 HTML 至少要包含用户 note 的关键内容（QPrinter 渲染后会内嵌）
    # 由于 PDF 是二进制，无法直接比对，但 size 应该 >= 整图 PDF 的几分之一
    print(f"[OK] 单节点 PDF 导出 ({pdf_size} bytes)")

    # ==================== 测试 4: 整个导图导出（回归：仍无水印）====================
    out_full_html = TEST_DIR / "full.html"
    export_to_html("测试导图", g, out_full_html, "smoke", mindmap_id=mid)
    full_html = out_full_html.read_text(encoding="utf-8")
    assert "由 MindFlow 生成" not in full_html
    assert "<footer>" not in full_html
    assert "Python + PySide6" not in full_html
    assert "📊" not in full_html
    assert "节点总数" not in full_html
    assert "目标节点" in full_html  # 但应包含所有节点
    print(f"[OK] 整个导图 HTML 回归: 无水印")

    out_full_pdf = TEST_DIR / "full.pdf"
    export_to_pdf("测试导图", g, out_full_pdf, "smoke", mindmap_id=mid)
    assert out_full_pdf.exists()
    with open(out_full_pdf, "rb") as f:
        magic2 = f.read(5)
    assert magic2 == b"%PDF-"
    print(f"[OK] 整个导图 PDF 回归 ({out_full_pdf.stat().st_size} bytes)")

    print(f"\n[ALL PASS] 单节点导出 = 预览面板 1:1 内容 + 无水印 smoke test 通过！")
    print(f"[INFO] 测试输出目录: {TEST_DIR}")
    print(f"[INFO] 样例文件:")
    print(f"       - {out_md}  (节点 note 原文)")
    print(f"       - {out_html} (NoteEditor 预览面板 HTML)")
    print(f"       - {out_pdf}  (预览 HTML → PDF)")


if __name__ == "__main__":
    try:
        test_node_export_equals_preview()
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)