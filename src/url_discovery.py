from urllib.parse import urljoin, urlparse
from typing import List, Set
import time

from playwright.sync_api import sync_playwright, Page

BASE_URL = "https://developer.apple.com"
DEFAULT_START_URL = "https://developer.apple.com/design/"
DEFAULT_URL_PATTERN = "/design/"


def _is_valid_design_url(url: str, url_pattern: str) -> bool:
    """Check if URL is a valid design page to include."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    # Must contain the URL pattern
    if url_pattern not in path:
        return False

    # Exclude certain patterns
    excluded_patterns = [
        "/search", "/downloads", "/download/",
        "/forums/", "/bug-reporting/",
        "/account/", "/contact/",
        "#",  # Anchor-only links
        ".pdf", ".zip", ".dmg",  # Direct file downloads
    ]

    for pattern in excluded_patterns:
        if pattern in url.lower():
            return False

    return True


def _discover_links_on_page(page: Page, url_pattern: str) -> Set[str]:
    """Discover all valid links on the current page."""
    links = page.query_selector_all(f'a[href*="{url_pattern}"]')
    discovered = set()

    for link in links:
        href = link.get_attribute("href")
        if not href:
            continue

        # Handle relative and absolute URLs
        full_url = urljoin(BASE_URL, href)

        # Remove fragments and trailing slashes for consistency
        parsed = urlparse(full_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"

        if _is_valid_design_url(clean_url, url_pattern):
            discovered.add(clean_url)

    return discovered


def get_article_urls(
    start_url: str = DEFAULT_START_URL,
    url_pattern: str = DEFAULT_URL_PATTERN,
    max_depth: int = 2,
    max_pages: int = 500
) -> List[str]:
    """
    Recursively discover all pages under the specified URL pattern.

    Args:
        start_url: The starting URL to begin discovery
        url_pattern: URL pattern to match (e.g., "/design/")
        max_depth: Maximum depth for recursive discovery (0 = start page only)
        max_pages: Maximum number of pages to discover

    Returns:
        Sorted list of unique URLs
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            discovered_urls = set()
            urls_to_visit = {start_url}
            visited_urls = set()
            depth_map = {start_url: 0}

            print(f"Starting URL discovery from: {start_url}")
            print(f"URL pattern: {url_pattern}, Max depth: {max_depth}, Max pages: {max_pages}")

            while urls_to_visit and len(discovered_urls) < max_pages:
                # Get next URL to visit
                current_url = urls_to_visit.pop()

                if current_url in visited_urls:
                    continue

                current_depth = depth_map.get(current_url, 0)
                visited_urls.add(current_url)

                try:
                    print(f"\n[Depth {current_depth}] Visiting: {current_url}")
                    page.goto(current_url, wait_until="networkidle", timeout=60_000)

                    # Add current page to discovered URLs
                    discovered_urls.add(current_url)
                    print(f"  ✓ Added ({len(discovered_urls)} total)")

                    # If we haven't reached max depth, discover links on this page
                    if current_depth < max_depth:
                        new_links = _discover_links_on_page(page, url_pattern)
                        print(f"  Found {len(new_links)} links on this page")

                        # Add new links to visit queue
                        for link in new_links:
                            if link not in visited_urls and link not in urls_to_visit:
                                urls_to_visit.add(link)
                                depth_map[link] = current_depth + 1

                        print(f"  Added {len(new_links - visited_urls)} new URLs to queue")

                    # Small delay to be respectful
                    time.sleep(0.5)

                except Exception as e:
                    print(f"  ✗ Error visiting {current_url}: {str(e)}")
                    continue

            print(f"\n{'='*60}")
            print(f"Discovery complete: {len(discovered_urls)} unique pages found")
            print(f"{'='*60}\n")

            return sorted(discovered_urls)

        finally:
            browser.close()
