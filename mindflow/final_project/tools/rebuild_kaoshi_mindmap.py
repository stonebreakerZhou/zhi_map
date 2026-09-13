"""重建「期末复习计划」28 节点样例导图，插入到两个 DB。

不在用户的真实 DB 里反复实验，只在脚本里建一次写一次。

- Track 1: final_project/data/mindflow.db
- Track 2: final_project_integrate/data/mindflow.db

结构（28 节点）：
    期末复习计划 (root)
    ├── 高等数学 (8 子节点)
    ├── 概率统计 (8 子节点)
    └── Python   (8 子节点)

会清掉所有其他 mindmap（图测试 / diag_undo_e2e 等调试残留），最终只剩
「期末复习计划」一个，符合"队友测试时一眼看到 demo"的需求。

用法::
    PYTHONIOENCODING=utf-8 python tools/rebuild_kaoshi_mindmap.py
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATHS = [
    ROOT / "data" / "mindflow.db",
    ROOT.parent / "final_project_integrate" / "data" / "mindflow.db",
]


# ---- 28 节点结构 --------------------------------------------------------

SUBJECTS: list[tuple[str, list[str]]] = [
    (
        "高等数学",
        [
            "函数与极限",
            "极限的四则运算",
            "两个重要极限",
            "ε-δ 定义",
            "函数的连续性",
            "导数概念与几何意义",
            "微分中值定理",
            "泰勒公式",
        ],
    ),
    (
        "概率统计",
        [
            "随机事件与样本空间",
            "古典概型",
            "条件概率与独立性",
            "随机变量分布",
            "常见分布（二项/泊松/正态）",
            "大数定律与中心极限定理",
            "参数估计",
            "假设检验",
        ],
    ),
    (
        "Python",
        [
            "基础语法与控制流",
            "列表 / 字典 / 集合",
            "函数与 lambda",
            "面向对象（类 / 继承）",
            "异常处理",
            "文件 I/O 与路径",
            "常用标准库（os / json / collections）",
            "综合实战：爬虫 + 报告生成",
        ],
    ),
]


# 颜色 token（与 project-graph 调色板对齐；cyan 主调 + 三科副色）
COLOR_ROOT = "#22d3ee"
COLOR_MATH = "#f59e0b"  # 高数 = 琥珀
COLOR_STAT = "#a78bfa"  # 概统 = 紫
COLOR_PY = "#10b981"  # Python = 翠绿
COLOR_LEAF_BY_SUBJECT = {
    "高等数学": "#fbbf24",
    "概率统计": "#c4b5fd",
    "Python": "#34d399",
}


def _make_node(
    *,
    mindmap_id: str,
    parent_id: str | None,
    text: str,
    color: str,
    note: str,
    pos_x: float,
    pos_y: float,
) -> tuple[str, str, str | None, str, str, str, float, float, int, str, str, str]:
    """返回 (id, mindmap_id, parent_id, text, note, color, pos_x, pos_y, is_expanded, search_source, image_path, image_caption)。"""
    return (
        str(uuid.uuid4()),
        mindmap_id,
        parent_id,
        text,
        note,
        color,
        pos_x,
        pos_y,
        1,  # is_expanded
        None,  # search_source
        None,  # image_path
        None,  # image_caption
    )


def build_nodes() -> tuple[str, list[tuple]]:
    """生成 (mindmap_id, [(row, ...), ...])。"""

    mindmap_id = str(uuid.uuid4())
    rows: list[tuple] = []
    now = datetime.utcnow().isoformat(sep=" ")

    # ---- Root ----
    rows.append(
        (
            str(uuid.uuid4()),  # node id
            mindmap_id,
            None,
            "期末复习计划",
            "考前 7 天冲刺路线图\n三科并进：理论 → 习题 → 真题",
            COLOR_ROOT,
            0.0,
            0.0,
            1,
            None,
            None,
            None,
        )
    )
    root_id = rows[0][0]

    # ---- 三大科 + 各科 8 个子节点 ----
    # 布局：三大科水平方向拉开，每科 8 子节点紧凑在一段，避免不同科叶子重叠
    branch_x = {"高等数学": -1000.0, "概率统计": 0.0, "Python": 1000.0}
    branch_y = -260.0
    leaf_y = -560.0
    leaf_step = 130.0  # 同科 8 个子节点横向间距

    for subj_idx, (subj, leaves) in enumerate(SUBJECTS):
        # 父节点（学科）
        branch_id = str(uuid.uuid4())
        rows.append(
            (
                branch_id,
                mindmap_id,
                root_id,
                subj,
                f"📚 学科 {subj_idx + 1}/3\n共 {len(leaves)} 个复习模块",
                COLOR_MATH if subj == "高等数学"
                else COLOR_STAT if subj == "概率统计" else COLOR_PY,
                branch_x[subj],
                branch_y,
                1,
                None,
                None,
                None,
            )
        )

        # 8 个子节点（按当前学科居中）
        leaf_color = COLOR_LEAF_BY_SUBJECT[subj]
        # 居中：让 8 个叶子以 branch_x 为中心
        total_width = (len(leaves) - 1) * leaf_step
        start_x = branch_x[subj] - total_width / 2
        for i, leaf_text in enumerate(leaves):
            rows.append(
                (
                    str(uuid.uuid4()),
                    mindmap_id,
                    branch_id,
                    leaf_text,
                    f"{subj} · 模块 {i + 1}\n目标：理解定义 → 推导 → 做 5 道题",
                    leaf_color,
                    start_x + i * leaf_step,
                    leaf_y,
                    1,
                    None,
                    None,
                    None,
                )
            )

    return mindmap_id, rows


def write_to(db_path: Path, mindmap_id: str, rows: list[tuple]) -> None:
    """幂等写入：先删所有旧 mindmap（只留 期末复习计划），再插新的。"""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        # 1. 删所有旧 mindmap（cascade 会带走 nodes / attachments / edges）
        cur.execute("SELECT id, title FROM mindmaps")
        all_old = cur.fetchall()
        kept = [r for r in all_old if r[1] == "期末复习计划"]
        to_delete = [r for r in all_old if r[1] != "期末复习计划"]
        if to_delete:
            ids = [r[0] for r in to_delete]
            placeholders = ",".join("?" * len(ids))
            cur.execute(
                f"DELETE FROM mindmaps WHERE id IN ({placeholders})",
                ids,
            )
            print(
                f"  [{db_path.name}] 删除旧 mindmap（cascade）："
                f"{[r[1] for r in to_delete]}"
            )
        if kept:
            kept_ids = [r[0] for r in kept]
            placeholders = ",".join("?" * len(kept_ids))
            cur.execute(
                f"DELETE FROM mindmaps WHERE id IN ({placeholders})",
                kept_ids,
            )
            print(f"  [{db_path.name}] 删除旧 期末复习计划（重写）：{len(kept_ids)} 个")

        # 2. 插入 mindmap 行
        now = datetime.utcnow().isoformat(sep=" ")
        cur.execute(
            """
            INSERT INTO mindmaps (id, title, description, root_node_id,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mindmap_id,
                "期末复习计划",
                "期末考前复习路线图：高等数学 / 概率统计 / Python 三科并进",
                rows[0][0],  # root node id
                now,
                now,
            ),
        )

        # 3. 插入 nodes（批量）
        cur.executemany(
            """
            INSERT INTO nodes (id, mindmap_id, parent_id, text, note, color,
                               pos_x, pos_y, is_expanded, search_source,
                               image_path, image_caption,
                               created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [r + (now, now) for r in rows],
        )

        conn.commit()
        print(f"  [{db_path.name}] 写入 1 个 mindmap + {len(rows)} 个 node")
    finally:
        conn.close()


def verify(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, root_node_id FROM mindmaps WHERE title = ?",
            ("期末复习计划",),
        )
        rows = cur.fetchall()
        print(f"  [{db_path.name}] 期末复习计划 mindmap 数：{len(rows)}")
        for mindmap_id, root_id in rows:
            cur.execute(
                "SELECT COUNT(*) FROM nodes WHERE mindmap_id = ?",
                (mindmap_id,),
            )
            (n,) = cur.fetchone()
            print(f"    - {mindmap_id[:8]} 节点数：{n}  root={root_id[:8] if root_id else None}")
    finally:
        conn.close()


def main() -> None:
    print("=== 重建「期末复习计划」28 节点样例导图 ===\n")
    mindmap_id, rows = build_nodes()
    print(f"生成了 1 个 mindmap + {len(rows)} 个 node（应为 28）\n")

    for db_path in DB_PATHS:
        if not db_path.exists():
            print(f"[!] 跳过（不存在）：{db_path}")
            continue
        print(f"写入 {db_path}")
        write_to(db_path, mindmap_id, rows)

    print("\n=== 验证 ===\n")
    for db_path in DB_PATHS:
        if db_path.exists():
            verify(db_path)


if __name__ == "__main__":
    main()