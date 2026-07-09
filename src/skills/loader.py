"""CFA-Agent 技能加载器

扫描 config/skills/ 下的 .md 文件，加载技能提示词模板
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class SkillLoader:
    """技能加载器

    职责：
    - 扫描 config/skills/ 目录下的 .md 文件
    - 解析 YAML Frontmatter 格式的技能定义
    - 返回技能元数据和提示词模板
    """

    def __init__(self, skills_dir: str | Path = "config/skills"):
        self._skills_dir = Path(skills_dir)

    async def load_all(self) -> list[dict[str, Any]]:
        """加载所有技能

        Returns:
            list[dict]: 技能列表，每个技能包含 name, description, triggers, prompt
        """
        skills = []
        if not self._skills_dir.exists():
            return skills

        for skill_file in self._skills_dir.glob("*.md"):
            skill = await self.load_skill(skill_file)
            if skill:
                skills.append(skill)

        return skills

    async def load_skill(self, skill_file: Path) -> dict[str, Any] | None:
        """加载单个技能文件

        Args:
            skill_file: 技能文件路径

        Returns:
            dict | None: 技能定义，解析失败返回 None
        """
        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
            return self._parse_skill(content, str(skill_file))
        except Exception as e:
            print(f"[SkillLoader] Failed to load skill {skill_file}: {e}")
            return None

    def _parse_skill(self, content: str, source: str = "") -> dict[str, Any]:
        """解析技能文件内容

        支持两种格式：
        1. YAML Frontmatter 格式：
           ---
           name: skill_name
           description: ...
           triggers:
             - trigger1
             - trigger2
           ---
           Prompt content here

        2. 简化格式（注释行作为元数据）：
           # 技能名称
           name: skill_name
           description: ...
           triggers:
             - trigger1
           prompt: |
             Prompt content

        Args:
            content: 文件内容
            source: 文件来源（用于错误提示）

        Returns:
            dict: 技能定义
        """
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)

        if frontmatter_match:
            yaml_content = frontmatter_match.group(1)
            prompt_content = frontmatter_match.group(2).strip()

            metadata = yaml.safe_load(yaml_content)
            if not isinstance(metadata, dict):
                raise ValueError(f"Invalid frontmatter in {source}")

            metadata["prompt"] = prompt_content
            return self._validate_skill(metadata, source)

        lines = content.strip().split("\n")
        metadata = {}
        prompt_lines = []
        in_prompt = False

        for line in lines:
            if line.startswith("prompt:"):
                in_prompt = True
                prompt_indent = len(line) - len(line.lstrip())
                remaining = line[len("prompt:"):].strip()
                if remaining:
                    if remaining.startswith("|"):
                        continue
                    prompt_lines.append(remaining)
                continue

            if in_prompt:
                if line.strip() and not line.startswith(" " * (prompt_indent + 1) if prompt_indent else "  "):
                    if ":" in line and not line.startswith(" "):
                        in_prompt = False
                    else:
                        prompt_lines.append(line)
                else:
                    prompt_lines.append(line)
            else:
                if line.startswith("#"):
                    continue
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()

                    if key == "triggers":
                        metadata[key] = []
                    elif key in metadata and isinstance(metadata.get(key), list):
                        if line.startswith("  - "):
                            metadata[key].append(value.lstrip("- "))
                    else:
                        metadata[key] = value

        if prompt_lines:
            metadata["prompt"] = "\n".join(prompt_lines).strip()

        return self._validate_skill(metadata, source)

    def _validate_skill(self, metadata: dict, source: str) -> dict[str, Any]:
        """验证技能定义

        Args:
            metadata: 技能元数据
            source: 文件来源

        Returns:
            dict: 验证后的技能定义

        Raises:
            ValueError: 缺少必要字段
        """
        required = ["name", "description", "prompt"]
        for field in required:
            if field not in metadata:
                raise ValueError(f"Missing required field '{field}' in {source}")

        if "triggers" not in metadata:
            metadata["triggers"] = []

        if isinstance(metadata["triggers"], str):
            metadata["triggers"] = [metadata["triggers"]]

        metadata["source"] = source
        return metadata