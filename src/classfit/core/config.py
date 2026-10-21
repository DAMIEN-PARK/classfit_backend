"""설정. 환경 변수 이름 = CLASSFIT_ + 필드 이름(대문자).

- 꼭 필요한 값은 기본값 None 이다. 쓰는 쪽이 이름을 대며 실패한다(조용한 기본값 없음).
- 없어도 되는 기능은 `missing()` 으로 빠진 키 이름만 돌려받아 그 기능만 끈다.
- 범위·모양은 기동 때 validator 가 막는다. 고르는 값은 Literal.
- 우선순위: 셸 환경 변수 > .env 파일 > 기본값. 코드 곳곳에서 os.environ 을 직접 읽지 않는다. 이 모듈만 읽는다.
"""

from __future__ import annotations

from functools import cache
from typing import Literal

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
    cors_origins: list[str] = []  # JSON 배열로 준다: CLASSFIT_CORS_ORIGINS='["https://..."]'
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    @field_validator("database_url")
    @classmethod
    def _psycopg_only(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and not v.get_secret_value().startswith(DRIVER_PREFIX):
            # 값은 오류 문구에 넣지 않는다
            raise ValueError(f"{ENV_PREFIX}DATABASE_URL 은 {DRIVER_PREFIX} 로 시작해야 합니다")
        return v

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError("CORS 출처에 '*' 를 쓰지 않는다 (allow_credentials 와 함께면 사실상 전체 허용)")
        return v

    @field_validator("db_pool_size")
    @classmethod
    def _pool_size_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("1 이상이어야 합니다 (QueuePool 에서 0 은 무제한)")
        return v

    @field_validator("db_max_overflow")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("0 이상이어야 합니다")
        return v

    def missing(self, *fields: str) -> list[str]:
        """빠진 필드의 환경 변수 이름만 돌려준다. 503 안내문에 그대로 쓴다."""
        return [ENV_PREFIX + f.upper() for f in fields if getattr(self, f) is None]

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise RuntimeError(f"미구성: {ENV_PREFIX}DATABASE_URL 이 없습니다")
        return self.database_url.get_secret_value()


@cache
def get_settings() -> Settings:
    """한 번만 읽는다. 시험은 get_settings.cache_clear()."""
    return Settings()
