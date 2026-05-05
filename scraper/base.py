import logging
import yaml
from pathlib import Path
from typing import Optional

from scraper.utils import check_robots, RateLimiter
from scraper.engine import EngineRouter
from scraper.output import OutputManager

logger = logging.getLogger(__name__)


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge two dicts. Override values win on conflict.
    Unlike dict.update(), this merges nested dicts instead of replacing them.

    Example:
        base     = {'http': {'timeout': 30, 'retries': 3}}
        override = {'http': {'timeout': 10}}
        result   = {'http': {'timeout': 10, 'retries': 3}}  # retries preserved
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Both values are dicts - recurse to merge them
            result[key] = deep_merge(result[key], value)
        else:
            # Override wins - simple replacement
            result[key] = value

    return result


def load_config(site_name: str) -> dict:
    """
    Load and merge global settings with site-specific config.
    Site config values override global settings.

    Args:
        site_name: matches the YAML filename e.g. "books" -> config/books.yaml
    """
    config_dir = Path("config")

    # Load global settings first as the base
    global_path = config_dir / "settings.yaml"
    with open(global_path, "r") as f:
        global_config = yaml.safe_load(f)

    # Load site-specific config
    site_path = config_dir / f"{site_name}.yaml"
    with open(site_path, "r") as f:
        site_config = yaml.safe_load(f)

    # Merge: site values override global values
    # Any key in site_config replaces the same key in global_config
    merged = deep_merge(global_config, site_config)

    # Apply the site's overrides section if it exists
    # This lets sites override specific http settings cleanly
    overrides = site_config.get("overrides", {})
    if overrides:
        merged = deep_merge(merged, {"http": overrides})

    logger.debug(f"Loaded config for site: {site_name}")
    return merged


class BaseScraper:
    """
    Base class for all scrapers in the framework.
    Implements the Template Method pattern:
    - run() defines the fixed sequence of steps
    - parse() and get_next_url() are overridden by each site scraper

    Usage:
        class BooksScraper(BaseScraper):
            def parse(self, soup):
                # extract data from BeautifulSoup object
                return [{'title': ..., 'price': ...}]

            def get_next_url(self, soup, current_url):
                # return next page URL or None if done
                return next_url
    """

    def __init__(self, site_name: str):
        # site_name matches the YAML config filename
        self.site_name = site_name

        # Load and merge configs
        self.config = load_config(site_name)

        # Pull frequently used config sections into shortcuts
        self.site_config = self.config.get("site", {})
        self.pagination_config = self.config.get("pagination", {})
        self.http_config = self.config.get("http", {})

        # Instantiate the three core tools
        # RateLimiter: enforces delay between requests
        self.rate_limiter = RateLimiter(
            delay=self.http_config.get("request_delay", 2.0),
            jitter=self.http_config.get("jitter", 0.5),
        )

        # EngineRouter: returns the right engine (static or js_heavy)
        self.engine = EngineRouter(self.config).get_engine()

        # OutputManager: writes results to JSON, CSV, or PostgreSQL
        self.output_manager = OutputManager(self.config)

        # Storage for all scraped records across all pages
        self.results = []

        logger.info(f"Initialised {self.__class__.__name__} for site: {site_name}")

    def check_permissions(self, url: str):
        """
        Check robots.txt before scraping.
        Raises PermissionError if scraping is disallowed.
        Hard stop - never scrape a site that says no.
        """
        user_agent = self.http_config.get("user_agent", "*")
        allowed = check_robots(url, user_agent)

        if not allowed:
            raise PermissionError(
                f"robots.txt disallows scraping {url}. "
                f"Aborting to respect site rules."
            )

        logger.info(f"robots.txt check passed for {url}")

    def run(self):
        """
        Main entry point. Runs the full scrape job.
        This is the Template Method - sequence is fixed here.
        Subclasses only override parse() and get_next_url().
        """
        start_url = self.pagination_config.get("start_url")
        max_pages = self.pagination_config.get("max_pages", 10)

        if not start_url:
            raise ValueError("No start_url defined in pagination config")

        # Step 1: check we're allowed to scrape this site
        self.check_permissions(start_url)

        current_url = start_url
        page_num = 0

        logger.info(f"Starting scrape of {self.site_config.get('name')} from {start_url}")

        while current_url and page_num < max_pages:
            page_num += 1
            logger.info(f"Scraping page {page_num}: {current_url}")

            # Step 2: enforce rate limit before every request
            self.rate_limiter.wait()

            # Step 3: fetch the page using the configured engine
            # Returns a BeautifulSoup object ready to parse
            soup = self.engine.fetch(current_url)

            # Step 4: parse the page - implemented by each site scraper
            # Returns a list of dicts, one per item on the page
            page_results = self.parse(soup)

            if not page_results:
                logger.info("No results on this page - stopping pagination")
                break

            # Accumulate results across all pages
            self.results.extend(page_results)
            logger.info(f"Page {page_num}: {len(page_results)} items. Total: {len(self.results)}")

            # Step 5: get next page URL - implemented by each site scraper
            # Returns None when there are no more pages
            current_url = self.get_next_url(soup, current_url)

        # Step 6: save everything we collected
        logger.info(f"Scrape complete. Saving {len(self.results)} total records.")
        self.output_manager.save(self.results)

        return self.results

    def parse(self, soup) -> list[dict]:
        """
        Extract data from a parsed page.
        MUST be overridden by every site scraper.

        Args:
            soup: BeautifulSoup object of the fetched page

        Returns:
            list of dicts, one dict per scraped item
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement parse(). "
            f"This method extracts data from each page."
        )

    def get_next_url(self, soup, current_url: str) -> Optional[str]:
        """
        Return the URL of the next page, or None if done.
        MUST be overridden by every site scraper.

        Args:
            soup: BeautifulSoup object of the current page
            current_url: URL of the page just scraped

        Returns:
            str URL of next page, or None to stop pagination
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_next_url(). "
            f"Return None to stop pagination."
        )

    def close(self):
        """Clean up engine resources (closes HTTP session or browser)."""
        if hasattr(self.engine, 'close'):
            self.engine.close()
        logger.info(f"Closed {self.__class__.__name__}")