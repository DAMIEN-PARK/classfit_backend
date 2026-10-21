import httpx

from classfit import __version__
from classfit.core.config import Settings
from classfit.main import create_app


async def test_health_reports_db_ok(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok", "version": __version__}


async def test_unknown_path_is_problem_json(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404 and body["instance"] == "/v1/nope" and body["type"]


async def test_openapi_is_always_open_and_lists_routes(client: httpx.AsyncClient) -> None:
    # 경로 수는 app.routes 가 아니라 openapi paths 로 센다 (포함 라우터가 게으르게 담길 수 있다)
    r = await client.get("/v1/openapi.json")
    assert r.status_code == 200
    assert "/v1/health" in r.json()["paths"]


async def test_docs_closed_unless_switched_on(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/docs")).status_code == 404


async def test_docs_open_when_switched_on() -> None:
    application = create_app(Settings(_env_file=None, enable_docs=True))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/v1/docs")).status_code == 200
        assert (await c.get("/v1/openapi.json")).status_code == 200
