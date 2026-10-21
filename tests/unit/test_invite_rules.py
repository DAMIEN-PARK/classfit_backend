"""초대코드 모양(service/rules/invite.py)과 생성 도우미(service/courses/codes.py 의 _new_invite_code). DB 없음."""

from classfit.service.courses.codes import _new_invite_code
from classfit.service.rules.invite import INVITE_ALPHABET, INVITE_LENGTH


def test_invite_code_alphabet_excludes_confusables() -> None:
    assert len(INVITE_ALPHABET) == 32
    assert len(set(INVITE_ALPHABET)) == 32
    assert set(INVITE_ALPHABET).isdisjoint("0O1I")
    assert INVITE_LENGTH == 6


def test_invite_code_generator_shape() -> None:
    codes = [_new_invite_code() for _ in range(1000)]
    for code in codes:
        assert len(code) == INVITE_LENGTH, code
        assert set(code) <= set(INVITE_ALPHABET), code
    # 6000 글자면 32자가 다 나온다(한 글자라도 빠질 확률 ≈ 32·(31/32)^6000). 다른 알파벳·고정값을 잡는다
    assert set("".join(codes)) == set(INVITE_ALPHABET)
    assert len(set(codes)) > 990
