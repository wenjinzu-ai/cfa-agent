import pytest

from src.guardrails.output_guardrail import OutputGuardrail
from src.models.guardrail import GuardrailAction, GuardrailSeverity


class TestOutputGuardrailLength:
    @pytest.mark.asyncio
    async def test_normal_output_passes(self):
        rail = OutputGuardrail()
        result = await rail.check("这是正常的输出内容")
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_empty_output_blocked(self):
        rail = OutputGuardrail(min_length=1)
        result = await rail.check("")
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "output_length"

    @pytest.mark.asyncio
    async def test_very_long_output_warns(self):
        rail = OutputGuardrail(max_length=100)
        long_output = "x" * 200
        result = await rail.check(long_output)
        assert result.action == GuardrailAction.WARN
        assert result.rule_name == "output_length"


class TestOutputGuardrailLeaks:
    @pytest.mark.asyncio
    async def test_api_key_leak_sanitized(self):
        rail = OutputGuardrail()
        result = await rail.check("the api key is sk-abcdefghijklmnopqrstuvwxyz123456789")
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "output_leak"
        assert result.severity == GuardrailSeverity.HIGH
        assert result.sanitized_content is not None
        assert "[REDACTED]" in result.sanitized_content

    @pytest.mark.asyncio
    async def test_aws_key_leak_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("AKIAIOSFODNN7EXAMPLE")
        assert result.action == GuardrailAction.BLOCK

    @pytest.mark.asyncio
    async def test_password_leak_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("password= mysecretpassword123")
        assert result.action == GuardrailAction.BLOCK

    @pytest.mark.asyncio
    async def test_ssn_leak_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("SSN: 123-45-6789")
        assert result.action == GuardrailAction.BLOCK

    @pytest.mark.asyncio
    async def test_clean_output_passes_leak_check(self):
        rail = OutputGuardrail()
        result = await rail.check("Python 是一种流行的编程语言")
        assert result.action == GuardrailAction.PASS


class TestOutputGuardrailHarmful:
    @pytest.mark.asyncio
    async def test_hacking_content_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("how to hack into a system")
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "harmful_content"
        assert result.severity == GuardrailSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_malware_content_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("create a virus that spreads")
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "harmful_content"

    @pytest.mark.asyncio
    async def test_bypass_security_blocked(self):
        rail = OutputGuardrail()
        result = await rail.check("bypass authentication to gain access")
        assert result.action == GuardrailAction.BLOCK

    @pytest.mark.asyncio
    async def test_legitimate_security_research_passes(self):
        rail = OutputGuardrail()
        result = await rail.check("安全最佳实践包括使用强密码和双因素认证")
        assert result.action == GuardrailAction.PASS


class TestOutputGuardrailSanitization:
    @pytest.mark.asyncio
    async def test_leaked_key_sanitized(self):
        rail = OutputGuardrail()
        content = "result: sk-abcdefghijklmnopqrstuvwxyz123456789"
        result = await rail.check(content)
        if result.sanitized_content:
            assert "sk-abcdefghijklmnopqrstuvwxyz123456789" not in result.sanitized_content
            assert "[REDACTED]" in result.sanitized_content