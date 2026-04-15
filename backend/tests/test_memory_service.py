"""Regression tests for long-term memory and compressed thread context helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.chat.service import ChatService
from app.services.memory.service import MemoryService
from app.services.orchestration.graph import AtlasSupervisorGraphService


def test_extract_explicit_memory_text_reads_chinese_memory_intent() -> None:
    """Explicit remember instructions should be captured as semantic memory text."""

    extracted = MemoryService._extract_explicit_memory_text("请记住：我更偏好中文回答，代码注释尽量简短。")

    assert extracted == "我更偏好中文回答，代码注释尽量简短"


def test_extract_explicit_memory_text_does_not_misread_recall_question() -> None:
    """Recall questions should not be mistaken for write-memory commands."""

    extracted = MemoryService._extract_explicit_memory_text("你记住了我的什么回答偏好？")

    assert extracted is None


def test_noise_memory_text_flags_generic_failure_and_memory_ack() -> None:
    """Low-value generated answers should not be written or recalled as durable memory."""

    assert MemoryService._is_noise_memory_text("根据当前知识库中的证据，暂时无法可靠回答这个问题。")
    assert MemoryService._is_noise_memory_text("已记住：我偏好中文回答")
    assert MemoryService._is_noise_memory_text("我当前记住的要点是：1. 偏好中文回答")
    assert MemoryService._is_noise_memory_text("当前线程里还没有足够的项目背景信息。请先在同一线程告诉我项目背景，再让我总结。")
    assert MemoryService._is_noise_memory_text("我目前还没有检索到与这一轮新增内容相关的明确事件记忆。请在同一线程里先完成相关讨论，或明确指出要回顾的那一轮。")


def test_should_write_episodic_memory_allows_event_memory_direct_but_blocks_other_direct_answers() -> None:
    """Only high-value event recaps should be allowed through the direct->episodic path."""

    assert MemoryService._should_write_episodic_memory(
        result_status="success",
        request_type="event_memory",
        route_target="direct",
        answer="1. 长期记忆系统。2. 背景信息压缩。3. Memory Center。",
    )
    assert not MemoryService._should_write_episodic_memory(
        result_status="success",
        request_type="thread_context",
        route_target="direct",
        answer="你的项目是 Agentic RAG，后端使用 FastAPI。",
    )
    assert not MemoryService._should_write_episodic_memory(
        result_status="success",
        request_type="context_update",
        route_target="direct",
        answer="已记录当前线程背景。后续我会按这个项目上下文继续回答。",
    )


def test_score_procedural_memory_recalls_kb_answer_rules_by_scene() -> None:
    """知识库问答类 procedural rule 即使没有词面重合，也应能按场景被召回。"""

    score = MemoryService._score_procedural_memory(
        query="Starter 套餐每个工作区最多可以连接多少个 MCP Server？",
        haystack="回答知识库问题时，先给结论，再给 citations，不要展开无关背景。",
        is_pinned=False,
    )

    assert score > 0


def test_score_procedural_memory_does_not_recall_irrelevant_rules() -> None:
    """无关 procedural rule 不应仅因为是规则文本就被知识库问题召回。"""

    score = MemoryService._score_procedural_memory(
        query="Starter 套餐每个工作区最多可以连接多少个 MCP Server？",
        haystack="部署完成后请先重启本地 Redis 服务，再刷新浏览器缓存。",
        is_pinned=False,
    )

    assert score == 0


def test_extract_query_fragments_keeps_chinese_and_ascii_terms() -> None:
    """Memory recall fallback should preserve both product names and Chinese fragments."""

    fragments = MemoryService._extract_query_fragments("Business 套餐的 Viewer 可以导出引用吗？")

    assert "business" in fragments
    assert any("viewer" in item for item in fragments)
    assert any("导出引用" in item for item in fragments)


def test_graph_context_block_combines_summary_and_recalled_memories() -> None:
    """Prompt context should include compressed background and recalled memories together."""

    service = object.__new__(AtlasSupervisorGraphService)
    block = service._build_conversation_context_block(  # type: ignore[attr-defined]
        {
            "thread_summary": "- User prefers concise Chinese answers.",
            "recalled_memories": [
                {
                    "memory_type": "semantic",
                    "title": "Language Preference",
                    "summary_text": "Prefer concise Chinese answers.",
                },
                {
                    "memory_type": "procedural",
                    "title": "Citation Rule",
                    "content_text": "Always cite evidence when answering KB questions.",
                },
            ],
        }
    )

    assert "Thread summary" in block
    assert "Language Preference" in block
    assert "Citation Rule" in block


def test_fallback_thread_summary_compresses_recent_history() -> None:
    """Thread background compression should keep user focus and assistant conclusions."""

    service = object.__new__(ChatService)
    summary = service._fallback_thread_summary(  # type: ignore[attr-defined]
        [
            SimpleNamespace(role="user", content_text="请记住我更偏好中文回答。"),
            SimpleNamespace(role="assistant", content_text="好的，后续我会默认优先使用中文。"),
            SimpleNamespace(role="user", content_text="另外，答案尽量简洁并给出引用。"),
            SimpleNamespace(role="assistant", content_text="明白，后续会保持简洁并优先附带引用。"),
        ]
    )

    assert "User focus" in summary
    assert "Assistant conclusions" in summary
