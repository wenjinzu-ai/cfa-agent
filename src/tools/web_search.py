from __future__ import annotations

import os
import re
import time

import httpx

from src.common.logger import logger
from src.models.tool import ToolDefinition, ToolPermission, ToolResult
from src.tools.base import BaseTool
from src.tools.registry import tool_register

_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
_RESULT_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_DDG_LITE_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
_DDG_LITE_SNIPPET_RE = re.compile(
    r'<td[^>]+class="result__snippet"[^>]*>(.*?)</td>', re.DOTALL
)

_BING_LINK_RE = re.compile(
    r'<li[^>]+class="b_algo"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
_BING_SNIPPET_RE = re.compile(
    r'<div[^>]+class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', re.DOTALL
)


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text).strip()


def _get_proxy() -> str | None:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or \
        os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None


def _build_client(timeout: int = 30) -> httpx.AsyncClient:
    proxy = _get_proxy()
    kwargs: dict = {"timeout": timeout, "follow_redirects": True}
    if proxy:
        kwargs["proxy"] = proxy
        logger.debug("搜索使用代理: %s", proxy)
    return httpx.AsyncClient(**kwargs)


async def _search_duckduckgo_html(query: str, max_results: int) -> list[dict]:
    logger.debug("[ddg_html] 请求开始 query=%s", query[:50])
    t0 = time.monotonic()
    async with _build_client() as client:
        resp = await client.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
        )
        resp.raise_for_status()
        html = resp.text

    elapsed = time.monotonic() - t0
    titles = _RESULT_LINK_RE.findall(html)
    snippets = _RESULT_SNIPPET_RE.findall(html)
    logger.debug(
        "[ddg_html] 响应耗时=%.2fs html_len=%d titles=%d snippets=%d",
        elapsed, len(html), len(titles), len(snippets),
    )

    results = []
    for i in range(min(max_results, len(titles))):
        entry = {"title": _strip_html(titles[i][1]), "url": titles[i][0]}
        if i < len(snippets):
            entry["snippet"] = _strip_html(snippets[i])
        results.append(entry)
    return results


async def _search_duckduckgo_lite(query: str, max_results: int) -> list[dict]:
    logger.debug("[ddg_lite] 请求开始 query=%s", query[:50])
    t0 = time.monotonic()
    async with _build_client() as client:
        resp = await client.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query, "kl": "cn-zh"},
        )
        resp.raise_for_status()
        html = resp.text

    elapsed = time.monotonic() - t0
    titles = _DDG_LITE_LINK_RE.findall(html)
    snippets = _DDG_LITE_SNIPPET_RE.findall(html)
    logger.debug(
        "[ddg_lite] 响应耗时=%.2fs html_len=%d titles=%d snippets=%d",
        elapsed, len(html), len(titles), len(snippets),
    )

    results = []
    for i in range(min(max_results, len(titles))):
        entry = {"title": _strip_html(titles[i][1]), "url": titles[i][0]}
        if i < len(snippets):
            entry["snippet"] = _strip_html(snippets[i])
        results.append(entry)
    return results


async def _search_bing(query: str, max_results: int) -> list[dict]:
    logger.debug("[bing] 请求开始 query=%s", query[:50])
    t0 = time.monotonic()
    async with _build_client() as client:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "count": max_results},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        resp.raise_for_status()
        html = resp.text

    elapsed = time.monotonic() - t0
    titles = _BING_LINK_RE.findall(html)
    snippets = _BING_SNIPPET_RE.findall(html)
    logger.debug(
        "[bing] 响应耗时=%.2fs html_len=%d titles=%d snippets=%d",
        elapsed, len(html), len(titles), len(snippets),
    )

    if not titles:
        has_captcha = "captcha" in html.lower() or "verify" in html.lower()
        logger.warning(
            "[bing] 未解析到结果, html_len=%d, 疑似验证码=%s, html前500字符: %s",
            len(html), has_captcha, html[:500],
        )

    results = []
    for i in range(min(max_results, len(titles))):
        entry = {"title": _strip_html(titles[i][1]), "url": titles[i][0]}
        if i < len(snippets):
            entry["snippet"] = _strip_html(snippets[i])
        results.append(entry)
    return results


async def _search_duckduckgo_api(query: str, max_results: int) -> list[dict]:
    logger.debug("[ddg_api] 请求开始 query=%s", query[:50])
    t0 = time.monotonic()
    async with _build_client() as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    elapsed = time.monotonic() - t0
    related_count = len(data.get("RelatedTopics", []))
    has_abstract = bool(data.get("Abstract"))
    logger.debug(
        "[ddg_api] 响应耗时=%.2fs related_topics=%d has_abstract=%s",
        elapsed, related_count, has_abstract,
    )

    results = []
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and "Text" in topic and "FirstURL" in topic:
            results.append({
                "title": topic.get("Text", "")[:80],
                "url": topic.get("FirstURL", ""),
                "snippet": topic.get("Text", ""),
            })
    abstract = data.get("Abstract")
    if abstract and data.get("AbstractURL"):
        results.insert(0, {
            "title": data.get("Heading", "摘要"),
            "url": data.get("AbstractURL", ""),
            "snippet": abstract,
        })
    return results[:max_results]


_BACKENDS = [
    ("bing", _search_bing, "Bing HTML"),
    ("ddg_api", _search_duckduckgo_api, "DuckDuckGo API"),
    ("ddg_html", _search_duckduckgo_html, "DuckDuckGo HTML"),
    ("ddg_lite", _search_duckduckgo_lite, "DuckDuckGo Lite"),
]


@tool_register
class WebSearchTool(BaseTool):
    definition = ToolDefinition(
        name="web_search",
        version="2.0.0",
        description="搜索互联网获取最新信息，支持多后端自动降级",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        permissions=[ToolPermission.NETWORK],
        timeout_seconds=30,
    )

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        logger.info("搜索开始 query=%s max_results=%d", query[:50], max_results)
        t_start = time.monotonic()
        last_error: str = ""
        tried_backends: list[str] = []

        for backend_id, search_fn, backend_name in _BACKENDS:
            tried_backends.append(backend_id)
            try:
                results = await search_fn(query, max_results)
                if results:
                    total_elapsed = time.monotonic() - t_start
                    logger.info(
                        "搜索成功 [backend=%s] query=%s results=%d 总耗时=%.2fs 尝试后端=%s",
                        backend_id, query[:30], len(results), total_elapsed, tried_backends,
                    )
                    return ToolResult(
                        success=True,
                        data={"results": results, "backend": backend_id},
                    )
                logger.warning(
                    "搜索后端 %s 返回空结果 query=%s, 继续尝试下一个后端",
                    backend_name, query[:30],
                )
            except httpx.ConnectError as e:
                last_error = f"连接失败: {e}"
                logger.warning(
                    "搜索后端 %s 连接失败 query=%s error=%s",
                    backend_name, query[:30], str(e)[:100],
                )
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {e}"
                logger.warning(
                    "搜索后端 %s 请求超时 query=%s timeout=%s",
                    backend_name, query[:30], str(e)[:100],
                )
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.warning(
                    "搜索后端 %s HTTP错误 query=%s status=%d",
                    backend_name, query[:30], e.response.status_code,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "搜索后端 %s 异常 query=%s type=%s error=%s",
                    backend_name, query[:30], type(e).__name__, str(e)[:100],
                )

        total_elapsed = time.monotonic() - t_start
        logger.error(
            "搜索全部失败 query=%s 总耗时=%.2fs 尝试后端=%s 最后错误=%s",
            query[:30], total_elapsed, tried_backends, last_error[:200],
        )
        return ToolResult(
            success=False,
            error=f"所有搜索后端均失败，尝试: {', '.join(tried_backends)}，最后错误: {last_error[:200]}",
        )