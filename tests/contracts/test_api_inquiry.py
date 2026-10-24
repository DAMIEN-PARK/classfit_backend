"""교육 문의 접수 POST /v1/inquiries(인증 없음, T9b 계획 결정 i·ii·iv·v·viii·ix·xx·xxiii·xxiv · 증명 1~8·22·23·28).

새 접수 · 1분 안 재제출 · honeypot 은 셋 다 200 같은 모양 {receipt_no, received_at} 이다. 필수 넷은 회사명·담당자·이메일·연락처,
본문은 파싱 전 상한(413)과 JSON Content-Type(415)을 먼저 보고, 이메일당 24시간 상한은 429, 수신 주소 미설정은 501 이다. outbox
두 행의 params 는 {inquiry_id} 뿐이고 확인 메일 본문에 제출한 값이 없다. 계약 시험은 요청 사이에 트랜잭션이 리셋되지 않으므로
(한 시험의 요청이 같은 바깥 트랜잭션 안의 SAVEPOINT 로 돈다) "행 0" 은 쓰기 성공 앞에만 두고 그 뒤는 "행 +1" 로 잰다. 같은
까닭으로 now() 가 시험 안에서 고정이라 1분 창은 age_inquiry 로 행의 시각을 밀어 잰다.
"""

import datetime as dt
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.core.config import Settings
from classfit.database.session import make_session_factory
from classfit.main import create_app
from classfit.models import AuditLog, Company, Inquiry, MailOutbox
from classfit.models.inquiry import INQUIRY_SIZES
from classfit.schemas.inquiry import InquiryIn
from scripts import outbox_preview
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.inquiry import (
    INQUIRY_BODY,
    NORMALIZED_EMAIL,
    NOTIFY_TO,
    RECEIPT_KEYS,
    RECEIPT_RE,
    age_inquiry,
    configured,
    inquiry_body,
    outbox_rows,
    post_inquiry,
    submitted_values,
)
from tests.fixtures.instructors import count, locs, problem_of

URL = "/v1/inquiries"
REQUIRED = ("company_name", "contact_name", "email", "phone")
FIELDS = {
    "company_name",
    "contact_name",
    "email",
    "phone",
    "dept_title",
    "company_size",
    "message",
    "privacy_agreed",
    "website",
}


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


def _receipt(r: httpx.Response) -> dict[str, Any]:
    """200 영수증 — 키 둘 · 번호 모양 · 시간대 있는 ISO 시각."""
    body: dict[str, Any] = _ok(r)
    assert set(body) == RECEIPT_KEYS, body
    assert re.fullmatch(RECEIPT_RE, body["receipt_no"]), body
    assert dt.datetime.fromisoformat(body["received_at"]).tzinfo is not None, body
    return body


async def _row(db: AsyncSession, receipt_no: str) -> Inquiry:
    row = await db.scalar(select(Inquiry).where(Inquiry.receipt_no == receipt_no))
    assert row is not None, receipt_no
    return row


async def _rows(db: AsyncSession) -> tuple[int, int]:
    """(문의 행 수, outbox 행 수)."""
    return await count(db, Inquiry), await count(db, MailOutbox)


async def test_inquiry_submit_200_receipt_and_outbox(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    configured(app)
    assert await _rows(db) == (0, 0)

    body = _receipt(await post_inquiry(client, company_name="  A사  "))
    row = await _row(db, body["receipt_no"])
    assert await count(db, Inquiry) == 1
    assert row.email == NORMALIZED_EMAIL  # 소문자 정규화
    assert row.company_name == "A사"  # 앞뒤 공백 제거
    assert row.contact_name == INQUIRY_BODY["contact_name"]
    assert row.phone == INQUIRY_BODY["phone"]
    assert row.dept_title == INQUIRY_BODY["dept_title"]
    assert row.company_size == "30_99"  # 코드 그대로(라벨이 아니다)
    assert row.message == INQUIRY_BODY["message"]
    assert row.privacy_agreed_at is not None
    columns = set(Inquiry.__table__.columns.keys())
    # honeypot 칸 · 요청 주소는 저장하지 않는다
    assert not columns & {"website", "client", "ip"}
    # outbox 두 행(미발송) — params 는 행 id 하나
    params = {"inquiry_id": row.id}
    assert await outbox_rows(db) == [
        ("inquiry_received", params, NORMALIZED_EMAIL, None),
        ("inquiry_notify", params, NOTIFY_TO, None),
    ]
    assert await count(db, AuditLog) == 0  # 접수는 audit 대상이 아니다(결정 x)
    assert await count(db, Company) == 0  # Company 연결 없음(r3 171)

    # 공개 끝점 — 토큰을 붙여도(관리자 · 수강생 · 없는 토큰) 같은 200 이고 주체를 보지 않는다
    _, admin = await admin_headers(db)
    course, _ = await open_test_course(db)
    learner = await learner_headers(db, course.id)
    for i, headers in enumerate(
        (admin, learner, {"Authorization": "Bearer no-such-token"})
    ):
        _receipt(
            await post_inquiry(client, headers=headers, email=f"tok-{i}@example.com")
        )
    assert await count(db, Inquiry) == 4

    # 긍정 사례 — 이메일마다 새 행(+1)
    n = await count(db, Inquiry)
    cases: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (inquiry_body(drop=["message"]), {"message": None}),  # 내용 없이
        (inquiry_body(message="  \n\t "), {"message": None}),  # 다듬어 비면 None
        # 줄바꿈·탭 보존
        (inquiry_body(message="첫 줄\n\t둘째 줄"), {"message": "첫 줄\n\t둘째 줄"}),
        (inquiry_body(phone=" +82 (10) 0000-0000 "), {"phone": "+82 (10) 0000-0000"}),
        (inquiry_body(drop=["dept_title"]), {"dept_title": None}),
        (inquiry_body(drop=["company_size"]), {"company_size": None}),
    ]
    for i, (sent, stored) in enumerate(cases):
        sent = {**sent, "email": f"case-{i}@example.com"}
        got = await _row(db, _receipt(await client.post(URL, json=sent))["receipt_no"])
        for key, value in stored.items():
            assert getattr(got, key) == value, (i, key)
        n += 1
        assert await count(db, Inquiry) == n


async def test_inquiry_honeypot_200_same_shape_no_row(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    configured(app)
    trap = _receipt(await post_inquiry(client, website="https://example.com"))
    again = _receipt(await post_inquiry(client, website="x", message="다른 내용"))
    assert await _rows(db) == (0, 0)
    assert await count(db, AuditLog) == 0

    # 공백뿐인 website 는 honeypot 이 아니다 — 정상 접수(행 1 · outbox 2)
    normal = _receipt(await post_inquiry(client, website="  "))
    assert await _rows(db) == (1, 2)
    assert set(trap) == set(again) == set(normal)
    # 시각은 둘 다 DB now() 다 — 시험 안에서 now() 가 바깥 트랜잭션 시작 시각으로 고정이라 값까지 같다
    assert trap["received_at"] == again["received_at"] == normal["received_at"]


async def test_inquiry_resubmit_within_minute_same_receipt(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    configured(app)
    first = _receipt(await post_inquiry(client))
    assert _receipt(await post_inquiry(client)) == first  # 같은 영수증 · 같은 접수 시각
    assert await _rows(db) == (1, 2)

    # 이메일 대소문자·앞뒤 공백 · 회사명만 달라도 같은 문의(이메일 + 내용 기준)
    same = (
        inquiry_body(email="  CONTACT.a@EXAMPLE.com "),
        inquiry_body(company_name="B사"),
    )
    for sent in same:
        r = await client.post(URL, json=sent)
        assert _receipt(r)["receipt_no"] == first["receipt_no"]
    row = await _row(db, first["receipt_no"])
    await age_inquiry(db, row.id, seconds=30)  # 창 안
    assert _receipt(await post_inquiry(client))["receipt_no"] == first["receipt_no"]
    assert await _rows(db) == (1, 2)

    # 내용이 한 글자라도 다르면 새 문의
    other = _receipt(await post_inquiry(client, message=INQUIRY_BODY["message"] + "!"))
    assert other["receipt_no"] != first["receipt_no"]
    assert await _rows(db) == (2, 4)

    # 1분이 지나면 같은 본문도 새 문의
    await age_inquiry(db, row.id, seconds=120)
    late = _receipt(await post_inquiry(client))
    assert late["receipt_no"] not in {first["receipt_no"], other["receipt_no"]}
    assert await _rows(db) == (3, 6)


async def test_inquiry_required_four_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    configured(app)
    blank_type = {
        "company_name": "string_too_short",
        "contact_name": "string_too_short",
        "email": "value_error",  # AfterValidator(normalize_email)
        "phone": "value_error",  # AfterValidator(_inquiry_phone)
    }
    for key in REQUIRED:
        body = problem_of(await client.post(URL, json=inquiry_body(drop=[key])), 422)
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["body", key], "missing")
        ], key
        body = problem_of(
            await client.post(URL, json=inquiry_body(**{key: "   "})), 422
        )
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["body", key], blank_type[key])
        ], key
    assert await _rows(db_session) == (0, 0)


async def test_inquiry_format_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """거절 사례만 — 끝에 행 0(긍정 사례는 test_inquiry_submit_200_receipt_and_outbox)."""
    configured(app)
    cases: list[tuple[str, Any, str]] = [
        ("email", "not-an-email", "value_error"),
        ("email", "a" * 243 + "@example.com", "value_error"),  # 255자
        ("phone", "abc", "value_error"),
        ("phone", "-------", "value_error"),  # 숫자 0개
        ("phone", "0100-0000", "value_error"),  # 숫자 8자
        ("phone", "0100-0000-0000-0000", "value_error"),  # 숫자 16자
        ("phone", "010 0000 0000       0", "value_error"),  # 21자
        ("phone", "010-0000-0000\x00", "value_error"),
        ("company_size", "10_49", "literal_error"),
        ("company_name", "가" * 101, "string_too_long"),
        ("contact_name", "가" * 51, "string_too_long"),
        ("dept_title", "경영\x00지원팀", "value_error"),
        ("message", "가" * 5001, "string_too_long"),
        ("message", "교육\x00문의", "value_error"),
        ("stage", "01", "extra_forbidden"),  # 공개홈의 단계는 칸이 아니다
    ]
    for key, value, type_ in cases:
        r = await client.post(URL, json=inquiry_body(**{key: value}))
        body = problem_of(r, 422)
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["body", key], type_)
        ], (key, value)
    # 본문이 JSON 이 아님(Content-Type 은 JSON)
    r = await client.post(
        URL, headers={"content-type": "application/json"}, content=b"{not json"
    )
    body = problem_of(r, 422)
    assert locs(body) == [["body"]]
    assert [v["type"] for v in body["violations"]] == ["json_invalid"]
    assert await _rows(db_session) == (0, 0)


async def test_inquiry_consent_required_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    configured(app)
    for sent, type_ in (
        (inquiry_body(privacy_agreed=False), "literal_error"),
        (inquiry_body(drop=["privacy_agreed"]), "missing"),
    ):
        body = problem_of(await client.post(URL, json=sent), 422)
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["body", "privacy_agreed"], type_)
        ]
    assert await _rows(db_session) == (0, 0)


async def test_inquiry_body_too_large_413(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    limit = 2048
    configured(app, inquiry_body_max_bytes=limit)
    json_type = {"content-type": "application/json"}

    def padded(sent: dict[str, Any], size: int) -> bytes:
        raw = json.dumps(sent).encode()
        assert len(raw) <= size
        return raw + b" " * (size - len(raw))  # JSON 뒤 공백은 허용된다

    def chunks(raw: bytes, step: int) -> AsyncIterator[bytes]:
        async def gen() -> AsyncIterator[bytes]:
            for i in range(0, len(raw), step):
                yield raw[i : i + step]

        return gen()

    # Content-Length 가 상한을 넘으면 413(내용 3000자 — 칸 모양은 맞다)
    big = await client.post(URL, json=inquiry_body(message="x" * 3000))
    assert int(big.request.headers["content-length"]) > limit
    problem_of(big, 413, "/problems/content-too-large")
    # Content-Length 없는 chunked — 작은 청크 여럿으로 상한 + 1 바이트
    small = await client.post(
        URL, headers=json_type, content=chunks(b" " * (limit + 1), 256)
    )
    assert "content-length" not in small.request.headers
    problem_of(small, 413, "/problems/content-too-large")
    # 단일 과대 청크 하나(복사 전에 거른다)
    one = await client.post(URL, headers=json_type, content=chunks(b" " * 4096, 4096))
    problem_of(one, 413, "/problems/content-too-large")
    assert await _rows(db) == (0, 0)

    # 상한 바로 아래(정확히 2048 바이트) chunked — 모양 틀림 422 · 정상 200
    bad = padded(inquiry_body(email="chunk@example.com", phone="abc"), limit)
    problem_of(await client.post(URL, headers=json_type, content=chunks(bad, 500)), 422)
    good = padded(inquiry_body(email="chunk@example.com"), limit)
    _receipt(await client.post(URL, headers=json_type, content=chunks(good, 500)))
    assert await count(db, Inquiry) == 1

    # Content-Type 이 JSON 이 아니면 맞는 본문이어도 415(결정 xxiii ⑤ — 읽기 전, 413 보다 먼저)
    n = await count(db, Inquiry)
    sent = json.dumps(inquiry_body(email="plain@example.com")).encode()
    rejected: list[tuple[dict[str, str], bytes]] = [
        ({"content-type": "text/plain"}, sent),
        ({}, sent),  # 헤더 없음
        ({"content-type": "text/plain"}, b" " * (limit + 1)),  # 상한을 넘어도 415
        ({"content-type": "application/x-www-form-urlencoded"}, b"company_name=A"),
        ({"content-type": "multipart/form-data; boundary=x"}, sent),
    ]
    for headers, raw in rejected:
        r = await client.post(URL, headers=headers, content=raw)
        assert r.request.headers.get("content-type") == headers.get("content-type")
        problem_of(r, 415, "/problems/unsupported-media-type")
    assert await count(db, Inquiry) == n

    # 매개변수 · +json · 대소문자는 받는다
    for i, media in enumerate(
        (
            "application/json; charset=utf-8",
            "application/vnd.a+json",
            "Application/JSON",
        )
    ):
        raw = json.dumps(inquiry_body(email=f"media-{i}@example.com")).encode()
        _receipt(await client.post(URL, headers={"content-type": media}, content=raw))
    assert await count(db, Inquiry) == n + 3


def test_inquiry_openapi_request_body() -> None:
    spec = create_app(Settings()).openapi()
    op = spec["paths"]["/v1/inquiries"]["post"]
    assert op["requestBody"]["required"] is True
    # InquiryIn.model_json_schema() 그대로다(OpenAPI 출력은 default: null 을 뺀다 — 그래서 == 대신 칸마다 잰다)
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema["title"] == "InquiryIn"
    assert schema["additionalProperties"] is False  # extra="forbid"
    assert set(schema["properties"]) == set(InquiryIn.model_fields) == FIELDS
    assert set(schema["required"]) == {*REQUIRED, "privacy_agreed"}
    size = schema["properties"]["company_size"]
    assert size["anyOf"][0]["enum"] == list(INQUIRY_SIZES)  # Literal | None
    assert schema["properties"]["privacy_agreed"]["const"] is True  # Literal[True]
    assert "$defs" not in schema  # 중첩 모델 없음
    assert {"409", "413", "415", "422", "429", "501"} <= set(op["responses"])
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/InquiryReceiptOut"
    }


async def test_inquiry_daily_limit_429(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    configured(app, inquiry_daily_max=2)
    first = _receipt(await post_inquiry(client, message="첫째 문의"))
    _receipt(await post_inquiry(client, message="둘째 문의"))
    r = await post_inquiry(client, message="셋째 문의")
    problem_of(r, 429, "/problems/too-many-requests")  # T1·T3 로그인 잠김과 같은 type
    assert await _rows(db) == (2, 4)
    # 1분 안 재제출은 상한보다 먼저 — 같은 영수증 200
    again = _receipt(await post_inquiry(client, message="첫째 문의"))
    assert again["receipt_no"] == first["receipt_no"]

    # 다른 이메일은 따로 센다. honeypot 은 행이 없어 상한에 세지 않는다
    other = "other@example.com"
    for i in range(4):
        _receipt(
            await post_inquiry(client, email=other, message=f"봇 {i}", website="x")
        )
    assert await _rows(db) == (2, 4)
    for i in range(2):
        _receipt(await post_inquiry(client, email=other, message=f"다른 {i}"))
    problem_of(
        await post_inquiry(client, email=other, message="다른 2"),
        429,
        "/problems/too-many-requests",
    )
    assert await _rows(db) == (4, 8)
    assert await count(db, Inquiry, Inquiry.email == NORMALIZED_EMAIL) == 2


async def test_inquiry_not_configured_501(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # app 픽스처는 Settings() 그대로 — INQUIRY_NOTIFY_TO 없음
    for settings in (
        app.state.settings,
        Settings(inquiry_notify_to=""),
        Settings(inquiry_notify_to="   "),
    ):
        app.state.settings = settings
        for over in ({}, {"website": "https://example.com"}):  # honeypot 도 501
            body = problem_of(
                await post_inquiry(client, **over), 501, "/problems/not_configured"
            )
            assert body["detail"] == "문의 수신 주소가 구성되지 않았습니다"
            assert body["missing"] == ["CLASSFIT_INQUIRY_NOTIFY_TO"]
    assert await _rows(db_session) == (0, 0)


async def test_inquiry_outbox_params_have_no_content(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    configured(app)
    receipt = _receipt(await post_inquiry(client))
    rows = await outbox_rows(db)
    assert [kind for kind, *_ in rows] == ["inquiry_received", "inquiry_notify"]
    assert all(set(params) == {"inquiry_id"} for _, params, _, _ in rows)

    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    assert await outbox_preview.run([], factory) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False
    bodies = {m["kind"]: m["body"] for m in out["messages"]}
    assert set(bodies) == {"inquiry_received", "inquiry_notify"}
    # 확인 메일: 영수증 번호와 고정 문구만 — 제출한 값(회사명·이름·연락처·부서직함·내용)은 되비치지 않는다
    assert receipt["receipt_no"] in bodies["inquiry_received"]
    for value in submitted_values(INQUIRY_BODY):
        assert value not in bodies["inquiry_received"], value
        assert value in bodies["inquiry_notify"], value  # 관리자 알림에는 다 있다
    sent_at = select(MailOutbox.sent_at).where(MailOutbox.kind.like("inquiry_%"))
    assert set((await db.scalars(sent_at)).all()) == {None}  # 미리 보기는 롤백
