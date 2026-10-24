"""SQLAlchemy 표. 이 모듈이 전부 재노출한다 — alembic env.py 는 `import classfit.models` 한 줄로 다 본다.

정면(facade)이므로 시험에서 여기 이름을 monkeypatch 하면 stale_patch_guard 가 막는다.
새 표를 만들면 여기에 한 줄 더한다.
"""

from classfit.models.admin import AdminAccount
from classfit.models.advanced import AdvancedCourse
from classfit.models.attachment import SessionAttachment
from classfit.models.audit import AuditLog
from classfit.models.auth import AuthAttempt, AuthSession, EmailVerification
from classfit.models.base import Base, BigIdMixin, TimestampMixin
from classfit.models.course import Course, CourseDay, CourseSession, Section
from classfit.models.curriculum import Curriculum, CurriculumFile, CurriculumSlot
from classfit.models.diagnosis import Company, DiagLink, Diagnosis
from classfit.models.document import DocumentType, InstructorDocument
from classfit.models.instructor import Instructor, InstructorTag
from classfit.models.invite_code import InviteCode
from classfit.models.learner import Enrollment, Learner
from classfit.models.outbox import MailOutbox
from classfit.models.pool import Capability, CapabilityFile, PoolCourse, PoolCourseFile
from classfit.models.record import Photo, SessionRecord
from classfit.models.stored_file import StoredFile
from classfit.models.survey import Survey, SurveyResponse, SurveyTemplate
from classfit.models.tag import Tag

__all__ = [
    "AdminAccount",
    "AdvancedCourse",
    "AuditLog",
    "AuthAttempt",
    "AuthSession",
    "Base",
    "BigIdMixin",
    "Capability",
    "CapabilityFile",
    "Company",
    "Course",
    "CourseDay",
    "CourseSession",
    "Curriculum",
    "CurriculumFile",
    "CurriculumSlot",
    "DiagLink",
    "Diagnosis",
    "DocumentType",
    "EmailVerification",
    "Enrollment",
    "Instructor",
    "InstructorDocument",
    "InstructorTag",
    "InviteCode",
    "Learner",
    "MailOutbox",
    "Photo",
    "PoolCourse",
    "PoolCourseFile",
    "Section",
    "SessionAttachment",
    "SessionRecord",
    "StoredFile",
    "Survey",
    "SurveyResponse",
    "SurveyTemplate",
    "Tag",
    "TimestampMixin",
]
