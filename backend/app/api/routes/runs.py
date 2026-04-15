"""运行记录、Trace 与重试相关路由。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.routes.chat import build_chat_stream_response
from app.db.session import get_db
from app.repositories.run_repository import RunRepository
from app.schemas.chat import ChatResponse
from app.schemas.runs import RunRead, RunStateSnapshotRead, RunStepRead, RunTraceRead
from app.services.chat.service import ChatExecutionError, ChatService
from app.services.chat.stream_control import stream_cancellation_registry

router = APIRouter(prefix="/runs")


@router.get("", response_model=list[RunRead])
def list_runs(workspace_id: UUID, limit: int = 30, db: Session = Depends(get_db)) -> list[RunRead]:
    """返回指定工作区最近的运行记录。"""

    repository = RunRepository(db)
    return [RunRead.model_validate(item) for item in repository.list_by_workspace(workspace_id, limit=limit)]


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> RunRead:
    """返回单条运行摘要。"""

    repository = RunRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return RunRead.model_validate(run)


@router.get("/{run_id}/steps", response_model=list[RunStepRead])
def get_run_steps(run_id: UUID, db: Session = Depends(get_db)) -> list[RunStepRead]:
    """返回指定运行的步骤级 Trace 记录。"""

    repository = RunRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return [RunStepRead.model_validate(item) for item in repository.list_steps(run_id)]


@router.get("/{run_id}/trace", response_model=RunTraceRead)
def get_run_trace(run_id: UUID, db: Session = Depends(get_db)) -> RunTraceRead:
    """返回运行摘要、步骤记录与状态快照。"""

    repository = RunRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return RunTraceRead(
        run=RunRead.model_validate(run),
        steps=[RunStepRead.model_validate(item) for item in repository.list_steps(run_id)],
        snapshots=[RunStateSnapshotRead.model_validate(item) for item in repository.list_snapshots(run_id)],
    )


@router.post("/{run_id}/cancel")
def cancel_run(run_id: UUID, db: Session = Depends(get_db)) -> dict[str, str | bool]:
    """请求取消一个正在流式执行的运行。"""

    repository = RunRepository(db)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")

    accepted = stream_cancellation_registry.cancel(run_id)
    return {
        "run_id": str(run_id),
        "accepted": accepted,
        "status": "正在取消" if accepted else run.status,
    }


@router.post("/{run_id}/retry", response_model=ChatResponse)
def retry_run(run_id: UUID, db: Session = Depends(get_db)) -> ChatResponse:
    """基于当前线程状态重新执行一条历史请求。"""

    service = ChatService(db)
    try:
        payload = service.rebuild_chat_request(run_id)
        response = service.chat(payload)
        db.commit()
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatExecutionError as exc:
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/retry/stream")
def retry_run_stream(run_id: UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """重试一条历史请求，并以流式方式返回新执行过程。"""

    try:
        payload = ChatService(db).rebuild_chat_request(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_chat_stream_response(payload)
