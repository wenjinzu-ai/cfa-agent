from src.llm.token_counter import TokenCounter, TokenUsage


class TestTokenUsage:
    def test_default_values(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_add(self):
        u1 = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        u2 = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        u1.add(u2)
        assert u1.prompt_tokens == 30
        assert u1.completion_tokens == 15
        assert u1.total_tokens == 45

    def test_to_dict(self):
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        d = usage.to_dict()
        assert d == {"prompt": 100, "completion": 50, "total": 150}


class TestTokenCounter:
    def test_record_dict_usage(self):
        counter = TokenCounter()
        counter.record(
            {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
            session_id="sess-001",
        )
        usage = counter.get_session_usage("sess-001")
        assert usage.prompt_tokens == 50
        assert usage.total_tokens == 75

    def test_record_token_usage_object(self):
        counter = TokenCounter()
        u = TokenUsage(prompt_tokens=30, completion_tokens=15, total_tokens=45)
        counter.record(u, session_id="sess-001")
        usage = counter.get_session_usage("sess-001")
        assert usage.prompt_tokens == 30

    def test_record_with_task_id(self):
        counter = TokenCounter()
        counter.record(
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_id="sess-001",
            task_id="task-001",
        )
        task_usage = counter.get_task_usage("task-001")
        assert task_usage.total_tokens == 15

    def test_accumulates_usage(self):
        counter = TokenCounter()
        counter.record({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, session_id="sess-001")
        counter.record({"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}, session_id="sess-001")
        usage = counter.get_session_usage("sess-001")
        assert usage.prompt_tokens == 30
        assert usage.total_tokens == 45

    def test_is_over_budget(self):
        counter = TokenCounter(budget_per_session=100)
        counter.record({"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}, session_id="sess-001")
        assert counter.is_over_budget("sess-001") is False
        counter.record({"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25}, session_id="sess-001")
        assert counter.is_over_budget("sess-001") is True

    def test_is_not_over_budget_default(self):
        counter = TokenCounter()
        assert counter.is_over_budget("nonexistent") is False

    def test_estimate_tokens_english(self):
        counter = TokenCounter()
        text = "Hello world this is a test"
        tokens = counter.estimate_tokens(text)
        assert tokens > 0
        assert tokens < len(text)

    def test_estimate_tokens_chinese(self):
        counter = TokenCounter()
        text = "你好世界这是一个测试"
        tokens = counter.estimate_tokens(text)
        assert tokens > 0

    def test_estimate_tokens_mixed(self):
        counter = TokenCounter()
        text = "Hello 你好 world 世界"
        tokens = counter.estimate_tokens(text)
        assert tokens > 0

    def test_truncate_context_empty(self):
        counter = TokenCounter()
        assert counter.truncate_context([]) == []

    def test_truncate_context_preserves_system(self):
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
        ]
        result = counter.truncate_context(messages, max_tokens=1000)
        assert result[0]["role"] == "system"

    def test_truncate_context_truncates(self):
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "System"},
        ]
        for i in range(100):
            messages.append({"role": "user", "content": f"Message {i} " * 50})
        result = counter.truncate_context(messages, max_tokens=500)
        assert len(result) < len(messages)
        assert result[0]["role"] == "system"

    def test_get_session_usage_default(self):
        counter = TokenCounter()
        usage = counter.get_session_usage("nonexistent")
        assert usage.total_tokens == 0