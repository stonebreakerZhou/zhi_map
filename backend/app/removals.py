"""Operation-scoped, disk-backed tombstones. Unrelated revisions never invalidate recovery."""

import json
import time

from sqlalchemy import LargeBinary, cast, delete, func, insert, select, update, text

from .db import Workspace, utcnow
from .graph_schema import contacts, operations, positions
from .repository import Repository, branches, dump, entries, heads, sessions
from .services import error

BUDGET = 8 * 1024 * 1024


class RemovalRepository(Repository):
    def receipt(self, operation_id):
        self.ensure()
        row = self.db.execute(select(operations).where(self.owned(operations),
            operations.c.id == operation_id)).mappings().first()
        if not row:
            error(404, "移除操作不存在。")
        return self.public(row)

    def public(self, row):
        status = row["status"]
        if status == "removed" and row["expires"] <= int(time.time()):
            status = "expired"
        return {"operationId": row["id"], "targets": json.loads(row["targets"]),
                "committedAt": row["committed"], "expiresAt": row["expires"], "status": status}

    def recent(self, cursor=""):
        self.ensure()
        condition = (self.owned(operations), operations.c.expires > int(time.time()),
                     operations.c.status == "removed")
        rows = self.db.execute(select(operations.c.id, operations.c.targets, operations.c.committed,
            operations.c.expires, operations.c.status).where(*condition, operations.c.id > cursor)
            .order_by(operations.c.id).limit(41)).mappings().all()
        return {"items": [self.public(r) for r in rows[:40]],
                "count": self.db.scalar(select(func.count()).select_from(operations).where(*condition)),
                "nextCursor": rows[39]["id"] if len(rows) > 40 else None}

    def bump(self):
        self.db.execute(update(Workspace).where(Workspace.user_id == self.uid)
            .values(version=Workspace.version + 1, updated_at=utcnow()))

    def remove(self, operation_id, targets):
        self.ensure()
        self.db.rollback()
        self.db.execute(text("BEGIN IMMEDIATE"))
        existing = self.db.execute(select(operations).where(self.owned(operations),
            operations.c.id == operation_id)).mappings().first()
        ids = [t["id"] for t in targets]
        if existing:
            if [t["id"] for t in json.loads(existing["targets"])] != ids:
                error(409, "operationId 已用于另一目标集。")
            return {**self.view(), **self.public(existing), "affectedIds": ids}
        if not 1 <= len(ids) <= 20 or len(set(ids)) != len(ids):
            error(400, "每次移除须为 1–20 个不同主题。")
        for t in targets:
            if self.meta(t["id"])["revision"] != t["revision"]:
                error(409, "目标主题已更新，请重新检查后移除。")
        child_condition = (self.owned(branches), branches.c.id.not_in(ids),
                           func.json_extract(branches.c.data, "$.parent.branchId").in_(ids))
        # Preflight bytes before materializing any history or high-fanout dependencies.
        self.check_size(ids, BUDGET)
        child_bytes = self.db.scalar(select(func.coalesce(func.sum(func.length(cast(branches.c.data, LargeBinary))), 0)).where(*child_condition))
        if child_bytes > BUDGET:
            error(413, "移除依赖超过 8 MiB，未移除任何主题。")
        saved = {"branches": [dict(r) for r in self.db.execute(select(branches).where(self.owned(branches), branches.c.id.in_(ids))).mappings()],
                 "entries": [dict(r) for r in self.db.execute(select(entries).where(self.owned(entries), entries.c.branch_id.in_(ids))).mappings()],
                 "children": [dict(r) for r in self.db.execute(select(branches).where(*child_condition)).mappings()],
                 "contacts": [dict(r) for r in self.db.execute(select(contacts).where(self.owned(contacts), (contacts.c.source.in_(ids) | contacts.c.target.in_(ids))).limit(100001)).mappings()],
                 "positions": [dict(r) for r in self.db.execute(select(positions).where(self.owned(positions), positions.c.branch_id.in_(ids))).mappings()]}
        raw = dump(saved)
        if len(raw.encode("utf-8")) > BUDGET:
            error(413, "移除恢复资料超过 8 MiB，未移除任何主题。")
        for child in saved["children"]:
            data = json.loads(child["data"])
            data["sourceOrigin"] = data["parent"]
            data["parent"] = None
            self.db.execute(update(branches).where(self.owned(branches), branches.c.id == child["id"])
                .values(data=dump(data), revision=child["revision"] + 1))
        self.db.execute(delete(entries).where(self.owned(entries), entries.c.branch_id.in_(ids)))
        self.db.execute(delete(branches).where(self.owned(branches), branches.c.id.in_(ids)))
        self.db.execute(delete(positions).where(self.owned(positions), positions.c.branch_id.in_(ids)))
        self.db.execute(delete(contacts).where(self.owned(contacts), contacts.c.source.in_(ids) | contacts.c.target.in_(ids)))
        active = self.view()["active"]
        if active in ids:
            active = self.db.scalar(select(branches.c.id).where(self.owned(branches)).order_by(branches.c.position).limit(1))
            self.db.execute(update(heads).where(self.owned(heads)).values(active=active))
        now = int(time.time())
        self.db.execute(update(operations).where(self.owned(operations), operations.c.expires <= now,
            operations.c.status == "removed").values(data="{}", status="expired"))
        self.db.execute(insert(operations).values(user_id=self.uid, id=operation_id,
            committed=now, expires=now + 600, status="removed", data=raw,
            targets=dump([{"id": r["id"], "title": json.loads(r["data"])["title"]} for r in sorted(saved["branches"], key=lambda r: ids.index(r["id"]))])))
        self.bump()
        self.db.commit()
        return {**self.view(), **self.receipt(operation_id), "affectedIds": ids + [c["id"] for c in saved["children"]]}

    def restore(self, operation_id, as_root=False):
        self.ensure()
        self.db.rollback()
        self.db.execute(text("BEGIN IMMEDIATE"))
        receipt = self.receipt(operation_id)
        ids = [t["id"] for t in receipt["targets"]]
        if receipt["status"] == "restored":
            return {**self.view(), **receipt, "affectedIds": ids}
        if receipt["status"] == "expired":
            error(410, "恢复期限已过。")
        row = self.db.execute(select(operations).where(self.owned(operations), operations.c.id == operation_id)).mappings().one()
        saved = json.loads(row["data"])
        for b in saved["branches"]:
            if self.db.scalar(select(branches.c.id).where(self.owned(branches), branches.c.id == b["id"])):
                error(409, "restore_id_occupied: 原主题 ID 已被占用。")
            data = json.loads(b["data"])
            if not self.db.scalar(select(sessions.c.id).where(self.owned(sessions), sessions.c.id == data["sessionId"])):
                error(409, "restore_session_missing: 原会话已永久删除。")
            parent = (data.get("parent") or {}).get("branchId")
            if not as_root and parent and parent not in ids and not self.db.scalar(select(branches.c.id).where(self.owned(branches), branches.c.id == parent)):
                error(409, "restore_parent_missing: 原父主题已移除；可确认作为独立根恢复。")
        if not as_root:
            for child in saved["children"]:
                version = self.db.scalar(select(branches.c.revision).where(self.owned(branches), branches.c.id == child["id"]))
                if version != child["revision"] + 1:
                    error(409, "restore_child_changed: 子分支已修改；收据仍有效，可确认仅恢复为独立根。")
            for c in saved["contacts"]:
                other = c["source"] if c["source"] not in ids else c["target"]
                if other not in ids and not self.db.scalar(select(branches.c.id).where(self.owned(branches), branches.c.id == other)):
                    error(409, "restore_contact_missing: 联系端点已移除。")
        for b in saved["branches"]:
            data = json.loads(b["data"])
            # Restoring never resumes a cancelled generation.
            if as_root:
                data["sourceOrigin"] = data.get("parent")
                data["parent"] = None
            b["data"] = dump(data)
            b["revision"] += 1
            if self.db.scalar(select(branches.c.id).where(self.owned(branches), branches.c.position == b["position"]).limit(1)):
                # A newly created topic may have reused the removed tail ordinal.
                # Preserve its row and the restored world position; allocate only a new cursor slot.
                b["position"] = self.db.scalar(select(func.max(branches.c.position)).where(self.owned(branches))) + 1
            self.db.execute(insert(branches).values(**b))
        for e in saved["entries"]:
            self.db.execute(insert(entries).values(**e))
        for p in saved["positions"]:
            self.db.execute(insert(positions).values(**p))
        if not as_root:
            for child in saved["children"]:
                self.db.execute(update(branches).where(self.owned(branches), branches.c.id == child["id"])
                    .values(data=child["data"], revision=child["revision"] + 2))
            for c in saved["contacts"]:
                self.db.execute(insert(contacts).values(**c))
        self.db.execute(update(operations).where(self.owned(operations), operations.c.id == operation_id,
            operations.c.status == "removed").values(status="restored", data="{}"))
        self.bump()
        self.db.commit()
        return {**self.view(), **self.receipt(operation_id), "affectedIds": ids}
