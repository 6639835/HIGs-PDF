from urllib.parse import urljoin, urlparse
from typing import List

from playwright.sync_api import sync_playwright

HIG_URL = "https://developer.apple.com/design/human-interface-guidelines/"
BASE_URL = "https://developer.apple.com"


def get_article_urls() -> List[str]:
    """Return unique HIG article URLs, removing duplicates by path."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(HIG_URL, wait_until="networkidle", timeout=60_000)
            if not page.title().startswith("Human Interface Guidelines"):
                raise RuntimeError("Failed to load HIG main page")

            links = page.query_selector_all('a[href*="/design/human-interface-guidelines/"]')
            print(f"Initial links found: {len(links)}")

            articles = set()
            seen_paths = set()

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                full_url = urljoin(BASE_URL, href)
                path = urlparse(full_url).path.rstrip("/")

                if "/design/human-interface-guidelines/" in full_url and path not in seen_paths:
                    seen_paths.add(path)
                    articles.add(full_url)
                    print(f"Added unique URL: {full_url}")

            print(f"Found {len(articles)} unique articles after deduplication")
            return sorted(articles)
        finally:
            browser.close()
