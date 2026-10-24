"""요청 단위 의존성: 세션(= 트랜잭션) · 인증 주체 · 오늘 날짜.

- 인증은 `Authorization: Bearer <불투명 토큰>` 하나다(관리자·강사·수강생 공용 auth_session).
  헤더 없음·모양 틀림·없는 토큰·폐기·만료는 전부 401 + WWW-Authenticate: Bearer.
- 권한은 타입 별칭으로 건다: CurrentPrincipal(로그인만) · AdminCaller(관리자, 아니면 403) ·
  LearnerCaller(수강생, 아니면 403) · InstructorCaller(강사, 아니면 403). 수강생 주체는 토큰의 강의 하나에
  묶인다(ADR-002 결정 1). LearnerCaller 는 learner 행을 찾지 않는다. 세션 행의 (principal_id, course_id) 가 주체다.
- InstructorCaller 도 instructor 행을 읽지 않는다(T3 계획 결정 v). 정지(:suspend)가 그 강사의 산 세션을 전부
  폐기하므로 정지된 강사의 옛 토큰은 401 이다. 대기·반려 강사도 통과한다(승인 여부는 배정·첨부 태스크가 본다).
- 날짜는 Today(Asia/Seoul) 한 곳에서 받는다. 시험은 app.dependency_overrides[today] 로 주입한다.
- JSON 본문에 상한을 둘 끝점은 본문 매개변수 대신 limited_json(모델, 상한) 의존성을 인증 의존성 뒤에 둔다(T8 결정 ix).
- 토큰 전체가 실리는 응답(로그인 둘 · 입장 · 회사 상세 GET·PATCH · 진단 링크 발급)은 데코레이터 dependencies 에
  no_store 를 둔다(T11 결정 ii — Cache-Control: no-store).
- 정수 경로 매개변수는 IdPath(행 id, 1 ≤ id < 2**63) · DayPath(일차 번호 1..60) 로만 받는다(T11 결정 iv — 밖이면
  자원 질의 전에 422 loc ["path", <이름>], DB 의 BIGINT DataError 500 이 없다).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import Depends, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.errors import AppError, forbidden, unauthorized
from classfit.core.clock import today_kst
from classfit.schemas.course import DB_ID_LIMIT
from classfit.service.auth.sessions import Principal, authenticate

# token_urlsafe 글자만, 길이 상한. 모양이 틀리면 DB 를 보지 않고 401
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")
# limited_json 이 받는 미디어 타입(매개변수 앞 · 소문자): application/json · application/<x>+json
_JSON_MEDIA = re.compile(r"application/(?:json|[^/\s]+\+json)")


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """요청 1개 = 트랜잭션 1개. 핸들러가 정상 종료하면 커밋, 예외면 롤백.

    scope="function": 응답을 보내기 전에 커밋한다(yield 의존성 기본값은 응답 뒤에 닫혀서,
    302 를 따라온 다음 요청이 방금 쓴 것을 못 본다).
    """
    factory = request.app.state.session_factory
    if factory is None:
        raise RuntimeError(
            "미구성: app.state.session_factory 가 없습니다 (lifespan 또는 시험이 채운다)"
        )
    async with factory() as session, session.begin():
        yield session


DbSession = Annotated[AsyncSession, Depends(db, scope="function")]


def bearer_token(request: Request) -> str:
    """Authorization 헤더의 토큰 글자. 헤더가 없거나 모양이 틀리면 401."""
    header = request.headers.get("authorization")
    if header is None:
        raise unauthorized()
    scheme, _, token = header.strip().partition(" ")
    if scheme.lower() != "bearer" or not _TOKEN.fullmatch(token.strip()):
        raise unauthorized("Authorization 헤더 모양이 틀렸습니다 (Bearer <토큰>)")
    return token.strip()


async def bearer_principal(request: Request, session: DbSession) -> Principal:
    principal = await authenticate(session, bearer_token(request))
    if principal is None:
        raise unauthorized("토큰이 없거나 폐기·만료됐습니다")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(bearer_principal)]


async def require_admin(principal: CurrentPrincipal) -> Principal:
    if principal.type != "admin":
        raise forbidden("관리자만 할 수 있습니다")
    return principal


AdminCaller = Annotated[Principal, Depends(require_admin)]


async def require_learner(principal: CurrentPrincipal) -> Principal:
    if principal.type != "learner" or principal.course_id is None:
        raise forbidden("수강생만 할 수 있습니다")
    return principal


LearnerCaller = Annotated[Principal, Depends(require_learner)]


async def require_instructor(principal: CurrentPrincipal) -> Principal:
    if principal.type != "instructor":
        raise forbidden("강사만 할 수 있습니다")
    return principal


InstructorCaller = Annotated[Principal, Depends(require_instructor)]


def today() -> date:
    return today_kst()


Today = Annotated[date, Depends(today)]

# 경로의 행 id(BIGINT, T5 에서 옮김). 범위 밖은 DB 를 치지 않고 422 loc ["path", <이름>] 다(본문 DbId 와 같은 상한)
IdPath = Annotated[int, Path(ge=1, lt=DB_ID_LIMIT)]
# 일차 번호 경로(본문 DayNo 1..60 의 경로 판, T7 에서 옮김). 밖이면 DB 를 치지 않고 422 loc ["path", "day_no"]
DayPath = Annotated[int, Path(ge=1, le=60)]


def no_store(response: Response) -> None:
    """응답 헤더만 단다(인증·자원 판정과 순서 무관). FastAPI 는 핸들러가 모델을 돌려줄 때만 이 헤더를 합친다
    (fastapi/routing.py:790) — problem 응답(오류 · 로그인 실패)에는 붙지 않는다."""
    response.headers["Cache-Control"] = "no-store"


def limited_json[M: BaseModel](
    model: type[M], max_bytes: int
) -> Callable[[Request], Awaitable[M]]:
    """JSON 본문을 max_bytes 까지만 읽어 model 로 검증하는 함수(의존성)를 만든다(T8 결정 ix · T9b 재사용).

    FastAPI 가 핸들러 전에 읽는 JSON 본문에 상한을 두는 유일한 자리다(fastapi/routing.py:455-471·511 — 본문 매개변수를
    선언하면 통째로 읽는다). 폼은 request.form(max_files…)(T2b), JSON 은 이것이다.
    ① Content-Length 가 상한을 넘으면 읽기 전에 413 ② 스트림을 읽으며 누적 + 이번 청크 길이를 버퍼에 복사하기 전에 잰다 —
    넘으면 그 청크를 버리고 413(ASGI 청크는 통째로 오므로 "상한 + 1 바이트만 읽기" 가 아니다) ③ model_validate_json 이
    JSON 파싱과 검증을 한 번에 한다(깊은 중첩도 json_invalid 422 — json.loads 의 RecursionError 500 이 없다) ④ 검증
    실패는 loc 앞에 "body" 를 붙인 422 violations. 413 type 은 /problems/content-too-large 다. ⑤ 본문을 읽기 전에
    Content-Type 이 JSON(application/json · application/<x>+json — 매개변수 charset 등은 보지 않고 대소문자 무시)이
    아니면 415 /problems/unsupported-media-type 다(헤더 없음 포함 — T9b 결정 xxiii ⑤). 순서는 ⑤ → ① → ② → ③·④ 다.
    끝점은 Depends(limited_json(…)) 를 인증 의존성 뒤에 선언하고(401·403 이 먼저) openapi_extra 의 requestBody
    (required · model.model_json_schema())로 스키마를 남긴다. 설정 상한은 요청 때 await limited_json(M, n)(request) 로
    부른다. 안에서 Depends 를 쓰지 않는 순수 함수다.
    """

    async def _read(request: Request) -> M:
        media = (
            request.headers.get("content-type", "").partition(";")[0].strip().lower()
        )
        if not _JSON_MEDIA.fullmatch(media):
            raise AppError(415, "JSON 본문만 받습니다(Content-Type: application/json)")
        declared = request.headers.get("content-length", "").strip()
        # isdigit 은 '²' 같은 비 ASCII 숫자도 참이라 int() 가 ValueError 다 — ASCII 숫자만 믿고 나머지는 스트림 가드에 맡긴다
        if declared.isascii() and declared.isdigit() and int(declared) > max_bytes:
            raise _too_large(max_bytes)
        buf = bytearray()
        async for chunk in request.stream():
            if len(buf) + len(chunk) > max_bytes:
                raise _too_large(max_bytes)
            buf += chunk
        try:
            return model.model_validate_json(bytes(buf))
        except ValidationError as exc:
            raise RequestValidationError(
                [
                    {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ]
            ) from None

    return _read


def _too_large(max_bytes: int) -> AppError:
    return AppError(413, f"본문이 너무 큽니다({max_bytes}바이트까지)")
