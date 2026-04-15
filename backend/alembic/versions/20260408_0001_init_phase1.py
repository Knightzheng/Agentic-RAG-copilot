"""初始化第一阶段基础表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260408_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建第一阶段需要的 schema 与表。"""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS app_core")
    op.execute("CREATE SCHEMA IF NOT EXISTS app_kb")
    op.execute("CREATE SCHEMA IF NOT EXISTS app_agent")

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="app_core",
    )

    op.create_table(
        "workspace_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_core",
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("latest_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="app_kb",
    )
    op.create_index("ix_documents_workspace_hash", "documents", ["workspace_id", "file_hash"], unique=False, schema="app_kb")

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.documents.id"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("chunk_status", sa.String(length=32), nullable=False),
        sa.Column("embedding_status", sa.String(length=32), nullable=False),
        sa.Column("index_status", sa.String(length=32), nullable=False),
        sa.Column("parser_name", sa.String(length=128), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_kb",
    )

    op.create_table(
        "document_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_versions.id"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("block_order", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("bbox_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_kb",
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.documents.id"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_versions.id"), nullable=False),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_kb.document_chunks.id"), nullable=True),
        sa.Column("chunk_level", sa.String(length=16), nullable=False),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("block_span_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("contextualized_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_kb",
    )

    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latest_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pinned_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema="app_agent",
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("parent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )


def downgrade() -> None:
    """回滚第一阶段基础表。"""

    op.drop_table("messages", schema="app_agent")
    op.drop_table("threads", schema="app_agent")
    op.drop_table("document_chunks", schema="app_kb")
    op.drop_table("document_blocks", schema="app_kb")
    op.drop_table("document_versions", schema="app_kb")
    op.drop_index("ix_documents_workspace_hash", table_name="documents", schema="app_kb")
    op.drop_table("documents", schema="app_kb")
    op.drop_table("workspace_members", schema="app_core")
    op.drop_table("workspaces", schema="app_core")
    op.execute("DROP SCHEMA IF EXISTS app_agent CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app_kb CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app_core CASCADE")
