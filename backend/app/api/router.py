"""API 路由聚合入口。"""

from fastapi import APIRouter

from app.api.routes import chat, documents, health, memory, runs, threads, workspaces
from app.core.config import settings

api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(health.router, tags=["health"])
api_router.include_router(workspaces.router, tags=["workspaces"])
api_router.include_router(threads.router, tags=["threads"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(memory.router, tags=["memory"])
api_router.include_router(runs.router, tags=["runs"])
