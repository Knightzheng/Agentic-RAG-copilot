"""PDF 解析器。"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.services.parsers.base import BaseParser, ParsedBlock, ParsedDocument, normalize_text


class PdfParser(BaseParser):
    """基于 pypdf 做最小文本抽取。"""

    parser_name = "pypdf"

    def parse(self, file_path: Path) -> ParsedDocument:
        reader = PdfReader(str(file_path))
        blocks: list[ParsedBlock] = []
        block_order = 0
        title = (reader.metadata.title if reader.metadata else None) or file_path.stem
        total_text_chars = 0

        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            total_text_chars += len(text)
            if not text:
                continue

            paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
            for paragraph in paragraphs:
                block_type = "paragraph"
                if paragraph == title and block_order == 0:
                    block_type = "title"
                blocks.append(
                    ParsedBlock(
                        block_type=block_type,
                        raw_text=paragraph,
                        normalized_text=normalize_text(paragraph),
                        section_path=[],
                        page_no=page_index,
                        block_order=block_order,
                        metadata={},
                    )
                )
                block_order += 1

        return ParsedDocument(
            title=title,
            file_type="pdf",
            parser_name=self.parser_name,
            blocks=blocks,
            metadata={
                "page_count": len(reader.pages),
                "ocr_used": False,
                "likely_scanned": total_text_chars < 100,
            },
        )
