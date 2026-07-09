"""CFA-Agent Supervisor 委派工具

delegate 工具：让 Supervisor（监督者）可以委派任务给其他智能体执行。
这是 Supervisor 模式的核心：简单任务直接回答，复杂任务委派给专家。

支持两种模式：
- execute(): 同步执行，返回最终结果（兼容旧接口）
- astream_execute(): 流式执行，逐步推送子智能体事件

审查者结果程序化解析：
- 当委派目标是 reviewer 时，自动解析其输出中的 verdict
- 如果 verdict 为 reject/revise，在返回结果中标记 needs_retry=true
- Supervisor 的 think_prompt 据此强制重新委派，避免忽略审查意见
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator, Optional, TYPE_CHECKING

from pydantic import PrivateAttr

from src.agents.service import get_agent_service
from src.tools.base import BaseTool

if TYPE_CHECKING:
    from src.llm.router import LLMRouter
    from src.llm.token_counter import TokenCounter

logger = logging.getLogger("cfa-agent.tools.delegate")


class Delegate(BaseTool):
    """委派智能体工具

    Supervisor 调用此工具将子任务委派给其他智能体（规划者/执行者/审查者）。
    每个调用会启动目标智能体的 ReAct 循环，完成后再将结果返回给 Supervisor。
    """

    name: str = "delegate"
    description: str = (
        "委派子任务给专家智能体并获取结果。"
        "当你需要调度专家能力时使用此工具。"
        "参数 role 是目标 Agent ID，如: planner, executor, reviewer"
    )
    max_steps: int = 10

    _router: Any = PrivateAttr(default=None)
    _token_counter: Any = PrivateAttr(default=None)
    _skill_registry: Any = PrivateAttr(default=None)
    _agent_service: Any = PrivateAttr(default=None)

    def init_runtime_deps(
        self,
        router: "LLMRouter",
        token_counter: "TokenCounter",
        skill_registry: Any = None,
        agent_service: Any = None,
    ) -> None:
        self._router = router
        self._token_counter = token_counter
        self._skill_registry = skill_registry
        self._agent_service = agent_service

    @staticmethod
    def _parse_reviewer_verdict(result: str) -> Optional[dict]:
        """解析审查者的评审结果

        Reviewer 的输出可能包含 JSON 格式的 verdict，需要从文本中提取。
        支持以下格式：
        - 纯 JSON 对象
        - ```json ... ``` 代码块
        - 内联 JSON 对象

        Args:
            result: Reviewer 的最终输出文本

        Returns:
            解析后的 verdict 字典，或 None（无法解析时）
        """
        if not result:
            return None

        def _try_parse(text: str) -> Optional[dict]:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "verdict" in data:
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
            return None

        parsed = _try_parse(result.strip())
        if parsed:
            return parsed

        code_blocks = re.findall(r'```(?:json)?\s*(.*?)```', result, re.DOTALL)
        for block in code_blocks:
            parsed = _try_parse(block.strip())
            if parsed:
                return parsed

        inline_match = re.search(r'\{[^{}]*"verdict"[^{}]*\}', result)
        if inline_match:
            parsed = _try_parse(inline_match.group(0))
            if parsed:
                return parsed

        return None

    def _enrich_reviewer_result(self, agent_id: str, result: str, return_data: dict) -> dict:
        """为审查者结果添加程序化标记

        当委派目标是 reviewer 时，解析其 verdict 并添加 needs_retry 标记，
        使 Supervisor 的 think_prompt 能据此强制重新委派。

        Args:
            agent_id: 目标 Agent ID
            result: Agent 的最终输出
            return_data: 待返回的结果字典

        Returns:
            增强后的结果字典
        """
        if agent_id != "reviewer":
            return return_data

        verdict_data = self._parse_reviewer_verdict(result)
        if not verdict_data:
            return return_data

        verdict = verdict_data.get("verdict", "")
        if verdict in ("reject", "revise"):
            return_data["needs_retry"] = True
            return_data["verdict"] = verdict
            return_data["retry_suggestions"] = verdict_data.get("suggestions", [])
            return_data["retry_issues"] = verdict_data.get("issues", [])
            return_data["score"] = verdict_data.get("score", 0.0)
            logger.info(
                "Reviewer verdict=%s, score=%s, needs_retry=true",
                verdict, verdict_data.get("score"),
            )
        elif verdict == "approve":
            return_data["needs_retry"] = False
            return_data["verdict"] = "approve"
            return_data["score"] = verdict_data.get("score", 1.0)

        return return_data

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "要委派的目标 Agent ID（如: planner, executor, reviewer）",
                },
                "task": {
                    "type": "string",
                    "description": "委派给专家的任务描述",
                },
            },
            "required": ["role", "task"],
        }

    async def execute(self, **kwargs) -> dict[str, Any]:
        agent_id = kwargs.get("role", "") or kwargs.get("agent_id", "")
        task = kwargs.get("task", "")

        from src.loop_engine.graph import ReActGraph
        from src.tools.registry import get_tool_registry

        agent_service = get_agent_service()
        agent_config = agent_service.get(agent_id)
        if agent_config is None:
            available = ", ".join(agent_service.list_ids())
            return {
                "agent_id": agent_id,
                "status": "error",
                "error": f"Agent 不存在: {agent_id}，可用: {available}",
            }

        graph = ReActGraph.create(
            router=self._router,
            tool_registry=get_tool_registry(),
            token_counter=self._token_counter,
            agent_config=agent_config,
            skill_registry=self._skill_registry,
            agent_service=self._agent_service,
        )

        logger.info(f"Supervisor 委派 {agent_config.name}({agent_id}): {task[:100]}")

        state = await graph.run(task=task, max_steps=agent_config.max_steps)

        result = state.get("final_answer", "")
        steps = state.get("step_count", 0)

        logger.info(f"{agent_config.name} 完成，{steps} 步")

        return_data = {
            "agent_id": agent_id,
            "agent_name": agent_config.name,
            "status": "success",
            "result": result,
            "steps": steps,
        }

        return self._enrich_reviewer_result(agent_id, result, return_data)

    async def astream_execute(self, **kwargs) -> AsyncGenerator[dict, None]:
        """流式委派：逐步推送子智能体执行事件

        与 execute() 不同，此方法使用 astream_run() 实时推送子智能体的
        思考、工具调用、观察等事件，前端可实时展示子智能体进度。

        Args:
            **kwargs: role (Agent ID) 和 task (任务描述)

        Yields:
            dict: 子智能体的实时事件（带 agent 标识）
        """
        agent_id = kwargs.get("role", "") or kwargs.get("agent_id", "")
        task = kwargs.get("task", "")

        from src.loop_engine.graph import ReActGraph
        from src.tools.registry import get_tool_registry

        agent_service = get_agent_service()
        agent_config = agent_service.get(agent_id)
        if agent_config is None:
            available = ", ".join(agent_service.list_ids())
            yield {
                "type": "error",
                "node": "delegate",
                "agent": agent_id,
                "content": f"Agent 不存在: {agent_id}，可用: {available}",
            }
            return

        yield {
            "type": "handoff",
            "node": "delegate",
            "agent": agent_id,
            "content": f"委派给 {agent_config.name}",
        }

        graph = ReActGraph.create(
            router=self._router,
            tool_registry=get_tool_registry(),
            token_counter=self._token_counter,
            agent_config=agent_config,
            skill_registry=self._skill_registry,
            agent_service=self._agent_service,
        )

        logger.info(f"Supervisor 流式委派 {agent_config.name}({agent_id}): {task[:100]}")

        final_result = ""

        async for event in graph.astream_run(task=task, max_steps=agent_config.max_steps):
            if not isinstance(event, dict):
                continue
            event_dict = {k: v for k, v in event.items() if v is not None}

            if event_dict.get("type") == "answer":
                final_result = event_dict.get("content", "")

            if not event_dict.get("agent"):
                event_dict["agent"] = agent_id
            yield event_dict

        if agent_id == "reviewer" and final_result:
            verdict_data = self._parse_reviewer_verdict(final_result)
            if verdict_data:
                verdict = verdict_data.get("verdict", "")
                review_event = {
                    "type": "review_verdict",
                    "node": "delegate",
                    "agent": agent_id,
                    "verdict": verdict,
                    "score": verdict_data.get("score"),
                    "needs_retry": verdict in ("reject", "revise"),
                }
                if verdict in ("reject", "revise"):
                    review_event["retry_suggestions"] = verdict_data.get("suggestions", [])
                    review_event["retry_issues"] = verdict_data.get("issues", [])
                yield review_event

        logger.info(f"{agent_config.name} 流式委派完成")