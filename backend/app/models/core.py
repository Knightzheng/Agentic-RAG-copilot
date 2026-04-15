"""app_core 域模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """工作区主表。"""

    __tablename__ = "workspaces"
    __table_args__ = {"schema": "app_core"}

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace")


class WorkspaceMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """工作区成员表。"""

    __tablename__ = "workspace_members"
    __table_args__ = {"schema": "app_core"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="members")
