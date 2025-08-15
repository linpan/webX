from urllib.parse import urlparse

from fake_useragent import UserAgent

from webX.config import settings

user_agent = UserAgent()
random_ua = user_agent.random


def check_allow_domain(url: str) -> bool:
    domain = urlparse(url).netloc
    last_part = domain.split(".")[-1]
    if last_part in settings.allowed_domains:
        return True
    return False


if __name__ == "__main__":
    print(
        check_allow_domain(
            "https://www.zaobao.com/realtime/china/story20250815-7357116"
        )
    )
