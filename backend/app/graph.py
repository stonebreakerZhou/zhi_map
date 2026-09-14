"""Bounded SQL projection of native branches. Camera/contact data never enters context."""

import json
import math

from sqlalchemy import Integer, and_, cast, delete, func, insert, or_, select, update, text

from .domain.utf16 import utf16_length
from .graph_schema import contacts, positions
from .repository import Repository, branches, dump, entries
from .services import error

WORLD_LIMIT = 1_000_000


class GraphRepository(Repository):
    def ensure_layout(self):
        """Initialize missing positions in SQLite; never materialize history in Python.

        Existing positions (including explicit moves) are recursion anchors. Appending a
        child only allocates that child, and version zero remains the first move token.
        """
        missing = self.db.scalar(select(branches.c.id).select_from(branches.outerjoin(positions,
            and_(branches.c.user_id == positions.c.user_id, branches.c.id == positions.c.branch_id)))
            .where(self.owned(branches), positions.c.branch_id.is_(None)).limit(1))
        if missing is None:
            return
        self.db.execute(text("""
            WITH RECURSIVE ranked AS (
              SELECT b.id, json_extract(b.data,'$.parent.branchId') AS parent,
                row_number() OVER (
                  PARTITION BY json_extract(b.data,'$.parent.branchId')
                  ORDER BY b.position,b.id) - 1 AS slot
              FROM history_branches b WHERE b.user_id=:uid
            ), tree(id,x,y,depth) AS (
              SELECT r.id, coalesce(p.x,(r.slot/512)*1800), coalesce(p.y,(r.slot%512)*1600),0
              FROM ranked r LEFT JOIN graph_positions p
                ON p.user_id=:uid AND p.branch_id=r.id
              WHERE r.parent IS NULL
              UNION ALL
              SELECT r.id,coalesce(p.x,min(t.x+1040,999999)),
                coalesce(p.y,min(999999,max(-999999,t.y+
                  CASE WHEN r.slot%2=0 THEN (r.slot/2+1)*240
                       ELSE -(r.slot/2+1)*240 END))),t.depth+1
              FROM tree t JOIN ranked r ON r.parent=t.id
              LEFT JOIN graph_positions p ON p.user_id=:uid AND p.branch_id=r.id
              WHERE t.depth<10000
            )
            INSERT OR IGNORE INTO graph_positions(user_id,branch_id,x,y,version)
            SELECT :uid,id,x,y,0 FROM tree
        """), {"uid": self.uid})
        self.db.commit()

    def root(self, bid):
        self.ensure()
        seen = set()
        current = bid
        # Bounded ancestry walk reads only IDs, not branch drafts or entries.
        for _ in range(128):
            if current in seen:
                error(409, "主树包含环，无法定位所属根。")
            seen.add(current)
            row = self.db.execute(select(branches.c.id,
                func.json_extract(branches.c.data, "$.parent.branchId").label("parent"))
                .where(self.owned(branches), branches.c.id == current)).first()
            if not row:
                error(404, "上级主题已不存在。")
            if not row.parent:
                return {"rootId": current, "depth": len(seen) - 1}
            current = row.parent
        return {"rootId": None, "depth": 128, "continuationId": current, "truncated": True}

    def query(self, bounds, focus=None, search="", cursor=-1, reading=None, expand=None, child_cursor=-1):
        self.ensure()
        self.ensure_layout()
        x, y = positions.c.x, positions.c.y
        parent = func.json_extract(branches.c.data, "$.parent.branchId")
        base = branches.outerjoin(positions, and_(
            branches.c.user_id == positions.c.user_id, branches.c.id == positions.c.branch_id))
        spatial = and_(x >= bounds[0], y >= bounds[1], x <= bounds[2], y <= bounds[3])
        if focus:
            if not self.db.scalar(select(branches.c.id).where(self.owned(branches), branches.c.id == focus)):
                error(404, "主题不存在。")
            spatial = or_(spatial, branches.c.id == focus, parent == focus)
        path = []
        continuation = None
        current = focus
        for _ in range(40):
            if not current or current in path:
                break
            path.append(current)
            current = self.db.scalar(select(parent).where(self.owned(branches), branches.c.id == current))
        if current and current not in path:
            continuation = current
        condition = and_(self.owned(branches), spatial,
                         func.json_extract(branches.c.data, "$.title").contains(search, autoescape=True))
        if search:
            condition = and_(self.owned(branches), func.json_extract(branches.c.data, "$.title").contains(search, autoescape=True))
        total = self.db.scalar(select(func.count()).select_from(branches).where(self.owned(branches)))
        covered = self.db.scalar(select(func.count()).select_from(base).where(condition))
        columns = select(
            branches.c.id, branches.c.position, branches.c.revision,
            func.substr(func.json_extract(branches.c.data, "$.title"), 1, 160).label("title"),
            parent.label("parent"), x.label("x"), y.label("y"),
            func.coalesce(positions.c.version, 0).label("layoutVersion"),
        ).select_from(base)
        rows = self.db.execute(columns.where(condition, branches.c.position > cursor)
            .order_by(branches.c.position).limit(199)).mappings().all()
        # Reserve one object for the aggregate, with a stable cursor in insertion order.
        nodes = [dict(r) for r in rows[:198]]
        next_cursor = rows[197]["position"] if len(rows) == 199 else None
        if focus:
            focal = self.db.execute(columns.where(self.owned(branches), branches.c.id == focus)).mappings().first()
            if focal:
                nodes = [dict(focal)] + [n for n in nodes if n["id"] != focus]
        priority = list(path)
        if focus:
            for relation in self.db.execute(select(contacts.c.source, contacts.c.target).where(
                self.owned(contacts), or_(contacts.c.source == focus, contacts.c.target == focus)).limit(40)):
                priority.append(relation.target if relation.source == focus else relation.source)
            reference_source = func.json_extract(entries.c.data, "$.source.branchId")
            for relation in self.db.execute(select(entries.c.branch_id, reference_source.label("source")).where(
                self.owned(entries), func.json_extract(entries.c.data, "$.kind") == "reference",
                or_(entries.c.branch_id == focus, reference_source == focus)).limit(40)):
                priority.append(relation.source if relation.branch_id == focus else relation.branch_id)
        child_next = None
        if expand:
            children = self.db.execute(columns.where(self.owned(branches), parent == expand,
                branches.c.position > child_cursor).order_by(branches.c.position).limit(41)).mappings().all()
            priority.extend(r["id"] for r in children[:40])
            if len(children) > 40:
                child_next = children[39]["position"]
        if priority:
            preferred = {r["id"]: dict(r) for r in self.db.execute(columns.where(
                self.owned(branches), branches.c.id.in_(priority))).mappings()}
            nodes = [preferred[i] for i in dict.fromkeys(priority) if i in preferred] + [n for n in nodes if n["id"] not in preferred]
            nodes = nodes[:199]
        ids = [n["id"] for n in nodes]
        counts = dict(self.db.execute(select(parent, func.count()).where(self.owned(branches),
            parent.in_(ids)).group_by(parent)).all())
        edges = []
        for n in nodes:
            n["kind"] = "branch" if n["parent"] else "root"
            n["previews"] = []
            n["childrenCount"] = counts.get(n["id"], 0)
            n["visibleChildren"] = sum(child["parent"] == n["id"] for child in nodes)
            if n["parent"] in ids:
                edges.append({"id": "parent:" + n["id"], "type": "parent",
                              "source": n["parent"], "target": n["id"]})
        for row in self.db.execute(select(contacts).where(self.owned(contacts),
                contacts.c.source.in_(ids), contacts.c.target.in_(ids)).limit(400 - len(edges))).mappings():
            edges.append({"id": "contact:" + row["source"] + ":" + row["target"],
                          "type": "contact", "source": row["source"], "target": row["target"]})
        source = func.json_extract(entries.c.data, "$.source.branchId")
        for row in self.db.execute(select(entries.c.id, entries.c.branch_id, source.label("source"))
                .where(self.owned(entries), entries.c.branch_id.in_(ids), source.in_(ids),
                       func.json_extract(entries.c.data, "$.kind") == "reference")
                .limit(400 - len(edges))).mappings():
            edges.append({"id": row["id"], "type": "reference",
                          "source": row["source"], "target": row["branch_id"]})
        for n in nodes[:12]:
            # SQLite substr limits materialized text even for multi-megabyte messages.
            stmt = select(entries.c.id,
                func.substr(func.json_extract(entries.c.data, "$.text"), 1, 1024).label("text"),
                func.json_extract(entries.c.data, "$.source").label("source"),
                func.json_extract(entries.c.data, "$.range.start").label("base"))
            stmt = stmt.where(self.owned(entries), entries.c.branch_id == n["id"],
                              func.json_extract(entries.c.data, "$.kind") == "message")
            if n["id"] == focus and reading:
                pos = self.db.scalar(select(entries.c.position).where(self.owned(entries),
                    entries.c.branch_id == focus, entries.c.id == reading))
                if pos is not None:
                    stmt = stmt.where(entries.c.position >= pos).order_by(entries.c.position)
                else:
                    stmt = stmt.order_by(entries.c.position.desc())
            else:
                stmt = stmt.order_by(entries.c.position.desc())
            for e in self.db.execute(stmt.limit(2)).mappings():
                text = e["text"] or ""
                stripped = text.lstrip()
                excerpt = stripped.split("\n\n", 1)[0][:120]
                if not excerpt:
                    continue
                start = utf16_length(text[:len(text) - len(stripped)])
                n["previews"].append({"text": excerpt, "entryId": e["id"],
                    "branchId": n["id"], "start": start, "end": start + utf16_length(excerpt),
                    "source": json.loads(e["source"]),
                    "sourceRange": {"start": (e["base"] or 0) + start,
                                    "end": (e["base"] or 0) + start + utf16_length(excerpt)},
                    "version": n["revision"]})
        result = {**self.view(), "nodes": nodes, "edges": edges, "total": total,
                  "coverage": {"bounds": bounds, "matching": covered, "returned": len(nodes)},
                  "aggregate": max(0, total - len(nodes)),
                  "nextCursor": next_cursor, "path": path, "pathContinuation": continuation,
                  "expanded": expand, "childNextCursor": child_next}
        if len(dump(result).encode("utf-8")) > 256 * 1024:
            for n in nodes:
                n["previews"] = []
        if len(dump(result).encode("utf-8")) > 256 * 1024:
            error(413, "图投影超过字节预算，请缩小查询范围。")
        return result

    def position(self, bid, x, y, version):
        self.ensure()
        self.db.rollback()
        self.db.execute(text("BEGIN IMMEDIATE"))
        self.meta(bid)
        if not all(math.isfinite(v) and abs(v) <= WORLD_LIMIT for v in (x, y)):
            error(400, "世界坐标须为 ±1,000,000 内的有限数。")
        condition = and_(self.owned(positions), positions.c.branch_id == bid)
        old = self.db.scalar(select(positions.c.version).where(condition))
        if (old or 0) != version:
            error(409, "布局版本已变化，请刷新位置。")
        if old is None:
            self.db.execute(insert(positions).values(user_id=self.uid, branch_id=bid, x=x, y=y, version=1))
        else:
            if self.db.execute(update(positions).where(condition, positions.c.version == version)
                    .values(x=x, y=y, version=version + 1)).rowcount != 1:
                error(409, "布局版本已变化。")
        self.db.commit()
        return {"branchId": bid, "x": x, "y": y, "layoutVersion": version + 1}

    def contact(self, source, targets, unlink=False):
        self.ensure()
        self.db.rollback()
        self.db.execute(text("BEGIN IMMEDIATE"))
        if not 1 <= len(targets) <= 20 or len(set(targets)) != len(targets) or source in targets:
            error(400, "联系须有 1–20 个不同目标，不能关联自己。")
        for bid in [source, *targets]:
            self.meta(bid)
        pairs = [tuple(sorted((source, t))) for t in targets]
        for a, b in pairs:
            exists = self.db.scalar(select(contacts.c.source).where(self.owned(contacts),
                contacts.c.source == a, contacts.c.target == b))
            if bool(exists) == (not unlink):
                error(409, "联系已存在。" if exists else "联系已断开。")
        for a, b in pairs:
            if unlink:
                self.db.execute(delete(contacts).where(self.owned(contacts), contacts.c.source == a, contacts.c.target == b))
            else:
                self.db.execute(insert(contacts).values(user_id=self.uid, source=a, target=b))
        self.db.commit()
        return {"ok": True, "type": "contact", "contextIncluded": False}
