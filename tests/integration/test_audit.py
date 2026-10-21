"""crud.audit 와 마이그레이션 0001. 라이브 PG."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.crud.audit import insert_audit
from classfit.models import AuditLog


async def test_insert_audit_flushes_and_fetches_server_defaults(db_session: AsyncSession) -> None:
    row = await insert_audit(
        db_session, actor="system", action="test.ping", target_type="none", detail={"k": 1}
    )
    assert row.id > 0
    assert row.at is not None  # server_default 를 RETURNING 으로 받아 온다 (async 에서 lazy load 금지)
    assert row.detail == {"k": 1}


async def test_previous_test_was_rolled_back(db_session: AsyncSession) -> None:
    count = await db_session.scalar(select(func.count()).select_from(AuditLog))
    assert count == 0


async def test_constraint_names_follow_convention(db_connection: AsyncConnection) -> None:
    rows = await db_connection.execute(
        text("select conname from pg_constraint where conrelid = 'audit_log'::regclass")
    )
    assert "pk_audit_log" in set(rows.scalars().all())
    rows = await db_connection.execute(
        text("select indexname from pg_indexes where tablename = 'audit_log'")
    )
    assert {"ix_audit_log_at", "ix_audit_log_target"} <= set(rows.scalars().all())
