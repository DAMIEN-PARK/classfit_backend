"""초대코드 모양의 원본 한 곳(Design 5절 16). 생성(service/courses)과 입장 형식 검사(service/enroll)가 같이 쓴다.

알파벳은 시안 관리자.html:1417 genCode 의 32자 그대로다. 헷갈리는 0·O·1·I 가 없다.
입장 입력은 앞뒤 공백을 지우고 대문자로 바꾼 뒤(시안 학습자.html:663) 혼동 문자를 먼저 본다(T2b 계획 결정 i·iv).
"""

from __future__ import annotations

from typing import Literal

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 6
CONFUSABLE = frozenset("0O1I")  # 알파벳에 없는 글자 중 손님이 잘못 읽기 쉬운 넷

InviteInputError = Literal["confusable", "malformed"]


def parse_invite_input(raw: str) -> str | InviteInputError:
    """입장 입력의 정규화 코드. 혼동 문자(0·O·1·I)가 하나라도 있으면 "confusable" 이 먼저고,
    그 밖에 길이(6자가 아님, 짧든 길든)·문자가 틀리면 "malformed" 다. 정규화 코드는 대문자 6자라 두 값과 겹치지 않는다.
    """
    code = raw.strip().upper()
    if any(ch in CONFUSABLE for ch in code):
        return "confusable"
    if len(code) != INVITE_LENGTH or any(ch not in INVITE_ALPHABET for ch in code):
        return "malformed"
    return code
