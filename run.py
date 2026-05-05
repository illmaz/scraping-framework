import argparse
import logging
import sys


def setup_logging(verbose: bool):
    """
    Configure logging for the entire framework.
    verbose=True shows DEBUG messages (every detail).
    verbose=False shows INFO and above (clean summary).
    """
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            # Print to terminal
            logging.StreamHandler(sys.stdout),
        ]
    )


def run_books(max_pages: int = 50):
    """Run the books.toscrape.com scraper."""
    from sites.books import BooksScraper
    scraper = BooksScraper()
    if max_pages != 50:
        scraper.pagination_config['max_pages'] = max_pages
    results = scraper.run()
    scraper.close()
    return results


def run_asos(query: str = "black shirt", max_pages: int = 2):
    """Run the ASOS product scraper."""
    from sites.asos import search_products, save_results
    products = search_products(query=query, max_pages=max_pages)
    save_results(products, query)
    return products


def run_rightmove(max_pages: int = 3):
    """Run the Rightmove London property scraper."""
    from sites.rightmove import scrape, save_csv
    properties = scrape(max_pages=max_pages)
    save_csv(properties)
    return properties


# Map site name strings to their runner functions
# Adding a new scraper = add one line here
SCRAPERS = {
    'books': run_books,
    'asos': run_asos,
    'rightmove': run_rightmove,
}


def main():
    # argparse reads sys.argv and parses named arguments
    # This is Python's built-in CLI argument library - no extra install needed
    parser = argparse.ArgumentParser(
        description="Reusable web scraping framework",
        epilog="Example: python3 run.py --site books"
    )

    # --site is a required argument
    # choices= restricts input to only valid site names
    # If you pass --site invalid it prints an error automatically
    parser.add_argument(
        "--site",
        required=True,
        choices=list(SCRAPERS.keys()),
        help=f"Site to scrape. Options: {', '.join(SCRAPERS.keys())}"
    )

    # --verbose is an optional flag
    # store_true means: if --verbose is present, args.verbose = True
    # if --verbose is absent, args.verbose = False
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed debug logging"
    )

    # --pages lets you override the default number of pages
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Number of pages to scrape (overrides default)"
    )

    # --query is used by ASOS scraper to set the search term
    parser.add_argument(
        "--query",
        type=str,
        default="black shirt",
        help="Search query (used by ASOS scraper)"
    )

    # Parse the arguments from the terminal
    args = parser.parse_args()

    # Set up logging based on --verbose flag
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)
    logger.info(f"Starting scraper: {args.site}")

    # Look up and call the right runner function
    runner = SCRAPERS[args.site]

    # Pass optional arguments if provided
    # Each runner accepts different kwargs so we build them dynamically
    kwargs = {}
    if args.pages is not None:
        kwargs['max_pages'] = args.pages
    if args.site == 'asos':
        kwargs['query'] = args.query

    results = runner(**kwargs)
    logger.info(f"Done. Scraped {len(results)} records.")


if __name__ == "__main__":
    main()