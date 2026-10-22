"""설정. 환경 변수 이름 = CLASSFIT_ + 필드 이름(대문자).

- 꼭 필요한 값은 기본값 None 이다. 쓰는 쪽이 이름을 대며 실패한다(조용한 기본값 없음).
- 없어도 되는 기능은 `missing()` 으로 빠진 키 이름만 돌려받아 그 기능만 끈다.
- 범위·모양은 기동 때 validator 가 막는다. 고르는 값은 Literal.
- 우선순위: 셸 환경 변수 > .env 파일 > 기본값. 코드 곳곳에서 os.environ 을 직접 읽지 않는다. 이 모듈만 읽는다.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "CLASSFIT_"
DRIVER_PREFIX = "postgresql+psycopg://"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 꼭 필요한 값 (없으면 쓰는 쪽이 이름을 대며 멈춘다)
    database_url: SecretStr | None = None

    # ── 없어도 되는 값
    enable_docs: bool = False
    cors_origins: list[
        str
    ] = []  # JSON 배열로 준다: CLASSFIT_CORS_ORIGINS='["https://..."]'
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ── 기능별 값 (없으면 그 기능만 501, missing() 대상)
    file_store_root: Path | None = (
        None  # 예 var.nosync/files (gitignore). 저장소 밖이면 iCloud 폴더 밖에
    )
    # ── 예약 칸 (서명 URL 은 프론트 확정 때, ADR-003 결정 3). missing() 목록 밖
    file_signing_key: SecretStr | None = None

    # ── 수명·잠금. Design 1절 값이 기본값이고 칸 하나로 바꾼다(ADR-002 결정 5)
    admin_session_hours: int = 8
    learner_session_days: int = 1
    login_lock_failures: int = (
        10  # 같은 (계정, 클라이언트 주소)의 최근 창 실패가 이 수 이상이면 잠김
    )
    login_lock_minutes: int = 15  # 실패를 세는 창이자 잠김 시간
    file_gc_grace_hours: int = 24
    invite_expiry_days: int = 30  # 초대코드 만료 = 강의 종료일 + 이 일수(Design 1절)
    # 관리자 첨부 PDF 상한(기획안 I4). 기본값이 있어 missing() 대상이 아니다
    attachment_pdf_max_mb: int = 50
    instructor_session_days: int = 14
    email_code_minutes: int = 10  # 인증 코드 수명. 기준은 해시를 저장한 시각(issued_at)
    email_code_max_tries: int = 5  # 한 코드에 틀릴 수 있는 횟수. 넘으면 재발송해야 한다
    document_pdf_max_mb: int = 10  # 강사 서류 PDF 상한(T3 결정 ix)
    # 약관 판본. 제품 상수에 가까워 기본값을 둔다 — "미구성은 실패" 규칙의 예외(T3 결정 iii). 빈 글자는 막는다
    terms_version: str = "2026-10-22"

    @field_validator("file_store_root", "file_signing_key", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: Any) -> Any:
        # .env.example 을 그대로 복사한 빈 값이 Path("") = 현재 폴더로 조용히 바뀌지 않게
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("database_url")
    @classmethod
    def _psycopg_only(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and not v.get_secret_value().startswith(DRIVER_PREFIX):
            # 값은 오류 문구에 넣지 않는다
            raise ValueError(
                f"{ENV_PREFIX}DATABASE_URL 은 {DRIVER_PREFIX} 로 시작해야 합니다"
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError(
                "CORS 출처에 '*' 를 쓰지 않는다 (allow_credentials 와 함께면 사실상 전체 허용)"
            )
        return v

    @field_validator("db_pool_size")
    @classmethod
    def _pool_size_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("1 이상이어야 합니다 (QueuePool 에서 0 은 무제한)")
        return v

    @field_validator(
        "admin_session_hours",
        "learner_session_days",
        "login_lock_failures",
        "login_lock_minutes",
        "file_gc_grace_hours",
        "invite_expiry_days",
        "attachment_pdf_max_mb",
        "instructor_session_days",
        "email_code_minutes",
        "email_code_max_tries",
        "document_pdf_max_mb",
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("1 이상이어야 합니다")
        return v

    @field_validator("terms_version")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 글자를 쓰지 않는다")
        return v

    @field_validator("db_max_overflow")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("0 이상이어야 합니다")
        return v

    def missing(self, *fields: str) -> list[str]:
        """빠진 필드의 환경 변수 이름만 돌려준다. 501(미구성) 안내문에 그대로 쓴다."""
        return [ENV_PREFIX + f.upper() for f in fields if getattr(self, f) is None]

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise RuntimeError(f"미구성: {ENV_PREFIX}DATABASE_URL 이 없습니다")
        return self.database_url.get_secret_value()


@cache
def get_settings() -> Settings:
    """한 번만 읽는다. 시험은 get_settings.cache_clear()."""
    return Settings()
