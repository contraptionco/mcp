import pytest
from httpx import ASGITransport, AsyncClient

from src.http_middleware import build_http_middleware
from src.mcp_server import mcp


@pytest.mark.asyncio
async def test_browser_request_redirects_to_repo() -> None:
    app = mcp.http_app(path="/", middleware=build_http_middleware())

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/", headers={"accept": "text/html"})

    assert response.status_code == 307
    assert response.headers["location"] == "https://github.com/contraptionco/mcp"
