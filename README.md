# Apple Developer Design - PDF Generator

This tool automatically scrapes and compiles Apple's Developer Design documentation (including Human Interface Guidelines) into comprehensive PDF documents, complete with cover pages, table of contents, and bookmarks.

## 🚨 Important Notice

This tool is for **personal use only**. The Apple Human Interface Guidelines are copyrighted material owned by Apple Inc. This script merely facilitates access to publicly available content for personal reference. The generated PDF should not be redistributed or used for commercial purposes.

## 🤔 Why Use This Tool

Having Apple's Human Interface Guidelines available as a single, offline PDF provides several benefits:

- **Offline Access**: Access the complete HIG documentation during flights, commutes, or in areas with limited internet connectivity
- **Persistent Reference**: Maintain access to a specific version of the guidelines even if the online documentation changes
- **Improved Navigation**: Quickly search across the entire documentation using PDF reader search functions
- **Annotation**: Add personal notes, highlights, and bookmarks directly on the document

## ✨ Features

- **Recursive URL Discovery**: Automatically discovers pages from any Apple Developer Design section
- **Configurable Target**: Pull from Human Interface Guidelines, full Design section, or custom URLs
- **Smart Deduplication**: Detects and removes duplicate content based on content hashing
- **Professional PDFs**: Generates individual PDFs for each article with proper formatting
- **Cover & TOC**: Creates a professional cover page and table of contents with page numbers
- **Bookmarks**: Merges all PDFs with working bookmarks and internal navigation
- **Image Handling**: Prevents page breaks inside images and special sections
- **Flexible Options**: Command-line arguments for depth, max pages, and custom output

## 📋 Requirements

- Python 3.7+
- Playwright
- PyPDF2

## 🛠️ Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd HIGs-PDF
   ```

2. Install required dependencies:
   ```
   pip install playwright pypdf2
   playwright install chromium
   ```

## 🚀 Usage

### Basic Usage

Pull all pages from the entire `/design/` section (including HIGs, resources, guides, etc.):

```bash
python main.py
```

### Advanced Options

```bash
# Pull only Human Interface Guidelines
python main.py --url https://developer.apple.com/design/human-interface-guidelines/ \
               --pattern "/design/human-interface-guidelines/"

# Pull all design pages with deeper recursion (follows more links)
python main.py --depth 3

# Limit the number of pages discovered
python main.py --max-pages 100 --depth 1

# Custom output directory
python main.py --output-dir "Apple-Design-Docs"

# View all options
python main.py --help
```

### Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--url` | `https://developer.apple.com/design/` | Starting URL for discovery |
| `--pattern` | `/design/` | URL pattern to match |
| `--depth` | `2` | Maximum recursion depth for link discovery |
| `--max-pages` | `500` | Maximum number of pages to discover |
| `--output-dir` | Auto-generated | Custom output directory name |

### Output

The script will:
1. Recursively discover pages from the specified URL
2. Generate individual PDFs for each page
3. Create a cover page and table of contents
4. Merge everything into a single PDF
5. Save the final PDF in the output directory (default: "Apple-HIGs")

## ⚠️ Potential Issues and Solutions

### Network and Web Scraping Issues

- **Rate limiting**: The script might be blocked if too many requests are made too quickly. Solution: Add delay between requests or use proxies.
- **Website structure changes**: If Apple updates their website structure, the URL discovery might break. Solution: Update the selectors in `url_discovery.py`.
- **Timeout errors**: Some pages might take too long to load. Solution: Increase timeout values in the code.

### PDF Generation Issues

- **Missing images**: Sometimes images might not load properly. Solution: Increase the wait time for images in `pdf_generator.py`.
- **Rendering inconsistencies**: Different browsers might render content differently. Solution: Adjust the viewport settings or CSS modifications.
- **Memory issues**: Processing many large PDFs can consume significant memory. Solution: Process in smaller batches or increase available memory.

### PDF Merging Issues

- **Bookmark errors**: Incorrect page numbers in bookmarks. Solution: Check the page counting logic in `pdf_merger.py`.
- **Large file size**: The final PDF might be very large. Solution: Adjust the PDF compression settings.

## 🔍 Project Structure

```
HIGs-PDF/
├── main.py                      # Entry point with CLI argument parsing
├── src/
│   ├── url_discovery.py        # Recursive URL discovery with configurable patterns
│   ├── pdf_generator.py        # Converts web pages to PDFs with proper formatting
│   ├── pdf_merger.py           # Merges PDFs with bookmarks and TOC
│   └── utils.py                # Utility functions (hashing, sanitization, etc.)
└── README.md
```

### Key Improvements in This Version

1. **Recursive Discovery**: Now crawls links recursively to discover nested pages
2. **Configurable Targets**: Support for any Apple Developer section, not just HIGs
3. **Better Title Extraction**: Improved extraction from multiple selectors and page titles
4. **Smart Filtering**: Excludes download links, forums, and other non-content pages
5. **CLI Arguments**: Full command-line interface for customization
6. **Depth Control**: Configurable recursion depth to control discovery scope

## 📝 License

This project is for personal use only. The Apple Human Interface Guidelines content is copyrighted by Apple Inc.

## 🙏 Acknowledgements

This tool is not affiliated with, authorized, maintained, sponsored, or endorsed by Apple Inc. or any of its affiliates or subsidiaries.
