"""文档相关请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    """文档列表响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    original_filename: str
    file_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentDetailRead(DocumentRead):
    """文档详情响应。"""

    source_type: str
    source_uri: str | None
    latest_version_id: UUID | None
    metadata_json: dict
    tags_json: list


class DocumentChunkRead(BaseModel):
    """chunk 列表响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    parent_chunk_id: UUID | None
    chunk_level: str
    chunk_order: int
    page_no: int | None
    page_start: int | None
    page_end: int | None
    section_path: list
    raw_text: str
    contextualized_text: str
    token_count: int
    char_count: int
    metadata_json: dict


class DocumentUploadResponse(BaseModel):
    """上传接口响应。"""

    document_id: UUID
    version_id: UUID
    status: str
    duplicate_of: UUID | None = None
