"""工作区仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Workspace, WorkspaceMember
from app.schemas.workspaces import WorkspaceCreate


class WorkspaceRepository:
    """封装工作区表的最小读写操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Workspace]:
        """返回未删除的工作区列表。"""

        stmt = select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.created_at.desc())
        return list(self.db.scalars(stmt))

    def get_by_slug(self, slug: str) -> Workspace | None:
        """根据 slug 查询工作区。"""

        stmt = select(Workspace).where(Workspace.slug == slug, Workspace.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def create(self, payload: WorkspaceCreate) -> Workspace:
        """创建工作区和默认管理员成员。"""

        workspace = Workspace(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            owner_user_id=payload.owner_user_id,
            visibility=payload.visibility,
            status="active",
            settings_json=payload.settings_json,
        )
        self.db.add(workspace)
        self.db.flush()

        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=payload.owner_user_id,
            role="admin",
            status="active",
        )
        self.db.add(member)
        return workspace
