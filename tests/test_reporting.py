import pymupdf
from src.ai.council import run_council
from src.ai.synthesis import run_synthesis
from src.reporting.export import markdown_report, pdf_report
from tests.test_validation import reviewed_demo


def test_full_report_and_pdf_evidence_links():
    run = reviewed_demo()
    run_council(run)
    run_synthesis(run)
    markdown = markdown_report(run)
    assert 'DEMO / SYNTHETIC DATA' in markdown
    assert '[field:revenue](#field-revenue)' in markdown
    assert '1,000,000,000.00' in markdown
    assert 'Final Neutral Conclusion' in markdown
    content = pdf_report(run)
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        text = ''.join(p.get_text() for p in pdf)
        assert len(pdf) >= 3
        assert "Sources / Evidence" in text
        assert "Final Neutral Conclusion" in text
        assert any(p.get_links() for p in pdf)
