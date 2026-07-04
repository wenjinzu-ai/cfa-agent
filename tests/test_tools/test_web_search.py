import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.tool import ToolPermission, ToolResult
from src.tools.registry import ToolRegistry
from src.tools.web_search import WebSearchTool


@pytest.fixture(autouse=True)
def reset_registry():
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


class TestWebSearchToolDefinition:
    def test_definition_name(self):
        tool = WebSearchTool()
        assert tool.definition.name == "web_search"

    def test_definition_description(self):
        tool = WebSearchTool()
        assert "搜索" in tool.definition.description

    def test_definition_permissions(self):
        tool = WebSearchTool()
        assert ToolPermission.NETWORK in tool.definition.permissions

    def test_definition_timeout(self):
        tool = WebSearchTool()
        assert tool.definition.timeout_seconds == 30

    def test_definition_parameters(self):
        tool = WebSearchTool()
        params = tool.definition.parameters
        assert "query" in params["properties"]
        assert "query" in params["required"]

    @pytest.mark.asyncio
    async def test_validate_params_valid(self):
        tool = WebSearchTool()
        valid, err = await tool.validate_params({"query": "test"})
        assert valid is True
        assert err == ""

    @pytest.mark.asyncio
    async def test_validate_params_missing_query(self):
        tool = WebSearchTool()
        valid, err = await tool.validate_params({})
        assert valid is False
        assert "query" in err.lower()


class TestWebSearchToolExecute:
    @pytest.mark.asyncio
    async def test_execute_success_with_results(self):
        html = (
            '<a class="result__a" href="https://example.com">Python Docs</a>'
            '<a class="result__snippet">Official Python documentation</a>'
            '<a class="result__a" href="https://pypi.org">PyPI</a>'
            '<a class="result__snippet">Python Package Index</a>'
        )
        tool = WebSearchTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(query="Python", max_results=2)

        assert result.success is True
        assert "results" in result.data
        assert len(result.data["results"]) == 2
        assert result.data["results"][0]["title"] == "Python Docs"
        assert result.data["results"][0]["snippet"] == "Official Python documentation"
        assert "raw_html" in result.data

    @pytest.mark.asyncio
    async def test_execute_max_results_limits_output(self):
        html = ""
        for i in range(10):
            html += f'<a class="result__a" href="#">Result {i}</a>'
            html += f'<a class="result__snippet">Snippet {i}</a>'

        tool = WebSearchTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(query="test", max_results=3)

        assert result.success is True
        assert len(result.data["results"]) == 3

    @pytest.mark.asyncio
    async def test_execute_http_error(self):
        tool = WebSearchTool()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPError("connection failed")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(query="test")

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_truncates_html(self):
        long_html = "x" * 10000
        tool = WebSearchTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = long_html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(query="test")

        assert result.success is True
        assert len(result.data["raw_html"]) <= 5000