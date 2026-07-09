"""CFA-Agent 统一响应 Schema"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    success: bool
    message: str = ""
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应格式"""
    success: bool
    message: str = ""
    data: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorResponse(BaseModel):
    """错误响应格式"""
    success: bool = False
    message: str
    error_code: str | None = None
    details: Any | None = None