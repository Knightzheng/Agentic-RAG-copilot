"""Memory routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.memory import MemoryCreate, MemoryPinRequest, MemoryRead, MemoryUpdate
from app.services.memory.service import MemoryService

router = APIRouter(prefix="/memory")


@router.get("", response_model=list[MemoryRead])
def list_memory(
    workspace_id: UUID,
    memory_type: str | None = Query(default=None),
    query: str | None = Query(default=None),
    pinned: bool | None = Query(default=None),
    limit: int = Query(default=100, le=200),
    db: Session = Depends(get_db),
) -> list[MemoryRead]:
    """List memories for one workspace."""

    try:
        return MemoryService(db).list_memories(
            workspace_id=workspace_id,
            memory_type=memory_type,
            query=query,
            pinned=pinned,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=MemoryRead)
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db)) -> MemoryRead:
    """Create one memory item."""

    try:
        memory = MemoryService(db).create_memory(payload)
        db.commit()
        return memory
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{memory_id}", response_model=MemoryRead)
def update_memory(memory_id: UUID, payload: MemoryUpdate, db: Session = Depends(get_db)) -> MemoryRead:
    """Update one memory item."""

    try:
        memory = MemoryService(db).update_memory(memory_id, payload)
        db.commit()
        return memory
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def delete_memory(memory_id: UUID, db: Session = Depends(get_db)) -> dict[str, str]:
    """Soft-delete one memory item."""

    try:
        MemoryService(db).delete_memory(memory_id)
        db.commit()
        return {"status": "deleted", "memory_id": str(memory_id)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{memory_id}/pin", response_model=MemoryRead)
def pin_memory(memory_id: UUID, payload: MemoryPinRequest, db: Session = Depends(get_db)) -> MemoryRead:
    """Pin or unpin one memory item."""

    try:
        memory = MemoryService(db).set_pinned(memory_id, pinned=payload.pinned)
        db.commit()
        return memory
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
