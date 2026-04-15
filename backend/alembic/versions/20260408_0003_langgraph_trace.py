"""Add LangGraph step trace tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260408_0003"
down_revision = "20260408_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create step-level trace tables for graph orchestration."""

    op.create_table(
        "agent_run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("step_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"], schema="app_agent")
    op.create_index("ix_agent_run_steps_thread_id", "agent_run_steps", ["thread_id"], schema="app_agent")
    op.create_index("ix_agent_run_steps_step_key", "agent_run_steps", ["step_key"], schema="app_agent")

    op.create_table(
        "run_state_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.agent_runs.id"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_agent.threads.id"), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("snapshot_index", sa.Integer(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="app_agent",
    )
    op.create_index("ix_run_state_snapshots_run_id", "run_state_snapshots", ["run_id"], schema="app_agent")
    op.create_index("ix_run_state_snapshots_snapshot_index", "run_state_snapshots", ["snapshot_index"], schema="app_agent")


def downgrade() -> None:
    """Drop LangGraph step trace tables."""

    op.drop_index("ix_run_state_snapshots_snapshot_index", table_name="run_state_snapshots", schema="app_agent")
    op.drop_index("ix_run_state_snapshots_run_id", table_name="run_state_snapshots", schema="app_agent")
    op.drop_table("run_state_snapshots", schema="app_agent")
    op.drop_index("ix_agent_run_steps_step_key", table_name="agent_run_steps", schema="app_agent")
    op.drop_index("ix_agent_run_steps_thread_id", table_name="agent_run_steps", schema="app_agent")
    op.drop_index("ix_agent_run_steps_run_id", table_name="agent_run_steps", schema="app_agent")
    op.drop_table("agent_run_steps", schema="app_agent")
