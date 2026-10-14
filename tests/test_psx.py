"""PSX financial reports library client, against a fake server: no network in tests."""
import json
import httpx
import pytest
from src.sources import psx

HOME = """<select id="country"><option value="">Company Name ...</option>
<option value="EFERT">Engro Fertilizers Limited</option><option value="ABOT">Abbott Laboratories (Pakistan) Limited</option>
<option value="GEMNETS   ">Nets International</option><option value="ABL-FUNDS">-</option><option value="TELE.">Treet</option></select>"""
REPORTS = [
    {"Reports": '<a target="_blank" href="lib/DownloadPDF.php?id=EFERT-ANNUAL-2017">Annual</a>', "period_ended": "2017", "posting_date": "2018-12-27"},
    {"Reports": '<a target="_blank" href="lib/DownloadPDF.php?id=249069">Annual</a>', "period_ended": "2024", "posting_date": "2025-03-03"},
    {"Reports": '<a target="_blank" href="lib/DownloadPDF.php?id=253178">Quarterly</a>', "period_ended": "2025-03-31", "posting_date": "2025-04-30"},
]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FINSIGHT_CACHE_DIR", str(tmp_path / "psx"))
    monkeypatch.setattr(psx, "_pause", lambda: None)


def fake(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_company_list_is_parsed_and_cleaned():
    seen = {}
    def handler(request):
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(200, text=HOME)
    companies = psx.list_companies(fake(handler))
    assert companies == {"EFERT": "Engro Fertilizers Limited", "ABOT": "Abbott Laboratories (Pakistan) Limited",
                         "GEMNETS": "Nets International"}
    assert "FinSight" in psx.HEADERS["User-Agent"]


def test_annual_reports_are_listed_newest_first_without_quarterlies():
    def handler(request):
        assert request.method == "POST" and b"smbCode=EFERT" in request.content and b"get_comp_data" in request.content
        return httpx.Response(200, text=json.dumps(REPORTS))
    reports = psx.annual_reports("EFERT", fake(handler))
    assert list(reports) == [2024, 2017]
    assert reports[2024].doc_id == "249069" and reports[2024].url.endswith("DownloadPDF.php?id=249069")


def test_download_checks_pdf_and_uses_the_cache():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b"%PDF-1.7 fake report")
    report = psx.Report("EFERT", "Annual", "2024", "2025-03-03", "249069")
    assert psx.download(report, fake(handler)) == b"%PDF-1.7 fake report"
    assert psx.download(report, fake(handler)) == b"%PDF-1.7 fake report"
    assert len(calls) == 1  # the second request was served from disk


@pytest.mark.parametrize("response,message", [
    (httpx.Response(200, content=b"<html>login</html>"), "did not return a PDF"),
    (httpx.Response(404, text="missing"), "HTTP 404"),
])
def test_download_failures_are_explained(response, message):
    with pytest.raises(psx.PSXError, match=message):
        psx.download(psx.Report("EFERT", "Annual", "2024", "", "1"), fake(lambda request: response))


def test_oversized_download_is_stopped(monkeypatch):
    monkeypatch.setattr(psx, "MAX_BYTES", 10)
    with pytest.raises(psx.PSXError, match="100 MB"):
        psx.download(psx.Report("EFERT", "Annual", "2024", "", "2"), fake(lambda r: httpx.Response(200, content=b"%PDF" + b"x" * 20)))


def test_unreachable_or_changed_library_fails_gracefully():
    def down(request):
        raise httpx.ConnectError("no route")
    with pytest.raises(psx.PSXError, match="not reachable"):
        psx.list_companies(fake(down))
    with pytest.raises(psx.PSXError, match="changed"):
        psx.list_companies(fake(lambda r: httpx.Response(200, text="<html>new design</html>")))
    with pytest.raises(psx.PSXError, match="report list"):
        psx.list_reports("EFERT", fake(lambda r: httpx.Response(200, text="not json")))
    with pytest.raises(psx.PSXError, match="letters and digits"):
        psx.list_reports("EFERT'; DROP")
