# Scraping Framework

A modular, configuration-driven web scraping framework built as a portfolio project. Supports both static and JavaScript-heavy sites, multiple output formats, and ethical scraping practices out of the box.

## Features

- **Template Method pattern** — extend `BaseScraper` and override two methods to add a new site
- **Config-driven** — define selectors, pagination, and output format in YAML; minimal Python boilerplate
- **Two rendering engines** — `requests` + BeautifulSoup for static pages, Playwright (headless Chromium) for JS-heavy sites
- **Three output formats** — JSON, CSV, PostgreSQL
- **Ethical defaults** — robots.txt checking, rate limiting with jitter, exponential retry backoff

## Quickstart

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 run.py --site books
```

## CLI

```
python3 run.py --site {books|asos|rightmove} [--pages N] [--query "search term"] [--verbose]
```

| Flag | Description |
|---|---|
| `--site` | Site to scrape — `books`, `asos`, or `rightmove` (required) |
| `--pages` | Override default max pages |
| `--query` | Search term (ASOS only, default: `"black shirt"`) |
| `--verbose` | Enable DEBUG logging |

**Examples:**

```bash
python3 run.py --site books --pages 5 --verbose
python3 run.py --site asos --query "white sneakers" --pages 3
python3 run.py --site rightmove --pages 2
```

## Scrapers

| Site | Engine | Extracts | Output |
|---|---|---|---|
| [books.toscrape.com](http://books.toscrape.com) | Static | title, price, rating, availability | JSON + CSV |
| [asos.com](https://www.asos.com) | API (JSON) | name, brand, price, colour, image URL | JSON |
| [rightmove.co.uk](https://www.rightmove.co.uk) | `__NEXT_DATA__` JSON | address, price, bedrooms, agent, lat/lon | CSV |

Output files are written to `output/` with a timestamp suffix (e.g. `books_20260505.json`).

## Configuration

Global HTTP defaults live in `config/settings.yaml`. Each site has its own `config/{site}.yaml` that deep-merges on top of the global config.

```yaml
# config/settings.yaml (excerpt)
http:
  request_delay: 2.0      # seconds between requests
  jitter: 0.5             # random extra delay
  max_retries: 3
  retry_backoff: 2.0      # exponential: 2s, 4s, 8s
  request_timeout: 30
```

Site configs define selectors, pagination strategy, output format, and optional per-site HTTP overrides.

## Project Structure

```
scraping-framework/
├── run.py                  # CLI entry point
├── requirements.txt
├── scraper/
│   ├── base.py             # BaseScraper + config loader
│   ├── engine.py           # StaticEngine, PlaywrightEngine, EngineRouter
│   ├── output.py           # OutputManager, JsonWriter, CsvWriter, PostgresWriter
│   └── utils.py            # check_robots(), RateLimiter
├── sites/
│   ├── books.py
│   ├── asos.py
│   └── rightmove.py
├── config/
│   ├── settings.yaml       # Global defaults
│   ├── books.yaml
│   ├── asos.yaml
│   └── rightmove.yaml
├── output/                 # Scraped data (gitignored)
└── logs/                   # Log files (gitignored)
```

## Adding a New Scraper

**1. Create `sites/mysite.py`:**

```python
from scraper.base import BaseScraper

class MySiteScraper(BaseScraper):
    def __init__(self):
        super().__init__("mysite")

    def parse(self, soup):
        # Return a list of dicts
        return [{"field": soup.select_one(".field").text}]

    def get_next_url(self, soup, current_url):
        # Return next page URL, or None to stop
        next_btn = soup.select_one("a.next")
        return next_btn["href"] if next_btn else None
```

**2. Create `config/mysite.yaml`:**

```yaml
site:
  name: "mysite"
  base_url: "https://example.com"
  engine: "static"           # or "js_heavy" for Playwright

pagination:
  start_url: "https://example.com/page/1"
  max_pages: 10

output:
  filename: "mysite"
  formats: [json, csv]

overrides:
  request_delay: 1.5
```

**3. Register in `run.py`:**

```python
def run_mysite(max_pages=10):
    from sites.mysite import MySiteScraper
    scraper = MySiteScraper()
    if max_pages:
        scraper.pagination_config["max_pages"] = max_pages
    results = scraper.run()
    scraper.close()
    return results

SCRAPERS = {
    ...
    "mysite": run_mysite,
}
```

## PostgreSQL Output

Add a `DATABASE_URL` to `.env`:

```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

Then set `formats: [postgres]` in the site's YAML config. Rows are appended to a table named after the `output.filename` key.

## Ethical Scraping

- robots.txt is checked before scraping begins
- 2s default delay between requests with 0–0.5s random jitter
- Exponential backoff on failed requests (2s → 4s → 8s)
- `User-Agent: PortfolioScraper/1.0` header on all requests
