"""CFA-Agent 网页抓取工具

两步式智能抓取：
Step 1: web_fetch(url, query="黄金价格") → 返回页面大纲 + 相关区域预览
Step 2: web_fetch(url, selector=".price-table") → 精确提取指定区域

核心能力：
- query 参数：按关键词定位最相关内容区域，避免全文截断丢失关键数据
- 页面大纲：返回页面结构概览，Agent 可据此选择精确 selector
- JS 渲染检测：自动识别并给出策略建议
- CSS 选择器：支持精确提取

典型使用链路：
  web_search → snippet 不够 → web_fetch(url, query="XXX") 定位区域
  → 如果需要更精确 → web_fetch(url, selector=".xxx") 提取
  → 如果 JS 渲染 → 搜索 API 或委派 code_agent
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import Field

from src.tools.base import BaseTool

logger = logging.getLogger("cfa-agent.tools.web_fetch")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg", "form"}

_SECTION_TAGS = {"section", "article", "div", "table", "ul", "ol", "dl", "main"}

_HEADING_TAGS = {"h1", "h2", "h3", "h4"}


class WebFetch(BaseTool):
    """网页抓取工具

    在 web_search 之后使用，访问搜索结果中的 URL 获取详细内容。
    支持 query 参数按关键词定位相关区域，支持 CSS 选择器精确提取。
    """

    name: str = "web_fetch"
    description: str = (
        "Fetch and extract text content from a URL. "
        "Use this AFTER web_search when search snippets lack the details you need. "
        "Supports two modes: "
        "1) query mode: pass query='what you are looking for' to auto-locate relevant sections. "
        "2) selector mode: pass selector='.class' to extract specific elements. "
        "If the page requires JavaScript rendering (is_js_rendered=true), "
        "try: 1) another URL, 2) search for an API, 3) delegate to code_agent."
    )
    timeout: int = Field(default=20, description="Request timeout in seconds")
    max_content_length: int = Field(default=5000, description="Max content length to return")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "What information you are looking for on this page. "
                        "The tool will locate the most relevant sections containing these keywords. "
                        "Examples: 'gold price', 'earnings data', 'weather forecast'. "
                        "If not provided, returns the main content from the top of the page."
                    ),
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "CSS selector to extract specific elements "
                        "(e.g. '.price', '#content', 'table', 'article'). "
                        "Use this when you know the page structure from a previous fetch. "
                        "If both query and selector are provided, selector takes priority."
                    ),
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        url = kwargs.get("url", "")
        query = kwargs.get("query", "")
        selector = kwargs.get("selector")

        if not url:
            return {"url": url, "content": "", "error": "URL is required"}

        if not url.startswith(("http://", "https://")):
            return {"url": url, "content": "", "error": "URL must start with http:// or https://"}

        try:
            return await self._fetch(url, query=query, selector=selector)
        except httpx.TimeoutException:
            return {"url": url, "content": "", "error": f"Request timed out after {self.timeout}s"}
        except httpx.HTTPStatusError as e:
            return {"url": url, "content": "", "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.warning("web_fetch error for %s: %s", url, e)
            return {"url": url, "content": "", "error": str(e)}

    async def _fetch(self, url: str, query: str = "", selector: str | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(_NOISE_TAGS):
            tag.decompose()

        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)

        is_js_rendered, js_hint = self._detect_js_rendering(html, soup)

        if selector:
            content = self._extract_by_selector(soup, selector)
            return {
                "url": url,
                "title": title,
                "content": content,
                "content_length": len(content),
                "is_js_rendered": is_js_rendered,
                "js_hint": js_hint,
                "status_code": resp.status_code,
            }

        if query:
            content, sections = self._extract_by_query(soup, query)
            return {
                "url": url,
                "title": title,
                "content": content,
                "content_length": len(content),
                "sections": sections,
                "is_js_rendered": is_js_rendered,
                "js_hint": js_hint,
                "status_code": resp.status_code,
            }

        content = self._extract_main(soup)
        sections = self._build_outline(soup)

        return {
            "url": url,
            "title": title,
            "content": content,
            "content_length": len(content),
            "sections": sections,
            "is_js_rendered": is_js_rendered,
            "js_hint": js_hint,
            "status_code": resp.status_code,
        }

    def _extract_by_selector(self, soup: BeautifulSoup, selector: str) -> str:
        elements = soup.select(selector)
        if not elements:
            return f"No elements found for selector: {selector}"
        parts = []
        for el in elements:
            text = el.get_text(strip=True, separator=" ")
            text = " ".join(text.split())
            if text:
                parts.append(text)
        content = "\n".join(parts)
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length] + "\n... (content truncated)"
        return content

    def _extract_by_query(self, soup: BeautifulSoup, query: str) -> tuple[str, list[dict]]:
        keywords = self._extract_keywords(query)
        sections = self._find_sections(soup, keywords)

        if not sections:
            main_content = self._extract_main(soup)
            outline = self._build_outline(soup)
            if len(main_content) > self.max_content_length:
                main_content = main_content[:self.max_content_length] + "\n... (content truncated)"
            return main_content, outline

        sections.sort(key=lambda s: s["relevance"], reverse=True)

        content_parts = []
        seen_texts = set()
        for sec in sections:
            text = sec["text"]
            if text[:80] not in seen_texts:
                seen_texts.add(text[:80])
                content_parts.append(text)

        content = "\n\n".join(content_parts)
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length] + "\n... (content truncated)"

        outline = []
        for sec in sections[:10]:
            outline.append({
                "selector": sec["selector"],
                "heading": sec.get("heading", ""),
                "preview": sec["text"][:120],
                "relevance": sec["relevance"],
            })

        return content, outline

    def _extract_main(self, soup: BeautifulSoup) -> str:
        main = (
            soup.select_one("main")
            or soup.select_one("article")
            or soup.select_one("#content")
            or soup.select_one(".content")
            or soup.select_one(".main")
        )
        if main:
            content = main.get_text(strip=True, separator=" ")
        else:
            content = soup.get_text(strip=True, separator=" ")
        content = " ".join(content.split())
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length] + "\n... (content truncated)"
        return content

    def _build_outline(self, soup: BeautifulSoup) -> list[dict]:
        outline = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "table", "article", "section"]):
            text = tag.get_text(strip=True, separator=" ")[:100]
            if not text:
                continue
            selector = self._get_selector_for_tag(tag)
            tag_name = tag.name
            if tag_name in _HEADING_TAGS:
                outline.append({"selector": selector, "type": "heading", "preview": text})
            elif tag_name == "table":
                outline.append({"selector": selector, "type": "table", "preview": text[:120]})
            elif tag_name in ("article", "section"):
                outline.append({"selector": selector, "type": "section", "preview": text[:120]})
            if len(outline) >= 15:
                break
        return outline

    def _find_sections(self, soup: BeautifulSoup, keywords: list[str]) -> list[dict]:
        sections = []
        candidates = soup.find_all(_SECTION_TAGS)

        for tag in candidates:
            text = tag.get_text(strip=True, separator=" ")
            text = " ".join(text.split())
            if len(text) < 20:
                continue

            relevance = self._calc_relevance(text, keywords)
            if relevance <= 0:
                continue

            heading = ""
            for h in tag.find_all(_HEADING_TAGS):
                heading = h.get_text(strip=True)
                break
            if not heading:
                prev = tag.find_previous_sibling()
                if prev and prev.name in _HEADING_TAGS:
                    heading = prev.get_text(strip=True)

            selector = self._get_selector_for_tag(tag)

            sections.append({
                "selector": selector,
                "heading": heading,
                "text": text[:2000],
                "relevance": relevance,
            })

        return sections

    @staticmethod
    def _calc_relevance(text: str, keywords: list[str]) -> float:
        if not keywords:
            return 0
        text_lower = text.lower()
        score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            count = text_lower.count(kw_lower)
            if count > 0:
                score += min(count * 2, 10)
                idx = text_lower.find(kw_lower)
                if idx < 300:
                    score += 5
        return score

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        words = re.split(r"[\s,，、|]+", query.strip())
        keywords = [w for w in words if len(w) >= 2]
        if len(keywords) == 1 and len(keywords[0]) >= 4:
            bigrams = [keywords[0][i:i+2] for i in range(len(keywords[0])-1)]
            keywords.extend(bigrams)
        return keywords

    @staticmethod
    def _get_selector_for_tag(tag: Tag) -> str:
        if tag.get("id"):
            return f"#{tag['id']}"
        if tag.get("class"):
            classes = tag.get("class")
            if isinstance(classes, list) and classes:
                return f"{tag.name}.{classes[0]}"
        return tag.name

    @staticmethod
    def _detect_js_rendering(html: str, soup: BeautifulSoup) -> tuple[bool, str]:
        body = soup.find("body")
        if body:
            visible_text = body.get_text(strip=True)
        else:
            visible_text = soup.get_text(strip=True)

        if len(visible_text) >= 200 or len(html) < 5000:
            return False, ""

        scripts = soup.find_all("script")
        script_text_len = sum(len(s.get_text() + str(s.get("src", ""))) for s in scripts)

        if script_text_len > len(html) * 0.3:
            return True, (
                "This page appears to require JavaScript rendering. "
                "The static HTML contains mostly scripts with little visible text. "
                "Suggestions: 1) Try a different URL from search results, "
                "2) Search for 'XXX API' or 'XXX json' to find a structured data source, "
                "3) Delegate to code_agent to write a custom fetch script."
            )

        return False, ""