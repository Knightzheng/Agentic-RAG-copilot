"""工作区相关模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    """创建工作区请求。"""

    name: str
    slug: str
    description: str | None = None
    owner_user_id: UUID
    visibility: str = "private"
    settings_json: dict = Field(default_factory=dict)


class WorkspaceRead(BaseModel):
    """工作区响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    owner_user_id: UUID
    visibility: str
    status: str
    settings_json: dict
    created_at: datetime
    updated_at: datetime
