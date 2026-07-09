"""CFA-Agent 网络搜索工具

支持多搜索引擎 + 自动降级策略：
1. Bing 中国版（cn.bing.com）— 国内直连可用，默认首选
2. DuckDuckGo — 海外可用，国内可能超时
3. Google — 需要代理，通过 googlesearch-python 库

搜索策略：
- 默认使用 bing，失败自动降级到 duckduckgo → google
- 可指定 engine 强制使用某个引擎
- engine="auto" 时按优先级自动降级
"""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from src.tools.base import BaseTool

_ENGINES = ["bing", "duckduckgo", "google"]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class WebSearch(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for real-time and up-to-date information. "
        "MUST use this tool when you need: current prices (gold, stock, crypto, exchange rate), "
        "today's weather, latest news, live scores, recent events, "
        "or any time-sensitive information that changes frequently. "
        "Returns search results with titles, URLs, and snippets. "
        "Supports multiple search engines with automatic fallback."
    )
    default_max_results: int = Field(default=8, description="Default max results")
    timeout: int = Field(default=15, description="Per-engine timeout in seconds")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 8)",
                    "default": 8,
                },
                "engine": {
                    "type": "string",
                    "description": (
                        "Search engine: 'bing' (default, works in China), "
                        "'duckduckgo', 'google', or 'auto' (try bing → duckduckgo → google)"
                    ),
                    "enum": ["auto", "bing", "duckduckgo", "google"],
                    "default": "auto",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", self.default_max_results)
        engine = kwargs.get("engine", "auto")

        if not query:
            return {"query": query, "results": [], "error": "Query cannot be empty"}

        if engine == "auto":
            return await self._search_auto(query, max_results)

        try:
            results = await self._search_single(query, max_results, engine)
            return {
                "query": query,
                "engine": engine,
                "results": results,
                "total": len(results),
            }
        except Exception as e:
            return {"query": query, "engine": engine, "results": [], "error": str(e)}

    async def _search_auto(self, query: str, max_results: int) -> dict[str, Any]:
        errors = []
        for eng in _ENGINES:
            try:
                results = await self._search_single(query, max_results, eng)
                if results:
                    return {
                        "query": query,
                        "engine": eng,
                        "results": results,
                        "total": len(results),
                    }
            except Exception as e:
                errors.append(f"{eng}: {e}")
                continue

        return {
            "query": query,
            "engine": "auto",
            "results": [],
            "error": f"All engines failed: {'; '.join(errors)}",
        }

    async def _search_single(
        self, query: str, max_results: int, engine: str
    ) -> list[dict[str, str]]:
        if engine == "bing":
            return await self._search_bing(query, max_results)
        elif engine == "duckduckgo":
            return await self._search_duckduckgo(query, max_results)
        elif engine == "google":
            return await self._search_google(query, max_results)
        else:
            return await self._search_bing(query, max_results)

    async def _search_bing(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        import httpx
        from bs4 import BeautifulSoup

        url = "https://cn.bing.com/search"
        params = {"q": query, "count": max_results}
        headers = {"User-Agent": _UA}

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("#b_results > li.b_algo")

        results = []
        for item in items[:max_results]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p") or item.select_one("p")
            title = title_el.get_text(strip=True) if title_el else ""
            href = title_el.get("href", "") if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title:
                results.append({"title": title, "url": href, "snippet": snippet})

        return results

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            raise RuntimeError("duckduckgo-search not installed. Run: pip install duckduckgo-search")

        results = []
        with DDGS(timeout=self.timeout) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results

    async def _search_google(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        try:
            from googlesearch import search as gsearch
        except ImportError:
            raise RuntimeError("googlesearch-python not installed. Run: pip install googlesearch-python")

        urls = list(gsearch(query, num_results=max_results, timeout=self.timeout, lang="zh-CN"))
        results = []
        for url in urls:
            results.append({"title": "", "url": str(url), "snippet": ""})
        return results