import re
import json
import time
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'referer': 'https://www.rightmove.co.uk/',
}

# London for-sale listings - 24 properties per page
# Pagination uses ?index=24, ?index=48 etc
BASE_URL = 'https://www.rightmove.co.uk/property-for-sale/London-87490.html'


def extract_next_data(html: str) -> dict:
    """
    Extract the __NEXT_DATA__ JSON blob from the page HTML.
    Rightmove embeds all property data in a <script> tag as JSON.
    No BeautifulSoup needed - regex is faster for a single known tag.
    """
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ in page HTML")

    return json.loads(match.group(1))


def parse_properties(data: dict) -> list[dict]:
    """
    Navigate the JSON structure to the properties list
    and extract only the fields we care about.
    """
    properties_raw = data['props']['pageProps']['searchResults']['properties']

    properties = []
    for p in properties_raw:
        properties.append({
            'id': p.get('id'),
            'address': p.get('displayAddress'),
            'property_type': p.get('propertySubType'),
            'bedrooms': p.get('bedrooms'),
            'bathrooms': p.get('bathrooms'),
            'price': p.get('price', {}).get('amount'),
            'currency': p.get('price', {}).get('currencyCode'),
            'tenure': p.get('tenure', {}).get('tenureType'),
            'agent': p.get('customer', {}).get('brandTradingName'),
            'agent_phone': p.get('customer', {}).get('contactTelephone'),
            'added_date': p.get('addedOrReduced'),
            'latitude': p.get('location', {}).get('latitude'),
            'longitude': p.get('location', {}).get('longitude'),
            'url': f"https://www.rightmove.co.uk{p.get('propertyUrl', '')}",
            'image_url': p.get('propertyImages', {}).get('mainImageSrc'),
        })

    return properties


def scrape(max_pages: int = 3) -> list[dict]:
    """
    Scrape Rightmove London for-sale listings.
    Paginates by incrementing the index parameter by 24 per page.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    all_properties = []

    for page in range(max_pages):
        index = page * 24
        url = f"{BASE_URL}?index={index}"

        logger.info(f"Scraping page {page + 1} (index={index})")
        print(f"Fetching page {page + 1}...")

        response = session.get(url)
        response.raise_for_status()

        data = extract_next_data(response.text)
        properties = parse_properties(data)

        if not properties:
            print("No more properties found.")
            break

        all_properties.extend(properties)
        print(f"  Got {len(properties)} properties. Total: {len(all_properties)}")

        # Polite delay between pages
        if page < max_pages - 1:
            time.sleep(2)

    session.close()
    return all_properties


def save_csv(properties: list[dict]) -> str:
    """
    Save properties to a timestamped CSV using pandas.
    Demonstrates: list of dicts -> DataFrame -> typed CSV.
    """
    df = pd.DataFrame(properties)

    # Cast numeric columns to proper types
    df['price'] = pd.to_numeric(df['price'], errors='coerce').astype('Int64')
    df['bedrooms'] = pd.to_numeric(df['bedrooms'], errors='coerce').astype('Int64')
    df['bathrooms'] = pd.to_numeric(df['bathrooms'], errors='coerce').astype('Int64')

    Path('output').mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = f"output/rightmove_london_{timestamp}.csv"

    df.to_csv(filepath, index=False, encoding='utf-8')

    print(f"\nSaved {len(df)} properties to {filepath}")
    print(f"Price range: £{df['price'].min():,} - £{df['price'].max():,}")
    print(f"Avg bedrooms: {df['bedrooms'].mean():.1f}")

    return filepath


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    properties = scrape(max_pages=3)
    save_csv(properties)

    if properties:
        print('\nSample property:')
        print(json.dumps(properties[0], indent=2))