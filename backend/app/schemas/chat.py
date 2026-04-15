"""聊天与引用相关模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class ChatRequest(BaseModel):
    """聊天请求。"""

    thread_id: UUID | None = None
    workspace_id: UUID
    message: str
    attachments: list[UUID] = Field(default_factory=list)
    mode: str = "auto"
    metadata: dict = Field(default_factory=dict)
    user_id: UUID = settings.default_owner_user_id


class CitationRead(BaseModel):
    """引用响应。"""

    chunk_id: UUID
    document_id: UUID
    citation_label: str
    chunk_level: str
    page_no: int | None
    page_start: int | None
    page_end: int | None
    section_path: list[str]
    snippet: str


class ChatResponse(BaseModel):
    """同步聊天响应。"""

    run_id: UUID
    thread_id: UUID
    status: str
    answer: str
    evidence_grade: str
    citations: list[CitationRead]


class MessageRead(BaseModel):
    """消息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content_text: str
    sequence_no: int
    metadata_json: dict
    created_at: datetime


class ThreadDetailRead(BaseModel):
    """线程详情响应。"""

    id: UUID
    workspace_id: UUID
    title: str
    mode: str
    status: str
    thread_summary: str | None = None
    messages: list[MessageRead]
