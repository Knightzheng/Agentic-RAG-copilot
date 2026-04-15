"""Regression tests for Milestone 4 orchestration primitives."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.chat.stream_control import RunCancelledError
from app.services.chat.stream_control import StreamCancellationRegistry
from app.services.orchestration.graph import AtlasSupervisorGraphService
from app.services.orchestration.tracing import RunTraceRecorder
from app.services.retrieval.service import RetrievedCandidate


def test_classify_request_prefers_rag_for_kb_questions_with_selected_documents() -> None:
    """Selected documents should still trigger RAG when the user is clearly asking a KB question."""

    service = object.__new__(AtlasSupervisorGraphService)

    rag_result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "Business 套餐的单文件大小上限是多少？",
            "attached_document_ids": [uuid4()],
            "pinned_document_ids": [],
        }
    )
    direct_result = service._classify_request(  # type: ignore[attr-defined]
        {
            "attached_document_ids": [],
            "pinned_document_ids": [],
            "route_target": "direct",
        }
    )

    assert rag_result == {"request_type": "kb_qa", "route_target": "rag"}
    assert direct_result == {"request_type": "smalltalk", "route_target": "direct"}


def test_classify_request_does_not_force_rag_for_generic_smalltalk_with_selected_documents() -> None:
    """Selecting documents should not force every conversational turn onto the RAG path."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "你好，先打个招呼。",
            "requested_mode": "auto",
            "attached_document_ids": [uuid4()],
            "pinned_document_ids": [],
        }
    )

    assert result == {"request_type": "smalltalk", "route_target": "direct"}


def test_classify_request_routes_explicit_memory_write_to_direct_even_when_rag_is_forced() -> None:
    """Memory-write instructions should bypass forced RAG and use direct handling."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "请记住：我偏好中文回答，先给结论再给原因。",
            "route_target": "rag",
            "attached_document_ids": [],
            "pinned_document_ids": [],
        }
    )

    assert result == {"request_type": "memory", "route_target": "direct"}


def test_classify_request_routes_thread_context_questions_to_direct_even_with_documents() -> None:
    """Current-thread project summary requests should stay on direct/context path."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景",
            "requested_mode": "auto",
            "attached_document_ids": [uuid4()],
            "pinned_document_ids": [],
        }
    )

    assert result == {"request_type": "thread_context", "route_target": "direct"}


def test_classify_request_routes_background_context_updates_to_direct_even_with_documents() -> None:
    """Declarative project background updates should stay on the direct path even when docs are selected."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "后端是 FastAPI，前端是 React，数据库是 PostgreSQL。",
            "requested_mode": "auto",
            "attached_document_ids": [uuid4()],
            "pinned_document_ids": [],
        }
    )

    assert result == {"request_type": "context_update", "route_target": "direct"}


def test_classify_request_routes_event_memory_questions_to_direct() -> None:
    """Round-recap questions should use the dedicated event-memory direct path."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._classify_request(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我们这一轮新增的 3 个核心能力。",
            "requested_mode": "auto",
            "attached_document_ids": [uuid4()],
            "pinned_document_ids": [],
        }
    )

    assert result == {"request_type": "event_memory", "route_target": "direct"}


def test_invoke_direct_answer_acknowledges_memory_write_without_llm() -> None:
    """Explicit memory writes should return a deterministic acknowledgement."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请记住：我偏好中文回答，先给结论再给原因。",
            "recalled_memories": [],
            "thread_summary": None,
        }
    )

    assert result["final_answer"] == "已记住：我偏好中文回答，先给结论再给原因"
    assert result["metrics"]["pipeline"] == "direct"


def test_invoke_direct_answer_acknowledges_background_context_without_llm() -> None:
    """Project-background declarations should return a stable acknowledgement instead of hallucinated content."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "我的项目是 Agentic RAG，后端是 FastAPI。",
            "request_type": "context_update",
            "recalled_memories": [],
            "thread_summary": None,
        }
    )

    assert result["final_answer"] == "已记录当前线程背景。后续我会按这个项目上下文继续回答。"
    assert result["metrics"]["pipeline"] == "direct"


def test_invoke_direct_answer_summarizes_thread_context_without_llm() -> None:
    """Thread-context summary requests should summarize prior user background instead of returning the update ack."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景",
            "request_type": "thread_context",
            "messages": [
                {"role": "user", "content_text": "我的项目是 Agentic RAG。后端是 FastAPI。前端是 React。"},
                {"role": "assistant", "content_text": "已记录当前线程背景。"},
            ],
            "recalled_memories": [],
            "thread_summary": None,
        }
    )

    assert "Agentic RAG" in result["final_answer"]
    assert "FastAPI" in result["final_answer"]
    assert "React" in result["final_answer"]
    assert "项目是 Agentic RAG" in result["final_answer"]
    assert "我的项目是 Agentic RAG" not in result["final_answer"]
    assert "已记录当前线程背景" not in result["final_answer"]


def test_invoke_direct_answer_refuses_thread_summary_without_same_thread_context() -> None:
    """Thread-context summary requests should not invent project background from unrelated memory."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景",
            "request_type": "thread_context",
            "messages": [],
            "recalled_memories": [
                {"memory_type": "semantic", "summary_text": "系统默认保留最近 40 条消息作为 Working Memory"}
            ],
            "thread_summary": None,
        }
    )

    assert result["final_answer"] == "当前线程里还没有足够的项目背景信息。请先在同一线程告诉我项目背景，再让我总结。"


def test_thread_context_summary_uses_only_thread_facts_for_llm_rewrite() -> None:
    """LLM rewrite for thread summaries should only see extracted thread facts, not recalled memory noise."""

    captured: dict[str, str] = {}

    class FakeLLM:
        def chat(self, messages, temperature=0.0, max_tokens=220):
            captured["prompt"] = messages[-1]["content"]
            return ("你的项目是 Agentic RAG，后端使用 FastAPI，前端为 React。", {})

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = FakeLLM()
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景",
            "request_type": "thread_context",
            "messages": [
                {"role": "user", "content_text": "我的项目是 Agentic RAG。后端是 FastAPI。前端是 React。"},
                {"role": "assistant", "content_text": "已记录当前线程背景。"},
            ],
            "recalled_memories": [
                {"memory_type": "semantic", "summary_text": "系统默认保留最近 40 条消息作为 Working Memory"}
            ],
            "thread_summary": None,
        }
    )

    assert "Known thread facts:" in captured["prompt"]
    assert "Agentic RAG" in captured["prompt"]
    assert "FastAPI" in captured["prompt"]
    assert "Working Memory" not in captured["prompt"]
    assert "40 条消息" not in captured["prompt"]
    assert result["final_answer"] == "你的项目是 Agentic RAG，后端使用 FastAPI，前端为 React。"


def test_thread_context_summary_combines_compressed_summary_and_recent_facts() -> None:
    """线程背景总结应同时吸收压缩摘要中的早期事实和近期消息中的新增事实。"""

    captured: dict[str, str] = {}

    class FakeLLM:
        def chat(self, messages, temperature=0.0, max_tokens=220):
            captured["prompt"] = messages[-1]["content"]
            return ("你的项目是 Agentic RAG，后端使用 FastAPI，前端为 React，数据库是 PostgreSQL。", {})

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = FakeLLM()
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景。",
            "request_type": "thread_context",
            "messages": [
                {"role": "user", "content_text": "模型是 qwen3-max、text-embedding-v4、qwen3-rerank。"},
                {"role": "assistant", "content_text": "已记录当前线程背景。"},
                {"role": "user", "content_text": "第一版部署是本地存储 + 本地 PostgreSQL + 可选 Redis。"},
            ],
            "thread_summary": (
                "- 项目类型：Agentic RAG\n"
                "- 后端框架：FastAPI\n"
                "- 前端框架：React\n"
                "- 数据库：PostgreSQL"
            ),
            "recalled_memories": [
                {"memory_type": "semantic", "summary_text": "系统默认保留最近 40 条消息作为 Working Memory"}
            ],
        }
    )

    assert "项目类型：Agentic RAG" in captured["prompt"]
    assert "后端框架：FastAPI" in captured["prompt"]
    assert "前端框架：React" in captured["prompt"]
    assert "数据库：PostgreSQL" in captured["prompt"]
    assert "模型是 qwen3-max" in captured["prompt"]
    assert "第一版部署是本地存储" in captured["prompt"]
    assert "Working Memory" not in captured["prompt"]
    assert result["final_answer"] == "你的项目是 Agentic RAG，后端使用 FastAPI，前端为 React，数据库是 PostgreSQL。"


def test_focused_memory_answer_uses_only_matching_memory_fact() -> None:
    """Cross-thread fact questions should answer from the matched memory fact only."""

    captured: dict[str, str] = {}

    class FakeLLM:
        def chat(self, messages, temperature=0.0, max_tokens=180):
            captured["prompt"] = messages[-1]["content"]
            return ("第一版部署方式是本地存储 + 本地 PostgreSQL + 可选 Redis。", {})

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = FakeLLM()
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "我们第一版怎么部署？",
            "request_type": "smalltalk",
            "messages": [],
            "recalled_memories": [
                {
                    "memory_type": "semantic",
                    "summary_text": "我们第一版部署方式是本地存储 + 本地 PostgreSQL + 可选 Redis",
                },
                {
                    "memory_type": "semantic",
                    "summary_text": "后端是 FastAPI，前端是 React，模型是 qwen3-max",
                },
            ],
            "thread_summary": None,
        }
    )

    assert "Relevant memory facts:" in captured["prompt"]
    assert "本地 PostgreSQL + 可选 Redis" in captured["prompt"]
    assert "后端是 FastAPI" not in captured["prompt"]
    assert "qwen3-max" not in captured["prompt"]
    assert result["final_answer"] == "第一版部署方式是本地存储 + 本地 PostgreSQL + 可选 Redis。"


def test_event_memory_answer_uses_recent_thread_evidence_without_irrelevant_memory() -> None:
    """Event recap answers should use recent thread evidence and avoid unrelated recalled memories."""

    captured: dict[str, str] = {}

    class FakeLLM:
        def chat(self, messages, temperature=0.0, max_tokens=260):
            captured["prompt"] = messages[-1]["content"]
            return ("1. 长期记忆系统。 2. 背景信息压缩。 3. Memory Center。", {})

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = FakeLLM()
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我们这一轮新增的 3 个核心能力。",
            "request_type": "event_memory",
            "messages": [
                {"role": "user", "content_text": "请你先主动进行背景信息压缩，然后继续做完整的memory系统。"},
                {
                    "role": "assistant",
                    "content_text": (
                        "背景信息压缩和完整 memory 系统已经接上了。"
                        "现在的结构是两层记忆一起工作：线程背景压缩、长期记忆系统、Memory Center。"
                    ),
                },
            ],
            "recalled_memories": [
                {
                    "memory_type": "semantic",
                    "summary_text": "后端是 FastAPI，前端是 React，模型是 qwen3-max。",
                }
            ],
            "thread_summary": None,
        }
    )

    assert "Event evidence:" in captured["prompt"]
    assert "线程背景压缩" in captured["prompt"]
    assert "长期记忆系统" in captured["prompt"]
    assert "Memory Center" in captured["prompt"]
    assert "qwen3-max" not in captured["prompt"]
    assert "FastAPI" not in captured["prompt"]
    assert result["final_answer"] == "1. 长期记忆系统。 2. 背景信息压缩。 3. Memory Center。"


def test_event_memory_answer_refuses_when_no_event_evidence_exists() -> None:
    """Event recap questions should not fall through to generic direct LLM when evidence is missing."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我们这一轮新增的 3 个核心能力。",
            "request_type": "event_memory",
            "messages": [],
            "recalled_memories": [
                {"memory_type": "semantic", "summary_text": "后端是 FastAPI，前端是 React。"},
            ],
            "thread_summary": None,
        }
    )

    assert (
        result["final_answer"]
        == "我目前还没有检索到与这一轮新增内容相关的明确事件记忆。请在同一线程里先完成相关讨论，或明确指出要回顾的那一轮。"
    )


def test_invoke_direct_answer_prefers_memory_recall_over_write_like_phrase() -> None:
    """Recall phrasing like '你记住了…吗' should return recalled memory instead of write acknowledgement."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None
    service.answer_token_callback = None
    service.cancel_checker = None

    result = service._invoke_direct_answer(  # type: ignore[attr-defined]
        {
            "user_message": "你记住了我的什么回答偏好？",
            "recalled_memories": [
                {
                    "memory_type": "semantic",
                    "title": "Answer Preference",
                    "summary_text": "偏好中文回答，先给结论再给原因",
                }
            ],
            "thread_summary": None,
        }
    )

    assert "我当前记住的要点是" in result["final_answer"]
    assert "偏好中文回答" in result["final_answer"]


def test_memory_recall_answer_filters_noisy_generated_memory_lines() -> None:
    """Recall answers should drop buggy acknowledgements and generic failure text."""

    service = object.__new__(AtlasSupervisorGraphService)

    result = service._build_memory_recall_answer(  # type: ignore[attr-defined]
        {
            "user_message": "你记住了我的什么回答偏好？",
            "recalled_memories": [
                {"memory_type": "episodic", "summary_text": "已记住：了我的什么回答偏好？"},
                {"memory_type": "episodic", "summary_text": "根据当前知识库中的证据，暂时无法可靠回答这个问题。"},
                {"memory_type": "episodic", "summary_text": "2818024391@qq.com"},
                {"memory_type": "semantic", "summary_text": "我偏好中文回答，且默认先给结论再给原因"},
            ],
            "thread_summary": None,
        }
    )

    assert result == "我当前记住的要点是：\n1. 我偏好中文回答，且默认先给结论再给原因"


def test_conversation_context_block_includes_recent_thread_messages() -> None:
    """Direct answers should still see the latest thread history before summary compression exists."""

    service = object.__new__(AtlasSupervisorGraphService)

    block = service._build_conversation_context_block(  # type: ignore[attr-defined]
        {
            "user_message": "请总结一下我当前项目的关键背景",
            "messages": [
                {"role": "user", "content_text": "我的项目是 Agentic RAG。"},
                {"role": "assistant", "content_text": "好的，我会按这个背景继续。"},
                {"role": "user", "content_text": "后端是 FastAPI，前端是 React。"},
            ],
            "thread_summary": None,
            "recalled_memories": [],
        }
    )

    assert "Recent thread messages" in block
    assert "我的项目是 Agentic RAG" in block
    assert "后端是 FastAPI，前端是 React" in block


def test_build_citation_reads_preserves_graph_payload_shape() -> None:
    """Graph citation payloads should map directly into API response schemas."""

    service = object.__new__(AtlasSupervisorGraphService)
    payloads = [
        {
            "chunk_id": uuid4(),
            "document_id": uuid4(),
            "citation_label": "C1",
            "chunk_level": "child",
            "page_no": 2,
            "page_start": 2,
            "page_end": 2,
            "section_path": ["1. Overview", "1.1 Limits"],
            "snippet": "single file size limit: 200 MB",
        }
    ]

    citations = service.build_citation_reads(payloads)  # type: ignore[attr-defined]

    assert len(citations) == 1
    assert citations[0].citation_label == "C1"
    assert citations[0].section_path == ["1. Overview", "1.1 Limits"]


def test_trace_summary_condenses_retrieved_candidates() -> None:
    """Trace snapshots should keep retrieved candidates JSON-safe and compact."""

    recorder = RunTraceRecorder(db=None)
    candidate = RetrievedCandidate(
        chunk=SimpleNamespace(
            id=uuid4(),
            section_path=["2. Plans", "2.2 Business"],
            page_start=4,
            page_end=4,
        ),
        document_id=uuid4(),
        hybrid_score=0.73,
        rerank_score=0.91,
        alignment_score=1.2,
        final_score=2.84,
    )

    summary = recorder._summarize_state(
        {
            "run_id": uuid4(),
            "thread_id": uuid4(),
            "workspace_id": uuid4(),
            "messages": [{"role": "user", "content_text": "question"}],
            "retrieved_candidates": [candidate],
            "citation_candidates": [{"citation_label": "C1"}],
            "metrics": {"candidate_count": 1},
            "token_usage": {"answer": {"total_tokens": 32}},
        }
    )

    assert summary["message_count"] == 1
    assert summary["retrieved_candidate_count"] == 1
    assert summary["citation_count"] == 1
    assert summary["token_usage"] == {"answer": {"total_tokens": 32}}


def test_precise_answer_compression_prefers_evidence_line() -> None:
    """Simple factual questions should be compressed back to the matched evidence line."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.retrieval_service = SimpleNamespace(
        _extract_query_fragments=lambda _: ["business", "单文件大小上限"],
    )
    candidate = RetrievedCandidate(
        chunk=SimpleNamespace(
            raw_text="2.2 Business\n单文件大小上限：200 MB\n每月对话额度：500,000 次",
            section_path=["2. 产品版本与套餐", "2.2 Business"],
        ),
        document_id=uuid4(),
    )

    answer = service._compress_answer_if_needed(  # type: ignore[attr-defined]
        question="Business 套餐的单文件大小上限是多少？",
        answer=(
            "Business 是 Atlas Agentic RAG 的一个产品套餐，具有以下特性：\n"
            "- 单文件大小上限：200 MB\n"
            "- 每月对话额度：500,000 次"
        ),
        candidates=[candidate],
    )

    assert answer == "单文件大小上限是 200 MB。"


def test_partial_answer_extraction_reads_incremental_json_answer() -> None:
    """Streaming parser should expose only the answer field from partial JSON output."""

    service = object.__new__(AtlasSupervisorGraphService)

    partial = '{"answer":"200'
    partial_with_escape = '{"answer":"Line 1\\nLine'
    completed = '{"answer":"200 MB","citations":["C1"],"insufficient_reason":null}'

    assert service._extract_partial_answer_text(partial) == "200"  # type: ignore[attr-defined]
    assert service._extract_partial_answer_text(partial_with_escape) == "Line 1\nLine"  # type: ignore[attr-defined]
    assert service._extract_partial_answer_text(completed) == "200 MB"  # type: ignore[attr-defined]


def test_follow_up_rewrite_uses_previous_user_question_when_context_is_needed() -> None:
    """Short follow-up questions should be expanded with thread context before retrieval."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None

    rewritten = service._rewrite_follow_up_query(  # type: ignore[attr-defined]
        {
            "user_message": "\u90a3\u5982\u679c\u662f Business \u5462\uff1f",
            "messages": [
                {"role": "user", "content_text": "Viewer \u53ef\u4ee5\u5bfc\u51fa\u5f15\u7528\u5417\uff1f"},
                {"role": "assistant", "content_text": "Starter \u4e0b\u9ed8\u8ba4\u4e0d\u53ef\u4ee5\u3002"},
                {"role": "user", "content_text": "\u90a3\u5982\u679c\u662f Business \u5462\uff1f"},
            ],
        }
    )

    assert "Viewer" in rewritten["rewritten_message"]
    assert "Business" in rewritten["rewritten_message"]


def test_follow_up_rewrite_keeps_standalone_question_unchanged() -> None:
    """Standalone questions should not be rewritten just because a thread already exists."""

    service = object.__new__(AtlasSupervisorGraphService)
    service.llm_client = None

    rewritten = service._rewrite_follow_up_query(  # type: ignore[attr-defined]
        {
            "user_message": "Business \u5957\u9910\u7684\u5355\u6587\u4ef6\u5927\u5c0f\u4e0a\u9650\u662f\u591a\u5c11\uff1f",
            "messages": [
                {"role": "user", "content_text": "Starter \u5957\u9910\u80fd\u8fde\u51e0\u4e2a MCP\uff1f"},
                {"role": "assistant", "content_text": "Starter \u5f53\u524d\u6700\u591a\u53ef\u4ee5\u8fde\u63a5 2 \u4e2a MCP Server\u3002"},
                {"role": "user", "content_text": "Business \u5957\u9910\u7684\u5355\u6587\u4ef6\u5927\u5c0f\u4e0a\u9650\u662f\u591a\u5c11\uff1f"},
            ],
        }
    )

    assert (
        rewritten["rewritten_message"]
        == "Business \u5957\u9910\u7684\u5355\u6587\u4ef6\u5927\u5c0f\u4e0a\u9650\u662f\u591a\u5c11\uff1f"
    )


def test_stream_cancellation_registry_tracks_one_run() -> None:
    """Cancellation registry should register, cancel, and unregister a run."""

    registry = StreamCancellationRegistry()
    run_id = uuid4()

    signal = registry.register(run_id)

    assert signal.is_set() is False
    assert registry.is_cancelled(run_id) is False
    assert registry.cancel(run_id) is True
    assert signal.is_set() is True
    assert registry.is_cancelled(run_id) is True

    registry.unregister(run_id)
    assert registry.cancel(run_id) is False


def test_trace_recorder_emits_running_and_cancelled_step_events() -> None:
    """Live step callbacks should expose cancellation explicitly instead of generic failure."""

    class FakeDb:
        def add(self, _value: object) -> None:
            return None

        def flush(self) -> None:
            return None

    recorder = RunTraceRecorder(db=FakeDb())
    events: list[dict[str, object]] = []
    recorder.set_step_event_callback(events.append)

    wrapped = recorder.instrument(
        step_key="rag.generate_grounded_answer",
        step_type="rag_node",
        handler=lambda _state: (_ for _ in ()).throw(RunCancelledError("Run cancelled by user.")),
    )

    try:
        wrapped({"run_id": uuid4(), "thread_id": uuid4()})
    except RunCancelledError:
        pass
    else:
        raise AssertionError("RunCancelledError should have been re-raised")

    assert [item["status"] for item in events] == ["running", "cancelled"]
    assert isinstance(events[0]["started_at"], str)
    assert events[0]["ended_at"] is None
    assert events[0]["duration_ms"] is None
    assert events[-1]["step_key"] == "rag.generate_grounded_answer"
    assert isinstance(events[-1]["started_at"], str)
    assert isinstance(events[-1]["ended_at"], str)
    assert isinstance(events[-1]["duration_ms"], int)
