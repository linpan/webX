import asyncio

import trafilatura
from aiohttp import ClientTimeout
from fastapi import APIRouter
from fastapi.params import Query
from loguru import logger
from pydantic import BaseModel
import aiohttp
from typing import Annotated
from webX.config import settings
from aiohttp import TCPConnector

from webX.models import SearchParams, SearchSnippets, SearchResponse, SearchMode
from webX.playwright_manager import playwright_manager
from webX.utils import check_allow_domain

search_router = APIRouter()


class FetchResult(BaseModel):
    url: str
    title: str | None = None
    content: str | None = None
    error: str | None = None


async def fetch_with_playwright(url: str, mode: SearchMode = SearchMode.medium) -> SearchSnippets:
    try:
        print("fetching use playwright")

        async def work(page):
            await page.goto(url, timeout=5000, wait_until="domcontentloaded")
            await page.wait_for_load_state("domcontentloaded")
            title = await page.title()
            html = await page.content()
            cleaned_body = trafilatura.extract(
                html,
                url=url,
                include_links=False,
                include_tables=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,  # 更偏向召回，适合通用页面
            )

            if not cleaned_body:
                # 回退：若抽取失败，退回到 body.inner_text()
                cleaned_body = await page.locator("body").inner_text()

            content = cleaned_body.strip()[: mode.context_size]

            return SearchSnippets(url=url, title=title, content=content)

        return await playwright_manager.run_in_page(work)
    except Exception:
        return SearchSnippets(url=url, title="", content="")


def run_parser_as_low(data) -> list[SearchSnippets]:
    results: list[SearchSnippets] = []

    for item in data:
        results.append({"url": item["url"], "title": item["title"], "content": item["content"], "score": item["score"]})
    return results


async def fetch_html_content(url: str, mode: SearchMode = SearchMode.medium) -> SearchSnippets:
    """
    use aiohttp sync to fetch html content
    :param url:
    :return:
    """
    timeout = ClientTimeout(total=0.7)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as response:
            html = await response.text(encoding="utf-8") or ""
            cleaned_body = trafilatura.extract(
                html,
                url=url,
                include_links=False,
                include_tables=False,
                include_images=False,
                include_comments=False,
                favor_recall=True,  # 更偏向召回，适合通用页面
            )
            content = cleaned_body.strip()[: mode.context_size]
            return SearchSnippets(url=url, title="", content=content)


async def run_parser_as_other(data, mode: SearchMode) -> list[SearchSnippets]:
    """
    urls exclude file types: like pdf, docx, excel
    html_urls, include, shtml, html, html
    """
    urls = [data["url"] for data in data if data["url"]]

    allowed_urls = []
    for url in urls:
        if check_allow_domain(url):
            allowed_urls.append(url)

    html_urls = [url for url in urls if url.endswith((".shtml", ".html", ".htm", ".xhtml"))]
    print(f"html_urls: {html_urls}")
    js_urls = list(set(allowed_urls) - set(html_urls))
    print("js_urls:", js_urls)
    # slow mode doesn't use playwright
    tasks = [fetch_with_playwright(url, mode=mode) for url in js_urls if mode != SearchMode.low]
    print("tasks:", tasks)
    for url in html_urls:
        tasks.append(fetch_html_content(url, mode=mode))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


@search_router.get("/search")
async def search_view(q: str = Query(default="K字签证"), mode: Annotated[SearchMode, Query()] = SearchMode.low):
    """
    use aiohttp sync to fetch searxng search results
    """
    params: SearchParams = {"q": q, "lang": "zh-CN", "format": "json", "safesearch": "2", "engines": "google"}
    connector = TCPConnector(limit=100, limit_per_host=10, ssl=False)
    import time

    start_ts = time.time()
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=ClientTimeout(total=5.0)) as session:
            async with session.get(settings.searxng_url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                data = data["results"]

        match mode:
            case SearchMode.low:
                snippets = run_parser_as_low(data)
            case SearchMode.medium:
                snippets = await run_parser_as_other(data, mode=SearchMode.medium)
                return snippets
            case SearchMode.high:
                snippets = await run_parser_as_other(data, mode=SearchMode.high)
                return snippets
            case _:
                return data["results"]

    except aiohttp.ClientResponseError as e:
        logger.error(f"Failed to fetch search results: {e.status}")
        return SearchResponse(q=q, mode=mode, snippets=[])

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error(f"Failed to fetch search results: {e}")
        return SearchResponse(q=q, mode=mode, snippets=[])

    except Exception as e:
        logger.error(f"Failed to fetch search results: {e}")
        return SearchResponse(q=q, mode=mode, snippets=[])

    end_ts = time.time()
    total_time = f"{end_ts - start_ts:.2f}s"
    return SearchResponse(snippets=snippets, q=q, time=total_time, mode=mode)
