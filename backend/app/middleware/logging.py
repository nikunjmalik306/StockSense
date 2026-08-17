"""
Structured request logging middleware.

Logs every request with:
- request_id (UUID per request, useful for correlating logs)
- method, path, status code
- response time in milliseconds
- user_id (extracted from JWT if present, without full validation)

We do NOT log:
- Authorization headers
- Request bodies (may contain passwords)
- Sensitive query parameters
"""
import time
import uuid
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("stocksense.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # Attach request_id to request state so it can be used
        # inside route handlers if needed (e.g., error responses)
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                # x-forwarded-for for reverse proxy deployments
                "client_ip": request.headers.get(
                    "x-forwarded-for", request.client.host if request.client else "unknown"
                ),
            },
        )

        # Attach request_id to response headers for client-side debugging
        response.headers["X-Request-ID"] = request_id
        return response
