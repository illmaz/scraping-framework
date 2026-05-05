import requests
import json
import time
from pathlib import Path
from datetime import datetime

# Only the headers ASOS actually needs - stripped down from the full set
HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'asos-c-name': '@asosteam/asos-web-product-listing-page',
    'asos-c-plat': 'web',
    'asos-c-ver': '1.2.0-510-810f62fd',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'referer': 'https://www.asos.com/search/',
}

# Only the cookies that control store/currency preferences
COOKIES = {
    'geocountry': 'TR',
    'browseCountry': 'TR',
    'browseCurrency': 'USD',
    'browseLanguage': 'en-GB',
    'browseSizeSchema': 'UK',
    'storeCode': 'ROW',
    'keyStoreDataversion': 'qx71qrg-45',
}

BASE_URL = 'https://www.asos.com/api/product/search/v2/'
LIMIT = 72  # items per page - ASOS max


def search_products(query: str, max_pages: int = 3) -> list[dict]:
    """
    Search ASOS for products and return clean list of dicts.
    Paginates automatically by incrementing offset.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(COOKIES)

    all_products = []
    offset = 0

    for page in range(max_pages):
        print(f"Fetching page {page + 1} (offset {offset})...")

        params = {
            'q': query,
            'offset': offset,
            'limit': LIMIT,
            'includeNonPurchasableTypes': 'restocking',
            'store': 'ROW',
            'lang': 'en-GB',
            'currency': 'USD',
            'rowlength': '3',
            'channel': 'desktop-web',
            'country': 'TR',
            'keyStoreDataversion': 'qx71qrg-45',
        }

        response = session.get(BASE_URL, params=params)
        response.raise_for_status()

        data = response.json()
        products = data.get('products', [])

        if not products:
            print("No more products found - stopping.")
            break

        # Extract only the fields we care about
        for p in products:
            all_products.append({
                'id': p.get('id'),
                'name': p.get('name'),
                'brand': p.get('brandName'),
                'price': p.get('price', {}).get('current', {}).get('value'),
                'currency': p.get('price', {}).get('currency'),
                'colour': p.get('colour'),
                'url': f"https://www.asos.com/{p.get('url', '')}",
                'image_url': f"https://{p.get('imageUrl', '')}",
                'is_marked_down': p.get('price', {}).get('isMarkedDown'),
            })

        print(f"  Got {len(products)} products. Total so far: {len(all_products)}")
        offset += LIMIT

        # Be polite - wait between pages
        if page < max_pages - 1:
            time.sleep(2)

    session.close()
    return all_products


def save_results(products: list[dict], query: str):
    """Save results to JSON file."""
    Path('output').mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"output/asos_{query.replace(' ', '_')}_{timestamp}.json"

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(products)} products to {filename}")
    return filename


if __name__ == '__main__':
    query = 'black shirt'
    print(f"Searching ASOS for: '{query}'")

    products = search_products(query, max_pages=2)
    save_results(products, query)

    # Preview first result
    if products:
        print("\nFirst result:")
        print(json.dumps(products[0], indent=2))