"""Embedding 与 FTS 索引构建服务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.kb import Document, DocumentChunk, DocumentEmbedding, DocumentFTS, DocumentVersion
from app.services.llm.dashscope_client import DashScopeClient


@dataclass(slots=True)
class IndexBuildResult:
    """索引构建结果。"""

    chunk_count: int
    embedding_count: int


class DocumentIndexService:
    """把 child chunk 写入 embedding 表和全文检索表。"""

    def __init__(self, db: Session, llm_client: DashScopeClient | None = None) -> None:
        self.db = db
        self.llm_client = llm_client or (DashScopeClient() if settings.has_dashscope_api_key else None)

    def reindex_document(self, document_id: UUID) -> IndexBuildResult:
        """根据 document_id 对最新版本重新构建索引。"""

        document = self.db.get(Document, document_id)
        if document is None:
            raise ValueError("文档不存在")
        if document.latest_version_id is None:
            raise ValueError("文档没有可用版本")
        version = self.db.get(DocumentVersion, document.latest_version_id)
        if version is None:
            raise ValueError("文档版本不存在")
        return self.reindex_version(document=document, version=version)

    def reindex_version(self, document: Document, version: DocumentVersion) -> IndexBuildResult:
        """对指定版本执行 embedding 和 FTS 构建。

        FTS 不依赖外部模型，因此始终可以构建。
        embedding 依赖百炼模型，缺少 key 时只跳过向量索引。
        """

        child_chunks = list(
            self.db.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_version_id == version.id,
                    DocumentChunk.chunk_level == "child",
                )
                .order_by(DocumentChunk.chunk_order.asc())
            )
        )
        if not child_chunks:
            raise ValueError("当前文档没有可索引的 child chunk")

        version.embedding_status = "running" if self.llm_client is not None else "partial"
        version.index_status = "building"
        now = datetime.now(timezone.utc)

        self.db.execute(
            delete(DocumentEmbedding).where(DocumentEmbedding.document_version_id == version.id)
        )
        self.db.execute(delete(DocumentFTS).where(DocumentFTS.document_version_id == version.id))

        embedding_rows = []
        if self.llm_client is not None:
            embeddings = self.llm_client.embed_texts([chunk.contextualized_text for chunk in child_chunks])
            for chunk, embedding in zip(child_chunks, embeddings, strict=True):
                embedding_rows.append(
                    DocumentEmbedding(
                        workspace_id=document.workspace_id,
                        document_id=document.id,
                        document_version_id=version.id,
                        chunk_id=chunk.id,
                        model_name=settings.embedding_model,
                        model_revision=None,
                        embedding_dim=len(embedding),
                        embedding=embedding,
                        distance_metric="cosine",
                        text_hash=hashlib.sha256(chunk.contextualized_text.encode("utf-8")).hexdigest(),
                        created_at=now,
                    )
                )
            self.db.add_all(embedding_rows)

        for chunk in child_chunks:
            searchable_text = chunk.contextualized_text
            stmt = pg_insert(DocumentFTS).values(
                chunk_id=chunk.id,
                workspace_id=document.workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                searchable_text=searchable_text,
                tsv=func.to_tsvector("simple", searchable_text),
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[DocumentFTS.chunk_id],
                set_={
                    "workspace_id": document.workspace_id,
                    "document_id": document.id,
                    "document_version_id": version.id,
                    "searchable_text": searchable_text,
                    "tsv": func.to_tsvector("simple", searchable_text),
                    "updated_at": now,
                },
            )
            self.db.execute(stmt)

        if self.llm_client is not None:
            version.embedding_status = "success"
            version.embedding_model = settings.embedding_model
            version.embedding_dim = settings.embedding_dimensions
        else:
            version.embedding_status = "partial"
            version.embedding_model = None
            version.embedding_dim = None
        version.index_status = "ready"
        return IndexBuildResult(chunk_count=len(child_chunks), embedding_count=len(embedding_rows))
