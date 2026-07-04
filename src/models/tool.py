from pydantic import BaseModel, Field
from enum import Enum
from typing import Any


class ToolPermission(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK = "network"
    CODE_EXEC = "code_exec"
    DB_ACCESS = "db_access"
    PRIVILEGED = "privileged"


class ToolDefinition(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )
    permissions: list[ToolPermission] = Field(default_factory=list)
    timeout_seconds: int = 30
    retry_policy: dict[str, Any] = Field(
        default_factory=lambda: {"max_retries": 2, "backoff": "exponential"}
    )


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    token_used: int = 0