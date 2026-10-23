"""교육 사진 내려받기 이름(T7 결정 xi ③). 순수 함수다 — DB·crud·models 를 부르지 않는다(tests/unit/test_import_rules.py).

- 꼴은 시안 phFname(관리자.html:792)의 `<고객사>_<YYYYMMDD>_<n>일차_<NN>.<확장자>` 다. 고객사의 공백·파일 이름에 못 쓰는
  글자는 `_` 로 바꾼다. 교육일은 사진의 taken_on 이고, 세션의 일차가 없어졌으면(None) `_<n>일차` 마디를 뺀다.
- 확장자는 받은 파일 이름이 아니라 표의 content_type 으로 정한다(rules.attachment.EXTENSIONS 의 image 셋). 변환·압축은 없다.
"""

from __future__ import annotations

import re
from datetime import date

EXTENSION_OF = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_UNSAFE = re.compile(r'[\s<>:"/\\|?*\x00-\x1f\x7f]')


def download_name(
    client_name: str, taken_on: date, day_no: int | None, index: int, content_type: str
) -> str:
    """index 는 1부터 센 차례다(두 자리, 100 이상은 그대로)."""
    client = _UNSAFE.sub("_", client_name)
    day = "" if day_no is None else f"_{day_no}일차"
    return f"{client}_{taken_on:%Y%m%d}{day}_{index:02d}.{EXTENSION_OF[content_type]}"
