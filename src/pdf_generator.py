import os
import urllib.parse
from typing import Iterable, List, Tuple

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


def add_page_break_script() -> str:
    """JavaScript to handle image pagination and section breaks."""
    return """
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
    """


def generate_pdfs(article_urls: Iterable[str]) -> Tuple[str, List[str], List[Tuple[str, int]]]:
    """Generate PDFs for all articles."""
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
            cover_html = create_cover_html()
            cover_page.set_content(cover_html)
            cover_file = os.path.join(output_dir, "_cover.pdf")
            cover_page.pdf(
                path=cover_file,
                format="A4",
                print_background=True,
                margin=PDF_MARGIN,
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

                    title_element = page.query_selector("h1")
                    title = title_element.inner_text() if title_element else "Untitled"
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
            index_html = create_index_html(sections_info)
            index_file = os.path.join(output_dir, "_index.pdf")

            index_page = context.new_page()
            index_page.set_content(index_html)
            index_page.pdf(
                path=index_file,
                format="A4",
                print_background=True,
                margin=PDF_MARGIN,
            )
            index_page.close()

            # Add files in the correct order: cover, index, content
            generated_files = [cover_file, index_file] + generated_files

            return output_dir, generated_files, sections_info
        finally:
            browser.close()
