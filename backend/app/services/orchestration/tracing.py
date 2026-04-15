"""Run step tracing helpers for LangGraph execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent import AgentRunStep, RunStateSnapshot
from app.services.chat.stream_control import RunCancelledError
from app.services.retrieval.service import RetrievedCandidate


class RunTraceRecorder:
    """Persist step records and state snapshots during graph execution."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._snapshot_index = 0
        self._step_event_callback: Callable[[dict[str, Any]], None] | None = None

    def instrument(
        self,
        *,
        step_key: str,
        handler: Callable[[dict], dict],
        step_type: str = "graph_node",
    ) -> Callable[[dict], dict]:
        """Wrap a graph node so each invocation is persisted as a trace step."""

        def wrapped(state: dict) -> dict:
            now = datetime.now(timezone.utc)
            step = AgentRunStep(
                run_id=state["run_id"],
                thread_id=state["thread_id"],
                step_key=step_key,
                step_type=step_type,
                status="running",
                input_json=self._summarize_state(state),
                output_json={},
                error_code=None,
                error_message=None,
                started_at=now,
                ended_at=None,
                created_at=now,
            )
            self.db.add(step)
            self.db.flush()
            self._emit_step_event(step=step, output=None, error=None)

            try:
                result = handler(state)
                merged_state = dict(state)
                merged_state.update(result)
                step.status = "completed"
                summarized_output = self._summarize_update(result)
                step.output_json = summarized_output
                step.ended_at = datetime.now(timezone.utc)
                self._write_snapshot(
                    run_id=state["run_id"],
                    thread_id=state["thread_id"],
                    step_key=step_key,
                    state=merged_state,
                )
                self._emit_step_event(step=step, output=summarized_output, error=None)
                return result
            except Exception as exc:
                failed_state = dict(state)
                step_status = "cancelled" if isinstance(exc, RunCancelledError) else "failed"
                failed_state["status"] = step_status
                failed_state["error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                step.status = step_status
                step.error_code = type(exc).__name__
                step.error_message = str(exc)
                step.output_json = {"error": {"type": type(exc).__name__, "message": str(exc)}}
                step.ended_at = datetime.now(timezone.utc)
                self._write_snapshot(
                    run_id=state["run_id"],
                    thread_id=state["thread_id"],
                    step_key=step_key,
                    state=failed_state,
                )
                self._emit_step_event(
                    step=step,
                    output=step.output_json,
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                raise

        return wrapped

    def set_step_event_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        """Register an optional callback for live step lifecycle updates."""

        self._step_event_callback = callback

    def _write_snapshot(self, *, run_id: UUID, thread_id: UUID, step_key: str, state: dict) -> None:
        """Persist one condensed snapshot after a successful or failed step."""

        self._snapshot_index += 1
        self.db.add(
            RunStateSnapshot(
                run_id=run_id,
                thread_id=thread_id,
                step_key=step_key,
                snapshot_index=self._snapshot_index,
                state_json=self._summarize_state(state),
                created_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

    def _summarize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Keep snapshots compact and JSON-safe for Trace Center rendering."""

        summary = {
            "run_id": self._jsonable(state.get("run_id")),
            "thread_id": self._jsonable(state.get("thread_id")),
            "workspace_id": self._jsonable(state.get("workspace_id")),
            "request_type": state.get("request_type"),
            "route_target": state.get("route_target"),
            "status": state.get("status"),
            "thread_summary": state.get("thread_summary"),
            "user_message": state.get("user_message"),
            "rewritten_message": state.get("rewritten_message"),
            "normalized_message": state.get("normalized_message"),
            "attached_document_ids": self._jsonable(state.get("attached_document_ids", [])),
            "pinned_document_ids": self._jsonable(state.get("pinned_document_ids", [])),
            "message_count": len(state.get("messages", [])),
            "recalled_memory_count": len(state.get("recalled_memories", [])),
            "retrieval_run_id": self._jsonable(state.get("retrieval_run_id")),
            "retrieved_candidate_count": len(state.get("retrieved_candidates", [])),
            "evidence_grade": state.get("evidence_grade"),
            "insufficiency_reason": state.get("insufficiency_reason"),
            "citation_count": len(state.get("citation_candidates", [])),
            "final_answer_preview": (state.get("final_answer") or "")[:240],
            "metrics": self._jsonable(state.get("metrics", {})),
            "token_usage": self._jsonable(state.get("token_usage", {})),
            "error": self._jsonable(state.get("error")),
        }
        return summary

    def _summarize_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Store a safe summary of the step output rather than raw in-memory objects."""

        return self._jsonable(update)

    def summarize_update(self, update: Any) -> Any:
        """Expose JSON-safe output summaries to streaming and UI layers."""

        return self._jsonable(update)

    def _emit_step_event(
        self,
        *,
        step: AgentRunStep,
        output: Any,
        error: dict[str, Any] | None,
    ) -> None:
        if self._step_event_callback is None:
            return

        duration_ms = None
        if step.ended_at is not None:
            duration_ms = int((step.ended_at - step.started_at).total_seconds() * 1000)

        self._step_event_callback(
            {
                "run_id": str(step.run_id),
                "thread_id": str(step.thread_id),
                "step_key": step.step_key,
                "step_type": step.step_type,
                "status": step.status,
                "started_at": step.started_at.isoformat(),
                "ended_at": step.ended_at.isoformat() if step.ended_at is not None else None,
                "duration_ms": duration_ms,
                "output": self._jsonable(output) if output is not None else None,
                "error": self._jsonable(error),
            }
        )

    def _jsonable(self, value: Any) -> Any:
        """Convert rich Python objects used in the graph state into JSON-safe data."""

        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, RetrievedCandidate):
            return {
                "chunk_id": str(value.chunk.id),
                "document_id": str(value.document_id),
                "section_path": [str(item) for item in value.chunk.section_path],
                "page_start": value.chunk.page_start,
                "page_end": value.chunk.page_end,
                "hybrid_score": value.hybrid_score,
                "rerank_score": value.rerank_score,
                "alignment_score": value.alignment_score,
                "final_score": value.final_score,
            }

        if isinstance(value, list):
            return [self._jsonable(item) for item in value[:20]]

        if isinstance(value, tuple):
            return [self._jsonable(item) for item in value[:20]]

        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}

        return str(value)
