import argparse
from typing import Optional

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

    return parser.parse_args()


def main() -> None:
    """Discover design pages, render PDFs, and merge them into a single file."""
    args = parse_args()

    print(f"\n{'='*60}")
    print("Apple Developer Design PDF Generator")
    print(f"{'='*60}")
    print(f"Start URL: {args.url}")
    print(f"URL Pattern: {args.pattern}")
    print(f"Max Depth: {args.depth}")
    print(f"Max Pages: {args.max_pages}")
    print(f"{'='*60}\n")

    # Discover URLs
    articles = get_article_urls(
        start_url=args.url,
        url_pattern=args.pattern,
        max_depth=args.depth,
        max_pages=args.max_pages
    )
    print(f"\nFound {len(articles)} pages to convert")

    if not articles:
        print("❌ No articles found. Exiting.")
        return

    # Generate PDFs
    print("\n" + "="*60)
    print("Starting PDF generation...")
    print("="*60 + "\n")
    output_folder, generated_files, sections_info = generate_pdfs(
        articles,
        output_dir=args.output_dir
    )

    # Merge PDFs
    print("\n" + "="*60)
    print("Starting PDF merge process...")
    print("="*60 + "\n")
    final_pdf = merge_pdfs(output_folder, generated_files, sections_info)

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
