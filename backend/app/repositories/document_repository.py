"""文档仓储。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kb import Document, DocumentChunk


class DocumentRepository:
    """封装文档主表和 chunk 查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_workspace(self, workspace_id: UUID) -> list[Document]:
        """按工作区列出文档。"""

        stmt = (
            select(Document)
            .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc())
        )
        return list(self.db.scalars(stmt))

    def get(self, document_id: UUID) -> Document | None:
        """根据主键查询文档。"""

        stmt = select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def get_by_hash(self, workspace_id: UUID, file_hash: str) -> Document | None:
        """根据工作区和文件 hash 检查重复文档。"""

        stmt = select(Document).where(
            Document.workspace_id == workspace_id,
            Document.file_hash == file_hash,
            Document.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def list_chunks(self, document_id: UUID) -> list[DocumentChunk]:
        """返回文档对应的所有 chunk。"""

        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_level.desc(), DocumentChunk.chunk_order.asc())
        )
        return list(self.db.scalars(stmt))
