from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

import yaml

from src.common.logger import logger


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _safe_format(template: str, **variables: Any) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


class PromptManager:
    _instance: PromptManager | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._templates: dict[str, dict] = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> PromptManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def load_all(self) -> None:
        self._templates = {}
        if not PROMPTS_DIR.exists():
            logger.warning("Prompts directory not found: %s", PROMPTS_DIR)
            self._loaded = True
            return
        for yaml_file in PROMPTS_DIR.rglob("*.yaml"):
            rel_path = yaml_file.relative_to(PROMPTS_DIR)
            key = str(rel_path).replace("\\", "/").replace(".yaml", "")
            with open(yaml_file, "r", encoding="utf-8") as f:
                self._templates[key] = yaml.safe_load(f)
        logger.info("Loaded %d prompt templates from %s", len(self._templates), PROMPTS_DIR)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_all()

    def get(self, template_key: str, **variables: Any) -> tuple[str, str]:
        self._ensure_loaded()
        template = self._templates.get(template_key)
        if template is None:
            logger.warning("Prompt template not found: %s", template_key)
            return "", ""
        system = template.get("system", "")
        user = template.get("user", "")
        if variables:
            system = _safe_format(system, **variables)
            user = _safe_format(user, **variables)
        return system, user

    def get_system_prompt(self, template_key: str, **variables: Any) -> str:
        system, _ = self.get(template_key, **variables)
        return system

    def get_user_prompt(self, template_key: str, **variables: Any) -> str:
        _, user = self.get(template_key, **variables)
        return user

    def build_messages(
        self,
        template_key: str,
        history: list[dict] | None = None,
        **variables: Any,
    ) -> list[dict]:
        system, user = self.get(template_key, **variables)
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})
        return messages

    def list_templates(self) -> list[str]:
        self._ensure_loaded()
        return list(self._templates.keys())

    def reset(self) -> None:
        self._templates = {}
        self._loaded = False