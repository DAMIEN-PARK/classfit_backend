"""GET /v1/health — 앱이 떠 있고 DB 에 닿는지."""

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from classfit import __version__
from classfit.app.deps import DbSession
from classfit.core.errors import Unavailable
from classfit.schemas.health import HealthOut

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(session: DbSession) -> HealthOut:
    try:
        await session.execute(text("select 1"))
    except OperationalError as exc:  # 503: 지금 확인 불가. 401 로 뭉개지 않는다
        raise Unavailable("데이터베이스에 지금 연결할 수 없습니다") from exc
    return HealthOut(status="ok", database="ok", version=__version__)
