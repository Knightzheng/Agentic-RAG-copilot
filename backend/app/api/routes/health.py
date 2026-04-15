"""健康检查接口。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """返回简单健康状态。"""

    return {"status": "ok"}
