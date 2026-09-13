"""把转换结果写入 MindFlow 数据库。

约定：
- 一个 ConvertedMindMap → 一个 MindMap（含所有节点 + 一个 list_attachments 兼容的初始化）
- 用 ``mindmap_repo`` 现有 CRUD，不改任何 schema。
- 失败时回滚：已写入的 mindmap 删掉，避免半成品。

P3 负责维护。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.integrations.zhishu.converter import ConvertedMindMap, ConvertResult
from src.storage import mindmap_repo
from src.storage.db import session_scope
from src.storage.schema import MindMap as MindMapModel
from src.storage.schema import Node as NodeModel
from src.utils.logger import get_logger

logger = get_logger("mindflow.zhishu.importer")


@dataclass
class ImportResult:
    """单次导入的实际入库结果。"""

    mindmap_ids: list[str]
    total_nodes: int
    failures: list[str]  # 出错的 session 描述


def import_converted(
    result: ConvertResult,
    *,
    on_progress: callable | None = None,
) -> ImportResult:
    """把 ConvertResult 全部入库。

    Args:
        result: convert_state() 的输出。
        on_progress: 可选回调 ``(index, total, title)``，UI 显示进度用。

    Returns:
        ImportResult 含每个 mindmap 的 id。
    """
    ids: list[str] = []
    failures: list[str] = []
    total_nodes = 0

    total = len(result.mindmaps)
    for idx, mm in enumerate(result.mindmaps):
        try:
            mid = _import_one_mindmap(mm)
            ids.append(mid)
            total_nodes += len(mm.nodes)
            if on_progress:
                on_progress(idx + 1, total, mm.title)
            logger.info(f"导入 mindmap: {mm.title} ({mid[:8]}) — {len(mm.nodes)} 节点")
        except Exception as exc:
            logger.exception(f"导入失败：{mm.title}")
            failures.append(f"{mm.title}: {exc}")

    return ImportResult(
        mindmap_ids=ids,
        total_nodes=total_nodes,
        failures=failures,
    )


def _import_one_mindmap(mm: ConvertedMindMap) -> str:
    """导入单个 MindMap。失败时回滚（删已建的 mindmap）。"""
    mid = mindmap_repo.create_mindmap(title=mm.title, description=mm.description)

    try:
        # ⭐ 关键：所有节点在同一个 SQLAlchemy session 里 add，避免 FK constraint failed
        # （每个 mindmap_repo.add_node() 是独立 session + commit，root 的 commit 还没完成
        # child 的 INSERT 就会失败）
        sorted_nodes = _topological_order(mm.nodes)
        _bulk_insert_nodes(mid, sorted_nodes)

        # ⭐ 节点 text 和 note 需要 update（NodeModel.text 默认是新节点 text）
        for n in sorted_nodes:
            mindmap_repo.update_node_text(n["id"], n["text"])
            if n.get("note"):
                mindmap_repo.update_node_note(n["id"], n["note"])
        return mid
    except Exception:
        # ⭐ 回滚：删掉半成品的 mindmap（级联删节点）
        try:
            mindmap_repo.delete_mindmap(mid)
        except Exception:
            logger.exception("回滚失败：无法删除半成品 mindmap")
        raise


def _bulk_insert_nodes(mindmap_id: str, nodes: list[dict]) -> None:
    """⭐ 在同一个 session_scope 里把所有节点 add + flush + commit。

    保证父节点的 INSERT 在 child 之前 flush 到当前事务，FK 检查能通过。
    """
    if not nodes:
        return
    with session_scope() as session:
        # 第一节点如果是 root，需要把 mindmap.root_node_id 指过去（保持 add_node 的副作用）
        root_assigned = False
        for n in nodes:
            node = NodeModel(
                id=n["id"],
                mindmap_id=mindmap_id,
                parent_id=n.get("parent_id"),
                text=n["text"],
                note=n.get("note") or "",
                color=n.get("color", "#4A90E2"),
                pos_x=n.get("x", 0.0),
                pos_y=n.get("y", 0.0),
                is_expanded=True,
                search_source=n.get("search_source"),
                image_path=n.get("image_path"),
                image_caption=n.get("image_caption"),
            )
            session.add(node)
            if not root_assigned:
                session.flush()  # 先 flush 让 root 有 id
                mm = session.query(MindMapModel).filter_by(id=mindmap_id).first()
                if mm and mm.root_node_id is None:
                    mm.root_node_id = n["id"]
                root_assigned = True
        # 最后再 flush 一次（其实退出 with 时 session_scope 会 commit）


def _topological_order(nodes: list[dict]) -> list[dict]:
    """⭐ 按 BFS 拓扑序排序节点（父先于子）。

    防止 UUID 字符串排序后 child 排在 parent 前面 → FK constraint failed。
    支持多个 root（多个 parent_id=None）。
    """
    by_id = {n["id"]: n for n in nodes}
    parent_of = {n["id"]: n.get("parent_id") for n in nodes}
    children_of: dict[str | None, list[str]] = {}
    for nid, pid in parent_of.items():
        children_of.setdefault(pid, []).append(nid)

    valid_ids = set(by_id.keys())
    roots = [
        nid for nid, pid in parent_of.items() if pid is None or pid not in valid_ids
    ]

    order: list[dict] = []
    queue = list(roots)
    visited: set[str] = set()
    while queue:
        cur_id = queue.pop(0)
        if cur_id in visited:
            continue
        visited.add(cur_id)
        order.append(by_id[cur_id])
        for child_id in children_of.get(cur_id, []):
            if child_id not in visited:
                queue.append(child_id)

    # 防兜底：如有节点未 BFS 到达（异常情况），追加在末尾
    if len(order) < len(nodes):
        for n in nodes:
            if n["id"] not in visited:
                order.append(n)
    return order


__all__ = ["ImportResult", "import_converted"]
