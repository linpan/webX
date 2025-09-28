import asyncio
import time

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    Page,
    BrowserContext,
    ViewportSize,
)
from typing import Optional, Callable, Any
from loguru import logger

from webX.config import Settings

settings = Settings()


class PlaywrightManager:
    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._started = False
        self._start_lock = asyncio.Lock()

    async def start(self):
        # 启动过程的原子性
        async with self._start_lock:
            if self._started and self._browser is not None:
                return

            try:
                # 重置状态
                self._started = False

                logger.info("Starting Playwright...")
                self._playwright = await async_playwright().start()

                launch_kwargs = {
                    "headless": settings.browser_headless,
                    "args": list(settings.launch_args),
                    # 新增性能优化选项
                    "ignore_default_args": ["--enable-blink-features=IdleDetection"],
                }

                logger.info(f"Launching browser with kwargs: {launch_kwargs}")
                self._browser = await self._playwright.chromium.launch(**launch_kwargs)

                self._started = True

                logger.info("Playwright started successfully")

            except Exception as e:
                logger.error(f"Failed to start Playwright: {e}")
                await self._cleanup_partial_init()
                raise

    async def _create_new_context(self) -> BrowserContext:
        """创建新的 browser context"""
        viewport_size = ViewportSize(width=1280, height=720)
        context = await self._browser.new_context(
            user_agent=settings.user_agent,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
            permissions=[],
            device_scale_factor=1.0,
            viewport=viewport_size,
            locale="zh-CN",
            # 新增优化选项
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            # 禁用一些不必要的功能来提升性能
            color_scheme="light",
            reduced_motion="reduce",
        )

        # 设置页面级别的超时时间
        context.set_default_timeout(45000)  # 30秒超时
        context.set_default_navigation_timeout(45000)  # 10秒导航超时

        return context

    async def _cleanup_partial_init(self):
        """清理部分初始化的状态"""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception as e:
            logger.error(f"Error closing browser during cleanup: {e}")

        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.error(f"Error stopping playwright during cleanup: {e}")

        self._started = False

    async def stop(self):
        await self._cleanup_partial_init()
        logger.info("Playwright stopped")

    async def _handle_route(self, route, request):
        """处理资源拦截的路由函数 - 必须是异步函数"""
        resource_type = request.resource_type
        if resource_type in settings.blocked_resources:
            await route.abort()
        else:
            await route.continue_()

    async def run_in_page(self, func: Callable[[Page], Any], timeout: Optional[float] = 20) -> Any:
        """
        创建新的 context 和 page，运行 func，然后清理资源。
        每次调用都会创建新的 context 和 page，用完即销毁。
        """
        # 确保 Playwright 已启动且浏览器实例有效
        if not self._started or self._browser is None:
            logger.warning("Playwright not properly initialized, starting now...")
            await self.start()

        # 双重检查确保启动成功
        if self._browser is None:
            raise RuntimeError("Failed to initialize Playwright browser")

        async with self._semaphore:  # 控制并发数
            context: BrowserContext | None = None
            page: Page | None = None
            start_ts = time.time()
            logger.debug("Creating new context and page")
            try:
                # 每次都创建新的 context
                context = await self._create_new_context()
                page = await context.new_page()

                # 优化页面性能
                await page.add_init_script("""
                    // 禁用一些可能影响性能的功能
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    window.alert = () => {};
                    window.confirm = () => true;
                    window.prompt = () => null;
                """)

                # 应用资源拦截
                await page.route("**/*", self._handle_route)

                # 设置更快的页面加载策略
                await page.set_extra_http_headers(
                    {
                        "Accept-Encoding": "gzip, deflate, br",
                        "Cache-Control": "no-cache",
                    }
                )

                coro_page = func(page)
                logger.debug(f"context duration: {time.time() - start_ts:.2f}s")
                return await asyncio.wait_for(coro_page, timeout=timeout)
            finally:
                # 清理资源：每次用完就关闭 page 和 context
                if page:
                    try:
                        await page.close()
                    except Exception as e:
                        logger.error(f"Error closing page: {e}")

                if context:
                    try:
                        await context.close()
                    except Exception as e:
                        logger.error(f"Error closing context: {e}")


playwright_manager = PlaywrightManager()
