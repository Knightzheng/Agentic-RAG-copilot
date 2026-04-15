"""app_agent 域模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """对话线程表。"""

    __tablename__ = "threads"
    __table_args__ = {"schema": "app_agent"}

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    latest_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pinned_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="thread")


class Message(UUIDPrimaryKeyMixin, Base):
    """线程消息表。"""

    __tablename__ = "messages"
    __table_args__ = {"schema": "app_agent"}

    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str] = mapped_column(Text(), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread: Mapped[Thread] = relationship(back_populates="messages")


class AgentRun(UUIDPrimaryKeyMixin, Base):
    """一次聊天 / RAG 执行记录。"""

    __tablename__ = "agent_runs"
    __table_args__ = {"schema": "app_agent"}

    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.messages.id"), nullable=False)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    route_target: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    final_answer_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    token_usage_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunStep(UUIDPrimaryKeyMixin, Base):
    """记录 LangGraph 节点级执行情况。"""

    __tablename__ = "agent_run_steps"
    __table_args__ = {"schema": "app_agent"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunStateSnapshot(UUIDPrimaryKeyMixin, Base):
    """记录每个关键节点完成后的状态摘要。"""

    __tablename__ = "run_state_snapshots"
    __table_args__ = {"schema": "app_agent"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetrievalRun(UUIDPrimaryKeyMixin, Base):
    """一次检索执行记录。"""

    __tablename__ = "retrieval_runs"
    __table_args__ = {"schema": "app_agent"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.threads.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_core.workspaces.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(Text(), nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text(), nullable=True)
    dense_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    lexical_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetrievalCandidate(UUIDPrimaryKeyMixin, Base):
    """检索候选记录。"""

    __tablename__ = "retrieval_candidates"
    __table_args__ = {"schema": "app_agent"}

    retrieval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.retrieval_runs.id"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.documents.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    rank_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    merged_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RerankResult(UUIDPrimaryKeyMixin, Base):
    """重排序结果。"""

    __tablename__ = "rerank_results"
    __table_args__ = {"schema": "app_agent"}

    retrieval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.retrieval_runs.id"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), nullable=False)
    rerank_model: Mapped[str] = mapped_column(String(128), nullable=False)
    rank_no: Mapped[int] = mapped_column(Integer, nullable=False)
    rerank_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    is_selected: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Citation(UUIDPrimaryKeyMixin, Base):
    """回答与 chunk 的引用绑定。"""

    __tablename__ = "citations"
    __table_args__ = {"schema": "app_agent"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=False)
    answer_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.messages.id"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_kb.document_chunks.id"), nullable=False)
    citation_label: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceAssessment(UUIDPrimaryKeyMixin, Base):
    """证据充分性判定记录。"""

    __tablename__ = "evidence_assessments"
    __table_args__ = {"schema": "app_agent"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_agent.agent_runs.id"), nullable=False)
    evidence_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    insufficiency_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
