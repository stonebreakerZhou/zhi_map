"""思维导图仓储层（CRUD 函数）。

所有数据库操作走这里，UI 层通过这些函数读写数据。

函数分类：
- MindMap CRUD: create_mindmap, list_mindmaps, get_mindmap, delete_mindmap
- Node CRUD:    add_node, get_nodes, update_node_*, delete_node
- 工具:          load_graph (一次性加载整个导图到内存)

P3 负责维护。
"""

from __future__ import annotations

from src.mindmap.graph import MindMapGraph
from src.mindmap.node import NodeData
from src.storage.attachment_manager import get_attachment_manager
from src.storage.db import session_scope
from src.storage.image_manager import get_image_manager
from src.storage.schema import Edge as EdgeModel
from src.storage.schema import MindMap as MindMapModel
from src.storage.schema import Node as NodeModel
from src.storage.schema import NodeAttachment as NodeAttachmentModel
from src.utils.logger import get_logger

logger = get_logger("mindflow.storage.repo")


# ==================== MindMap CRUD ====================


def create_mindmap(title: str, description: str = "") -> str:
    """创建新导图。

    Args:
        title: 导图标题
        description: 导图描述（可选）

    Returns:
        新导图的 ID
    """
    with session_scope() as session:
        mm = MindMapModel(title=title, description=description)
        session.add(mm)
        session.flush()
        mid = mm.id
        logger.info(f"创建导图: {title} ({mid[:8]})")
        return mid


def list_mindmaps() -> list[dict]:
    """列出所有导图（按更新时间倒序）。

    Returns:
        [{"id": ..., "title": ..., "updated_at": ...}, ...]
    """
    with session_scope() as session:
        results = (
            session.query(MindMapModel).order_by(MindMapModel.updated_at.desc()).all()
        )
        return [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "updated_at": m.updated_at,
            }
            for m in results
        ]


def get_mindmap(mindmap_id: str) -> dict | None:
    """获取单个导图信息（不含节点）。"""
    with session_scope() as session:
        m = session.query(MindMapModel).filter_by(id=mindmap_id).first()
        if not m:
            return None
        return {
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "root_node_id": m.root_node_id,
            "updated_at": m.updated_at,
        }


def update_mindmap_title(mindmap_id: str, title: str) -> None:
    """修改导图标题。"""
    with session_scope() as session:
        m = session.query(MindMapModel).filter_by(id=mindmap_id).first()
        if m:
            m.title = title


def delete_mindmap(mindmap_id: str) -> None:
    """删除导图（级联删除节点）。"""
    with session_scope() as session:
        m = session.query(MindMapModel).filter_by(id=mindmap_id).first()
        if m:
            session.delete(m)
            logger.info(f"删除导图: {mindmap_id[:8]}")


# ==================== Node CRUD ====================


def add_node(
    mindmap_id: str,
    text: str,
    parent_id: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    color: str = "#4A90E2",
    search_source: str | None = None,
) -> str:
    """添加节点。

    Args:
        mindmap_id: 所属导图 ID
        text: 节点文本
        parent_id: 父节点 ID（None 表示根节点）
        x, y: 节点位置
        color: 节点颜色
        search_source: AI 来源标记

    Returns:
        新节点 ID
    """
    with session_scope() as session:
        node = NodeModel(
            mindmap_id=mindmap_id,
            parent_id=parent_id,
            text=text,
            pos_x=x,
            pos_y=y,
            color=color,
            search_source=search_source,
        )
        session.add(node)
        session.flush()
        nid = node.id

        # 如果是导图的第一个节点，更新 root_node_id
        mm = session.query(MindMapModel).filter_by(id=mindmap_id).first()
        if mm and mm.root_node_id is None:
            mm.root_node_id = nid

        return nid


def get_nodes(mindmap_id: str) -> list[NodeData]:
    """获取导图的所有节点。"""
    with session_scope() as session:
        nodes = session.query(NodeModel).filter_by(mindmap_id=mindmap_id).all()
        return [
            NodeData(
                id=n.id,
                mindmap_id=n.mindmap_id,
                parent_id=n.parent_id,
                text=n.text,
                note=n.note or "",
                color=n.color or "#4A90E2",
                pos_x=n.pos_x or 0.0,
                pos_y=n.pos_y or 0.0,
                is_expanded=bool(n.is_expanded),
                search_source=n.search_source,
                image_path=n.image_path,  # ⭐ 新增
                image_caption=n.image_caption,  # ⭐ 新增
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            for n in nodes
        ]


def update_node_text(node_id: str, text: str) -> None:
    """修改节点文本。"""
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            n.text = text


def update_node_note(node_id: str, note: str) -> None:
    """修改节点笔记。"""
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            n.note = note


def update_node_position(node_id: str, x: float, y: float) -> None:
    """修改节点位置（拖拽后调用）。"""
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            n.pos_x = x
            n.pos_y = y


def update_node_color(node_id: str, color: str) -> None:
    """修改节点颜色。"""
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            n.color = color


def update_node_image(
    node_id: str, image_path: str | None, image_caption: str | None = None
) -> None:
    """⭐ 修改节点图片（手写笔记挂图）。

    Args:
        node_id: 节点 ID
        image_path: 图片相对路径（如 "images/abc.jpg"），传 None 表示删除图片
        image_caption: 图片说明（可选）
    """
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            # 如果是替换图片（旧图被新图替代），删掉旧图文件
            old_path = n.image_path
            n.image_path = image_path
            if image_caption is not None:
                n.image_caption = image_caption

            # 注意：删除旧图前要确认没有其他节点在引用（这里简化处理，直接删）
            if old_path and old_path != image_path:
                get_image_manager().delete_image(old_path)


def get_node_image(node_id: str) -> dict | None:
    """⭐ 获取节点的图片信息。

    Returns:
        {"image_path": "...", "image_caption": "..."} 或 None
    """
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n and n.image_path:
            return {
                "image_path": n.image_path,
                "image_caption": n.image_caption,
            }
        return None


def delete_node(node_id: str) -> None:
    """删除节点（级联删除子树）。"""
    # 先取出图片路径，删除节点后再清掉图片文件
    image_to_delete: str | None = None
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n:
            image_to_delete = n.image_path
            session.delete(n)
        # ⭐ 同时清理涉及该节点的附加边（任意两节点关系，非父子）
        session.query(EdgeModel).filter(
            (EdgeModel.source_id == node_id) | (EdgeModel.target_id == node_id)
        ).delete(synchronize_session=False)

    # 节点删除后清理孤儿图片
    if image_to_delete:
        _cleanup_orphan_image(image_to_delete)


def detach_node(node_id: str) -> None:
    """⭐ 仅删除节点本身，把子树（直接子节点）的 parent_id 改成 NULL。

    划线切割语义：
    - 节点本身从 DB 删掉
    - 所有直接子节点的 parent_id 置为 NULL（成为独立根）
    - 不清理图片（节点的图片可能正被引用）
    """
    image_to_delete: str | None = None
    with session_scope() as session:
        n = session.query(NodeModel).filter_by(id=node_id).first()
        if n is None:
            return
        image_to_delete = n.image_path
        # ⭐ 关键：先把直接子节点的 parent_id 置为 NULL（避免 FK 级联连带删）
        session.query(NodeModel).filter_by(parent_id=node_id).update(
            {NodeModel.parent_id: None}, synchronize_session=False
        )
        # ⭐ 清理涉及该节点的附加边
        session.query(EdgeModel).filter(
            (EdgeModel.source_id == node_id) | (EdgeModel.target_id == node_id)
        ).delete(synchronize_session=False)
        # 再删自己
        session.delete(n)

    # 节点删除后清理孤儿图片
    if image_to_delete:
        _cleanup_orphan_image(image_to_delete)


def detach_parent_link(parent_id: str, child_id: str) -> None:
    """⭐ 仅断开 parent-child 链接（不删节点、不删边）。

    划线切到树形边时调用：把 child.parent_id 置 NULL，child 成为新根。
    附加边不动；child 的子树内部结构不变。
    """
    with session_scope() as session:
        child = session.query(NodeModel).filter_by(id=child_id).first()
        if child is None:
            return
        # 仅当 child 真的指向这个 parent 才操作（避免误断）
        if child.parent_id == parent_id:
            child.parent_id = None


def reparent_node(child_id: str, new_parent_id: str | None) -> None:
    """⭐ 强制把 child.parent_id 改成 new_parent_id（None = 独立根）。

    划线切割的 undo 用：把之前 detach 的子节点挂回原父节点。

    Raises:
        ValueError: child 不存在、自挂（child_id == new_parent_id）、new_parent
                    不存在或不属于同一导图。
    """
    with session_scope() as session:
        child = session.query(NodeModel).filter_by(id=child_id).first()
        if child is None:
            raise ValueError(f"节点不存在: {child_id}")
        if new_parent_id == child_id:
            raise ValueError(f"不能把节点挂到自己: {child_id}")
        if new_parent_id is not None:
            parent = (
                session.query(NodeModel)
                .filter_by(id=new_parent_id, mindmap_id=child.mindmap_id)
                .first()
            )
            if parent is None:
                raise ValueError(f"父节点不存在或不属于同一导图: {new_parent_id}")
        child.parent_id = new_parent_id


# ==================== ⭐ Edge CRUD（任意两节点关系） ====================


def add_edge(mindmap_id: str, source_id: str, target_id: str) -> int | None:
    """⭐ 添加节点之间的"附加边"（不是父子树关系）。

    返回新边的 id（int）；下列情况返回 None：
    - 自环（source_id == target_id）
    - 同对节点已存在边（不论方向 A→B 还是 B→A）
    - 节点不属于该导图
    """
    if source_id == target_id:
        return None  # 自环
    with session_scope() as session:
        # 校验节点存在且同属一个导图
        sn = (
            session.query(NodeModel)
            .filter_by(id=source_id, mindmap_id=mindmap_id)
            .first()
        )
        tn = (
            session.query(NodeModel)
            .filter_by(id=target_id, mindmap_id=mindmap_id)
            .first()
        )
        if sn is None or tn is None:
            return None
        # 检查重复边（不论方向）
        existing = (
            session.query(EdgeModel)
            .filter(
                (
                    (EdgeModel.source_id == source_id)
                    & (EdgeModel.target_id == target_id)
                )
                | (
                    (EdgeModel.source_id == target_id)
                    & (EdgeModel.target_id == source_id)
                )
            )
            .first()
        )
        if existing is not None:
            return None
        # 创建
        edge = EdgeModel(
            mindmap_id=mindmap_id, source_id=source_id, target_id=target_id
        )
        session.add(edge)
        session.flush()
        return edge.id


def delete_edge(edge_id: int) -> None:
    """⭐ 删除单条边（按主键 id）。"""
    with session_scope() as session:
        session.query(EdgeModel).filter_by(id=edge_id).delete(synchronize_session=False)


def get_edges(mindmap_id: str) -> list[dict]:
    """⭐ 获取某导图的所有附加边。

    返回 [{\"id\": int, \"source_id\": str, \"target_id\": str}, ...]
    """
    with session_scope() as session:
        rows = session.query(EdgeModel).filter_by(mindmap_id=mindmap_id).all()
        return [
            {"id": e.id, "source_id": e.source_id, "target_id": e.target_id}
            for e in rows
        ]


def _cleanup_orphan_image(image_path: str) -> None:
    """删除不再被任何节点引用的图片。"""
    with session_scope() as session:
        count = session.query(NodeModel).filter_by(image_path=image_path).count()
        if count == 0:
            get_image_manager().delete_image(image_path)
            logger.debug(f"清理孤儿图片: {image_path}")


def _sort_nodes_dfs(nodes: list) -> list:
    """⭐⭐ 把 nodes 列表按 DFS 序重排，父永远在子前。

    划线切割后图可能有多个孤儿根，按 first-seen 顺序遍历每棵子树。
    容错：如果某个节点的 parent_id 指向不在 nodes 里的孤儿（理论上不应发生），
    把它当作根处理。
    """
    by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    children_of: dict[str | None, list[str]] = {}
    for n in nodes:
        parent = n.get("parent_id")
        children_of.setdefault(parent, []).append(n["id"])

    # 多根场景：所有 parent_id=None 的都是根
    roots = children_of.get(None, [])
    # 容错：parent 不在 by_id 里 → 当作根
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in by_id and n["id"] not in roots:
            roots.append(n["id"])

    result: list = []
    seen: set[str] = set()
    # 用栈模拟 DFS（先入后出 → 右子树先访问）
    for root_id in reversed(roots):
        stack = [root_id]
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in by_id:
                continue
            seen.add(cur)
            result.append(by_id[cur])
            kids = children_of.get(cur, [])
            for cid in reversed(kids):
                if cid not in seen and cid in by_id:
                    stack.append(cid)

    # 兜底：万一还有未访问的（极端数据异常），追加在末尾
    for n in nodes:
        if n["id"] not in seen:
            result.append(n)
    return result


def load_graph(mindmap_id: str) -> MindMapGraph:
    """一次性把整个导图加载到内存图结构。

    这是 UI 层最常用的入口：打开导图时调用一次。
    """
    nodes = get_nodes(mindmap_id)
    graph = MindMapGraph()
    # 先按 parent_id 排序，确保父节点先加入
    nodes.sort(key=lambda n: (n.parent_id is not None, n.parent_id or ""))
    for node in nodes:
        graph.add_node(node, parent_id=node.parent_id)
    # ⭐ 加载附加边
    for e in get_edges(mindmap_id):
        # 用 DB 的真实 id 直接插入（避免 _next_edge_id 自增冲突）
        from src.mindmap.graph import EdgeData

        graph._edges[e["id"]] = EdgeData(
            id=e["id"], source_id=e["source_id"], target_id=e["target_id"]
        )
        graph._next_edge_id = max(graph._next_edge_id, e["id"] + 1)
    return graph


# ==================== ⭐ Snapshot（TimeEfficient history 用）====================


def take_snapshot(mindmap_id: str) -> dict:
    """⭐ 序列化整个导图的可编辑数据（节点 + 附加边 + 附件 + 根节点缓存）。

    返回 dict，结构：
        {
          "mindmap_id": str,
          "root_node_id": str | None,
          "nodes": [NodeData.to_dict(), ...],
          "edges": [{"id": int, "source_id": str, "target_id": str}, ...],
          "attachments": [{"id": str, "node_id": str, "file_path": str,
                           "file_type": str, "caption": str|None,
                           "sort_order": int, "is_cover": bool}, ...],
        }

    不包含：mindmap.title / description / created_at — 这些是元信息，不进 history。
    """
    with session_scope() as session:
        mm = session.query(MindMapModel).filter_by(id=mindmap_id).first()
        if mm is None:
            raise ValueError(f"导图不存在: {mindmap_id}")
        root_node_id = mm.root_node_id

        node_rows = session.query(NodeModel).filter_by(mindmap_id=mindmap_id).all()
        nodes = []
        for n in node_rows:
            nd = NodeData(
                id=n.id,
                mindmap_id=n.mindmap_id,
                parent_id=n.parent_id,
                text=n.text,
                note=n.note or "",
                color=n.color or "#4A90E2",
                pos_x=n.pos_x or 0.0,
                pos_y=n.pos_y or 0.0,
                is_expanded=bool(n.is_expanded),
                search_source=n.search_source,
                image_path=n.image_path,
                image_caption=n.image_caption,
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            nodes.append(nd.to_dict())

        # ⭐⭐ 关键：在 Python 层按 DFS 序排序，保证父永远在子前。
        # SQL ORDER BY parent_id ASC 不行（a1 < a2 字典序，与父子关系无关）。
        nodes = _sort_nodes_dfs(nodes)

        edge_rows = session.query(EdgeModel).filter_by(mindmap_id=mindmap_id).all()
        edges = [
            {"id": e.id, "source_id": e.source_id, "target_id": e.target_id}
            for e in edge_rows
        ]

        att_rows = (
            session.query(NodeAttachmentModel)
            .filter(
                NodeAttachmentModel.node_id.in_(
                    session.query(NodeModel.id).filter_by(mindmap_id=mindmap_id)
                )
            )
            .all()
        )
        attachments = [
            {
                "id": a.id,
                "node_id": a.node_id,
                "file_path": a.file_path,
                "file_type": a.file_type,
                "caption": a.caption,
                "sort_order": a.sort_order,
                "is_cover": a.is_cover,
            }
            for a in att_rows
        ]

        return {
            "mindmap_id": mindmap_id,
            "root_node_id": root_node_id,
            "nodes": nodes,
            "edges": edges,
            "attachments": attachments,
        }


def restore_snapshot(snapshot: dict) -> None:
    """⭐ 把 snapshot 写回 DB（节点 + 附加边 + 附件 + root_node_id）。

    策略：DELETE 该 mindmap_id 的所有 nodes/edges/attachments，再按 snapshot 顺序 INSERT。

    为何不用 ORM session.add：SQLAlchemy 按 dependency 排序 flush 时，edges 可能
    先于 nodes INSERT（Edge 只 FK mindmap_id，不 FK node_id）。改用 raw SQL，按
    nodes → edges → attachments 顺序手动 INSERT，FK 必定满足。

    Raises:
        ValueError: mindmap 不存在、edges / attachments 引用了不在 snapshot.nodes
                    里的 node_id。
    """
    mindmap_id = snapshot["mindmap_id"]
    from sqlalchemy import text

    from src.storage.db import get_engine

    # ⭐ 预校验：mindmap 存在 + 边/附件引用完整性。失败立刻 raise，
    # 避免 DELETE 后才发现 INSERT 撞 FK → 事务回滚 + 数据丢失。
    node_ids = {n["id"] for n in snapshot["nodes"]}
    for ed in snapshot["edges"]:
        if ed["source_id"] not in node_ids or ed["target_id"] not in node_ids:
            raise ValueError(
                f"snapshot 边引用了不存在的节点: "
                f"edge {ed['id']} → ({ed['source_id']}, {ed['target_id']})"
            )
    for ad in snapshot["attachments"]:
        if ad["node_id"] not in node_ids:
            raise ValueError(
                f"snapshot 附件引用了不存在的节点: "
                f"attachment {ad['id']} → {ad['node_id']}"
            )

    engine = get_engine()
    with engine.begin() as conn:
        # 0) 校验 mindmap 存在（无此行 INSERT nodes 时 FK 失败会导致静默回滚）
        mm_row = conn.execute(
            text("SELECT id FROM mindmaps WHERE id = :mid"), {"mid": mindmap_id}
        ).first()
        if mm_row is None:
            raise ValueError(f"导图不存在: {mindmap_id}")

        # 1) 清理 attachments（按现有 node_id 范围）
        existing_node_ids = [
            row[0]
            for row in conn.execute(
                text("SELECT id FROM nodes WHERE mindmap_id = :mid"),
                {"mid": mindmap_id},
            ).fetchall()
        ]
        if existing_node_ids:
            ph = ",".join([f":n{i}" for i in range(len(existing_node_ids))])
            params = {f"n{i}": nid for i, nid in enumerate(existing_node_ids)}
            conn.execute(
                text(f"DELETE FROM node_attachments WHERE node_id IN ({ph})"),
                params,
            )

        # 2) 删 edges / nodes（顺序无关）
        conn.execute(
            text("DELETE FROM edges WHERE mindmap_id = :mid"), {"mid": mindmap_id}
        )
        conn.execute(
            text("DELETE FROM nodes WHERE mindmap_id = :mid"), {"mid": mindmap_id}
        )

        # 3) INSERT nodes
        for nd in snapshot["nodes"]:
            conn.execute(
                text("""INSERT INTO nodes
                    (id, mindmap_id, parent_id, text, note, color,
                     pos_x, pos_y, is_expanded, search_source,
                     image_path, image_caption,
                     created_at, updated_at)
                    VALUES
                    (:id, :mid, :pid, :text, :note, :color,
                     :px, :py, :ie, :ss,
                     :ip, :ic,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""),
                {
                    "id": nd["id"],
                    "mid": mindmap_id,
                    "pid": nd.get("parent_id"),
                    "text": nd.get("text", "新节点"),
                    "note": nd.get("note", "") or "",
                    "color": nd.get("color", "#4A90E2") or "#4A90E2",
                    "px": nd.get("pos_x", 0.0) or 0.0,
                    "py": nd.get("pos_y", 0.0) or 0.0,
                    "ie": 1 if nd.get("is_expanded", True) else 0,
                    "ss": nd.get("search_source"),
                    "ip": nd.get("image_path"),
                    "ic": nd.get("image_caption"),
                },
            )

        # 4) INSERT edges
        for ed in snapshot["edges"]:
            conn.execute(
                text("""INSERT INTO edges (id, mindmap_id, source_id, target_id)
                        VALUES (:id, :mid, :src, :tgt)"""),
                {
                    "id": ed["id"],
                    "mid": mindmap_id,
                    "src": ed["source_id"],
                    "tgt": ed["target_id"],
                },
            )

        # 5) INSERT attachments
        for ad in snapshot["attachments"]:
            conn.execute(
                text("""INSERT INTO node_attachments
                    (id, node_id, file_path, file_type, caption, sort_order, is_cover,
                     created_at)
                    VALUES
                    (:id, :nid, :fp, :ft, :cap, :so, :cv,
                     CURRENT_TIMESTAMP)"""),
                {
                    "id": ad["id"],
                    "nid": ad["node_id"],
                    "fp": ad["file_path"],
                    "ft": ad.get("file_type", "image"),
                    "cap": ad.get("caption"),
                    "so": ad.get("sort_order", 0),
                    "cv": 1 if ad.get("is_cover") else 0,
                },
            )

        # 6) 更新 root_node_id
        conn.execute(
            text("UPDATE mindmaps SET root_node_id = :rn WHERE id = :mid"),
            {"rn": snapshot.get("root_node_id"), "mid": mindmap_id},
        )


# ==================== ⭐ NodeAttachment CRUD ====================


def add_attachment(
    node_id: str,
    file_path: str,
    file_type: str = "image",
    caption: str | None = None,
    is_cover: bool = False,
) -> str:
    """给节点添加一个附件。

    Args:
        node_id: 节点 ID
        file_path: 附件相对路径（已由 AttachmentManager.import_attachment 返回）
        file_type: 'image' / 'document'
        caption: 可选说明
        is_cover: 是否设为主图（封面）

    Returns:
        新附件的 ID
    """
    with session_scope() as session:
        # 新附件排在最后
        max_order = (
            session.query(NodeAttachmentModel).filter_by(node_id=node_id).count()
        )
        att = NodeAttachmentModel(
            node_id=node_id,
            file_path=file_path,
            file_type=file_type,
            caption=caption,
            is_cover=is_cover,
            sort_order=max_order,
        )
        session.add(att)
        session.flush()
        att_id = att.id
        logger.info(f"添加附件到节点 {node_id[:8]}: {file_path}")
        return att_id


def list_attachments(node_id: str) -> list[dict]:
    """列出节点的所有附件，按 sort_order 升序，封面置顶。

    Returns:
        [{id, file_path, file_type, caption, sort_order, is_cover, created_at}, ...]
    """
    with session_scope() as session:
        rows = (
            session.query(NodeAttachmentModel)
            .filter_by(node_id=node_id)
            .order_by(
                NodeAttachmentModel.sort_order.asc(),
                NodeAttachmentModel.created_at.asc(),
            )
            .all()
        )
        return [
            {
                "id": r.id,
                "file_path": r.file_path,
                "file_type": r.file_type,
                "caption": r.caption,
                "sort_order": r.sort_order,
                "is_cover": r.is_cover,
                "created_at": r.created_at,
            }
            for r in rows
        ]


def get_attachment(attachment_id: str) -> dict | None:
    """按 ID 获取附件。"""
    with session_scope() as session:
        r = session.query(NodeAttachmentModel).filter_by(id=attachment_id).first()
        if not r:
            return None
        return {
            "id": r.id,
            "node_id": r.node_id,
            "file_path": r.file_path,
            "file_type": r.file_type,
            "caption": r.caption,
            "sort_order": r.sort_order,
            "is_cover": r.is_cover,
            "created_at": r.created_at,
        }


def update_attachment_caption(attachment_id: str, caption: str | None) -> None:
    """更新附件说明。"""
    with session_scope() as session:
        r = session.query(NodeAttachmentModel).filter_by(id=attachment_id).first()
        if r:
            r.caption = caption


def set_attachment_cover(attachment_id: str) -> None:
    """把某个附件设为主图（封面）—— 同时取消该节点其他附件的封面。"""
    with session_scope() as session:
        r = session.query(NodeAttachmentModel).filter_by(id=attachment_id).first()
        if not r:
            return
        # 取消同节点其他附件的封面
        session.query(NodeAttachmentModel).filter(
            NodeAttachmentModel.node_id == r.node_id,
            NodeAttachmentModel.id != attachment_id,
        ).update({"is_cover": False})
        r.is_cover = True


def move_attachment(attachment_id: str, direction: str) -> None:
    """调整附件顺序（direction: 'up' 或 'down'）。

    简单实现：和相邻 sort_order 互换。
    """
    if direction not in ("up", "down"):
        raise ValueError(f"direction 必须是 'up' 或 'down'，收到: {direction!r}")
    with session_scope() as session:
        r = session.query(NodeAttachmentModel).filter_by(id=attachment_id).first()
        if not r:
            return
        node_id = r.node_id
        # 找邻居
        if direction == "up":
            neighbor = (
                session.query(NodeAttachmentModel)
                .filter(
                    NodeAttachmentModel.node_id == node_id,
                    NodeAttachmentModel.sort_order < r.sort_order,
                )
                .order_by(NodeAttachmentModel.sort_order.desc())
                .first()
            )
        else:
            neighbor = (
                session.query(NodeAttachmentModel)
                .filter(
                    NodeAttachmentModel.node_id == node_id,
                    NodeAttachmentModel.sort_order > r.sort_order,
                )
                .order_by(NodeAttachmentModel.sort_order.asc())
                .first()
            )
        if neighbor:
            r.sort_order, neighbor.sort_order = neighbor.sort_order, r.sort_order


def reorder_attachments(node_id: str, ordered_ids: list[str]) -> None:
    """⭐ 按给定顺序重排节点所有附件的 sort_order（拖拽排序用）。

    Args:
        node_id: 节点 ID
        ordered_ids: 附件 ID 的新顺序（如 list_attachments 返回的 id 列表）

    一次性事务处理，不存在的 ID 跳过。
    """
    with session_scope() as session:
        for idx, att_id in enumerate(ordered_ids):
            r = (
                session.query(NodeAttachmentModel)
                .filter_by(id=att_id, node_id=node_id)
                .first()
            )
            if r:
                r.sort_order = idx
    logger.info(f"重排节点 {node_id[:8]} 的附件顺序：{len(ordered_ids)} 个")


def delete_attachment(attachment_id: str, delete_file: bool = True) -> None:
    """删除附件（默认同时删文件，引用计数 = 0 才真正删）。

    Args:
        attachment_id: 附件 ID
        delete_file: 是否真删文件（True = 是，False = 只删记录，保留文件）
    """
    file_path = None
    with session_scope() as session:
        r = session.query(NodeAttachmentModel).filter_by(id=attachment_id).first()
        if not r:
            return
        file_path = r.file_path
        session.delete(r)

    if delete_file and file_path:
        # 引用计数检查
        with session_scope() as session:
            count = (
                session.query(NodeAttachmentModel)
                .filter_by(file_path=file_path)
                .count()
            )
            if count == 0:
                get_attachment_manager().delete_attachment(file_path)
                logger.debug(f"清理孤儿附件: {file_path}")


def count_attachments(node_id: str) -> int:
    """统计节点附件数（用于节点徽章显示）。"""
    with session_scope() as session:
        return session.query(NodeAttachmentModel).filter_by(node_id=node_id).count()


def list_all_image_attachments(mindmap_id: str) -> list[dict]:
    """列出整个导图里所有图片附件（用于全屏浏览的 prev/next 导航）。

    按节点 DFS 顺序。
    """
    nodes = get_nodes(mindmap_id)
    # 按 parent_id 排序模拟 DFS
    nodes.sort(key=lambda n: (n.parent_id is not None, n.parent_id or "", n.pos_y))
    result = []
    for n in nodes:
        for att in list_attachments(n.id):
            if att["file_type"] == "image":
                result.append({**att, "node_id": n.id, "node_text": n.text})
    return result


__all__ = [
    "create_mindmap",
    "list_mindmaps",
    "get_mindmap",
    "update_mindmap_title",
    "delete_mindmap",
    "add_node",
    "get_nodes",
    "update_node_text",
    "update_node_note",
    "update_node_position",
    "update_node_color",
    "update_node_image",  # 旧字段（保留向后兼容）
    "get_node_image",  # 旧字段
    "delete_node",
    "load_graph",
    # ⭐ 多附件
    "add_attachment",
    "list_attachments",
    "get_attachment",
    "update_attachment_caption",
    "set_attachment_cover",
    "move_attachment",
    "reorder_attachments",
    "delete_attachment",
    "count_attachments",
    "list_all_image_attachments",
]
