"""app_kb 域模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """文档主表。"""

    __tablename__ = "documents"
    __table_args__ = {"schema": "app_kb"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    source_uri: Mapped[str | None] = mapped_column(Text(), nullable=True)
    latest_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tags_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """文档版本表。"""

    __tablename__ = "document_versions"
    __table_args__ = {"schema": "app_kb"}

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.documents.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_uri: Mapped[str] = mapped_column(Text(), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    chunk_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    embedding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)

    document: Mapped[Document] = relationship(back_populates="versions")
    blocks: Mapped[list["DocumentBlock"]] = relationship(back_populates="document_version")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document_version")


class DocumentBlock(UUIDPrimaryKeyMixin, Base):
    """结构化 block 表。"""

    __tablename__ = "document_blocks"
    __table_args__ = {"schema": "app_kb"}

    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_versions.id"), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_order: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    section_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    raw_text: Mapped[str] = mapped_column(Text(), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text(), nullable=False)
    bbox_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    document_version: Mapped[DocumentVersion] = relationship(back_populates="blocks")


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    """parent / child chunk 表。"""

    __tablename__ = "document_chunks"
    __table_args__ = {"schema": "app_kb"}

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_versions.id"), nullable=False)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), nullable=True)
    chunk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    block_span_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    raw_text: Mapped[str] = mapped_column(Text(), nullable=False)
    contextualized_text: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


class DocumentEmbedding(UUIDPrimaryKeyMixin, Base):
    """child chunk 向量表。"""

    __tablename__ = "document_embeddings"
    __table_args__ = {"schema": "app_kb"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_versions.id"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(32), nullable=False, default="cosine")
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentFTS(Base):
    """全文检索索引表。"""

    __tablename__ = "document_fts"
    __table_args__ = {"schema": "app_kb"}

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.documents.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_versions.id"), nullable=False)
    searchable_text: Mapped[str] = mapped_column(Text(), nullable=False)
    tsv: Mapped[str] = mapped_column(TSVECTOR, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
