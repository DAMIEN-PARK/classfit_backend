"""포털 세션 카드의 상태(기획안 원칙 5, T2b 계획 결정 vii). 순수 함수다.

카드는 세션이 열려 있고(is_open) 첨부가 하나 이상일 때만 open 이고, 아니면 preparing(준비 중)이다.
잠긴 카드의 설명·키워드·첨부를 빼는 일과 파일 판정(crud/scope.py)은 부르는 쪽 몫이다.
"""

from __future__ import annotations

from typing import Literal

CardState = Literal["open", "preparing"]


def card_state(*, is_open: bool, attachments: int) -> CardState:
    """attachments 는 그 세션의 첨부 수다."""
    return "open" if is_open and attachments >= 1 else "preparing"
