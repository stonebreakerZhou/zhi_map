# -*- coding: utf-8 -*-
"""多附件功能 smoke test (without GUI).

- 创建导图 + 节点
- 添加图片附件（生成一张测试 PNG）
- 添加文档附件（生成测试 .txt / .md）
- 设置封面
- 拖拽重排 reorder_attachments（替代旧的 ↑↓ move）
- 删除
- 导出 Markdown / HTML（验证多附件嵌入）
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# 让脚本从 tests/ 运行时也能找到 src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 临时切换数据目录避免污染现有 DB
TEST_DIR = Path(tempfile.mkdtemp(prefix="mindflow_test_"))
print(f"[INFO] Using temp dir: {TEST_DIR}")

# 必须在 import src 前修改 DATA_DIR
import src.config as cfg
cfg.DATA_DIR = TEST_DIR / "data"
cfg.IMAGES_DIR = cfg.DATA_DIR / "images"
cfg.DOCUMENTS_DIR = cfg.DATA_DIR / "documents"
cfg.DATABASE_PATH = cfg.DATA_DIR / "mindflow.db"
for d in (cfg.DATA_DIR, cfg.IMAGES_DIR, cfg.DOCUMENTS_DIR, TEST_DIR / "logs"):
    d.mkdir(parents=True, exist_ok=True)

from src.storage import mindmap_repo
from src.storage.attachment_manager import get_attachment_manager
from src.utils.exporter import export_to_markdown, export_to_html
from src.mindmap.graph import MindMapGraph


def _make_test_image(path: Path, color: tuple = (255, 100, 50)) -> None:
    """生成一张最小有效 PNG（不依赖 PIL/Qt）。"""
    # 1x1 PNG bytes for given color
    import struct, zlib
    r, g, b = color
    raw = b''
    # IHDR
    raw += struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    raw += struct.pack('>I', zlib.crc32(raw[4:]) & 0xffffffff)
    # IDAT (single filter byte + 1 pixel RGB)
    pixel_data = b'\x00' + bytes([r, g, b])
    compressed = zlib.compress(pixel_data)
    raw += struct.pack('>I', len(compressed)) + b'IDAT' + compressed
    raw += struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    # IEND
    raw += struct.pack('>I', 0) + b'IEND'
    raw += struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    path.write_bytes(raw)


def test_full_flow():
    mgr = get_attachment_manager()

    # 1) 准备源文件
    src_img = TEST_DIR / "src1.png"
    src_img2 = TEST_DIR / "src2.png"
    src_doc = TEST_DIR / "src.md"
    src_txt = TEST_DIR / "src.txt"
    _make_test_image(src_img, (255, 100, 50))
    _make_test_image(src_img2, (50, 200, 100))
    src_doc.write_text("# Markdown Notes\n\n- bullet 1\n- bullet 2\n", encoding="utf-8")
    src_txt.write_text("Hello MindFlow multi-attachment test!", encoding="utf-8")

    # 2) 创建导图 + 节点
    mid = mindmap_repo.create_mindmap("测试导图", "smoke test")
    nid_root = mindmap_repo.add_node(mid, "根节点")
    nid_child = mindmap_repo.add_node(mid, "子节点 A", parent_id=nid_root)

    # 3) 添加 4 个附件（2 图 + 2 文档）
    rel1 = mgr.import_attachment(src_img)
    rel2 = mgr.import_attachment(src_img2)
    rel3 = mgr.import_attachment(src_doc)
    rel4 = mgr.import_attachment(src_txt)
    assert all([rel1, rel2, rel3, rel4]), "import should succeed"

    a1 = mindmap_repo.add_attachment(nid_child, rel1, "image", caption="封面图")
    a2 = mindmap_repo.add_attachment(nid_child, rel2, "image", caption="补充图")
    a3 = mindmap_repo.add_attachment(nid_child, rel3, "document", caption="学习笔记")
    a4 = mindmap_repo.add_attachment(nid_child, rel4, "document", caption="摘录")

    # 4) 设置封面
    mindmap_repo.set_attachment_cover(a1)
    atts = mindmap_repo.list_attachments(nid_child)
    cover_count = sum(1 for a in atts if a["is_cover"])
    assert cover_count == 1, f"应只有 1 个封面，实得 {cover_count}"
    assert atts[0]["is_cover"] is True, "封面应置顶"
    print(f"[OK] 4 个附件已添加 + 封面设置: {len(atts)} 个")

    # 5) count_attachments
    cnt = mindmap_repo.count_attachments(nid_child)
    assert cnt == 4, f"应 4 个，实得 {cnt}"
    print(f"[OK] count_attachments = {cnt}")

    # 6) 拖拽排序：把 [a1,a2,a3,a4] 重排成 [a3,a1,a4,a2]（一次性事务）
    new_order = [a3, a1, a4, a2]
    mindmap_repo.reorder_attachments(nid_child, new_order)
    atts = mindmap_repo.list_attachments(nid_child)
    actual_order = [a["id"] for a in atts]
    assert actual_order == new_order, \
        f"重排后顺序应为 {new_order}，实得 {actual_order}"
    # 验证 sort_order 从 0 开始连续
    for i, att in enumerate(atts):
        assert att["sort_order"] == i, f"第 {i} 个 sort_order 应={i}，实得 {att['sort_order']}"
    print(f"[OK] 拖拽重排成功: {actual_order}")

    # 7) 删除一个附件
    mindmap_repo.delete_attachment(a4, delete_file=True)
    cnt2 = mindmap_repo.count_attachments(nid_child)
    assert cnt2 == 3, f"应剩 3 个，实得 {cnt2}"
    print(f"[OK] 删除附件后剩 {cnt2} 个")

    # 8) 加载图 + 导出 Markdown
    g = mindmap_repo.load_graph(mid)
    out_md = TEST_DIR / "out.md"
    export_to_markdown("测试导图", g, out_md, "smoke test", mindmap_id=mid)
    md_text = out_md.read_text(encoding="utf-8")
    assert "测试导图" in md_text
    assert "根节点" in md_text
    assert "子节点 A" in md_text
    assert "封面图" in md_text, "封面图 caption 应嵌入 MD"
    assert "补充图" in md_text, "补充图 caption 应嵌入 MD"
    assert "学习笔记" in md_text, "文档附件 caption 应嵌入 MD"
    assert rel1 in md_text, "图片路径应嵌入"
    assert "```" in md_text, "文档附件应作为代码块"
    print(f"[OK] Markdown 导出: {out_md} ({len(md_text)} chars)")

    # 9) 导出 HTML
    out_html = TEST_DIR / "out.html"
    export_to_html("测试导图", g, out_html, "smoke test", mindmap_id=mid)
    html_text = out_html.read_text(encoding="utf-8")
    assert "测试导图" in html_text
    assert "data:image/png;base64" in html_text, "图片应 base64 嵌入"
    assert "node-doc" in html_text, "文档附件应嵌入 .node-doc 块"
    assert "封面图" in html_text
    print(f"[OK] HTML 导出: {out_html} ({len(html_text)} chars)")

    # 10) 引用计数：再删除剩余 2 个，看文件是否真的被清理
    mindmap_repo.delete_attachment(a1, delete_file=True)
    mindmap_repo.delete_attachment(a3, delete_file=True)
    cnt_final = mindmap_repo.count_attachments(nid_child)
    assert cnt_final == 1, f"应剩 1 个，实得 {cnt_final}"
    # rel1 文件应被删
    assert not (cfg.DATA_DIR / rel1).exists(), "孤儿文件应被清理"
    print(f"[OK] 引用计数清理正确")

    # 11) 删除最后一个附件
    mindmap_repo.delete_attachment(a2, delete_file=True)
    assert not (cfg.DATA_DIR / rel2).exists()
    print(f"[OK] 最后文件也清理了")

    print("\n[ALL PASS] 多附件功能 smoke test 通过！")


if __name__ == "__main__":
    try:
        test_full_flow()
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 不删 temp dir，留作查看
        print(f"[INFO] 临时目录保留: {TEST_DIR}")
