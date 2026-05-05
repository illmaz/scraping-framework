import time
import logging
import asyncio

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class StaticEngine:
    """
    Fetches static HTML pages using requests + BeautifulSoup.
    Use for pages where all content is in the raw HTML source.
    Fast and lightweight - no browser required.
    """

    def __init__(self, config: dict):
        # Pull http settings from config, with sensible defaults
        http = config.get("http", {})
        self.timeout = http.get("request_timeout", 30)
        self.max_retries = http.get("max_retries", 3)
        self.backoff = http.get("retry_backoff", 2.0)
        self.user_agent = http.get(
            "user_agent",
            "PortfolioScraper/1.0 (+https://github.com/illmaz/scraping-framework)"
        )

        # requests.Session reuses TCP connections across requests
        # Faster than a new connection every time
        # Also persists headers automatically on every request
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch(self, url: str) -> BeautifulSoup:
        """
        Fetch a URL and return a parsed BeautifulSoup object.
        Retries on failure with exponential backoff.
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout)

                # Raises an exception for 4xx and 5xx responses
                # Better than silently parsing an error page as real data
                response.raise_for_status()

                # Parse the HTML with Python's built-in html.parser
                # No extra dependencies needed
                return BeautifulSoup(response.text, "html.parser")

            except requests.RequestException as e:
                # Calculate wait time: 2s, 4s, 8s for attempts 0, 1, 2
                wait = self.backoff * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying in {wait}s")

                # Don't sleep after the last attempt - just let it fall through
                if attempt < self.max_retries - 1:
                    time.sleep(wait)

        # All retries exhausted - raise so the scraper can handle it
        raise Exception(f"Failed to fetch {url} after {self.max_retries} attempts")

    def close(self):
        # Always close the session when done to release the TCP connection
        self.session.close()


class PlaywrightEngine:
    """
    Fetches JS-rendered pages using a real Chromium browser.
    Use when content is loaded by JavaScript after page load.
    Slower than StaticEngine - only use when necessary.
    """

    def __init__(self, config: dict):
        pw_config = config.get("playwright", {})
        http_config = config.get("http", {})

        self.headless = pw_config.get("headless", True)
        self.browser_type = pw_config.get("browser", "chromium")

        # CSS selector to wait for before extracting HTML
        # Ensures JS has finished rendering before we read the DOM
        self.wait_for_selector = pw_config.get("wait_for_selector", None)

        # Extra buffer after selector appears - for slow JS frameworks
        self.wait_after_ms = pw_config.get("wait_after_load_ms", 500)

        self.user_agent = http_config.get(
            "user_agent",
            "PortfolioScraper/1.0 (+https://github.com/illmaz/scraping-framework)"
        )

    def fetch(self, url: str) -> BeautifulSoup:
        """
        Launch a browser, navigate to the URL, wait for JS to render,
        return a BeautifulSoup object of the fully rendered page.

        asyncio.run() lets us call async Playwright from sync code.
        """
        html = asyncio.run(self._fetch_async(url))
        return BeautifulSoup(html, "html.parser")

    async def _fetch_async(self, url: str) -> str:
        """
        The actual async Playwright logic.
        async_playwright() is a context manager that starts and
        stops the browser process automatically.
        """
        async with async_playwright() as pw:
            # Launch the browser - chromium, firefox, or webkit
            browser = await pw.chromium.launch(headless=self.headless)

            # A context is like a fresh browser profile
            # Setting user_agent here applies it to all pages in this context
            context = await browser.new_context(user_agent=self.user_agent)

            # A page is a single browser tab
            page = await context.new_page()

            # Navigate to the URL and wait for the network to settle
            # "networkidle" means no network requests for 500ms
            await page.goto(url, wait_until="networkidle")

            # If configured, wait for a specific element to appear in the DOM
            # This is how we know the JS has finished rendering our data
            if self.wait_for_selector:
                await page.wait_for_selector(self.wait_for_selector)

            # Optional extra wait for slow-loading elements
            if self.wait_after_ms:
                await page.wait_for_timeout(self.wait_after_ms)

            # Get the fully rendered HTML from the browser
            html = await page.content()

            # Clean up - close page, context, and browser process
            await page.close()
            await context.close()
            await browser.close()

            return html


class EngineRouter:
    """
    Reads the 'engine' key from site config and returns
    the correct engine instance.

    Usage:
        router = EngineRouter(config)
        engine = router.get_engine()
        soup = engine.fetch(url)
    """

    def __init__(self, config: dict):
        self.config = config

    def get_engine(self):
        engine_type = self.config.get("site", {}).get("engine", "static")

        if engine_type == "static":
            logger.debug("Using StaticEngine (requests + BeautifulSoup)")
            return StaticEngine(self.config)
        elif engine_type == "js_heavy":
            logger.debug("Using PlaywrightEngine (Chromium)")
            return PlaywrightEngine(self.config)
        else:
            raise ValueError(f"Unknown engine type: '{engine_type}'. Use 'static' or 'js_heavy'.")