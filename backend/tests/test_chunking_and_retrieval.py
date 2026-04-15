"""第三阶段检索质量修复的回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services.chunking.service import ChunkingService
from app.services.parsers.registry import ParserRegistry
from app.services.retrieval.service import RetrievedCandidate, RetrievalService


def _sample_corpus_path() -> Path:
    return Path(__file__).resolve().parents[2] / "atlas_agentic_rag_testset_v1" / "atlas_kb_test_corpus_v1.md"


def test_child_chunks_respect_section_boundaries() -> None:
    """同一 child chunk 不应再跨越 Starter / Business / Enterprise 这类 sibling section。"""

    sample_path = _sample_corpus_path()
    parser = ParserRegistry().get(sample_path)
    parsed = parser.parse(sample_path)
    chunks = ChunkingService().build_chunks(parsed)

    business_chunk = next(
        chunk
        for chunk in chunks
        if chunk.chunk_level == "child"
        and chunk.section_path[-1] == "2.2 Business"
        and "单文件大小上限：200 MB" in chunk.raw_text
    )
    enterprise_chunk = next(
        chunk
        for chunk in chunks
        if chunk.chunk_level == "child"
        and chunk.section_path[-1] == "2.3 Enterprise"
        and "单文件大小上限：500 MB" in chunk.raw_text
    )

    assert "2.1 Starter" not in business_chunk.raw_text
    assert "单文件大小上限：500 MB" not in business_chunk.raw_text
    assert "2.2 Business" not in enterprise_chunk.raw_text


def test_alignment_score_prefers_exact_attribute_match() -> None:
    """精确属性命中的候选应该比只命中套餐名的候选拿到更高对齐分。"""

    service = RetrievalService(db=None, llm_client=None)
    query = "Business 套餐的单文件大小上限是多少？"

    good_candidate = RetrievedCandidate(
        chunk=SimpleNamespace(
            raw_text="2.2 Business\n单文件大小上限：200 MB\n每月对话额度：500,000 次",
            contextualized_text="文档标题: Atlas\n章节路径: 2.2 Business\n正文:\n单文件大小上限：200 MB",
            section_path=["Atlas Agentic RAG 测试知识库文档（V1）", "2. 产品版本与套餐", "2.2 Business"],
            metadata_json={"source_title": "Atlas Agentic RAG 测试知识库文档（V1）"},
        ),
        document_id=uuid4(),
    )
    noisy_candidate = RetrievedCandidate(
        chunk=SimpleNamespace(
            raw_text="Business\nChat API：300 次/分钟\nSearch API：600 次/分钟",
            contextualized_text="文档标题: Atlas\n章节路径: 12.2 附加资源包\n正文:\nBusiness\nChat API：300 次/分钟",
            section_path=["Atlas Agentic RAG 测试知识库文档（V1）", "12. 套餐价格与资源包", "12.2 附加资源包"],
            metadata_json={"source_title": "Atlas Agentic RAG 测试知识库文档（V1）"},
        ),
        document_id=uuid4(),
    )

    assert service._compute_alignment_score(query, good_candidate) > service._compute_alignment_score(query, noisy_candidate)
