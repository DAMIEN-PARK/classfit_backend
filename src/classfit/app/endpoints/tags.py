"""태그 끝점(T3 계획 결정 xi): 공개 검색 · 관리자 목록·추가·수정.

- GET /v1/tags?kind=field&q=(인증 없음): 사용 중인 태그만 이름 부분 일치로 최대 20개. 더 있으면 has_more 참이고
  커서는 없다(next_cursor 항상 null) — 손님은 q 를 좁힌다. 가입 화면 자동완성용이다.
- GET /v1/admin/tags?kind=: 사용 중지 포함 최대 500개 + 태그마다 단 강사 수(used_by). 같은 규칙으로 has_more.
- POST /v1/admin/tags: 관리자 추가(source admin, field 태그의 대분류 기본 "기타"). 같은 (kind, 정규화한 이름)은 409.
- PATCH /v1/admin/tags/{tag_id}: 이름·대분류·사용 여부. 이름을 바꾸면 FK 라 모든 프로필에 반영된다. 사용 중지한 태그는
  새로 붙일 수 없고 이미 붙은 프로필에는 남는다. 바뀐 칸이 있을 때만 audit tag.update 1행(T2a 멱등 규칙).
- 이름 정규화(앞뒤 공백 제거 + 연속 공백 하나)는 crud.tag.normalize_tag_name 한 곳이다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import AdminCaller, DbSession, IdPath
from classfit.app.endpoints.admin_instructors import query_text
from classfit.core.errors import NotFound
from classfit.crud import tag as crud_tag
from classfit.crud.audit import insert_audit
from classfit.models import Tag
from classfit.schemas.page import Page
from classfit.schemas.tag import TagAdminOut, TagCreateIn, TagKind, TagOut, TagPatchIn

router = APIRouter(prefix="/v1", tags=["tags"])

PUBLIC_LIMIT = 20
ADMIN_LIMIT = 500
# 스키마 칸 이름 → 표 칸 이름(group 은 PG 예약어라 표에서는 group_name)
_COLUMNS = {"name": "name", "group": "group_name", "active": "active"}


def tag_out(row: Tag) -> TagOut:
    return TagOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        group=row.group_name,
        active=row.active,
        source=row.source,
    )


def admin_tag_out(row: Tag, used_by: int) -> TagAdminOut:
    return TagAdminOut(**tag_out(row).model_dump(), used_by=used_by)


@router.get("/tags", response_model=Page[TagOut])
async def search_tags(
    session: DbSession,
    kind: TagKind = "field",
    q: Annotated[str | None, Query(max_length=30)] = None,
) -> Page[TagOut]:
    rows, has_more = await crud_tag.list_tags(
        session, kind=kind, q=query_text(q), active_only=True, limit=PUBLIC_LIMIT
    )
    return Page[TagOut](
        items=[tag_out(r) for r in rows], next_cursor=None, has_more=has_more
    )


@router.get("/admin/tags", response_model=Page[TagAdminOut])
async def list_admin_tags(
    session: DbSession, _: AdminCaller, kind: TagKind = "field"
) -> Page[TagAdminOut]:
    rows, has_more = await crud_tag.list_tags(
        session, kind=kind, q=None, active_only=False, limit=ADMIN_LIMIT
    )
    used = await crud_tag.usage_counts(session, [r.id for r in rows])
    return Page[TagAdminOut](
        items=[admin_tag_out(r, used.get(r.id, 0)) for r in rows],
        next_cursor=None,
        has_more=has_more,
    )


@router.post(
    "/admin/tags",
    response_model=TagAdminOut,
    status_code=201,
    responses={409: {"description": "같은 종류에 같은 이름이 있음"}},
)
async def create_tag(
    body: TagCreateIn, session: DbSession, caller: AdminCaller
) -> TagAdminOut:
    row = await crud_tag.insert_tag(
        session,
        kind=body.kind,
        name=crud_tag.normalize_tag_name(body.name),
        group_name=body.group,
        source="admin",
    )
    await insert_audit(
        session,
        actor=f"admin:{caller.id}",
        action="tag.create",
        target_type="tag",
        target_id=str(row.id),
        detail={"kind": row.kind, "name": row.name},
    )
    return admin_tag_out(row, 0)


@router.patch(
    "/admin/tags/{tag_id}",
    response_model=TagAdminOut,
    responses={
        404: {"description": "태그가 없음"},
        409: {"description": "바꾼 이름이 같은 종류에 이미 있음"},
        422: {"description": "본문 모양 · field 가 아닌 태그에 대분류"},
    },
)
async def patch_tag(
    tag_id: IdPath, body: TagPatchIn, session: DbSession, caller: AdminCaller
) -> TagAdminOut:
    row = await crud_tag.get_tag(session, tag_id)
    if row is None:
        raise NotFound("태그가 없습니다")
    changes = body.changes()
    if "group" in changes and row.kind != "field":
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "group"),
                    "msg": "대분류는 field 태그에만 있습니다",
                    "type": "value_error",
                }
            ]
        )
    if "name" in changes:
        changes["name"] = crud_tag.normalize_tag_name(changes["name"])
    fields = await crud_tag.update_tag(
        session, row, **{_COLUMNS[k]: v for k, v in changes.items()}
    )
    if fields:
        await insert_audit(
            session,
            actor=f"admin:{caller.id}",
            action="tag.update",
            target_type="tag",
            target_id=str(row.id),
            detail={"fields": fields},
        )
    used = await crud_tag.usage_counts(session, [row.id])
    return admin_tag_out(row, used.get(row.id, 0))
