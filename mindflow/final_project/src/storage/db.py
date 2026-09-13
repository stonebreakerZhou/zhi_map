"""数据库初始化、Session 工厂。

设计要点：
- 单例 engine + sessionmaker
- session_scope() 自动 commit/rollback（推荐用法）
- get_session() 给高级用户手动控制

P3 负责维护。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_database_url
from src.storage.schema import Base
from src.utils.logger import get_logger

logger = get_logger("mindflow.storage.db")

# 模块级单例
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db() -> Engine:
    """初始化数据库（创建表）。

    Returns:
        SQLAlchemy Engine 实例
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    url = get_database_url()
    logger.info(f"初始化数据库: {url}")

    # SQLite 需要 check_same_thread=False 以支持多线程
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

    _engine = create_engine(url, echo=False, connect_args=connect_args)

    # 🔧 关键：SQLite 默认不启用外键级联，必须通过 PRAGMA 开启
    @event.listens_for(_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        if url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)

    # ⭐ 一次性迁移：把旧 Node.image_path 字段数据搬到 node_attachments 表
    # 必须在表创建之后、所有业务调用之前执行
    try:
        from src.storage.migration import ensure_attachment_migration

        ensure_attachment_migration()
    except Exception as e:
        logger.error(f"附件迁移失败（可忽略，不影响主功能）: {e}")

    logger.info("数据库初始化完成")
    return _engine


def get_engine() -> Engine:
    """获取 engine（按需初始化）。"""
    if _engine is None:
        init_db()
    return _engine  # type: ignore[return-value]


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务性 session 上下文。

    用法：
        with session_scope() as session:
            session.add(obj)
            # 自动 commit
        # 出错时自动 rollback

    Yields:
        Session 实例
    """
    if _SessionLocal is None:
        init_db()

    session = _SessionLocal()  # type: ignore[misc]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """手动获取一个 session（调用方负责关闭）。

    推荐使用 session_scope()，仅在需要更细粒度控制时使用。
    """
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()  # type: ignore[misc]


def reset_db() -> None:
    """删除所有表（危险！仅测试用）。

    Windows 上 SQLite 文件需要先 dispose engine 再强制 GC 才能删。
    """
    import gc

    global _engine, _SessionLocal

    # 1. 强制 dispose engine 关闭所有连接
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _SessionLocal = None

    # 2. 强制垃圾回收（确保所有 Session 对象被销毁）
    gc.collect()

    # 3. 尝试删除文件
    from src.config import DATABASE_PATH

    if DATABASE_PATH.exists():
        try:
            DATABASE_PATH.unlink()
            logger.warning(f"数据库已重置（删除文件: {DATABASE_PATH.name}）")
        except PermissionError:
            # Windows 上偶发，重试一次
            import time

            time.sleep(0.1)
            gc.collect()
            DATABASE_PATH.unlink()
            logger.warning(f"数据库已重置（重试删除成功: {DATABASE_PATH.name}）")
