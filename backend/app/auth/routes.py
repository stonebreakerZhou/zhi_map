"""/api/auth/* routes — email registration, login, logout, status.

Independent of the main app's anonymous-session `user()` dependency.
Anonymous data is migrated to the registered user_id at register/login
time so no content is lost.

Tables touched (read/write):
    auth_email_credentials, auth_email_verifications, users,
    auth_sessions (issued for the registered user),
    workspaces, user_ai_configs,
    history_heads, history_sessions, history_branches, history_entries,
    history_tombstones,
    graph_positions, graph_contacts, graph_removals.

No pre-existing route, schema, or column is altered.
"""
from __future__ import annotations
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.orm import Session

from ..db import AuthSession, User, UserAiConfig, Workspace, engine, token_hash
from ..config import settings
from .email_sender import get_sender
from .models import EmailCredential, EmailVerification
from .passwords import hash_password, verify_password


router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DEV_CODE_HEADER = "X-Dev-Auth-Code"
_MAX_VERIFY_ATTEMPTS = 5
_VERIFY_TTL_MINUTES = 10
_SESSION_TTL_DAYS = 30


# ───────── helpers ─────────

def _db():
    with Session(engine) as s:
        yield s


def _now():
    return datetime.now(timezone.utc)


def _now_naive():
    """SQLite stores datetimes as naive UTC; comparisons need naive."""
    return datetime.utcnow()


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "zhishu_session",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.production(),
        max_age=_SESSION_TTL_DAYS * 86400,
        path="/",
    )


def _current_uid(db: Session, request: Request) -> str | None:
    """Resolve the cookie's user_id, if any session is valid."""
    cookie = request.cookies.get("zhishu_session")
    if not cookie:
        return None
    row = db.execute(
        select(AuthSession.user_id).where(
            AuthSession.token_hash == token_hash(cookie),
            AuthSession.expires_at > _now(),
        )
    ).first()
    return row[0] if row else None


# ───────── migration ─────────

# Tables that hold per-user data, in INSERT OR IGNORE + DELETE order.
# Composite-PK tables whose leading column is user_id work cleanly with
# UPDATE … WHERE user_id = src, but using INSERT … SELECT is safer when
# dst may already contain rows (login path).
_USER_DATA_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (table_name, non-user_id column list to copy verbatim)
    ("workspaces", ("state", "version", "updated_at")),
    ("user_ai_configs", (
        "version", "base_url", "model", "timeout_ms",
        "encrypted_key", "nonce", "auth_tag", "updated_at",
        "provider", "max_tokens", "temperature",
    )),
    ("history_heads", ("active",)),
    ("history_sessions", ("id", "position", "data")),
    ("history_branches", ("id", "position", "revision", "data")),
    ("history_entries", ("branch_id", "position", "id", "data")),
    ("history_tombstones", ("token", "expires", "data")),
    ("graph_positions", ("branch_id", "x", "y", "version")),
    ("graph_contacts", ("source", "target")),
    ("graph_removals", ("id", "committed", "expires", "status", "targets", "data")),
)


def _migrate_anonymous_data(db: Session, src: str, dst: str) -> None:
    """Move every row under user_id=src into user_id=dst.

    Strategy:
        For each user-scoped table, INSERT OR IGNORE INTO dst SELECT … FROM src
        then DELETE FROM src. Conflicts (rows that already exist under dst)
        are kept on the dst side; src duplicates are dropped.

    auth_sessions is intentionally NOT migrated: the old anon session
    cookie becomes useless once user_id changes, so its rows are simply
    dropped. Their absence is what also lets the old anon user record
    be deleted (FK on users.id).
    """
    for table, cols in _USER_DATA_TABLES:
        col_list = ", ".join(cols)
        # Insert dst side first; dst-wins on conflict.
        db.execute(text(
            f"INSERT OR IGNORE INTO {table} (user_id, {col_list}) "
            f"SELECT :dst, {col_list} FROM {table} WHERE user_id = :src"
        ), {"dst": dst, "src": src})
        db.execute(text(
            f"DELETE FROM {table} WHERE user_id = :src"
        ), {"src": src})
    # Drop the old anon user's session rows (FK target on users.id).
    db.execute(delete(AuthSession).where(AuthSession.user_id == src))
    # Drop the old anon user record.
    db.execute(delete(User).where(User.id == src))


# ───────── request bodies ─────────

class EmailStartBody(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]


class EmailVerifyBody(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    code: Annotated[str, Field(pattern=r"^\d{6}$")]
    password: Annotated[str, Field(min_length=8, max_length=128)]


class EmailLoginBody(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


class PasswordChangeBody(BaseModel):
    oldPassword: Annotated[str, Field(min_length=8, max_length=128)]
    newPassword: Annotated[str, Field(min_length=8, max_length=128)]


class PasswordResetBody(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    code: Annotated[str, Field(pattern=r"^\d{6}$")]
    newPassword: Annotated[str, Field(min_length=8, max_length=128)]


# ───────── endpoints ─────────

@router.post("/email/start")
def email_start(
    body: EmailStartBody,
    request: Request,
    response: Response,
    db: Session = Depends(_db),
):
    """Send a 6-digit verification code to the given email."""
    email = _norm_email(body.email)
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确。")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = _now() + timedelta(minutes=_VERIFY_TTL_MINUTES)

    # Replace any prior pending code for this email.
    db.execute(delete(EmailVerification).where(EmailVerification.email == email))
    db.execute(insert(EmailVerification).values(
        id=secrets.token_urlsafe(16),
        email=email,
        code_hash=_hash_code(code),
        expires_at=expires,
        attempts=0,
        created_at=_now(),
    ))
    db.commit()

    get_sender().send(
        email,
        "【知树】邮箱验证码",
        f"您的验证码是 {code}，{_VERIFY_TTL_MINUTES} 分钟内有效。\n"
        f"如果不是你本人操作，请忽略本邮件。",
    )

    # Dev-mode hint: write code to a response header so the local UI can
    # auto-fill it. Only honoured in dev and only for localhost callers.
    if (not settings.production()
            and request.client
            and request.client.host in ("127.0.0.1", "::1")):
        response.headers[_DEV_CODE_HEADER] = code

    return {"ok": True}


@router.post("/email/register")
def email_register(
    body: EmailVerifyBody,
    request: Request,
    response: Response,
    db: Session = Depends(_db),
):
    """Verify code + password → create user → migrate anon data → issue session."""
    email = _norm_email(body.email)
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确。")

    row = db.execute(
        select(EmailVerification.__table__).where(EmailVerification.email == email)
    ).mappings().first()
    if not row or row["expires_at"] < _now_naive():
        raise HTTPException(400, "验证码不存在或已过期，请重新获取。")
    if row["attempts"] >= _MAX_VERIFY_ATTEMPTS:
        raise HTTPException(429, "尝试次数过多，请稍后再试。")
    if not _hash_code(body.code) == row["code_hash"]:
        db.execute(
            update(EmailVerification.__table__)
            .where(EmailVerification.id == row["id"])
            .values(attempts=row["attempts"] + 1)
        )
        db.commit()
        raise HTTPException(400, "验证码不正确。")

    if db.execute(
        select(EmailCredential.__table__).where(EmailCredential.email == email)
    ).first():
        raise HTTPException(409, "该邮箱已注册，请直接登录。")

    new_uid = secrets.token_urlsafe(24)
    now = _now()
    db.execute(insert(User).values(id=new_uid, created_at=now))
    db.execute(insert(EmailCredential).values(
        user_id=new_uid,
        email=email,
        password_hash=hash_password(body.password),
        created_at=now,
        updated_at=now,
    ))

    anon_uid = _current_uid(db, request)
    if anon_uid and anon_uid != new_uid:
        _migrate_anonymous_data(db, anon_uid, new_uid)

    token = secrets.token_urlsafe(48)
    db.execute(insert(AuthSession).values(
        id=secrets.token_urlsafe(24),
        user_id=new_uid,
        token_hash=token_hash(token),
        created_at=now,
        expires_at=now + timedelta(days=_SESSION_TTL_DAYS),
    ))
    db.execute(delete(EmailVerification).where(EmailVerification.id == row["id"]))
    db.commit()

    _set_session_cookie(response, token)
    return {"ok": True, "userId": new_uid}


@router.post("/email/login")
def email_login(
    body: EmailLoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(_db),
):
    """Log in by email + password; merge any anonymous data into the user."""
    email = _norm_email(body.email)
    cred = db.execute(
        select(EmailCredential.__table__).where(EmailCredential.email == email)
    ).mappings().first()
    if not cred or not verify_password(body.password, cred["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确。")

    user_id = cred["user_id"]
    anon_uid = _current_uid(db, request)
    if anon_uid and anon_uid != user_id:
        _migrate_anonymous_data(db, anon_uid, user_id)

    now = _now()
    token = secrets.token_urlsafe(48)
    db.execute(insert(AuthSession).values(
        id=secrets.token_urlsafe(24),
        user_id=user_id,
        token_hash=token_hash(token),
        created_at=now,
        expires_at=now + timedelta(days=_SESSION_TTL_DAYS),
    ))
    db.commit()

    _set_session_cookie(response, token)
    return {"ok": True, "userId": user_id}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(_db)):
    cookie = request.cookies.get("zhishu_session")
    if cookie:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(cookie)))
        db.commit()
    response.delete_cookie("zhishu_session", path="/")
    return {"ok": True}


@router.post("/password/change")
def password_change(
    body: PasswordChangeBody,
    request: Request,
    db: Session = Depends(_db),
):
    """Change the password for the currently-logged-in user.

    Requires a valid session cookie. Verifies the old password before
    committing the new one; revokes every session for the user on success
    so all devices must re-authenticate.
    """
    user_id = _current_uid(db, request)
    if not user_id:
        raise HTTPException(401, "请先登录。")
    cred = db.execute(
        select(EmailCredential.__table__).where(EmailCredential.user_id == user_id)
    ).mappings().first()
    if not cred or not verify_password(body.oldPassword, cred["password_hash"]):
        raise HTTPException(400, "当前密码不正确。")
    if body.newPassword == body.oldPassword:
        raise HTTPException(400, "新密码不能与当前密码相同。")
    db.execute(
        update(EmailCredential.__table__)
        .where(EmailCredential.user_id == user_id)
        .values(password_hash=hash_password(body.newPassword), updated_at=_now())
    )
    # Revoke all sessions so the change takes effect everywhere immediately.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.commit()
    return {"ok": True}


@router.post("/password/reset")
def password_reset(
    body: PasswordResetBody,
    request: Request,
    response: Response,
    db: Session = Depends(_db),
):
    """Forgot-password flow: verify code sent to email, then set new password.

    No session required. Re-uses the existing EmailVerification table that
    /api/auth/email/start populates. On success, all of the user's existing
    sessions are revoked so any current device must re-authenticate.
    """
    from ..config import settings
    email = _norm_email(body.email)
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确。")
    row = db.execute(
        select(EmailVerification.__table__).where(EmailVerification.email == email)
    ).mappings().first()
    if not row or row["expires_at"] < _now_naive():
        raise HTTPException(400, "验证码不存在或已过期，请重新获取。")
    if row["attempts"] >= _MAX_VERIFY_ATTEMPTS:
        raise HTTPException(429, "尝试次数过多，请稍后再试。")
    if not _hash_code(body.code) == row["code_hash"]:
        db.execute(
            update(EmailVerification.__table__)
            .where(EmailVerification.id == row["id"])
            .values(attempts=row["attempts"] + 1)
        )
        db.commit()
        raise HTTPException(400, "验证码不正确。")

    cred = db.execute(
        select(EmailCredential.__table__).where(EmailCredential.email == email)
    ).mappings().first()
    if not cred:
        # Don't leak whether the email is registered.
        raise HTTPException(400, "验证码不正确或该邮箱未注册。")

    db.execute(
        update(EmailCredential.__table__)
        .where(EmailCredential.user_id == cred["user_id"])
        .values(password_hash=hash_password(body.newPassword), updated_at=_now())
    )
    # Revoke all sessions for this user.
    db.execute(delete(AuthSession).where(AuthSession.user_id == cred["user_id"]))
    # Clean up the verification row.
    db.execute(delete(EmailVerification).where(EmailVerification.id == row["id"]))
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(_db)):
    cookie = request.cookies.get("zhishu_session")
    if not cookie:
        return {"isLoggedIn": False}
    row = db.execute(
        select(AuthSession.user_id).where(
            AuthSession.token_hash == token_hash(cookie),
            AuthSession.expires_at > _now(),
        )
    ).first()
    if not row:
        return {"isLoggedIn": False}
    email = db.scalar(
        select(EmailCredential.__table__.c.email).where(EmailCredential.user_id == row[0])
    )
    return {"isLoggedIn": True, "userId": row[0], "email": email}