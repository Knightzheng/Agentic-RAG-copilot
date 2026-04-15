"""app_memory domain models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MemoryNamespace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Namespace used to group long-term memories."""

    __tablename__ = "memory_namespaces"
    __table_args__ = {"schema": "app_memory"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    namespace_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SemanticMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Long-term factual or preference memory."""

    __tablename__ = "semantic_memories"
    __table_args__ = {"schema": "app_memory"}

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_memory.memory_namespaces.id"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_text: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=True)
    source_thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SemanticMemoryEmbedding(UUIDPrimaryKeyMixin, Base):
    """Vector index row for semantic memories."""

    __tablename__ = "semantic_memory_embeddings"
    __table_args__ = {"schema": "app_memory"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_memory.semantic_memories.id"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer(), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EpisodicMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Task or event summary memory."""

    __tablename__ = "episodic_memories"
    __table_args__ = {"schema": "app_memory"}

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_memory.memory_namespaces.id"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_text: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=True)
    source_thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EpisodicMemoryEmbedding(UUIDPrimaryKeyMixin, Base):
    """Vector index row for episodic memories."""

    __tablename__ = "episodic_memory_embeddings"
    __table_args__ = {"schema": "app_memory"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_memory.episodic_memories.id"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer(), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProceduralMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Rule or strategy memory maintained by admins."""

    __tablename__ = "procedural_memories"
    __table_args__ = {"schema": "app_memory"}

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_memory.memory_namespaces.id"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_text: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=True)
    source_thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    is_pinned: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
