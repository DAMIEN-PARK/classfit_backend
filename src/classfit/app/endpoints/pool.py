"""강사 과정 풀 끝점(InstructorCaller, T4 계획 결정 i·vii·ix·xii·xvi).

- GET /v1/pool?source=&job=&difficulty=&q=: 활성 과정만이다(첫 WHERE crud.scope.pool_scope). 한 쪽에 500개까지 주고
  넘으면 has_more 참, 커서는 없다(next_cursor 항상 null, 결정 xii). 순서는 (source, id).
- GET /v1/pool/{pool_id}: 비활성·없는 id 는 404. 파일 목록은 본인 고유 과정일 때만 채운다(결정 ix — 남의 고유 과정은
  내용만, 강사.html:963 poolForMe).
- 남의 고유 과정에도 작성자 칸(강사 id·이름)이 없고 mine 만 있다(기획안 :435 · CAT-004). id 글자의 강사 번호는 결정 xiii.
- 대기·반려 강사도 쓴다(결정 xvi). 승인 여부는 T5 배정이 본다.
- job·difficulty 가 값 집합 밖이면 422 loc ["query", <칸>]. q 는 제목·목표·산출물 부분 일치다.
- 이 파일의 출력 도우미(file_outs·files_by_owner·base_fields·content_fields)는 다른 풀 끝점도 쓴다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import DbSession, InstructorCaller
from classfit.app.endpoints.admin_instructors import query_text
from classfit.core.errors import NotFound
from classfit.crud import capability as crud_capability
from classfit.crud import pool as crud_pool
from classfit.crud import pool_file as crud_pool_file
from classfit.crud.scope import Subject, owned_by
from classfit.models import PoolCourse
from classfit.models.pool import DIFFICULTIES, JOB_GROUPS
from classfit.schemas.page import Page
from classfit.schemas.pool import PoolDetailOut, PoolFileOut, PoolItemOut
from classfit.service.files.store import href_for

router = APIRouter(prefix="/v1", tags=["pool"])

# 풀·커리큘럼·심화 id(ax-…·own-<n>-<n>·cur-<n>-<n>·adv-<n>). 이 모양 밖은 DB 를 치지 않고 같은 404
_TEXT_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_TEXT_ID_MAX = 80

Source = Literal["ax", "own"]


def valid_text_id(value: str) -> bool:
    return len(value) <= _TEXT_ID_MAX and _TEXT_ID.fullmatch(value) is not None


def id_or_404(value: str, message: str) -> str:
    """글자 id 가 모양 밖이면 DB 를 치지 않고 404(없는 id 와 같은 본문)."""
    if not valid_text_id(value):
        raise NotFound(message)
    return value


def _invalid_query(field: str, msg: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": msg, "type": "value_error"}]
    )


def pool_filters(
    job: str | None, difficulty: str | None, q: str | None
) -> tuple[str | None, str | None, str | None]:
    """질의 셋을 다듬는다. job·difficulty 가 값 집합 밖이면 422."""
    job = query_text(job, "job")
    if job is not None and job not in JOB_GROUPS:
        raise _invalid_query("job", "직무군 값 집합 밖입니다")
    if difficulty is not None and difficulty not in DIFFICULTIES:
        raise _invalid_query("difficulty", "난이도는 하·중·상 중 하나입니다")
    return job, difficulty, query_text(q)


def file_outs(rows: Iterable[crud_pool_file.FileRow]) -> list[PoolFileOut]:
    out = []
    for row, key, size in rows:
        href = href_for(key) if key is not None else row.url
        # CHECK target: link 면 url 이 있다. pdf 는 넣기가 file_id 까지 채운다
        if href is None:
            raise RuntimeError(f"풀 파일 {row.id} 에 파일도 주소도 없습니다")
        out.append(
            PoolFileOut(id=row.id, kind=row.kind, title=row.title, href=href, size=size)
        )
    return out


async def files_by_owner(
    session: AsyncSession, owner_kind: str, owner_ids: Iterable[Any]
) -> dict[Any, list[PoolFileOut]]:
    """소유자 id → 파일 출력(sort, id 순). 파일이 없는 소유자는 키가 없다."""
    grouped: dict[Any, list[crud_pool_file.FileRow]] = {}
    for item in await crud_pool_file.list_file_rows(session, owner_kind, owner_ids):
        grouped.setdefault(crud_pool_file.owner_of(item[0]), []).append(item)
    return {owner: file_outs(rows) for owner, rows in grouped.items()}


def base_fields(row: PoolCourse) -> dict[str, Any]:
    """강사용·관리자용 출력이 같이 쓰는 칸(작성자 칸 없음)."""
    return {
        "id": row.id,
        "source": row.source,
        "title": row.title,
        "job_groups": list(row.job_groups),
        "difficulty": row.difficulty,
        "minutes": row.minutes,
        "goal": row.goal,
        "output": row.output,
    }


def content_fields(row: PoolCourse) -> dict[str, Any]:
    return {
        "material": row.material,
        "theory": list(row.theory),
        "practice": list(row.practice),
        "schedule": [list(r) for r in row.schedule],
    }


async def pool_detail_out(
    session: AsyncSession, row: PoolCourse, subject: Subject
) -> PoolDetailOut:
    mine = owned_by(subject, row.owner_instructor_id)
    files = (
        (await files_by_owner(session, "pool_course_file", [row.id])).get(row.id, [])
        if mine
        else []
    )
    capable = (
        await crud_capability.get_capability_any(session, subject.id, row.id)
        is not None
    )
    return PoolDetailOut(
        **base_fields(row),
        **content_fields(row),
        mine=mine,
        capable=capable,
        files=files,
    )


@router.get("/pool", response_model=Page[PoolItemOut])
async def list_pool(
    session: DbSession,
    caller: InstructorCaller,
    source: Source | None = None,
    job: Annotated[str | None, Query(max_length=50)] = None,
    difficulty: Annotated[str | None, Query(max_length=10)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[PoolItemOut]:
    job, difficulty, text = pool_filters(job, difficulty, q)
    stmt = crud_pool.list_stmt(
        caller, source=source, job=job, difficulty=difficulty, q=text
    )
    rows, has_more = await crud_pool.first_page(session, stmt)
    capable = await crud_capability.capable_pool_ids(
        session, caller.id, [r.id for r in rows]
    )
    return Page[PoolItemOut](
        items=[
            PoolItemOut(
                **base_fields(r),
                mine=owned_by(caller, r.owner_instructor_id),
                capable=r.id in capable,
            )
            for r in rows
        ],
        next_cursor=None,
        has_more=has_more,
    )


@router.get(
    "/pool/{pool_id}",
    response_model=PoolDetailOut,
    responses={404: {"description": "없는 과정 · 비활성 과정"}},
)
async def get_pool(
    pool_id: str, session: DbSession, caller: InstructorCaller
) -> PoolDetailOut:
    row = (
        await crud_pool.get_pool_course(session, caller, pool_id)
        if valid_text_id(pool_id)
        else None
    )
    if row is None:
        raise NotFound("과정이 없습니다")
    return await pool_detail_out(session, row, caller)
