"""SQLAlchemy 표. 이 모듈이 전부 재노출한다 — alembic env.py 는 `import classfit.models` 한 줄로 다 본다.

정면(facade)이므로 시험에서 여기 이름을 monkeypatch 하면 stale_patch_guard 가 막는다.
새 표를 만들면 여기에 한 줄 더한다.
"""

from classfit.models.admin import AdminAccount
from classfit.models.audit import AuditLog
from classfit.models.auth import AuthAttempt, AuthSession, EmailVerification
from classfit.models.base import Base, BigIdMixin, TimestampMixin
from classfit.models.outbox import MailOutbox
from classfit.models.stored_file import StoredFile

__all__ = [
    "AdminAccount",
    "AuditLog",
    "AuthAttempt",
    "AuthSession",
    "Base",
    "BigIdMixin",
    "EmailVerification",
    "MailOutbox",
    "StoredFile",
    "TimestampMixin",
]
