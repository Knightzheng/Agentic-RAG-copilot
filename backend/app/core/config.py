"""运行时配置。"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目全局配置对象。"""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Atlas Agentic RAG Copilot"
    api_prefix: str = "/api"
    env: str = "local"
    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/rag_lab")
    local_storage_root: Path = Path("../data/storage")
    default_owner_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    default_workspace_name: str = "Atlas Demo Workspace"
    main_model: str = "qwen3-max"
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "qwen3-rerank"
    dashscope_api_key: str | None = None
    dashscope_chat_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_rerank_url: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    embedding_dimensions: int = 1024
    parser_version: str = "0.1.0"
    supported_file_types: tuple[str, ...] = (".pdf", ".docx", ".pptx", ".md", ".txt")
    parent_chunk_char_limit: int = 2400
    child_chunk_char_limit: int = 900

    @property
    def dashscope_embeddings_url(self) -> str:
        """返回 Embedding 接口地址。"""

        return f"{self.dashscope_chat_base_url.rstrip('/')}/embeddings"

    @property
    def dashscope_chat_url(self) -> str:
        """返回 Chat Completions 接口地址。"""

        return f"{self.dashscope_chat_base_url.rstrip('/')}/chat/completions"

    @property
    def has_dashscope_api_key(self) -> bool:
        """标记当前环境是否已提供百炼 API Key。"""

        return bool(self.dashscope_api_key)


settings = Settings()
