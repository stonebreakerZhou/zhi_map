import json
import time

import pytest
from sqlalchemy import insert, select, update, text
from sqlalchemy.orm import Session

from app.domain.utf16 import utf16_slice
from app.domain.workspace import seed_state
from app.graph import GraphRepository
from app.graph_schema import operations
from app.removals import RemovalRepository
from app.repository import Repository, branches, dump, entries, sessions
from app.services import ApiError, context_messages
from .test_history import storage
from .graph_fixtures import seed_large_graph


def setup(db):
    repo = Repository(db, "a")
    state = seed_state()
    repo.replace(state, 0)
    return repo, state["branches"]


def test_native_projection_contacts_utf16_and_layout(storage):
    with Session(storage) as db:
        repo, (a, b) = setup(db)
        graph = GraphRepository(db, "a")
        before = context_messages(repo.context(a["id"]))
        graph.contact(a["id"], [b["id"]])
        result = graph.query([-1000, -1000, 2000, 2000], a["id"])
        assert all(n["parent"] is None for n in result["nodes"])
        assert [e["type"] for e in result["edges"]] == ["contact"]
        for node in result["nodes"]:
            for preview in node["previews"]:
                source = next(e for e in repo.page(node["id"], 40, -1)["items"] if e["id"] == preview["entryId"])
                assert utf16_slice(source["text"], preview["start"], preview["end"]) == preview["text"]
                assert len(preview["text"]) <= 120
        graph.position(a["id"], 130, -140, 0)
        assert repo.view()["revision"] == 1
        assert context_messages(repo.context(a["id"])) == before
        for point in [(float("inf"), 0), (0, float("nan")), (1_000_001, 0)]:
            with pytest.raises(ApiError):
                graph.position(a["id"], *point, 1)
        with pytest.raises(ApiError):
            graph.position(a["id"], 0, 0, 0)
        with pytest.raises(ApiError):
            graph.contact(b["id"], [a["id"]])
        with pytest.raises(ApiError):
            GraphRepository(db, "b").position(a["id"], 1, 1, 0)
        with pytest.raises(ApiError):
            graph.contact(a["id"], [a["id"]])


def test_independent_restore_preserves_unrelated_draft_answer_and_parent(storage):
    with Session(storage) as db:
        repo, (a, b) = setup(db)
        child = repo.action({"type": "fork", "branchId": a["id"], "entryId": a["entries"][0]["id"], "revision": 1})["active"]
        removals = RemovalRepository(db, "a")
        targets = [{"id": a["id"], "revision": repo.meta(a["id"])["revision"]}]
        result = removals.remove("remove-a", targets)
        assert repo.meta(child)["parent"] is None
        assert repo.meta(child)["sourceOrigin"]["branchId"] == a["id"]
        repo.action({"type": "draft", "branchId": b["id"], "text": "another draft 😀", "revision": result["revision"]})
        repo.action({"type": "send", "branchId": b["id"], "revision": repo.view()["revision"]})
        repo.action({"type": "answer", "branchId": b["id"], "text": "another answer", "revision": repo.view()["revision"]})
        unchanged = repo.context(b["id"])
        active = repo.view()["active"]
        restored = removals.restore("remove-a")
        assert restored["active"] == active
        assert repo.context(b["id"]) == unchanged
        assert repo.meta(child)["parent"]["branchId"] == a["id"]
        assert removals.restore("remove-a")["revision"] == restored["revision"]
        assert removals.remove("remove-a", targets)["status"] == "restored"


def test_restore_dependency_conflict_root_confirmation_owner_and_expiry(storage, monkeypatch):
    with Session(storage) as db:
        repo, (a, b) = setup(db)
        child = repo.action({"type": "fork", "branchId": a["id"], "entryId": a["entries"][0]["id"], "revision": 1})["active"]
        remove = RemovalRepository(db, "a")
        result = remove.remove("idempotent", [{"id": a["id"], "revision": repo.meta(a["id"])["revision"]}])
        repo.action({"type": "draft", "branchId": child, "text": "child edited", "revision": result["revision"]})
        with pytest.raises(ApiError, match="restore_child_changed"):
            remove.restore("idempotent")
        db.rollback()
        assert remove.receipt("idempotent")["status"] == "removed"
        remove.restore("idempotent", as_root=True)
        assert repo.meta(child)["draft"] == "child edited"
        assert repo.meta(a["id"])["parent"] is None
        with pytest.raises(ApiError) as foreign:
            RemovalRepository(db, "b").receipt("idempotent")
        assert foreign.value.status == 404
        result = remove.remove("expires", [{"id": b["id"], "revision": repo.meta(b["id"])["revision"]}])
        monkeypatch.setattr("app.removals.time.time", lambda: result["expiresAt"])
        with pytest.raises(ApiError) as expired:
            remove.restore("expires")
        assert expired.value.status == 410


def test_atomic_limits_no_partial_removal(storage):
    with Session(storage) as db:
        repo, (a, b) = setup(db)
        remove = RemovalRepository(db, "a")
        with pytest.raises(ApiError):
            remove.remove("bad", [{"id": a["id"], "revision": 0}, {"id": "foreign", "revision": 0}])
        db.rollback()
        assert repo.meta(a["id"])
        db.execute(update(entries).where(entries.c.user_id == "a", entries.c.branch_id == a["id"])
                   .values(data=dump({"text": "x" * (8 * 1024 * 1024 + 1)})))
        db.commit()
        with pytest.raises(ApiError) as oversized:
            remove.remove("oversize", [{"id": a["id"], "revision": repo.meta(a["id"])["revision"]}])
        assert oversized.value.status == 413
        db.rollback()
        assert repo.meta(a["id"])
        assert remove.recent()["count"] == 0


def test_restore_after_new_topic_does_not_duplicate_pagination_slot(storage):
    with Session(storage) as db:
        repo, (_, tail) = setup(db)
        removal = RemovalRepository(db, "a")
        result = removal.remove("tail", [{"id": tail["id"], "revision": repo.meta(tail["id"])["revision"]}])
        created = repo.action({"type": "create", "title": "same cursor tail", "revision": result["revision"]})
        removal.restore("tail")
        rows = db.execute(select(branches.c.id, branches.c.position).where(branches.c.user_id == "a")).all()
        assert len({r.position for r in rows}) == 3
        assert repo.meta(created["active"])["title"] == "same cursor tail"


def test_10000_nodes_bounded_sql_projection_and_cursor(storage, monkeypatch):
    with Session(storage) as db:
        seed_large_graph(db)
        graph = GraphRepository(db, "a")
        monkeypatch.setattr(graph, "snapshot", lambda *a: pytest.fail("graph must not snapshot"))
        start = time.perf_counter()
        result = graph.query([-1e6, -1e6, 1e6, 1e6], "deep-9999")
        elapsed = (time.perf_counter() - start) * 1000
        size = len(dump(result).encode())
        assert size <= 256 * 1024 and len(result["nodes"]) <= 200
        assert result["total"] == 10003 and result["nodes"][0]["id"] == "deep-9999"
        second = graph.query([-1e6, -1e6, 1e6, 1e6], cursor=result["nextCursor"])
        assert second["nodes"][0]["id"] == "deep-198"
        print(f"\nGRAPH 10000 nodes cold_query_ms={elapsed:.2f} bytes={size} mounted_projection={len(result['nodes'])}")


def test_forest_deep_path_fanout_stability_and_local_pages(storage):
    with Session(storage) as db:
        repo, (a, b) = setup(db)
        values = []
        for i in range(10000):
            parent = a["id"] if i < 300 else (f"tree-{i-1}" if i < 500 else b["id"])
            values.append({"user_id": "a", "id": f"tree-{i}", "position": i + 2,
                "revision": 0, "data": dump({"id": f"tree-{i}", "sessionId": a["sessionId"],
                "title": "同名数学讨论", "parent": {"branchId": parent}, "draft": "", "tags": [], "kept": False})})
        db.execute(insert(branches), values)
        db.commit()
        graph = GraphRepository(db, "a")
        deep = graph.query([-1e6, -1e6, 1e6, 1e6], "tree-499")
        plan = db.execute(text("EXPLAIN QUERY PLAN SELECT id FROM history_branches WHERE user_id=:uid AND json_extract(data,'$.parent.branchId')=:parent ORDER BY position LIMIT 41"), {"uid": "a", "parent": a["id"]}).all()
        assert any("ix_graph_parent_position" in row[3] for row in plan)
        assert len(deep["path"]) == 40 and deep["pathContinuation"] == "tree-459"
        assert deep["nodes"][0]["kind"] == "branch"
        assert all(n["parent"] is not None for n in deep["nodes"][:40])
        assert len(deep["nodes"]) <= 199 and len(deep["edges"]) <= 400
        assert graph.root("tree-499")["continuationId"] == "tree-371"
        page = graph.query([-1, -1, 1, 1], a["id"], expand=a["id"])
        assert page["nodes"][0]["childrenCount"] == 300
        assert page["childNextCursor"] is not None
        second = graph.query([-1, -1, 1, 1], a["id"], expand=a["id"], child_cursor=page["childNextCursor"])
        assert second["nodes"][1]["id"] == "tree-40"
        original = next(n for n in page["nodes"] if n["id"] == "tree-0")
        graph.position("tree-0", 321, 654, original["layoutVersion"])
        repo.action({"type": "metadata", "branchId": "tree-1", "title": "更名", "tags": [], "revision": repo.view()["revision"]})
        updated = graph.query([-1e6, -1e6, 1e6, 1e6], "tree-0")
        assert (updated["nodes"][0]["x"], updated["nodes"][0]["y"]) == (321, 654)
        graph.contact(a["id"], ["tree-0"])
        graph.contact("tree-0", ["tree-1"])
        graph.contact("tree-1", [a["id"]])
        assert len(dump(graph.query([-1e6, -1e6, 1e6, 1e6], a["id"])).encode()) <= 256 * 1024
