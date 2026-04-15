"""线程接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.thread_repository import ThreadRepository
from app.schemas.chat import MessageRead, ThreadDetailRead
from app.schemas.threads import ThreadCreate, ThreadRead

router = APIRouter(prefix="/threads")


@router.get("", response_model=list[ThreadRead])
def list_threads(workspace_id: UUID, db: Session = Depends(get_db)) -> list[ThreadRead]:
    """按工作区列出线程。"""

    repository = ThreadRepository(db)
    return [ThreadRead.model_validate(item) for item in repository.list_by_workspace(workspace_id)]


@router.post("", response_model=ThreadRead)
def create_thread(payload: ThreadCreate, db: Session = Depends(get_db)) -> ThreadRead:
    """创建一个最小线程记录。"""

    repository = ThreadRepository(db)
    thread = repository.create(payload)
    db.commit()
    db.refresh(thread)
    return ThreadRead.model_validate(thread)


@router.get("/{thread_id}", response_model=ThreadDetailRead)
def get_thread(thread_id: UUID, db: Session = Depends(get_db)) -> ThreadDetailRead:
    """返回线程详情和消息列表。"""

    repository = ThreadRepository(db)
    thread = repository.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="线程不存在")
    messages = [MessageRead.model_validate(item) for item in repository.list_messages(thread_id)]
    return ThreadDetailRead(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        mode=thread.mode,
        status=thread.status,
        thread_summary=thread.metadata_json.get("thread_summary") if isinstance(thread.metadata_json, dict) else None,
        messages=messages,
    )
