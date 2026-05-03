import time
import random
import logging
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def check_robots(url: str, user_agent: str = "*") -> bool:
    """
    Returns True if we are allowed to scrape this URL.
    Fetches and parses the site's robots.txt automatically.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        rp.read()
        allowed = rp.can_fetch(user_agent, url)
        if not allowed:
            logger.warning(f"robots.txt disallows scraping: {url}")
        return allowed
    except Exception as e:
        logger.warning(f"Could not read robots.txt at {robots_url}: {e}")
        return True


class RateLimiter:
    """
    Enforces a minimum delay between requests.
    Call wait() before every HTTP request.

    Usage:
        limiter = RateLimiter(delay=2.0, jitter=0.5)
        limiter.wait()
        response = requests.get(url)
    """

    def __init__(self, delay: float = 2.0, jitter: float = 0.5):
        self.delay = delay
        self.jitter = jitter
        self._last_request: float = 0.0

    def wait(self):
        elapsed = time.time() - self._last_request
        sleep_time = self.delay + random.uniform(0, self.jitter)

        if elapsed < sleep_time:
            pause = sleep_time - elapsed
            logger.debug(f"Rate limiter sleeping {pause:.2f}s")
            time.sleep(pause)

        self._last_request = time.time()