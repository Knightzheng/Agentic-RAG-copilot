"""本地文件存储服务。"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import settings


class LocalStorageService:
    """负责把原始文件写入本地目录。"""

    def __init__(self) -> None:
        self.root = (Path(__file__).resolve().parents[4] / settings.local_storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, workspace_id: UUID, document_id: UUID, filename: str, file_bytes: bytes) -> Path:
        """把上传文件保存到本地目录并返回绝对路径。"""

        target_dir = self.root / str(workspace_id) / str(document_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        target_path.write_bytes(file_bytes)
        return target_path
