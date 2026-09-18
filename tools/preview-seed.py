"""Development helper: seed a deterministic topic tree into the preview database.

The fixture backend answers chat requests from a queue, which makes UI review runs flaky, so the
preview workspace is written straight into the same tables the repository uses.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import create_engine, select  # noqa: E402

from app.db import Workspace  # noqa: E402
from app.repository import branches, entries, heads, sessions  # noqa: E402


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def entry(branch_id, session_id, role, text, source=None):
    return {
        "id": str(uuid.uuid4()),
        "kind": "message",
        "role": role,
        "text": text,
        "inherited": False,
        "simulated": False,
        "createdAt": stamp(),
        "source": source or {"sessionId": session_id, "sessionTitle": "二次函数：从配方看见顶点", "branchId": branch_id, "branchTitle": "二次函数", "messageId": ""},
        "branchId": branch_id,
    }


def main() -> None:
    database = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/vscode-project/git-project/linbo/data/devui.db")
    arg = sys.argv[3] if len(sys.argv) > 3 else None
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    workspaces = Workspace.__table__
    if arg == '--list':
        with engine.connect() as connection:
            for row in connection.execute(select(Workspace.user_id, Workspace.updated_at).order_by(Workspace.updated_at)):
                print(row[0], row[1])
        return
    only = arg
    with engine.begin() as connection:
        # Seed every known user by default: the browser's anonymous cookie decides which workspace it
        # reads, and a headless profile does not reliably persist that cookie between runs. Pass a user
        # id as the third argument to seed just that session.
        owners = [row[0] for row in connection.execute(select(Workspace.user_id))]
        if only:
            owners = [only]
        elif not owners:
            raise SystemExit("no users yet: open the preview once so the app creates an anonymous session")
        for table in (entries, branches, sessions, heads):
            connection.execute(table.delete().where(table.c.user_id.in_(owners)))
        connection.execute(workspaces.delete().where(workspaces.c.user_id.in_(owners)))
        session_id = str(uuid.uuid4())
        root_id, child_a, child_b = (str(uuid.uuid4()) for _ in range(3))

        root_text = "二次函数 y = x² - 4x + 1 的顶点在哪里？为什么配方能看出最小值？"
        answer = (
            "把函数写成「平方 + 常数」就能读出顶点。\n\n"
            "$$y = x^2 - 4x + 1 = (x-2)^2 - 3$$\n\n"
            "平方项总是非负，所以 (x-2)² 最小为 0，顶点落在 (2, -3)。"
        )
        follow = "那开口方向和顶点有什么关系？"
        follow_answer = "开口方向决定顶点是最高点还是最低点：a > 0 时顶点最低，a < 0 时顶点最高。"
        root_entries = [
            entry(root_id, session_id, "user", root_text),
            entry(root_id, session_id, "assistant", answer),
            entry(root_id, session_id, "user", follow),
            entry(root_id, session_id, "assistant", follow_answer),
        ]
        selection = {"start": 0, "end": len(root_text), "text": root_text, "entryId": root_entries[0]["id"]}
        child_a_entries = [
            entry(child_a, session_id, "user", "配方这一步为什么要写成平方加常数？"),
            entry(child_a, session_id, "assistant", "因为平方项的最小值可以立刻看出，不需要再求导。"),
        ]
        child_b_entries = [
            entry(child_b, session_id, "user", "顶点式还能读出对称轴吗？"),
            entry(child_b, session_id, "assistant", "可以：对称轴是 x = 2，而且它就是顶点的横坐标。"),
        ]
        plan = [
            (root_id, "二次函数：从配方看见顶点", None, root_entries),
            (child_a, "配方这一步为什么要写成平方加常数？", {"branchId": root_id, "branchTitle": "二次函数：从配方看见顶点", "entryId": root_entries[0]["id"]}, child_a_entries),
            (child_b, "顶点式还能读出对称轴吗？", {"branchId": root_id, "branchTitle": "二次函数：从配方看见顶点", "entryId": root_entries[2]["id"]}, child_b_entries),
        ]
        # Optional extra children make label density and zoom rendering easier to review.
        extra = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        for step in range(extra):
            more = str(uuid.uuid4())
            plan.append((
                more,
                f"第 {step + 1} 个延伸讨论：判别式与交点",
                {"branchId": root_id, "branchTitle": "二次函数：从配方看见顶点", "entryId": root_entries[0]["id"]},
                [
                    entry(more, session_id, "user", f"判别式在第 {step + 1} 个例子里怎么用？"),
                    entry(more, session_id, "assistant", "判别式 Δ = b² - 4ac 决定抛物线与 x 轴的交点个数。"),
                ],
            ))

        for uid in owners:
            connection.execute(sessions.insert().values(user_id=uid, id=session_id, position=0, data=json.dumps({"id": session_id, "title": "二次函数：从配方看见顶点"})))
            for index, (bid, title, parent, rows) in enumerate(plan):
                data = {
                    "id": bid,
                    "sessionId": session_id,
                    "title": title,
                    "tags": [],
                    "parent": parent,
                    "kept": False,
                    "draft": "",
                    "entries": [],
                    "selection": selection if parent else None,
                    "metadataDone": True,
                }
                connection.execute(branches.insert().values(user_id=uid, id=bid, position=index, revision=1, data=json.dumps(data)))
                for position, row in enumerate(rows):
                    connection.execute(entries.insert().values(user_id=uid, branch_id=bid, position=position, id=row["id"], data=json.dumps(row)))
            connection.execute(heads.insert().values(user_id=uid, active=root_id))
            connection.execute(workspaces.insert().values(user_id=uid, version=9, state=json.dumps({"version": 2, "sessions": [{"id": session_id, "title": "二次函数：从配方看见顶点"}], "branches": [], "active": root_id}), updated_at=datetime.now(timezone.utc)))
        print("seeded", len(owners), "users", session_id, root_id, child_a, child_b)


if __name__ == "__main__":
    main()
