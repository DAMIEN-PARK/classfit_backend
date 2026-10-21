"""계약 시험 전용 부품: 트랜잭션 경계 회귀. 운영 앱(app/routers.py)에는 절대 등록하지 않는다.

- POST /v1/_probe/audit?fail=none|conflict|crash : 한 행 쓰고 정상 종료 / 도메인 오류 / 처리되지 않은 예외
- NestedTxProbe : 응답이 시작되는 순간 연결에 SAVEPOINT 가 남아 있는지(= 요청 트랜잭션이 응답 전에 닫혔는지) 기록
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from classfit.app.deps import DbSession
from classfit.core.errors import Conflict
from classfit.crud.audit import insert_audit

router = APIRouter(prefix="/v1/_probe", tags=["probe"])


@router.post("/audit")
async def write_then(session: DbSession, fail: str = "none") -> dict[str, int]:
    row = await insert_audit(session, actor="probe", action="probe.write", target_type="probe")
    if fail == "conflict":
        raise Conflict("일부러 낸 상태 충돌")
    if fail == "crash":
        raise RuntimeError("일부러 낸 서버 오류")
    return {"id": row.id}


class NestedTxProbe:
    def __init__(self, app: ASGIApp, connection: AsyncConnection, sink: list[bool]) -> None:
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
