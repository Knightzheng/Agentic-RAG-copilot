"""Shared graph state for Atlas orchestration."""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID


class AtlasAgentState(TypedDict, total=False):
    """Minimal supervisor state used in Milestone 4."""

    run_id: UUID
    thread_id: UUID
    workspace_id: UUID
    user_id: UUID
    user_message: str
    requested_mode: str | None
    rewritten_message: str | None
    normalized_message: str | None
    request_type: str | None
    route_target: str | None
    status: str
    thread_summary: str | None
    messages: list[dict]
    attached_document_ids: list[UUID]
    pinned_document_ids: list[UUID]
    recalled_memories: list[dict]
    retrieval_run_id: UUID | None
    retrieval_usage: dict
    retrieved_candidates: list[Any]
    evidence_grade: str | None
    insufficiency_reason: str | None
    final_answer: str | None
    citation_candidates: list[dict]
    token_usage: dict
    error: dict | None
    metrics: dict
