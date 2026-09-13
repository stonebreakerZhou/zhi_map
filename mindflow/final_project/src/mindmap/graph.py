"""思维导图图结构（内存中操作）。

提供：
- 节点增删改
- DFS / BFS 遍历（用于复习模式）
- 子树操作

P3 负责维护。
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from src.mindmap.node import NodeData


@dataclass
class EdgeData:
    """⭐ 内存中的边（与 NodeData 对应，承载任意两节点关系）。"""

    id: int
    source_id: str
    target_id: str


class MindMapGraph:
    """内存中的思维导图图结构。

    用法：
        graph = MindMapGraph()
        graph.add_node(NodeData(text="根节点"))
        graph.add_node(NodeData(text="子节点"), parent_id=graph.root_id)
        for node in graph.dfs():
            print(node.text)
    """

    def __init__(self) -> None:
        self._nodes: dict[str, NodeData] = {}
        self._children: dict[str | None, list[str]] = {}
        self._root_id: str | None = None
        # ⭐ 附加边（任意两节点关系，独立于父子树骨架）
        self._edges: dict[int, EdgeData] = {}
        self._next_edge_id: int = 1

    # ==================== 属性 ====================

    @property
    def root_id(self) -> str | None:
        return self._root_id

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def __len__(self) -> int:
        return self.node_count

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes

    def __iter__(self) -> Iterator[NodeData]:
        return iter(self._nodes.values())

    # ==================== 节点操作 ====================

    def add_node(self, node: NodeData, parent_id: str | None = None) -> None:
        """添加节点。

        Args:
            node: 节点数据
            parent_id: 父节点 ID（None 表示根节点）
        """
        self._nodes[node.id] = node
        node.parent_id = parent_id

        if parent_id not in self._children:
            self._children[parent_id] = []
        if node.id not in self._children[parent_id]:
            self._children[parent_id].append(node.id)

        # 如果是第一个节点，自动设为根
        if self._root_id is None and parent_id is None:
            self._root_id = node.id

    def remove_node(self, node_id: str) -> None:
        """删除节点及其所有后代。"""
        if node_id not in self._nodes:
            return

        # 递归删除后代
        descendants = list(self._children.get(node_id, []))
        for child_id in descendants:
            self.remove_node(child_id)

        # 从父节点的 children 中移除
        parent_id = self._nodes[node_id].parent_id
        if parent_id in self._children:
            self._children[parent_id] = [
                cid for cid in self._children[parent_id] if cid != node_id
            ]

        # ⭐ 清理涉及该节点的附加边（任意两节点关系）
        self._purge_edges_for_node(node_id)

        # 清理
        self._children.pop(node_id, None)
        del self._nodes[node_id]

        # 如果删的是根，重置 root_id
        if self._root_id == node_id:
            self._root_id = next(iter(self._nodes), None)

    def detach_node(self, node_id: str) -> None:
        """⭐ 仅删除节点本身，后代（直接子）重新挂为根。

        划线切割语义：
        - 节点本身从父链移除并删除
        - 所有直接子节点的 parent_id 置 None（成为新根）
        - 间接后代的内部结构不变（仍挂在直接子下）
        - 涉及该节点的附加边全部清除
        """
        if node_id not in self._nodes:
            return

        # 1) 记录所有后代（仅用于 root_id 重置时排除它们）
        descendant_ids = {n.id for n in self.get_descendants(node_id)}

        # 2) 把直接子挂到 _children[None]（成为新根）
        direct_children = list(self._children.get(node_id, []))
        self._children.setdefault(None, [])
        for cid in direct_children:
            child = self._nodes.get(cid)
            if child is None:
                continue
            child.parent_id = None
            if cid not in self._children[None]:
                self._children[None].append(cid)

        # 3) 从父节点 children 中移除自己
        parent_id = self._nodes[node_id].parent_id
        if parent_id in self._children:
            self._children[parent_id] = [
                cid for cid in self._children[parent_id] if cid != node_id
            ]

        # 4) 清理自身
        self._children.pop(node_id, None)
        del self._nodes[node_id]

        # 5) 如果删的是根，重置 root_id（找一个非后代的幸存节点）
        if self._root_id == node_id:
            self._root_id = next(
                (nid for nid in self._nodes if nid not in descendant_ids),
                next(iter(self._nodes), None),
            )

        # 6) ⭐ 清理涉及该节点的附加边
        self._purge_edges_for_node(node_id)

    def get_node(self, node_id: str) -> NodeData | None:
        return self._nodes.get(node_id)

    def detach_parent_link(self, parent_id: str, child_id: str) -> None:
        """⭐ 仅断开 parent-child 链接（不删节点、不动附加边、不动 child 子树）。

        划线切到树形边时调用：child 脱离 parent，自身成为新根。

        Args:
            parent_id: 父节点 ID
            child_id: 子节点 ID（必须真的是这个 parent 的 child，否则 no-op）
        """
        child = self._nodes.get(child_id)
        if child is None or child.parent_id != parent_id:
            return  # 节点不存在 / 不是这个 parent 的 child → 拒操作
        # 从 parent 的 children 移除
        if parent_id in self._children:
            self._children[parent_id] = [
                cid for cid in self._children[parent_id] if cid != child_id
            ]
        # child 进入根列表
        roots = self._children.setdefault(None, [])
        if child_id not in roots:
            roots.append(child_id)
        child.parent_id = None

    def get_children(self, node_id: str | None) -> list[NodeData]:
        """获取某节点的所有直接子节点。"""
        return [
            self._nodes[cid]
            for cid in self._children.get(node_id, [])
            if cid in self._nodes
        ]

    def get_descendants(self, node_id: str) -> list[NodeData]:
        """获取某节点的所有后代（含间接子节点）。"""
        result: list[NodeData] = []
        stack = [node_id]
        while stack:
            nid = stack.pop()
            for cid in self._children.get(nid, []):
                if cid in self._nodes:
                    result.append(self._nodes[cid])
                    stack.append(cid)
        return result

    # ==================== ⭐ 附加边（任意两节点关系） ====================

    def add_edge(self, source_id: str, target_id: str) -> int | None:
        """⭐ 添加附加边。返回新边 id；自环/重复/节点不存在返回 None。"""
        if source_id == target_id:
            return None  # 自环
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        if self.has_edge(source_id, target_id):
            return None  # 重复边
        eid = self._next_edge_id
        self._next_edge_id += 1
        self._edges[eid] = EdgeData(id=eid, source_id=source_id, target_id=target_id)
        return eid

    def remove_edge(self, edge_id: int) -> None:
        """⭐ 按主键 id 删边。"""
        self._edges.pop(edge_id, None)

    def get_edges(self) -> list[EdgeData]:
        """⭐ 获取所有附加边。"""
        return list(self._edges.values())

    def has_edge(self, source_id: str, target_id: str) -> bool:
        """⭐ 检查两节点间是否已存在边（不论方向 A→B / B→A 都算）。"""
        for e in self._edges.values():
            if (e.source_id == source_id and e.target_id == target_id) or (
                e.source_id == target_id and e.target_id == source_id
            ):
                return True
        return False

    def _purge_edges_for_node(self, node_id: str) -> None:
        """⭐ 清理涉及某节点的所有附加边（删节点时调用）。"""
        to_remove = [
            eid
            for eid, e in self._edges.items()
            if e.source_id == node_id or e.target_id == node_id
        ]
        for eid in to_remove:
            self._edges.pop(eid, None)

    # ==================== 遍历 ====================

    def dfs(self, start_id: str | None = None) -> list[NodeData]:
        """深度优先遍历（复习模式用）。"""
        if start_id is None:
            start_id = self._root_id
        if start_id is None or start_id not in self._nodes:
            return []

        result: list[NodeData] = []
        stack = [start_id]
        visited = set()

        while stack:
            nid = stack.pop()
            if nid in visited or nid not in self._nodes:
                continue
            visited.add(nid)
            result.append(self._nodes[nid])

            # 反向 push 让从左到右遍历
            for cid in reversed(self._children.get(nid, [])):
                if cid not in visited:
                    stack.append(cid)

        return result

    def bfs(self, start_id: str | None = None) -> list[NodeData]:
        """广度优先遍历。"""
        if start_id is None:
            start_id = self._root_id
        if start_id is None or start_id not in self._nodes:
            return []

        result: list[NodeData] = []
        queue = deque([start_id])
        visited = {start_id}

        while queue:
            nid = queue.popleft()
            if nid not in self._nodes:
                continue
            result.append(self._nodes[nid])

            for cid in self._children.get(nid, []):
                if cid not in visited and cid in self._nodes:
                    visited.add(cid)
                    queue.append(cid)

        return result

    # ==================== 工具 ====================

    def all_nodes(self) -> list[NodeData]:
        return list(self._nodes.values())

    # ==================== ⭐ 子树快照（undo 用）====================

    def snapshot_subtree(self, node_id: str) -> tuple[list[NodeData], list[EdgeData]]:
        """⭐ 递归收集 ``node_id`` 整棵子树（含自身 + 全部后代）+ 涉及的附加边。

        调用方在 delete 之前 snapshot，用于 undo 时把整棵子树回写。
        返回：``(nodes, edges)`` —— nodes 按 DFS 顺序（父在前），edges 是端点任意一端在本子树的附加边。

        ⭐ 关键：必须 deep copy，否则后续 ``detach_node`` 等操作会改 ``child.parent_id``，
            同时把 snapshot 里的对应 NodeData 也污染掉，导致 undo 还原时父子关系全错。
        """
        nodes: list[NodeData] = []
        ids: set[str] = set()
        stack = [node_id]
        while stack:
            cur = stack.pop()
            if cur in ids:
                continue
            n = self._nodes.get(cur)
            if n is None:
                continue
            nodes.append(copy.deepcopy(n))
            ids.add(cur)
            # reversed 让子节点按原顺序输出（栈 LIFO）
            for cid in reversed(self._children.get(cur, [])):
                if cid not in ids:
                    stack.append(cid)

        edges = [
            copy.deepcopy(e)
            for e in self._edges.values()
            if e.source_id in ids or e.target_id in ids
        ]
        return nodes, edges

    def restore_subtree(self, nodes: list[NodeData], edges: list[EdgeData]) -> None:
        """⭐ 把 snapshot 写回图。

        设计原则：
        - **只**覆盖/新增 snapshot 涉及的 id，不动其它节点。
        - ``_children`` 重新建立 snapshot 内的父子关系（parent → child）。
        - 附加边写回 ``_edges``。
        - 如果图当前 ``_root_id`` 为空（极端情况），把 snapshot 里第一个 ``parent_id=None`` 的设为根。

        调用约定：snapshot 之前 delete 操作已经把 nodes/edges 都移除了，所以这里可以放心覆盖。
        """
        for n in nodes:
            self._nodes[n.id] = n

        # 在 _children 里登记 snapshot 内所有父子关系（不重置整个 _children）
        for n in nodes:
            bucket = self._children.setdefault(n.parent_id, [])
            if n.id not in bucket:
                bucket.append(n.id)
            # 也要让父节点的 children 包含自己（如果父节点不在 snapshot 里）
            if n.parent_id is not None and n.parent_id in self._nodes:
                parent_bucket = self._children.setdefault(n.parent_id, [])
                if n.id not in parent_bucket:
                    parent_bucket.append(n.id)

        for e in edges:
            self._edges[e.id] = e

        # 极端：图当前没根 → 把 snapshot 里第一个无 parent 的设为根
        if self._root_id is None:
            for n in nodes:
                if n.parent_id is None:
                    self._root_id = n.id
                    break

    def clear(self) -> None:
        """清空图。"""
        self._nodes.clear()
        self._children.clear()
        self._root_id = None

    def __repr__(self) -> str:
        return f"MindMapGraph(nodes={self.node_count}, root={self._root_id[:8] if self._root_id else None})"
