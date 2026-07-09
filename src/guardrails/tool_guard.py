"""CFA-Agent 工具调用护栏

限制和审计工具调用行为
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("cfa-agent.guardrails.tool")


class ToolGuard:
    """工具调用护栏

    职责：
    - 检查工具调用权限
    - 限制工具调用频率
    - 审计工具调用行为
    - 高危操作审批
    - 参数校验
    """

    HIGH_RISK_TOOLS = {
        "code_executor",
        "file_ops_delete",
        "api_caller",
    }

    def __init__(
        self,
        rate_limits: Optional[dict[str, int]] = None,
        default_rate_limit: int = 60,
        rate_limit_window: float = 60.0,
        blocked_tools: Optional[set[str]] = None,
        agent_permissions: Optional[dict[str, set[str]]] = None,
        require_approval: Optional[set[str]] = None,
    ):
        self._rate_limits = rate_limits or {}
        self._default_rate_limit = default_rate_limit
        self._rate_limit_window = rate_limit_window
        self._blocked_tools = blocked_tools or set()
        self._agent_permissions = agent_permissions or {}
        self._require_approval = require_approval or self.HIGH_RISK_TOOLS.copy()
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)
        self._audit_log: list[dict] = []

    async def check_permission(self, tool_name: str, agent_id: str) -> dict:
        """检查工具调用权限

        Args:
            tool_name: 工具名称
            agent_id: 智能体 ID

        Returns:
            dict: {"allowed": bool, "reason": str | None}
        """
        if tool_name in self._blocked_tools:
            logger.warning(f"Tool {tool_name} is blocked")
            return {
                "allowed": False,
                "reason": f"工具 '{tool_name}' 已被禁用",
            }

        if self._agent_permissions:
            allowed_tools = self._agent_permissions.get(agent_id, set())
            if allowed_tools and tool_name not in allowed_tools:
                logger.warning(f"Agent {agent_id} has no permission for tool {tool_name}")
                return {
                    "allowed": False,
                    "reason": f"智能体 '{agent_id}' 无权使用工具 '{tool_name}'",
                }

        return {
            "allowed": True,
            "reason": None,
        }

    async def check_rate_limit(self, tool_name: str, agent_id: str) -> dict:
        """检查工具调用频率限制

        Args:
            tool_name: 工具名称
            agent_id: 智能体 ID

        Returns:
            dict: {"allowed": bool, "reason": str | None, "remaining": int}
        """
        key = f"{agent_id}:{tool_name}"
        now = time.time()

        self._call_timestamps[key] = [
            ts for ts in self._call_timestamps[key]
            if now - ts < self._rate_limit_window
        ]

        limit = self._rate_limits.get(tool_name, self._default_rate_limit)
        current_count = len(self._call_timestamps[key])
        remaining = limit - current_count

        if current_count >= limit:
            logger.warning(
                f"Rate limit exceeded for {tool_name} by {agent_id}: "
                f"{current_count}/{limit} in {self._rate_limit_window}s"
            )
            return {
                "allowed": False,
                "reason": f"工具 '{tool_name}' 调用频率超限（{current_count}/{limit}次/{self._rate_limit_window}秒）",
                "remaining": 0,
            }

        self._call_timestamps[key].append(now)

        return {
            "allowed": True,
            "reason": None,
            "remaining": remaining - 1,
        }

    async def check_high_risk(self, tool_name: str, args: dict) -> dict:
        """检查高危操作

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            dict: {"allowed": bool, "reason": str | None, "requires_approval": bool}
        """
        requires_approval = tool_name in self._require_approval

        if requires_approval:
            risk_factors = self._assess_risk(tool_name, args)
            if risk_factors:
                logger.warning(
                    f"High-risk tool call: {tool_name}, risk_factors={risk_factors}"
                )
                return {
                    "allowed": True,
                    "reason": None,
                    "requires_approval": True,
                    "risk_factors": risk_factors,
                }

        return {
            "allowed": True,
            "reason": None,
            "requires_approval": False,
        }

    async def validate_parameters(self, tool_name: str, args: dict, schema: dict) -> dict:
        """校验工具参数

        Args:
            tool_name: 工具名称
            args: 工具参数
            schema: 参数 Schema

        Returns:
            dict: {"valid": bool, "errors": list[str]}
        """
        errors = []

        if not schema:
            return {"valid": True, "errors": []}

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for req_field in required:
            if req_field not in args:
                errors.append(f"缺少必需参数: '{req_field}'")

        for key, value in args.items():
            if key not in properties:
                continue

            prop_schema = properties[key]
            expected_type = prop_schema.get("type")

            if expected_type and not self._check_type(value, expected_type):
                errors.append(f"参数 '{key}' 类型错误: 期望 {expected_type}, 实际 {type(value).__name__}")

            if "enum" in prop_schema and value not in prop_schema["enum"]:
                errors.append(f"参数 '{key}' 值不在允许范围: {prop_schema['enum']}")

            if "minimum" in prop_schema and isinstance(value, (int, float)) and value < prop_schema["minimum"]:
                errors.append(f"参数 '{key}' 值过小: 最小值 {prop_schema['minimum']}")

            if "maximum" in prop_schema and isinstance(value, (int, float)) and value > prop_schema["maximum"]:
                errors.append(f"参数 '{key}' 值过大: 最大值 {prop_schema['maximum']}")

            if "maxLength" in prop_schema and isinstance(value, str) and len(value) > prop_schema["maxLength"]:
                errors.append(f"参数 '{key}' 长度超限: 最大 {prop_schema['maxLength']} 字符")

        if errors:
            logger.warning(f"Parameter validation failed for {tool_name}: {errors}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    async def full_check(
        self,
        tool_name: str,
        agent_id: str,
        args: dict,
        schema: Optional[dict] = None,
    ) -> dict:
        """执行完整的工具调用检查

        Args:
            tool_name: 工具名称
            agent_id: 智能体 ID
            args: 工具参数
            schema: 参数 Schema

        Returns:
            dict: {
                "allowed": bool,
                "reasons": list[str],
                "requires_approval": bool,
                "checks": dict,
            }
        """
        reasons = []
        requires_approval = False
        checks = {}

        perm_check = await self.check_permission(tool_name, agent_id)
        checks["permission"] = perm_check
        if not perm_check["allowed"]:
            reasons.append(perm_check["reason"])

        rate_check = await self.check_rate_limit(tool_name, agent_id)
        checks["rate_limit"] = rate_check
        if not rate_check["allowed"]:
            reasons.append(rate_check["reason"])

        risk_check = await self.check_high_risk(tool_name, args)
        checks["high_risk"] = risk_check
        if risk_check.get("requires_approval"):
            requires_approval = True

        if schema:
            param_check = await self.validate_parameters(tool_name, args, schema)
            checks["parameters"] = param_check
            if not param_check["valid"]:
                reasons.extend(param_check["errors"])

        allowed = len(reasons) == 0

        await self._audit(tool_name, agent_id, args, allowed)

        return {
            "allowed": allowed,
            "reasons": reasons,
            "requires_approval": requires_approval,
            "checks": checks,
        }

    async def _audit(self, tool_name: str, agent_id: str, args: dict, allowed: bool) -> None:
        """审计工具调用

        Args:
            tool_name: 工具名称
            agent_id: 智能体 ID
            args: 工具参数
            allowed: 是否允许
        """
        record = {
            "timestamp": time.time(),
            "tool_name": tool_name,
            "agent_id": agent_id,
            "args_keys": list(args.keys()),
            "allowed": allowed,
        }

        self._audit_log.append(record)

        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

    def _assess_risk(self, tool_name: str, args: dict) -> list[str]:
        """评估风险因素

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            list[str]: 风险因素列表
        """
        risk_factors = []

        if tool_name == "code_executor":
            code = args.get("code", "")
            dangerous_patterns = [
                ("os.system", "系统命令执行"),
                ("subprocess", "子进程调用"),
                ("eval(", "动态代码执行"),
                ("exec(", "动态代码执行"),
                ("__import__", "动态导入"),
                ("open(", "文件操作"),
                ("shutil.rmtree", "目录删除"),
                ("os.remove", "文件删除"),
            ]
            for pattern, desc in dangerous_patterns:
                if pattern in code:
                    risk_factors.append(f"危险代码模式: {desc} ({pattern})")

        elif tool_name == "file_ops_delete":
            path = args.get("path", "")
            critical_paths = ["/etc", "/usr", "/system", "C:\\Windows", "C:\\Program"]
            for cp in critical_paths:
                if path.startswith(cp):
                    risk_factors.append(f"删除关键系统路径: {path}")
                    break

        elif tool_name == "api_caller":
            method = args.get("method", "GET").upper()
            if method in ("DELETE", "PUT", "PATCH"):
                risk_factors.append(f"高危 HTTP 方法: {method}")

        return risk_factors

    @staticmethod
    def _check_type(value: object, expected_type: str) -> bool:
        """检查值类型

        Args:
            value: 值
            expected_type: 期望类型字符串

        Returns:
            bool: 类型是否匹配
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        if expected_type == "integer" and isinstance(value, bool):
            return False
        return isinstance(value, expected)

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """获取审计日志

        Args:
            limit: 返回条数限制

        Returns:
            list[dict]: 审计记录列表
        """
        return self._audit_log[-limit:]

    def clear_rate_limits(self) -> None:
        """清除频率限制计数器"""
        self._call_timestamps.clear()