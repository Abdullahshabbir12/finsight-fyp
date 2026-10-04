"""Bounded text extraction; physical PDF page numbers are always one-based."""
from time import perf_counter
import pymupdf
from src.models import Page

KEYWORDS = ("statement of financial position", "balance sheet", "statement of profit",
            "income statement", "statement of cash flows", "cash flow statement",
            "notes to the financial statements", "revenue", "total assets")
MAX_BYTES = 30 * 1024 * 1024
MAX_PAGES = 600


def read_pdf(content: bytes) -> tuple[list[Page], list[str], float]:
    start = perf_counter()
    if len(content) > MAX_BYTES:
        raise ValueError("PDF exceeds the 30 MB prototype limit. Upload a smaller file.")
    warnings = []
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("This PDF is password-protected. Upload an unlocked copy.")
            if not 0 < len(doc) <= MAX_PAGES:
                raise ValueError("Use a PDF with between 1 and 600 pages.")
            pages = [Page(number=i + 1, text=p.get_text(sort=True)) for i, p in enumerate(doc)]
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError("Cannot read this PDF. It may be damaged or not a PDF.") from exc
    sparse = sum(len(p.text.strip()) < 80 for p in pages)
    if sparse:
        warnings.append(f"{sparse} of {len(pages)} pages have little extractable text. Scanned pages, images or tables may need OCR or manual entry; OCR is outside this MVP.")
    return pages, warnings, perf_counter() - start


def candidate_pages(pages: list[Page], limit: int = 12) -> list[int]:
    scores = {p.number: sum(p.text.lower().count(k) for k in KEYWORDS) for p in pages}
    ranked = sorted(pages, key=lambda p: (-scores[p.number], p.number))
    selected = []
    for page in ranked:
        if scores[page.number] > 0 and page.number not in selected:
            selected.append(page.number)
        if len(selected) >= limit:
            break
    # A no-keyword document remains inspectable; never pretend it was fully searched.
    return sorted(selected or [p.number for p in pages[:min(3, limit)]])


def chunk_pages(pages: list[Page], selected: list[int], max_chars: int = 14000) -> list[str]:
    """Split even long pages with overlap; retain physical page identifiers per segment."""
    chunks = []
    for page in pages:
        if page.number not in selected or not page.text.strip():
            continue
        step = max_chars - 600
        for offset in range(0, len(page.text), step):
            text = page.text[offset:offset + max_chars]
            chunks.append(f"[PDF PAGE {page.number}]\n{text}")
    return chunks


def render_page(content: bytes, page_number: int) -> bytes:
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        return doc[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).tobytes("png")
