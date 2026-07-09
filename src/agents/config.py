"""CFA-Agent AgentConfig 配置定义

Agent 由纯配置驱动，不再使用枚举角色。
新增 Agent 只需在 agents.yaml 中添加配置，无需修改代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Agent 配置

    定义 Agent 的所有行为参数，替代原来的 AgentRole 枚举 + 角色子类。
    所有字段从 agents.yaml 加载。

    Attributes:
        id: Agent 唯一标识（如 "supervisor", "planner", "executor", "reviewer"）
        name: 显示名称（如 "监督者", "规划者", "执行者", "审查者"）
        system_prompt: 系统提示词
        think_prompt: think 节点提示词模板
        tools: 可用工具列表
        capabilities: 能力声明（用于意图分类器自动匹配路由）
        enable_verify: 是否启用结果验证
        max_steps: 最大 ReAct 步数
        max_verify_retries: 最大验证重试次数
        is_entry_point: 是否系统入口（只有入口 Agent 才需要 call_agent 等调度能力）
        default_timeout: 工具执行默认超时（秒）
    """

    id: str
    name: str
    system_prompt: str
    think_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    enable_verify: bool = False
    max_steps: int = 10
    max_verify_retries: int = 2
    is_entry_point: bool = False
    default_timeout: float = 30.0