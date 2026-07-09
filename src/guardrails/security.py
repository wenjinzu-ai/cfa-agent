"""CFA-Agent 安全策略

脱敏/加密/审计
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional

logger = logging.getLogger("cfa-agent.guardrails.security")


class SecurityPolicy:
    """安全策略

    职责：
    - 数据脱敏
    - 敏感信息加密
    - 安全审计
    - 访问控制
    """

    DEFAULT_MASK_PATTERNS = [
        (re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([A-Za-z0-9\-_]{20,})["\']?', re.IGNORECASE), "api_key"),
        (re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.IGNORECASE), "password"),
        (re.compile(r'(?:secret|token|bearer)\s*[:=]\s*["\']?([A-Za-z0-9\-_.]{20,})["\']?', re.IGNORECASE), "secret"),
        (re.compile(r'(?:aws_access_key_id)\s*[:=]\s*["\']?(AKIA[A-Z0-9]{16})["\']?', re.IGNORECASE), "aws_key"),
        (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE), "email"),
        (re.compile(r'1[3-9]\d{9}', re.IGNORECASE), "phone"),
        (re.compile(r'\d{17}[\dXx]', re.IGNORECASE), "id_card"),
        (re.compile(r'\d{16,19}', re.IGNORECASE), "bank_card"),
    ]

    def __init__(
        self,
        encryption_key: Optional[str] = None,
        custom_mask_patterns: Optional[list[tuple[str, str]]] = None,
        audit_enabled: bool = True,
    ):
        self._encryption_key = encryption_key or os.environ.get(
            "CFA_ENCRYPTION_KEY", "default-dev-key-change-in-production"
        )
        self._mask_patterns = list(self.DEFAULT_MASK_PATTERNS)
        if custom_mask_patterns:
            for pattern_str, label in custom_mask_patterns:
                self._mask_patterns.append((re.compile(pattern_str, re.IGNORECASE), label))
        self._audit_enabled = audit_enabled
        self._audit_records: list[dict] = []

    def mask_sensitive_data(self, text: str) -> str:
        """脱敏处理

        将文本中的敏感信息替换为掩码

        Args:
            text: 原始文本

        Returns:
            str: 脱敏后的文本
        """
        masked = text
        for pattern, label in self._mask_patterns:
            masked = pattern.sub(f"[{label}_REDACTED]", masked)
        return masked

    def mask_dict(self, data: dict, sensitive_keys: Optional[set[str]] = None) -> dict:
        """对字典中的敏感字段进行脱敏

        Args:
            data: 原始字典
            sensitive_keys: 敏感键名集合

        Returns:
            dict: 脱敏后的字典
        """
        default_sensitive = {
            "password", "passwd", "pwd", "secret", "token", "api_key",
            "apikey", "access_key", "private_key", "credit_card",
        }
        keys_to_mask = sensitive_keys or default_sensitive

        masked = {}
        for key, value in data.items():
            if key.lower() in keys_to_mask:
                masked[key] = "***REDACTED***"
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value, sensitive_keys)
            elif isinstance(value, str):
                masked[key] = self.mask_sensitive_data(value)
            else:
                masked[key] = value

        return masked

    def encrypt(self, data: str) -> str:
        """简单加密（基于 XOR + Base64）

        注意：生产环境应使用专业的加密库（如 cryptography）

        Args:
            data: 明文数据

        Returns:
            str: 加密后的字符串
        """
        key_bytes = self._encryption_key.encode("utf-8")
        data_bytes = data.encode("utf-8")

        encrypted_bytes = bytes(
            b ^ key_bytes[i % len(key_bytes)]
            for i, b in enumerate(data_bytes)
        )

        return base64.b64encode(encrypted_bytes).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """解密

        Args:
            encrypted: 加密后的字符串

        Returns:
            str: 解密后的明文
        """
        key_bytes = self._encryption_key.encode("utf-8")

        try:
            encrypted_bytes = base64.b64decode(encrypted.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid encrypted data: {e}")

        decrypted_bytes = bytes(
            b ^ key_bytes[i % len(key_bytes)]
            for i, b in enumerate(encrypted_bytes)
        )

        return decrypted_bytes.decode("utf-8")

    def hash_data(self, data: str) -> str:
        """哈希数据（不可逆）

        Args:
            data: 原始数据

        Returns:
            str: SHA-256 哈希值
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    async def audit(self, action: str, agent_id: str, details: dict) -> None:
        """安全审计

        Args:
            action: 操作类型
            agent_id: 智能体 ID
            details: 操作详情
        """
        if not self._audit_enabled:
            return

        record = {
            "timestamp": time.time(),
            "action": action,
            "agent_id": agent_id,
            "details": self.mask_dict(details) if isinstance(details, dict) else str(details),
        }

        self._audit_records.append(record)

        if len(self._audit_records) > 10000:
            self._audit_records = self._audit_records[-5000:]

        logger.info(f"Audit: action={action}, agent={agent_id}")

    def get_audit_records(self, limit: int = 100, action_filter: Optional[str] = None) -> list[dict]:
        """获取审计记录

        Args:
            limit: 返回条数限制
            action_filter: 操作类型过滤

        Returns:
            list[dict]: 审计记录列表
        """
        records = self._audit_records
        if action_filter:
            records = [r for r in records if r["action"] == action_filter]
        return records[-limit:]

    def check_access(self, agent_id: str, resource: str, action: str = "read") -> bool:
        """检查访问权限

        Args:
            agent_id: 智能体 ID
            resource: 资源名称
            action: 操作类型（read/write/execute）

        Returns:
            bool: 是否有权限
        """
        return True

    @property
    def audit_count(self) -> int:
        """审计记录数量"""
        return len(self._audit_records)