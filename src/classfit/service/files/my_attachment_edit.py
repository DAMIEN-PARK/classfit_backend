"""강사 첨부 고치기·바꾸기(T6 결정 vii·viii·xi·xii·xv). flush 까지만.

- 판정·잠금은 service.files.my_attachments 와 같다: 범위 없는 getter 로 404 → 내 세션 아님 403 → 강의 행 잠금 →
  첨부·세션을 populate_existing 으로 다시 읽어 404·403 을 다시 본다(재배정·삭제와 엇갈린 쓰기를 막는다).
- PATCH(patch_my_attachment)는 title·description·url·position 이다. url 은 link 만(아니면 409). 정규화한 주소가 지금 값과
  실제로 다르면 origin 을 NULL 로 한다 — 기본 강의안 사본의 주소를 바꾸면 더는 사본이 아니다(결정 viii). position 은
  그 세션 첨부 목록((sort, id) 순)의 0부터 센 자리이고, 잠근 뒤 목록을 다시 읽어 sort 를 0..n-1 로 다시 매긴다.
  바뀐 칸이 없으면 쓰지 않고 audit 도 없다(T2a 멱등 규칙). audit fields 는 바뀐 칸 이름이다(origin 비움은 싣지 않는다).
- 교체(replace_my_file)는 같은 행의 파일만 바꾼다: id·sort·title·description 은 그대로, 같은 종류만(아니면
  FileRejected kind_changed), link 는 409. 바이트 쓰기 → 잠금 → 다시 읽기 → 새 stored_file(owner = 같은 첨부) →
  crud swap_file(file_id 바꿈 · origin NULL · 옛 stored_file 행 삭제, 같은 트랜잭션). 지우는 옛 행은 잠근 뒤 다시 읽은
  file_id 다 — 두 교체가 겹치면 뒤 요청이 앞 요청의 파일 행을 지워 파일 행이 하나로 남는다. 옛 key 의 행이 없으니
  옛 href 는 404 다. audit fields 는 ["file"].
- crud 는 모듈 별칭(crud_*)의 속성으로 부른다(행동 시험의 감싸개, T5 결정 xviii).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import attachment_edit as crud_attachment_edit
from classfit.crud import course as crud_course
from classfit.crud import stored_file as crud_stored_file
from classfit.service.files.attachments import OWNER_KIND, audit_attachment
from classfit.service.files.my_attachments import checked, require_mine
from classfit.service.files.store import store_bytes
from classfit.service.rules.attachment import reordered

MY_ATTACHMENT_FIELDS = frozenset({"title", "description", "url", "position"})
# link 첨부 :replace 의 409 문구(끝점의 미리 판정도 이 글자를 쓴다)
LINK_REPLACE_REFUSED = "링크 첨부는 파일로 바꿀 수 없습니다(주소는 PATCH url)"
_NO_ATTACHMENT = "첨부가 없습니다"


async def patch_my_attachment(
    session: AsyncSession,
    *,
    instructor_id: int,
    attachment_id: int,
    changes: dict[str, Any],
    actor: str,
) -> crud_attachment.AttachmentRow:
    """제목·설명·주소·자리를 바꾼다. (첨부, 파일 key, 크기). 없으면 404, 내 세션이 아니면 403, link 아닌 url 은 409."""
    if unknown := set(changes) - MY_ATTACHMENT_FIELDS:
        raise ValueError(f"강사가 고칠 수 없는 칸: {sorted(unknown)}")
    found = await crud_attachment_edit.get_with_session(session, attachment_id)
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    require_mine(found[1], instructor_id)
    if await crud_course.lock_course(session, found[2]) is None:
        raise NotFound(_NO_ATTACHMENT)
    found = await crud_attachment_edit.get_with_session(
        session, attachment_id, fresh=True
    )
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    row, owner, _ = found
    require_mine(owner, instructor_id)
    if "url" in changes and row.kind != "link":
        raise Conflict("주소는 링크 첨부만 바꿀 수 있습니다")
    fields = {k: changes[k] for k in ("title", "description", "url") if k in changes}
    changed = await crud_attachment_edit.apply_changes(session, row, fields)
    if "url" in changed:
        await crud_attachment_edit.apply_changes(session, row, {"origin": None})
    if "position" in changes:
        rows = await crud_attachment_edit.rows_for_session(session, row.session_id)
        ids = [r.id for r in rows]
        order = reordered(ids, row.id, changes["position"])
        if order != ids:
            by_id = {r.id: r for r in rows}
            await crud_attachment_edit.set_sorts(session, [by_id[i] for i in order])
            changed.append("position")
    if changed:
        await audit_attachment(
            session,
            actor=actor,
            action="session_attachment.update",
            attachment_id=row.id,
            session_id=row.session_id,
            kind=row.kind,
            fields=changed,
        )
    return await crud_attachment_edit.with_file(session, row)


async def replace_my_file(
    session: AsyncSession,
    *,
    root: Path,
    max_bytes: Mapping[str, int],
    instructor_id: int,
    attachment_id: int,
    filename: str,
    data: bytes,
    actor: str,
) -> crud_attachment.AttachmentRow:
    """그 첨부의 파일을 같은 종류의 새 파일로 바꾼다. (첨부, 새 key, 크기).

    없으면 404, 내 세션이 아니면 403, link 는 409, 모양·종류·크기가 틀리면 FileRejected(바이트를 쓰기 전).
    """
    found = await crud_attachment_edit.get_with_session(session, attachment_id)
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    require_mine(found[1], instructor_id)
    if found[0].kind == "link":
        raise Conflict(LINK_REPLACE_REFUSED)
    kind, content_type = checked(filename, data, max_bytes, expect_kind=found[0].kind)
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    if await crud_course.lock_course(session, found[2]) is None:
        raise NotFound(_NO_ATTACHMENT)
    found = await crud_attachment_edit.get_with_session(
        session, attachment_id, fresh=True
    )
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    row, owner, _ = found
    require_mine(owner, instructor_id)
    stored = await crud_stored_file.insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=OWNER_KIND,
        owner_id=row.id,
        content_type=content_type,
        size=len(data),
    )
    await crud_attachment_edit.swap_file(session, row, stored.id)
    await audit_attachment(
        session,
        actor=actor,
        action="session_attachment.update",
        attachment_id=row.id,
        session_id=row.session_id,
        kind=kind,
        fields=["file"],
    )
    return row, stored.key, stored.size
