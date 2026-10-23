"""교육 기록: 상태 전이표 행마다 · 계획대로 기록 · 일괄 확인 · 목록 범위 · 포털 비노출 · 홈 미기록
(T7 계획 결정 i·iii·v·vi·x·xi·xv·xvii·xxi·xxii · 증명 1~9·11~13).

전이(결정 iii): 강사 저장 none → done(R1) · 바뀐 칸이 있으면 done(R2·R3 — 확인된 기록도 done 으로) · 바뀐 칸이 없으면
그대로(R4) · 관리자 저장 ok(R5) · 확인 done → ok(R6) · ok 그대로(R7) · 기록 없음 409(R8) · 계획대로는 기록 없는 세션만
(R9~R12) · 일괄 확인은 done 만(R13·R14) · 남의 세션 403(R15) · 모양 밖 422(R16) · 예정 일차 계획대로 409(R17).
바뀐 것이 있는 쓰기마다 audit 1행이다. 응답은 허용 키 집합을 정확히 잰다. 픽스처 강의는 2026-11-02(월)부터 평일 2일,
하루 13:00~17:00(50분 + 10분 → 4교시)이다. 강사 이름은 make_instructor 의 "강사" 다.
"""

from datetime import date, time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud.instructor import lock_instructor, update_instructor
from classfit.models import AuditLog, SessionRecord
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.courses import admin_headers, learner_headers
from tests.fixtures.enter import (
    add_pdf,
    add_section,
    add_session,
    bearer,
    enter_learner,
    json_keys,
)
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.records import (
    ADMIN_PHOTO_KEYS,
    ADMIN_SESSION_KEYS,
    IMAGES,
    MY_PHOTO_KEYS,
    MY_SESSION_KEYS,
    RECORD_BODY,
    RECORD_FIELD_KEYS,
    RECORD_KEYS,
    SUMMARY_KEYS,
    Assigned,
    assigned,
    put_record,
    set_today,
    upload_photo,
)

ADMIN = "/v1/admin"
ME = "/v1/me"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
DAY1 = date(
    2026, 11, 2
)  # 시험 강의 1일차. 이 날을 오늘로 두면 1일차는 지났고(≤ 오늘) 2일차(11-03)는 예정이다
X_NAME = "강사"  # make_instructor 가 주는 이름
Y_NAME = "이가명"
# 저장 본문 여섯 칸(service.rules.record.RecordFields 차례) — 없던 기록을 쓰면 audit fields 가 이 여섯이다
SIX = ["held_on", "start_time", "end_time", "attendees", "content", "note"]
RECORD_ACTIONS = (
    "session_record.save",
    "session_record.confirm",
    "course_day.record_as_planned",
    "course_day.confirm_all",
)
PRIVATE_KEYS = {"email", "phone", "learner_id", "enrollment_id", "dept", "public"}
LIST_KEYS = {"course_id", "summary", "sessions"}
# 포털 응답의 허용 키(T5 test_assign_portal_instructor_name 과 같은 집합)
TOP_KEYS = {"course", "sections"}
COURSE_KEYS = {"id", "title", "start_on", "end_on", "status", "intro", "notice"}
SECTION_KEYS = {"id", "title", "description", "sessions"}
CARD_KEYS = {
    "id",
    "title",
    "day_no",
    "date",
    "start",
    "end",
    "state",
    "description",
    "keywords",
    "attachments",
    "instructor_name",
}
ATTACHMENT_KEYS = {"id", "kind", "title", "description", "href", "size"}
# 강사 홈 할 일 항목(T6 MyTodoOut) — 미기록 항목도 같은 모양이다
TODO_KEYS = {
    "course_id",
    "course_title",
    "section_id",
    "section_title",
    "session_id",
    "session_title",
    "day_no",
    "slot",
}


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _ok(r: httpx.Response) -> Any:
    assert r.status_code == 200, (r.request.method, r.request.url, r.text)
    return r.json()


async def _assign(
    client: httpx.AsyncClient, admin: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=admin, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _owned(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    course_id: int,
    section_id: int,
    iid: int | None,
    **fields: Any,
) -> int:
    """관리자 API 로 세션을 만들고 iid 에게 배정한다(None 이면 미배정)."""
    sid = await add_session(client, admin, course_id, section_id=section_id, **fields)
    if iid is not None:
        await _assign(client, admin, sid, iid)
    return sid


async def _session(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    me: Assigned,
    iid: int | None,
    **fields: Any,
) -> int:
    """me 의 강의·섹션에 세션 하나."""
    return await _owned(client, admin, me.course_id, me.section_id, iid, **fields)


async def _admin_put(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: int, **over: Any
) -> httpx.Response:
    return await client.put(
        f"{ADMIN}/sessions/{session_id}/record",
        headers=headers,
        json={**RECORD_BODY, **over},
    )


async def _confirm(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: int
) -> httpx.Response:
    return await client.post(
        f"{ADMIN}/sessions/{session_id}/record:confirm", headers=headers
    )


async def _audits(session: AsyncSession, action: str) -> list[tuple[Any, ...]]:
    """그 action 의 (actor, target_id, detail), id 순."""
    rows = await session.execute(
        select(AuditLog.actor, AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _written(session: AsyncSession) -> tuple[int, int]:
    """(기록 행, 기록 audit) 수."""
    return (
        await count(session, SessionRecord),
        await count(session, AuditLog, AuditLog.action.in_(RECORD_ACTIONS)),
    )


async def _records(session: AsyncSession) -> dict[int, Row[Any]]:
    """세션 id → 기록 칸(ORM 객체가 아니라 칸 값 — 요청이 고친 값을 그대로 읽는다)."""
    rows = await session.execute(
        select(
            SessionRecord.session_id,
            SessionRecord.status,
            SessionRecord.held_on,
            SessionRecord.start_time,
            SessionRecord.end_time,
            SessionRecord.attendees,
            SessionRecord.content,
            SessionRecord.note,
            SessionRecord.recorded_by_kind,
            SessionRecord.confirmed_at,
        )
    )
    return {r.session_id: r for r in rows}


def _clock(value: str | None) -> time | None:
    return None if value is None else time.fromisoformat(value)


async def _code(
    client: httpx.AsyncClient, admin: dict[str, str], course_id: int
) -> str:
    r = await client.get(f"{ADMIN}/courses/{course_id}/invite-code", headers=admin)
    code: str = _ok(r)["code"]
    return code


async def _rename(session: AsyncSession, instructor_id: int, name: str) -> None:
    row = await lock_instructor(session, instructor_id)
    assert row is not None
    await update_instructor(session, row, name=name)


async def _upload_id(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: int, n: int
) -> int:
    """사진마다 다른 바이트(같은 sha 로 합쳐지지 않게)."""
    data = IMAGES[".png"] + f"-records-{n}".encode()
    r = await upload_photo(client, headers, session_id, f"{n}.png", data)
    assert r.status_code == 201, r.text
    photo_id: int = r.json()["id"]
    return photo_id


async def test_record_instructor_put_creates_done(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    actor = f"instructor:{me.instructor_id}"

    body = _ok(await put_record(client, me.headers, me.session_id))  # R1 none → done
    assert set(body) == RECORD_KEYS
    assert body["recorded_at"] is not None
    assert {k: v for k, v in body.items() if k != "recorded_at"} == {
        "session_id": me.session_id,
        "status": "done",
        "held_on": "2026-11-02",
        "start_time": "13:00:00",
        "end_time": "13:50:00",
        "attendees": 3,
        "content": "실제 진행",
        "note": None,
        "recorded_by": "instructor",
        "recorded_by_name": X_NAME,
        "confirmed_at": None,
    }
    body = _ok(  # R2 done → done(내용 바뀜)
        await put_record(
            client, me.headers, me.session_id, content="바꾼 진행 내용", note="비고"
        )
    )
    assert (body["status"], body["content"], body["note"], body["confirmed_at"]) == (
        "done",
        "바꾼 진행 내용",
        "비고",
        None,
    )
    assert await _audits(db_session, "session_record.save") == [
        (actor, str(me.session_id), {"from": "none", "to": "done", "fields": SIX}),
        (
            actor,
            str(me.session_id),
            {"from": "done", "to": "done", "fields": ["content", "note"]},
        ),
    ]
    assert await count(db_session, SessionRecord) == 1

    # 저장은 일정 날짜를 보지 않는다 — 예정 차시·일차 미정 세션도, 오늘보다 뒤 실시일도 받는다(결정 v)
    set_today(app, DAY1)
    future = await _session(
        client, admin, me, me.instructor_id, title="2일차", day_no=2, slot=1
    )
    undated = await _session(client, admin, me, me.instructor_id, title="미정")
    for sid in (future, undated):  # 공백뿐인 비고는 null 이다
        body = _ok(
            await put_record(client, me.headers, sid, held_on="2026-11-20", note="  ")
        )
        assert (body["session_id"], body["status"], body["held_on"], body["note"]) == (
            sid,
            "done",
            "2026-11-20",
            None,
        )


async def test_record_identical_put_keeps_status(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    _ok(await put_record(client, me.headers, me.session_id, note="비고"))
    # 같은 값 — 진행 내용·비고는 앞뒤 공백만, 시각은 초까지 쓴 글자만 다르다
    same = {"content": "  실제 진행 \n", "start_time": "13:00:00", "note": " 비고\t"}

    body = _ok(await put_record(client, me.headers, me.session_id, **same))  # R4 done
    assert (body["status"], body["content"], body["start_time"], body["note"]) == (
        "done",
        "실제 진행",
        "13:00:00",
        "비고",
    )
    assert len(await _audits(db_session, "session_record.save")) == 1

    confirmed = _ok(await _confirm(client, admin, me.session_id))
    assert confirmed["status"] == "ok"
    body = _ok(await put_record(client, me.headers, me.session_id, **same))  # R4 ok
    assert body == confirmed  # 확인이 그대로다(confirmed_at 포함)
    assert len(await _audits(db_session, "session_record.save")) == 1
    assert (await _records(db_session))[me.session_id].status == "ok"


async def test_record_confirm_then_instructor_edit_done(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    admin_id, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    _ok(await put_record(client, me.headers, me.session_id))

    body = _ok(await _confirm(client, admin, me.session_id))  # R6 done → ok
    assert set(body) == RECORD_KEYS
    assert (body["status"], body["recorded_by"], body["recorded_by_name"]) == (
        "ok",
        "instructor",  # 기록자는 그대로다
        X_NAME,
    )
    assert body["confirmed_at"] is not None
    confirm = [(f"admin:{admin_id}", str(me.session_id), {"from": "done", "to": "ok"})]
    assert await _audits(db_session, "session_record.confirm") == confirm

    assert _ok(await _confirm(client, admin, me.session_id)) == body  # R7 ok 그대로
    assert await _audits(db_session, "session_record.confirm") == confirm

    body = _ok(  # R3 확인 뒤 강사가 고치면 done(UAT-011)
        await put_record(
            client, me.headers, me.session_id, start_time="13:10", end_time="14:00"
        )
    )
    assert (
        body["status"],
        body["confirmed_at"],
        body["start_time"],
        body["end_time"],
    ) == ("done", None, "13:10:00", "14:00:00")
    assert (await _audits(db_session, "session_record.save"))[-1] == (
        f"instructor:{me.instructor_id}",
        str(me.session_id),
        {"from": "ok", "to": "done", "fields": ["start_time", "end_time"]},
    )


async def test_record_admin_put_ok(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    admin_id, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    by_admin, by_x = f"admin:{admin_id}", f"instructor:{me.instructor_id}"

    body = _ok(await _admin_put(client, admin, me.session_id))  # none → ok
    assert set(body) == RECORD_KEYS
    assert (body["status"], body["recorded_by"], body["recorded_by_name"]) == (
        "ok",
        "admin",
        None,  # 관리자는 이름 칸이 없다(역할만)
    )
    assert body["confirmed_at"] is not None

    done = await _session(
        client, admin, me, me.instructor_id, title="강사 기록", day_no=1, slot=2
    )
    _ok(await put_record(client, me.headers, done))
    body = _ok(await _admin_put(client, admin, done, content="관리자가 고침"))
    assert (body["status"], body["recorded_by"], body["content"]) == (
        "ok",
        "admin",
        "관리자가 고침",
    )
    assert _ok(await _admin_put(client, admin, done, content="관리자가 고침")) == body
    body = _ok(
        await _admin_put(client, admin, done, content="관리자가 고침", attendees=5)
    )
    assert (body["status"], body["attendees"]) == ("ok", 5)

    same = await _session(
        client, admin, me, me.instructor_id, title="같은 칸", day_no=1, slot=3
    )
    _ok(await put_record(client, me.headers, same))
    body = _ok(await _admin_put(client, admin, same))  # 강사 done 에 같은 칸 → ok
    assert (body["status"], body["recorded_by"]) == ("ok", "admin")

    nobody = await _session(client, admin, me, None, title="미배정", day_no=2, slot=1)
    assert _ok(await _admin_put(client, admin, nobody))["status"] == "ok"

    assert await _audits(db_session, "session_record.save") == [
        (by_admin, str(me.session_id), {"from": "none", "to": "ok", "fields": SIX}),
        (by_x, str(done), {"from": "none", "to": "done", "fields": SIX}),
        (by_admin, str(done), {"from": "done", "to": "ok", "fields": ["content"]}),
        # ok 에 같은 값은 audit 이 없다
        (by_admin, str(done), {"from": "ok", "to": "ok", "fields": ["attendees"]}),
        (by_x, str(same), {"from": "none", "to": "done", "fields": SIX}),
        (by_admin, str(same), {"from": "done", "to": "ok", "fields": []}),
        (by_admin, str(nobody), {"from": "none", "to": "ok", "fields": SIX}),
    ]


async def test_record_confirm_without_record_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    assert await _written(db_session) == (0, 0)

    problem_of(await _confirm(client, admin, me.session_id), 409, "/problems/conflict")
    for r in (
        await _confirm(client, admin, LARGEST),
        await _admin_put(client, admin, LARGEST),
        await put_record(client, me.headers, LARGEST),
    ):
        problem_of(r, 404, "/problems/not_found")
    for r in (
        await _confirm(client, admin, OVERFLOW),
        await _admin_put(client, admin, OVERFLOW),
        await put_record(client, me.headers, OVERFLOW),
    ):
        body = problem_of(r, 422)
        assert locs(body) == [["path", "session_id"]], r.request.url
        assert [v["type"] for v in body["violations"]] == ["less_than"]
    assert await _written(db_session) == (0, 0)


async def test_record_validation_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    _ok(await put_record(client, me.headers, me.session_id))
    before = await _written(db_session)
    kept = await _records(db_session)

    def without(key: str) -> dict[str, Any]:
        return {k: v for k, v in RECORD_BODY.items() if k != key}

    cases: list[tuple[dict[str, Any], list[Any], str | None]] = [
        (without("content"), ["body", "content"], "missing"),
        ({**RECORD_BODY, "content": "  \n "}, ["body", "content"], "string_too_short"),
        (
            {**RECORD_BODY, "content": "가" * 5001},
            ["body", "content"],
            "string_too_long",
        ),
        ({**RECORD_BODY, "content": "줄\x00바꿈"}, ["body", "content"], None),
        ({**RECORD_BODY, "note": "비고\x00"}, ["body", "note"], None),
        (without("held_on"), ["body", "held_on"], "missing"),
        ({**RECORD_BODY, "held_on": "어제"}, ["body", "held_on"], None),
        ({**RECORD_BODY, "end_time": None}, ["body"], None),  # 시각 하나만
        ({**RECORD_BODY, "start_time": None}, ["body"], None),
        ({**RECORD_BODY, "start_time": "14:00", "end_time": "13:00"}, ["body"], None),
        ({**RECORD_BODY, "start_time": "13:00", "end_time": "13:00"}, ["body"], None),
        ({**RECORD_BODY, "start_time": "13:00+09:00"}, ["body", "start_time"], None),
        ({**RECORD_BODY, "attendees": -1}, ["body", "attendees"], None),
        ({**RECORD_BODY, "attendees": 10_001}, ["body", "attendees"], None),
        (
            {**RECORD_BODY, "attendees": 2**31},
            ["body", "attendees"],
            None,
        ),  # INTEGER 밖
        ({**RECORD_BODY, "status": "ok"}, ["body", "status"], "extra_forbidden"),
    ]
    for prefix, headers in ((ME, me.headers), (ADMIN, admin)):
        url = f"{prefix}/sessions/{me.session_id}/record"
        for payload, loc, type_ in cases:
            body = problem_of(await client.put(url, headers=headers, json=payload), 422)
            assert locs(body) == [loc], (prefix, payload, body)
            if type_ is not None:
                assert [v["type"] for v in body["violations"]] == [type_], payload
        body = problem_of(
            await client.put(
                f"{prefix}/sessions/{OVERFLOW}/record",
                headers=headers,
                json=RECORD_BODY,
            ),
            422,
        )
        assert locs(body) == [["path", "session_id"]]
    assert await _written(db_session) == before
    assert await _records(db_session) == kept


async def test_record_permissions_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    theirs = await _session(client, admin, me, y, title="Y 세션", day_no=1, slot=2)
    nobody = await _session(client, admin, me, None, title="미배정", day_no=1, slot=3)
    _ok(await put_record(client, me.headers, me.session_id))
    learner = await learner_headers(db_session, me.course_id)
    before = await _written(db_session)
    kept = await _records(db_session)
    day = f"courses/{me.course_id}/days/1"

    for r in (
        await put_record(client, y_auth, me.session_id),  # 남의 세션(같은 강의)
        await put_record(client, me.headers, theirs),
        await put_record(client, me.headers, nobody),  # 미배정
        await put_record(client, learner, me.session_id),  # 수강생 토큰
        await put_record(client, admin, me.session_id),  # 관리자 토큰의 /v1/me
        await client.post(f"{ME}/{day}:record-as-planned", headers=admin),
        await _admin_put(client, me.headers, me.session_id),  # 강사 토큰의 /v1/admin
        await _confirm(client, me.headers, me.session_id),
        await client.post(f"{ADMIN}/{day}:record-as-planned", headers=me.headers),
        await client.post(f"{ADMIN}/{day}:confirm-all", headers=me.headers),
        await client.get(f"{ADMIN}/courses/{me.course_id}/records", headers=me.headers),
        await client.get(f"{ME}/courses/{me.course_id}/records", headers=learner),
    ):
        problem_of(r, 403, "/problems/forbidden")
    assert await _written(db_session) == before
    assert await _records(db_session) == kept

    # 그 강의에 내 세션이 없으면 403, 없는 강의 404
    only_x, only_x_section = await course_with_section(db_session, title="X 만의 강의")
    await _owned(
        client, admin, only_x.id, only_x_section.id, me.instructor_id, day_no=1, slot=1
    )
    problem_of(
        await client.get(f"{ME}/courses/{only_x.id}/records", headers=y_auth),
        403,
        "/problems/forbidden",
    )
    for prefix, headers in ((ME, me.headers), (ADMIN, admin)):
        problem_of(
            await client.get(f"{prefix}/courses/{LARGEST}/records", headers=headers),
            404,
            "/problems/not_found",
        )


async def test_record_as_planned_instructor(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(
        app, DAY1
    )  # 1일차는 지났고 2일차는 예정이다. 강의가 열려 있어 수강생이 들어온다
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    x = me.instructor_id
    written = me.session_id  # 1일차 1교시 — 이미 쓴 기록
    _ok(await put_record(client, me.headers, written))
    blank = await _session(
        client, admin, me, x, title="2교시", description="   ", day_no=1, slot=2
    )
    described = await _session(
        client, admin, me, x, title="3교시", description=" 도구 실습 ", day_no=1, slot=3
    )
    await _session(client, admin, me, y, title="Y 교시", day_no=1, slot=4)
    track = await add_section(client, admin, me.course_id, title="B 트랙")
    other_track = await _owned(
        client, admin, me.course_id, track, x, title="B 1교시", day_no=1, slot=1
    )
    await _owned(
        client, admin, me.course_id, track, None, title="B 미배정", day_no=1, slot=2
    )
    await _session(client, admin, me, x, title="2일차", day_no=2, slot=1)
    code = await _code(client, admin, me.course_id)
    for n, email in enumerate(("a@example.com", "b@example.com")):
        r = await enter_learner(client, code, email, f"수강생 {n}")
        assert r.status_code == 201, r.text

    url = f"{ME}/courses/{me.course_id}/days/1:record-as-planned"
    planned = [blank, described, other_track]  # 섹션 차례 → 교시 → id
    body = _ok(await client.post(url, headers=me.headers))  # R9
    assert body == {"day_no": 1, "status": "done", "changed": 3, "session_ids": planned}
    schedule = _ok(
        await client.get(f"{ADMIN}/courses/{me.course_id}/schedule", headers=admin)
    )
    times = {
        s["id"]: (s["start"], s["end"]) for d in schedule["days"] for s in d["sessions"]
    }
    # 둘째 트랙의 1교시는 그 섹션 기준이라 첫 트랙의 1교시와 같은 시각이다(결정 vi)
    assert times[other_track] == times[written] == ("13:00", "13:50")
    rows = await _records(db_session)
    assert set(rows) == {written, *planned}  # Y·미배정·2일차 세션은 기록이 없다
    contents = {blank: "2교시", described: "도구 실습", other_track: "B 1교시"}
    for sid in planned:
        start, end = times[sid]
        assert tuple(rows[sid])[1:9] == (
            "done",
            DAY1,
            _clock(start),
            _clock(end),
            2,  # 등록 수
            contents[sid],  # 설명(다듬어 비면 제목)
            None,
            "instructor",
        ), sid
    assert (rows[written].content, rows[written].status) == ("실제 진행", "done")  # R10
    assert _ok(await client.post(url, headers=me.headers)) == {
        "day_no": 1,
        "status": "done",
        "changed": 0,
        "session_ids": [],
    }
    assert await _audits(db_session, "course_day.record_as_planned") == [
        (
            f"instructor:{x}",
            str(me.course_id),
            {"day_no": 1, "status": "done", "session_ids": planned},
        )
    ]

    base = f"{ME}/courses/{me.course_id}/days"
    problem_of(  # R17 예정 일차
        await client.post(f"{base}/2:record-as-planned", headers=me.headers),
        409,
        "/problems/conflict",
    )
    problem_of(  # 강의는 2일
        await client.post(f"{base}/3:record-as-planned", headers=me.headers),
        404,
        "/problems/not_found",
    )
    for day_no in (0, 61):
        body = problem_of(
            await client.post(f"{base}/{day_no}:record-as-planned", headers=me.headers),
            422,
        )
        assert locs(body) == [["path", "day_no"]]
    other, other_section = await course_with_section(db_session, title="Y 만의 강의")
    await _owned(client, admin, other.id, other_section.id, y, day_no=1, slot=1)
    problem_of(
        await client.post(
            f"{ME}/courses/{other.id}/days/1:record-as-planned", headers=me.headers
        ),
        403,
        "/problems/forbidden",
    )
    assert len(await _audits(db_session, "course_day.record_as_planned")) == 1


async def test_record_admin_as_planned_and_confirm_all(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, DAY1)
    settings = app.state.settings
    admin_id, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    x = me.instructor_id
    done = me.session_id
    _ok(await put_record(client, me.headers, done))
    confirmed = await _session(client, admin, me, x, title="2교시", day_no=1, slot=2)
    _ok(await put_record(client, me.headers, confirmed, content="확인된 기록"))
    _ok(await _confirm(client, admin, confirmed))
    theirs = await _session(client, admin, me, y, title="Y 교시", day_no=1, slot=3)
    nobody = await _session(client, admin, me, None, title="미배정", day_no=1, slot=4)
    future = await _session(client, admin, me, x, title="2일차", day_no=2, slot=1)
    _ok(await put_record(client, me.headers, future))  # 예정 차시에도 저장은 된다
    base = f"{ADMIN}/courses/{me.course_id}/days"

    body = _ok(await client.post(f"{base}/1:record-as-planned", headers=admin))  # R11
    assert body == {
        "day_no": 1,
        "status": "ok",
        "changed": 2,
        "session_ids": [theirs, nobody],
    }
    rows = await _records(db_session)
    for sid, title in ((theirs, "Y 교시"), (nobody, "미배정")):
        assert (rows[sid].status, rows[sid].recorded_by_kind, rows[sid].content) == (
            "ok",
            "admin",
            title,
        )
        assert rows[sid].confirmed_at is not None
    assert (rows[done].status, rows[done].content) == ("done", "실제 진행")  # R12
    assert (rows[confirmed].status, rows[confirmed].content) == ("ok", "확인된 기록")

    body = _ok(await client.post(f"{base}/1:confirm-all", headers=admin))  # R13·R14
    assert body == {"day_no": 1, "status": "ok", "changed": 1, "session_ids": [done]}
    rows = await _records(db_session)
    assert (rows[done].status, rows[done].recorded_by_kind) == ("ok", "instructor")
    assert rows[done].confirmed_at is not None
    for path in ("1:confirm-all", "1:record-as-planned"):
        assert _ok(await client.post(f"{base}/{path}", headers=admin)) == {
            "day_no": 1,
            "status": "ok",
            "changed": 0,
            "session_ids": [],
        }

    problem_of(  # R17 예정 일차 계획대로
        await client.post(f"{base}/2:record-as-planned", headers=admin),
        409,
        "/problems/conflict",
    )
    body = _ok(
        await client.post(f"{base}/2:confirm-all", headers=admin)
    )  # 날짜는 안 본다
    assert body == {"day_no": 2, "status": "ok", "changed": 1, "session_ids": [future]}
    for action in ("confirm-all", "record-as-planned"):
        body = problem_of(  # 강의는 2일
            await client.post(f"{base}/3:{action}", headers=admin),
            404,
            "/problems/not_found",
        )
        assert body["detail"] == "그 일차가 없습니다"
        body = problem_of(  # 없는 강의는 일차보다 먼저 가린다(결정 i — course_or_404)
            await client.post(
                f"{ADMIN}/courses/{LARGEST}/days/1:{action}", headers=admin
            ),
            404,
            "/problems/not_found",
        )
        assert body["detail"] == "강의가 없습니다"
    actor, target = f"admin:{admin_id}", str(me.course_id)
    assert await _audits(db_session, "course_day.record_as_planned") == [
        (actor, target, {"day_no": 1, "status": "ok", "session_ids": [theirs, nobody]})
    ]
    assert await _audits(db_session, "course_day.confirm_all") == [
        (actor, target, {"day_no": 1, "status": "ok", "session_ids": [done]}),
        (actor, target, {"day_no": 2, "status": "ok", "session_ids": [future]}),
    ]


async def test_record_lists_scope_and_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    await _rename(db_session, y, Y_NAME)
    x = me.instructor_id
    first = me.session_id  # 1일차 1교시 · done · 사진 21
    second = await _session(client, admin, me, x, title="2교시", day_no=1, slot=2)
    theirs = await _session(client, admin, me, y, title="Y 교시", day_no=1, slot=3)
    nobody = await _session(client, admin, me, None, title="미배정", day_no=2, slot=1)
    confirmed = await _session(client, admin, me, x, title="2일차", day_no=2, slot=2)
    _ok(await put_record(client, me.headers, first))
    _ok(await put_record(client, me.headers, confirmed))
    _ok(await _confirm(client, admin, confirmed))
    # second 의 첫 사진은 Y 가 담당이었을 때 올렸다 — X 에게 editable 거짓
    await _assign(client, admin, second, y)
    photos = {first: [], second: [await _upload_id(client, y_auth, second, 0)]}
    await _assign(client, admin, second, x)
    for n in range(1, 21):
        photos[first].append(await _upload_id(client, me.headers, first, n))
        photos[second].append(await _upload_id(client, me.headers, second, 100 + n))
    photos[first].append(await _upload_id(client, me.headers, first, 21))
    await _upload_id(client, y_auth, theirs, 200)  # 남의 세션 사진 — X 의 셈에서 빠진다
    url = f"{ME}/courses/{me.course_id}/records"
    admin_url = f"{ADMIN}/courses/{me.course_id}/records"

    body = _ok(await client.get(url, headers=me.headers))
    assert set(body) == LIST_KEYS
    assert body["course_id"] == me.course_id
    assert set(body["summary"]) == SUMMARY_KEYS
    assert body["summary"] == {
        "sessions": 3,
        "recorded": 2,
        "confirmed": 1,
        "missing": 1,  # second(1일차 · 기록 없음)
        "photos": 42,
    }
    assert [s["session_id"] for s in body["sessions"]] == [first, second, confirmed]
    for item in body["sessions"]:
        assert set(item) == MY_SESSION_KEYS, item
        assert item["record"] is None or set(item["record"]) == RECORD_KEYS
        for photo in item["photos"]:
            assert set(photo) == MY_PHOTO_KEYS, photo
    items = {s["session_id"]: s for s in body["sessions"]}
    assert [(items[s]["status"], items[s]["record"] is None) for s in items] == [
        ("done", False),
        ("none", True),
        ("ok", False),
    ]
    head = items[first]
    assert {k: head[k] for k in MY_SESSION_KEYS - {"record", "photos"}} == {
        "session_id": first,
        "section_id": me.section_id,
        "section_title": "공통",
        "title": "교육",
        "day_no": 1,
        "date": "2026-11-02",
        "plan_start": "13:00",
        "plan_end": "13:50",
        "status": "done",
        "photos_more": True,
    }
    for sid in (first, second):  # 세션마다 올린 순 앞 20장 + 더 있음
        assert [p["id"] for p in items[sid]["photos"]] == photos[sid][:20], sid
        assert items[sid]["photos_more"] is True
    assert all(p["editable"] for p in items[first]["photos"])
    assert [
        (p["editable"], p["uploader_name"]) for p in items[second]["photos"][:2]
    ] == [(False, Y_NAME), (True, X_NAME)]
    assert (items[confirmed]["photos"], items[confirmed]["photos_more"]) == ([], False)
    assert json_keys(body) & PRIVATE_KEYS == set()

    full = _ok(await client.get(admin_url, headers=admin))
    assert set(full) == LIST_KEYS
    assert [s["session_id"] for s in full["sessions"]] == [
        first,
        second,
        theirs,
        nobody,
        confirmed,
    ]
    assert full["summary"] == {
        "sessions": 5,
        "recorded": 2,
        "confirmed": 1,
        "missing": 3,  # second · theirs · nobody(2일차도 지났다)
        "photos": 43,  # 남의 세션 사진도 센다
    }
    for item in full["sessions"]:
        assert set(item) == ADMIN_SESSION_KEYS, item
        for photo in item["photos"]:
            assert set(photo) == ADMIN_PHOTO_KEYS, photo
    by_id = {s["session_id"]: s for s in full["sessions"]}
    assert [
        (by_id[s]["instructor_id"], by_id[s]["instructor_name"])
        for s in (first, theirs, nobody)
    ] == [(x, X_NAME), (y, Y_NAME), (None, None)]
    assert [(p["seen"], p["uploader_name"]) for p in by_id[theirs]["photos"]] == [
        (False, Y_NAME)
    ]
    assert json_keys(full) & PRIVATE_KEYS == set()

    # 앞쪽 사진을 지우면 21번째가 앞 20장에 든다
    r = await client.delete(f"{ME}/photos/{photos[first][0]}", headers=me.headers)
    assert r.status_code == 204, r.text
    items = {
        s["session_id"]: s
        for s in _ok(await client.get(url, headers=me.headers))["sessions"]
    }
    assert [p["id"] for p in items[first]["photos"]] == photos[first][1:]
    assert items[first]["photos_more"] is False
    assert [p["id"] for p in items[second]["photos"]] == photos[second][:20]
    assert items[second]["photos_more"] is True
    assert _ok(await client.get(url, headers=me.headers))["summary"]["photos"] == 41
    assert _ok(await client.get(admin_url, headers=admin))["summary"]["photos"] == 42

    for path, headers in ((ME, me.headers), (ADMIN, admin)):
        body = problem_of(
            await client.get(f"{path}/courses/{OVERFLOW}/records", headers=headers),
            422,
        )
        assert locs(body) == [["path", "course_id"]]


async def test_record_portal_has_no_record_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(
        app, DAY1
    )  # 열린 강의(수강생이 들어온다) · 1일차는 지난 차시(사진을 올린다)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    second = await _session(
        client,
        admin,
        me,
        me.instructor_id,
        title="2교시",
        day_no=1,
        slot=2,
        is_open=True,
    )
    r = await add_pdf(client, admin, me.session_id)  # 열린 카드(첨부 1개 이상)
    assert r.status_code == 201, r.text
    _ok(await put_record(client, me.headers, me.session_id))  # done
    _ok(await put_record(client, me.headers, second))
    _ok(await _confirm(client, admin, second))  # ok
    photo = await upload_photo(client, me.headers, me.session_id, caption="실습 장면")
    assert photo.status_code == 201, photo.text
    code = await _code(client, admin, me.course_id)
    r = await enter_learner(client, code, "kim@example.com", "김가명", dept="교육팀")
    assert r.status_code == 201, r.text
    learner = bearer(r.json()["access_token"])

    portals = {
        "learner": await client.get(
            f"/v1/learner/courses/{me.course_id}/portal", headers=learner
        ),
        "admin": await client.get(
            f"{ADMIN}/courses/{me.course_id}/portal", headers=admin
        ),
        "instructor": await client.get(
            f"{ME}/courses/{me.course_id}/portal", headers=me.headers
        ),
    }
    for who, r in portals.items():
        body = _ok(r)
        assert json_keys(body) & RECORD_FIELD_KEYS == set(), who
        assert set(body) == TOP_KEYS, who
        assert set(body["course"]) == COURSE_KEYS, who
        cards = [card for sec in body["sections"] for card in sec["sessions"]]
        assert {c["id"] for c in cards} == {me.session_id, second}, who
        for sec in body["sections"]:
            assert set(sec) == SECTION_KEYS, who
        for card in cards:
            assert set(card) == CARD_KEYS, (who, card)
            for item in card["attachments"]:
                assert set(item) == ATTACHMENT_KEYS, (who, item)
    assert portals["learner"].json() == portals["instructor"].json()

    # 수강생은 사진도 기록 경로도 열지 못한다
    problem_of(
        await client.get(photo.json()["href"], headers=learner),
        403,
        "/problems/forbidden",
    )
    for r in (
        await put_record(client, learner, me.session_id),
        await client.get(f"{ME}/courses/{me.course_id}/records", headers=learner),
        await upload_photo(client, learner, me.session_id),
        await client.delete(f"{ME}/photos/{photo.json()['id']}", headers=learner),
        await client.get(f"{ADMIN}/photos", headers=learner),
        await client.get(f"{ADMIN}/courses/{me.course_id}/records", headers=learner),
    ):
        problem_of(r, 403, "/problems/forbidden")


async def test_record_home_todo(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, date(2026, 11, 3))
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    running, rs = await course_with_section(
        db_session, title="진행 강의", day_count=4
    )  # 11-02 ~ 11-05
    ended, es = await course_with_section(
        db_session, title="종료 강의", start_on=date(2026, 10, 19)
    )
    archived, ars = await course_with_section(db_session, title="보관 강의")
    first = await _owned(
        client, admin, running.id, rs.id, x, title="1일차", day_no=1, slot=1
    )
    second = await _owned(
        client, admin, running.id, rs.id, x, title="2일차", day_no=2, slot=1
    )
    await _owned(client, admin, running.id, rs.id, x, title="3일차", day_no=3, slot=1)
    await _owned(client, admin, running.id, rs.id, y, title="Y 1일차", day_no=1, slot=2)
    await _owned(client, admin, ended.id, es.id, x, title="끝난 세션", day_no=1, slot=1)
    await _owned(
        client, admin, archived.id, ars.id, x, title="보관 세션", day_no=1, slot=1
    )
    r = await client.post(f"{ADMIN}/courses/{archived.id}:archive", headers=admin)
    assert r.status_code == 200, r.text

    def todo(session_id: int, title: str, day_no: int) -> dict[str, Any]:
        return {
            "course_id": running.id,
            "course_title": "진행 강의",
            "section_id": rs.id,
            "section_title": rs.title,
            "session_id": session_id,
            "session_title": title,
            "day_no": day_no,
            "slot": 1,
        }

    body = _ok(await client.get(f"{ME}/home", headers=x_auth))
    # 지난 일차의 내 미기록만, 일차 날짜 순 — 예정·종료·보관·남의 세션은 빠진다
    assert body["records_todo"] == [todo(first, "1일차", 1), todo(second, "2일차", 2)]
    for item in body["records_todo"]:
        assert set(item) == TODO_KEYS, item
    assert body["records_todo_more"] is False

    _ok(await put_record(client, x_auth, first))
    body = _ok(await client.get(f"{ME}/home", headers=x_auth))
    assert (body["records_todo"], body["records_todo_more"]) == (
        [todo(second, "2일차", 2)],
        False,
    )

    _, pending = await approved(
        db_session, settings, email="p@example.com", status="pending"
    )
    body = _ok(await client.get(f"{ME}/home", headers=pending))
    assert (body["records_todo"], body["records_todo_more"]) == ([], False)
