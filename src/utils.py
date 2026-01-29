import hashlib
import html
import os
import re
import time
from typing import Iterable, Tuple

from PyPDF2 import PdfReader

FILENAME_MAX_LEN = 100


def sanitize_filename(text: str) -> str:
    """Create safe filenames from titles."""
    return re.sub(r'[\\/*?:"<>|]', '', text)[:FILENAME_MAX_LEN].strip()


def get_unique_filename(output_dir: str, base_name: str) -> str:
    """Create a unique filename using timestamp and hash if needed."""
    base, ext = os.path.splitext(base_name)
    timestamp = int(time.time() * 1000)
    counter = 0
    
    while True:
        if counter == 0:
            filename = f"{base}_{timestamp}{ext}"
        else:
            filename = f"{base}_{timestamp}_{counter}{ext}"
            
        filepath = os.path.join(output_dir, filename)
        if not os.path.exists(filepath):
            return filepath
        counter += 1


def calculate_content_hash(page) -> str:
    """Calculate hash of page content for duplicate detection."""
    content = page.evaluate("""() => {
        const main = document.querySelector('main') || document.body;
        const clone = main.cloneNode(true);
        const dynamics = clone.querySelectorAll('[data-dynamic], .timestamp, time');
        dynamics.forEach(el => el.remove());
        return clone.textContent;
    }""")
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def get_pdf_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            return len(reader.pages)
    except Exception as e:
        print(f"Error getting page count for {pdf_path}: {str(e)}")
        return 0


def create_index_html(sections_info: Iterable[Tuple[str, int]]) -> str:
    """Create index page HTML with Apple-style design."""
    items = '\n'.join([
        f'<li><div class="row" data-idx="{idx}"><span class="title">{html.escape(title)}</span>'
        f'<span class="page">{page}</span></div></li>'
        for idx, (title, page) in enumerate(sections_info, 1)
    ])
    
    return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Icons", sans-serif;
                    padding: 48px;
                    max-width: 980px;
                    margin: 0 auto;
                    color: #1d1d1f;
                }}
                h1 {{
                    font-size: 40px;
                    font-weight: 600;
                    letter-spacing: -0.003em;
                    margin-bottom: 40px;
                }}
                ul {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                    border-top: 1px solid #d2d2d7;
                }}
                li {{
                    border-bottom: 1px solid #d2d2d7;
                }}
                .row {{
                    cursor: pointer;
                    padding: 12px 0;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .row:hover {{
                    color: #06c;
                }}
                .title {{
                    font-size: 17px;
                    letter-spacing: -0.022em;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 720px;
                }}
                .page {{
                    color: #86868b;
                    font-size: 15px;
                    font-weight: 400;
                    flex: 0 0 auto;
                }}
            </style>
        </head>
        <body>
            <h1>Contents</h1>
            <ul>{items}</ul>
        </body>
        </html>
    """


def create_cover_html(title: str = "Apple Developer Design", subtitle: str = "A comprehensive offline reference") -> str:
    """Create a minimalist cover page."""
    return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 40px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                }}
                .cover {{ text-align: center; max-width: 800px; }}
                h1 {{
                    font-size: 48px;
                    font-weight: 500;
                    margin: 0 0 2rem;
                    color: #1d1d1f;
                }}
                .subtitle {{
                    font-size: 24px;
                    font-weight: 300;
                    color: #86868b;
                    margin: 0;
                }}
            </style>
        </head>
        <body>
            <div class="cover">
                <h1>{html.escape(title)}</h1>
                <p class="subtitle">{html.escape(subtitle).replace("\\n", "<br>")}</p>
            </div>
        </body>
        </html>
    """
