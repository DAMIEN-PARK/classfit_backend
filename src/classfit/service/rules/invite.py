"""초대코드 모양의 원본 한 곳(Design 5절 16). 생성(service/courses)과 입장 형식 검사(T2b)가 같이 쓴다.

알파벳은 시안 관리자.html:1417 genCode 의 32자 그대로다. 헷갈리는 0·O·1·I 가 없다.
"""

from __future__ import annotations

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 6
