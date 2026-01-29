import os
import urllib.parse
from typing import Dict, Iterable, List, Tuple

from playwright.sync_api import sync_playwright

from src.utils import (
    calculate_content_hash,
    create_cover_html,
    create_index_html,
    get_pdf_page_count,
    get_unique_filename,
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


def generate_pdfs(
    article_urls: Iterable[str],
    output_dir: str = None,
    cover_title: str = "Apple Developer Design",
    cover_subtitle: str = "A comprehensive offline reference",
) -> Tuple[str, List[str], List[Tuple[str, int]], List[Dict]]:
    """
    Generate PDFs for all articles.

    Args:
        article_urls: Iterable of URLs to convert to PDFs
        output_dir: Custom output directory (optional, defaults to OUTPUT_DIR)

    Returns:
        Tuple of (output_dir, generated_files, sections_info, toc_links)
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    generated_files: List[str] = []
    titles: List[str] = []
    page_numbers: List[int] = []
    content_hashes = set()
    current_page = 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1200, "height": 800},
            forced_colors="none",
        )

        try:
            # Generate cover page
            cover_page = context.new_page()
            cover_html = create_cover_html(title=cover_title, subtitle=cover_subtitle)
            cover_page.set_content(cover_html)
            cover_file = os.path.join(output_dir, "_cover.pdf")
            cover_page.pdf(
                path=cover_file,
                format="A4",
                print_background=True,
                margin=INDEX_MARGIN,
            )
            cover_page.close()

            # Store cover file but don't add to generated_files yet
            current_page += get_pdf_page_count(cover_file)

            # Generate PDFs for articles
            article_list = list(article_urls)
            for idx, url in enumerate(article_list, 1):
                page = None
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=60_000)

                    content_hash = calculate_content_hash(page)
                    if content_hash in content_hashes:
                        print(f"Skipping duplicate content: {url}")
                        continue

                    content_hashes.add(content_hash)

                    try:
                        page.evaluate(add_page_break_script())
                    except Exception as exc:
                        print(f"Warning: Could not apply image pagination for {url}: {exc}")

                    try:
                        page.wait_for_selector("img", state="attached", timeout=5_000)
                    except Exception:
                        print(f"Warning: No images found or timeout waiting for images in {url}")

                    # Try multiple selectors for title extraction
                    title_element = (
                        page.query_selector("h1") or
                        page.query_selector("title") or
                        page.query_selector("h2")
                    )
                    if title_element:
                        title = title_element.inner_text()
                        # Clean up title from common patterns
                        title = title.replace(" | Apple Developer", "").strip()
                    else:
                        # Fallback to page title or URL
                        title = page.title().replace(" | Apple Developer", "").strip() or "Untitled"

                    titles.append(title)

                    path_parts = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
                    section = path_parts[-2] if len(path_parts) > 1 else "misc"
                    safe_title = sanitize_filename(f"{section}-{title}")
                    filepath = get_unique_filename(output_dir, f"{safe_title}.pdf")

                    pdf_options = {
                        "path": filepath,
                        "format": "A4",
                        "print_background": True,
                        "margin": PDF_MARGIN,
                        "display_header_footer": False,
                    }

                    page.pdf(**pdf_options)

                    page_count = get_pdf_page_count(filepath)
                    page_numbers.append(current_page)
                    current_page += page_count

                    generated_files.append(filepath)
                    print(
                        f"Generated ({idx}/{len(article_list)}): "
                        f"{os.path.basename(filepath)} - {page_count} pages"
                    )
                except Exception as exc:
                    print(f"Failed {url}: {exc}")
                finally:
                    if page is not None:
                        page.close()

            # Create index
            sections_info = list(zip(titles, page_numbers))
            index_file = os.path.join(output_dir, "_index.pdf")

            # Render index PDF with corrected page numbers (2-pass/iterative: index page count can affect page numbers).
            index_pages = 1
            toc_links: List[Dict] = []
            for _attempt in range(3):
                display_sections_info = [(t, p + index_pages) for (t, p) in sections_info]
                index_html = create_index_html(display_sections_info)

                index_page = context.new_page()
                index_page.set_viewport_size({"width": A4_WIDTH_PX, "height": A4_HEIGHT_PX})
                index_page.set_content(index_html)
                index_page.emulate_media(media="print")

                toc_links = _extract_index_link_rects(index_page)

                index_page.pdf(
                    path=index_file,
                    format="A4",
                    print_background=True,
                    margin=INDEX_MARGIN,
                )
                index_page.close()

                new_index_pages = get_pdf_page_count(index_file)
                if new_index_pages == index_pages:
                    break
                index_pages = new_index_pages

            # Add files in the correct order: cover, index, content
            generated_files = [cover_file, index_file] + generated_files

            return output_dir, generated_files, sections_info, toc_links
        finally:
            browser.close()
