import asyncio
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

        # Context 连接池相关
        self._context_pool: list[BrowserContext] = []
        self._pool_lock = asyncio.Lock()
        self._max_pool_size = min(settings.max_concurrency * 2, 10)  # 池大小为并发数的2倍，最多10个
        self._context_usage_count: dict[BrowserContext, int] = {}  # 跟踪每个context的使用次数
        self._max_context_reuse = 2  # 每个context最多复用20次后重建

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

                # 初始化 context 池
                await self._initialize_context_pool()

                logger.info("Playwright started successfully")

            except Exception as e:
                logger.error(f"Failed to start Playwright: {e}")
                await self._cleanup_partial_init()
                raise

    async def _initialize_context_pool(self):
        """初始化 context 连接池"""
        try:
            initial_pool_size = min(10, self._max_pool_size)  # 初始创建3个context
            for _ in range(initial_pool_size):
                context = await self._create_new_context()
                self._context_pool.append(context)
                self._context_usage_count[context] = 0
            logger.info(f"Context pool initialized with {len(self._context_pool)} contexts")
        except Exception as e:
            logger.error(f"Failed to initialize context pool: {e}")
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
        )
        return context

    async def _get_context_from_pool(self) -> BrowserContext:
        """从连接池获取一个可用的 context"""
        async with self._pool_lock:
            # 尝试从池中获取可用的context
            while self._context_pool:
                context = self._context_pool.pop(0)

                # 检查context是否还有效且没有超过复用次数
                try:
                    if (
                        context not in self._context_usage_count
                        or self._context_usage_count[context] < self._max_context_reuse
                    ):
                        return context
                    else:
                        # 超过复用次数，关闭并创建新的
                        await context.close()
                        del self._context_usage_count[context]
                        logger.debug("Context reached max reuse limit, closed")
                except Exception:
                    # context 无效，忽略并继续
                    logger.debug("Invalid context found in pool, skipping")
                    if context in self._context_usage_count:
                        del self._context_usage_count[context]

            # 池为空或没有可用context，创建new context
            context = await self._create_new_context()
            self._context_usage_count[context] = 0
            return context

    async def _return_context_to_pool(self, context: BrowserContext):
        """将 context 返还到连接池"""
        async with self._pool_lock:
            try:
                # 增加使用计数
                if context in self._context_usage_count:
                    self._context_usage_count[context] += 1

                # 检查池大小限制
                if len(self._context_pool) < self._max_pool_size:
                    self._context_pool.append(context)
                    logger.debug(f"Context returned to pool, pool size: {len(self._context_pool)}")
                else:
                    # 池已满，关闭context
                    await context.close()
                    if context in self._context_usage_count:
                        del self._context_usage_count[context]
                    logger.debug("Pool full, context closed")
            except Exception as e:
                logger.error(f"Error returning context to pool: {e}")
                # 发生错误时确保清理
                if context in self._context_usage_count:
                    del self._context_usage_count[context]

    async def _cleanup_partial_init(self):
        """清理部分初始化的状态"""
        # 清理 context 池
        await self._cleanup_context_pool()

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

    async def _cleanup_context_pool(self):
        """清理 context 连接池"""
        async with self._pool_lock:
            for context in self._context_pool[:]:
                try:
                    await context.close()
                except Exception as e:
                    logger.error(f"Error closing context during cleanup: {e}")

            self._context_pool.clear()
            self._context_usage_count.clear()
            logger.debug("Context pool cleaned up")

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

    async def _close_page_safe(self, page: Page):
        """安全地关闭页面，并记录异常"""
        try:
            await page.close()
        except Exception:
            logger.exception("closing page failed")

    async def _release_context(self, context: BrowserContext, from_pool: bool):
        """将 context 返还到池中或关闭它"""
        if from_pool:
            try:
                await self._return_context_to_pool(context)
            except Exception:
                logger.exception("returning context to pool failed")
        else:
            try:
                await context.close()
            except Exception:
                logger.exception("closing context failed")

    async def run_in_page(self, func: Callable[[Page], Any], timeout: Optional[float] = 30) -> Any:
        """
        Acquire semaphore, create context+page, run func(page), ensure cleanup.
        func 可以是 async 函数。
        """
        # 确保 Playwright 已启动且浏览器实例有效
        if not self._started or self._browser is None:
            logger.warning("Playwright not properly initialized, starting now...")
            await self.start()

        # 双重检查确保启动成功
        if self._browser is None:
            raise RuntimeError("Failed to initialize Playwright browser")

        async with self._semaphore:  # 使用 async with 确保正确释放
            context: BrowserContext | None = None
            page: Page | None = None
            context_from_pool = False

            try:
                # 从连接池获取 context
                context = await self._get_context_from_pool()
                context_from_pool = True

                page = await context.new_page()

                # 设置页面超时和视口
                page.set_default_timeout(settings.page_timeout)
                page.set_default_navigation_timeout(settings.page_timeout)

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
                return await asyncio.wait_for(coro_page, timeout=timeout)
            finally:
                if page:
                    await self._close_page_safe(page)
                if context:
                    await self._release_context(context, context_from_pool)


playwright_manager = PlaywrightManager()