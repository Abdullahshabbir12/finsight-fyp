"""Bounded text extraction; physical PDF page numbers are always one-based."""
import re
from time import perf_counter
import pymupdf
from src.models import Page

KEYWORDS = ("statement of financial position", "balance sheet", "statement of profit",
            "income statement", "statement of cash flows", "cash flow statement",
            "notes to the financial statements", "revenue", "total assets")
# Titles of the three primary statements that hold every predefined field. A real title starts its line.
TITLE = re.compile(r"^(?:(?:consolidated|unconsolidated|separate|standalone)\s+)?(?:statement of financial position|"
                   r"balance sheet|statement of profit (?:or|and) loss(?: account)?|profit and loss account|income statement|"
                   r"statement of cash flows|cash flow statement)")  # no trailing \b: some PDFs glue "positionas at"
# Pages that repeat statement titles but are not the audited statements themselves.
# Pages labelled "direct method" are supplementary cash-flow summaries in the analysis section (audited statements carry no such label).
NOT_STATEMENT_HEAD = ("analysis", "summary", "six year", "ten year", "highlights", "horizontal", "vertical", "direct method", "graphical")
# Annexures repeat statement titles, e.g. a conventional bank's Islamic banking window; only the page head is checked.
NOT_STATEMENT_TOP = ("annexure", "islamic banking business")
NOT_STATEMENT_LINE = ("....", "notes to", "auditor", "comprise", "audited", "we have", "annexed")
TITLE_FOLLOWERS = ("as at", "as on", "for the year", "for the period", "(", "note", "rupees", "amounts", "rs")
SHARE_NOTE = "issued, subscribed and paid"
AMOUNT = re.compile(r"\(?\d{1,3}(?:,\d{3})+\)?")
MAX_BYTES = 100 * 1024 * 1024
MAX_PAGES = 600


def page_text(page: pymupdf.Page) -> str:
    """Read a two-page spread as left page then right page, so the two columns never interleave."""
    r = page.rect
    if r.width > r.height * 1.2:
        mid = (r.x0 + r.x1) / 2
        blocks = [b for b in page.get_text("blocks") if b[4].strip()]
        crossing = [b for b in blocks if b[0] < mid - 10 and b[2] > mid + 10]
        # A real spread has almost nothing across the fold except a running footer.
        if len(blocks) >= 6 and len(crossing) <= max(2, len(blocks) // 10):
            left = page.get_text(sort=True, clip=pymupdf.Rect(r.x0, r.y0, mid, r.y1))
            right = page.get_text(sort=True, clip=pymupdf.Rect(mid, r.y0, r.x1, r.y1))
            return left.rstrip() + "\n\n" + right
    return page.get_text(sort=True)


def read_pdf(content: bytes) -> tuple[list[Page], list[str], float]:
    start = perf_counter()
    if len(content) > MAX_BYTES:
        raise ValueError("PDF exceeds the 100 MB prototype limit. Upload a smaller file or only the financial statements.")
    warnings = []
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("This PDF is password-protected. Upload an unlocked copy.")
            if not 0 < len(doc) <= MAX_PAGES:
                raise ValueError("Use a PDF with between 1 and 600 pages.")
            pages = [Page(number=i + 1, text=page_text(p)) for i, p in enumerate(doc)]
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError("Cannot read this PDF. It may be damaged or not a PDF.") from exc
    sparse = sum(len(p.text.strip()) < 80 for p in pages)
    if sparse:
        warnings.append(f"{sparse} of {len(pages)} pages have little extractable text. Scanned pages, images or tables may need OCR or manual entry; OCR is outside this MVP.")
    return pages, warnings, perf_counter() - start


def statement_title(text: str) -> str:
    """Return a primary-statement title line, or '' when the page is not a statement page."""
    if any(word in " ".join(text.split()).lower() for word in NOT_STATEMENT_HEAD):
        return ""
    if any(word in " ".join(text[:400].split()).lower() for word in NOT_STATEMENT_TOP):
        return ""
    lines = [" ".join(line.split()).lower() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        # Titles are sometimes broken over two lines ("STATEMENT OF" / "FINANCIAL POSITION").
        pair = line + " " + lines[i + 1] if i + 1 < len(lines) else line
        match = TITLE.match(pair)
        if len(line) <= 90 and match and not any(x in pair for x in NOT_STATEMENT_LINE):
            # A title is followed by its date or column headings, never by a line item.
            rest = pair[match.end():].strip()
            if not rest or rest.startswith(TITLE_FOLLOWERS):
                return pair
    return ""


def title_basis(title: str) -> str:
    if "unconsolidated" in title or "separate" in title:
        return "standalone"
    return "consolidated" if "consolidated" in title else "unlabelled"


def statement_bases(pages: list[Page]) -> set[str]:
    """Which statement sets the report contains: {"consolidated"}, {"standalone"} or both."""
    labels = {title_basis(statement_title(p.text)) for p in pages if len(AMOUNT.findall(p.text)) >= 15 and statement_title(p.text)}
    return {"consolidated" if label == "consolidated" else "standalone" for label in labels}


def bank_note_pages(pages: list[Page], statements: list[int]) -> list[int]:
    """The advances, deposits and capital adequacy notes that follow the chosen statements.

    The statement of financial position prints each line's note number ("Advances 9 ..."), so the note
    heading ("9. ADVANCES") can be found exactly. Notes are searched only up to the next statement set.
    """
    later = [p.number for p in pages if p.number > max(statements) and statement_title(p.text)
             and len(AMOUNT.findall(p.text)) >= 15]
    end = min(later) if later else len(pages) + 1
    section = [p for p in pages if min(statements) < p.number < end]
    lines = lambda page: "\n".join(" ".join(line.split()) for line in page.text.lower().splitlines())
    balance_sheet = next((lines(p) for p in pages if p.number in statements and "financial position" in statement_title(p.text)), "")
    picked = []
    for label, heading, extra in [(r"(?:advances|islamic financing[^\n]{0,40}?)(?:\s*[-–]\s*net)?", r"(?:advances|islamic financing)", 3),
                                  (r"deposits and other accounts", r"deposits and other accounts", 1)]:
        number = re.search(r"\b" + label + r"\s+(\d{1,2})\s+[\d(]", balance_sheet)
        if not number:
            continue
        start = next((p.number for p in section if re.search(r"(?m)^" + number.group(1) + r"\.?\s+" + heading, lines(p))), None)
        if start:
            picked += range(start, start + extra + 1)
    car = next((p.number for p in section if re.search(r"(?m)^\d{1,2}\.?\s+capital adequacy", lines(p))), None)
    if car:
        picked += [car, car + 1]
    return [n for n in dict.fromkeys(picked) if n <= len(pages)]


def candidate_pages(pages: list[Page], basis: str = "consolidated", limit: int = 12, sector: str = "general") -> list[int]:
    """Suggest the primary statement pages for the chosen basis, then the share-capital note.

    Statement pages are dense with amounts and carry a short title line. Analysis and
    summary pages repeat those titles, so they are excluded by their headings.
    """
    amounts = {p.number: len(AMOUNT.findall(p.text)) for p in pages}
    titles = {p.number: statement_title(p.text) for p in pages if amounts[p.number] >= 15}
    titles = {n: t for n, t in titles.items() if t}
    has_consolidated = any(title_basis(t) == "consolidated" for t in titles.values())

    has_standalone = any(title_basis(t) == "standalone" for t in titles.values())

    def matches(label: str) -> bool:
        if basis == "consolidated":
            return label == "consolidated" or (label == "unlabelled" and not has_consolidated)
        # Unlabelled titles are standalone statements, unless the report labels them "unconsolidated" explicitly.
        return label == "standalone" or (label == "unlabelled" and not has_standalone)

    selected = [n for n, t in sorted(titles.items()) if matches(title_basis(t))]
    by_number = {p.number: p for p in pages}
    for n in list(selected):
        # The second page of a statement (e.g. assets after equity and liabilities) has no title.
        nxt = by_number.get(n + 1)
        if nxt and nxt.number not in titles and amounts[nxt.number] >= 15 and "notes to" not in nxt.text[:300].lower():
            selected.append(nxt.number)
    if not selected:
        return keyword_pages(pages, limit)
    if sector == "bank":
        selected += bank_note_pages(pages, [n for n in selected if n in titles])
        limit = max(limit, 18)
    statements = [n for n in selected if n in titles]
    later = [n for n in titles if n > max(statements) and not matches(title_basis(titles[n]))]
    section_end = min(later) if later else len(pages) + 1
    share_notes = [p for p in pages if SHARE_NOTE in p.text.lower() and "ordinary shares" in p.text.lower()]
    # Prefer the note inside the chosen statements' section; note pages do not always repeat "consolidated".
    def other_basis(page: Page) -> bool:
        low = page.text.lower()
        consolidated = "consolidated" in low and "unconsolidated" not in low
        return consolidated if basis == "standalone" else "unconsolidated" in low[:600]
    in_section = [p for p in share_notes if min(statements) < p.number < section_end and not other_basis(p)]
    for p in in_section or share_notes:
        low = p.text.lower()
        label = "consolidated" if "consolidated" in low and "unconsolidated" not in low else "unlabelled"
        if (in_section or matches(label)) and p.number not in selected:
            selected.append(p.number)
            break
    return sorted(set(selected))[:limit]


def keyword_pages(pages: list[Page], limit: int = 12) -> list[int]:
    """Fallback when no statement title is recognised: rank pages by keyword counts."""
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


# Lines that appear in banks' statements and never in a manufacturing or services company's (checked on 7 reports).
BANK_TERMS = ("deposits and other accounts", "lendings to financial institutions", "balances with other banks",
              "due to financial institutions", "mark-up / return / interest earned", "mark-up/return/interest earned",
              "advances - net")
BANK_WARNING = ("This looks like a bank's annual report, but the company type is set to non-financial. Banks do not report "
                "revenue, cost of sales, current assets or inventory, so most fields will be unavailable. Start again with "
                "company type **Bank** (or Detect automatically).")


def looks_like_bank(pages: list[Page], industry: str = "") -> bool:
    if re.search(r"\b(bank|banking|microfinance)\b", industry, re.I):
        return True
    text = " ".join(" ".join(p.text.split()).lower() for p in pages)
    return sum(term in text for term in BANK_TERMS) >= 2


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
