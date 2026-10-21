"""API 정본은 /v1/openapi.json 이다. 운영 앱의 경로 집합 = expected_paths.txt, 시험 전용 /v1/_probe 없음."""

from pathlib import Path

import httpx

from classfit.core.config import Settings
from classfit.main import create_app

EXPECTED = Path(__file__).with_name("expected_paths.txt")


async def test_openapi_paths_match_expected_without_probe() -> None:
    application = create_app(Settings())  # probe 를 붙이지 않은 새 앱
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        paths = set((await c.get("/v1/openapi.json")).json()["paths"])
    assert not any(p.startswith("/v1/_probe") for p in paths)
    assert sorted(paths) == EXPECTED.read_text(encoding="utf-8").split()
