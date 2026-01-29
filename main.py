import argparse
import os
import shutil
import time

from urllib.parse import urlparse

from src.pdf_merger import merge_pdfs
from src.pdf_generator import generate_pdfs
from src.url_discovery import get_article_urls


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate PDFs from Apple Developer Design pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Pull all pages from /design/ section (max depth 2)
  python main.py

  # Pull only Human Interface Guidelines
  python main.py --url https://developer.apple.com/design/human-interface-guidelines/ \\
                 --pattern "/design/human-interface-guidelines/"

  # Pull all design pages with deeper recursion
  python main.py --depth 3

  # Pull with custom limits
  python main.py --max-pages 100 --depth 1

  # Keep only the merged PDF (delete individual PDFs after merging)
  python main.py --no-keep-separate

  # Don't move individual PDFs into a subdirectory
  python main.py --no-organize
        """
    )

    parser.add_argument(
        "--url",
        default="https://developer.apple.com/design/",
        help="Starting URL for discovery (default: https://developer.apple.com/design/)"
    )

    parser.add_argument(
        "--pattern",
        default="/design/",
        help="URL pattern to match (default: /design/)"
    )

    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum recursion depth for link discovery (default: 2)"
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Maximum number of pages to discover (default: 500)"
    )

    parser.add_argument(
        "--output-dir",
        help="Custom output directory name (default: auto-generated from URL)"
    )

    parser.add_argument(
        "--stable-filenames",
        action="store_true",
        default=False,
        help="Use deterministic filenames for generated PDFs (useful for CI)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(16, (os.cpu_count() or 8))),
        help="Concurrent workers for PDF generation (default: min(16, CPU count))",
    )

    parser.add_argument(
        "--discovery-delay",
        type=float,
        default=0.0,
        help="Optional delay (seconds) between page visits during URL discovery (default: 0.0)",
    )

    parser.add_argument(
        "--clean-output",
        action="store_true",
        default=False,
        help="Delete output directory before generating PDFs",
    )

    parser.add_argument(
        "--keep-separate",
        dest="keep_separate",
        action="store_true",
        default=True,
        help="Keep individual PDF files after merging (default: True)",
    )
    parser.add_argument(
        "--no-keep-separate",
        dest="keep_separate",
        action="store_false",
        help="Delete individual PDF files after merging (keep only the merged PDF)",
    )

    parser.add_argument(
        "--organize",
        dest="organize",
        action="store_true",
        default=True,
        help="Organize individual PDFs into subdirectory (default: True)",
    )
    parser.add_argument(
        "--no-organize",
        dest="organize",
        action="store_false",
        help="Do not move individual PDFs into a subdirectory",
    )

    return parser.parse_args()


def _slugify_filename(name: str) -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch in " .-_()") else " " for ch in name)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned[:120] or "Document"


def _document_title_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if any(p == "human-interface-guidelines" for p in parts):
        return "Human Interface Guidelines"
    if parts and parts[-1] == "design":
        return "Apple Developer Design"
    if parts:
        return parts[-1].replace("-", " ").replace("_", " ").title()
    return "Apple Developer Design"


def _default_output_dir_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if any(p == "human-interface-guidelines" for p in parts):
        return "Apple-HIGs"
    if parts and parts[-1] == "design":
        return "Apple-Design"
    if parts:
        slug = parts[-1]
        slug = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in slug)
        slug = "-".join([p for p in slug.split("-") if p])
        slug = slug[:60] or "Docs"
        return f"Apple-{slug}"
    return "Apple-Design"


def main() -> None:
    """Discover design pages, render PDFs, and merge them into a single file."""
    args = parse_args()
    output_dir = args.output_dir or _default_output_dir_from_url(args.url)
    document_title = _document_title_from_url(args.url)
    merged_filename = f"{_slugify_filename(document_title)} Complete.pdf"

    if args.clean_output and os.path.exists(output_dir):
        repo_root = os.path.abspath(os.getcwd())
        target = os.path.abspath(output_dir)
        if not target.startswith(repo_root + os.sep):
            raise ValueError(f"Refusing to delete output directory outside repo: {output_dir}")
        if os.path.isfile(target):
            raise ValueError(f"Refusing to delete file path: {output_dir}")
        shutil.rmtree(target)

    print(f"\n{'='*60}")
    print("Apple Developer Design PDF Generator")
    print(f"{'='*60}")
    print(f"Start URL: {args.url}")
    print(f"URL Pattern: {args.pattern}")
    print(f"Max Depth: {args.depth}")
    print(f"Max Pages: {args.max_pages}")
    print(f"Output Dir: {output_dir}")
    print(f"Merged Filename: {merged_filename}")
    print(f"{'='*60}\n")

    # Discover URLs
    t0 = time.perf_counter()
    articles = get_article_urls(
        start_url=args.url,
        url_pattern=args.pattern,
        max_depth=args.depth,
        max_pages=args.max_pages,
        delay_seconds=args.discovery_delay,
    )
    t1 = time.perf_counter()
    print(f"\nFound {len(articles)} pages to convert")
    print(f"Discovery time: {t1 - t0:.2f}s")

    if not articles:
        print("❌ No articles found. Exiting.")
        return

    # Generate PDFs
    print("\n" + "="*60)
    print("Starting PDF generation...")
    print("="*60 + "\n")
    t2 = time.perf_counter()
    output_folder, generated_files, sections_info, toc_links = generate_pdfs(
        articles,
        output_dir=output_dir,
        cover_title=document_title,
        cover_subtitle="A comprehensive offline reference",
        stable_filenames=args.stable_filenames,
        workers=args.workers,
    )
    t3 = time.perf_counter()
    print(f"PDF generation time: {t3 - t2:.2f}s")

    # Merge PDFs
    print("\n" + "="*60)
    print("Starting PDF merge process...")
    print("="*60 + "\n")
    t4 = time.perf_counter()
    final_pdf = merge_pdfs(
        output_folder,
        generated_files,
        sections_info,
        toc_links=toc_links,
        merged_filename=merged_filename,
        keep_separate=args.keep_separate,
        organize_files=args.organize,
    )
    t5 = time.perf_counter()
    print(f"PDF merge time: {t5 - t4:.2f}s")

    if final_pdf:
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS!")
        print(f"{'='*60}")
        print(f"Final PDF: {final_pdf}")
        print(f"Total pages processed: {len(articles)}")
        print(f"{'='*60}\n")
    else:
        print("\n❌ Failed to merge PDFs")


if __name__ == "__main__":
    main()
