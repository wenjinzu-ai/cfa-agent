from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class GuardrailAction(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    WARN = "warn"


class GuardrailSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailResult(BaseModel):
    action: GuardrailAction = GuardrailAction.PASS
    rule_name: str = ""
    severity: GuardrailSeverity = GuardrailSeverity.LOW
    message: str = ""
    details: dict = Field(default_factory=dict)
    sanitized_content: str | None = None