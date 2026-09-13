# -*- coding: utf-8 -*-
"""⭐ 演示数据生成：清空所有旧导图 + 造一份"期末复习计划"演示数据。

跑法：
    PYTHONIOENCODING=utf-8 python tools/setup_demo_mindmap.py

不依赖 PIL —— 用 PySide6 自带的 QImage+QPainter 生成示例图片（保证 .exe 打包无额外依赖）。

结构：
    期末复习计划 (根)
    ├── Python 数据结构     → 笔记 + 1 张图
    ├── 计算机网络          → 笔记 + 1 张图
    ├── 高数（多元函数）    → 笔记 + 1 张图
    └── 英语作文           → 笔记
        └─ 模板与范文       → 1 张图

附加边：
    - Python 数据结构  --跨学科关联-->  计算机网络
    - 计算机网络       --跨学科关联-->  高数（多元函数）

操作演示覆盖：
    树形层级、Markdown 笔记、图片附件、跨节点附加边、复习模式入口素材
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Optional

# 让脚本能 import src.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 关掉 Qt 的 GUI 提示（脚本只用来调 QImage 画图，不弹窗）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QLinearGradient
from PySide6.QtWidgets import QApplication

# ⭐ 必须先实例化 QApplication（否则 offscreen 平台下 QPainter / QImage 会段错误）
_app = QApplication.instance() or QApplication(sys.argv)

from src.storage.db import init_db
from src.storage import mindmap_repo
from src.storage.attachment_manager import get_attachment_manager


# ============================================================
# 颜色调色板（节点用，统一柔和）
# ============================================================
COLORS = {
    "root": "#2C3E50",      # 深蓝灰
    "subject": "#4A90E2",  # 蓝（科目）
    "leaf": "#7ED321",     # 绿（叶子）
    "extra": "#9013FE",    # 紫（附加边的虚拟标签）
}


# ============================================================
# 用 QImage 画示例图片（每张图有文字标签，让队友一眼能识别"这是哪门课的图"）
# ============================================================

def _make_demo_image(title: str, subtitle: str, color: str, out_path: Path) -> None:
    """⭐ 画一张 480x360 的彩色示例图，写上 title + subtitle。"""
    W, H = 480, 360
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)

    # 渐变背景（让图看着像真实截图）
    p = QPainter(img)
    grad = QLinearGradient(0, 0, W, H)
    grad.setColorAt(0.0, QColor(color))
    grad.setColorAt(1.0, QColor(color).darker(140))
    p.fillRect(0, 0, W, H, grad)

    # 白色卡片
    p.setBrush(QColor(255, 255, 255, 230))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(40, 60, W - 80, H - 120, 16, 16)

    # 大标题
    p.setPen(QColor(color).darker(180))
    p.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
    p.drawText(QRect(60, 90, W - 120, 60), int(Qt.AlignVCenter | Qt.AlignLeft), title)

    # 副标题
    p.setPen(QColor("#555555"))
    p.setFont(QFont("Microsoft YaHei", 14))
    p.drawText(QRect(60, 160, W - 120, 40), int(Qt.AlignVCenter | Qt.AlignLeft), subtitle)

    # 底部装饰条
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(40, H - 60, W - 80, 30, 12, 12)
    p.setPen(QColor("white"))
    p.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
    p.drawText(QRect(60, H - 60, W - 120, 30), int(Qt.AlignCenter), "MindFlow 演示图")

    p.end()
    img.save(str(out_path), "PNG")


# ============================================================
# 笔记模板
# ============================================================

NOTES = {
    "Python 数据结构": """\
## 重点

- **链表**：增删 O(1)，查 O(n)
- **哈希表**：平均 O(1)，最坏 O(n)
- **红黑树**：自平衡 BST，插入 O(log n)

## 高频考题

1. 两数之和（哈希表）
2. 反转链表（双指针）
3. 二叉树层序遍历（队列）

## 复习策略

> 先把基础数据结构写一遍代码，
> 再刷 5 道 LeetCode 简单题巩固。
""",
    "计算机网络": """\
## 重点章节

- **OSI 七层模型** vs **TCP/IP 四层**
- **三次握手 / 四次挥手**
- **HTTP vs HTTPS**

## 公式速记

```
带宽 = 比特率 × log2(1 + SNR)
时延 = 发送时延 + 传播时延 + 处理时延 + 排队时延
```

## 复习策略

- 抓包工具（wireshark）实操一次
- 画一遍三次握手时序图
""",
    "高数（多元函数）": """\
## 核心概念

- **偏导数** → 把其它变量当常数
- **全微分** → dz = (∂z/∂x)dx + (∂z/∂y)dy
- **梯度** → 沿梯度方向函数增长最快

## 常见题型

1. 求偏导 + 全微分
2. 多元极值（无条件 / 拉格朗日乘数法）
3. 二重积分（直角坐标 / 极坐标）

> 💡 二重积分：先画积分区域 → 选坐标系 → 确定积分上下限
""",
    "英语作文": """\
## 模板框架

```
Paragraph 1: 引出话题 + 个人观点
Paragraph 2: 论点 1 + 例子
Paragraph 3: 论点 2 + 例子
Paragraph 4: 总结 + 升华
```

## 高分句型

- It is widely accepted that ...
- From my perspective, ...
- Last but not least, ...

## 字数控制

- 目标 180 词左右（上下浮动 10 词）
""",
}


# ============================================================
# 主流程
# ============================================================

def cleanup_all() -> int:
    """⭐ 清空所有旧导图，返回清理数。"""
    init_db()
    deleted = 0
    for m in mindmap_repo.list_mindmaps():
        try:
            mindmap_repo.delete_mindmap(m["id"])
            deleted += 1
        except Exception as e:
            print(f"  ! 删除 {m['title']} 失败: {e}")
    return deleted


def build_demo() -> None:
    """⭐ 造"期末复习计划"演示数据。"""
    init_db()

    mid = mindmap_repo.create_mindmap("期末复习计划", "Python + 计网 + 高数 + 英语，覆盖 4 门课的复习要点")
    print(f"  + 创建导图: 期末复习计划 ({mid})")

    # ------- 根节点 -------
    root = mindmap_repo.add_node(
        mid, "期末复习计划",
        parent_id=None, x=400, y=300, color=COLORS["root"],
    )
    mindmap_repo.update_node_text(root, "期末复习计划")
    print(f"    · 根节点: 期末复习计划")

    # ------- 4 个一级科目 -------
    py = mindmap_repo.add_node(mid, "Python 数据结构", parent_id=root, x=100, y=100, color=COLORS["subject"])
    cn = mindmap_repo.add_node(mid, "计算机网络", parent_id=root, x=350, y=100, color=COLORS["subject"])
    math = mindmap_repo.add_node(mid, "高数（多元函数）", parent_id=root, x=600, y=100, color=COLORS["subject"])
    eng = mindmap_repo.add_node(mid, "英语作文", parent_id=root, x=850, y=100, color=COLORS["subject"])

    # ------- Python 下的叶子 -------
    py_leaf = mindmap_repo.add_node(mid, "链表 / 哈希 / 红黑树", parent_id=py, x=100, y=-80, color=COLORS["leaf"])

    # ------- 计算机网络 下的叶子 -------
    cn_leaf = mindmap_repo.add_node(mid, "TCP 三次握手", parent_id=cn, x=350, y=-80, color=COLORS["leaf"])

    # ------- 高数 下的叶子 -------
    math_leaf = mindmap_repo.add_node(mid, "偏导 + 二重积分", parent_id=math, x=600, y=-80, color=COLORS["leaf"])

    # ------- 英语作文 下的 2 层叶子 -------
    eng_para = mindmap_repo.add_node(mid, "模板与范文", parent_id=eng, x=850, y=-20, color=COLORS["leaf"])
    eng_word = mindmap_repo.add_node(mid, "高频词汇", parent_id=eng, x=1050, y=-80, color=COLORS["leaf"])

    # ------- 写笔记 -------
    print(f"  + 写 Markdown 笔记 ...")
    for nid, key in [(py, "Python 数据结构"), (cn, "计算机网络"),
                     (math, "高数（多元函数）"), (eng, "英语作文")]:
        mindmap_repo.update_node_note(nid, NOTES[key])

    # ------- 图片附件 -------
    print(f"  + 生成示例图片 ...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="mindflow_demo_"))
    try:
        # Python 数据结构 → 链表可视化
        py_img = tmp_dir / "py_linked_list.png"
        _make_demo_image("Linked List", "节点 + next 指针 + 头节点", "#4A90E2", py_img)
        # 计算机网络 → TCP 握手
        cn_img = tmp_dir / "cn_tcp_handshake.png"
        _make_demo_image("TCP 3-Way", "SYN → SYN+ACK → ACK", "#50E3C2", cn_img)
        # 高数 → 二重积分区域
        math_img = tmp_dir / "math_double_integral.png"
        _make_demo_image("∬ D f(x,y) dA", "积分区域 D + 坐标系选择", "#9013FE", math_img)
        # 英语 → 作文结构图
        eng_img = tmp_dir / "eng_essay_structure.png"
        _make_demo_image("Essay Outline", "4 段式议论文结构", "#F5A623", eng_img)

        # 导入 + 关联
        am = get_attachment_manager()
        for nid, img_path, caption in [
            (py, py_img, "链表结构示意图"),
            (cn, cn_img, "TCP 三次握手时序图"),
            (math, math_img, "二重积分区域"),
            (eng_leaf_para := eng_para, eng_img, "作文 4 段式结构"),
        ]:
            rel_path = am.import_attachment(img_path)
            if rel_path:
                mindmap_repo.add_attachment(
                    nid, rel_path, file_type="image",
                    caption=caption, is_cover=True,
                )
                print(f"    · 附件: {caption} → {nid[:8]}…")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------- 跨学科附加边（演示"图"而非树） -------
    print(f"  + 附加边（跨学科关联） ...")
    eid1 = mindmap_repo.add_edge(mid, py, math)
    eid2 = mindmap_repo.add_edge(mid, cn, eng)
    print(f"    · Python 数据结构 ↔ 高数（多元函数） edge_id={eid1}")
    print(f"    · 计算机网络 ↔ 英语作文 edge_id={eid2}")

    # 总结
    total_nodes = len(mindmap_repo.get_nodes(mid))
    total_edges = len(mindmap_repo.get_edges(mid))
    print(f"\n  ✅ 完成: 1 导图 / {total_nodes} 节点 / {total_edges} 附加边")


def main():
    print("⭐ 清空所有旧导图 ...")
    n = cleanup_all()
    print(f"  - 已删除 {n} 个导图\n")

    print("⭐ 生成演示数据 ...")
    build_demo()

    print("\n⭐ 当前导图列表：")
    for m in mindmap_repo.list_mindmaps():
        n_count = len(mindmap_repo.get_nodes(m["id"]))
        print(f"  · {m['title']} ({n_count} 节点)")


if __name__ == "__main__":
    main()