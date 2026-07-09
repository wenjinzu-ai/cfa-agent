"""CFA-Agent 输入护栏

注入检测：检测 Prompt 注入、越狱等恶意输入
敏感词过滤：过滤输入中的敏感词汇
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("cfa-agent.guardrails.input")


class InputGuard:
    """输入护栏

    职责：
    - 检测 Prompt 注入攻击
    - 检测越狱尝试
    - 过滤敏感信息
    - 检测编码绕过尝试
    """

    PROMPT_INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
        re.compile(r"forget\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
        re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"sudo\s+mode", re.IGNORECASE),
        re.compile(r"developer\s+mode", re.IGNORECASE),
        re.compile(r"jailbreak", re.IGNORECASE),
        re.compile(r"DAN\s+mode", re.IGNORECASE),
        re.compile(r"override\s+(safety|security|guard)", re.IGNORECASE),
        re.compile(r"bypass\s+(safety|security|filter|guard)", re.IGNORECASE),
        re.compile(r"pretend\s+you\s+(are|can|have)", re.IGNORECASE),
        re.compile(r"act\s+as\s+if\s+you", re.IGNORECASE),
        re.compile(r"roleplay\s+as", re.IGNORECASE),
        re.compile(r"模拟.*系统", re.IGNORECASE),
        re.compile(r"忽略.*指令", re.IGNORECASE),
        re.compile(r"绕过.*安全", re.IGNORECASE),
        re.compile(r"假装.*你是", re.IGNORECASE),
    ]

    JAILBREAK_PATTERNS = [
        re.compile(r"what\s+would\s+you\s+do\s+if\s+you\s+(had|could|were)", re.IGNORECASE),
        re.compile(r"hypothetically\s*,?\s*(if|you)", re.IGNORECASE),
        re.compile(r"in\s+a\s+fictional\s+world", re.IGNORECASE),
        re.compile(r"for\s+(research|educational|academic)\s+purposes?\s*[,，]?\s*(please|can|could)", re.IGNORECASE),
        re.compile(r"假设.*场景", re.IGNORECASE),
        re.compile(r"虚构.*世界", re.IGNORECASE),
        re.compile(r"学术.*目的", re.IGNORECASE),
    ]

    ENCODING_BYPASS_PATTERNS = [
        re.compile(r"base64\s*[:：]\s*[A-Za-z0-9+/=]{10,}", re.IGNORECASE),
        re.compile(r"hex\s*[:：]\s*[0-9a-fA-F]{10,}", re.IGNORECASE),
        re.compile(r"unicode\s*[:：]\s*\\u[0-9a-fA-F]{4,}", re.IGNORECASE),
        re.compile(r"rot13\s*[:：]", re.IGNORECASE),
    ]

    def __init__(
        self,
        custom_sensitive_words: Optional[list[str]] = None,
        max_input_length: int = 10000,
        injection_threshold: float = 0.5,
    ):
        self._sensitive_words = set(custom_sensitive_words or [])
        self._max_input_length = max_input_length
        self._injection_threshold = injection_threshold

    async def check(self, user_input: str) -> dict:
        """检查输入安全性

        Args:
            user_input: 用户输入文本

        Returns:
            dict: {
                "safe": bool,
                "reason": str | None,
                "risk_level": "low" | "medium" | "high" | "critical",
                "violations": list[str],
                "filtered_input": str,
            }
        """
        if not user_input or not user_input.strip():
            return {
                "safe": True,
                "reason": None,
                "risk_level": "low",
                "violations": [],
                "filtered_input": user_input,
            }

        violations = []
        risk_score = 0.0

        if len(user_input) > self._max_input_length:
            violations.append(f"输入长度超限（{len(user_input)}/{self._max_input_length}）")
            risk_score += 0.6

        injection_results = self._detect_prompt_injection(user_input)
        if injection_results:
            violations.extend(injection_results)
            risk_score += 0.6 * len(injection_results)

        jailbreak_results = self._detect_jailbreak(user_input)
        if jailbreak_results:
            violations.extend(jailbreak_results)
            risk_score += 0.5 * len(jailbreak_results)

        encoding_results = self._detect_encoding_bypass(user_input)
        if encoding_results:
            violations.extend(encoding_results)
            risk_score += 0.5 * len(encoding_results)

        sensitive_results = self._detect_sensitive_words(user_input)
        if sensitive_results:
            violations.extend(sensitive_results)
            risk_score += 0.6 * len(sensitive_results)

        risk_level = self._calculate_risk_level(risk_score)
        safe = risk_score < self._injection_threshold
        filtered_input = self._filter_sensitive_words(user_input) if not safe else user_input

        if not safe:
            logger.warning(f"Input guard triggered: risk_level={risk_level}, violations={violations}")

        return {
            "safe": safe,
            "reason": "; ".join(violations) if violations else None,
            "risk_level": risk_level,
            "violations": violations,
            "filtered_input": filtered_input,
        }

    def _detect_prompt_injection(self, text: str) -> list[str]:
        """检测 Prompt 注入攻击

        Args:
            text: 输入文本

        Returns:
            list[str]: 检测到的注入模式列表
        """
        results = []
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                results.append(f"Prompt注入检测: 匹配模式 '{pattern.pattern}'")
        return results

    def _detect_jailbreak(self, text: str) -> list[str]:
        """检测越狱尝试

        Args:
            text: 输入文本

        Returns:
            list[str]: 检测到的越狱模式列表
        """
        results = []
        for pattern in self.JAILBREAK_PATTERNS:
            if pattern.search(text):
                results.append(f"越狱检测: 匹配模式 '{pattern.pattern}'")
        return results

    def _detect_encoding_bypass(self, text: str) -> list[str]:
        """检测编码绕过尝试

        Args:
            text: 输入文本

        Returns:
            list[str]: 检测到的编码绕过模式列表
        """
        results = []
        for pattern in self.ENCODING_BYPASS_PATTERNS:
            if pattern.search(text):
                results.append(f"编码绕过检测: 匹配模式 '{pattern.pattern}'")
        return results

    def _detect_sensitive_words(self, text: str) -> list[str]:
        """检测敏感词

        Args:
            text: 输入文本

        Returns:
            list[str]: 检测到的敏感词列表
        """
        results = []
        text_lower = text.lower()
        for word in self._sensitive_words:
            if word.lower() in text_lower:
                results.append(f"敏感词检测: '{word}'")
        return results

    def _filter_sensitive_words(self, text: str) -> str:
        """过滤敏感词

        Args:
            text: 输入文本

        Returns:
            str: 过滤后的文本
        """
        filtered = text
        for word in self._sensitive_words:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            filtered = pattern.sub("*" * len(word), filtered)
        return filtered

    @staticmethod
    def _calculate_risk_level(score: float) -> str:
        """计算风险等级

        Args:
            score: 风险分数

        Returns:
            str: 风险等级
        """
        if score >= 1.0:
            return "critical"
        elif score >= 0.7:
            return "high"
        elif score >= 0.4:
            return "medium"
        return "low"