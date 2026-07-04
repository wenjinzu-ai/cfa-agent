import pytest
from pydantic import ValidationError
from src.models.message import (
    Role,
    ChatMessage,
    EventType,
    EventCategory,
    StreamEvent,
    ChatRequest,
    ChatResponse,
)


class TestRole:
    def test_role_values(self):
        assert Role.USER == "user"
        assert Role.ASSISTANT == "assistant"
        assert Role.SYSTEM == "system"
        assert Role.TOOL == "tool"


class TestChatMessage:
    def test_create_message(self):
        msg = ChatMessage(role=Role.USER, content="Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        msg = ChatMessage(role=Role.ASSISTANT, content="Hi", metadata={"token_count": 5})
        assert msg.metadata["token_count"] == 5


class TestEventType:
    def test_event_type_values(self):
        assert EventType.THOUGHT == "thought"
        assert EventType.ACTION == "action"
        assert EventType.OBSERVATION == "observation"
        assert EventType.RESULT == "result"
        assert EventType.PLAN_UPDATE == "plan_update"
        assert EventType.ERROR == "error"


class TestEventCategory:
    def test_event_category_values(self):
        assert EventCategory.DECISION == "decision"
        assert EventCategory.TOOL_CALL == "tool_call"
        assert EventCategory.GUARDRAIL == "guardrail"


class TestStreamEvent:
    def test_create_stream_event(self):
        event = StreamEvent(event_type=EventType.THOUGHT, content="thinking...")
        assert event.event_type == EventType.THOUGHT
        assert event.event_category is None
        assert event.content == "thinking..."
        assert event.plan_id is None
        assert event.step_id is None
        assert event.timestamp is not None
        assert event.metadata == {}

    def test_stream_event_with_ids(self):
        event = StreamEvent(
            event_type=EventType.ACTION,
            event_category=EventCategory.TOOL_CALL,
            plan_id="plan-123",
            step_id=1,
            content="calling tool",
        )
        assert event.event_category == EventCategory.TOOL_CALL
        assert event.plan_id == "plan-123"
        assert event.step_id == 1

    def test_stream_event_with_guardrail_category(self):
        event = StreamEvent(
            event_type=EventType.ERROR,
            event_category=EventCategory.GUARDRAIL,
            content="blocked",
        )
        assert event.event_category == EventCategory.GUARDRAIL


class TestChatRequest:
    def test_create_request_auto_session(self):
        req = ChatRequest(message="Hello")
        assert req.message == "Hello"
        assert req.session_id is not None
        assert len(req.session_id) > 0
        assert req.stream is False

    def test_create_request_unique_session_ids(self):
        req1 = ChatRequest(message="Hello")
        req2 = ChatRequest(message="Hello")
        assert req1.session_id != req2.session_id

    def test_request_with_session(self):
        req = ChatRequest(message="Hello", session_id="sess-001", stream=True)
        assert req.session_id == "sess-001"
        assert req.stream is True

    def test_request_message_validation_empty(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_request_message_validation_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 10001)


class TestChatResponse:
    def test_create_response(self):
        resp = ChatResponse(session_id="sess-001", reply="Hi there")
        assert resp.session_id == "sess-001"
        assert resp.reply == "Hi there"
        assert resp.plan_id is None
        assert resp.steps_executed == 0
        assert resp.token_usage == {"prompt": 0, "completion": 0, "total": 0}

    def test_response_with_full_data(self):
        resp = ChatResponse(
            session_id="sess-001",
            reply="Done",
            plan_id="plan-123",
            steps_executed=3,
            token_usage={"prompt": 100, "completion": 50, "total": 150},
        )
        assert resp.plan_id == "plan-123"
        assert resp.steps_executed == 3
        assert resp.token_usage["total"] == 150