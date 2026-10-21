"""계약 시험 전용 부품: 트랜잭션 경계 회귀. 운영 앱(app/routers.py)에는 절대 등록하지 않는다.

- POST /v1/_probe/audit?fail=none|conflict|crash : 한 행 쓰고 정상 종료 / 도메인 오류 / 처리되지 않은 예외
- POST /v1/_probe/check-violation : course_id 없는 수강생 세션을 flush_or_conflict 로 넣는다(CHECK 23514 → 500)
- POST /v1/_probe/outbox-then-conflict?login_id= : outbox 1행 뒤 같은 아이디 관리자를 넣는다(409 → outbox 도 롤백)
- NestedTxProbe : 응답이 시작되는 순간 연결에 SAVEPOINT 가 남아 있는지(= 요청 트랜잭션이 응답 전에 닫혔는지) 기록
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from classfit.app.deps import DbSession
from classfit.core.errors import Conflict
from classfit.crud.admin import insert_admin
from classfit.crud.audit import insert_audit
from classfit.crud.flush import flush_or_conflict
from classfit.crud.outbox import enqueue
from classfit.models import AuthSession

router = APIRouter(prefix="/v1/_probe", tags=["probe"])


@router.post("/audit")
async def write_then(session: DbSession, fail: str = "none") -> dict[str, int]:
    row = await insert_audit(
        session, actor="probe", action="probe.write", target_type="probe"
    )
    if fail == "conflict":
        raise Conflict("일부러 낸 상태 충돌")
    if fail == "crash":
        raise RuntimeError("일부러 낸 서버 오류")
    return {"id": row.id}


@router.post("/check-violation")
async def check_violation(session: DbSession) -> dict[str, int]:
    row = AuthSession(
        token_hash="probe-check-violation",
        principal_type="learner",
        principal_id=1,
        course_id=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await flush_or_conflict(session, "일부러 낸 CHECK 위반", row)
    return {"id": row.id}


@router.post("/outbox-then-conflict")
async def outbox_then_conflict(session: DbSession, login_id: str) -> dict[str, int]:
    await enqueue(session, kind="probe", params={}, to="a@example.com")
    row = await insert_admin(session, login_id=login_id, password_hash="probe")
    return {"id": row.id}


class NestedTxProbe:
    def __init__(
        self, app: ASGIApp, connection: AsyncConnection, sink: list[bool]
    ) -> None:
        self.app = app
        self.connection = connection
        self.sink = sink

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.sink.append(self.connection.in_nested_transaction())
            await send(message)

        await self.app(scope, receive, send_wrapper)
