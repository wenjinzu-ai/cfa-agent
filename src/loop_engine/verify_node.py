"""CFA-Agent 验证节点

verify 节点：在 Agent 准备输出答案前，验证结果是否满足原始任务要求。
这是自修正闭环的核心，任何 Agent 都可以配置启用验证。

验证时机：
- 由 AgentConfig.enable_verify 配置控制
- enable_verify = true → 执行验证
- enable_verify = false → 直接跳过验证，标记为通过

验证流程：
- 对比原始任务和当前结果
- 检查完整性、正确性、格式
- 不通过 → 返回具体修正建议 → 回到 think 节点重新处理
- 通过 → 进入 answer 节点输出结果
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.loop_engine.state import ReActState, VerifyResult

logger = logging.getLogger("cfa-agent.loop_engine.verify")


class VerifyNode:
    """验证节点

    职责：
    - 根据配置决定是否执行验证：enable_verify=true 才执行，否则跳过
    - 验证不通过时给出具体修正建议，由 think 节点重新处理
    - 验证维度：完整性、正确性、格式、质量

    Attributes:
        router: LLM 路由器
        enable_verify: 是否启用验证
        max_verify_retries: 最大验证重试次数
    """

    def __init__(
        self,
        router: Any,
        enable_verify: bool = False,
        max_verify_retries: int = 2,
    ):
        self._router = router
        self._enable_verify = enable_verify
        self._max_verify_retries = max_verify_retries

    async def execute(self, state: ReActState) -> dict:
        task = state.get("task", "")
        result = state.get("final_answer", "")
        verify_count = state.get("verify_count", 0)
        verify_history = list(state.get("verify_history", []))

        logger.info(
            "verify node: enable_verify=%s, verify_count=%d/%d, result_len=%d",
            self._enable_verify, verify_count, self._max_verify_retries, len(result),
        )

        if not self._enable_verify:
            return {
                **state,
                "verify_result": {
                    "passed": True,
                    "reason": "验证未启用，跳过验证",
                    "suggestions": [],
                },
            }

        if verify_count >= self._max_verify_retries:
            return {
                **state,
                "verify_result": {
                    "passed": True,
                    "reason": f"已达最大验证重试次数({self._max_verify_retries})，强制通过",
                    "suggestions": [],
                },
            }

        if not result or not task:
            return {
                **state,
                "verify_result": {
                    "passed": True,
                    "reason": "结果或任务为空，直接通过",
                    "suggestions": [],
                },
            }

        verify_data = await self._verify(task, result, verify_history)
        passed = verify_data.get("passed", True)
        reason = verify_data.get("reason", "LLM 验证完成")
        suggestions = verify_data.get("suggestions", [])

        new_verify_history = verify_history + [
            {
                "attempt": verify_count + 1,
                "passed": passed,
                "reason": reason,
                "suggestions": suggestions,
            }
        ]

        if passed:
            logger.info("verify passed: %s", reason)
            return {
                **state,
                "verify_result": {
                    "passed": passed,
                    "reason": reason,
                    "suggestions": suggestions,
                },
                "verify_history": new_verify_history,
                "verify_count": verify_count + 1,
            }
        else:
            logger.warning(
                "verify failed (attempt %d/%d): %s",
                verify_count + 1, self._max_verify_retries, reason,
            )
            if suggestions:
                logger.info("verify suggestions: %s", suggestions)

            suggestion_text = "\n".join(f"- {s}" for s in suggestions)
            feedback = (
                f"[验证不通过 ({verify_count + 1}/{self._max_verify_retries})]\n"
                f"原始任务: {task}\n"
                f"当前结果: {result[:500]}...\n"
                f"问题: {reason}\n"
                f"修正建议:\n{suggestion_text}\n"
                f"请在下一轮中按修正建议重新处理任务。"
            )

            return {
                **state,
                "verify_result": {
                    "passed": False,
                    "reason": reason,
                    "suggestions": suggestions,
                },
                "verify_history": new_verify_history,
                "verify_count": verify_count + 1,
                "last_observation": feedback,
                "action_type": "think",
                "final_answer": "",
            }

    async def _verify(
        self, task: str, result: str, history: list[dict]
    ) -> dict[str, Any]:
        history_text = ""
        if history:
            history_lines = [
                f"第{i+1}次验证: {'通过' if h['passed'] else '不通过'} - {h['reason']}"
                for i, h in enumerate(history)
            ]
            history_text = "前次验证记录:\n" + "\n".join(history_lines) + "\n\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个严格的结果验证器。请对比原始任务和当前结果，判断是否满足要求。\n\n"
                    "验证维度：\n"
                    "1. 完整性：结果是否覆盖任务的所有要求？\n"
                    "2. 正确性：结果内容是否正确？\n"
                    "3. 格式：结果格式是否合适？\n"
                    "4. 质量：是否有遗漏、错误或歧义？\n"
                    "5. 事实性：如果用户问的是可验证的事实性问题（价格、数据、时间、地点等），"
                    "结果中必须包含具体的数值或事实，不能只有'无法提供''建议自行查询'等拒绝式回答。"
                    "但对于开放性、主观性、哲学性问题（如'生命的意义'），允许给出分析性回答，不要求具体数值。"
                    "拒绝式回答仅在对可验证的事实性问题时判定为不通过。\n\n"
                    "返回 JSON 格式：\n"
                    '{"passed": true/false, "reason": "简洁说明通过或不通过的原因", "suggestions": ["具体修正建议1", "建议2"]}\n\n'
                    "重要：如果 passed 为 false，suggestions 必须给出具体可操作的修正建议，"
                    "让执行者能根据建议修复问题。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{history_text}"
                    f"原始任务:\n{task}\n\n"
                    f"当前结果:\n{result}\n\n"
                    f"请验证并返回 JSON。"
                ),
            },
        ]

        try:
            response = await self._router.route_verify(messages=messages)
            content = response.get("content", "")

            if isinstance(content, str):
                content = self._parse_json(content)

            if isinstance(content, dict):
                return {
                    "passed": content.get("passed", True),
                    "reason": content.get("reason", "验证结果解析成功"),
                    "suggestions": content.get("suggestions", []),
                }

            return {
                "passed": True,
                "reason": "验证 LLM 返回了非 JSON 格式，默认通过",
                "suggestions": [],
            }

        except Exception as e:
            logger.error("verify LLM call failed: %s", e)
            return {
                "passed": True,
                "reason": f"验证 LLM 调用失败({e})，默认通过以避免阻塞",
                "suggestions": [],
            }

    @staticmethod
    def _parse_json(content: str) -> dict | str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 2:
                content = "\n".join(lines[1:-1])
            else:
                content = content.replace("```", "").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content