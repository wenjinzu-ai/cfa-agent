"""CFA-Agent 技能注册表

关键词匹配 + 触发机制
"""
from __future__ import annotations

from typing import Any

from src.skills.loader import SkillLoader


class SkillRegistry:
    """技能注册表

    职责：
    - 管理技能的注册与查询
    - 基于关键词匹配触发技能
    - 技能 = 提示词模板（非可执行代码）
    """

    def __init__(self):
        self._skills: dict[str, dict[str, Any]] = {}
        self._trigger_index: dict[str, set[str]] = {}

    def register(self, skill: dict[str, Any]) -> None:
        """注册技能

        Args:
            skill: 技能定义，包含 name, description, triggers, prompt
        """
        name = skill.get("name")
        if not name:
            raise ValueError("Skill must have a 'name' field")

        self._skills[name] = skill

        triggers = skill.get("triggers", [])
        for trigger in triggers:
            trigger_lower = trigger.lower()
            if trigger_lower not in self._trigger_index:
                self._trigger_index[trigger_lower] = set()
            self._trigger_index[trigger_lower].add(name)

    def unregister(self, name: str) -> None:
        """注销技能

        Args:
            name: 技能名称
        """
        if name not in self._skills:
            return

        skill = self._skills[name]
        for trigger in skill.get("triggers", []):
            trigger_lower = trigger.lower()
            if trigger_lower in self._trigger_index:
                self._trigger_index[trigger_lower].discard(name)
                if not self._trigger_index[trigger_lower]:
                    del self._trigger_index[trigger_lower]

        del self._skills[name]

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """搜索匹配的技能

        搜索策略：
        1. 精确触发词匹配
        2. 名称/描述模糊匹配
        3. 按匹配分数排序

        Args:
            query: 搜索查询
            top_k: 返回最多 top_k 个技能

        Returns:
            list[dict]: 匹配的技能列表
        """
        query_lower = query.lower()
        scores: dict[str, float] = {}

        for trigger, skill_names in self._trigger_index.items():
            if trigger in query_lower:
                for skill_name in skill_names:
                    scores[skill_name] = scores.get(skill_name, 0) + 1.0

        for name, skill in self._skills.items():
            if name.lower() in query_lower:
                scores[name] = scores.get(name, 0) + 0.8

            desc_lower = skill.get("description", "").lower()
            if desc_lower and any(word in query_lower for word in desc_lower.split()):
                scores[name] = scores.get(name, 0) + 0.5

        sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self._skills[name] for name, _ in sorted_skills[:top_k] if name in self._skills]

    def get(self, skill_name: str) -> dict[str, Any] | None:
        """获取技能

        Args:
            skill_name: 技能名称

        Returns:
            dict | None: 技能定义，不存在返回 None
        """
        return self._skills.get(skill_name)

    def list_all(self) -> list[dict[str, Any]]:
        """获取所有技能

        Returns:
            list[dict]: 所有技能列表
        """
        return list(self._skills.values())

    def get_triggered_skills(self, query: str) -> list[dict[str, Any]]:
        """获取被触发的技能

        匹配策略（按优先级）：
        1. 精确触发词子串匹配
        2. 触发词与查询的字符级重叠匹配（适配中文无空格分词）
        3. 描述关键词匹配

        Args:
            query: 用户查询

        Returns:
            list[dict]: 被触发的技能列表
        """
        query_lower = query.lower()
        triggered: dict[str, float] = {}

        for trigger, skill_names in self._trigger_index.items():
            if trigger in query_lower:
                for name in skill_names:
                    triggered[name] = max(triggered.get(name, 0), 1.0)
                continue

            trigger_lower = trigger.lower()
            overlap = self._char_overlap(trigger_lower, query_lower)
            if overlap > 0.4:
                for name in skill_names:
                    triggered[name] = max(triggered.get(name, 0), overlap)

        for name, skill in self._skills.items():
            if name in triggered:
                continue
            desc = skill.get("description", "").lower()
            overlap = self._char_overlap(desc, query_lower)
            if overlap > 0.25:
                triggered[name] = max(triggered.get(name, 0), overlap * 0.8)

        return [self._skills[name] for name, _ in sorted(triggered.items(), key=lambda x: x[1], reverse=True) if name in self._skills]

    @staticmethod
    def _char_overlap(text: str, query: str) -> float:
        """计算文本与查询的字符级重叠度

        使用 bigram 匹配，适配中文无空格分词场景

        Args:
            text: 被匹配文本
            query: 查询文本

        Returns:
            float: 0.0 ~ 1.0 重叠度
        """
        def bigrams(s: str) -> set[str]:
            return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}

        t_bigrams = bigrams(text)
        q_bigrams = bigrams(query)
        if not t_bigrams:
            return 0.0
        return len(t_bigrams & q_bigrams) / len(t_bigrams)

    def get_skill_prompt(self, skill_name: str) -> str | None:
        """获取技能的提示词

        Args:
            skill_name: 技能名称

        Returns:
            str | None: 提示词模板
        """
        skill = self.get(skill_name)
        if skill:
            return skill.get("prompt")
        return None

    @property
    def size(self) -> int:
        """已注册技能数量"""
        return len(self._skills)


_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表（单例模式）"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


async def load_skills_from_directory(skills_dir: str = "config/skills") -> int:
    """从目录加载所有技能到全局注册表

    Args:
        skills_dir: 技能目录路径

    Returns:
        int: 加载的技能数量
    """
    loader = SkillLoader(skills_dir)
    skills = await loader.load_all()

    registry = get_skill_registry()
    for skill in skills:
        registry.register(skill)

    return len(skills)