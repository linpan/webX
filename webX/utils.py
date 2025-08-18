from urllib.parse import urlparse
from typing import Optional

from webX.config import settings


def _extract_hostname(url: str) -> Optional[str]:
    """
    从 URL 中解析出 hostname（不包含端口）。
    返回 None 表示解析失败或无效 URL。
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname:
            return hostname.lower()
    except Exception:
        pass
    return None


def check_allow_domain(url: str) -> bool:
    """
    判断给定 URL 是否允许抓取：
    - 如果 URL 无法解析为 hostname，返回 False。
    - 若 hostname 包含在黑名单条目（settings.ip_blacklist）中，则返回 False。
      黑名单匹配使用子串匹配（例如 'youtube.com' 能匹配 'www.youtube.com'）。
    - 若 hostname 的顶级后缀（最后一段）在 settings.allowed_domains 中，返回 True。
      例如 hostname 'www.example.com' -> 后缀 'com'。
    - 其它情况返回 False。
    """
    hostname = _extract_hostname(url)
    if not hostname:
        return False
    if url.endswith(".pdf") or url.endswith(".docx") or url.endswith(".xlsx"):
        return False
    # 黑名单：如果黑名单中的任一条是 hostname 的后缀或子串，则拒绝
    for blocked in settings.ip_blacklist:
        blocked_normalized = blocked.lower()
        if (
            blocked_normalized == hostname
            or hostname.endswith("." + blocked_normalized)
            or blocked_normalized in hostname
        ):
            return False

    # 允许的顶级后缀判断
    parts = hostname.split(".")
    if not parts:
        return False
    tld = parts[-1]
    if tld in settings.allowed_domains:
        return True

    return False


if __name__ == "__main__":
    print(check_allow_domain("https://air.tsinghua.edu.cn/__local/A/F3/79/CC9A0C81875F8B35A4733E36A57_BD4E1211_324F1.pdf"))