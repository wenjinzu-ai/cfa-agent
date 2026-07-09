"""CFA-Agent API 调用工具"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from pydantic import Field

from src.tools.base import BaseTool


class APICaller(BaseTool):
    """API 调用工具

    提供安全的 HTTP 请求功能，支持各种 HTTP 方法
    """

    name: str = "api_caller"
    description: str = (
        "Make HTTP requests to external APIs. "
        "Supports GET, POST, PUT, DELETE, PATCH methods."
    )
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    default_headers: dict = Field(default_factory=lambda: {"Content-Type": "application/json"})

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "API endpoint URL",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP method",
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers (will merge with default headers)",
                },
                "body": {
                    "type": "object",
                    "description": "Request body (for POST/PUT/PATCH)",
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Request timeout in seconds (default: {self.timeout})",
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> dict[str, Any]:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers", {})
        body = kwargs.get("body")
        params = kwargs.get("params")
        timeout = kwargs.get("timeout", self.timeout)

        if not url:
            return {"error": "URL is required", "status": "error"}

        if not url.startswith(("http://", "https://")):
            return {"error": "URL must start with http:// or https://", "status": "error"}

        merged_headers = {**self.default_headers, **headers}

        try:
            result = await self._make_request(
                url=url,
                method=method,
                headers=merged_headers,
                body=body,
                params=params,
                timeout=timeout,
            )
            return result
        except Exception as e:
            return {
                "url": url,
                "method": method,
                "error": str(e),
                "status": "error",
            }

    async def _make_request(
        self,
        url: str,
        method: str,
        headers: dict,
        body: dict | None,
        params: dict | None,
        timeout: int,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            request_args = {
                "url": url,
                "method": method,
                "headers": headers,
            }

            if params:
                request_args["params"] = params

            if body and method in ["POST", "PUT", "PATCH"]:
                request_args["json"] = body

            response = await client.request(**request_args)

            try:
                response_body = response.json()
            except json.JSONDecodeError:
                response_body = response.text

            return {
                "url": url,
                "method": method,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "status": "success" if response.status_code < 400 else "error",
                "is_success": response.is_success,
            }

    async def on_before_execute(self, **kwargs) -> None:
        url = kwargs.get("url", "")
        sensitive_patterns = [
            "api_key",
            "apikey",
            "secret",
            "password",
            "token",
        ]

        for pattern in sensitive_patterns:
            if pattern in url.lower():
                print(f"[APICaller] Warning: URL may contain sensitive parameter: {pattern}")

        headers = kwargs.get("headers", {})
        for key in headers:
            if any(p in key.lower() for p in sensitive_patterns):
                print(f"[APICaller] Warning: Header may contain sensitive data: {key}")