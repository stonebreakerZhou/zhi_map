"""⭐ ZhishuHttpChatBackend：用 HTTP 调队友的 zhi_map FastAPI 后端。

实现路径：
- 跟 zhi_map 的 HTTP API 通信（不需要内置 zhi_map 状态机）
- 数据格式完全按 zhi_map 已有 schema（schemaVersion=2）
- 乐观锁：每次写操作带 revision，409 冲突时自动 reload
- 用 httpx + cookie 持久化（首次自动让后端发 session cookie）

API 端点对应表（来自 zhi_map backend/app/main.py）：
  GET  /api/workspace              → load_workspace
  POST /api/workspace/actions      → apply_action
  POST /api/ai/chat                → ask_question
  GET  /api/export                 → export_workspace
  POST /api/import                 → import_workspace
  GET  /api/status                 → get_status
  GET  /api/ai/config              → get_ai_config
  POST /api/ai/config              → save_ai_config
  POST /api/ai/config/clear        → clear_ai_config

P3 负责维护。
"""

from __future__ import annotations

import httpx

from src.utils.logger import get_logger

logger = get_logger("mindflow.backends.zhishu_http")


class ZhishuHttpChatBackend:
    """⭐ HTTP IChatBackend 实现：对接 zhi_map FastAPI。

    用法::

        backend = ZhishuHttpChatBackend("http://127.0.0.1:8000")
        state = backend.get_state()
        backend.send(state["active"], "你好")
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 10.0):
        # base_url 标准化（去掉末尾 /）
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # ⭐ 用 httpx.Client 维持 Cookie（zhi_map 自动发 zhishu_session）
        self._client = httpx.Client(timeout=timeout)
        logger.info(f"ZhishuHttpChatBackend 初始化：{self._base_url}")

    @property
    def base_url(self) -> str:
        return self._base_url

    # ==================== 状态查询 ====================

    def get_state(self) -> dict:
        """GET /api/workspace → {state, revision}"""
        resp = self._get("/api/workspace")
        return resp["state"]

    def get_status(self) -> dict:
        """GET /api/status → {configured, model, mode}"""
        return self._get("/api/status")

    # ==================== 会话/分支创建 ====================

    def create_session(self, title: str) -> str:
        """POST /api/workspace/actions {type:'create', title} → 新 session_id"""
        # 拿当前 revision
        current = self._get("/api/workspace")
        result = self._post(
            "/api/workspace/actions",
            {"type": "create", "title": title, "revision": current["revision"]},
        )
        return result["state"]["active"]

    def switch_branch(self, branch_id: str) -> None:
        """POST /api/workspace/actions {type:'switch', branchId}"""
        current = self._get("/api/workspace")
        self._post(
            "/api/workspace/actions",
            {"type": "switch", "branchId": branch_id, "revision": current["revision"]},
        )

    # ==================== 对话动作 ====================

    def send(self, branch_id: str, text: str) -> None:
        """POST /api/workspace/actions {type:'send', branchId, text}"""
        current = self._get("/api/workspace")
        self._post(
            "/api/workspace/actions",
            {
                "type": "send",
                "branchId": branch_id,
                "text": text,
                "revision": current["revision"],
            },
        )

    def answer(self, branch_id: str, text: str) -> None:
        """POST /api/workspace/actions {type:'answer', branchId, text}"""
        current = self._get("/api/workspace")
        self._post(
            "/api/workspace/actions",
            {
                "type": "answer",
                "branchId": branch_id,
                "text": text,
                "revision": current["revision"],
            },
        )

    def fork(self, branch_id: str, entry_id: str, title: str) -> str:
        """POST /api/workspace/actions {type:'fork'}"""
        current = self._get("/api/workspace")
        result = self._post(
            "/api/workspace/actions",
            {
                "type": "fork",
                "branchId": branch_id,
                "entryId": entry_id,
                "title": title,
                "revision": current["revision"],
            },
        )
        return result["state"]["active"]

    def expand(
        self,
        branch_id: str,
        selection: dict,
        context_ids: list[str],
        text: str,
    ) -> str:
        """POST /api/workspace/actions {type:'expand', selection, contextIds, text}"""
        current = self._get("/api/workspace")
        result = self._post(
            "/api/workspace/actions",
            {
                "type": "expand",
                "branchId": branch_id,
                "selection": selection,
                "contextIds": context_ids,
                "text": text,
                "revision": current["revision"],
            },
        )
        return result["state"]["active"]

    def keep(self, branch_id: str) -> None:
        """POST /api/workspace/actions {type:'keep', branchId}"""
        current = self._get("/api/workspace")
        self._post(
            "/api/workspace/actions",
            {"type": "keep", "branchId": branch_id, "revision": current["revision"]},
        )

    def add_tags(self, branch_id: str, tags: list[str]) -> None:
        """POST /api/workspace/actions {type:'metadata', tags}"""
        current = self._get("/api/workspace")
        # 取现有 title
        state = current["state"]
        branch = next((b for b in state["branches"] if b["id"] == branch_id), None)
        if not branch:
            raise ValueError(f"分支不存在：{branch_id}")
        existing_tags = list(branch.get("tags", []))
        merged = list(dict.fromkeys(existing_tags + tags))
        self._post(
            "/api/workspace/actions",
            {
                "type": "metadata",
                "branchId": branch_id,
                "title": branch["title"],
                "tags": merged,
                "revision": current["revision"],
            },
        )

    def delete_branch(self, branch_id: str) -> None:
        """POST /api/workspace/actions {type:'delete', kind:'branch'}"""
        current = self._get("/api/workspace")
        self._post(
            "/api/workspace/actions",
            {
                "type": "delete",
                "kind": "branch",
                "targetId": branch_id,
                "revision": current["revision"],
            },
        )

    # ==================== 导入导出 ====================

    def export_workspace(self) -> dict:
        """GET /api/export → {schemaVersion, state}"""
        return self._get("/api/export")

    def import_workspace(self, payload: dict) -> dict:
        """POST /api/import {state, revision} → {state, revision}"""
        current = self._get("/api/workspace")
        result = self._post(
            "/api/import",
            {"state": payload.get("state", payload), "revision": current["revision"]},
        )
        return result

    # ==================== AI（直接发到 zhi_map 调 AI） ====================

    def ask_question(self, branch_id: str, revision: int) -> tuple[dict, int, str]:
        """POST /api/ai/chat {branchId, revision} → {state, revision, answer}"""
        result = self._post(
            "/api/ai/chat",
            {"branchId": branch_id, "revision": revision},
        )
        return result["state"], result["revision"], result.get("answer", "")

    # ==================== 生命周期 ====================

    def reset(self) -> None:
        """清空：zhi_map 没有 reset API，最接近是导入空 state。"""
        empty = {"version": 2, "sessions": [], "branches": [], "active": None}
        try:
            self.import_workspace({"state": empty})
        except Exception as exc:
            logger.warning(f"reset 失败：{exc}")

    # ==================== AI 配置 ====================

    def get_ai_config(self) -> dict:
        """GET /api/ai/config"""
        return self._get("/api/ai/config")

    def save_ai_config(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_ms: int | None = None,
    ) -> dict:
        """POST /api/ai/config"""
        payload = {"baseUrl": base_url, "model": model, "apiKey": api_key}
        if timeout_ms is not None:
            payload["timeoutMs"] = timeout_ms
        return self._post("/api/ai/config", payload)

    def clear_ai_config(self) -> dict:
        """POST /api/ai/config/clear {confirm:true}"""
        return self._post("/api/ai/config/clear", {"confirm": True})

    # ==================== HTTP 辅助 ====================

    def _get(self, path: str) -> dict:
        """GET 请求 + JSON 返回 + 错误归一化。"""
        try:
            resp = self._client.get(f"{self._base_url}{path}")
            return self._handle(resp)
        except httpx.RequestError as exc:
            raise RuntimeError(f"HTTP 请求失败：{exc}") from exc

    def _post(self, path: str, json_body: dict) -> dict:
        """POST 请求 + JSON 返回 + 错误归一化。"""
        try:
            resp = self._client.post(f"{self._base_url}{path}", json=json_body)
            return self._handle(resp)
        except httpx.RequestError as exc:
            raise RuntimeError(f"HTTP 请求失败：{exc}") from exc

    def _handle(self, resp: httpx.Response) -> dict:
        """处理 HTTP 响应：409 友好提示，500+ 报错，2xx 返 JSON。"""
        if resp.status_code == 409:
            raise ConflictError("工作区已被其他请求更新（409），请刷新重试")
        if resp.status_code >= 400:
            try:
                err = resp.json()
                msg = err.get("error", resp.text[:200])
            except Exception:
                msg = resp.text[:200]
            raise RuntimeError(f"HTTP {resp.status_code}: {msg}")
        return resp.json()

    def close(self):
        """⭐ 关闭 client（应用退出时调用）。"""
        self._client.close()


class ConflictError(RuntimeError):
    """工作区乐观锁冲突（HTTP 409）。"""


__all__ = ["ConflictError", "ZhishuHttpChatBackend"]
