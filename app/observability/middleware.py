"""Starlette middleware that instruments every HTTP request with Prometheus metrics."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip instrumenting the /metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = request.url.path
        start = time.perf_counter()

        response = await call_next(request)

        elapsed = time.perf_counter() - start
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(elapsed)

        return response
