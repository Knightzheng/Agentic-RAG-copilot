"""增加第二阶段索引与 RAG 运行表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20260408_0002"
down_revision = "20260408_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建第二阶段需要的索引、检索与引用表。"""

    op.create_table(
        "document_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.documents.id"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_versions.id"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_revision", sa.String(length=64), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("distance_metric", sa.String(length=32), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_kb",
    )
    op.create_index("ix_document_embeddings_chunk_id", "document_embeddings", ["chunk_id"], schema="app_kb")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_embeddings_embedding_ivfflat
        ON app_kb.document_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )

    op.create_table(
        "document_fts",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.documents.id"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_versions.id"), nullable=False),
        sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_kb",
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_fts_tsv_gin
        ON app_kb.document_fts
        USING gin (tsv)
        """
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.messages.id"), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("route_target", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("model_revision", sa.String(length=64), nullable=True),
        sa.Column("evidence_grade", sa.String(length=32), nullable=True),
        sa.Column("final_answer_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )

    op.create_table(
        "retrieval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("dense_top_k", sa.Integer(), nullable=False),
        sa.Column("lexical_top_k", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )

    op.create_table(
        "retrieval_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("retrieval_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.retrieval_runs.id"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.documents.id"), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("rank_no", sa.Integer(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("merged_score", sa.Float(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )

    op.create_table(
        "rerank_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("retrieval_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.retrieval_runs.id"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), nullable=False),
        sa.Column("rerank_model", sa.String(length=128), nullable=False),
        sa.Column("rank_no", sa.Integer(), nullable=False),
        sa.Column("rerank_score", sa.Float(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )

    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=False),
        sa.Column("answer_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.messages.id"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), nullable=False),
        sa.Column("citation_label", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )

    op.create_table(
        "evidence_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=False),
        sa.Column("evidence_grade", sa.String(length=32), nullable=False),
        sa.Column("insufficiency_reason", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )


def downgrade() -> None:
    """回滚第二阶段新增表。"""

    op.drop_table("evidence_assessments", schema="app_agent")
    op.drop_table("citations", schema="app_agent")
    op.drop_table("rerank_results", schema="app_agent")
    op.drop_table("retrieval_candidates", schema="app_agent")
    op.drop_table("retrieval_runs", schema="app_agent")
    op.drop_table("agent_runs", schema="app_agent")
    op.execute("DROP INDEX IF EXISTS app_kb.ix_document_fts_tsv_gin")
    op.drop_table("document_fts", schema="app_kb")
    op.execute("DROP INDEX IF EXISTS app_kb.ix_document_embeddings_embedding_ivfflat")
    op.drop_index("ix_document_embeddings_chunk_id", table_name="document_embeddings", schema="app_kb")
    op.drop_table("document_embeddings", schema="app_kb")
