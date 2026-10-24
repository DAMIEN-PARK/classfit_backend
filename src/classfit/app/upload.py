"""업로드 끝점 공용 도우미(T11 결정 v): 본문을 읽기 전의 Content-Length 판정 · 폼 칸 422.

T2b 첨부 끝점에 있던 MIB · _check_length · _invalid 를 옮겼다. 업로드 여섯 자리(관리자 첨부 · 강사 서류 · 풀 파일 ·
강사 첨부 둘 · 사진)가 같이 쓴다.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from classfit.app.errors import AppError

MIB = 1024 * 1024


def invalid(field: str, msg: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("body", field), "msg": msg, "type": "value_error"}]
    )


def length_over(digits: str, limit: int) -> bool:
    """ASCII 숫자 글자(Content-Length)가 limit 을 넘는가. int() 는 4,300자리를 넘으면 ValueError(500)라 앞 0 을 떼고
    자릿수가 limit 의 자릿수보다 길면 바꾸지 않고 넘는다고 본다."""
    digits = digits.lstrip("0")
    return len(digits) > len(str(limit)) or int(digits or "0") > limit


def check_length(request: Request, max_bytes: int) -> None:
    """본문을 읽기 전에 Content-Length 로 거른다. 없거나 ASCII 숫자가 아니면 411, max_bytes + 1MiB 초과 413.

    1MiB 는 폼 머리·다른 칸의 여유라 안에서 더한다. 413 안내문은 파일 상한 max_bytes 를 MiB 로 보인다.
    """
    raw = request.headers.get("content-length", "").strip()
    # isdigit 은 '²' 같은 비 ASCII 숫자도 참이라 int() 가 ValueError(500) 다 — ASCII 숫자만 길이로 믿는다
    if not (raw.isascii() and raw.isdigit()):
        raise AppError(411, "Content-Length 헤더가 필요합니다")
    if length_over(raw, max_bytes + MIB):
        raise AppError(413, f"본문이 너무 큽니다({max_bytes // MIB}MiB 까지)")
