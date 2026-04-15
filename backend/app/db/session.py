"""数据库连接与会话管理。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app import models  # noqa: F401

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """为 FastAPI 提供数据库会话。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
