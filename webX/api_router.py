import asyncio
import time
import trafilatura
from aiohttp import ClientTimeout
from fake_useragent import UserAgent
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
from webX.utils import check_allow_domain, timeit_sync

search_router = APIRouter(prefix="/v1")


class FetchResult(BaseModel):
    url: str
    title: str | None = None
    content: str | None = None
    error: str | None = None


async def fetch_with_playwright(item: dict, mode: SearchMode = SearchMode.medium) -> SearchSnippets:
    url = item["url"]
    import time

    start_ts = time.time()
    try:
        logger.debug(f"fetching use playwright: url: {url}")

        @timeit_sync
        async def work(page):
            await page.goto(url, timeout=25_000, wait_until="domcontentloaded")
            title = await page.title()
            html = await page.content()

            result = trafilatura.bare_extraction(
                html,
                url=url,
                include_links=False,
                include_tables=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,  # 更偏向召回，适合通用页面
            )
            title = result.title or title
            cleaned_body = result.text
            date = result.date
            logger.info(f"fetch  {url} content: {cleaned_body[:100]}")

            if not cleaned_body:
                # 回退：若抽取失败，退回到 body.inner_text()
                cleaned_body = await page.locator("body").inner_text()

            content = cleaned_body.strip()[: mode.context_size]
            logger.info(f"scrapy duration: {time.time() - start_ts:.2f}s")
            return SearchSnippets(url=url, title=title, content=content, error=None, publish_date=date)

        return await playwright_manager.run_in_page(work)
    except Exception as e:
        logger.error(f"⚠️ Error fetching url: {url}, error: {e}")
        return SearchSnippets(url=url, title=item.get("title", "-"), content=item.get("content", "-"))


def run_parser_as_low(data) -> list[SearchSnippets]:
    results: list[SearchSnippets] = []

    for item in data:
        results.append(
            {
                "url": item["url"],
                "title": item["title"],
                "content": item["content"],
                "score": f"{item['score']:.3f}",
            }
        )
    return results


async def fetch_html_content(item: dict[str, str], mode: SearchMode = SearchMode.medium) -> SearchSnippets:
    """
    use aiohttp sync to fetch html content
    :param url:
    :return:
    """
    url = item["url"]
    timeout = ClientTimeout(total=1.2)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }
    ua = UserAgent()
    headers["User-Agent"] = ua.random
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as response:
                html = await response.text(encoding="utf-8") or ""
                result = trafilatura.bare_extraction(
                    html,
                    url=url,
                    include_links=False,
                    include_tables=False,
                    include_images=False,
                    include_comments=False,
                    favor_recall=True,  # 更偏向召回，适合通用页面
                )
                cleaned_body = result.text
                date = result.date or ""
                title = result.title or ""
                content = cleaned_body.strip()[: mode.context_size]
                return SearchSnippets(url=url, title=title, content=content, error=None, publish_date=date)
    except Exception as e:
        logger.error(f"Error fetching HTML content:  {item}")
        return SearchSnippets(url=url, title=item["title"], content=item["content"], error=str(e), publish_date=None)


async def run_parser_as_other(data, mode: SearchMode) -> list[SearchSnippets]:
    """
    urls exclude file types: like pdf, docx, excel
    html_urls, include, shtml, html, html
    """
    snippets = [data for data in data if data["url"]]

    allowed_items = []
    for item in snippets:
        url = item["url"]
        if check_allow_domain(url):
            allowed_items.append(item)

    # 区分静态HTML页面和其他页面
    static_html_items = []
    dynamic_items = []

    for item in allowed_items:
        url = item["url"].lower()
        # 检查是否为静态HTML页面
        if any(url.endswith(ext) for ext in [".html", ".htm", ".shtml"]):
            static_html_items.append(item)
        else:
            dynamic_items.append(item)

    static_tasks = [fetch_html_content(item, mode) for item in static_html_items]

    dynamic_tasks = [fetch_with_playwright(item, mode) for item in dynamic_items]

    all_tasks = static_tasks + dynamic_tasks
    results = await asyncio.gather(*all_tasks, return_exceptions=True)

    results_remain = [SearchSnippets(url=item["url"], title=item["title"], content=item["content"]) for item in results]
    return results_remain


@search_router.get("/search")
async def search_view(
    q: str = Query(default="K字签证"),
    mode: Annotated[SearchMode, Query()] = SearchMode.low,
):
    """
    use aiohttp sync to fetch searxng search results
    """
    params: SearchParams = {
        "q": q,
        "lang": "zh-CN",
        "format": "json",
        "safesearch": "2",
        "engines": "google",
    }
    connector = TCPConnector(limit=100, limit_per_host=15, ssl=False)

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
            case SearchMode.high:
                snippets = await run_parser_as_other(data, mode=SearchMode.high)
            case _:
                snippets = data

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