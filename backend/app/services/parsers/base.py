"""解析器基础协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def normalize_text(text: str) -> str:
    """做最小归一化，便于后续切块与检索。"""

    return " ".join(text.replace("\u3000", " ").split())


@dataclass(slots=True)
class ParsedBlock:
    """解析阶段输出的最小 block。"""

    block_type: str
    raw_text: str
    normalized_text: str
    section_path: list[str]
    page_no: int | None
    block_order: int
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    """解析器统一输出。"""

    title: str
    file_type: str
    parser_name: str
    blocks: list[ParsedBlock]
    metadata: dict = field(default_factory=dict)


class BaseParser:
    """所有文件解析器共享的接口。"""

    parser_name = "base"

    def parse(self, file_path: Path) -> ParsedDocument:
        """把文件解析为统一结构。"""

        raise NotImplementedError
