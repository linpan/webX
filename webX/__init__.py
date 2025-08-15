# import asyncio
# import time
#
# from playwright.async_api import async_playwright
#
# import trafilatura
#
# async def fetch_page_content_async(url: str, timeout: int = 3000) -> str | None:
#     """
#     使用 Playwright 的异步 API 抓取页面内容并返回 HTML 字符串。
#     timeout 单位为毫秒(ms)，默认 3000。
#     """
#     playwright = None
#     browser = None
#     try:
#         async with async_playwright() as p:
#             playwright = p
#             # 启动 Chromium 浏览器（无头模式）
#             browser = await p.chromium.launch(headless=True)
#             page = await browser.new_page()
#
#             # 访问目标网页，设置超时（毫秒）
#             await page.goto(url, timeout=timeout)
#             # 等待页面加载完成
#             await page.wait_for_load_state("domcontentloaded")
#
#             # 获取页面内容
#             content = await page.content()
#             cleaned = trafilatura.extract(content, url=url)
#             content = cleaned.strip()[:1000]
#             print(content)
#             return content
#
#     except Exception as e:
#         print(f"抓取失败: {e}")
#         return None
#     finally:
#         # 关闭浏览器（如果已启动）
#         if browser:
#             try:
#                 await browser.close()
#             except Exception:
#                 pass
#
#
# def fetch_page_content(url: str, timeout: int = 3000) -> str | None:
#     """
#     同步包装，便于同步代码直接调用。
#     """
#     return asyncio.run(fetch_page_content_async(url, timeout=timeout))
#
#
# if __name__ == "__main__":
#     # 测试 URL（示例：仅在作为脚本运行时执行）
#     url = "https://mp.weixin.qq.com/s?src=11&timestamp=1755242708&ver=6175&signature=ee4Lokyi9XluNpq39gd5Ns*FIQH1UYHNGOcmD7wxcsHlqKDTG059UDTTqWSTrDdw3iWFuRK9CT67ihr1mr0wsP--NesJypxI7b2K4JnsDmh22aokrWmJjQBZRB8ecoxl&new=1"
#     t = time.time()
#     html_content = asyncio.run(fetch_page_content_async(url))
#     print(f"耗时：{time.time() - t}秒")