"""把知树 (Zhishu) workspace state 转成 MindFlow 思维导图数据。

约定（Phase 1 — 最小侵入）：
- **每个 session 转成一个独立 MindMap**（1:1），title = session.title。
- **每个 branch 转成一个 node**（不含 entries 拆分）：
    - node.text       ← branch.title
    - node.parent_id  ← branch.parent?.branchId（根 branch → parent_id=None）
    - node.note       ← branch.entries[] 拼成的 Markdown（含元数据 header）
    - node.color      ← 按 tags / kept / 默认 启发式
    - node.pos_x/y    ← 简单放射状自动布局（不需要完美，能进画布就行）
- **不入附加边**（zhi_map 没有显式 cross-link 概念；后续如需要再扩展）。
- **保留 zhi_map 字段**（kept/tags/source/range）→ 塞进 note 的 Markdown header 块，
  这样不破坏 MindFlow 现有 schema / 撤销栈 / 附件系统。

P3 负责维护。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("mindflow.zhishu.converter")


# ---------- 颜色启发式 ----------
# 把 zhi_map tag 映射到 MindFlow 节点 color；最多 8 种 tag → 8 种颜色
_TAG_COLOR_TABLE = {
    "数学": "#E74C3C",
    "配方法": "#E67E22",
    "二次函数": "#F1C40F",
    "语文": "#27AE60",
    "英语": "#16A085",
    "物理": "#3498DB",
    "化学": "#2980B9",
    "生物": "#1ABC9C",
    "历史": "#8E44AD",
    "地理": "#9B59B6",
    "政治": "#34495E",
    "AI": "#5558BA",
    "编程": "#2C3E50",
    "笔记": "#7F8C8D",
    "重点": "#D35400",
    "复习": "#C0392B",
    "考试": "#A93226",
}
_DEFAULT_COLOR = "#4A90E2"
_KEPT_COLOR = "#F39C12"  # 收藏 / kept 高亮


def _pick_color(tags: list[str], kept: bool) -> str:
    """根据 tags / kept 选颜色。"""
    if kept:
        return _KEPT_COLOR
    for tag in tags:
        if tag in _TAG_COLOR_TABLE:
            return _TAG_COLOR_TABLE[tag]
    return _DEFAULT_COLOR


# ---------- Markdown 拼装 ----------
_ROLE_ICON = {"user": "👤 你", "assistant": "🤖 AI", "system": "⚙️ 系统"}


def _format_entry_md(entry: dict[str, Any]) -> str:
    """把 zhi_map 一条 entry 转成 Markdown 块。"""
    role = entry.get("role", "assistant")
    label = _ROLE_ICON.get(role, role)
    text = (entry.get("text") or "").strip()
    kind = entry.get("kind", "message")
    inherited = entry.get("inherited", False)

    if kind == "reference":
        src = entry.get("source", {})
        src_branch = src.get("branchTitle", "?")
        src_session = src.get("sessionTitle", "?")
        caption = f"📎 **引用快照**：来自《{src_session}》/{src_branch}"
        if entry.get("range"):
            r = entry["range"]
            caption += f"（字符 {r.get('start', '?')}–{r.get('end', '?')}）"
        return f"{caption}\n\n> {text}"

    head = f"**{label}**"
    if inherited:
        head += "　_(继承自父分支)_"
    return f"{head}\n\n{text}"


def _build_note(branch: dict[str, Any]) -> str:
    """把整条 branch 的 entries 拼成 Markdown note。

    在开头放一个 ⭐ 元数据 header 块，保留 zhi_map 特有字段。
    """
    entries = branch.get("entries", []) or []
    body = "\n\n---\n\n".join(_format_entry_md(e) for e in entries) or "_(空分支)_"

    tags = branch.get("tags", []) or []
    kept = bool(branch.get("kept"))
    parent = branch.get("parent")
    selection = branch.get("selection")
    source_lines: list[str] = []
    for e in entries:
        src = e.get("source") or {}
        if src:
            source_lines.append(
                f"  - {src.get('sessionTitle', '?')} / {src.get('branchTitle', '?')} / {src.get('messageId', '?')[:8]}"
            )

    header = "<!-- zhi_map-meta\n"
    header += "  source: zhishu\n"
    header += f"  sessionId: {branch.get('sessionId', '?')}\n"
    header += f"  branchId: {branch.get('id', '?')}\n"
    if parent:
        header += f"  parentBranchId: {parent.get('branchId', '?')}\n"
    header += f"  kept: {kept}\n"
    header += f"  tags: {', '.join(tags) if tags else '(none)'}\n"
    if selection:
        header += (
            f"  selection: {selection.get('start', '?')}-{selection.get('end', '?')}\n"
        )
    if source_lines:
        header += "  sources:\n" + "\n".join(source_lines) + "\n"
    header += "-->\n\n"

    return header + body


# ---------- 自动布局 ----------
# 简单右展式 + 同级垂直堆叠：
#   root 在 (0, 0)
#   第 1 层子节点：x=300, y=依次 0, 120, 240, ...
#   第 2 层子节点：x=600, y= 父节点的 y ± 120 * (兄弟数)
#
# 节点视觉宽度 ~180，高度 ~80；间距：水平 280，垂直 120。
_X_STEP = 280
_Y_STEP = 120


@dataclass
class _LayoutNode:
    """布局计算中间态。"""

    id: str
    parent_id: str | None
    depth: int
    x: float = 0.0
    y: float = 0.0
    children: list[str] = field(default_factory=list)


def _layout(state: dict[str, Any]) -> dict[str, _LayoutNode]:
    """给所有 branch 算 (x, y)。

    算法：
    1. 按 session 分桶，每个 session 内部独立布局
    2. 每个 session 里找 root branches（parent=None）作为多个独立的根
    3. 依次 BFS 摆位置：每棵子树分配一个"垂直区间"
    """
    # 按 session 分桶
    by_session: dict[str, list[dict[str, Any]]] = {}
    for b in state["branches"]:
        by_session.setdefault(b["sessionId"], []).append(b)

    # 全局 branch_id → _LayoutNode
    nodes: dict[str, _LayoutNode] = {}

    for session_id, branches in by_session.items():
        # 子 → 父
        parent_of: dict[str, str | None] = {}
        children_of: dict[str, list[str]] = {}
        for b in branches:
            bid = b["id"]
            parent_id = b.get("parent", {}).get("branchId") if b.get("parent") else None
            parent_of[bid] = parent_id
            children_of.setdefault(parent_id, []).append(bid)

        # 找所有 session 内的"根"（parent=None 或 parent 不在同 session）
        roots = [
            bid
            for bid, p in parent_of.items()
            if p is None or p not in {x["id"] for x in branches}
        ]

        # 给每棵子树垂直分配：每棵树占一个总高，按节点数估计
        cursor_y = 0.0  # 整个 session 内的累计 y 起点

        def assign_subtree(root_id: str, root_x: float, top_y: float) -> float:
            """返回整棵子树的最终 bottom y。"""
            # 先 DFS 收集所有后代（用于估算高度）
            stack = [(root_id, 0)]  # (id, depth)
            visited = set()
            members: list[tuple[str, int]] = []
            while stack:
                cur, depth = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                members.append((cur, depth))
                for child_id in children_of.get(cur, []):
                    stack.append((child_id, depth + 1))

            # 按 max_depth 分层
            max_depth = max(d for _, d in members) if members else 0
            levels: dict[int, list[str]] = {}
            for bid, d in members:
                levels.setdefault(d, []).append(bid)

            # 每行占 Y_STEP；总高 = (max_depth + 1) * Y_STEP
            for d in range(max_depth + 1):
                for idx, bid in enumerate(levels.get(d, [])):
                    nodes[bid] = _LayoutNode(
                        id=bid,
                        parent_id=parent_of[bid],
                        depth=d,
                        x=root_x + d * _X_STEP,
                        y=top_y + (idx + 0.5) * _Y_STEP,
                        children=children_of.get(bid, []),
                    )

            return top_y + (max_depth + 1) * _Y_STEP

        # 多个根 → 每个根水平错开
        for idx, root_id in enumerate(sorted(roots)):
            root_x = idx * _X_STEP * 3  # 不同根之间也拉开
            sub_bottom = assign_subtree(root_id, root_x, cursor_y)
            # 估算下一棵的起点（粗略：用本棵的层数 * 行高）
            sub_members_count = (
                sum(
                    1
                    for n in nodes.values()
                    if n.id in children_of.get(root_id, []) or n.id == root_id
                )
                or 1
            )
            cursor_y = sub_bottom + _Y_STEP

    return nodes


# ---------- 公开 API ----------
@dataclass
class ConvertedMindMap:
    """转换后的单个 MindMap 数据（未入库）。"""

    title: str
    description: str
    nodes: list[dict[str, Any]]  # 给 mindmap_repo.add_node 用
    extra: dict[str, Any] = field(default_factory=dict)  # 溯源信息


@dataclass
class ConvertResult:
    """整个 workspace 的转换结果。"""

    mindmaps: list[ConvertedMindMap]


def convert_state(
    state: dict[str, Any],
    *,
    aggregate_entries: bool = True,
) -> ConvertResult:
    """把 state 转成若干 MindMap 数据。

    Args:
        state: 已 validate 的知树 state。
        aggregate_entries: True → 整个 branch 的 entries 拼成一条 note（默认）；
                          False → 把每条 entry 拆成独立 node（user → assistant 链）。

    Returns:
        ConvertResult 含每个 session 对应一个 ConvertedMindMap。
    """
    if not aggregate_entries:
        # 拆分模式留作 Phase 2 扩展，本期只做聚合
        logger.warning("aggregate_entries=False 暂未实现，按 True 处理")

    layout_map = _layout(state)
    sessions = {s["id"]: s for s in state["sessions"]}

    mindmaps: list[ConvertedMindMap] = []
    for session in state["sessions"]:
        sid = session["id"]
        session_branches = [b for b in state["branches"] if b["sessionId"] == sid]
        if not session_branches:
            continue

        nodes: list[dict[str, Any]] = []
        for b in session_branches:
            layout = layout_map.get(b["id"])
            x = layout.x if layout else 0.0
            y = layout.y if layout else 0.0
            parent_id = layout.parent_id if layout else None
            color = _pick_color(b.get("tags", []) or [], bool(b.get("kept")))
            note = _build_note(b)

            nodes.append(
                {
                    "id": b["id"],
                    "text": b.get("title") or "(无标题)",
                    "parent_id": parent_id,
                    "x": x,
                    "y": y,
                    "color": color,
                    "note": note,
                    # 旧字段（兼容）：zhi_map 时代 image 不传
                    "image_path": None,
                    "image_caption": None,
                }
            )

        mindmaps.append(
            ConvertedMindMap(
                title=session["title"] or f"未命名会话 {sid[:8]}",
                description=f"从知树导入，{len(session_branches)} 个分支",
                nodes=nodes,
                extra={
                    "source": "zhishu",
                    "sessionId": sid,
                    "imported_at": __import__("datetime").datetime.utcnow().isoformat()
                    + "Z",
                    "branch_count": len(session_branches),
                },
            )
        )

    logger.info(
        f"知树→MindFlow 转换完成：{len(mindmaps)} 个导图, "
        f"共 {sum(len(m.nodes) for m in mindmaps)} 个节点"
    )
    return ConvertResult(mindmaps=mindmaps)


__all__ = [
    "ConvertResult",
    "ConvertedMindMap",
    "convert_state",
]
