"""Add app_memory tables for semantic, episodic, and procedural memories."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20260408_0004"
down_revision = "20260408_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create app_memory schema plus long-term memory tables."""

    op.execute("CREATE SCHEMA IF NOT EXISTS app_memory")

    op.create_table(
        "memory_namespaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("namespace_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "namespace_key", name="uq_memory_namespaces_workspace_key"),
        schema="app_memory",
    )
    op.create_index(
        "ix_memory_namespaces_workspace_type",
        "memory_namespaces",
        ["workspace_id", "memory_type"],
        schema="app_memory",
    )

    op.create_table(
        "semantic_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("namespace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_memory.memory_namespaces.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=True),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_memory",
    )
    op.create_index("ix_semantic_memories_workspace_updated", "semantic_memories", ["workspace_id", "updated_at"], schema="app_memory")

    op.create_table(
        "semantic_memory_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_memory.semantic_memories.id"), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_memory",
    )
    op.create_index(
        "ix_semantic_memory_embeddings_memory_id",
        "semantic_memory_embeddings",
        ["memory_id"],
        schema="app_memory",
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_semantic_memory_embeddings_embedding_ivfflat
        ON app_memory.semantic_memory_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 50)
        """
    )

    op.create_table(
        "episodic_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("namespace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_memory.memory_namespaces.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=True),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_memory",
    )
    op.create_index("ix_episodic_memories_workspace_updated", "episodic_memories", ["workspace_id", "updated_at"], schema="app_memory")

    op.create_table(
        "episodic_memory_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_memory.episodic_memories.id"), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_memory",
    )
    op.create_index(
        "ix_episodic_memory_embeddings_memory_id",
        "episodic_memory_embeddings",
        ["memory_id"],
        schema="app_memory",
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_episodic_memory_embeddings_embedding_ivfflat
        ON app_memory.episodic_memory_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 50)
        """
    )

    op.create_table(
        "procedural_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("namespace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_memory.memory_namespaces.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_core.workspaces.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=True),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_memory",
    )
    op.create_index(
        "ix_procedural_memories_workspace_priority",
        "procedural_memories",
        ["workspace_id", "priority"],
        schema="app_memory",
    )


def downgrade() -> None:
    """Drop app_memory objects."""

    op.drop_index("ix_procedural_memories_workspace_priority", table_name="procedural_memories", schema="app_memory")
    op.drop_table("procedural_memories", schema="app_memory")
    op.execute("DROP INDEX IF EXISTS app_memory.ix_episodic_memory_embeddings_embedding_ivfflat")
    op.drop_index("ix_episodic_memory_embeddings_memory_id", table_name="episodic_memory_embeddings", schema="app_memory")
    op.drop_table("episodic_memory_embeddings", schema="app_memory")
    op.drop_index("ix_episodic_memories_workspace_updated", table_name="episodic_memories", schema="app_memory")
    op.drop_table("episodic_memories", schema="app_memory")
    op.execute("DROP INDEX IF EXISTS app_memory.ix_semantic_memory_embeddings_embedding_ivfflat")
    op.drop_index("ix_semantic_memory_embeddings_memory_id", table_name="semantic_memory_embeddings", schema="app_memory")
    op.drop_table("semantic_memory_embeddings", schema="app_memory")
    op.drop_index("ix_semantic_memories_workspace_updated", table_name="semantic_memories", schema="app_memory")
    op.drop_table("semantic_memories", schema="app_memory")
    op.drop_index("ix_memory_namespaces_workspace_type", table_name="memory_namespaces", schema="app_memory")
    op.drop_table("memory_namespaces", schema="app_memory")
    op.execute("DROP SCHEMA IF EXISTS app_memory")
