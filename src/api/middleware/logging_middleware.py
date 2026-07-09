"""CFA-Agent 日志中间件"""
from __future__ import annotations

import time
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("cfa-agent")


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件

    记录所有 HTTP 请求和响应的基本信息
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        logger.info(f"Request: {request.method} {request.url.path}")

        response: Response = await call_next(request)

        duration = time.time() - start_time
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"status={response.status_code} duration={duration:.3f}s"
        )

        response.headers["X-Process-Time"] = str(duration)
        return response