"""Shared bounded graph fixture used by graph API tests."""
from app.repository import branches, dump, sessions


def seed_large_graph(db, user_id="a", count=10000):
    db.execute(sessions.insert().values(
        user_id=user_id, id="fixture-session", position=0,
        data=dump({"id": "fixture-session", "title": "graph fixture"})))
    rows = []
    for i in range(count):
        if i < 300:
            parent = "root-a"
        elif i < 500:
            parent = f"deep-{i - 1}"
        elif i < 9000:
            parent = "root-b"
        else:
            parent = None
        rows.append({"user_id": user_id, "id": f"deep-{i}", "position": i,
                     "revision": 0, "data": dump({"id": f"deep-{i}",
                     "sessionId": "fixture-session", "title": f"Fixture {i}",
                     "parent": {"branchId": parent} if parent else None,
                     "draft": "", "tags": [], "kept": False})})
    rows.extend([
        {"user_id": user_id, "id": "root-a", "position": count + 1, "revision": 0,
         "data": dump({"id": "root-a", "sessionId": "fixture-session", "title": "Root A", "parent": None, "draft": "", "tags": [], "kept": False})},
        {"user_id": user_id, "id": "root-b", "position": count + 2, "revision": 0,
         "data": dump({"id": "root-b", "sessionId": "fixture-session", "title": "Root B", "parent": None, "draft": "", "tags": [], "kept": False})},
        {"user_id": user_id, "id": "isolated", "position": count + 3, "revision": 0,
         "data": dump({"id": "isolated", "sessionId": "fixture-session", "title": "Isolated", "parent": None, "draft": "", "tags": [], "kept": False})},
    ])
    db.execute(branches.insert(), rows)
    db.commit()
    return "root-a", "root-b", "isolated"
