from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "total": self.total_tokens,
        }


class TokenCounter:
    def __init__(self, budget_per_session: int = 50000):
        self.budget = budget_per_session
        self._session_usage: dict[str, TokenUsage] = {}
        self._task_usage: dict[str, TokenUsage] = {}

    def _get_or_create_session(self, session_id: str) -> TokenUsage:
        if session_id not in self._session_usage:
            self._session_usage[session_id] = TokenUsage()
        return self._session_usage[session_id]

    def _get_or_create_task(self, task_id: str) -> TokenUsage:
        if task_id not in self._task_usage:
            self._task_usage[task_id] = TokenUsage()
        return self._task_usage[task_id]

    def record(self, usage: dict | TokenUsage, session_id: str, task_id: str | None = None) -> None:
        if isinstance(usage, dict):
            u = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        else:
            u = usage
        self._get_or_create_session(session_id).add(u)
        if task_id:
            self._get_or_create_task(task_id).add(u)

    def get_session_usage(self, session_id: str) -> TokenUsage:
        return self._session_usage.get(session_id, TokenUsage())

    def get_task_usage(self, task_id: str) -> TokenUsage:
        return self._task_usage.get(task_id, TokenUsage())

    def is_over_budget(self, session_id: str) -> bool:
        usage = self._session_usage.get(session_id)
        if usage is None:
            return False
        return usage.total_tokens >= self.budget

    def estimate_tokens(self, text: str) -> int:
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 3.5 + other_chars / 4)

    def truncate_context(self, messages: list[dict], max_tokens: int = 4000) -> list[dict]:
        if not messages:
            return messages
        result = []
        remaining = list(messages)

        if remaining[0].get("role") == "system":
            result.append(remaining[0])
            remaining = remaining[1:]

        total = self.estimate_tokens(str(result))
        kept = []
        for msg in reversed(remaining):
            msg_tokens = self.estimate_tokens(str(msg))
            if total + msg_tokens > max_tokens:
                break
            kept.append(msg)
            total += msg_tokens

        kept.reverse()
        result.extend(kept)
        return result