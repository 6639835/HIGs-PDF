import asyncio
import hashlib
import os
import urllib.parse
import uuid
from typing import Dict, Iterable, List, Optional, Tuple

from playwright.async_api import async_playwright

from src.utils import (
    calculate_content_hash_async,
    create_cover_html,
    create_index_html,
    get_pdf_page_count,
    sanitize_filename,
)

OUTPUT_DIR = "Apple-HIGs"
PDF_MARGIN = {"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
INDEX_MARGIN = {"top": "0cm", "bottom": "0cm", "left": "0cm", "right": "0cm"}

# A4 page size (CSS px at 96dpi). Used to map DOM coordinates to PDF points (72dpi).
A4_WIDTH_PX = 794
A4_HEIGHT_PX = 1123
PT_PER_PX = 72.0 / 96.0


def add_page_break_script() -> str:
    """JavaScript to handle image pagination and section breaks."""
    return """() => {
        // Handle images and their captions
        function wrapImageWithCaption(img) {
            const wrapper = document.createElement('div');
            wrapper.style.pageBreakInside = 'avoid';
            wrapper.style.breakInside = 'avoid';
            wrapper.style.margin = '1em 0';
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';

            // Find related caption
            let caption = img.closest('figure')?.querySelector('figcaption') ||
                         (img.nextElementSibling?.matches('.caption, [class*="caption"], p[class*="caption"]') 
                            ? img.nextElementSibling : null) ||
                         img.closest('dt')?.nextElementSibling;

            // Get the container that holds both image and caption
            const container = img.closest('figure') || img.parentElement;
            
            if (container) {
                container.style.pageBreakInside = 'avoid';
                container.style.breakInside = 'avoid';
                
                if (!container.parentElement?.hasAttribute('data-image-wrapper')) {
                    wrapper.setAttribute('data-image-wrapper', 'true');
                    container.parentNode.insertBefore(wrapper, container);
                    wrapper.appendChild(container);
                }
            } else {
                wrapper.setAttribute('data-image-wrapper', 'true');
                img.parentNode.insertBefore(wrapper, img);
                wrapper.appendChild(img);
                if (caption) wrapper.appendChild(caption);
            }
        }

        // Handle Resources and Change Log sections
        function handleSpecialSections() {
            const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
            
            const resourcesHeading = headings.find(h => 
                h.textContent.toLowerCase().includes('resource') ||
                h.textContent.toLowerCase().includes('related') ||
                h.textContent.toLowerCase().includes('see also')
            );

            if (resourcesHeading) {
                // Create resources wrapper with page break
                const wrapper = document.createElement('div');
                wrapper.style.pageBreakBefore = 'always';
                wrapper.style.breakBefore = 'page';
                
                // Get all content until next major heading or end
                const content = [];
                let current = resourcesHeading;
                
                while (current) {
                    const next = current.nextElementSibling;
                    if (next && next.matches('h1')) break;
                    content.push(current);
                    current = next;
                }

                // Move content to wrapper
                resourcesHeading.parentNode.insertBefore(wrapper, resourcesHeading);
                content.forEach(node => wrapper.appendChild(node));
            }
        }

        // Process images first
        document.querySelectorAll('img, [role="img"], svg').forEach(wrapImageWithCaption);
        document.querySelectorAll('.graphics-container, [class*="figure"], [class*="image"]').forEach(container => {
            container.style.pageBreakInside = 'avoid';
            container.style.breakInside = 'avoid';
        });

        // Then handle special sections
        handleSpecialSections();
    }"""


def _extract_index_link_rects(index_page) -> List[Dict]:
    """
    Extract clickable rectangles for each TOC row in CSS pixels, then convert to PDF points.

    Returns:
        List[Dict]: [{idx: int, index_page: int, rect: [x1, y1, x2, y2]}] where rect is in PDF points.
    """
    return index_page.evaluate(
        """(args) => {
            const PAGE_W = args.pageWidthPx;
            const PAGE_H = args.pageHeightPx;
            const PT_PER_PX = args.ptPerPx;
            const rows = Array.from(document.querySelectorAll('.row[data-idx]'));
            return rows.map((row) => {
                const idx = parseInt(row.getAttribute('data-idx') || '0', 10);
                const rect = row.getBoundingClientRect();
                // For long lists, the layout extends beyond a single "screen"; rect values can exceed PAGE_H.
                const absTop = rect.top + window.scrollY;
                const absBottom = rect.bottom + window.scrollY;
                const pageIndex = Math.floor(absTop / PAGE_H);
                const topOnPage = absTop - pageIndex * PAGE_H;
                const bottomOnPage = absBottom - pageIndex * PAGE_H;

                const x1 = rect.left;
                const x2 = rect.right;
                // Convert from CSS top-left origin to PDF bottom-left origin.
                const y1 = (PAGE_H - bottomOnPage);
                const y2 = (PAGE_H - topOnPage);

                return {
                    idx,
                    index_page: pageIndex,
                    rect: [x1 * PT_PER_PX, y1 * PT_PER_PX, x2 * PT_PER_PX, y2 * PT_PER_PX],
                };
            });
        }""",
        {"pageWidthPx": A4_WIDTH_PX, "pageHeightPx": A4_HEIGHT_PX, "ptPerPx": PT_PER_PX},
    )


def _url_digest(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


async def _extract_title(page) -> str:
    # Avoid multiple round-trips by extracting via JS.
    raw: str = await page.evaluate(
        """() => {
            const h1 = document.querySelector('h1');
            if (h1 && h1.innerText) return h1.innerText;
            const t = document.querySelector('title');
            if (t && t.innerText) return t.innerText;
            const h2 = document.querySelector('h2');
            if (h2 && h2.innerText) return h2.innerText;
            return document.title || '';
        }"""
    )
    title = (raw or "").replace(" | Apple Developer", "").strip()
    return title or "Untitled"


def _build_article_path(
    *,
    output_dir: str,
    idx: int,
    url: str,
    title: str,
    stable_filenames: bool,
) -> str:
    path_parts = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
    section = path_parts[-2] if len(path_parts) > 1 else "misc"
    safe_title = sanitize_filename(f"{section}-{title}")[:90] or "Untitled"
    digest = _url_digest(url)

    if stable_filenames:
        filename = f"{idx:04d}-{safe_title}-{digest}.pdf"
    else:
        nonce = uuid.uuid4().hex[:6]
        filename = f"{safe_title}-{digest}-{nonce}.pdf"
    return os.path.join(output_dir, filename)


async def _generate_one_pdf(
    *,
    context,
    semaphore: asyncio.Semaphore,
    idx: int,
    url: str,
    output_dir: str,
    stable_filenames: bool,
    seen_lock: asyncio.Lock,
    seen_hashes: set[str],
) -> Optional[Dict]:
    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60_000)

            content_hash = await calculate_content_hash_async(page)
            async with seen_lock:
                if content_hash in seen_hashes:
                    print(f"Skipping duplicate content: {url}")
                    return None
                seen_hashes.add(content_hash)

            try:
                await page.evaluate(add_page_break_script())
            except Exception as exc:
                print(f"Warning: Could not apply image pagination for {url}: {exc}")

            title = await _extract_title(page)
            filepath = _build_article_path(
                output_dir=output_dir,
                idx=idx,
                url=url,
                title=title,
                stable_filenames=stable_filenames,
            )

            await page.pdf(
                path=filepath,
                format="A4",
                print_background=True,
                margin=PDF_MARGIN,
                display_header_footer=False,
            )

            print(f"Generated ({idx}): {os.path.basename(filepath)}")
            return {"idx": idx, "url": url, "title": title, "path": filepath}
        except Exception as exc:
            print(f"Failed {url}: {exc}")
            return None
        finally:
            await page.close()


async def _generate_pdfs_async(
    article_urls: Iterable[str],
    output_dir: str = None,
    cover_title: str = "Apple Developer Design",
    cover_subtitle: str = "A comprehensive offline reference",
    stable_filenames: bool = False,
    workers: int = 8,
) -> Tuple[str, List[str], List[Tuple[str, int]], List[Dict]]:
    if output_dir is None:
        output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    article_list = list(article_urls)
    if not article_list:
        return output_dir, [], [], []

    workers = max(1, int(workers))
    semaphore = asyncio.Semaphore(workers)
    seen_lock = asyncio.Lock()
    seen_hashes: set[str] = set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1200, "height": 800},
            forced_colors="none",
        )

        # PDFs don't benefit from media streams, sockets, or other long-lived resources.
        async def _route_handler(route, request):
            if request.resource_type in {"media", "websocket", "eventsource"}:
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _route_handler)

        try:
            # Cover page
            cover_page = await context.new_page()
            cover_html = create_cover_html(title=cover_title, subtitle=cover_subtitle)
            await cover_page.set_content(cover_html)
            cover_file = os.path.join(output_dir, "_cover.pdf")
            await cover_page.pdf(
                path=cover_file,
                format="A4",
                print_background=True,
                margin=INDEX_MARGIN,
            )
            await cover_page.close()
            cover_pages = get_pdf_page_count(cover_file)

            # Articles (parallel)
            tasks = [
                asyncio.create_task(
                    _generate_one_pdf(
                        context=context,
                        semaphore=semaphore,
                        idx=idx,
                        url=url,
                        output_dir=output_dir,
                        stable_filenames=stable_filenames,
                        seen_lock=seen_lock,
                        seen_hashes=seen_hashes,
                    )
                )
                for idx, url in enumerate(article_list, 1)
            ]

            results = await asyncio.gather(*tasks)
            generated_articles = [r for r in results if r is not None]
            generated_articles.sort(key=lambda r: r["idx"])

            titles = [r["title"] for r in generated_articles]
            article_paths = [r["path"] for r in generated_articles]

            # Compute page numbers (sequential; uses generated PDFs).
            page_numbers: List[int] = []
            current_page = 1 + cover_pages
            for pdf_path in article_paths:
                page_numbers.append(current_page)
                current_page += get_pdf_page_count(pdf_path)
            sections_info = list(zip(titles, page_numbers))

            # Index (iterative: index page count affects displayed numbers)
            index_file = os.path.join(output_dir, "_index.pdf")
            index_pages = 1
            toc_links: List[Dict] = []
            for _attempt in range(3):
                display_sections_info = [(t, p + index_pages) for (t, p) in sections_info]
                index_html = create_index_html(display_sections_info)

                index_page = await context.new_page()
                await index_page.set_viewport_size({"width": A4_WIDTH_PX, "height": A4_HEIGHT_PX})
                await index_page.set_content(index_html)
                await index_page.emulate_media(media="print")

                toc_links = await _extract_index_link_rects(index_page)

                await index_page.pdf(
                    path=index_file,
                    format="A4",
                    print_background=True,
                    margin=INDEX_MARGIN,
                )
                await index_page.close()

                new_index_pages = get_pdf_page_count(index_file)
                if new_index_pages == index_pages:
                    break
                index_pages = new_index_pages

            generated_files = [cover_file, index_file] + article_paths
            return output_dir, generated_files, sections_info, toc_links
        finally:
            await context.close()
            await browser.close()


def generate_pdfs(
    article_urls: Iterable[str],
    output_dir: str = None,
    cover_title: str = "Apple Developer Design",
    cover_subtitle: str = "A comprehensive offline reference",
    stable_filenames: bool = False,
    workers: int = 8,
) -> Tuple[str, List[str], List[Tuple[str, int]], List[Dict]]:
    return asyncio.run(
        _generate_pdfs_async(
            article_urls=article_urls,
            output_dir=output_dir,
            cover_title=cover_title,
            cover_subtitle=cover_subtitle,
            stable_filenames=stable_filenames,
            workers=workers,
        )
    )
