"""강사 첨부 규칙(T6 결정 iii·viii, service/rules/attachment.py): 확장자 표 → (kind, content_type) · 거절 표 · 순서 바꾸기.

기대값은 규칙 모듈의 표를 읽지 않고 글자로 적는다(표를 고치면 이 시험이 빨개지게).
"""

from __future__ import annotations

import pytest

from classfit.service.rules.attachment import (
    EXTENSIONS,
    HEAD_BYTES,
    UPLOAD_KINDS,
    FileRejected,
    classify,
    reordered,
)

OOXML = "application/vnd.openxmlformats-officedocument"
ZIP = b"PK\x03\x04" + b"\x14\x00" * 4
PDF = b"%PDF-1.7\n%t6\n"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def test_attachment_rules_classify_table() -> None:
    table = [
        ("강의안.pdf", PDF, ("pdf", "application/pdf")),
        ("slides.pptx", ZIP, ("office", f"{OOXML}.presentationml.presentation")),
        ("doc.docx", ZIP, ("office", f"{OOXML}.wordprocessingml.document")),
        ("sheet.xlsx", ZIP, ("office", f"{OOXML}.spreadsheetml.sheet")),
        ("명단.csv", "이름,부서\n가명,A팀\n".encode(), ("office", "text/csv")),
        ("package.zip", ZIP, ("html", "application/zip")),
        ("empty.zip", b"PK\x05\x06" + b"\x00" * 18, ("html", "application/zip")),
        ("image.png", PNG, ("image", "image/png")),
        ("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", ("image", "image/jpeg")),
        ("photo.jpeg", b"\xff\xd8\xff\xe1\x00\x10Exif", ("image", "image/jpeg")),
        ("anim.webp", b"RIFF\x0a\x00\x00\x00WEBPVP8 ", ("image", "image/webp")),
        ("REPORT.PDF", PDF, ("pdf", "application/pdf")),
        ("dir/sub/a.Png", PNG, ("image", "image/png")),
    ]
    for filename, head, expected in table:
        assert classify(filename, head) == expected, filename
    assert set(EXTENSIONS) == {
        ".pdf",
        ".pptx",
        ".docx",
        ".xlsx",
        ".csv",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }
    assert {kind for kind, _ in EXTENSIONS.values()} == set(UPLOAD_KINDS)
    assert set(UPLOAD_KINDS) == {"pdf", "office", "html", "image"}
    assert HEAD_BYTES == 8192
    # 머리 판정은 HEAD_BYTES 안만 본다 — 그 뒤의 NUL 은 csv 판정을 바꾸지 않는다
    assert classify("big.csv", b"a" * HEAD_BYTES + b"\x00") == ("office", "text/csv")


def test_attachment_rules_rejects_table() -> None:
    unknown = ["a.exe", "a.svg", "a.ppt", "a.hwp", "a.gif", "noext", ".pdf", "a."]
    for filename in unknown:
        with pytest.raises(FileRejected) as caught:
            classify(filename, PDF)
        assert (caught.value.reason, caught.value.kind) == ("unknown_type", None), (
            filename
        )
    mismatch = [
        ("a.png", PDF, "image"),
        ("a.pdf", ZIP, "pdf"),
        ("a.csv", b"a,b\x00c\n", "office"),
        ("a.docx", PDF, "office"),
        ("a.zip", PDF, "html"),
        ("a.jpg", PNG, "image"),
        ("a.webp", b"RIFF\x0a\x00\x00\x00WAVEfmt ", "image"),
        ("a.pdf", b"", "pdf"),
    ]
    for filename, head, kind in mismatch:
        with pytest.raises(FileRejected) as caught:
            classify(filename, head)
        assert (caught.value.reason, caught.value.kind) == ("mismatch", kind), filename
    assert issubclass(FileRejected, ValueError)
    big = FileRejected("too_large", kind="image", limit_mb=10)
    assert (big.reason, big.kind, big.limit_mb) == ("too_large", "image", 10)


def test_attachment_rules_reorder() -> None:
    ids = [1, 2, 3]
    assert reordered(ids, 3, 0) == [3, 1, 2]  # 앞으로
    assert reordered(ids, 1, 2) == [2, 3, 1]  # 뒤로
    assert reordered(ids, 2, 1) == [1, 2, 3]  # 제자리
    assert reordered(ids, 1, 99) == [2, 3, 1]  # 범위 밖은 끝
    assert reordered([5], 5, 0) == [5]
    assert reordered([5], 5, 3) == [5]
    assert ids == [1, 2, 3]  # 준 목록은 그대로
    with pytest.raises(ValueError):
        reordered(ids, 4, 0)
    with pytest.raises(ValueError):
        reordered(ids, 1, -1)
