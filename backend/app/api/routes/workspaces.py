"""工作区接口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.workspaces import WorkspaceCreate, WorkspaceRead

router = APIRouter(prefix="/workspaces")


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(db: Session = Depends(get_db)) -> list[WorkspaceRead]:
    """列出当前已有工作区。"""

    repository = WorkspaceRepository(db)
    return [WorkspaceRead.model_validate(item) for item in repository.list_all()]


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)) -> WorkspaceRead:
    """创建一个新的工作区。"""

    repository = WorkspaceRepository(db)
    if repository.get_by_slug(payload.slug):
        raise HTTPException(status_code=409, detail="工作区 slug 已存在")

    workspace = repository.create(payload)
    db.commit()
    db.refresh(workspace)
    return WorkspaceRead.model_validate(workspace)
