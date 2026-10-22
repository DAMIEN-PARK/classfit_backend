"""라우터 등록부. 새 자원은 여기 튜플에만 더한다. 라우터마다 APIRouter(prefix="/v1")."""

from classfit.app.endpoints import (
    admins,
    attachments,
    auth,
    courses,
    enrollments,
    enter,
    files,
    health,
    invite_codes,
    portal,
    schedule,
)

ROUTERS = (
    health.router,
    auth.router,
    admins.router,
    files.router,
    courses.router,
    schedule.router,
    invite_codes.router,
    enter.router,
    portal.router,
    attachments.router,
    enrollments.router,
)
