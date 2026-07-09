import asyncio
import httpx
import json
import time
import sys

SCENARIOS = [
    {
        "id": 1,
        "name": "A股行情分析",
        "category": "金融数据",
        "query": "今日A股行情分析",
        "expect_tools": ["web_search", "code_executor"],
        "expect_delegate": True,
        "expect_agent": "code_agent",
    },
    {
        "id": 2,
        "name": "数学计算",
        "category": "纯计算",
        "query": "计算 (1+2^10) * sqrt(3) / 5 的结果",
        "expect_tools": ["code_executor"],
        "expect_delegate": True,
        "expect_agent": "executor",
    },
    {
        "id": 3,
        "name": "信息搜索",
        "category": "纯搜索",
        "query": "Python 3.13 有哪些新特性？",
        "expect_tools": ["web_search"],
        "expect_delegate": True,
        "expect_agent": "executor",
    },
    {
        "id": 4,
        "name": "闲聊问候",
        "category": "直接回答",
        "query": "你好，你能做什么？",
        "expect_tools": [],
        "expect_delegate": False,
        "expect_agent": "supervisor",
    },
    {
        "id": 5,
        "name": "实时新闻",
        "category": "搜索+汇总",
        "query": "今天有什么重要新闻？",
        "expect_tools": ["web_search"],
        "expect_delegate": True,
        "expect_agent": "executor",
    },
    {
        "id": 6,
        "name": "代码编写",
        "category": "编程",
        "query": "写一个Python快速排序算法并测试",
        "expect_tools": ["code_executor"],
        "expect_delegate": True,
        "expect_agent": "code_agent",
    },
    {
        "id": 7,
        "name": "投资建议",
        "category": "金融+分析",
        "query": "分析贵州茅台最近走势，给出投资建议",
        "expect_tools": ["web_search", "code_executor"],
        "expect_delegate": True,
        "expect_agent": "code_agent",
    },
    {
        "id": 8,
        "name": "数据查询",
        "category": "数据库",
        "query": "查询数据库中有多少条任务记录",
        "expect_tools": ["db_query"],
        "expect_delegate": True,
        "expect_agent": "executor",
    },
    {
        "id": 9,
        "name": "多步骤规划",
        "category": "复杂任务",
        "query": "帮我制定一个学习CFA一级的3个月计划",
        "expect_tools": ["web_search"],
        "expect_delegate": True,
        "expect_agent": "planner",
    },
    {
        "id": 10,
        "name": "技术指标分析",
        "category": "编码+数据",
        "query": "获取上证指数近30日收盘价，计算5日和20日均线",
        "expect_tools": ["code_executor", "web_search"],
        "expect_delegate": True,
        "expect_agent": "code_agent",
    },
]

URL = "http://localhost:8000/chat/stream"
TIMEOUT = httpx.Timeout(connect=10, read=None, write=10, pool=10)


async def run_scenario(scenario: dict) -> dict:
    payload = {
        "message": scenario["query"],
        "max_steps": 12,
        "temperature": 0.7,
    }

    result = {
        "id": scenario["id"],
        "name": scenario["name"],
        "category": scenario["category"],
        "query": scenario["query"],
        "status": "pending",
        "elapsed_s": 0,
        "event_count": 0,
        "events_by_type": {},
        "agents_seen": set(),
        "tools_used": set(),
        "delegate_count": 0,
        "llm_calls": 0,
        "has_answer": False,
        "answer_preview": "",
        "heartbeats": 0,
        "errors": [],
    }

    start = time.time()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", URL, json=payload) as resp:
                if resp.status_code != 200:
                    result["status"] = f"http_{resp.status_code}"
                    result["errors"].append(f"HTTP {resp.status_code}")
                    return result

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    result["event_count"] += 1
                    etype = event.get("type", "?")
                    agent = event.get("agent", "")

                    result["events_by_type"][etype] = result["events_by_type"].get(etype, 0) + 1

                    if agent:
                        result["agents_seen"].add(agent)

                    if etype == "handoff":
                        result["delegate_count"] += 1
                        fr = event.get("from", "")
                        to = event.get("to", "")
                        if fr:
                            result["agents_seen"].add(fr)
                        if to:
                            result["agents_seen"].add(to)

                    elif etype == "step":
                        tool = event.get("tool_name", "")
                        if tool:
                            result["tools_used"].add(tool)

                    elif etype == "thinking":
                        result["llm_calls"] += 1

                    elif etype == "answer":
                        result["has_answer"] = True
                        result["answer_preview"] = str(event.get("content", ""))[:150]

                    elif etype == "heartbeat":
                        result["heartbeats"] += 1

                    elif etype == "error":
                        result["errors"].append(event.get("error", "unknown")[:100])

    except Exception as e:
        result["status"] = "exception"
        result["errors"].append(str(e)[:100])

    result["elapsed_s"] = round(time.time() - start, 1)
    result["agents_seen"] = sorted(result["agents_seen"])
    result["tools_used"] = sorted(result["tools_used"])

    if result["errors"]:
        result["status"] = "error"
    elif result["has_answer"]:
        result["status"] = "success"
    else:
        result["status"] = "no_answer"

    return result


def score_scenario(scenario: dict, result: dict) -> dict:
    score = {
        "correct_delegate": 0,
        "correct_tools": 0,
        "has_answer": 0,
        "speed_score": 0,
        "total": 0,
        "grade": "F",
    }

    if scenario["expect_delegate"]:
        if result["delegate_count"] > 0:
            score["correct_delegate"] = 25
        if scenario["expect_agent"] in result["agents_seen"]:
            score["correct_delegate"] = 25
    else:
        if result["delegate_count"] == 0:
            score["correct_delegate"] = 25

    expected_tools = set(scenario["expect_tools"])
    actual_tools = set(result["tools_used"])
    if expected_tools:
        overlap = len(expected_tools & actual_tools) / len(expected_tools)
        score["correct_tools"] = round(overlap * 25)
    else:
        score["correct_tools"] = 25 if not actual_tools else 15

    score["has_answer"] = 25 if result["has_answer"] else 0

    if result["elapsed_s"] <= 30:
        score["speed_score"] = 25
    elif result["elapsed_s"] <= 60:
        score["speed_score"] = 20
    elif result["elapsed_s"] <= 90:
        score["speed_score"] = 15
    elif result["elapsed_s"] <= 120:
        score["speed_score"] = 10
    else:
        score["speed_score"] = 5

    score["total"] = score["correct_delegate"] + score["correct_tools"] + score["has_answer"] + score["speed_score"]

    if score["total"] >= 90:
        score["grade"] = "A"
    elif score["total"] >= 75:
        score["grade"] = "B"
    elif score["total"] >= 60:
        score["grade"] = "C"
    elif score["total"] >= 40:
        score["grade"] = "D"
    else:
        score["grade"] = "F"

    return score


async def main():
    print("=" * 90)
    print("  CFA-Agent 10 场景验证评测")
    print("=" * 90)

    results = []
    for i, scenario in enumerate(SCENARIOS):
        print(f"\n{'─' * 90}")
        print(f"  [{scenario['id']}/10] {scenario['name']} ({scenario['category']})")
        print(f"  查询: {scenario['query']}")
        print(f"  期望: 委派={scenario['expect_delegate']}, Agent={scenario['expect_agent']}, 工具={scenario['expect_tools']}")
        print(f"  执行中...", end=" ", flush=True)

        result = await run_scenario(scenario)
        score = score_scenario(scenario, result)
        result["score"] = score

        print(f"完成! {result['elapsed_s']}s [{score['grade']}]")

        print(f"  结果: {result['status']} | 事件={result['event_count']} | LLM调用={result['llm_calls']} | 委派={result['delegate_count']}")
        print(f"  Agent: {result['agents_seen']} | 工具: {result['tools_used']}")
        print(f"  心跳: {result['heartbeats']} | 错误: {result['errors'][:2]}")
        if result["has_answer"]:
            print(f"  回答预览: {result['answer_preview'][:100]}...")
        print(f"  评分: 委派={score['correct_delegate']}/25 工具={score['correct_tools']}/25 回答={score['has_answer']}/25 速度={score['speed_score']}/25 = {score['total']}/100 [{score['grade']}]")

        results.append(result)

    print(f"\n{'=' * 90}")
    print("  综合评测报告")
    print(f"{'=' * 90}")

    total_score = 0
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    total_time = 0
    total_events = 0
    total_llm = 0
    success_count = 0

    print(f"\n  {'#':<3} {'场景':<14} {'类别':<10} {'耗时':>6} {'LLM':>4} {'委派':>4} {'工具':>4} {'Agent':>20} {'评分':>5} {'等级':>4}")
    print(f"  {'─' * 80}")

    for r in results:
        s = r["score"]
        total_score += s["total"]
        grade_counts[s["grade"]] += 1
        total_time += r["elapsed_s"]
        total_events += r["event_count"]
        total_llm += r["llm_calls"]
        if r["has_answer"]:
            success_count += 1

        agents_str = ",".join(r["agents_seen"]) if r["agents_seen"] else "-"
        tools_str = ",".join(r["tools_used"]) if r["tools_used"] else "-"
        print(f"  {r['id']:<3} {r['name']:<14} {r['category']:<10} {r['elapsed_s']:>5.1f}s {r['llm_calls']:>4} {r['delegate_count']:>4} {tools_str:>4} {agents_str:>20} {s['total']:>5} {s['grade']:>4}")

    avg_score = total_score / len(results)
    avg_time = total_time / len(results)

    print(f"\n  {'─' * 80}")
    print(f"  平均得分: {avg_score:.1f}/100 | 平均耗时: {avg_time:.1f}s | 成功率: {success_count}/{len(results)}")
    print(f"  等级分布: A={grade_counts['A']} B={grade_counts['B']} C={grade_counts['C']} D={grade_counts['D']} F={grade_counts['F']}")
    print(f"  总事件数: {total_events} | 总LLM调用: {total_llm} | 总耗时: {total_time:.1f}s")

    if avg_score >= 80:
        verdict = "✅ 优秀 — 系统整体表现良好"
    elif avg_score >= 65:
        verdict = "⚠️  良好 — 部分场景需优化"
    elif avg_score >= 50:
        verdict = "⚠️  一般 — 多个场景需改进"
    else:
        verdict = "❌ 不及格 — 系统存在严重问题"

    print(f"\n  综合评定: {verdict}")

    slowest = sorted(results, key=lambda r: r["elapsed_s"], reverse=True)[:3]
    print(f"\n  最慢 3 个场景:")
    for r in slowest:
        print(f"    - {r['name']}: {r['elapsed_s']}s (LLM={r['llm_calls']}, 委派={r['delegate_count']})")

    failed = [r for r in results if r["status"] != "success"]
    if failed:
        print(f"\n  失败场景:")
        for r in failed:
            print(f"    - {r['name']}: {r['status']} | 错误: {r['errors'][:2]}")

    print(f"\n{'=' * 90}")


asyncio.run(main())