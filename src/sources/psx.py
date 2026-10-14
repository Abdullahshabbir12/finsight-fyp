"""Annual reports from PSX's public financial reports library (financials.psx.com.pk).

The library is the service behind PSX's own "Financials" web page. It is undocumented, so every call is
defensive: failures raise PSXError with a plain message and the app falls back to manual upload.
Requests are polite: an honest User-Agent, at most one request per second, and downloads cached on disk.
"""
import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
import httpx

BASE = "https://financials.psx.com.pk/"
HEADERS = {"User-Agent": "FinSight research prototype (university Accounting & Finance final-year project)"}
MAX_BYTES = 100 * 1024 * 1024
TICKER = re.compile(r"^[A-Z0-9]{1,12}$")
_last_request = 0.0


class PSXError(ValueError):
    """The PSX library could not provide the report; the user can still upload the PDF."""


@dataclass(frozen=True)
class Report:
    ticker: str
    kind: str          # "Annual" or "Quarterly"
    period: str        # "2024" for annual reports, "2024-06-30" for quarterly ones
    posted: str
    doc_id: str

    @property
    def url(self) -> str:
        return f"{BASE}lib/DownloadPDF.php?id={self.doc_id}"


def cache_dir() -> Path:
    path = Path(os.getenv("FINSIGHT_CACHE_DIR", "data/cache/psx"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=httpx.Timeout(120, connect=15), follow_redirects=True)


def _pause() -> None:
    global _last_request
    wait = 1.0 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def list_companies(client: httpx.Client | None = None) -> dict[str, str]:
    """Ticker -> company name, read from the library's company list."""
    _pause()
    try:
        with client or _client() as c:
            response = c.get(BASE)
    except httpx.HTTPError as exc:
        raise PSXError("The PSX financial reports library is not reachable right now. Upload the PDF instead.") from exc
    if response.status_code != 200:
        raise PSXError(f"The PSX library answered with HTTP {response.status_code}. Upload the PDF instead.")
    companies = {}
    for value, name in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', response.text):
        value = value.strip()
        if TICKER.match(value) and name.strip():
            companies[value] = html.unescape(name.strip())
    if not companies:
        raise PSXError("The PSX library page has changed and its company list could not be read. Upload the PDF instead.")
    return companies


def list_reports(ticker: str, client: httpx.Client | None = None) -> list[Report]:
    if not TICKER.match(ticker):
        raise PSXError("Ticker must be letters and digits only, e.g. EFERT.")
    _pause()
    try:
        with client or _client() as c:
            response = c.post(BASE + "annQtrStmts.php", data={"name": "get_comp_data", "smbCode": ticker})
        rows = json.loads(response.text) if response.status_code == 200 else None
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise PSXError("The PSX library did not return a report list. Upload the PDF instead.") from exc
    if not isinstance(rows, list):
        raise PSXError("The PSX library did not return a report list. Upload the PDF instead.")
    reports = []
    for row in rows:
        link = str(row.get("Reports", "")) if isinstance(row, dict) else ""
        doc = re.search(r"DownloadPDF\.php\?id=([A-Za-z0-9-]+)", link)
        kind = re.sub(r"<[^>]+>", "", link).strip()
        if doc and kind in {"Annual", "Quarterly"}:
            reports.append(Report(ticker, kind, str(row.get("period_ended", "")), str(row.get("posting_date", "")), doc.group(1)))
    return reports


def annual_reports(ticker: str, client: httpx.Client | None = None) -> dict[int, Report]:
    """Financial year -> annual report, newest first. Annual entries carry the year as their period."""
    found = {int(r.period): r for r in list_reports(ticker, client) if r.kind == "Annual" and r.period.isdigit()}
    return dict(sorted(found.items(), reverse=True))


def download(report: Report, client: httpx.Client | None = None) -> bytes:
    """The report PDF, from the disk cache when it was fetched before."""
    cached = cache_dir() / f"{report.doc_id}.pdf"
    if cached.exists():
        return cached.read_bytes()
    _pause()
    chunks, size = [], 0
    try:
        with client or _client() as c, c.stream("GET", report.url) as response:
            if response.status_code != 200:
                raise PSXError(f"PSX answered with HTTP {response.status_code} for this report. Upload the PDF instead.")
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise PSXError("This report is larger than 100 MB. Upload only the financial statements instead.")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise PSXError("The download from PSX failed. Check your connection and retry, or upload the PDF instead.") from exc
    content = b"".join(chunks)
    if not content.startswith(b"%PDF"):
        raise PSXError("PSX did not return a PDF for this report. Upload the PDF instead.")
    cached.write_bytes(content)
    return content
