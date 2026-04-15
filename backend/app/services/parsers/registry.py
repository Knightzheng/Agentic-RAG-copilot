"""解析器注册表。"""

from __future__ import annotations

from pathlib import Path

from app.services.parsers.base import BaseParser
from app.services.parsers.docx_parser import DocxParser
from app.services.parsers.markdown_parser import MarkdownParser
from app.services.parsers.pdf_parser import PdfParser
from app.services.parsers.pptx_parser import PptxParser


class ParserRegistry:
    """根据文件后缀分发到对应解析器。"""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {
            ".md": MarkdownParser(),
            ".txt": MarkdownParser(),
            ".pdf": PdfParser(),
            ".docx": DocxParser(),
            ".pptx": PptxParser(),
        }

    def get(self, file_path: Path) -> BaseParser:
        """返回适配当前文件类型的解析器。"""

        parser = self._parsers.get(file_path.suffix.lower())
        if parser is None:
            raise ValueError(f"未注册的文件类型: {file_path.suffix.lower()}")
        return parser
