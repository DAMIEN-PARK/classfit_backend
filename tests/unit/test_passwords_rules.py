"""core.passwords: argon2id 왕복. DB 없음."""

from classfit.core.passwords import DUMMY_HASH, hash_password, verify_password


def test_password_hash_argon2id_roundtrip() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert "correct horse" not in hashed
    assert verify_password(hashed, "correct horse battery") is True
    assert verify_password(hashed, "wrong") is False
    assert verify_password("not-a-hash", "x") is False  # 깨진 해시도 예외 대신 False
    assert DUMMY_HASH.startswith("$argon2id$")
