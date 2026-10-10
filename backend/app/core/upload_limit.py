"""Reject oversized (or length-less) upload requests before the multipart body is parsed.

Starlette spools the whole multipart body to disk before a handler runs, so the per-assignment size limit
alone would still let a client push an arbitrarily large body. This ASGI middleware checks Content-Length
for the submission endpoint first. The precise per-assignment limit is enforced later on the file itself.
"""

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_UPLOAD_PATH = re.compile(
    r"^/api/v1/(student/assignments/[^/]+/submissions|faculty/assignments/[^/]+/attachments)$"
)
MULTIPART_OVERHEAD = 512 * 1024


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_file_mb: int):
        self.app = app
        self.max_body = max_file_mb * 1024 * 1024 + MULTIPART_OVERHEAD
        self.max_file_mb = max_file_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and _UPLOAD_PATH.match(scope["path"]):
            headers = dict(scope["headers"])
            raw = headers.get(b"content-length")
            if raw is None or not raw.isdigit():
                await self._reject(scope, receive, send, 411, "LENGTH_REQUIRED", "A Content-Length header is required.")
                return
            if int(raw) > self.max_body:
                await self._reject(
                    scope,
                    receive,
                    send,
                    413,
                    "FILE_TOO_LARGE",
                    f"The upload is larger than the {self.max_file_mb} MB limit.",
                )
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str) -> None:
        response = JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": message, "details": {}}},
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)
