from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    browser_headless: bool = True
    max_concurrency: int = 5

    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.68 Safari/537.36"
    viewport_width: int = 1280
    viewport_height: int = 720
    page_timeout: int = 5000  # 5s
    # 扩展阻止的资源类型
    blocked_resources: tuple = (
        "image",
        "media",
        "font",
        "stylesheet",
        "websocket",
        "manifest",
    )
    wait_until: str = "domcontentloaded"  # 'load', 'domcontentloaded', 'networkidle'
    launch_args: tuple = (
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-ipc-flooding-protection",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-component-extensions-with-background-pages",
        "--memory-pressure-off",
        "--max_old_space_size=4096",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-sync",
        "--disable-translate",
        "--disable-default-apps",
        "--disable-background-mode",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-logging",
        "--disable-permissions-api",
        "--disable-notifications",
        "--disable-speech-api",
        "--disable-file-system",
        "--disable-presentation-api",
        "--disable-print-preview",
        "--aggressive-cache-discard",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-domain-reliability",
        "--disable-component-update",
        "--disable-client-side-phishing-detection",
        "--memory-model=low",
        "--disable-blink-features=AutomationControlled",  # 减少检测
        "--disable-features=TranslateUI,VizDisplayCompositor,AudioServiceOutOfProcess",
    )
    searxng_url: str = "http://47.79.94.250:8080/search"
    allowed_domains: tuple = ("cn", "com", "org", "gov")
    ip_blacklist: tuple = ("bilibili.com", "youtube.com", "facebook.com", "douyin.com", "x.com", "huaweicloud", "zhihu")


settings = Settings()