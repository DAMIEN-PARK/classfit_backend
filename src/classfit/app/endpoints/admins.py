"""관리자 계정 끝점: POST /v1/admin/admins (관리자만). 같은 아이디는 409, audit_log 1행을 같은 트랜잭션에."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession
from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from classfit.crud.audit import insert_audit
from classfit.schemas.admin import AdminCreateIn, AdminOut

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post(
    "/admins",
    response_model=AdminOut,
    status_code=201,
    responses={409: {"description": "같은 아이디의 관리자가 이미 있음"}},
)
async def create_admin(
    body: AdminCreateIn, session: DbSession, caller: AdminCaller
) -> AdminOut:
    password_hash = await asyncio.to_thread(hash_password, body.password)
    row = await insert_admin(
        session, login_id=body.login_id, password_hash=password_hash
    )
    await insert_audit(
        session,
        actor=f"admin:{caller.id}",
        action="admin.create",
        target_type="admin_account",
        target_id=str(row.id),
    )
    return AdminOut.model_validate(row)
