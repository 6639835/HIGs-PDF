import os
from typing import Iterable, List, Optional, Tuple

from PyPDF2 import PdfMerger, PdfReader

MERGED_FILENAME = "Apple HIGs Complete.pdf"


def merge_pdfs(
    output_dir: str,
    generated_files: Iterable[str],
    sections_info: List[Tuple[str, int]],
    organize_files: bool = True,
) -> Optional[str]:
    """
    Merge PDFs with working bookmarks and internal links.

    Args:
        output_dir: Directory containing the PDFs
        generated_files: List of PDF file paths to merge
        sections_info: List of (title, page_number) tuples for bookmarks
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
        if len(generated_list) > 0 and os.path.exists(generated_list[0]):
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

                    # Add bookmark with named destination
                    merger.append(
                        pdf_path,
                        outline_item={
                            "title": section_title,
                            "page_number": page_number + index_pages - 1,
                            "type": "/Fit",
                            "color": "0,0,0",  # Black color for bookmark
                            "dest": f"section_{idx}"  # Named destination for internal linking
                        },
                    )
                except Exception as e:
                    print(f"Error adding {pdf_path}: {str(e)}")
                    continue

        # Write final merged PDF
        merged_path = os.path.join(output_dir, MERGED_FILENAME)
        merger.write(merged_path)
        merger.close()

        # Organize individual PDFs into subdirectory if requested
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

        # Summary
        print(f"\n{'='*60}")
        print("✅ PDF Generation Complete!")
        print(f"{'='*60}")
        print(f"📄 Merged PDF: {merged_path}")
        if organize_files:
            print(f"📁 Individual PDFs: {os.path.join(output_dir, 'individual_pdfs')}/ ({len(generated_list)} files)")
        else:
            print(f"📁 Individual PDFs: {output_dir}/ ({len(generated_list)} files)")
        print(f"{'='*60}")

        return merged_path

    except Exception as e:
        print(f"Error during PDF merge: {str(e)}")
        return None
