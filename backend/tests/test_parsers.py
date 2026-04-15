"""解析器与切块服务的最小单测。"""

from __future__ import annotations

from pathlib import Path

from app.services.chunking.service import ChunkingService
from app.services.parsers.registry import ParserRegistry


def test_markdown_parser_can_extract_blocks() -> None:
    """验证 Markdown 语料能解析出标题和段落。"""

    sample_path = Path(__file__).resolve().parents[2] / "atlas_agentic_rag_testset_v1" / "atlas_kb_test_corpus_v1.md"
    parser = ParserRegistry().get(sample_path)
    parsed = parser.parse(sample_path)

    assert parsed.title
    assert parsed.blocks
    assert any(block.block_type == "title" for block in parsed.blocks)


def test_chunking_service_can_build_parent_and_child_chunks() -> None:
    """验证切块服务会生成 parent / child 两层 chunk。"""

    sample_path = Path(__file__).resolve().parents[2] / "atlas_agentic_rag_testset_v1" / "atlas_kb_test_corpus_v1.md"
    parser = ParserRegistry().get(sample_path)
    parsed = parser.parse(sample_path)
    chunks = ChunkingService().build_chunks(parsed)

    assert chunks
    assert any(chunk.chunk_level == "parent" for chunk in chunks)
    assert any(chunk.chunk_level == "child" for chunk in chunks)
