import pymupdf
import pytest
from src.models import Page
from src.pdf.reader import read_pdf, candidate_pages, chunk_pages


def test_pdf_pages_and_scan_warning():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Statement of Financial Position 2025\nTotal assets PKR million 1500")
    doc.new_page()
    pages, warnings, elapsed = read_pdf(doc.tobytes())
    assert [p.number for p in pages] == [1, 2]
    assert "Total assets" in pages[0].text
    assert warnings and elapsed >= 0
    assert candidate_pages(pages) == [1]


def test_invalid_pdf():
    with pytest.raises(ValueError, match="Cannot read"):
        read_pdf(b"not a pdf")


def test_long_pages_are_chunked_with_identifiers():
    chunks = chunk_pages([Page(number=7, text="A" * 30000)], [7])
    assert len(chunks) == 3
    assert all(c.startswith("[PDF PAGE 7]") for c in chunks)
    assert not chunk_pages([Page(number=1, text="a")], [2])
