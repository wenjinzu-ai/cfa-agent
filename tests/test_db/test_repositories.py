"""Repository 层测试"""
from __future__ import annotations

import pytest

from src.common.types import (
    AgentStatus,
    TaskStatus,
    MemoryType,
    EventType,
    ToolSource,
)


class TestAgentRepository:
    """智能体 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_agent(self, agent_repo):
        """测试创建智能体"""
        agent = await agent_repo.create(
            agent_id="test-agent-1",
            name="Test Agent",
            role="executor",
        )
        assert agent is not None
        assert agent["id"] == "test-agent-1"
        assert agent["name"] == "Test Agent"
        assert agent["role"] == "executor"
        assert agent["status"] == "idle"

    @pytest.mark.asyncio
    async def test_get_by_id(self, agent_repo):
        """测试根据 ID 获取智能体"""
        await agent_repo.create(
            agent_id="test-agent-2",
            name="Test Agent 2",
            role="planner",
        )
        agent = await agent_repo.get_by_id("test-agent-2")
        assert agent is not None
        assert agent["name"] == "Test Agent 2"

    @pytest.mark.asyncio
    async def test_get_by_role(self, agent_repo):
        """测试按角色获取智能体"""
        await agent_repo.create(
            agent_id="planner-1",
            name="Planner 1",
            role="planner",
        )
        agents = await agent_repo.get_by_role("planner")
        assert len(agents) >= 1
        assert all(a["role"] == "planner" for a in agents)

    @pytest.mark.asyncio
    async def test_update_status(self, agent_repo):
        """测试更新智能体状态"""
        await agent_repo.create(
            agent_id="test-agent-3",
            name="Test Agent 3",
            role="executor",
        )
        await agent_repo.update_status("test-agent-3", AgentStatus.BUSY)
        agent = await agent_repo.get_by_id("test-agent-3")
        assert agent["status"] == "busy"

    @pytest.mark.asyncio
    async def test_bind_tool(self, agent_repo):
        """测试工具绑定"""
        await agent_repo.create(
            agent_id="test-agent-4",
            name="Test Agent 4",
            role="executor",
        )
        await agent_repo.bind_tool(
            agent_id="test-agent-4",
            tool_name="web_search",
            tool_source=ToolSource.BUILTIN,
            proficiency=0.8,
        )
        tools = await agent_repo.get_agent_tools("test-agent-4")
        assert len(tools) == 1
        assert tools[0]["tool_name"] == "web_search"

    @pytest.mark.asyncio
    async def test_get_idle_agent_by_role(self, agent_repo):
        """测试获取空闲智能体"""
        await agent_repo.create(
            agent_id="idle-executor-1",
            name="Idle Executor",
            role="executor",
        )
        agent = await agent_repo.get_idle_agent_by_role("executor")
        assert agent is not None
        assert agent["status"] == "idle"


class TestTaskRepository:
    """任务 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_task(self, task_repo):
        """测试创建任务"""
        task = await task_repo.create(
            task_id="test-task-1",
            description="Test task description",
        )
        assert task is not None
        assert task["id"] == "test-task-1"
        assert task["description"] == "Test task description"
        assert task["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_status(self, task_repo):
        """测试更新任务状态"""
        await task_repo.create(
            task_id="test-task-2",
            description="Test task 2",
        )
        await task_repo.update_status("test-task-2", TaskStatus.RUNNING)
        task = await task_repo.get_by_id("test-task-2")
        assert task["status"] == "running"

    @pytest.mark.asyncio
    async def test_assign_agent(self, task_repo, agent_repo):
        """测试分配智能体"""
        await agent_repo.create(
            agent_id="agent-for-assign",
            name="Assign Agent",
            role="executor",
        )
        await task_repo.create(
            task_id="test-task-3",
            description="Test task 3",
        )
        await task_repo.assign_agent("test-task-3", "agent-for-assign")
        task = await task_repo.get_by_id("test-task-3")
        assert task["assigned_agent_id"] == "agent-for-assign"
        assert task["status"] == "assigned"

    @pytest.mark.asyncio
    async def test_increment_iteration(self, task_repo):
        """测试增加迭代次数"""
        await task_repo.create(
            task_id="test-task-4",
            description="Test task 4",
        )
        count = await task_repo.increment_iteration("test-task-4")
        assert count == 1
        count = await task_repo.increment_iteration("test-task-4")
        assert count == 2


class TestSessionRepository:
    """会话 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_session(self, session_repo):
        """测试创建会话"""
        session = await session_repo.create(session_id="session-1")
        assert session is not None
        assert session["id"] == "session-1"
        assert session["status"] == "active"

    @pytest.mark.asyncio
    async def test_append_history(self, session_repo):
        """测试追加对话历史"""
        await session_repo.create(session_id="session-2")
        await session_repo.append_history(
            "session-2",
            {"role": "user", "content": "Hello"},
        )
        session = await session_repo.get_by_id("session-2")
        history = session["session_history"]
        assert len(history) == 1
        assert history[0]["content"] == "Hello"


class TestToolRepository:
    """工具 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_tool(self, tool_repo):
        """测试注册工具"""
        tool = await tool_repo.create(name="web_search", version="1.0.0")
        assert tool is not None
        assert tool["name"] == "web_search"
        assert tool["status"] == "active"

    @pytest.mark.asyncio
    async def test_log_execution(self, tool_repo):
        """测试记录工具执行日志"""
        await tool_repo.create(name="test_tool")
        await tool_repo.log_execution(
            tool_name="test_tool",
            status="success",
            duration_ms=100,
        )
        history = await tool_repo.get_execution_history("test_tool")
        assert len(history) == 1
        assert history[0]["status"] == "success"


class TestMemoryRepository:
    """记忆 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_memory(self, memory_repo):
        """测试创建记忆"""
        memory = await memory_repo.create(
            content="Test memory content",
            memory_type=MemoryType.EPISODIC,
            importance=0.8,
        )
        assert memory is not None
        assert memory["content"] == "Test memory content"
        assert memory["memory_type"] == "episodic"

    @pytest.mark.asyncio
    async def test_fts_search(self, memory_repo):
        """测试 FTS5 全文搜索"""
        await memory_repo.create(
            content="Python is a programming language",
            memory_type=MemoryType.SEMANTIC,
        )
        await memory_repo.create(
            content="JavaScript is also a programming language",
            memory_type=MemoryType.SEMANTIC,
        )
        results = await memory_repo.search_fts("Python")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_create_react_step(self, memory_repo, task_repo):
        """测试创建 ReAct 步骤"""
        await task_repo.create(
            task_id="test-task-for-step",
            description="Test task for react step",
        )
        step = await memory_repo.create_react_step(
            task_id="test-task-for-step",
            step_index=0,
            status="success",
            thought="I need to search for information",
        )
        assert step is not None
        assert step["task_id"] == "test-task-for-step"
        assert step["step_index"] == 0


class TestEventRepository:
    """事件 Repository 测试"""

    @pytest.mark.asyncio
    async def test_create_event(self, event_repo):
        """测试创建事件"""
        await event_repo.create_event(
            event_type=EventType.HEARTBEAT,
            agent_id="agent-1",
            payload={"status": "alive"},
        )
        events = await event_repo.get_events_by_agent("agent-1")
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_create_audit_log(self, event_repo):
        """测试创建审计日志"""
        await event_repo.create_audit_log(
            action="tool_call",
            agent_id="agent-1",
            details={"tool": "web_search"},
        )
        logs = await event_repo.get_audit_logs(agent_id="agent-1")
        assert len(logs) >= 1