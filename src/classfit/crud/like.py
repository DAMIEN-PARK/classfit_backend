"""부분 일치 검색의 LIKE 패턴. 이스케이프는 이 파일 한 곳이다.

받은 글자의 % · _ · \\ 는 와일드카드가 아니라 글자 그대로 찾는다. 쓰는 쪽은
`column.ilike(contains_pattern(q), escape=LIKE_ESCAPE)` 로 부른다.
"""

from __future__ import annotations

LIKE_ESCAPE = "\\"


def contains_pattern(q: str) -> str:
    """q 를 어디든 포함하는 LIKE 패턴(%q%). q 안의 와일드카드·이스케이프 문자는 글자로 바꾼다."""
    escaped = (
        q.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
