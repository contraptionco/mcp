"""HTTP middleware utilities for the MCP server."""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp

DEFAULT_REDIRECT_URL = "https://github.com/contraptionco/mcp"


class RedirectNonStreamableClientMiddleware(BaseHTTPMiddleware):
    """Redirect plain HTTP clients that cannot negotiate the MCP stream."""

    def __init__(self, app: ASGIApp, redirect_url: str = DEFAULT_REDIRECT_URL) -> None:
        super().__init__(app)
        self._redirect_url = redirect_url

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        accept_header = request.headers.get("accept", "").lower()
        path = request.url.path

        if (
            request.method in {"GET", "HEAD"}
            and path == "/"
            and "text/event-stream" not in accept_header
        ):
            return RedirectResponse(self._redirect_url, status_code=307)

        return await call_next(request)


def build_http_middleware(redirect_url: str = DEFAULT_REDIRECT_URL) -> list[Middleware]:
    """Return the middleware stack for the HTTP transport."""

    return [
        Middleware(RedirectNonStreamableClientMiddleware, redirect_url=redirect_url),
    ]
