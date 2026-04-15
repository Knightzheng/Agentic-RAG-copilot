"""Run trace repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentRun, AgentRunStep, RunStateSnapshot


class RunRepository:
    """Encapsulate read access for run trace views."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, run_id: UUID) -> AgentRun | None:
        """Fetch a single run by primary key."""

        stmt = select(AgentRun).where(AgentRun.id == run_id)
        return self.db.scalar(stmt)

    def list_by_workspace(self, workspace_id: UUID, limit: int = 30) -> list[AgentRun]:
        """Return recent runs for one workspace."""

        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc(), AgentRun.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_steps(self, run_id: UUID) -> list[AgentRunStep]:
        """Return all recorded steps for a run."""

        stmt = (
            select(AgentRunStep)
            .where(AgentRunStep.run_id == run_id)
            .order_by(AgentRunStep.started_at.asc(), AgentRunStep.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    def list_snapshots(self, run_id: UUID) -> list[RunStateSnapshot]:
        """Return ordered state snapshots for a run."""

        stmt = (
            select(RunStateSnapshot)
            .where(RunStateSnapshot.run_id == run_id)
            .order_by(RunStateSnapshot.snapshot_index.asc(), RunStateSnapshot.created_at.asc())
        )
        return list(self.db.scalars(stmt))
