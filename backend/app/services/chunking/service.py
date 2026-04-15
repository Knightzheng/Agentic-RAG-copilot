"""Chunk 切分服务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.core.config import settings
from app.services.parsers.base import ParsedBlock, ParsedDocument


@dataclass(slots=True)
class ChunkDraft:
    """尚未落库的 chunk 草稿。"""

    chunk_level: str
    chunk_order: int
    parent_order: int | None
    page_no: int | None
    page_start: int | None
    page_end: int | None
    section_path: list[str]
    block_span: list[int]
    raw_text: str
    contextualized_text: str
    token_count: int
    char_count: int
    content_hash: str
    metadata: dict


class ChunkingService:
    """把 block 列表切成 parent / child chunk。"""

    def build_chunks(self, parsed_document: ParsedDocument) -> list[ChunkDraft]:
        """根据 block 列表构造两层 chunk。"""

        parents = self._build_parent_chunks(parsed_document)
        all_chunks: list[ChunkDraft] = []
        for parent in parents:
            all_chunks.append(parent)
            all_chunks.extend(self._build_child_chunks(parsed_document, parent))
        return all_chunks

    def _build_parent_chunks(self, parsed_document: ParsedDocument) -> list[ChunkDraft]:
        """按章节和字符数上限生成 parent chunk。"""

        chunks: list[ChunkDraft] = []
        buffer: list[ParsedBlock] = []
        chunk_order = 0

        def flush_buffer() -> None:
            nonlocal chunk_order
            if not buffer:
                return
            chunks.append(self._build_chunk_from_blocks(parsed_document, buffer, "parent", chunk_order, None))
            chunk_order += 1
            buffer.clear()

        current_chars = 0
        current_section_key = ""
        for block in parsed_document.blocks:
            section_key = " / ".join(block.section_path)
            block_chars = len(block.normalized_text)
            should_flush = False
            if buffer and current_chars + block_chars > settings.parent_chunk_char_limit:
                should_flush = True
            if buffer and current_section_key and section_key and section_key != current_section_key and current_chars > 400:
                should_flush = True
            if should_flush:
                flush_buffer()
                current_chars = 0
                current_section_key = ""

            buffer.append(block)
            current_chars += block_chars
            current_section_key = section_key or current_section_key

        flush_buffer()
        return chunks

    def _build_child_chunks(self, parsed_document: ParsedDocument, parent: ChunkDraft) -> list[ChunkDraft]:
        """在 parent chunk 内继续切出更小的 child chunk。"""

        parent_block_indexes = set(parent.block_span)
        block_pool = [block for block in parsed_document.blocks if block.block_order in parent_block_indexes]
        child_chunks: list[ChunkDraft] = []
        buffer: list[ParsedBlock] = []
        chunk_order = 0
        current_chars = 0
        current_section_key = ""

        def flush_buffer() -> None:
            nonlocal chunk_order
            if not buffer:
                return
            child_chunks.append(
                self._build_chunk_from_blocks(
                    parsed_document=parsed_document,
                    blocks=buffer,
                    chunk_level="child",
                    chunk_order=chunk_order,
                    parent_order=parent.chunk_order,
                )
            )
            chunk_order += 1
            buffer.clear()

        for block in block_pool:
            section_key = " / ".join(block.section_path)
            block_chars = len(block.normalized_text)
            should_flush = False
            if buffer and current_chars + block_chars > settings.child_chunk_char_limit:
                should_flush = True
            # child chunk 默认不跨 sibling section，避免把多个套餐或多个指标压进同一证据片段。
            if buffer and current_section_key and section_key and section_key != current_section_key:
                should_flush = True

            if should_flush:
                flush_buffer()
                current_chars = 0
                current_section_key = ""

            buffer.append(block)
            current_chars += block_chars
            current_section_key = section_key or current_section_key

        flush_buffer()
        return child_chunks

    def _build_chunk_from_blocks(
        self,
        parsed_document: ParsedDocument,
        blocks: list[ParsedBlock],
        chunk_level: str,
        chunk_order: int,
        parent_order: int | None,
    ) -> ChunkDraft:
        """把一组 block 封装为单个 chunk。"""

        raw_text = "\n\n".join(block.raw_text for block in blocks)
        section_path = self._resolve_chunk_section_path(blocks)
        page_numbers = [block.page_no for block in blocks if block.page_no is not None]
        contextualized_text = self._build_contextualized_text(
            title=parsed_document.title,
            section_path=section_path,
            body_text=raw_text,
        )
        char_count = len(raw_text)
        token_count = max(1, char_count // 4)
        content_hash = hashlib.sha256(contextualized_text.encode("utf-8")).hexdigest()

        return ChunkDraft(
            chunk_level=chunk_level,
            chunk_order=chunk_order,
            parent_order=parent_order,
            page_no=page_numbers[0] if len(page_numbers) == 1 else None,
            page_start=page_numbers[0] if page_numbers else None,
            page_end=page_numbers[-1] if page_numbers else None,
            section_path=list(section_path),
            block_span=[block.block_order for block in blocks],
            raw_text=raw_text,
            contextualized_text=contextualized_text,
            token_count=token_count,
            char_count=char_count,
            content_hash=content_hash,
            metadata={"source_title": parsed_document.title},
        )

    def _resolve_chunk_section_path(self, blocks: list[ParsedBlock]) -> list[str]:
        """为 chunk 选择稳定的章节路径，跨多个 sibling section 时退回公共前缀。"""

        paths = [list(block.section_path) for block in blocks if block.section_path]
        if not paths:
            return []

        common_prefix = list(paths[0])
        for path in paths[1:]:
            prefix_length = 0
            for left, right in zip(common_prefix, path, strict=False):
                if left != right:
                    break
                prefix_length += 1
            common_prefix = common_prefix[:prefix_length]
            if not common_prefix:
                break

        if common_prefix and all(path == common_prefix for path in paths):
            return common_prefix
        if common_prefix:
            return common_prefix
        return paths[-1]

    def _build_contextualized_text(self, title: str, section_path: list[str], body_text: str) -> str:
        """构造后续 embedding 和检索使用的上下文化文本。"""

        path_text = " > ".join(section_path) if section_path else "未命名章节"
        return f"文档标题: {title}\n章节路径: {path_text}\n正文内容:\n{body_text}"
