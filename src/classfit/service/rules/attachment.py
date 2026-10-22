"""강사 첨부의 종류 판정과 순서(T6 결정 iii·viii·ix). 순수 함수다 — DB·crud·models 를 부르지 않는다
(tests/unit/test_import_rules.py).

- 종류는 파일 이름의 확장자로 정하고(시안 kindOf 강사.html:1132 와 같은 방식), 첫 바이트가 그 확장자의 모양과 맞아야 한다.
  받는 확장자는 기획안 I4 표(:608-612) + 같은 JPEG 인 .jpeg 다. 대소문자는 보지 않는다. zip 은 풀지 않는다.
- content_type 은 받은 값이 아니라 EXTENSIONS 의 값으로 고정한다(T2b 결정 viii 꼴). HTML 패키지는
  HTML_PACKAGE_CONTENT_TYPE 이고 파일 끝점이 이 값으로 501 을 가린다(결정 ix).
- 끝점은 머리 HEAD_BYTES 만 먼저 읽어 classify 하고, service 는 받은 바이트로 다시 판정한다.
- PDF_MAGIC 원본은 여기다(service.files.attachments 가 다시 내보낸다 — T3·T4 import 는 그대로).
- reordered 는 PATCH position 의 새 차례다(결정 viii). 범위 밖 자리는 끝이다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
EMPTY_ZIP_MAGIC = b"PK\x05\x06"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
HEAD_BYTES = 8192
UPLOAD_KINDS = ("pdf", "office", "html", "image")
HTML_PACKAGE_CONTENT_TYPE = "application/zip"
_OOXML = "application/vnd.openxmlformats-officedocument"

# 확장자 → (kind, content_type)
EXTENSIONS: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".pptx": ("office", f"{_OOXML}.presentationml.presentation"),
    ".docx": ("office", f"{_OOXML}.wordprocessingml.document"),
    ".xlsx": ("office", f"{_OOXML}.spreadsheetml.sheet"),
    ".csv": ("office", "text/csv"),
    ".zip": ("html", HTML_PACKAGE_CONTENT_TYPE),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
}

RejectReason = Literal["unknown_type", "mismatch", "too_large", "kind_changed"]


def _zip(head: bytes) -> bool:
    return head.startswith(ZIP_MAGIC)


def _webp(head: bytes) -> bool:
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


# 확장자 → 첫 바이트 검사. csv 는 머리에 NUL 이 없으면 된다(글자 파일)
_SHAPES: dict[str, Callable[[bytes], bool]] = {
    ".pdf": lambda head: head.startswith(PDF_MAGIC),
    ".pptx": _zip,
    ".docx": _zip,
    ".xlsx": _zip,
    ".csv": lambda head: b"\x00" not in head,
    ".zip": lambda head: head.startswith((ZIP_MAGIC, EMPTY_ZIP_MAGIC)),
    ".png": lambda head: head.startswith(PNG_MAGIC),
    ".jpg": lambda head: head.startswith(JPEG_MAGIC),
    ".jpeg": lambda head: head.startswith(JPEG_MAGIC),
    ".webp": _webp,
}


class FileRejected(ValueError):
    """받을 수 없는 파일. 끝점이 too_large → 413, 나머지 → 422(loc ["body","file"]) 로 바꾼다.

    kind 는 판정한 종류(unknown_type 이면 None), limit_mb 는 too_large 일 때 그 종류 상한(MB)이다.
    """

    def __init__(
        self,
        reason: RejectReason,
        *,
        kind: str | None = None,
        limit_mb: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind
        self.limit_mb = limit_mb


def extension_of(filename: str) -> str:
    """마지막 마디의 마지막 점부터 소문자로. 점이 없거나 이름이 점 하나로 시작하는 마디(.pdf)면 빈 글자."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or not ext:
        return ""
    return "." + ext.lower()


def classify(filename: str, head: bytes) -> tuple[str, str]:
    """(kind, content_type). 모르는 확장자는 FileRejected("unknown_type"), 첫 바이트가 틀리면 "mismatch"."""
    ext = extension_of(filename)
    found = EXTENSIONS.get(ext)
    if found is None:
        raise FileRejected("unknown_type")
    kind, content_type = found
    if not _SHAPES[ext](head[:HEAD_BYTES]):
        raise FileRejected("mismatch", kind=kind)
    return kind, content_type


def reordered(ids: Sequence[int], moving: int, position: int) -> list[int]:
    """moving 을 0부터 센 position 자리로 옮긴 새 차례. 목록 길이를 넘으면 끝이다. 없는 id·음수 자리는 ValueError."""
    if moving not in ids:
        raise ValueError(f"차례에 없는 첨부: {moving}")
    if position < 0:
        raise ValueError("position 은 0 이상")
    rest = [i for i in ids if i != moving]
    rest.insert(min(position, len(rest)), moving)
    return rest
