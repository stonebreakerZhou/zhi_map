"""⭐ 撤销 / 重做（Undo / Redo）—— TimeEfficient 快照式历史。

设计（移植自 project-graph 的 HistoryManagerTimeEfficient）：
- 每条 history 是**整图快照**（nodes + edges + attachments + root_node_id）
- undo / redo 只移动 ``current_index`` 指针，然后 ``deserialize`` 覆盖整图
- 完全消除 closure-based 方案的脆弱性：
  - 节点 ID 复用 / 重命名 / 跨子树引用 → 全部消失
  - undo 第 2 步后第 1 步状态丢失 → 消失
  - 撤销某步后做新操作导致分支错乱 → 由 record_step 自动 truncate 修复
- 容量 100 条；超出从栈底挤掉。

调用约定：
    1. caller 做 mutation（写 DB + 同步 graph）
    2. caller 调 ``history.record_step()`` 快照当前状态
    3. UI 触发 undo → ``history.undo()`` → 内部 restore_snapshot + view reload
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from src.utils.logger import get_logger

logger = get_logger("mindflow.ui.history")


@dataclass
class HistoryEntry:
    """一条历史记录 = 整图快照 + 用户可读 label。"""

    label: str
    snapshot: dict  # mindmap_repo.take_snapshot() 的返回值


class HistoryManager(QObject):
    """⭐ TimeEfficient 快照式历史（单实例挂在 MainWindow 上）。"""

    changed = Signal()  # 栈变化（push/undo/redo/clear）时发
    undo_failed = Signal(
        str, str
    )  # (label, 错误消息) — main_window 在 restore_snapshot 抛异常时发
    redo_failed = Signal(str, str)

    MAX_SIZE = 100

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._history: list[HistoryEntry] = []
        self._current_index: int = -1  # -1 = 在 initial 状态之前
        self._current_mindmap_id: str | None = None  # 切导图时 clear 用
        self._initial_snapshot: dict | None = None  # 由 bind_mindmap 设置

    # ============================================================
    # 外部 API
    # ============================================================

    def bind_mindmap(self, mindmap_id: str, initial_snapshot: dict) -> None:
        """⭐ 打开新导图时调用：清空历史 + 把当前状态设为 initial。

        Args:
            mindmap_id: 导图 ID（之后 record_step 必须用同一个 id，否则 clear）
            initial_snapshot: ``take_snapshot(mindmap_id)`` 的返回值
        """
        self._current_mindmap_id = mindmap_id
        self._history.clear()
        # ⭐ initial 是 -1 位置（"再 undo 一次回到这里"），不进栈
        self._initial_snapshot = initial_snapshot
        self._current_index = -1
        self.changed.emit()

    def record_step(self, label: str, snapshot: dict) -> None:
        """⭐ 记录一步操作（do 完成后调用）。

        Args:
            label: 操作描述（状态栏 / tooltip 用）
            snapshot: ``take_snapshot(current_mindmap_id)`` 的返回值

        行为：
        - 如果当前不在栈尾（用户做过 undo 后又做新操作）→ 截断后续历史
        - 否则 push 到栈尾
        """
        if snapshot.get("mindmap_id") != self._current_mindmap_id:
            logger.warning(
                f"record_step 的 mindmap_id 不匹配: "
                f"{snapshot.get('mindmap_id')} vs {self._current_mindmap_id}，忽略"
            )
            return
        # 截断 current_index 之后的所有历史
        if self._current_index < len(self._history) - 1:
            self._history = self._history[: self._current_index + 1]
        self._history.append(HistoryEntry(label=label, snapshot=snapshot))
        # 容量限制
        while len(self._history) > self.MAX_SIZE:
            self._history.pop(0)
            # ⭐ 注意：挤掉一条后 current_index 不需要减 1，
            # 因为 current_index 之前（包括它在 history 里的位置）都没变。
        self._current_index = len(self._history) - 1
        self.changed.emit()
        logger.debug(
            f"record_step: {label}（index={self._current_index}, size={len(self._history)}）"
        )

    def undo(self) -> HistoryEntry | None:
        """⭐ 移动 current_index 指针到前一个，返回 entry。

        返回 None 表示已经在 initial 之前（不可 undo）。
        返回 entry 时 caller 负责 ``restore_snapshot(entry.snapshot)`` + view reload。
        """
        if self._current_index < 0:
            return None
        self._current_index -= 1
        self.changed.emit()
        if self._current_index < 0:
            # 回到 initial 状态
            return HistoryEntry(label="(初始状态)", snapshot=self._initial_snapshot)
        return self._history[self._current_index]

    def redo(self) -> HistoryEntry | None:
        """⭐ 移动 current_index 指针到后一个，返回 entry。"""
        if self._current_index >= len(self._history) - 1:
            return None
        self._current_index += 1
        self.changed.emit()
        return self._history[self._current_index]

    def peek_undo_label(self) -> str | None:
        """⭐ undo 按钮 tooltip：要撤销的那一步 label（current_index 之前那一步）。"""
        if self._current_index < 0:
            return None
        if self._current_index == 0:
            return "回到初始状态"
        return self._history[self._current_index - 1].label

    def peek_redo_label(self) -> str | None:
        """⭐ redo 按钮 tooltip：要重做的那一步 label。"""
        if self._current_index >= len(self._history) - 1:
            return None
        return self._history[self._current_index + 1].label

    def can_undo(self) -> bool:
        return self._current_index >= 0

    def can_redo(self) -> bool:
        return self._current_index < len(self._history) - 1

    def undo_count(self) -> int:
        return self._current_index + 1  # 包括 initial

    def redo_count(self) -> int:
        return len(self._history) - 1 - self._current_index

    def clear(self) -> None:
        """⭐ 清空（切导图 / 删导图时调）。"""
        if (
            not self._history
            and self._current_index == -1
            and self._current_mindmap_id is None
        ):
            return
        self._history.clear()
        self._current_index = -1
        self._current_mindmap_id = None
        self._initial_snapshot = None
        self.changed.emit()


__all__ = ["HistoryEntry", "HistoryManager"]
