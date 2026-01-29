import argparse
import os
import re
import subprocess
from pathlib import Path


def _safe_dir_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\- .()]+", " ", name, flags=re.UNICODE)
    cleaned = " ".join(cleaned.split()).strip()
    cleaned = cleaned.replace(" ", "-")
    return cleaned[:120] or "document"


def _marker_cli_mode() -> str:
    """
    Detect whether marker_single expects positional output_dir or --output_dir.

    Returns: "flag" or "positional"
    """
    try:
        proc = subprocess.run(
            ["marker_single", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("marker_single not found in PATH. Install marker-pdf first.") from exc

    help_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    usage = help_text.lower()
    if "marker_single" in usage and "output_dir" in usage and ("marker_single file.pdf output_dir" in usage):
        return "positional"
    if "marker_single" in usage and "output_dir" in usage and ("marker_single <filename> <output_dir>" in usage):
        return "positional"
    return "flag"


def _run_marker(pdf_path: Path, out_dir: Path, extra_args: list[str]) -> None:
    mode = _marker_cli_mode()
    base = ["marker_single", str(pdf_path)]
    if mode == "positional":
        base.append(str(out_dir))
    else:
        base.extend(["--output_dir", str(out_dir)])
    cmd = base + extra_args

    proc = subprocess.run(cmd, check=False)
    if proc.returncode == 0:
        return

    # Some versions don't support certain flags; retry with a minimal set.
    minimal_args = ["--output_format", "markdown"]
    cmd2 = base + minimal_args
    proc2 = subprocess.run(cmd2, check=False)
    if proc2.returncode != 0:
        raise SystemExit(f"marker_single failed for {pdf_path} (exit {proc2.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert PDFs to Markdown using datalab-to/marker.")
    parser.add_argument(
        "--input-dir",
        default="Apple-HIGs/individual_pdfs",
        help="Directory containing PDFs to convert (default: Apple-HIGs/individual_pdfs)",
    )
    parser.add_argument(
        "--output-dir",
        default="Apple-HIGs/markdown",
        help="Directory to write Markdown outputs (default: Apple-HIGs/markdown)",
    )
    parser.add_argument(
        "--include-aux",
        action="store_true",
        default=False,
        help="Also convert PDFs starting with '_' (e.g. _cover.pdf, _index.pdf)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.rglob("*.pdf"))
    if not args.include_aux:
        pdfs = [p for p in pdfs if not p.name.startswith("_")]

    if not pdfs:
        print(f"No PDFs found under {input_dir}")
        return

    extra_args = ["--output_format", "markdown", "--paginate_output"]

    for idx, pdf_path in enumerate(pdfs, 1):
        stem = _safe_dir_name(pdf_path.stem)
        out_subdir = output_dir / stem
        out_subdir.mkdir(parents=True, exist_ok=True)

        print(f"[{idx}/{len(pdfs)}] Converting {pdf_path} -> {out_subdir}")
        _run_marker(pdf_path, out_subdir, extra_args=extra_args)

    # Avoid committing OS-specific files if present.
    ds_store = output_dir / ".DS_Store"
    if ds_store.exists():
        try:
            os.remove(ds_store)
        except OSError:
            pass


if __name__ == "__main__":
    main()

