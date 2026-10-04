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


def statement_pdf(pages_text: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages_text:
        doc.new_page().insert_text((40, 40), text, fontsize=7)
    return doc.tobytes()


AMOUNTS = "\n".join(f"Line item {i}    {i},234,567    {i},111,222" for i in range(1, 21))


def test_suggests_statements_not_analysis_contents_or_wrong_basis():
    pages, _, _ = read_pdf(statement_pdf([
        "Contents\nStatement of Financial Position.......188\nStatement of Profit or Loss.......190",
        "VERTICAL ANALYSIS\nSTATEMENT OF PROFIT OR LOSS\n" + AMOUNTS,           # analysis repeats titles
        "Revenue revenue total assets total assets revenue " * 20,             # keyword-heavy narrative
        "CONSOLIDATED STATEMENT OF FINANCIAL POSITION\nAS AT DECEMBER 31, 2024\n" + AMOUNTS,
        "ASSETS\n" + AMOUNTS,                                                   # untitled second page
        "CONSOLIDATED STATEMENT OF PROFIT OR LOSS\nFOR THE YEAR ENDED DECEMBER 31, 2024\n" + AMOUNTS,
        "STATEMENT OF FINANCIAL POSITION\nAS AT DECEMBER 31, 2024\n" + AMOUNTS,  # standalone set
        "NOTES TO THE FINANCIAL STATEMENTS\nstatement of financial position borrowings 18 8,535,721\n" + AMOUNTS,
        "NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS\nShare capital\nIssued, subscribed and paid-up capital\n258,132,299 Ordinary shares of Rs. 10 each",
        "NOTES TO THE FINANCIAL STATEMENTS\nShare capital\nIssued, subscribed and paid-up capital\n258,132,299 Ordinary shares of Rs. 10 each",
    ]))
    assert candidate_pages(pages, "consolidated") == [4, 5, 6, 9]
    assert candidate_pages(pages, "standalone") == [7, 10]


def test_statement_title_split_over_two_lines():
    pages, _, _ = read_pdf(statement_pdf(["STATEMENT OF\nFINANCIAL POSITION     AS AT JUNE 30, 2024\n" + AMOUNTS]))
    assert candidate_pages(pages, "standalone") == [1]


def test_two_page_spread_is_read_left_then_right():
    doc = pymupdf.open()
    page = doc.new_page(width=1296, height=864)
    for i in range(8):
        page.insert_text((40, 60 + 30 * i), f"Left item {i} 1,00{i},000", fontsize=9)
        # Real spreads rarely share baselines across the fold; offset so text blocks stay separate.
        page.insert_text((700, 75 + 30 * i), f"Right item {i} 2,00{i},000", fontsize=9)
    pages, _, _ = read_pdf(doc.tobytes())
    text = pages[0].text
    assert "Left item 0 1,000,000\n" in text and "Right item" not in text.split("Left item 7")[0]
    assert text.index("Left item 7") < text.index("Right item 0")


def test_portrait_page_is_not_split():
    content = statement_pdf(["Revenue 1,000,000    Cost of sales (600,000)"])
    pages, _, _ = read_pdf(content)
    assert pages[0].text == pymupdf.open(stream=content, filetype="pdf")[0].get_text(sort=True)


def test_size_limit_is_one_hundred_megabytes(monkeypatch):
    from src.pdf import reader
    assert reader.MAX_BYTES == 100 * 1024 * 1024
    monkeypatch.setattr(reader, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="100 MB"):
        read_pdf(b"x" * 11)


def test_title_glued_to_its_date_is_recognised():
    pages, _, _ = read_pdf(statement_pdf(["abbott pakistan / 2025 annual report\nStatement of Financial Positionas at December 31, 2025\n" + AMOUNTS]))
    assert candidate_pages(pages, "standalone") == [1]
    pages, _, _ = read_pdf(statement_pdf(["Statement of financial positions and other narrative\n" + AMOUNTS,
                                          "DIRECT METHOD\nSTATEMENT OF CASH FLOWSFor the year ended 30 June 2024\n" + AMOUNTS]))
    from src.pdf.reader import statement_title
    assert statement_title(pages[0].text) == "" and statement_title(pages[1].text) == ""



def test_bank_reports_are_recognised():
    from src.pdf.reader import looks_like_bank
    bank = [Page(number=1, text="Deposits and other accounts 1,000\nLendings to financial institutions 500\nAdvances - net 900")]
    company = [Page(number=1, text="Trade debts 1,000\nBills payable 200\nStock in trade 300")]
    assert looks_like_bank(bank) and not looks_like_bank(company)
    assert looks_like_bank(company, industry="Commercial banking")
