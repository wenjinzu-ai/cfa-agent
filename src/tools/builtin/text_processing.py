"""CFA-Agent 文本处理工具"""
from __future__ import annotations

import json
import re
from typing import Any

from src.tools.base import BaseTool


class TextProcessing(BaseTool):
    """文本处理工具

    提供文本摘要、实体提取、翻译、格式化等操作
    """

    name: str = "text_processing"
    description: str = (
        "Process text: summarize, extract entities, translate, format, "
        "extract code blocks, spell check, etc."
    )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to process",
                },
                "operation": {
                    "type": "string",
                    "enum": [
                        "summarize",
                        "extract_entities",
                        "translate",
                        "format_json",
                        "extract_code",
                        "spell_check",
                        "word_count",
                        "extract_keywords",
                        "clean_whitespace",
                    ],
                    "description": "Text processing operation",
                },
                "target_language": {
                    "type": "string",
                    "description": "Target language for translation (e.g., 'en', 'zh', 'ja')",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length for summarize operation",
                    "default": 200,
                },
            },
            "required": ["text", "operation"],
        }

    async def execute(self, **kwargs) -> dict[str, Any]:
        text = kwargs.get("text", "")
        operation = kwargs.get("operation", "")

        if not text:
            return {"operation": operation, "result": "", "error": "Text is required"}

        try:
            if operation == "summarize":
                return await self._summarize(text, kwargs.get("max_length", 200))
            elif operation == "extract_entities":
                return await self._extract_entities(text)
            elif operation == "translate":
                return await self._translate(text, kwargs.get("target_language", "en"))
            elif operation == "format_json":
                return await self._format_json(text)
            elif operation == "extract_code":
                return await self._extract_code(text)
            elif operation == "spell_check":
                return await self._spell_check(text)
            elif operation == "word_count":
                return await self._word_count(text)
            elif operation == "extract_keywords":
                return await self._extract_keywords(text)
            elif operation == "clean_whitespace":
                return await self._clean_whitespace(text)
            else:
                return {"operation": operation, "result": "", "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"operation": operation, "result": "", "error": str(e)}

    async def _summarize(self, text: str, max_length: int) -> dict[str, Any]:
        sentences = re.split(r"[.!?。！？]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 3:
            summary = text[:max_length] if len(text) > max_length else text
        else:
            summary = " ".join(sentences[:3])
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."

        return {
            "operation": "summarize",
            "result": summary,
            "original_length": len(text),
            "summary_length": len(summary),
        }

    async def _extract_entities(self, text: str) -> dict[str, Any]:
        entities = {
            "emails": re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text),
            "urls": re.findall(r"https?://[^\s]+", text),
            "phone_numbers": re.findall(r"\+?[\d\s-]{10,15}", text),
            "dates": re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", text),
            "numbers": re.findall(r"\d+\.?\d*", text),
        }

        return {
            "operation": "extract_entities",
            "result": entities,
            "total_entities": sum(len(v) for v in entities.values()),
        }

    async def _translate(self, text: str, target_language: str) -> dict[str, Any]:
        return {
            "operation": "translate",
            "result": f"[Translation placeholder - requires LLM for actual translation to {target_language}]",
            "target_language": target_language,
            "note": "Use LLM-based translation for accurate results",
        }

    async def _format_json(self, text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            return {
                "operation": "format_json",
                "result": formatted,
                "valid": True,
            }
        except json.JSONDecodeError as e:
            return {
                "operation": "format_json",
                "result": "",
                "valid": False,
                "error": f"Invalid JSON: {str(e)}",
            }

    async def _extract_code(self, text: str) -> dict[str, Any]:
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", text, re.DOTALL)
        inline_code = re.findall(r"`([^`]+)`", text)

        result = []
        for lang, code in code_blocks:
            result.append({"language": lang or "unknown", "code": code.strip(), "type": "block"})
        for code in inline_code:
            result.append({"language": "unknown", "code": code, "type": "inline"})

        return {
            "operation": "extract_code",
            "result": result,
            "total_blocks": len(result),
        }

    async def _spell_check(self, text: str) -> dict[str, Any]:
        return {
            "operation": "spell_check",
            "result": "[Spell check placeholder - requires spell checker library]",
            "note": "Install spellchecker library for actual spell checking",
        }

    async def _word_count(self, text: str) -> dict[str, Any]:
        words = text.split()
        chars = len(text)
        chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
        lines = text.count("\n") + 1

        return {
            "operation": "word_count",
            "result": {
                "words": len(words),
                "characters": chars,
                "characters_no_spaces": chars_no_spaces,
                "lines": lines,
            },
        }

    async def _extract_keywords(self, text: str) -> dict[str, Any]:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1

        stopwords = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was", "one", "our", "out"}
        keywords = sorted(
            [(w, c) for w, c in word_freq.items() if w not in stopwords],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "operation": "extract_keywords",
            "result": [{"word": w, "count": c} for w, c in keywords],
        }

    async def _clean_whitespace(self, text: str) -> dict[str, Any]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return {
            "operation": "clean_whitespace",
            "result": cleaned,
            "original_length": len(text),
            "cleaned_length": len(cleaned),
        }