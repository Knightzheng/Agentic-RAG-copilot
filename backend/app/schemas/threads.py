"""线程相关模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThreadCreate(BaseModel):
    """创建线程请求。"""

    workspace_id: UUID
    created_by: UUID
    title: str
    mode: str = "auto"
    pinned_document_ids: list[UUID] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class ThreadRead(BaseModel):
    """线程响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    mode: str
    status: str
    created_at: datetime
    updated_at: datetime
