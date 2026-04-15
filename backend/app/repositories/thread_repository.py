"""线程仓储。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Message, Thread
from app.schemas.threads import ThreadCreate


class ThreadRepository:
    """封装线程主表的最小读写操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_workspace(self, workspace_id: UUID) -> list[Thread]:
        """返回某个工作区下的线程列表。"""

        stmt = select(Thread).where(Thread.workspace_id == workspace_id).order_by(Thread.updated_at.desc())
        return list(self.db.scalars(stmt))

    def get(self, thread_id: UUID) -> Thread | None:
        """根据主键查询线程。"""

        stmt = select(Thread).where(Thread.id == thread_id)
        return self.db.scalar(stmt)

    def list_messages(self, thread_id: UUID) -> list[Message]:
        """返回线程中的消息列表。"""

        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_no.asc())
        return list(self.db.scalars(stmt))

    def create(self, payload: ThreadCreate) -> Thread:
        """创建线程。"""

        thread = Thread(
            workspace_id=payload.workspace_id,
            created_by=payload.created_by,
            title=payload.title,
            mode=payload.mode,
            status="active",
            metadata_json=payload.metadata_json,
            pinned_document_ids=[str(item) for item in payload.pinned_document_ids],
        )
        self.db.add(thread)
        return thread
