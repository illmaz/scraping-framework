import logging
from urllib.parse import urljoin
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# Maps the CSS class word to a number
# <p class="star-rating Three"> -> 3
RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


class BooksScraper(BaseScraper):
    """
    Scraper for books.toscrape.com
    Extracts title, price, rating, and availability from all 50 pages.
    Output: JSON file with ~1000 books.
    """

    def __init__(self):
        # "books" tells BaseScraper to load config/books.yaml
        super().__init__("books")

    def parse(self, soup) -> list[dict]:
        """
        Extract all books from one listing page.
        Returns a list of dicts, one per book.
        """
        books = []

        # select() finds ALL elements matching the CSS selector
        # Each article tag wraps one book on the page
        containers = soup.select("article.product_pod")

        if not containers:
            logger.warning("No book containers found on page")
            return []

        for article in containers:
            # --- Title ---
            # The visible <a> text is truncated e.g. "A Light in the ..."
            # The full title lives in the title= attribute
            title_tag = article.select_one("h3 > a")
            title = title_tag.get("title", "").strip() if title_tag else None

            # --- Price ---
            # Text content is e.g. "£12.99" - we keep the full string
            price_tag = article.select_one("p.price_color")
            price = price_tag.text.strip().encode('latin-1').decode('utf-8') if price_tag else None

            # --- Rating ---
            # Class list is ["star-rating", "Three"]
            # We find the word that isn't "star-rating" and map it to int
            rating_tag = article.select_one("p.star-rating")
            rating = None
            if rating_tag:
                classes = rating_tag.get("class", [])
                # classes is a list - find the rating word
                for cls in classes:
                    if cls in RATING_MAP:
                        rating = RATING_MAP[cls]
                        break

            # --- Availability ---
            availability_tag = article.select_one("p.availability")
            availability = availability_tag.text.strip() if availability_tag else None

            # --- Detail URL ---
            # href is relative e.g. "../../../a-light-in-the-attic_1000/index.html"
            # urljoin makes it absolute using the base_url from config
            detail_url = None
            if title_tag:
                href = title_tag.get("href", "")
                base_url = self.config.get("site", {}).get("base_url", "")
                detail_url = urljoin(base_url + "/catalogue/", href)

            books.append({
                "title": title,
                "price": price,
                "rating": rating,
                "availability": availability,
                "url": detail_url,
            })

        logger.info(f"Parsed {len(books)} books from page")
        return books

    def get_next_url(self, soup, current_url: str):
        """
        Find the 'next' pagination link and return its absolute URL.
        Returns None when we're on the last page.

        The next button HTML looks like:
        <li class="next"><a href="page-2.html">next</a></li>
        """
        next_li = soup.select_one("li.next")

        if not next_li:
            # No next button = we're on the last page
            return None

        next_a = next_li.select_one("a")
        if not next_a:
            return None

        href = next_a.get("href", "")

        # href is relative to the current page's directory
        # urljoin resolves it correctly against the current URL
        return urljoin(current_url, href)


if __name__ == "__main__":
    # Set up basic logging so we can see what's happening
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    scraper = BooksScraper()
    results = scraper.run()
    scraper.close()

    print(f"\nDone. Scraped {len(results)} books.")
    print("Sample:", results[0] if results else "no results")