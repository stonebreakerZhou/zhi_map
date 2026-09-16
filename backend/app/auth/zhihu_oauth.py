"""Zhihu OAuth 2.0 — authorization-code flow.

User clicks 「用知乎登录」→ redirected to Zhihu → user grants → Zhihu
redirects back to redirect_uri?code=XXX&state=YYY → backend swaps code
for access_token → fetches basic user info → creates or links a
zhishu account → issues a session.

We only call 「get current user info」, never pull the user's content /
follows / favorites.
"""
from __future__ import annotations
import json
import os
import secrets
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import settings


def _load_zhihu_env() -> None:
    """Load ZHIHU_* from .env into os.environ. Zero deps.

    Mirrors _load_smtp_env in email_sender.py — duplicated rather than
    refactored to keep both modules self-contained and risk-free.
    """
    for p in (Path.cwd() / ".env",
              Path(__file__).parent.parent.parent / ".env",
              Path(__file__).parent.parent.parent.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ZHIHU_") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return
_load_zhihu_env()


# ────────── constants ──────────

# Verified against Zhihu's own OAuth docs (2026-09): the paths have NO
# `/oauth` segment, the authorize param is `app_id` (not `client_id`), the
# token endpoint takes a JSON body, and its errors come back as HTTP 200
# with a `code` field in the body.
_AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
_TOKEN_URL = "https://openapi.zhihu.com/access_token"
_USERINFO_URL = "https://openapi.zhihu.com/user"
_STATE_COOKIE = "zhishu_zhihu_state"
_STATE_TTL_SECONDS = 600
_TIMEOUT = 15.0


def _config() -> tuple[str, str, str] | None:
    app_id = os.environ.get("ZHIHU_APP_ID", "").strip()
    app_key = os.environ.get("ZHIHU_APP_KEY", "").strip()
    redirect = os.environ.get("ZHIHU_REDIRECT_URI", "").strip()
    if not app_id or not app_key or not redirect:
        return None
    return app_id, app_key, redirect


def is_configured() -> bool:
    """Whether the 3 required vars are set — front-end uses this to decide
    whether to render the 「用知乎登录」 button."""
    return _config() is not None


# ────────── state (CSRF defence) ──────────

def make_state() -> str:
    return secrets.token_urlsafe(32)


def set_state_cookie(response, state: str) -> None:
    response.set_cookie(
        _STATE_COOKIE, state,
        httponly=True, samesite="lax",
        secure=settings.production(),
        max_age=_STATE_TTL_SECONDS, path="/",
    )


def verify_state(request, expected: str) -> bool:
    actual = request.cookies.get(_STATE_COOKIE, "")
    return bool(actual) and secrets.compare_digest(actual, expected)


def clear_state_cookie(response) -> None:
    response.delete_cookie(_STATE_COOKIE, path="/")


# ────────── /authorize ──────────

def build_authorize_url(state: str) -> str:
    app_id, _, redirect = _config()  # type: ignore[misc]
    qs = urllib.parse.urlencode({
        "redirect_uri": redirect,
        "app_id": app_id,
        "response_type": "code",
        "state": state,
    })
    return f"{_AUTHORIZE_URL}?{qs}"


# ────────── code → access_token ──────────

def exchange_code_for_token(code: str) -> dict[str, Any] | None:
    """Swap the authorization code for an access_token.

    Uses Zhihu's own `app_id` / `app_key` parameter names. The body must be
    form-encoded: despite the docs showing JSON, a JSON body is rejected
    with "missing parameter: grant_type". Returns None on any error —
    including the HTTP 200 + `code` responses Zhihu uses for failures.
    """
    app_id, app_key, redirect = _config()  # type: ignore[misc]
    body = urllib.parse.urlencode({
        "app_id": app_id,
        "app_key": app_key,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
        "code": code,
    }).encode("utf-8")
    req = urllib.request.Request(
        _TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    # Zhihu signals failure with an error `code` instead of a bad status.
    if "access_token" not in data:
        print(f"[ZHIHU OAUTH] token exchange failed: {data!r}", flush=True)
        return None
    return data


# ────────── access_token → user info ──────────

def get_zhihu_user_info(access_token: str) -> dict[str, Any] | None:
    """Fetch the authorising user's profile.

    Fields (per Zhihu's docs): uid / fullname / gender / headline /
    description / avatar_path / phone_no / email. Anything beyond the basic
    profile is empty unless the user granted the extra scopes.
    """
    req = urllib.request.Request(
        _USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not (data.get("uid") or data.get("id")):
        print(f"[ZHIHU OAUTH] user info failed: {data!r}", flush=True)
        return None
    return data
