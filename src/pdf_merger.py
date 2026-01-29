import os
import tempfile
from typing import Dict, Iterable, List, Optional, Tuple

from PyPDF2 import PdfMerger, PdfReader
from PyPDF2.generic import ArrayObject, NumberObject, RectangleObject
from PyPDF2 import PdfWriter

DEFAULT_MERGED_FILENAME = "Apple Docs Complete.pdf"


def merge_pdfs(
    output_dir: str,
    generated_files: Iterable[str],
    sections_info: List[Tuple[str, int]],
    toc_links: List[Dict],
    merged_filename: str = DEFAULT_MERGED_FILENAME,
    keep_separate: bool = True,
    organize_files: bool = True,
) -> Optional[str]:
    """
    Merge PDFs with working bookmarks and internal links.

    Args:
        output_dir: Directory containing the PDFs
        generated_files: List of PDF file paths to merge
        sections_info: List of (title, page_number) tuples for bookmarks
        toc_links: List of TOC rectangles for adding internal links to the merged PDF
        merged_filename: Filename for the merged PDF
        keep_separate: If False, delete individual PDFs after merging
        organize_files: If True, move individual PDFs to a subdirectory

    Returns:
        Path to the merged PDF file, or None if merge failed
    """
    generated_list = list(generated_files)
    if not generated_list:
        print("No PDFs found to merge.")
        return None

    try:
        merger = PdfMerger()

        # Add cover page
        index_pages = 0
        cover_pages = 0
        if len(generated_list) > 0 and os.path.exists(generated_list[0]):
            cover_pages = len(PdfReader(generated_list[0]).pages)
            merger.append(generated_list[0])

        # Add index page
        if len(generated_list) > 1 and os.path.exists(generated_list[1]):
            index_pages = len(PdfReader(generated_list[1]).pages)
            merger.append(generated_list[1])

        # Add content pages with bookmarks using provided page numbers
        for idx, pdf_path in enumerate(generated_list[2:], 1):
            if os.path.exists(pdf_path):
                print(f"Adding: {os.path.basename(pdf_path)}")
                try:
                    section_title, page_number = sections_info[idx - 1]
                    dest_page = (page_number - 1) + index_pages

                    # Add bookmark with named destination
                    merger.append(
                        pdf_path,
                        outline_item={
                            "title": section_title,
                            "page_number": dest_page,
                            "type": "/Fit",
                            "color": "0,0,0",  # Black color for bookmark
                            "dest": f"section_{idx}"  # Named destination for internal linking
                        },
                    )
                except Exception as e:
                    print(f"Error adding {pdf_path}: {str(e)}")
                    continue

        # Write final merged PDF
        merged_path = os.path.join(output_dir, merged_filename or DEFAULT_MERGED_FILENAME)
        merger.write(merged_path)
        merger.close()

        # Add internal links on the TOC pages to the destination pages in the merged PDF.
        if toc_links:
            reader = PdfReader(merged_path)
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)

            border = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)])
            for link in toc_links:
                idx = int(link.get("idx", 0))
                index_page_idx = int(link.get("index_page", 0))
                rect = link.get("rect")
                if idx <= 0 or rect is None:
                    continue
                if idx > len(sections_info):
                    continue

                src_page = cover_pages + index_page_idx
                dest_page = (sections_info[idx - 1][1] - 1) + index_pages

                if src_page < 0 or src_page >= len(writer.pages):
                    continue
                if dest_page < 0 or dest_page >= len(writer.pages):
                    continue

                try:
                    writer.add_link(
                        pagenum=src_page,
                        page_destination=dest_page,
                        rect=RectangleObject(rect),
                        border=border,
                        fit="/Fit",
                    )
                except Exception as e:
                    print(f"Warning: Could not add TOC link for item {idx}: {e}")

            with tempfile.NamedTemporaryFile(
                mode="wb", dir=output_dir, delete=False, prefix="merged_", suffix=".pdf"
            ) as tmp:
                tmp_path = tmp.name
                writer.write(tmp)

            os.replace(tmp_path, merged_path)

        # Handle individual PDFs after merging.
        if keep_separate:
            if organize_files:
                individual_dir = os.path.join(output_dir, "individual_pdfs")
                os.makedirs(individual_dir, exist_ok=True)

                print(f"\nOrganizing individual PDFs into: {individual_dir}/")
                for pdf in generated_list:
                    if os.path.exists(pdf):
                        try:
                            filename = os.path.basename(pdf)
                            new_path = os.path.join(individual_dir, filename)
                            os.rename(pdf, new_path)
                        except Exception as e:
                            print(f"Warning: Could not move {pdf}: {str(e)}")
        else:
            print("\nDeleting individual PDFs (keeping only the merged PDF)...")
            for pdf in generated_list:
                try:
                    if os.path.exists(pdf):
                        os.remove(pdf)
                except Exception as e:
                    print(f"Warning: Could not delete {pdf}: {str(e)}")

        # Summary
        print(f"\n{'='*60}")
        print("✅ PDF Generation Complete!")
        print(f"{'='*60}")
        print(f"📄 Merged PDF: {merged_path}")
        if keep_separate:
            if organize_files:
                print(f"📁 Individual PDFs: {os.path.join(output_dir, 'individual_pdfs')}/ ({len(generated_list)} files)")
            else:
                print(f"📁 Individual PDFs: {output_dir}/ ({len(generated_list)} files)")
        else:
            print("📁 Individual PDFs: deleted")
        print(f"{'='*60}")

        return merged_path

    except Exception as e:
        print(f"Error during PDF merge: {str(e)}")
        return None
