"""Run trace schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RunRead(BaseModel):
    """Summary view for a single run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    workspace_id: UUID
    user_id: UUID
    request_type: str
    route_target: str
    status: str
    result_status: str | None
    evidence_grade: str | None
    error_code: str | None
    error_message: str | None
    token_usage_json: dict
    metrics_json: dict
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime


class RunStepRead(BaseModel):
    """Step-level trace record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    thread_id: UUID
    step_key: str
    step_type: str
    status: str
    input_json: dict
    output_json: dict
    error_code: str | None
    error_message: str | None
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime


class RunStateSnapshotRead(BaseModel):
    """State summary after a graph step."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    thread_id: UUID
    step_key: str
    snapshot_index: int
    state_json: dict
    created_at: datetime


class RunTraceRead(BaseModel):
    """Full trace payload for Trace Center."""

    run: RunRead
    steps: list[RunStepRead]
    snapshots: list[RunStateSnapshotRead]
