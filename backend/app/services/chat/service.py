"""基于 LangGraph 编排器的聊天服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRun, Citation, EvidenceAssessment, Message, Thread
from app.schemas.chat import ChatRequest, ChatResponse, CitationRead
from app.services.llm.dashscope_client import DashScopeClient
from app.services.memory.service import MemoryService
from app.services.orchestration.graph import AtlasSupervisorGraphService
from app.services.orchestration.state import AtlasAgentState


@dataclass(slots=True)
class PreparedChatRun:
    """封装图执行前已落库的线程、消息、运行记录与初始状态。"""

    thread: Thread
    user_message: Message
    run: AgentRun
    initial_state: AtlasAgentState


class ChatExecutionError(RuntimeError):
    """在失败运行已经持久化后抛出的执行异常。"""


class ChatService:
    """负责持久化聊天状态并执行当前阶段的图编排。"""

    def __init__(self, db: Session, llm_client: DashScopeClient | None = None) -> None:
        self.db = db
        self.llm_client = llm_client or (DashScopeClient() if settings.has_dashscope_api_key else None)
        self.memory_service = MemoryService(db=db, llm_client=self.llm_client)
        self.graph_service = AtlasSupervisorGraphService(db=db, llm_client=self.llm_client)

    def chat(self, payload: ChatRequest) -> ChatResponse:
        """执行一次同步聊天。"""

        prepared = self.prepare_chat(payload)
        try:
            final_state = self.graph_service.invoke(prepared.initial_state)
        except Exception as exc:
            self.mark_run_failed(prepared=prepared, exc=exc)
            raise ChatExecutionError(f"聊天执行失败：{exc}") from exc
        return self.complete_chat(prepared=prepared, final_state=final_state)

    def prepare_chat(self, payload: ChatRequest) -> PreparedChatRun:
        """创建线程、用户消息、运行记录以及图的初始状态。"""

        now = datetime.now(timezone.utc)
        thread = self._get_or_create_thread(payload=payload, created_at=now)
        self._sync_thread_attachments(thread=thread, payload=payload)

        user_message = self._create_message(
            thread_id=thread.id,
            run_id=None,
            role="user",
            content_text=payload.message,
            metadata_json={
                "attachments": [str(item) for item in payload.attachments],
                "requested_mode": payload.mode,
                "request_metadata": payload.metadata,
            },
            created_at=now,
        )
        self.db.add(user_message)
        self.db.flush()

        run = AgentRun(
            thread_id=thread.id,
            workspace_id=payload.workspace_id,
            user_id=payload.user_id,
            request_message_id=user_message.id,
            request_type="kb_qa",
            route_target="rag",
            status="running",
            result_status=None,
            model_name=settings.main_model,
            model_revision=None,
            evidence_grade=None,
            final_answer_message_id=None,
            token_usage_json={},
            metrics_json={},
            started_at=now,
            ended_at=None,
            error_code=None,
            error_message=None,
            created_at=now,
        )
        self.db.add(run)
        self.db.flush()

        initial_state: AtlasAgentState = {
            "run_id": run.id,
            "thread_id": thread.id,
            "workspace_id": payload.workspace_id,
            "user_id": payload.user_id,
            "user_message": payload.message,
            "requested_mode": payload.mode,
            "rewritten_message": None,
            "request_type": "smalltalk" if payload.mode == "direct" else "kb_qa",
            "route_target": "direct" if payload.mode == "direct" else "rag",
            "status": "running",
            "thread_summary": self._extract_thread_summary(thread),
            "messages": [],
            "attached_document_ids": list(payload.attachments),
            "pinned_document_ids": [],
            "recalled_memories": [],
            "retrieval_run_id": None,
            "retrieval_usage": {},
            "retrieved_candidates": [],
            "evidence_grade": None,
            "insufficiency_reason": None,
            "final_answer": None,
            "citation_candidates": [],
            "token_usage": {},
            "error": None,
            "metrics": {},
        }

        return PreparedChatRun(
            thread=thread,
            user_message=user_message,
            run=run,
            initial_state=initial_state,
        )

    def rebuild_chat_request(self, run_id: UUID) -> ChatRequest:
        """根据历史运行重建聊天请求，供重试使用。"""

        run = self.db.get(AgentRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")

        thread = self.db.get(Thread, run.thread_id)
        if thread is None:
            raise ValueError("线程不存在")

        request_message = self.db.get(Message, run.request_message_id)
        if request_message is None:
            raise ValueError("请求消息不存在")
        if request_message.role != "user":
            raise ValueError("请求消息不是用户消息")

        return self._build_retry_request(run=run, thread=thread, request_message=request_message)

    def complete_chat(self, *, prepared: PreparedChatRun, final_state: AtlasAgentState) -> ChatResponse:
        """根据图执行结果落库回答消息并完成本次运行。"""

        answer_text = str(final_state.get("final_answer") or "").strip()
        evidence_grade = str(final_state.get("evidence_grade") or "insufficient")
        citations = self.graph_service.build_citation_reads(final_state.get("citation_candidates", []))

        assistant_message = self._create_message(
            thread_id=prepared.thread.id,
            run_id=prepared.run.id,
            role="assistant",
            content_text=answer_text,
            metadata_json={
                "evidence_grade": evidence_grade,
                "route_target": final_state.get("route_target"),
            },
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(assistant_message)
        self.db.flush()

        self._persist_citations(
            run_id=prepared.run.id,
            answer_message_id=assistant_message.id,
            citations=citations,
        )
        self._persist_evidence_assessment(run_id=prepared.run.id, final_state=final_state)
        self._apply_run_completion(
            run=prepared.run,
            assistant_message_id=assistant_message.id,
            final_state=final_state,
        )
        self._write_memory_artifacts(
            prepared=prepared,
            final_state=final_state,
            answer_text=assistant_message.content_text,
        )
        self._refresh_thread_summary(thread=prepared.thread)

        prepared.thread.latest_run_id = prepared.run.id
        prepared.thread.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        return ChatResponse(
            run_id=prepared.run.id,
            thread_id=prepared.thread.id,
            status=prepared.run.status,
            answer=assistant_message.content_text,
            evidence_grade=evidence_grade,
            citations=citations,
        )

    def mark_run_failed(self, *, prepared: PreparedChatRun, exc: Exception) -> None:
        """持久化失败信息，便于在 Trace Center 中排查。"""

        self._mark_run_failed(run=prepared.run, thread=prepared.thread, exc=exc)

    def mark_run_cancelled(self, *, prepared: PreparedChatRun, reason: str = "运行已被用户取消。") -> None:
        """持久化取消状态，便于在 Trace Center 中排查。"""

        now = datetime.now(timezone.utc)
        prepared.run.status = "cancelled"
        prepared.run.result_status = "cancelled"
        prepared.run.ended_at = now
        prepared.run.error_code = "RunCancelledError"
        prepared.run.error_message = reason
        prepared.thread.latest_run_id = prepared.run.id
        prepared.thread.updated_at = now
        self.db.flush()

    def _get_or_create_thread(self, payload: ChatRequest, created_at: datetime) -> Thread:
        if payload.thread_id is not None:
            thread = self.db.get(Thread, payload.thread_id)
            if thread is None:
                raise ValueError("thread_id 不存在")
            return thread

        thread = Thread(
            workspace_id=payload.workspace_id,
            created_by=payload.user_id,
            title=payload.message[:48],
            mode=payload.mode,
            status="active",
            metadata_json=payload.metadata,
            pinned_document_ids=[str(item) for item in payload.attachments],
            created_at=created_at,
            updated_at=created_at,
        )
        self.db.add(thread)
        self.db.flush()
        return thread

    def _sync_thread_attachments(self, *, thread: Thread, payload: ChatRequest) -> None:
        if payload.attachments:
            thread.pinned_document_ids = [str(item) for item in payload.attachments]
        thread.updated_at = datetime.now(timezone.utc)

    def _create_message(
        self,
        *,
        thread_id: UUID,
        run_id: UUID | None,
        role: str,
        content_text: str,
        metadata_json: dict,
        created_at: datetime,
    ) -> Message:
        sequence_no = (
            self.db.scalar(select(func.coalesce(func.max(Message.sequence_no), 0)).where(Message.thread_id == thread_id))
            or 0
        ) + 1
        return Message(
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content_text=content_text,
            content_json={},
            sequence_no=sequence_no,
            parent_message_id=None,
            metadata_json=metadata_json,
            created_at=created_at,
        )

    def _persist_citations(
        self,
        *,
        run_id: UUID,
        answer_message_id: UUID,
        citations: list[CitationRead],
    ) -> None:
        now = datetime.now(timezone.utc)
        for ordinal, citation in enumerate(citations, start=1):
            self.db.add(
                Citation(
                    run_id=run_id,
                    answer_message_id=answer_message_id,
                    chunk_id=citation.chunk_id,
                    citation_label=citation.citation_label or f"C{ordinal}",
                    ordinal=ordinal,
                    created_at=now,
                )
            )

    def _persist_evidence_assessment(self, *, run_id: UUID, final_state: AtlasAgentState) -> None:
        candidates = final_state.get("retrieved_candidates", [])
        top_candidate = candidates[0] if candidates else None
        confidence_score = None
        if top_candidate is not None:
            confidence_score = top_candidate.rerank_score or top_candidate.hybrid_score

        self.db.add(
            EvidenceAssessment(
                run_id=run_id,
                evidence_grade=str(final_state.get("evidence_grade") or "insufficient"),
                insufficiency_reason=final_state.get("insufficiency_reason"),
                confidence_score=confidence_score,
                metadata_json={
                    "candidate_count": len(candidates),
                    "citation_count": len(final_state.get("citation_candidates", [])),
                },
                created_at=datetime.now(timezone.utc),
            )
        )

    def _apply_run_completion(
        self,
        *,
        run: AgentRun,
        assistant_message_id: UUID,
        final_state: AtlasAgentState,
    ) -> None:
        evidence_grade = str(final_state.get("evidence_grade") or "insufficient")
        run.request_type = str(final_state.get("request_type") or run.request_type)
        run.route_target = str(final_state.get("route_target") or run.route_target)
        run.status = str(final_state.get("status") or "completed")
        run.result_status = "success" if evidence_grade != "insufficient" else "insufficient"
        run.evidence_grade = evidence_grade
        run.final_answer_message_id = assistant_message_id
        run.token_usage_json = final_state.get("token_usage", {}) or {}
        run.metrics_json = final_state.get("metrics", {}) or {}
        run.ended_at = datetime.now(timezone.utc)
        run.error_code = None
        run.error_message = None

    def _mark_run_failed(self, *, run: AgentRun, thread: Thread, exc: Exception) -> None:
        now = datetime.now(timezone.utc)
        run.status = "failed"
        run.result_status = "error"
        run.ended_at = now
        run.error_code = type(exc).__name__
        run.error_message = str(exc)
        run.metrics_json = run.metrics_json or {}
        thread.latest_run_id = run.id
        thread.updated_at = now
        self.db.flush()

    def _write_memory_artifacts(
        self,
        *,
        prepared: PreparedChatRun,
        final_state: AtlasAgentState,
        answer_text: str,
    ) -> None:
        self.memory_service.ensure_default_namespaces(
            workspace_id=prepared.run.workspace_id,
            user_id=prepared.run.user_id,
        )
        self.memory_service.maybe_write_semantic_memory(
            workspace_id=prepared.run.workspace_id,
            user_id=prepared.run.user_id,
            thread_id=prepared.thread.id,
            run_id=prepared.run.id,
            user_message=prepared.user_message.content_text,
        )
        self.memory_service.maybe_write_episodic_memory(
            workspace_id=prepared.run.workspace_id,
            user_id=prepared.run.user_id,
            thread_id=prepared.thread.id,
            run_id=prepared.run.id,
            question=prepared.user_message.content_text,
            answer=answer_text,
            result_status=str(prepared.run.result_status or "success"),
            evidence_grade=str(final_state.get("evidence_grade") or "insufficient"),
            request_type=str(final_state.get("request_type") or prepared.run.request_type),
            route_target=str(final_state.get("route_target") or prepared.run.route_target),
        )

    def _refresh_thread_summary(self, *, thread: Thread) -> str | None:
        messages = list(
            self.db.scalars(select(Message).where(Message.thread_id == thread.id).order_by(Message.sequence_no.asc()))
        )
        summary_source = messages[:-4]
        metadata = dict(thread.metadata_json or {})
        if not summary_source:
            metadata.pop("thread_summary", None)
            metadata.pop("thread_summary_message_count", None)
            thread.metadata_json = metadata
            return None

        summary_text = self._summarize_messages(summary_source)
        metadata["thread_summary"] = summary_text
        metadata["thread_summary_message_count"] = len(summary_source)
        thread.metadata_json = metadata
        return summary_text

    def _summarize_messages(self, messages: list[Message]) -> str:
        if len(messages) <= 4:
            return self._fallback_thread_summary(messages)

        transcript = self._format_summary_transcript(messages)
        if self.llm_client is not None:
            try:
                summary, _usage = self.llm_client.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Compress the earlier conversation into a compact working-memory summary in Chinese. "
                                "Keep stable facts, user preferences, decisions, unresolved questions, and important constraints. "
                                "Do not include greetings. Keep it within 6 short bullet points."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Conversation transcript:\n{transcript}\n\nCompressed summary:",
                        },
                    ],
                    temperature=0.0,
                    max_tokens=220,
                )
                normalized = "\n".join(line.strip() for line in summary.splitlines() if line.strip()).strip()
                if normalized:
                    return normalized[:1200]
            except Exception:
                pass

        return self._fallback_thread_summary(messages)

    def _format_summary_transcript(self, messages: list[Message]) -> str:
        transcript_lines = []
        for message in messages[-16:]:
            role = message.role.upper()
            content = " ".join(message.content_text.split())
            if not content:
                continue
            transcript_lines.append(f"{role}: {content[:320]}")
        return "\n".join(transcript_lines)[:4000]

    def _fallback_thread_summary(self, messages: list[Message]) -> str:
        user_points: list[str] = []
        assistant_points: list[str] = []
        for message in messages[-12:]:
            content = " ".join(message.content_text.split())
            if not content:
                continue
            compact = content[:160]
            if message.role == "user":
                user_points.append(compact)
            elif message.role == "assistant":
                assistant_points.append(compact)

        lines: list[str] = []
        if user_points:
            lines.append(f"- User focus: {' | '.join(user_points[-3:])}")
        if assistant_points:
            lines.append(f"- Assistant conclusions: {' | '.join(assistant_points[-3:])}")
        if not lines:
            lines.append("- Earlier conversation exists but could not be compressed.")
        return "\n".join(lines)

    @staticmethod
    def _extract_thread_summary(thread: Thread) -> str | None:
        metadata = thread.metadata_json
        if isinstance(metadata, dict):
            summary = metadata.get("thread_summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip()
        return None

    @staticmethod
    def _build_retry_request(*, run: AgentRun, thread: Thread, request_message: Message) -> ChatRequest:
        attachments = ChatService._parse_attachment_ids(
            request_message.metadata_json.get("attachments"),
            thread.pinned_document_ids,
        )
        request_metadata = request_message.metadata_json.get("request_metadata")
        metadata = dict(request_metadata) if isinstance(request_metadata, dict) else dict(thread.metadata_json or {})
        metadata["retry_of_run_id"] = str(run.id)

        stored_mode = request_message.metadata_json.get("requested_mode")
        if isinstance(stored_mode, str) and stored_mode.strip():
            mode = stored_mode.strip()
        else:
            metadata_mode = metadata.get("requested_mode")
            if isinstance(metadata_mode, str) and metadata_mode.strip():
                mode = metadata_mode.strip()
            else:
                mode = str(thread.mode or "auto")

        return ChatRequest(
            thread_id=thread.id,
            workspace_id=run.workspace_id,
            message=request_message.content_text,
            attachments=attachments,
            mode=mode,
            metadata=metadata,
            user_id=run.user_id,
        )

    @staticmethod
    def _parse_attachment_ids(value: object, fallback: object = None) -> list[UUID]:
        raw_values = value if isinstance(value, list) else fallback if isinstance(fallback, list) else []
        attachment_ids: list[UUID] = []
        for item in raw_values:
            try:
                attachment_ids.append(item if isinstance(item, UUID) else UUID(str(item)))
            except (TypeError, ValueError):
                continue
        return attachment_ids
