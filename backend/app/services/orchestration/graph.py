"""基于 LangGraph 的主控编排器，内联 RAG 步骤并提供流式钩子。"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

import orjson
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import Message, Thread
from app.models.kb import Document
from app.schemas.chat import CitationRead
from app.services.chat.stream_control import RunCancelledError
from app.services.llm.dashscope_client import DashScopeClient
from app.services.memory.service import MemoryService
from app.services.orchestration.state import AtlasAgentState
from app.services.orchestration.tracing import RunTraceRecorder
from app.services.retrieval.service import RetrievalService


class AtlasSupervisorGraphService:
    """编译并执行当前阶段的最小主控图。"""

    def __init__(self, db: Session, llm_client: DashScopeClient | None = None) -> None:
        self.db = db
        self.llm_client = llm_client or (DashScopeClient() if settings.has_dashscope_api_key else None)
        self.retrieval_service = RetrievalService(db=db, llm_client=self.llm_client)
        self.memory_service = MemoryService(db=db, llm_client=self.llm_client)
        self.trace_recorder = RunTraceRecorder(db)
        self.answer_token_callback: Callable[[str], None] | None = None
        self.cancel_checker: Callable[[], bool] | None = None
        self._supervisor_graph = self._build_supervisor_graph()

    def invoke(self, initial_state: AtlasAgentState) -> AtlasAgentState:
        """同步执行编译后的图。"""

        return self._supervisor_graph.invoke(initial_state)

    def stream(self, initial_state: AtlasAgentState) -> Any:
        """向 SSE 消费端持续输出节点级更新。"""

        return self._supervisor_graph.stream(initial_state, stream_mode="updates")

    def summarize_stream_output(self, update: Any) -> Any:
        """将步骤输出压缩成适合 SSE 传输的安全 JSON 数据。"""

        return self.trace_recorder.summarize_update(update)

    def set_answer_token_callback(self, callback: Callable[[str], None] | None) -> None:
        """注册答案增量输出回调。"""

        self.answer_token_callback = callback

    def set_cancel_checker(self, callback: Callable[[], bool] | None) -> None:
        """注册运行中断检查函数。"""

        self.cancel_checker = callback

    def set_step_event_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        """注册步骤生命周期事件回调。"""

        self.trace_recorder.set_step_event_callback(callback)

    def _build_supervisor_graph(self):
        graph = StateGraph(AtlasAgentState)
        graph.add_node(
            "load_thread_context",
            self.trace_recorder.instrument(step_key="load_thread_context", handler=self._load_thread_context),
        )
        graph.add_node(
            "classify_request",
            self.trace_recorder.instrument(step_key="classify_request", handler=self._classify_request),
        )
        graph.add_node(
            "recall_long_term_memory",
            self.trace_recorder.instrument(
                step_key="recall_long_term_memory",
                handler=self._recall_long_term_memory,
            ),
        )
        graph.add_node(
            "invoke_rag_subgraph",
            self.trace_recorder.instrument(
                step_key="invoke_rag_subgraph",
                handler=self._enter_rag_subgraph,
                step_type="subgraph",
            ),
        )
        graph.add_node(
            "rag.rewrite_follow_up",
            self.trace_recorder.instrument(
                step_key="rag.rewrite_follow_up",
                handler=self._rewrite_follow_up_query,
                step_type="rag_node",
            ),
        )
        graph.add_node(
            "rag.normalize_query",
            self.trace_recorder.instrument(
                step_key="rag.normalize_query",
                handler=self._normalize_query,
                step_type="rag_node",
            ),
        )
        graph.add_node(
            "rag.retrieve_candidates",
            self.trace_recorder.instrument(
                step_key="rag.retrieve_candidates",
                handler=self._retrieve_candidates,
                step_type="rag_node",
            ),
        )
        graph.add_node(
            "rag.grade_evidence",
            self.trace_recorder.instrument(
                step_key="rag.grade_evidence",
                handler=self._grade_evidence,
                step_type="rag_node",
            ),
        )
        graph.add_node(
            "rag.generate_grounded_answer",
            self.trace_recorder.instrument(
                step_key="rag.generate_grounded_answer",
                handler=self._generate_grounded_answer,
                step_type="rag_node",
            ),
        )
        graph.add_node(
            "invoke_direct_answer",
            self.trace_recorder.instrument(step_key="invoke_direct_answer", handler=self._invoke_direct_answer),
        )
        graph.add_node(
            "compose_final_answer",
            self.trace_recorder.instrument(step_key="compose_final_answer", handler=self._compose_final_answer),
        )
        graph.add_node("finish", self.trace_recorder.instrument(step_key="finish", handler=self._finish))

        graph.add_edge(START, "load_thread_context")
        graph.add_edge("load_thread_context", "recall_long_term_memory")
        graph.add_edge("recall_long_term_memory", "classify_request")
        graph.add_conditional_edges(
            "classify_request",
            self._route_after_classify,
            {
                "invoke_rag_subgraph": "invoke_rag_subgraph",
                "invoke_direct_answer": "invoke_direct_answer",
            },
        )
        graph.add_edge("invoke_rag_subgraph", "rag.rewrite_follow_up")
        graph.add_edge("rag.rewrite_follow_up", "rag.normalize_query")
        graph.add_edge("rag.normalize_query", "rag.retrieve_candidates")
        graph.add_edge("rag.retrieve_candidates", "rag.grade_evidence")
        graph.add_edge("rag.grade_evidence", "rag.generate_grounded_answer")
        graph.add_edge("rag.generate_grounded_answer", "compose_final_answer")
        graph.add_edge("invoke_direct_answer", "compose_final_answer")
        graph.add_edge("compose_final_answer", "finish")
        graph.add_edge("finish", END)
        return graph.compile()

    def _load_thread_context(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        thread = self.db.get(Thread, state["thread_id"])
        if thread is None:
            raise ValueError("thread_id 不存在")

        all_messages = list(
            self.db.scalars(
                select(Message).where(Message.thread_id == state["thread_id"]).order_by(Message.sequence_no.asc())
            )
        )
        recent_messages = all_messages[-8:]
        metrics = dict(state.get("metrics", {}))
        metrics["thread_message_count"] = len(all_messages)
        metrics["context_message_window"] = len(recent_messages)
        return {
            "messages": [
                {
                    "id": str(item.id),
                    "role": item.role,
                    "content_text": item.content_text,
                    "sequence_no": item.sequence_no,
                }
                for item in recent_messages
            ],
            "pinned_document_ids": self._coerce_uuid_list(thread.pinned_document_ids),
            "thread_summary": self._extract_thread_summary(thread),
            "status": "running",
            "metrics": metrics,
        }

    def _recall_long_term_memory(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        recalled = self.memory_service.recall_memories(
            workspace_id=state["workspace_id"],
            query=str(state.get("user_message") or ""),
            limit=6,
        )
        metrics = dict(state.get("metrics", {}))
        metrics["recalled_memory_count"] = len(recalled)
        return {
            "recalled_memories": recalled,
            "metrics": metrics,
        }

    def _classify_request(self, state: AtlasAgentState) -> dict[str, str]:
        self._raise_if_cancelled()
        request_type, route_target = self._decide_request_routing(state)
        return {"request_type": request_type, "route_target": route_target}

    def _route_after_classify(self, state: AtlasAgentState) -> str:
        _request_type, route_target = self._decide_request_routing(state)
        if route_target == "direct":
            return "invoke_direct_answer"
        return "invoke_rag_subgraph"

    def _enter_rag_subgraph(self, state: AtlasAgentState) -> dict[str, Any]:
        """仅作为标记节点，便于流式客户端感知 RAG 路径开始。"""

        self._raise_if_cancelled()
        metrics = dict(state.get("metrics", {}))
        metrics["pipeline"] = "rag"
        return {"route_target": "rag", "metrics": metrics}

    def _rewrite_follow_up_query(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        current_question = " ".join(str(state["user_message"]).split())
        prior_messages = self._get_prior_messages(state)
        if not prior_messages:
            return {"rewritten_message": current_question}
        if not self._should_rewrite_follow_up(current_question, prior_messages):
            return {"rewritten_message": current_question}

        rewritten = self._rewrite_follow_up_with_context(
            current_question=current_question,
            prior_messages=prior_messages,
            thread_summary=str(state.get("thread_summary") or "").strip() or None,
        )
        return {"rewritten_message": rewritten or current_question}

    def _invoke_direct_answer(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        memory_recall_answer = self._build_memory_recall_answer(state)
        if memory_recall_answer is not None:
            return self._build_direct_result(memory_recall_answer)

        memory_write_ack = self._build_memory_write_ack(state)
        if memory_write_ack is not None:
            return self._build_direct_result(memory_write_ack)

        thread_context_summary = self._build_thread_context_summary_answer(state)
        if thread_context_summary is not None:
            return self._build_direct_result(thread_context_summary)

        thread_context_ack = self._build_thread_context_ack(state)
        if thread_context_ack is not None:
            return self._build_direct_result(thread_context_ack)

        event_memory_answer = self._build_event_memory_answer(state)
        if event_memory_answer is not None:
            return self._build_direct_result(event_memory_answer)

        focused_memory_answer = self._build_focused_memory_answer(state)
        if focused_memory_answer is not None:
            return self._build_direct_result(focused_memory_answer)

        prompt_message = self._build_direct_prompt_message(state)
        if self.llm_client is None:
            answer = "当前未配置对话模型，无法执行 direct 路由。"
            usage: dict[str, Any] = {}
        elif self.answer_token_callback is None:
            answer, usage = self.llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise assistant. Use the supplied conversation context when helpful. "
                            "If the user asks about the current project, thread, or remembered preferences, answer "
                            "only from the supplied thread summary, recent thread messages, and recalled memories. "
                            "Do not inject external facts or KB claims into thread-context answers. "
                            "If memory conflicts with the current user message, follow the current message."
                        ),
                    },
                    {"role": "user", "content": prompt_message},
                ],
                temperature=0.2,
                max_tokens=800,
            )
        else:
            answer, usage = self._stream_direct_answer(user_message=prompt_message)

        return {
            "evidence_grade": "weak",
            "insufficiency_reason": None,
            "final_answer": answer.strip(),
            "citation_candidates": [],
            "token_usage": {"answer": usage},
            "metrics": {
                "candidate_count": 0,
                "citation_count": 0,
                "pipeline": "direct",
            },
        }

    @staticmethod
    def _build_direct_result(answer: str) -> dict[str, Any]:
        return {
            "evidence_grade": "weak",
            "insufficiency_reason": None,
            "final_answer": answer,
            "citation_candidates": [],
            "token_usage": {"answer": {}},
            "metrics": {
                "candidate_count": 0,
                "citation_count": 0,
                "pipeline": "direct",
            },
        }

    def _compose_final_answer(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        final_answer = (state.get("final_answer") or "").strip()
        if final_answer:
            return {}

        metrics = dict(state.get("metrics", {}))
        metrics.setdefault("citation_count", len(state.get("citation_candidates", [])))
        return {
            "final_answer": "当前没有足够信息生成最终回答。",
            "evidence_grade": state.get("evidence_grade") or "insufficient",
            "insufficiency_reason": state.get("insufficiency_reason") or "graph did not produce a final answer",
            "metrics": metrics,
        }

    def _finish(self, state: AtlasAgentState) -> dict[str, str]:
        return {"status": "completed"}

    def _normalize_query(self, state: AtlasAgentState) -> dict[str, str]:
        self._raise_if_cancelled()
        source_message = str(state.get("rewritten_message") or state["user_message"])
        return {"normalized_message": " ".join(source_message.split())}

    def _retrieve_candidates(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        document_ids = state.get("attached_document_ids") or state.get("pinned_document_ids") or None
        retrieval_result = self.retrieval_service.retrieve(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            workspace_id=state["workspace_id"],
            query=state.get("normalized_message") or state["user_message"],
            document_ids=document_ids,
        )

        metrics = dict(state.get("metrics", {}))
        metrics["candidate_count"] = len(retrieval_result.candidates)
        return {
            "retrieval_run_id": retrieval_result.retrieval_run_id,
            "retrieval_usage": retrieval_result.usage,
            "retrieved_candidates": retrieval_result.candidates,
            "metrics": metrics,
        }

    def _grade_evidence(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        candidates = state.get("retrieved_candidates", [])
        if not candidates:
            return {
                "evidence_grade": "insufficient",
                "insufficiency_reason": "未检索到候选片段。",
            }

        top_score = candidates[0].rerank_score or candidates[0].hybrid_score
        if top_score >= 0.82:
            return {"evidence_grade": "sufficient", "insufficiency_reason": None}
        if top_score >= 0.45:
            return {
                "evidence_grade": "weak",
                "insufficiency_reason": "证据存在，但相关性仍偏弱。",
            }
        return {
            "evidence_grade": "insufficient",
            "insufficiency_reason": "检索结果与问题匹配度不足。",
        }

    def _generate_grounded_answer(self, state: AtlasAgentState) -> dict[str, Any]:
        self._raise_if_cancelled()
        candidates = state.get("retrieved_candidates", [])
        evidence_grade = state.get("evidence_grade") or "insufficient"
        answer_question = str(state.get("rewritten_message") or state["user_message"])
        token_usage = {"rerank": state.get("retrieval_usage", {})}
        metrics = dict(state.get("metrics", {}))

        if evidence_grade == "insufficient":
            used_candidates = candidates[:2]
            metrics["citation_count"] = len(used_candidates)
            return {
                "final_answer": "根据当前知识库中的证据，暂时无法可靠回答这个问题。请尝试补充更具体的文档或限定问题范围。",
                "citation_candidates": self._build_citation_payloads(used_candidates),
                "token_usage": token_usage,
                "metrics": metrics,
            }

        if self.llm_client is None:
            used_candidates = candidates[: min(3, len(candidates))]
            metrics["citation_count"] = len(used_candidates)
            return {
                "final_answer": "当前未配置对话模型，因此只能返回检索结果，无法生成最终自然语言回答。",
                "citation_candidates": self._build_citation_payloads(used_candidates),
                "token_usage": token_usage,
                "metrics": metrics,
            }

        evidence_blocks = []
        for index, candidate in enumerate(candidates[:6], start=1):
            section_text = " > ".join(str(item) for item in candidate.chunk.section_path) or "Untitled Section"
            location = candidate.chunk.page_no or candidate.chunk.page_start
            evidence_blocks.append(
                f"[C{index}] document_id={candidate.document_id} section={section_text} page={location}\n{candidate.evidence_text}"
            )

        context_block = self._build_conversation_context_block(state)
        system_prompt = (
            "You are Atlas Agentic RAG. Answer only from the supplied KB evidence. "
            "Thread summary and recalled memories are supplemental context for disambiguation and personalization only. "
            "If they conflict with KB evidence, trust the KB evidence. "
            "If evidence is insufficient, say so clearly and do not invent facts. "
            "For factual lookup questions, answer directly without extra background. "
            'Return strict JSON only: {"answer":"...","citations":["C1","C2"],"insufficient_reason":null}'
        )
        user_prompt = (
            f"{context_block}\n\n"
            f"Question: {answer_question}\n"
            f"Evidence grade: {evidence_grade}\n\n"
            "Available evidence:\n"
            + "\n\n".join(evidence_blocks)
        )

        if self.answer_token_callback is None:
            raw_text, answer_usage = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1200,
            )
        else:
            raw_text, answer_usage = self._stream_grounded_answer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        payload = self._extract_json_payload(raw_text)
        answer = str(payload.get("answer") or raw_text).strip()
        labels = [str(item) for item in payload.get("citations", []) if isinstance(item, str)]
        used_candidates = [
            candidate
            for index, candidate in enumerate(candidates[:6], start=1)
            if f"C{index}" in labels
        ] or candidates[: min(3, len(candidates))]
        answer = self._compress_answer_if_needed(
            question=answer_question,
            answer=answer,
            candidates=used_candidates,
        )

        token_usage["answer"] = answer_usage
        metrics["citation_count"] = len(used_candidates)
        return {
            "final_answer": answer,
            "citation_candidates": self._build_citation_payloads(used_candidates),
            "token_usage": token_usage,
            "metrics": metrics,
        }

    def _build_direct_prompt_message(self, state: AtlasAgentState) -> str:
        context_block = self._build_conversation_context_block(state)
        request_type = str(state.get("request_type") or "smalltalk")
        return f"Request type: {request_type}\n\n{context_block}\n\nUser question:\n{state['user_message']}"

    def _build_conversation_context_block(self, state: AtlasAgentState) -> str:
        parts = ["Conversation context:"]

        thread_summary = str(state.get("thread_summary") or "").strip()
        if thread_summary:
            parts.append(f"Thread summary:\n{thread_summary}")

        recent_context = self._format_recent_thread_messages(state)
        if recent_context:
            parts.append(f"Recent thread messages:\n{recent_context}")

        recalled = state.get("recalled_memories", [])
        if recalled:
            memory_lines = []
            for memory in recalled[:5]:
                if not isinstance(memory, dict):
                    continue
                title = str(memory.get("title") or "").strip() or "Untitled Memory"
                body = str(memory.get("summary_text") or memory.get("content_text") or "").strip()
                memory_type = str(memory.get("memory_type") or "memory")
                if body:
                    memory_lines.append(f"- [{memory_type}] {title}: {body[:220]}")
                else:
                    memory_lines.append(f"- [{memory_type}] {title}")
            if memory_lines:
                parts.append("Recalled memories:\n" + "\n".join(memory_lines))

        if len(parts) == 1:
            parts.append("No prior thread summary or long-term memory recalled.")

        return "\n\n".join(parts)

    def _format_recent_thread_messages(self, state: AtlasAgentState) -> str:
        prior_messages = self._get_prior_messages(state)
        if not prior_messages:
            return ""

        lines: list[str] = []
        for message in prior_messages[-4:]:
            role = str(message.get("role") or "").strip() or "user"
            content = " ".join(str(message.get("content_text") or "").split()).strip()
            if not content:
                continue
            lines.append(f"{role}: {content[:240]}")
        return "\n".join(lines)

    def _build_memory_write_ack(self, state: AtlasAgentState) -> str | None:
        extracted = MemoryService._extract_explicit_memory_text(str(state.get("user_message") or ""))
        if not extracted:
            return None
        return f"已记住：{extracted}"

    def _build_thread_context_summary_answer(self, state: AtlasAgentState) -> str | None:
        request_type = str(state.get("request_type") or "").strip()
        question = str(state.get("user_message") or "").strip()
        if request_type != "thread_context":
            return None
        if not self._is_thread_context_request(question):
            return None

        facts = self._collect_thread_context_facts(state)
        if not facts:
            return "当前线程里还没有足够的项目背景信息。请先在同一线程告诉我项目背景，再让我总结。"

        rendered_facts: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            rendered = self._normalize_thread_context_fact_for_summary(fact)
            if not rendered:
                continue
            lowered = rendered.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            rendered_facts.append(rendered)

        if not rendered_facts:
            return "当前线程里还没有足够的项目背景信息。请先在同一线程告诉我项目背景，再让我总结。"
        return self._rewrite_thread_context_summary(question=question, facts=rendered_facts[:6])

    def _build_thread_context_ack(self, state: AtlasAgentState) -> str | None:
        request_type = str(state.get("request_type") or "").strip()
        question = str(state.get("user_message") or "").strip()
        if request_type != "context_update":
            return None
        if not self._is_background_context_update(question):
            return None
        return "已记录当前线程背景。后续我会按这个项目上下文继续回答。"

    def _collect_thread_context_facts(self, state: AtlasAgentState) -> list[str]:
        facts: list[str] = []
        seen: set[str] = set()

        thread_summary = str(state.get("thread_summary") or "").strip()
        if thread_summary:
            for raw_line in thread_summary.splitlines():
                candidate = raw_line.strip().lstrip("-• ").strip()
                normalized = " ".join(candidate.split())
                if not normalized:
                    continue

                if normalized.startswith("User focus:"):
                    normalized = normalized.split(":", 1)[1].strip()
                elif normalized.startswith("Assistant conclusions:"):
                    continue

                for fragment in re.split(r"\s*\|\s*", normalized):
                    compact = fragment.strip().strip("。；;")
                    if not compact:
                        continue
                    lowered = compact.lower()
                    if lowered in seen:
                        continue
                    seen.add(lowered)
                    facts.append(compact)

        prior_messages = self._get_prior_messages(state)
        for message in prior_messages[-6:]:
            if str(message.get("role") or "").strip() != "user":
                continue
            content = " ".join(str(message.get("content_text") or "").split()).strip()
            if not content or self._looks_like_direct_question(content):
                continue

            segments = re.split(r"[。；;]\s*", content)
            for segment in segments:
                normalized = " ".join(segment.split()).strip().strip("。；;")
                if not normalized:
                    continue
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                facts.append(normalized)

        return facts

    def _normalize_thread_context_fact_for_summary(self, fact: str) -> str:
        normalized = " ".join(fact.split()).strip().strip("。；;")
        if not normalized:
            return ""

        replacements = (
            (r"^我的项目(是|为)", r"项目\1"),
            (r"^我们项目(是|为)", r"项目\1"),
            (r"^当前项目(是|为)", r"项目\1"),
            (r"^我的技术栈", "技术栈"),
            (r"^我的部署", "部署"),
            (r"^我的模型", "模型"),
            (r"^我的偏好", "偏好"),
            (r"^我偏好", "偏好"),
            (r"^我当前最关注", "当前最关注"),
        )
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized)
        return normalized

    def _build_focused_memory_answer(self, state: AtlasAgentState) -> str | None:
        question = str(state.get("user_message") or "").strip()
        if not self._is_focused_memory_question(question):
            return None

        recalled = [item for item in state.get("recalled_memories", []) if isinstance(item, dict)]
        if not recalled:
            return None

        focus_terms = self._extract_memory_focus_terms(question)
        prioritized = sorted(
            recalled,
            key=lambda item: 0 if str(item.get("memory_type") or "") in {"semantic", "procedural"} else 1,
        )

        facts: list[str] = []
        seen: set[str] = set()
        for memory in prioritized:
            fact = self._extract_focused_memory_fact(memory=memory, focus_terms=focus_terms)
            if not fact:
                continue
            lowered = fact.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            facts.append(fact)
            if len(facts) >= 2:
                break

        if not facts:
            return None
        return self._rewrite_focused_memory_answer(question=question, facts=facts)

    def _build_event_memory_answer(self, state: AtlasAgentState) -> str | None:
        request_type = str(state.get("request_type") or "").strip()
        question = str(state.get("user_message") or "").strip()
        if request_type != "event_memory":
            return None
        if not self._is_event_memory_request(question):
            return None

        transcript_lines = self._collect_recent_event_evidence(state)
        episodic_lines = self._collect_recalled_event_memories(state=state, question=question)
        if not transcript_lines and not episodic_lines:
            return "我目前还没有检索到与这一轮新增内容相关的明确事件记忆。请在同一线程里先完成相关讨论，或明确指出要回顾的那一轮。"
        return self._rewrite_event_memory_answer(
            question=question,
            transcript_lines=transcript_lines[:6],
            episodic_lines=episodic_lines[:4],
        )

    def _collect_recent_event_evidence(self, state: AtlasAgentState) -> list[str]:
        prior_messages = self._get_prior_messages(state)
        if not prior_messages:
            return []

        selected: list[str] = []
        seen: set[str] = set()
        recent_messages = prior_messages[-8:]
        for message in recent_messages:
            role = str(message.get("role") or "").strip() or "user"
            content = " ".join(str(message.get("content_text") or "").split()).strip()
            if not content:
                continue
            if not self._looks_like_event_related_message(content, role=role):
                continue
            rendered = f"{role}: {content[:320]}"
            lowered = rendered.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            selected.append(rendered)

        if selected:
            return selected

        fallback_lines: list[str] = []
        for message in recent_messages[-6:]:
            role = str(message.get("role") or "").strip() or "user"
            content = " ".join(str(message.get("content_text") or "").split()).strip()
            if not content:
                continue
            fallback_lines.append(f"{role}: {content[:320]}")
        return fallback_lines

    def _collect_recalled_event_memories(self, *, state: AtlasAgentState, question: str) -> list[str]:
        recalled = [item for item in state.get("recalled_memories", []) if isinstance(item, dict)]
        if not recalled:
            return []

        lines: list[str] = []
        seen: set[str] = set()
        for memory in recalled:
            if str(memory.get("memory_type") or "").strip() != "episodic":
                continue
            line = self._normalize_recalled_memory_line(memory=memory, question=question)
            if not line:
                continue
            if not self._looks_like_event_related_message(line, role="assistant"):
                continue
            lowered = line.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            lines.append(line)
        return lines

    def _extract_focused_memory_fact(self, *, memory: dict[str, Any], focus_terms: list[str]) -> str | None:
        body = self._normalize_recalled_memory_line(memory=memory, question="")
        if not body:
            return None

        best_segment = ""
        best_score = 0
        segments = [part.strip() for part in re.split(r"[。；;\n]+", body) if part.strip()]
        if not segments:
            segments = [body]

        for segment in segments:
            lowered = segment.lower()
            score = sum(1 for term in focus_terms if term and term in lowered)
            if score <= 0:
                continue
            if score > best_score:
                best_score = score
                best_segment = segment.strip().strip("。；;")

        if best_segment:
            return best_segment
        if self._memory_line_matches_focus_terms(body, focus_terms):
            return body.strip().strip("。；;")
        return None

    def _rewrite_focused_memory_answer(self, *, question: str, facts: list[str]) -> str:
        fallback = facts[0].rstrip("。；;") + "。"
        if self.llm_client is None:
            return fallback

        system_prompt = (
            "You answer user questions from long-term memory facts. "
            "Use only the supplied facts. Do not add any unrelated remembered details. "
            "If one fact fully answers the question, answer with that only. "
            "Keep the Chinese answer concise and natural."
        )
        user_prompt = (
            f"User question: {question}\n"
            "Relevant memory facts:\n"
            + "\n".join(f"- {fact}" for fact in facts)
            + "\n\nAnswer:"
        )
        try:
            if self.answer_token_callback is None:
                answer, _usage = self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=180,
                )
                normalized = " ".join(answer.split()).strip()
                return normalized or fallback

            answer_parts: list[str] = []
            for event in self.llm_client.chat_stream(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=180,
                cancel_checker=self.cancel_checker,
            ):
                self._raise_if_cancelled()
                if event.event == "delta" and event.text:
                    answer_parts.append(event.text)
                    self._emit_answer_token(event.text)
            normalized = " ".join("".join(answer_parts).split()).strip()
            return normalized or fallback
        except Exception:
            return fallback

    def _rewrite_thread_context_summary(self, *, question: str, facts: list[str]) -> str:
        fallback_answer = "你当前项目的关键背景是：" + "；".join(facts) + "。"
        if self.llm_client is None:
            return fallback_answer

        system_prompt = (
            "You rewrite structured project facts into natural Chinese. "
            "Use only the supplied facts. Do not add any unstated architecture, storage, memory, model, or system details. "
            "Prefer second-person or neutral phrasing. Keep the answer concise and fluent in 1-3 sentences."
        )
        user_prompt = (
            f"User question: {question}\n"
            "Known thread facts:\n"
            + "\n".join(f"- {fact}" for fact in facts)
            + "\n\nAnswer:"
        )
        try:
            if self.answer_token_callback is None:
                answer, _usage = self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=220,
                )
                normalized = " ".join(answer.split()).strip()
                return normalized or fallback_answer

            answer_parts: list[str] = []
            for event in self.llm_client.chat_stream(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=220,
                cancel_checker=self.cancel_checker,
            ):
                self._raise_if_cancelled()
                if event.event == "delta" and event.text:
                    answer_parts.append(event.text)
                    self._emit_answer_token(event.text)
            normalized = " ".join("".join(answer_parts).split()).strip()
            return normalized or fallback_answer
        except Exception:
            return fallback_answer

    def _rewrite_event_memory_answer(
        self,
        *,
        question: str,
        transcript_lines: list[str],
        episodic_lines: list[str],
    ) -> str:
        evidence_lines = [f"- {line}" for line in transcript_lines]
        if episodic_lines:
            evidence_lines.extend(f"- {line}" for line in episodic_lines)
        fallback_source = episodic_lines or transcript_lines
        fallback = "我目前能确认的这一轮关键信息是：\n" + "\n".join(
            f"{index}. {line.split(': ', 1)[-1].strip().rstrip('。')}" for index, line in enumerate(fallback_source[:3], start=1)
        )
        if self.llm_client is None:
            return fallback

        system_prompt = (
            "You answer event-recall questions from supplied conversation evidence only. "
            "Use only the provided recent thread transcript and episodic memories. "
            "Focus on what was newly added, completed, or changed in the referenced round. "
            "Do not add any unrelated architecture, model, storage, or memory details unless they are explicitly present in the evidence. "
            "Respond in concise natural Chinese, ideally as 2-3 short bullet points or numbered points when the user asks for multiple items."
        )
        user_prompt = (
            f"User question: {question}\n"
            "Event evidence:\n"
            + "\n".join(evidence_lines)
            + "\n\nAnswer:"
        )
        try:
            if self.answer_token_callback is None:
                answer, _usage = self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=260,
                )
                normalized = " ".join(answer.split()).strip()
                return normalized or fallback

            answer_parts: list[str] = []
            for event in self.llm_client.chat_stream(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=260,
                cancel_checker=self.cancel_checker,
            ):
                self._raise_if_cancelled()
                if event.event == "delta" and event.text:
                    answer_parts.append(event.text)
                    self._emit_answer_token(event.text)
            normalized = " ".join("".join(answer_parts).split()).strip()
            return normalized or fallback
        except Exception:
            return fallback

    def _build_memory_recall_answer(self, state: AtlasAgentState) -> str | None:
        question = str(state.get("user_message") or "").strip()
        if not self._is_memory_recall_request(question):
            return None

        recalled = [item for item in state.get("recalled_memories", []) if isinstance(item, dict)]
        if recalled:
            focus_terms = self._extract_memory_focus_terms(question)
            lines: list[str] = []
            fallback_lines: list[str] = []
            prioritized = sorted(
                recalled,
                key=lambda item: 0 if str(item.get("memory_type") or "") in {"semantic", "procedural"} else 1,
            )
            for memory in prioritized:
                body = self._normalize_recalled_memory_line(memory=memory, question=question)
                if not body:
                    continue
                target_list = lines if self._memory_line_matches_focus_terms(body, focus_terms) else fallback_lines
                if body not in target_list:
                    target_list.append(body[:120])
                if len(lines) >= 3:
                    break
            if not lines:
                lines = fallback_lines[:3]
            if lines:
                return "我当前记住的要点是：\n" + "\n".join(
                    f"{index}. {line}" for index, line in enumerate(lines, start=1)
                )

        thread_summary = str(state.get("thread_summary") or "").strip()
        if thread_summary:
            return f"我目前能从当前线程背景中确认这些要点：\n{thread_summary}"

        return "我目前还没有检索到明确的长期记忆。"

    def _normalize_recalled_memory_line(self, *, memory: dict[str, Any], question: str) -> str | None:
        body = str(memory.get("summary_text") or memory.get("content_text") or "").strip()
        if not body:
            return None

        normalized = " ".join(body.split()).strip()
        noisy_prefixes = (
            "根据当前知识库中的证据",
            "当前没有足够信息生成最终回答",
            "我当前记住的要点是",
            "我目前能从当前线程背景中确认这些要点",
            "我目前还没有检索到明确的长期记忆",
        )
        if any(normalized.startswith(prefix) for prefix in noisy_prefixes):
            return None

        if normalized.startswith(("已记住：", "已记住:")):
            normalized = normalized.split("：", 1)[-1] if "：" in normalized else normalized.split(":", 1)[-1]
            normalized = normalized.strip()

        if normalized.startswith("Q:") and "\nA:" in body:
            normalized = body.split("\nA:", 1)[1].strip()
            normalized = " ".join(normalized.split()).strip()

        if not normalized:
            return None
        if normalized == question:
            return None
        if normalized in {"了我的什么回答偏好？", "了我的什么回答偏好?"}:
            return None
        if normalized.endswith(("？", "?")) and "偏好" in normalized:
            return None

        return normalized

    def _extract_memory_focus_terms(self, question: str) -> list[str]:
        normalized = " ".join(question.lower().split())
        generic_phrases = (
            "你记住了我的",
            "你记住了",
            "你还记得我的",
            "你还记得",
            "我之前说过的",
            "我之前说过",
            "我的",
            "什么",
            "哪些",
            "吗",
            "么",
            "呢",
            "是什么",
            "是啥",
            "请问",
        )
        for phrase in generic_phrases:
            normalized = normalized.replace(phrase, " ")

        terms: list[str] = []
        ascii_terms = re.findall(r"[a-z][a-z0-9._-]*", normalized)
        keyword_terms = [
            term
            for term in (
                "偏好",
                "回答",
                "中文",
                "结论",
                "原因",
                "部署",
                "部署方式",
                "第一版",
                "模型",
                "技术栈",
                "项目",
                "后端",
                "前端",
                "数据库",
                "redis",
                "postgresql",
                "fastapi",
                "react",
                "邮箱",
                "能力",
                "规则",
                "引用",
                "memory",
            )
            if term in question
        ]
        for term in [*ascii_terms, *keyword_terms]:
            clean = term.strip().lower()
            if clean and clean not in terms:
                terms.append(clean)
        return terms

    def _is_focused_memory_question(self, question: str) -> bool:
        if not self._looks_like_direct_question(question):
            return False
        focus_terms = self._extract_memory_focus_terms(question)
        return any(
            term in focus_terms
            for term in (
                "部署",
                "部署方式",
                "第一版",
                "模型",
                "技术栈",
                "项目",
                "后端",
                "前端",
                "数据库",
                "redis",
                "postgresql",
                "fastapi",
                "react",
                "偏好",
            )
        )

    @staticmethod
    def _memory_line_matches_focus_terms(line: str, focus_terms: list[str]) -> bool:
        if not focus_terms:
            return True
        lowered = line.lower()
        return any(term in lowered for term in focus_terms)

    def _stream_direct_answer(self, *, user_message: str) -> tuple[str, dict]:
        answer_parts: list[str] = []
        usage: dict[str, Any] = {}

        for event in self.llm_client.chat_stream(
            messages=[
                {"role": "system", "content": "You are a concise assistant. Answer the user directly."},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=800,
            cancel_checker=self.cancel_checker,
        ):
            self._raise_if_cancelled()
            if event.event == "delta" and event.text:
                answer_parts.append(event.text)
                self._emit_answer_token(event.text)
            elif event.event == "usage" and event.usage:
                usage = event.usage

        return "".join(answer_parts).strip(), usage

    def _stream_grounded_answer(self, *, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        raw_parts: list[str] = []
        emitted_answer = ""
        usage: dict[str, Any] = {}

        for event in self.llm_client.chat_stream(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
            cancel_checker=self.cancel_checker,
        ):
            self._raise_if_cancelled()
            if event.event == "delta" and event.text:
                raw_parts.append(event.text)
                partial_answer = self._extract_partial_answer_text("".join(raw_parts))
                if len(partial_answer) > len(emitted_answer):
                    delta = partial_answer[len(emitted_answer) :]
                    emitted_answer = partial_answer
                    self._emit_answer_token(delta)
            elif event.event == "usage" and event.usage:
                usage = event.usage

        return "".join(raw_parts), usage

    def _emit_answer_token(self, text: str) -> None:
        if text and self.answer_token_callback is not None:
            self.answer_token_callback(text)

    def _raise_if_cancelled(self) -> None:
        cancel_checker = getattr(self, "cancel_checker", None)
        if cancel_checker is not None and cancel_checker():
            raise RunCancelledError("Run cancelled by user.")

    def _build_citation_payloads(self, candidates: list[Any]) -> list[dict[str, Any]]:
        payloads = []
        for ordinal, candidate in enumerate(candidates, start=1):
            payloads.append(
                {
                    "chunk_id": candidate.chunk.id,
                    "document_id": candidate.document_id,
                    "citation_label": f"C{ordinal}",
                    "chunk_level": candidate.chunk.chunk_level,
                    "page_no": candidate.chunk.page_no,
                    "page_start": candidate.chunk.page_start,
                    "page_end": candidate.chunk.page_end,
                    "section_path": [str(item) for item in candidate.chunk.section_path],
                    "snippet": candidate.chunk.raw_text[:240],
                }
            )
        return payloads

    def _extract_json_payload(self, text: str) -> dict[str, Any]:
        try:
            return orjson.loads(text)
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return orjson.loads(match.group(0))
            except Exception:
                return {}
        return {}

    def build_citation_reads(self, citation_payloads: list[dict[str, Any]]) -> list[CitationRead]:
        """将图生成的引用载荷转换为响应模型。"""

        return [
            CitationRead(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                citation_label=item["citation_label"],
                chunk_level=item["chunk_level"],
                page_no=item["page_no"],
                page_start=item["page_start"],
                page_end=item["page_end"],
                section_path=item["section_path"],
                snippet=item["snippet"],
            )
            for item in citation_payloads
        ]

    def _compress_answer_if_needed(self, *, question: str, answer: str, candidates: list[Any]) -> str:
        if not self._is_precise_lookup(question):
            return answer
        if self._is_concise_answer(answer):
            return answer

        evidence_line = self._extract_best_evidence_line(question=question, candidates=candidates)
        if not evidence_line:
            return answer
        return evidence_line

    def _is_precise_lookup(self, question: str) -> bool:
        precise_markers = ("多少", "上限", "是否", "能否", "可否", "可以", "允许", "多久", "几天", "几次", "默认", "最多")
        broad_markers = ("哪些", "分别", "模块", "列出", "概述", "介绍")
        return any(marker in question for marker in precise_markers) and not any(
            marker in question for marker in broad_markers
        )

    def _is_concise_answer(self, answer: str) -> bool:
        lines = [line.strip() for line in answer.splitlines() if line.strip()]
        if len(lines) > 2:
            return False
        if len(answer) > 72 and ("- " in answer or "\n" in answer):
            return False
        return True

    def _extract_best_evidence_line(self, *, question: str, candidates: list[Any]) -> str | None:
        fragments = self.retrieval_service._extract_query_fragments(question)
        best_line = None
        best_score = 0.0

        for candidate in candidates[:4]:
            section_tail = str(candidate.chunk.section_path[-1]).strip().lower() if candidate.chunk.section_path else ""
            for raw_line in candidate.chunk.raw_text.splitlines():
                line = raw_line.strip().lstrip("-•* ").strip()
                if len(line) < 2:
                    continue
                if line.lower() == section_tail:
                    continue

                normalized_line = line.lower()
                score = 0.0
                for fragment in fragments:
                    if fragment in normalized_line:
                        score += 1.2 if len(fragment) >= 4 else 0.6
                if "：" in line or ":" in line:
                    score += 0.3
                if any(char.isdigit() for char in line):
                    score += 0.3

                if score > best_score:
                    best_score = score
                    best_line = line

        if not best_line:
            return None

        if "：" in best_line or ":" in best_line:
            key, value = re.split(r"[:：]", best_line, maxsplit=1)
            key = key.strip()
            value = value.strip()
            if key and value:
                return f"{key}是 {value}。"

        return best_line.rstrip("。；;") + "。"

    def _extract_partial_answer_text(self, text: str) -> str:
        """从不完整的 JSON 流中尽量提取当前 `answer` 字段。"""

        answer_key_match = re.search(r'"answer"\s*:\s*"', text)
        if answer_key_match is None:
            return ""

        index = answer_key_match.end()
        chars: list[str] = []
        while index < len(text):
            char = text[index]
            if char == '"':
                break
            if char != "\\":
                chars.append(char)
                index += 1
                continue

            index += 1
            if index >= len(text):
                break

            escaped = text[index]
            if escaped == "n":
                chars.append("\n")
                index += 1
                continue
            if escaped == "t":
                chars.append("\t")
                index += 1
                continue
            if escaped in {'"', "\\", "/"}:
                chars.append(escaped)
                index += 1
                continue
            if escaped == "u":
                if index + 4 >= len(text):
                    break
                hex_value = text[index + 1 : index + 5]
                if re.fullmatch(r"[0-9a-fA-F]{4}", hex_value):
                    chars.append(chr(int(hex_value, 16)))
                    index += 5
                    continue
                break
            chars.append(escaped)
            index += 1

        return "".join(chars)

    @staticmethod
    def _extract_thread_summary(thread: Thread) -> str | None:
        metadata = thread.metadata_json
        if not isinstance(metadata, dict):
            return None

        summary = metadata.get("thread_summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return None

    def _coerce_uuid_list(self, values: list[Any]) -> list[UUID]:
        coerced: list[UUID] = []
        for value in values:
            try:
                coerced.append(UUID(str(value)))
            except (TypeError, ValueError):
                continue
        return coerced

    def _get_prior_messages(self, state: AtlasAgentState) -> list[dict[str, Any]]:
        messages = [item for item in state.get("messages", []) if isinstance(item, dict)]
        if not messages:
            return []

        last_message = messages[-1]
        if (
            last_message.get("role") == "user"
            and str(last_message.get("content_text") or "").strip() == str(state.get("user_message") or "").strip()
        ):
            return messages[:-1]
        return messages

    def _should_rewrite_follow_up(self, question: str, prior_messages: list[dict[str, Any]]) -> bool:
        if not prior_messages:
            return False

        lowered = question.strip().lower()
        if len(lowered) <= 18:
            return True

        follow_up_prefixes = (
            "那",
            "那如果",
            "如果是",
            "那它",
            "它",
            "这个",
            "这些",
            "那些",
            "为什么",
            "为啥",
            "那为什么",
            "怎么",
            "如何",
            "那呢",
        )
        if any(lowered.startswith(prefix) for prefix in follow_up_prefixes):
            return True

        follow_up_markers = ("呢", "还会", "也可以", "同样", "那", "它", "该限制", "这种情况")
        if any(marker in question for marker in follow_up_markers) and len(question) <= 32:
            return True

        return False

    def _rewrite_follow_up_with_context(
        self,
        *,
        current_question: str,
        prior_messages: list[dict[str, Any]],
        thread_summary: str | None = None,
    ) -> str:
        heuristic_rewrite = self._rewrite_follow_up_by_pattern(
            current_question=current_question,
            prior_messages=prior_messages,
        )
        if heuristic_rewrite:
            return heuristic_rewrite

        transcript = []
        for item in prior_messages:
            if item.get("role") != "user":
                continue
            content = str(item.get("content_text") or "").strip()
            if content:
                transcript.append(content)
        transcript = transcript[-3:]

        if not transcript:
            return current_question

        if self.llm_client is not None:
            prompt = (
                "Rewrite the latest user question into a standalone Chinese question for retrieval.\n"
                "Use prior conversation only when needed.\n"
                "Preserve exact product names, roles, limits, dates, and metrics.\n"
                "If the latest question is already standalone, return it unchanged.\n"
                "Return only the rewritten question."
            )
            chat_messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        (f"Thread summary:\n{thread_summary}\n\n" if thread_summary else "")
                        + (
                        "Earlier user questions:\n"
                        + "\n".join(transcript)
                        + f"\nLatest user question: {current_question}\nStandalone question:"
                        )
                    ),
                },
            ]
            try:
                rewritten, _usage = self.llm_client.chat(chat_messages, temperature=0.0, max_tokens=120)
                normalized = rewritten.strip().strip('"').strip()
                if normalized:
                    return normalized.splitlines()[0].strip()
            except Exception:
                pass

        return self._fallback_rewrite_follow_up(current_question=current_question, prior_messages=prior_messages)

    def _rewrite_follow_up_by_pattern(self, *, current_question: str, prior_messages: list[dict[str, Any]]) -> str | None:
        last_user_question = next(
            (
                str(item.get("content_text") or "").strip()
                for item in reversed(prior_messages)
                if item.get("role") == "user" and str(item.get("content_text") or "").strip()
            ),
            "",
        )
        if not last_user_question:
            return None

        known_targets = ("Starter", "Business", "Enterprise", "Owner", "Admin", "Editor", "Viewer", "Sev-1", "Sev-2", "Sev-3", "Sev-4")
        lower_question = current_question.lower()
        target = next((item for item in known_targets if item.lower() in lower_question), None)
        if target is None:
            return None
        if "如果是" in current_question or current_question.strip().startswith("那"):
            return self._contextualize_question_with_target(last_user_question=last_user_question, target=target)
        return None

    def _contextualize_question_with_target(self, *, last_user_question: str, target: str) -> str:
        base = last_user_question.rstrip("？?。；; ")
        return f"{base} ({target})"

    def _fallback_rewrite_follow_up(self, *, current_question: str, prior_messages: list[dict[str, Any]]) -> str:
        last_user_question = next(
            (
                str(item.get("content_text") or "").strip()
                for item in reversed(prior_messages)
                if item.get("role") == "user" and str(item.get("content_text") or "").strip()
            ),
            "",
        )
        if not last_user_question:
            return current_question

        if current_question in {"为什么？", "为什么", "为啥？", "为啥"}:
            return f"{last_user_question} 为什么？"

        return f"基于上一个问题“{last_user_question}”，{current_question}"

    def _decide_request_routing(self, state: AtlasAgentState) -> tuple[str, str]:
        question = str(state.get("user_message") or "").strip()
        requested_mode = str(state.get("requested_mode") or state.get("route_target") or "").strip().lower()
        has_selected_docs = bool(state.get("attached_document_ids") or state.get("pinned_document_ids"))
        workspace_id = state.get("workspace_id")
        workspace_has_docs = self._workspace_has_documents(workspace_id) if isinstance(workspace_id, UUID) else False
        looks_like_kb_query = self._looks_like_kb_query(question)

        if self._is_memory_intent(question):
            return "memory", "direct"
        if self._is_thread_context_request(question):
            return "thread_context", "direct"
        if self._is_background_context_update(question):
            return "context_update", "direct"
        if self._is_event_memory_request(question):
            return "event_memory", "direct"
        if requested_mode == "direct":
            return "smalltalk", "direct"
        if looks_like_kb_query and (has_selected_docs or workspace_has_docs):
            return "kb_qa", "rag"
        if has_selected_docs and requested_mode in {"rag", "hybrid"}:
            return "kb_qa", "rag"
        if requested_mode in {"rag", "hybrid"} and workspace_has_docs:
            return "kb_qa", "rag"
        return "smalltalk", "direct"

    def _workspace_has_documents(self, workspace_id: UUID) -> bool:
        if getattr(self, "db", None) is None:
            return False
        stmt = (
            select(Document.id)
            .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def _is_thread_context_request(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        direct_context_markers = (
            "关键背景",
            "项目背景",
            "当前背景",
            "我刚才说过",
            "根据我们刚才",
            "基于我们的对话",
            "这个线程",
            "当前线程",
            "这段对话",
            "总结一下我当前",
            "总结一下我们当前",
            "请总结一下我当前",
            "请总结一下我们当前",
        )
        if any(marker in normalized for marker in direct_context_markers):
            return True

        summary_markers = ("总结一下", "总结下", "概括一下", "概括下", "梳理一下", "梳理下")
        context_targets = ("项目", "背景", "对话", "线程", "现状", "技术栈", "方案")
        if any(marker in normalized for marker in summary_markers) and any(
            target in normalized for target in context_targets
        ):
            return True

        question_targets = (
            "我的项目",
            "当前项目",
            "我们当前",
            "我的技术栈",
            "我的部署",
            "我的模型",
            "我的偏好",
        )
        return self._looks_like_direct_question(question) and any(target in normalized for target in question_targets)

    def _is_background_context_update(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        if not normalized or self._looks_like_direct_question(question):
            return False
        if self._is_thread_context_request(question):
            return False

        declaration_markers = (
            "我的项目",
            "我们项目",
            "当前项目",
            "后端",
            "前端",
            "数据库",
            "技术栈",
            "模型",
            "部署",
            "偏好",
            "我当前最关注",
            "当前最关注",
            "我们的方案",
            "第一版",
            "本地存储",
            "postgresql",
            "fastapi",
            "react",
            "redis",
            "langgraph",
            "agentic rag",
            "memory",
        )
        return any(marker in normalized for marker in declaration_markers)

    def _is_event_memory_request(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        if not normalized:
            return False

        direct_markers = (
            "这一轮新增",
            "上一轮新增",
            "本轮新增",
            "刚才新增",
            "上一轮做了什么",
            "这一轮做了什么",
            "刚才做了什么",
            "上一轮改了什么",
            "这一轮改了什么",
            "刚才改了什么",
            "上一轮完成了什么",
            "这一轮完成了什么",
            "刚才完成了什么",
            "新增的 3 个核心能力",
            "新增的三个核心能力",
            "新增了哪些核心能力",
        )
        if any(marker in normalized for marker in direct_markers):
            return True

        round_markers = ("这一轮", "上一轮", "本轮", "刚才", "刚刚", "上一步", "这一步", "上次", "这次")
        action_markers = ("新增", "新增了", "做了什么", "改了什么", "完成了什么", "推进了什么", "核心能力", "核心改动")
        return any(marker in normalized for marker in round_markers) and any(
            marker in normalized for marker in action_markers
        )

    def _looks_like_direct_question(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        if not normalized:
            return False
        if normalized.endswith(("?", "？")):
            return True
        question_markers = (
            "什么",
            "哪些",
            "多少",
            "是否",
            "能否",
            "可以",
            "怎么",
            "如何",
            "为什么",
            "请问",
            "吗",
            "呢",
        )
        return any(marker in normalized for marker in question_markers)

    def _looks_like_kb_query(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        kb_markers = (
            "知识库",
            "文档",
            "根据文档",
            "引用",
            "citation",
            "chunk",
            "页码",
            "章节",
            "atlas",
            "starter",
            "business",
            "enterprise",
            "viewer",
            "owner",
            "editor",
            "套餐",
            "模块",
            "mcp",
            "工作区",
            "单文件",
            "上限",
            "导出引用",
            "high risk",
            "运行日志",
            "memory center",
        )
        return any(marker in normalized for marker in kb_markers)

    def _is_memory_intent(self, question: str) -> bool:
        return self._is_explicit_memory_write(question) or self._is_memory_recall_request(question)

    def _is_explicit_memory_write(self, question: str) -> bool:
        return MemoryService._extract_explicit_memory_text(question) is not None

    def _is_memory_recall_request(self, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        markers = (
            "你记住了",
            "你还记得",
            "我之前说过",
            "我的偏好",
            "我的回答偏好",
            "记忆里",
            "你记得什么",
            "你都记了什么",
            "还记得我",
        )
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _looks_like_event_related_message(text: str, *, role: str) -> bool:
        normalized = " ".join(text.lower().split())
        if not normalized:
            return False

        noisy_prefixes = (
            "已记录当前线程背景",
            "已记住：",
            "根据当前知识库中的证据",
            "当前线程里还没有足够的项目背景信息",
        )
        if any(normalized.startswith(prefix) for prefix in noisy_prefixes):
            return False

        common_markers = (
            "新增",
            "已完成",
            "完成",
            "补了",
            "支持",
            "接上",
            "落地",
            "上线",
            "修复",
            "改了",
            "优化",
            "阶段",
            "memory",
            "trace",
            "stream",
            "retry",
            "压缩",
            "多轮",
        )
        if any(marker in normalized for marker in common_markers):
            return True

        if role == "assistant":
            return normalized.startswith(("这一轮", "这一步", "本轮", "当前", "现在"))
        return normalized.startswith(("继续", "请继续", "请总结", "帮我总结"))
