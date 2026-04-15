"""Memory API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class MemoryCreate(BaseModel):
    """Create one long-term memory item."""

    workspace_id: UUID
    memory_type: str
    title: str
    content_text: str
    summary_text: str | None = None
    owner_user_id: UUID | None = settings.default_owner_user_id
    priority: int | None = None
    metadata_json: dict = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    """Update one memory item."""

    title: str | None = None
    content_text: str | None = None
    summary_text: str | None = None
    is_active: bool | None = None
    priority: int | None = None
    metadata_json: dict | None = None


class MemoryPinRequest(BaseModel):
    """Pin or unpin one memory item."""

    pinned: bool = True


class MemoryRead(BaseModel):
    """Unified read model for semantic, episodic, and procedural memories."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    memory_type: str
    title: str
    content_text: str
    summary_text: str | None
    source_run_id: UUID | None
    source_thread_id: UUID | None
    owner_user_id: UUID | None
    priority: int | None = None
    confidence_score: float | None = None
    score: float | None = None
    is_pinned: bool
    is_active: bool
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

