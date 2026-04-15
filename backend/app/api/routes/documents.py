"""文档接口。"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.repositories.document_repository import DocumentRepository
from app.schemas.documents import (
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentRead,
    DocumentUploadResponse,
)
from app.services.ingest.pipeline import DocumentIngestService
from app.services.indexing.service import DocumentIndexService

router = APIRouter(prefix="/documents")


@router.get("", response_model=list[DocumentRead])
def list_documents(workspace_id: UUID, db: Session = Depends(get_db)) -> list[DocumentRead]:
    """按工作区列出文档。"""

    repository = DocumentRepository(db)
    return [DocumentRead.model_validate(item) for item in repository.list_by_workspace(workspace_id)]


@router.get("/{document_id}", response_model=DocumentDetailRead)
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> DocumentDetailRead:
    """查询文档详情。"""

    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocumentDetailRead.model_validate(document)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkRead])
def get_document_chunks(document_id: UUID, db: Session = Depends(get_db)) -> list[DocumentChunkRead]:
    """查询指定文档的 chunk 列表。"""

    repository = DocumentRepository(db)
    chunks = repository.list_chunks(document_id=document_id)
    return [DocumentChunkRead.model_validate(item) for item in chunks]


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: UUID = Form(...),
    owner_user_id: UUID = Form(default=settings.default_owner_user_id),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """上传文件并同步完成最小解析链路。"""

    filename = file.filename or "uploaded.bin"
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.supported_file_types:
        raise HTTPException(status_code=400, detail=f"暂不支持的文件类型: {suffix}")

    file_bytes = await file.read()
    service = DocumentIngestService(db)
    result = service.ingest_bytes(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        filename=filename,
        file_bytes=file_bytes,
        source_type="upload",
    )
    db.commit()

    return DocumentUploadResponse(
        document_id=result.document.id,
        version_id=result.version.id,
        status=result.document.status,
        duplicate_of=result.duplicate_of,
    )


@router.post("/{document_id}/reindex", response_model=DocumentUploadResponse)
def reindex_document(document_id: UUID, db: Session = Depends(get_db)) -> DocumentUploadResponse:
    """手动触发文档 reindex。"""

    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    service = DocumentIndexService(db)
    service.reindex_document(document_id)
    db.commit()
    db.refresh(document)

    return DocumentUploadResponse(
        document_id=document.id,
        version_id=document.latest_version_id,
        status=document.status,
        duplicate_of=None,
    )


@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
def reprocess_document(document_id: UUID, db: Session = Depends(get_db)) -> DocumentUploadResponse:
    """按当前解析与切块规则重新构建指定文档。"""

    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="鏂囨。涓嶅瓨鍦?")

    service = DocumentIngestService(db)
    result = service.reprocess_document(document_id)
    db.commit()

    return DocumentUploadResponse(
        document_id=result.document.id,
        version_id=result.version.id,
        status=result.document.status,
        duplicate_of=None,
    )
