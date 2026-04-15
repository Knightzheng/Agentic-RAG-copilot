"""Markdown / TXT 解析器。"""

from __future__ import annotations

from pathlib import Path

from app.services.parsers.base import BaseParser, ParsedBlock, ParsedDocument, normalize_text


class MarkdownParser(BaseParser):
    """把 Markdown 文本解析成标题、列表和段落 block。"""

    parser_name = "markdown"

    def parse(self, file_path: Path) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        blocks: list[ParsedBlock] = []
        section_path: list[str] = []
        paragraph_buffer: list[str] = []
        block_order = 0
        title = file_path.stem

        def flush_paragraph() -> None:
            nonlocal block_order
            if not paragraph_buffer:
                return
            raw_text = "\n".join(paragraph_buffer).strip()
            paragraph_buffer.clear()
            if not raw_text:
                return
            blocks.append(
                ParsedBlock(
                    block_type="paragraph",
                    raw_text=raw_text,
                    normalized_text=normalize_text(raw_text),
                    section_path=list(section_path),
                    page_no=1,
                    block_order=block_order,
                )
            )
            block_order += 1

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                flush_paragraph()
                continue

            if stripped.startswith("#"):
                flush_paragraph()
                level = len(stripped) - len(stripped.lstrip("#"))
                heading_text = stripped[level:].strip()
                if not heading_text:
                    continue
                if block_order == 0:
                    title = heading_text
                if len(section_path) >= level:
                    section_path = section_path[: level - 1]
                while len(section_path) < level - 1:
                    section_path.append("未命名章节")
                section_path.append(heading_text)
                blocks.append(
                    ParsedBlock(
                        block_type="title",
                        raw_text=heading_text,
                        normalized_text=normalize_text(heading_text),
                        section_path=list(section_path),
                        page_no=1,
                        block_order=block_order,
                        metadata={"heading_level": level},
                    )
                )
                block_order += 1
                continue

            if stripped.startswith(("- ", "* ", "+ ")):
                flush_paragraph()
                item_text = stripped[2:].strip()
                blocks.append(
                    ParsedBlock(
                        block_type="list",
                        raw_text=item_text,
                        normalized_text=normalize_text(item_text),
                        section_path=list(section_path),
                        page_no=1,
                        block_order=block_order,
                    )
                )
                block_order += 1
                continue

            paragraph_buffer.append(stripped)

        flush_paragraph()
        return ParsedDocument(
            title=title,
            file_type=file_path.suffix.lower().lstrip("."),
            parser_name=self.parser_name,
            blocks=blocks,
            metadata={"page_count": 1},
        )
