from __future__ import annotations
from starlette.responses import JSONResponse

class BearerAuthMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if headers.get("authorization") != f"Bearer {self.token}":
            return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)
