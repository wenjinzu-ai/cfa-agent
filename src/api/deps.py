from __future__ import annotations

import threading

from src.core.agent import Agent

_agent: Agent | None = None
_lock = threading.Lock()


def get_agent() -> Agent:
    with _lock:
        if _agent is None:
            raise RuntimeError("Agent not initialized")
        return _agent


def set_agent(agent: Agent | None) -> None:
    global _agent
    with _lock:
        _agent = agent