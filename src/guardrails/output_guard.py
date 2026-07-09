"""CFA-Agent 输出护栏

内容过滤：检测和过滤不当输出
格式校验：确保输出格式合规
敏感信息泄露检测：防止输出中泄露敏感数据
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("cfa-agent.guardrails.output")


class OutputGuard:
    """输出护栏

    职责：
    - 过滤敏感信息泄露（API Key、密码、Token 等）
    - 检测不当内容
    - 确保输出格式合规
    - 检测幻觉/虚假信息标记
    """

    SENSITIVE_PATTERNS = [
        (re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']?[A-Za-z0-9\-_]{20,}["\']?', re.IGNORECASE), "API Key"),
        (re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']{8,}["\']?', re.IGNORECASE), "密码"),
        (re.compile(r'(?:secret|token|bearer)\s*[:=]\s*["\']?[A-Za-z0-9\-_.]{20,}["\']?', re.IGNORECASE), "Secret/Token"),
        (re.compile(r'(?:aws_access_key_id)\s*[:=]\s*["\']?AKIA[A-Z0-9]{16}["\']?', re.IGNORECASE), "AWS Access Key"),
        (re.compile(r'(?:aws_secret_access_key)\s*[:=]\s*["\']?[A-Za-z0-9/+=]{40}["\']?', re.IGNORECASE), "AWS Secret Key"),
        (re.compile(r'(?:private[_-]?key)\s*[:=]\s*["\']?-----BEGIN[A-Z\s]+PRIVATE KEY-----', re.IGNORECASE), "私钥"),
        (re.compile(r'(?:mongodb|mysql|postgres|redis)://[^\s"\']+', re.IGNORECASE), "数据库连接串"),
        (re.compile(r'(?:jdbc):[^\s"\']+', re.IGNORECASE), "JDBC连接串"),
        (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE), "邮箱地址"),
        (re.compile(r'(?:身份证|id[_-]?card)\s*[:：]\s*\d{17}[\dXx]', re.IGNORECASE), "身份证号"),
        (re.compile(r'(?:phone|手机|电话)\s*[:：]\s*1[3-9]\d{9}', re.IGNORECASE), "手机号"),
        (re.compile(r'(?:银行卡|bank[_-]?card)\s*[:：]\s*\d{16,19}', re.IGNORECASE), "银行卡号"),
    ]

    INAPPROPRIATE_CONTENT_PATTERNS = [
        re.compile(r'(?:how\s+to|ways\s+to|methods?\s+for)\s+(hack|exploit|attack|damage|destroy)', re.IGNORECASE),
        re.compile(r'(?:制造|制作|合成)\s*(炸弹|毒药|武器)', re.IGNORECASE),
        re.compile(r'(?:hack|exploit|vulnerability)\s+(into|against)\s+a\s+(specific\s+)?(system|server|network|database)', re.IGNORECASE),
    ]

    HALLUCINATION_MARKERS = [
        re.compile(r'my\s+(?:last\s+)?(?:update|training|knowledge)\s+(?:cut(?:off)?\s+is|is|ends?)\s+(?:off|at|in|to)', re.IGNORECASE),
        re.compile(r'i\s+(?:don\'t|do\s+not)\s+have\s+(?:access\s+to|real-?time)', re.IGNORECASE),
        re.compile(r'(?:this|the\s+above)\s+(?:might|may|could)\s+be\s+(?:outdated|incorrect|wrong|inaccurate)', re.IGNORECASE),
    ]

    def __init__(
        self,
        custom_sensitive_patterns: Optional[list[tuple[str, str]]] = None,
        max_output_length: int = 50000,
        mask_char: str = "***REDACTED***",
    ):
        self._custom_patterns = []
        if custom_sensitive_patterns:
            for pattern_str, label in custom_sensitive_patterns:
                self._custom_patterns.append((re.compile(pattern_str, re.IGNORECASE), label))
        self._max_output_length = max_output_length
        self._mask_char = mask_char

    async def check(self, output: str) -> dict:
        """检查输出安全性

        Args:
            output: 输出文本

        Returns:
            dict: {
                "safe": bool,
                "reason": str | None,
                "filtered_output": str,
                "violations": list[str],
                "has_sensitive_data": bool,
                "has_inappropriate_content": bool,
            }
        """
        if not output or not output.strip():
            return {
                "safe": True,
                "reason": None,
                "filtered_output": output,
                "violations": [],
                "has_sensitive_data": False,
                "has_inappropriate_content": False,
            }

        violations = []
        has_sensitive = False
        has_inappropriate = False
        filtered_output = output

        if len(output) > self._max_output_length:
            violations.append(f"输出长度超限（{len(output)}/{self._max_output_length}）")
            filtered_output = filtered_output[:self._max_output_length]

        sensitive_results = self._detect_sensitive_data(output)
        if sensitive_results:
            has_sensitive = True
            violations.extend(sensitive_results)
            filtered_output = self._mask_sensitive_data(filtered_output)

        custom_results = self._detect_custom_patterns(output)
        if custom_results:
            has_sensitive = True
            violations.extend(custom_results)
            filtered_output = self._mask_custom_data(filtered_output)

        inappropriate_results = self._detect_inappropriate_content(output)
        if inappropriate_results:
            has_inappropriate = True
            violations.extend(inappropriate_results)

        safe = not has_inappropriate and not has_sensitive

        if not safe:
            logger.warning(f"Output guard triggered: violations={violations}")

        return {
            "safe": safe,
            "reason": "; ".join(violations) if violations else None,
            "filtered_output": filtered_output,
            "violations": violations,
            "has_sensitive_data": has_sensitive,
            "has_inappropriate_content": has_inappropriate,
        }

    def detect_hallucination_markers(self, output: str) -> list[str]:
        """检测幻觉标记

        Args:
            output: 输出文本

        Returns:
            list[str]: 检测到的幻觉标记
        """
        markers = []
        for pattern in self.HALLUCINATION_MARKERS:
            if pattern.search(output):
                markers.append(f"幻觉标记检测: 匹配模式 '{pattern.pattern}'")
        return markers

    def _detect_sensitive_data(self, text: str) -> list[str]:
        """检测敏感数据泄露

        Args:
            text: 输出文本

        Returns:
            list[str]: 检测到的敏感数据类型列表
        """
        results = []
        for pattern, label in self.SENSITIVE_PATTERNS:
            if pattern.search(text):
                results.append(f"敏感信息泄露检测: {label}")
        return results

    def _detect_custom_patterns(self, text: str) -> list[str]:
        """检测自定义敏感模式

        Args:
            text: 输出文本

        Returns:
            list[str]: 检测到的自定义敏感模式列表
        """
        results = []
        for pattern, label in self._custom_patterns:
            if pattern.search(text):
                results.append(f"自定义敏感模式检测: {label}")
        return results

    def _detect_inappropriate_content(self, text: str) -> list[str]:
        """检测不当内容

        Args:
            text: 输出文本

        Returns:
            list[str]: 检测到的不当内容列表
        """
        results = []
        for pattern in self.INAPPROPRIATE_CONTENT_PATTERNS:
            if pattern.search(text):
                results.append(f"不当内容检测: 匹配模式 '{pattern.pattern}'")
        return results

    def _mask_sensitive_data(self, text: str) -> str:
        """脱敏处理敏感数据

        Args:
            text: 输出文本

        Returns:
            str: 脱敏后的文本
        """
        masked = text
        for pattern, label in self.SENSITIVE_PATTERNS:
            masked = pattern.sub(f"[{label}{self._mask_char}]", masked)
        return masked

    def _mask_custom_data(self, text: str) -> str:
        """脱敏处理自定义敏感数据

        Args:
            text: 输出文本

        Returns:
            str: 脱敏后的文本
        """
        masked = text
        for pattern, label in self._custom_patterns:
            masked = pattern.sub(f"[{label}{self._mask_char}]", masked)
        return masked