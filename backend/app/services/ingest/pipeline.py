"""文档接入与解析主链路。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import Citation, RetrievalCandidate, RerankResult
from app.models.kb import Document, DocumentBlock, DocumentChunk, DocumentEmbedding, DocumentFTS, DocumentVersion
from app.repositories.document_repository import DocumentRepository
from app.services.chunking.service import ChunkDraft, ChunkingService
from app.services.indexing.service import DocumentIndexService
from app.services.parsers.registry import ParserRegistry
from app.services.storage.local_storage import LocalStorageService


@dataclass(slots=True)
class IngestResult:
    """文档接入结果。"""

    document: Document
    version: DocumentVersion
    duplicate_of: UUID | None = None


class DocumentIngestService:
    """串起上传、去重、存储、解析和切块流程。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = DocumentRepository(db)
        self.storage = LocalStorageService()
        self.registry = ParserRegistry()
        self.chunking_service = ChunkingService()

    def ingest_bytes(
        self,
        workspace_id: UUID,
        owner_user_id: UUID,
        filename: str,
        file_bytes: bytes,
        source_type: str,
    ) -> IngestResult:
        """处理上传字节流。"""

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        duplicate = self.repository.get_by_hash(workspace_id=workspace_id, file_hash=file_hash)
        if duplicate is not None:
            version_stmt = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == duplicate.id)
                .order_by(DocumentVersion.version_no.desc())
            )
            version = self.db.scalar(version_stmt)
            if version is None:
                raise RuntimeError("检测到重复文档，但缺少版本记录")
            return IngestResult(document=duplicate, version=version, duplicate_of=duplicate.id)

        document = Document(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            title=Path(filename).stem,
            original_filename=filename,
            file_hash=file_hash,
            file_type=Path(filename).suffix.lower().lstrip("."),
            source_type=source_type,
            source_uri=None,
            status="processing",
            metadata_json={"ingest_mode": "sync"},
        )
        self.db.add(document)
        self.db.flush()

        storage_path = self.storage.save_bytes(workspace_id=workspace_id, document_id=document.id, filename=filename, file_bytes=file_bytes)
        version = DocumentVersion(
            document_id=document.id,
            version_no=1,
            storage_uri=str(storage_path),
            parse_status="running",
            chunk_status="pending",
            embedding_status="pending",
            index_status="pending",
        )
        self.db.add(version)
        self.db.flush()

        try:
            self._parse_and_materialize(document=document, version=version, storage_path=storage_path)
        except Exception as exc:
            version.parse_status = "failed"
            version.chunk_status = "failed"
            version.embedding_status = "failed"
            version.index_status = "failed"
            version.error_code = "parse_failed"
            version.error_message = str(exc)
            document.status = "failed"
            raise

        return IngestResult(document=document, version=version)

    def reprocess_document(self, document_id: UUID) -> IngestResult:
        """重新解析并重建指定文档的当前最新版本。"""

        document = self.repository.get(document_id)
        if document is None:
            raise ValueError("文档不存在")
        if document.latest_version_id is None:
            raise ValueError("文档没有可用版本")

        version = self.db.get(DocumentVersion, document.latest_version_id)
        if version is None:
            raise ValueError("文档版本不存在")

        storage_path = Path(version.storage_uri)
        if not storage_path.exists():
            raise FileNotFoundError(f"未找到源文件: {storage_path}")

        document.status = "processing"
        version.parse_status = "running"
        version.chunk_status = "pending"
        version.embedding_status = "pending"
        version.index_status = "pending"
        version.error_code = None
        version.error_message = None

        self._clear_version_artifacts(version.id)

        try:
            self._parse_and_materialize(document=document, version=version, storage_path=storage_path)
        except Exception as exc:
            version.parse_status = "failed"
            version.chunk_status = "failed"
            version.embedding_status = "failed"
            version.index_status = "failed"
            version.error_code = "reprocess_failed"
            version.error_message = str(exc)
            document.status = "failed"
            raise

        return IngestResult(document=document, version=version)

    def _parse_and_materialize(self, *, document: Document, version: DocumentVersion, storage_path: Path) -> None:
        """解析源文件并落库 blocks、chunks 与索引。"""

        parser = self.registry.get(storage_path)
        parsed_document = parser.parse(storage_path)

        document.title = parsed_document.title
        document.latest_version_id = version.id
        document.language = "auto"
        document.source_uri = str(storage_path)
        document.metadata_json = {
            "parser_name": parsed_document.parser_name,
            "page_count": parsed_document.metadata.get("page_count"),
            "ocr_used": parsed_document.metadata.get("ocr_used", False),
            "likely_scanned": parsed_document.metadata.get("likely_scanned", False),
        }
        version.parser_name = parsed_document.parser_name
        version.parser_version = settings.parser_version
        version.parse_status = "success"
        version.chunk_status = "running"

        now = datetime.now(timezone.utc)
        for block in parsed_document.blocks:
            self.db.add(
                DocumentBlock(
                    document_version_id=version.id,
                    page_no=block.page_no,
                    block_order=block.block_order,
                    block_type=block.block_type,
                    section_path=block.section_path,
                    raw_text=block.raw_text,
                    normalized_text=block.normalized_text,
                    bbox_json=None,
                    metadata_json=block.metadata,
                    created_at=now,
                )
            )

        chunk_drafts = self.chunking_service.build_chunks(parsed_document)
        parent_id_map: dict[int, UUID] = {}
        for draft in chunk_drafts:
            chunk = self._build_chunk_model(
                document_id=document.id,
                version_id=version.id,
                draft=draft,
                parent_chunk_id=parent_id_map.get(draft.parent_order) if draft.parent_order is not None else None,
                created_at=now,
            )
            self.db.add(chunk)
            self.db.flush()
            if draft.chunk_level == "parent":
                parent_id_map[draft.chunk_order] = chunk.id

        version.chunk_status = "success"
        index_service = DocumentIndexService(db=self.db)
        index_service.reindex_version(document=document, version=version)
        document.status = "ready"

    def _clear_version_artifacts(self, version_id: UUID) -> None:
        """清理指定版本的旧 blocks、chunks 与索引，便于按新规则重建。"""

        chunk_ids = list(
            self.db.scalars(
                select(DocumentChunk.id).where(DocumentChunk.document_version_id == version_id)
            )
        )

        self.db.execute(delete(DocumentEmbedding).where(DocumentEmbedding.document_version_id == version_id))
        self.db.execute(delete(DocumentFTS).where(DocumentFTS.document_version_id == version_id))
        if chunk_ids:
            self.db.execute(delete(Citation).where(Citation.chunk_id.in_(chunk_ids)))
            self.db.execute(delete(RerankResult).where(RerankResult.chunk_id.in_(chunk_ids)))
            self.db.execute(delete(RetrievalCandidate).where(RetrievalCandidate.chunk_id.in_(chunk_ids)))
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version_id))
        self.db.execute(delete(DocumentBlock).where(DocumentBlock.document_version_id == version_id))

    def _build_chunk_model(
        self,
        document_id: UUID,
        version_id: UUID,
        draft: ChunkDraft,
        parent_chunk_id: UUID | None,
        created_at: datetime,
    ) -> DocumentChunk:
        """把 chunk 草稿转为 ORM 模型。"""

        return DocumentChunk(
            document_id=document_id,
            document_version_id=version_id,
            parent_chunk_id=parent_chunk_id,
            chunk_level=draft.chunk_level,
            chunk_order=draft.chunk_order,
            page_no=draft.page_no,
            page_start=draft.page_start,
            page_end=draft.page_end,
            section_path=draft.section_path,
            block_span_json=draft.block_span,
            raw_text=draft.raw_text,
            contextualized_text=draft.contextualized_text,
            summary_text=None,
            token_count=draft.token_count,
            char_count=draft.char_count,
            content_hash=draft.content_hash,
            metadata_json=draft.metadata,
            created_at=created_at,
        )
