from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors import error_response

# Allowance for multipart framing around the file itself.
OVERHEAD_BYTES = 64 * 1024
_BODY_METHODS = {"POST", "PUT", "PATCH"}


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length is clearly too large.

    This is an early, cheap check. A client that omits Content-Length is still capped when the
    file is written to storage.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes + OVERHEAD_BYTES

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _BODY_METHODS:
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self.max_body_bytes:
                return error_response(
                    request, 413, "PAYLOAD_TOO_LARGE", "Request body is too large."
                )
        return await call_next(request)
