"""입장 입력 코드의 정규화·형식(service/rules/invite.py)과 포털 카드 상태(service/rules/portal.py). DB 없음."""

from classfit.service.rules.invite import INVITE_ALPHABET, parse_invite_input
from classfit.service.rules.portal import card_state


def test_enter_code_input_confusable_before_malformed() -> None:
    # 혼동 문자가 있으면 길이·다른 문자가 틀려도 confusable 이 먼저다(T2b 계획 결정 i)
    assert parse_invite_input("AB0CDE") == "confusable"
    # 소문자 o 는 대문자로 바꾼 뒤 O 다
    assert parse_invite_input("abcdo1") == "confusable"
    assert parse_invite_input("ABI") == "confusable"
    assert parse_invite_input("0") == "confusable"
    assert parse_invite_input("AB-1CDEFG") == "confusable"
    # 혼동 문자가 없으면 길이·문자 오류는 malformed
    assert parse_invite_input("") == "malformed"
    assert parse_invite_input("ABCDE") == "malformed"
    assert parse_invite_input("ABCDEFG") == "malformed"
    assert parse_invite_input("AB-CDE") == "malformed"
    assert parse_invite_input("AB CDE") == "malformed"  # 가운데 공백은 지우지 않는다
    assert parse_invite_input("ABCDÉ2") == "malformed"


def test_enter_code_input_normalizes_case_and_spaces() -> None:
    assert parse_invite_input("abcdef") == "ABCDEF"
    assert parse_invite_input("  aBc23Z \n") == "ABC23Z"
    assert parse_invite_input("\tHJKLMN") == "HJKLMN"
    # 알파벳 32자는 모두 그대로 통과한다
    for i in range(0, len(INVITE_ALPHABET), 6):
        chunk = (INVITE_ALPHABET[i : i + 6] + INVITE_ALPHABET)[:6]
        assert parse_invite_input(chunk.lower()) == chunk


def test_enter_card_state_needs_open_and_attachment() -> None:
    assert card_state(is_open=True, attachments=1) == "open"
    assert card_state(is_open=True, attachments=3) == "open"
    assert card_state(is_open=True, attachments=0) == "preparing"
    assert card_state(is_open=False, attachments=1) == "preparing"
    assert card_state(is_open=False, attachments=0) == "preparing"
