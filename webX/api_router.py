import asyncio

import trafilatura
from aiohttp import ClientTimeout
from fastapi import APIRouter
from fastapi.params import Query
from loguru import logger
from pydantic import BaseModel
import aiohttp
from typing import Annotated
from aiohttp import TCPConnector

from webX.models import SearchSnippets, SearchResponse, SearchMode
from webX.playwright_manager import playwright_manager, settings
from webX.utils import check_allow_domain, timeit_sync

search_router = APIRouter(prefix='/v1')


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
            title = item.get("title", "未知标题")
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
    print(1111, data)
    for item in data:
        results.append(
            {
                "url": item["url"],
                "title": item["title"],
                "content": item["content"],
                "score": item.get("score", 0.3),
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
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
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
                date = result.date
                title = result.title
                content = cleaned_body.strip()[: mode.context_size]
                return SearchSnippets(url=url, title=title, content=content, error=None, publish_date=date)
    except Exception as e:
        logger.error(f"Error fetching HTML content: {e}")
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

    tasks = [fetch_with_playwright(item, mode) for item in allowed_items[:8]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    results_remain = [
        SearchSnippets(url=item["url"], title=item["title"], content=item["content"]) for item in allowed_items[5:]
    ]
    return results + results_remain


@search_router.get("/search")
async def search_view(
    q: str = Query(default="K字签证"),
    engine:str = Query(default="mullvadleta"),
    mode: Annotated[SearchMode, Query()] = SearchMode.low,
):
    """
    use aiohttp sync to fetch searxng search results
    """
    params =  {
        "query": q,
    }
    connector = TCPConnector(limit=100, limit_per_host=15, ssl=False)
    import time

    start_ts = time.time()
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=ClientTimeout(total=5.0)) as session:
            async with session.get(settings.searxng_url, params=params) as resp:
                resp.raise_for_status()
                results = await resp.json()
                data = results["results"]
                new_data = []
                for item in data:
                    new_data.append({"url": item["link"], "title": item["title"], "content": item["content"] +f'来源: {item["source"]}', "score":"0.420"})


        match mode:
            case SearchMode.low:
                snippets = run_parser_as_low(new_data)
            case SearchMode.medium:
                snippets = await run_parser_as_other(new_data, mode=SearchMode.medium)
            case SearchMode.high:
                snippets = await run_parser_as_other(new_data, mode=SearchMode.high)
            case _:
                snippets = new_data

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