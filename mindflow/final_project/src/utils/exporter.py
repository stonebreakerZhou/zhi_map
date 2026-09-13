"""导出模块。

支持 4 种格式：
- PNG:   QGraphicsView 截图
- JSON:  完整数据结构（可重新导入）
- Markdown: 学习笔记！杀手功能
- HTML:  单文件网页（内嵌 CSS）

P1 负责维护。
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import markdown as _markdown

# ⭐ 共享 Markdown 渲染器（每次 reset() 复用同一个实例，省内存 + 提速）
_MD_RENDERER = _markdown.Markdown(
    extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
)

from src.config import DATA_DIR
from src.mindmap.graph import MindMapGraph
from src.storage import mindmap_repo
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.ui.mindmap_view import MindMapView

logger = get_logger("mindflow.utils.exporter")


# ==================== PNG 导出 ====================


def export_to_png(view: MindMapView, file_path: str | Path) -> None:
    """把画布截图导出为 PNG。

    Args:
        view: MindMapView 实例
        file_path: 输出 .png 文件路径
    """

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 获取场景中所有节点的边界矩形（含 padding）
    rect = view.scene().itemsBoundingRect().adjusted(-50, -50, 50, 50)

    # 渲染到 QPixmap
    pixmap = view.grab(rect)
    pixmap.save(str(file_path), "PNG")

    logger.info(f"导出 PNG: {file_path} ({pixmap.width()}x{pixmap.height()})")


# ==================== JSON 导出 ====================


def export_to_json(
    mindmap_title: str,
    graph: MindMapGraph,
    file_path: str | Path,
    description: str = "",
) -> None:
    """导出为 JSON（可重新导入）。

    Args:
        mindmap_title: 导图标题
        graph: MindMapGraph 实例
        file_path: 输出 .json 文件路径
        description: 导图描述
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "app": "MindFlow",
        "exported_at": datetime.now().isoformat(),
        "title": mindmap_title,
        "description": description,
        "nodes": [
            {
                **node.to_dict(),
            }
            for node in graph.all_nodes()
        ],
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"导出 JSON: {file_path} ({len(data['nodes'])} 节点)")


def import_from_json(file_path: str | Path) -> dict:
    """从 JSON 文件读取导图数据。

    Returns:
        {"title": ..., "description": ..., "nodes": [...]}
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== Markdown 导出（杀手功能）====================


def export_to_markdown(
    mindmap_title: str,
    graph: MindMapGraph,
    file_path: str | Path,
    description: str = "",
    mindmap_id: str | None = None,
) -> None:
    """导出为 Markdown 学习笔记。

    按树状层级用标题/列表渲染，把思维导图变成结构化学习笔记。

    ⭐ 多附件：节点的所有图片附件嵌入正文，文档附件作为代码块附加。

    示例输出：
        # Python 装饰器
        > 学习装饰器的笔记

        ## 基础概念
        - 定义
        - 作用

        ## 进阶
        ### 带参数装饰器
        - 嵌套
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# {mindmap_title}")
    lines.append("")

    if description:
        lines.append(f"> {description}")
        lines.append("")

    lines.append(f"*导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*节点总数：{graph.node_count}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 递归渲染树
    if graph.root_id:
        root = graph.get_node(graph.root_id)
        if root:
            _render_node_markdown(root, graph, lines, level=2, mindmap_id=mindmap_id)

    # 索引（所有节点列表）
    lines.append("---")
    lines.append("")
    lines.append("## 📑 节点索引")
    lines.append("")
    for i, node in enumerate(graph.dfs(), 1):
        marker = "🤖" if node.search_source else "•"
        att_count = mindmap_repo.count_attachments(node.id) if mindmap_id else 0
        suffix = f" 🖼{att_count}" if att_count else ""
        lines.append(f"{i}. {marker} {node.text}{suffix}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"导出 Markdown: {file_path} ({graph.node_count} 节点)")


def _render_node_markdown(node, graph, lines, level, mindmap_id=None):
    """递归渲染节点为 Markdown。

    标题用 # 号，深度每+1 标题级别+1（但不超过 6）
    子节点用 - 列表
    ⭐ 多附件：嵌入所有图片附件；文档附件作为代码块
    """
    if level > 6:
        # 超过 6 级用列表
        lines.append(f"- {node.text}")
    else:
        lines.append(f"{'#' * level} {node.text}")
    lines.append("")

    # 节点备注（⭐ Markdown 源码：多行时每行加 > 前缀，保持引用块格式）
    if node.note:
        note_text = node.note.rstrip()
        for note_line in note_text.split("\n"):
            if note_line.strip():
                lines.append(f"> 📝 {note_line}")
            else:
                lines.append(">")  # 空行也保留引用标记
        lines.append("")

    # AI 来源标记
    if node.search_source:
        lines.append(f"*（来源：AI 搜索 - {node.search_source}）*")
        lines.append("")

    # ⭐ 多附件：嵌入所有图片 + 文档
    if mindmap_id:
        atts = mindmap_repo.list_attachments(node.id)
        for att in atts:
            abs_path = DATA_DIR / att["file_path"]
            if not abs_path.exists():
                continue
            caption = att.get("caption") or ""
            cover_mark = " ★封面" if att.get("is_cover") else ""
            if att["file_type"] == "image":
                lines.append(f"![{caption or node.text}]({att['file_path']})")
                if caption:
                    lines.append(f"*图注：{caption}{cover_mark}*")
                elif cover_mark:
                    lines.append(f"*{cover_mark.strip()}*")
                lines.append("")
            else:
                # 文档附件：作为代码块附加
                lines.append(f"📎 **附件：{caption or abs_path.name}**{cover_mark}")
                lines.append("")
                try:
                    content = abs_path.read_text(encoding="utf-8")
                    lines.append("```")
                    lines.append(content)
                    lines.append("```")
                except Exception:
                    lines.append(f"*(无法读取文件：{att['file_path']})*")
                lines.append("")
    else:
        # ⭐ 旧版兼容：单图字段
        if node.image_path:
            abs_path = DATA_DIR / node.image_path
            if abs_path.exists():
                lines.append(f"![{node.image_caption or node.text}]({node.image_path})")
                lines.append("")
                if node.image_caption:
                    lines.append(f"*图注：{node.image_caption}*")
                    lines.append("")

    # 渲染子节点
    children = graph.get_children(node.id)
    if children:
        for child in children:
            _render_node_markdown(child, graph, lines, level + 1, mindmap_id=mindmap_id)


# ==================== HTML 导出 ====================


def _render_markdown_safe(text: str) -> str:
    """把 Markdown 文本渲染成 HTML 片段（导出时用）。"""
    if not text:
        return ""
    try:
        _MD_RENDERER.reset()
        return _MD_RENDERER.convert(text)
    except Exception as e:
        logger.error(f"Markdown 渲染失败: {e}")
        # 失败时回退为转义后的纯文本（避免破坏 HTML）
        return f"<pre style='color:red'>渲染错误：{e}</pre>" + "<br>".join(
            _html_escape(line) for line in text.splitlines()
        )


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{mindmap_title}</title>
<style>
  body {{
    font-family: 'Microsoft YaHei', sans-serif;
    max-width: 900px;
    margin: 40px auto;
    padding: 20px;
    background: #fafafa;
    color: #333;
  }}
  h1 {{
    color: #4A90E2;
    border-bottom: 3px solid #4A90E2;
    padding-bottom: 10px;
    font-weight: 600;
  }}
  .description {{
    background: #fff8dc;
    padding: 12px 16px;
    border-left: 4px solid #ffd700;
    margin: 20px 0;
    font-style: italic;
  }}
  ul {{ list-style: none; padding-left: 20px; }}
  ul ul {{ border-left: 2px dashed #ccc; }}
  li {{ padding: 4px 0; line-height: 1.6; }}
  .note {{ color: #888; font-size: 0.9em; }}
  .note-rendered {{
    margin: 8px 0 8px 20px;
    padding: 10px 14px;
    background: #ffffff;
    border-left: 3px solid #4A90E2;
    border-radius: 0 4px 4px 0;
    color: #333;
    font-size: 0.95em;
    line-height: 1.7;
  }}
  .note-rendered h1, .note-rendered h2, .note-rendered h3 {{
    margin: 12px 0 8px; color: #1976d2;
  }}
  .note-rendered h1 {{ font-size: 1.3em; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }}
  .note-rendered h2 {{ font-size: 1.15em; }}
  .note-rendered h3 {{ font-size: 1.0em; }}
  .note-rendered p {{ margin: 6px 0; }}
  .note-rendered code {{
    background: #f5f5f5; padding: 2px 5px; border-radius: 3px;
    font-family: Consolas, monospace; color: #c2185b; font-size: 0.9em;
  }}
  .note-rendered pre {{
    background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px;
    padding: 8px 12px; overflow-x: auto;
  }}
  .note-rendered pre code {{ background: transparent; padding: 0; }}
  .note-rendered blockquote {{
    border-left: 3px solid #90caf9; margin: 8px 0; padding: 4px 12px;
    color: #555; background: #f5f9ff;
  }}
  .note-rendered ul, .note-rendered ol {{ padding-left: 24px; margin: 6px 0; }}
  .note-rendered table {{ border-collapse: collapse; margin: 8px 0; }}
  .note-rendered th, .note-rendered td {{ border: 1px solid #ddd; padding: 4px 8px; }}
  .note-rendered th {{ background: #f0f0f0; }}
  .note-rendered img {{ max-width: 100%; border-radius: 4px; }}
  .note-rendered hr {{ border: none; border-top: 1px dashed #ccc; margin: 12px 0; }}
  .node-image {{ margin: 8px 0 12px 20px; max-width: 600px; }}
  .node-image img {{
    max-width: 100%; border: 1px solid #ddd; border-radius: 6px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
  }}
  .caption {{ color: #666; font-size: 0.85em; font-style: italic; margin-top: 4px; }}
  .node-doc {{
    margin: 8px 0 12px 20px; border: 1px solid #e0e0e0;
    border-radius: 6px; background: #fafafa; overflow: hidden;
  }}
  .doc-header {{
    background: #f0f4f8; color: #1976d2; padding: 6px 12px;
    font-size: 0.9em; font-weight: bold; border-bottom: 1px solid #e0e0e0;
  }}
  .doc-content {{
    margin: 0; padding: 10px 14px; font-family: Consolas, monospace;
    font-size: 0.85em; line-height: 1.5; white-space: pre-wrap;
    color: #444; background: #ffffff;
  }}
</style>
</head>
<body>
  <h1>{mindmap_title}</h1>
  {description_html}
  <ul>
{nodes_html}
  </ul>
</body>
</html>
"""


# ⭐ 单节点导出复用了 note_editor.py 的 render_markdown + _wrap_html，
# 保证导出和预览面板 1:1 一致 — 用户看到什么就导出什么。


def _build_full_html(
    mindmap_title: str,
    graph: MindMapGraph,
    description: str = "",
    mindmap_id: str | None = None,
) -> str:
    """⭐ 复用 export_to_html 的 HTML body 生成逻辑（refactor）。

    之前 export_to_html 把 HTML 写在函数末尾的 f-string 里，现在拆出来给 PDF 复用。
    行为完全一致 — 同样 base64 嵌入图片、同样渲染 note 为富文本。
    """
    nodes_html = []
    for node in graph.all_nodes():
        depth = _get_depth(node.id, graph)
        indent = "  " * depth
        marker = "🤖" if node.search_source else "•"
        att_html = ""

        # ⭐ 多附件：渲染所有图片 + 文档
        atts = mindmap_repo.list_attachments(node.id) if mindmap_id else []
        # 旧字段兼容
        if not atts and node.image_path:
            atts = [
                {
                    "file_path": node.image_path,
                    "file_type": "image",
                    "caption": node.image_caption,
                    "is_cover": False,
                }
            ]

        if atts:
            att_blocks = []
            for att in atts:
                abs_path = DATA_DIR / att["file_path"]
                if not abs_path.exists():
                    continue
                cover_mark = " ★封面" if att.get("is_cover") else ""
                caption = att.get("caption") or ""
                if att["file_type"] == "image":
                    data_uri = _image_to_base64(abs_path)
                    if data_uri:
                        caption_html = (
                            f'<div class="caption">📷 {_html_escape(caption)}{cover_mark}</div>'
                            if caption or cover_mark
                            else ""
                        )
                        att_blocks.append(
                            f'<div class="node-image">'
                            f'<img src="{data_uri}" alt="{_html_escape(node.text)}" />'
                            f"{caption_html}"
                            f"</div>"
                        )
                else:
                    # 文档附件
                    try:
                        content = abs_path.read_text(encoding="utf-8")
                        content_html = _html_escape(content)
                        att_blocks.append(
                            f'<div class="node-doc">'
                            f'<div class="doc-header">📎 {_html_escape(caption or abs_path.name)}{cover_mark}</div>'
                            f'<pre class="doc-content">{content_html}</pre>'
                            f"</div>"
                        )
                    except Exception:
                        att_blocks.append(
                            f'<div class="node-doc">'
                            f'<div class="doc-header">📎 {_html_escape(caption or abs_path.name)}{cover_mark}</div>'
                            f"<p><em>无法读取文件</em></p>"
                            f"</div>"
                        )
            att_html = "".join(att_blocks)
        # ⭐ note 字段是 Markdown 源码，渲染成 HTML（用户能写富文本笔记了）
        note_html = ""
        if node.note and node.note.strip():
            rendered = _render_markdown_safe(node.note)
            note_html = f'<div class="note-rendered">{rendered}</div>'
        nodes_html.append(
            f"{indent}<li>{marker} {_html_escape(node.text)}"
            + note_html
            + att_html
            + "</li>"
        )

    return _HTML_TEMPLATE.format(
        mindmap_title=mindmap_title,
        description_html=(
            f'<div class="description">{_html_escape(description)}</div>'
            if description
            else ""
        ),
        node_count=graph.node_count,
        export_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        nodes_html="\n".join(nodes_html),
    )


def export_to_html(
    mindmap_title: str,
    graph: MindMapGraph,
    file_path: str | Path,
    description: str = "",
    mindmap_id: str | None = None,
) -> None:
    """导出为单文件 HTML（双击可在浏览器打开）。"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    html = _build_full_html(mindmap_title, graph, description, mindmap_id)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"导出 HTML: {file_path} ({graph.node_count} 节点)")


# ==================== PDF 导出（复用 HTML 生成 + Qt 原生 QPrinter）====================


def export_to_pdf(
    mindmap_title: str,
    graph: MindMapGraph,
    file_path: str | Path,
    description: str = "",
    mindmap_id: str | None = None,
) -> None:
    """⭐ 导出为 PDF — 复用 HTML 渲染 + Qt 原生 QPrinter。

    行为和 export_to_html 一致（同样的样式、同样嵌入图片 base64、同样渲染 note），
    只是输出格式换成了 PDF。

    Args:
        mindmap_title: 导图标题
        graph: MindMapGraph 实例
        file_path: 输出 .pdf 路径
        description: 导图描述
        mindmap_id: 用于加载节点的图片/文档附件（可空）
    """
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) 生成完整的 HTML（与 export_to_html 同样的样式 + base64 图片）
    full_html = _build_full_html(mindmap_title, graph, description, mindmap_id)

    # 2) 配置打印机为 PDF 输出（A4 / 15mm 边距）
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(file_path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)

    # 3) 用 QTextDocument 渲染 HTML 到 PDF
    doc = QTextDocument()
    # 设置文档宽度 = A4 宽度 - 2*边距 ≈ 180mm，Qt 用 point (1mm ≈ 2.83pt)
    doc.setPageSize(QSizeF(180 * 2.83, -1))
    doc.setHtml(full_html)
    doc.print_(printer)  # PySide6 用 print_ 避免和 builtin 冲突

    logger.info(f"导出 PDF: {file_path} ({graph.node_count} 节点)")


# ==================== 单节点导出（⭐ 等同预览面板内容）====================


def export_node_to_markdown(node, file_path: str | Path) -> None:
    """⭐⭐ 导出节点笔记 — 输出 = 节点 note 的 Markdown 源码（用户编辑器左栏看到的原文）。

    没有任何额外包装：
    - 不加节点标题作 h1（如果用户在 note 里自己写了 # 标题，就用用户的）
    - 不加任何水印 / footer / 元信息
    - 不附加附件
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # ⭐ 直接写 node.note 原样 — 这就是用户在编辑器左栏看到的 Markdown 源码
    content = (node.note or "").rstrip() + "\n"
    file_path.write_text(content, encoding="utf-8")

    logger.info(f"导出节点笔记(MD): {file_path} (node={node.id}, {len(content)} chars)")


def _build_node_preview_html(node, target_width_px: int | None = None) -> str:
    """⭐⭐ 生成与 NoteEditor 预览面板 1:1 一致的 HTML。

    复用 note_editor.render_markdown + _wrap_html — 同一份 CSS / 同一份渲染器，
    保证「用户在预览面板看到什么，导出的 HTML 就是什么」。

    Args:
        node:             节点对象
        target_width_px:  若指定，把 `<img class="mindflow-img" width="X%">` 转成
                          `<img ... height="N">`（按目标宽度反算 height，因为
                          Qt 的 QTextBrowser/QTextDocument 只认 height 属性）
                          - HTML 导出：传 None（保留百分比源，浏览器自适应）
                          - PDF 导出：传 PDF 页面可写区宽度（保证图片占 PDF 整体宽度的 X%）
    """
    from src.ui.note_editor import (
        _resolve_img_percent_to_pixels,
        _wrap_html,
        render_markdown,
    )

    rendered = render_markdown(node.note or "")
    if target_width_px is not None:
        # ⭐ PDF/打印场景：把图片百分比按目标宽度解析为 height 像素
        # QTextBrowser/QTextDocument 只认 height 属性，不解析 width/style
        rendered = _resolve_img_percent_to_pixels(rendered, target_width_px)
    return _wrap_html(rendered)


def export_node_to_html(node, file_path: str | Path) -> None:
    """⭐⭐ 导出节点笔记为 HTML — 输出 = NoteEditor 预览面板看到的渲染结果。"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    html = _build_node_preview_html(node)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"导出节点笔记(HTML): {file_path} (node={node.id}, {len(html)} chars)")


def export_node_to_pdf(node, file_path: str | Path) -> None:
    """⭐⭐ 导出节点笔记为 PDF — 输出 = NoteEditor 预览面板看到的渲染结果（PDF 版）。

    ⭐ 图片百分比：按 PDF 页面**可写区**宽度（A4 - 2×15mm 边距 ≈ 180mm ≈ 510pt）
    把 `<img class="mindflow-img" width="X%">` 解析为 height 像素，保证"图片占 PDF 整体宽度的 X%"的语义。
    """
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtWidgets import QTextBrowser

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # ⭐ PDF 可写区宽度（按 doc.setPageSize 与 setPageMargins 一致）：
    # 180mm × 2.83 px/mm（@96dpi）= 509 px
    # 这就是用户希望"width: 50%" → "占 PDF 整体宽度的 50%"的基准
    PDF_WRITABLE_WIDTH_PX = int(180 * 2.83)
    full_html = _build_node_preview_html(node, target_width_px=PDF_WRITABLE_WIDTH_PX)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(file_path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)

    # ⭐⭐ 关键：用 QTextBrowser 渲染 HTML（不是裸 QTextDocument）。
    #   - QTextBrowser 有 setSearchPaths，能自动加载 DATA_DIR 下的相对路径图片
    #     （如 attachments/.../pic.png）
    #   - 裸 QTextDocument 即便设 setBaseUrl，对 print_() 路径上的图片资源加载
    #     也不可靠（实测：图片对象确实生成但渲染结果里看不到色块）
    #   - 复用 QTextBrowser.document()（已经加载好图片资源）给 printer 打印，
    #     是 Qt 文档里推荐的做法
    browser = QTextBrowser()
    browser.setSearchPaths([str(DATA_DIR)])
    browser.setHtml(full_html)
    doc = browser.document()
    doc.setPageSize(QSizeF(180 * 2.83, -1))
    doc.print_(printer)

    logger.info(f"导出节点笔记(PDF): {file_path} (node={node.id})")


def _get_depth(node_id: str, graph: MindMapGraph) -> int:
    """计算节点深度（根节点为 0）。"""
    depth = 0
    current_id = node_id
    while True:
        node = graph.get_node(current_id)
        if not node or not node.parent_id:
            break
        current_id = node.parent_id
        depth += 1
        if depth > 20:  # 防止循环
            break
    return depth


def _image_to_base64(image_path: Path) -> str | None:
    """把图片转 base64 data URI（用于 HTML 单文件嵌入）。

    Returns:
        data URI 字符串，如 "data:image/png;base64,iVBOR..."
        失败返回 None
    """
    try:
        ext = image_path.suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        mime = f"image/{ext}"

        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception as e:
        logger.error(f"图片转 base64 失败 {image_path}: {e}")
        return None


__all__ = [
    "export_to_png",
    "export_to_json",
    "import_from_json",
    "export_to_markdown",
    "export_to_html",
    "export_to_pdf",
    # ⭐ 单节点导出（最终整理笔记专用）
    "export_node_to_markdown",
    "export_node_to_html",
    "export_node_to_pdf",
]
