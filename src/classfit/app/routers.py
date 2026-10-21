"""라우터 등록부. 새 자원은 여기 튜플에만 더한다. 라우터마다 APIRouter(prefix="/v1")."""

from classfit.app.endpoints import health

ROUTERS = (health.router,)
