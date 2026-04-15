"""DOCX 解析器。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from docx import Document as DocxDocument
from docx.document import Document as DocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.parsers.base import BaseParser, ParsedBlock, ParsedDocument, normalize_text


def iter_block_items(document: DocumentType) -> Iterator[Paragraph | Table]:
    """按照原始顺序遍历 docx 中的段落和表格。"""

    parent = document.element.body
    for child in parent.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


class DocxParser(BaseParser):
    """提取标题、普通段落和表格。"""

    parser_name = "python-docx"

    def parse(self, file_path: Path) -> ParsedDocument:
        document = DocxDocument(str(file_path))
        blocks: list[ParsedBlock] = []
        section_path: list[str] = []
        block_order = 0
        title = file_path.stem
        table_count = 0

        for item in iter_block_items(document):
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                style_name = item.style.name if item.style is not None else ""
                block_type = "paragraph"
                metadata: dict = {"style_name": style_name}

                if style_name.startswith("Heading"):
                    block_type = "title"
                    try:
                        level = int(style_name.replace("Heading", "").strip())
                    except ValueError:
                        level = 1
                    if block_order == 0:
                        title = text
                    if len(section_path) >= level:
                        section_path = section_path[: level - 1]
                    while len(section_path) < level - 1:
                        section_path.append("未命名章节")
                    section_path.append(text)
                    metadata["heading_level"] = level
                elif text.startswith(("- ", "* ")):
                    block_type = "list"

                blocks.append(
                    ParsedBlock(
                        block_type=block_type,
                        raw_text=text,
                        normalized_text=normalize_text(text),
                        section_path=list(section_path),
                        page_no=None,
                        block_order=block_order,
                        metadata=metadata,
                    )
                )
                block_order += 1
                continue

            table_count += 1
            rows = []
            for row in item.rows:
                cell_values = [" ".join(cell.text.split()) for cell in row.cells]
                rows.append(" | ".join(cell_values))
            table_text = "\n".join(row for row in rows if row.strip())
            if not table_text:
                continue
            blocks.append(
                ParsedBlock(
                    block_type="table",
                    raw_text=table_text,
                    normalized_text=normalize_text(table_text),
                    section_path=list(section_path),
                    page_no=None,
                    block_order=block_order,
                    metadata={"row_count": len(rows)},
                )
            )
            block_order += 1

        return ParsedDocument(
            title=title,
            file_type="docx",
            parser_name=self.parser_name,
            blocks=blocks,
            metadata={"page_count": None, "table_count": table_count},
        )
