"""Request correlation, structured logging, security headers and metrics.

Logs deliberately contain only operational metadata (method, route template,
status, latency, request id). Query strings, bodies and record content are
never logged because they can contain personal or investigative data.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
client_ip_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("client_ip", default=None)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
access_logger = logging.getLogger("ai_crms.access")


def current_request_id() -> Optional[str]:
    return request_id_var.get()


def current_client_ip() -> Optional[str]:
    return client_ip_var.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or current_request_id(),
        }
        for key in ("method", "route", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root.handlers = [handler]
    root.setLevel(level)


class Metrics:
    """Minimal in-process request metrics (per worker process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.requests: Dict[str, int] = defaultdict(int)
        self.errors: Dict[str, int] = defaultdict(int)
        self.latency_ms_total: Dict[str, float] = defaultdict(float)
        self.latency_ms_max: Dict[str, float] = defaultdict(float)
        self.status_classes: Dict[str, int] = defaultdict(int)

    def record(self, route: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.requests[route] += 1
            self.latency_ms_total[route] += duration_ms
            self.latency_ms_max[route] = max(self.latency_ms_max[route], duration_ms)
            self.status_classes[f"{status // 100}xx"] += 1
            if status >= 500:
                self.errors[route] += 1

    def snapshot(self) -> dict:
        with self._lock:
            routes = {
                route: {
                    "requests": count,
                    "server_errors": self.errors.get(route, 0),
                    "avg_latency_ms": round(self.latency_ms_total[route] / count, 2) if count else 0.0,
                    "max_latency_ms": round(self.latency_ms_max[route], 2),
                }
                for route, count in sorted(self.requests.items())
            }
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "status_classes": dict(self.status_classes),
                "routes": routes,
            }


metrics = Metrics()


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, apply security headers and record access metrics."""

    def __init__(self, app, *, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)
        ip_token = client_ip_var.set(request.client.host if request.client else None)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            route = _route_template(request)
            metrics.record(f"{request.method} {route}", status, duration_ms)
            access_logger.info(
                "%s %s -> %s (%.1f ms)", request.method, route, status, duration_ms,
                extra={"method": request.method, "route": route, "status": status,
                       "duration_ms": round(duration_ms, 2), "request_id": request_id},
            )
            request_id_var.reset(rid_token)
            client_ip_var.reset(ip_token)

        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if self.hsts:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
