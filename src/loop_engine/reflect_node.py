"""CFA-Agent 反思节点

reflect 节点：方向评估与修正建议

技术方案 §7.5.4：
触发时机：
- think 节点主动判断需要反思
- 连续 N 步未取得有效进展
- 工具连续返回空结果或错误
- 检测到偏离原始任务目标

反思内容：
- 当前方向是否正确？
- 是否遗漏了关键信息？
- 是否有更高效的替代方案？
- 是否需要委派给其他智能体？

输出格式（ReflectResult）：
{
    "should_continue": true,
    "direction_correct": true,
    "issues_found": [...],
    "suggestions": [...],
    "need_delegation": false,
    "delegation_target": null
}
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from src.llm.router import LLMRouter
from src.loop_engine.state import ReActState, ReflectResult

logger = logging.getLogger("cfa-agent.loop_engine.reflect")


class ReflectNode:
    """反思节点

    职责：
    - 评估当前执行方向是否正确
    - 检测偏差并生成修正建议
    - 决定是否需要自我修正或告警
    - 防止连续反思导致死循环

    Attributes:
        _router: LLM 路由器（使用推理层模型）
        _max_reflect_count: 最大连续反思次数
    """

    def __init__(
        self,
        router: LLMRouter,
        max_reflect_count: int = 2,
    ):
        self._router = router
        self._max_reflect_count = max_reflect_count

    async def execute(self, state: ReActState) -> dict:
        """执行反思

        Args:
            state: 当前状态

        Returns:
            dict: 状态更新（包含反思结论和修正建议）
        """
        reflect_count = state.get("consecutive_reflect_count", 0)

        if reflect_count >= self._max_reflect_count:
            logger.warning(f"Max reflect count ({self._max_reflect_count}) reached, forcing answer")
            return {
                "action_type": "answer",
                "current_thought": "已达到最大反思次数，基于已有信息输出答案",
                "is_alerting": True,
            }

        logger.info(f"Reflect node executing, consecutive count: {reflect_count + 1}")

        messages = self._build_messages(state)

        try:
            response = await self._router.route_reflect(messages=messages)
        except Exception as e:
            logger.error(f"LLM call failed in reflect node: {e}")
            return {
                "action_type": "answer",
                "current_thought": f"反思失败，直接输出答案",
                "final_answer": "抱歉，在反思过程中遇到错误。",
                "is_alerting": True,
            }

        return self._process_response(response, state)

    def _build_messages(self, state: ReActState) -> list[dict]:
        """构建反思消息列表

        Args:
            state: 当前状态

        Returns:
            list[dict]: 消息列表
        """
        task = state["task"]
        history_text = self._format_history(state["history"])
        step_count = state["step_count"]
        max_steps = state["max_steps"]
        failures = state.get("consecutive_failures", 0)

        prompt = (
            "You are in the REFLECT phase of a ReAct loop.\n"
            "Evaluate your progress and decide what to do next.\n\n"
            f"Original task:\n{task}\n\n"
            f"Progress so far ({step_count}/{max_steps} steps):\n{history_text}\n\n"
            f"Consecutive failures: {failures}\n\n"
            "Analyze:\n"
            "1. Are you moving in the right direction?\n"
            "2. Have you made any errors or assumptions that need correction?\n"
            "3. Should you continue, change approach, or escalate?\n\n"
            "Respond in JSON format with these fields:\n"
            "- should_continue: boolean (should we keep trying?)\n"
            "- direction_correct: boolean (are we on the right track?)\n"
            "- issues_found: list of strings (what problems do you see?)\n"
            "- suggestions: list of strings (what should we change?)\n"
            "- need_delegation: boolean (should another agent handle this?)\n"
            "- delegation_target: string or null (which agent type would be better?)\n\n"
            "Be specific and actionable in your suggestions."
        )

        messages = [
            {"role": "system", "content": "You are an AI assistant analyzing your own reasoning process."},
            {"role": "user", "content": prompt},
        ]

        return messages

    def _process_response(self, response: dict, state: ReActState) -> dict:
        """处理 LLM 响应

        Args:
            response: LLM 响应
            state: 当前状态

        Returns:
            dict: 状态更新
        """
        content = response.get("content", "")

        try:
            reflect_result = self._parse_reflect_content(content)
        except Exception as e:
            logger.warning(f"Failed to parse reflect result: {e}, using default")
            reflect_result = ReflectResult(
                should_continue=True,
                direction_correct=True,
                issues_found=["无法解析反思结果"],
                suggestions=["继续尝试其他方法"],
                need_delegation=False,
                delegation_target=None,
            )

        if not reflect_result.get("should_continue", True):
            return {
                "action_type": "answer",
                "current_thought": "反思后决定停止，输出最终答案",
                "reflect_result": reflect_result,
            }

        if reflect_result.get("need_delegation", False):
            return {
                "escalate": True,
                "action_type": "answer",
                "current_thought": "反思后决定升级委派",
                "reflect_result": reflect_result,
                "is_alerting": True,
            }

        return {
            "consecutive_reflect_count": state.get("consecutive_reflect_count", 0) + 1,
            "reflect_result": reflect_result,
            "action_type": None,
            "current_thought": f"反思完成，建议: {', '.join(reflect_result.get('suggestions', [])[:2])}",
        }

    @staticmethod
    def _format_history(history: list) -> str:
        """格式化历史步骤"""
        if not history:
            return "(无历史步骤)"
        parts = []
        for i, step in enumerate(history[-5:]):
            thought = step.get("thought", "")
            action = step.get("action", "")
            obs = step.get("observation", "")
            parts.append(f"Step {i + 1}:")
            if thought:
                parts.append(f"  Thought: {thought[:200]}")
            if action:
                parts.append(f"  Action: {json.dumps(action, ensure_ascii=False)[:150]}")
            if obs:
                parts.append(f"  Observation: {obs[:200]}")
        return "\n".join(parts)

    @staticmethod
    def _parse_reflect_content(content: str) -> ReflectResult:
        """解析 LLM 返回的反思内容

        Args:
            content: LLM 返回的文本内容

        Returns:
            ReflectResult: 结构化的反思结果
        """
        json_match = None
        for pattern in [r'\{[^{}]*\}', r'```json\s*(.*?)\s*```']:
            import re
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                json_match = matches[0] if isinstance(matches[0], str) else matches[0]
                break

        if json_match:
            data = json.loads(json_match)
            return ReflectResult(
                should_continue=data.get("should_continue", True),
                direction_correct=data.get("direction_correct", True),
                issues_found=data.get("issues_found", []),
                suggestions=data.get("suggestions", []),
                need_delegation=data.get("need_delegation", False),
                delegation_target=data.get("delegation_target"),
            )

        return ReflectResult(
            should_continue=True,
            direction_correct=True,
            issues_found=[content[:500]],
            suggestions=[content[:300] if len(content) > 100 else content],
            need_delegation=False,
            delegation_target=None,
        )