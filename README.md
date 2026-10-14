# FinSight

A local Accounting & Finance final-year project prototype. FinSight helps a human analyst review an annual report, verify financial values, calculate ratios, and produce a source-linked research report. It does not make investment decisions or replace professional judgment.

## Start here (no API key needed)

You need **Python 3.12**. Open a terminal in this project's folder.

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

**macOS / Linux:**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Keep this terminal open. Open the local address printed in it, usually http://localhost:8501. Press **Ctrl+C** in the terminal to stop the app.

If you already activated your Python environment, the short version is:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Choose **Load synthetic demo** to start your presentation without uploading a PDF or calling an API. All demo content is labeled **DEMO / SYNTHETIC DATA**. Review the values before calculating. The example is a fictional manufacturing company, not an actual security.

## API setup (recommended: Gemini free tier)

1. Open [Google AI Studio API keys](https://aistudio.google.com/apikey) and sign in with your Google account.
2. Create a key for a project using the **Free** tier. Billing upgrades are not required for the documented free-tier models. Check the project's tier and model quota in AI Studio before sending a report.
3. Find `.env` beside `app.py`. If it does not exist, copy `.env.example` and rename the copy to exactly `.env` (not `.env.txt`).
4. Open `.env` in a text editor and enter:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=paste_your_key_here
GEMINI_MODEL=gemini-3.8-flash
AI_RESPONSE_FORMAT=json_schema
```

5. Save the file, stop the running app with **Ctrl+C**, and run it again. A browser refresh alone does not reload changed environment settings. Never put a key in Python files, screenshots, Git, chat messages or reports.

As checked on October 1, 2026, Google lists a free API tier for Gemini 3.8 Flash and supports Pakistan. This is a published offering, not a guarantee of quota for every account. Check your actual model access and limits in AI Studio. The app uses Google's documented chat-completions compatibility endpoint, requests structured JSON, and still validates every response locally. Live access requires your own key; the automated integration tests use mocked responses.

**Free does not mean unlimited.** Model availability and quotas can change. If you hit a rate limit, wait and retry; the council retains completed perspectives. Start with a small selection of actual statement pages. No provider or paid-model fallback happens automatically. The synthetic demo remains available without a key.

Google's free-tier pricing page says content may be used to improve its products. Use public annual reports for this prototype and do not send confidential documents through the free tier.

### Other supported providers

- **OpenRouter:** set `AI_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL=openrouter/free`, and `AI_RESPONSE_FORMAT=json_object`. Its free model availability and quotas may restrict access.
- **OpenAI (paid API):** set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` to a model available to your account. Use a response format supported by that model. A key alone is not enough; you must select a model.

Provider keys are not interchangeable. The app reads only the key belonging to the selected provider and sends it only to that provider's fixed endpoint.

Selected report text is sent to the configured provider when you request extraction. Council requests send company details, verified values, calculations, evidence and supplied benchmarks. Keys are loaded from environment variables using python-dotenv and are never stored in saved analyses.

## Architecture

One Streamlit process, a local SQLite file, and ordinary Python modules. No vector database, background worker, or authentication service.

```text
app.py                 Streamlit entry point
src/catalog.py         Predefined financial fields
src/models.py          Validated records
src/demo.py            Synthetic teaching dataset
src/pdf/               Page extraction and candidate selection
src/extraction/        Structured AI extraction and unit normalization
src/validation/        Human review gate and accounting checks
src/calculations/      Deterministic ratio definitions and functions
src/ai/                API client, four analyst perspectives, synthesis
src/reporting/         Markdown and PDF exports
src/database/          SQLite snapshots
src/utils/             Evaluation metrics
src/ui/                Workflow and results screens
tests/                Financial, pipeline, and UI tests
```

### How AI text is checked

The AI never types numbers. Where a value belongs in a sentence it writes a reference ID such as `metric:current_ratio`, and Python replaces it with the verified value (for example `0.76x`). Before any AI text is accepted, Python rejects it if it:

- cites a field or metric that is not verified;
- contains typed numbers, investment advice or allegations of fraud;
- contradicts a verified comparison or sign (e.g. "total liabilities exceed total assets" when they do not, or "positive operating cash flow" when it is negative);
- uses evaluative words such as "strong" or "efficient" without user-supplied benchmarks.

Bank-specific guidance (deposits, net interest income) is only given to the AI when the industry is banking. A citation shows where a claim came from; it does not prove the claim, so these checks are deliberately strict.

Python 3.12, Streamlit, PyMuPDF, Pydantic, pandas, SQLite, and pytest follow the requested stack. `httpx` is the small HTTP client for the supported compatible chat APIs. `reportlab` creates PDF exports, and `python-dotenv` loads local environment settings.

## Accounting conventions

- All monetary inputs are stored in **base PKR**, not millions. EPS stays PKR/share; shares stay a count. During verification you type values in the **Entry Unit**, which starts as the statement's own unit (e.g. `184,390,517` with `PKR thousand`); Python does the scaling, so you never add zeros by hand.
- **Expense convention:** cost of sales, finance cost, tax expense and capital expenditure are stored as positive amounts. Statements print them in brackets as deductions, so extraction converts `(54,345,821)` to a positive amount, keeps the raw bracketed value, and shows a note on that row. Every other field keeps its sign: losses, negative operating cash flow and negative equity are preserved.
- ROA, ROE, asset turnover, and receivables turnover use **year-end balances**, because the MVP extracts a single selected year. They are not average-balance ratios.
- Profit margins and cash flow margins can be negative. A nonpositive denominator returns N/A: negative equity does not produce a misleading ROE or debt-to-equity figure. Quick ratio also returns N/A when inventory exceeds current assets.
- Debt is interest-bearing borrowings, not all liabilities. EBIT must be reported or explicitly verified by a human; the model must not derive it from other lines. The same applies to totals that are not explicitly reported.
- One statement basis (consolidated or standalone) and one financial year are selected per run. Industry benchmarks are optional user-supplied context and are not independently verified.
- **Prior year (key fields only):** revenue, net profit, operating cash flow, total assets, equity and trade receivables are also captured from the comparative column (6 extra rows to verify). They give:
  - **Growth:** revenue, net profit and operating cash flow growth = (current − prior) ÷ prior. N/A when the prior year is zero or negative, because a growth rate from a loss or negative base is not meaningful.
  - **Average balances:** return on average assets, return on average equity and average receivables turnover use (opening + closing) ÷ 2.
  - **Profit vs cash-flow divergence:** a warning when net profit growth exceeds operating cash flow growth by more than 25 percentage points (a teaching threshold).
- Financial-quality flags are indicators requiring further review, never findings of fraud. Two years of data give one growth rate, not a trend.

| Metric | Python calculation |
|---|---|
| Gross profit margin | Gross profit / Revenue |
| Operating margin | Operating profit / Revenue |
| Net profit margin | Net profit / Revenue |
| Return on assets | Net profit / Total assets |
| Return on equity | Net profit / Equity |
| Current ratio | Current assets / Current liabilities |
| Quick ratio | (Current assets - Inventory) / Current liabilities |
| Debt to equity | Total debt / Equity |
| Debt ratio | Total liabilities / Total assets |
| Interest coverage | EBIT / Finance cost |
| Operating cash flow margin | Operating cash flow / Revenue |
| Operating cash flow to debt | Operating cash flow / Total debt |
| Asset turnover | Revenue / Total assets |
| Receivables turnover | Revenue / Trade receivables |

The calculation engine uses Python Decimal arithmetic. Rounding happens for display only. Percentage ratios are stored as fractions and displayed as percentages. The LLM receives these calculated values and is instructed not to calculate ratios. AI prose cannot contain numeric literals; cited quantities are rendered from the verified data and calculated metrics by Python. This reduces unsupported numerical claims but does not guarantee that qualitative interpretation is correct.

## Using the workflow

The step bar at the top (**1 · Upload → 2 · Extract → 3 · Verify → 4 · Results → 5 · Evaluate**) shows where you are, every screen starts with a short **What to do here** box, and a **Next** button appears when a step is done. It works the same on a phone.

1. **Upload:** on **📥 Get it from PSX**, type a company name or ticker, pick the financial year and click **Fetch annual report**. FinSight downloads the report from PSX's public financial reports library (financials.psx.com.pk, about 670 companies, annual reports since 2013), fills in the company name, ticker and year, and chooses consolidated or standalone from the statements the report contains. Or use **⬆️ Upload a PDF** for a report you already have; if you pick a basis the report does not contain, FinSight switches and tells you. Non-bank companies only: if the PDF looks like a bank's report, FinSight says so before any AI call.
2. **Extract:** FinSight suggests the primary statements for your basis plus the share-capital note, skipping analysis, summary and contents pages; two-page spreads are read left page then right page. Compare the suggestion with the report's contents page, then click **Extract financial fields**. A summary shows how many values are 🟢 Ready, 🟠 Check and ⚪ Missing.
3. **Verify:** each row shows the AI's value, unit and page. Choose **accept**, **edit** or **unavailable**:
   - **✓ Accept all ready** accepts every 🟢 row; **Mark remaining unavailable** gives the rest one reason. Check accepted values against the PDF before finishing.
   - **Edit** needs evidence (a quote or source) and a **Reason** from the list (wrong number, wrong unit, wrong year, sign, missing, flagged). **Unavailable** needs a reason too. Notes are optional unless you pick *Other*.
   - Type values in the unit shown (e.g. `184,390,517` with PKR thousand). Expenses are positive.
   - **Save progress** keeps unfinished work. **Finish verification** lists every remaining problem at once; ratios and AI analysis only use finished verifications.
   - **Check a field against the PDF**, under the table, shows the quote, extraction notes and the original page image.
4. **Results:** deterministic ratios and growth, then **Run AI council & synthesis** (or **Generate demo council & synthesis**). Completed perspectives survive an API failure, and rejected AI answers are retried automatically with the reason. Download the **PDF**, **Markdown** or **full audit JSON** report.
5. **Evaluate:** extraction outcomes per field, precision and recall, CSV downloads, and the combined table of all saved live runs.

Click **💾 Save run** (top of the page) to keep a run; reopen it from **Open a saved analysis** on the Upload screen. The SQLite file is `data/finsight.sqlite3` by default and holds extracted page text, proposals, reviews, metrics and analysis, never API keys or the PDF itself.

## A two-minute university demo

1. Click **Load synthetic demo**. FinSight opens **3 · Verify**.
2. Click **✓ Accept all ready**, then **Finish verification**, then **Next: results →**.
3. The unedited example shows revenue of PKR 1,000 million, net profit of PKR 105 million, ROA of 7%, ROE of about 12.35%, current ratio of 2.00x and debt-to-equity of about 0.47x, plus revenue growth of about 11%.
4. Click **Generate demo council & synthesis**, inspect the tabs and download the report.
5. Open **5 · Evaluate** to explain the measures. These are synthetic demonstration metrics, not empirical performance results.

To demonstrate correction tracking, in Verify set revenue to **edit**, type `990`, choose the reason **Wrong number**, and finish again. The ratios and evaluation update. Load a fresh demo to reset.

## Evaluation for the FYP

- **Proposal precision:** of the numbers the AI proposed, the share that matched the final verified value (including correct numbers that a check flagged). **Field recall:** of the fields with a verified value, the share where the AI proposed the right number. These two measures separate "the AI read it wrong" from "the AI did not find it".
- **Outcome per field:** correct, correct but flagged, sign corrected, wrong year, wrong value, filled by human, unavailable. Download the per-field CSV for your appendix.
- **All saved live runs:** the Evaluation screen combines every reviewed, non-demo run you saved with **Save run locally**, with CSV downloads per run and per field. Use this for results across several annual reports.
- **Strict accuracy** (shown for continuity): original normalized value and reporting year match the final verified value/year, divided by all fields with a final verified value. A missing extraction entered by a human is a failed extraction in this denominator. Fields marked unavailable are excluded. If no fields can be verified, accuracy is N/A.
- **Extraction completeness:** non-null normalized extracted values divided by all 21 predefined fields. This is separate from correctness.
- **Accepted without changes:** fields with the accept decision. **Edited by user:** fields with the edit decision, including evidence-only edits. **Numeric/year correction count:** verified fields whose original number or year did not match. An evidence-only edit may count as an edit without reducing numeric accuracy.
- **Unavailable and pending fields** are reported separately. Unavailable does not mean zero.
- **PDF/extraction/council/synthesis times:** measured wall-clock processing durations, including failed requests. Total processing excludes analyst waiting and UI rendering. Observed workflow time includes human interaction since loading the current session; reopening a saved run starts a new observed interval.
- **API usage:** requested and actual model, stage, tokens, cost when supplied, request success and duration. Unknown token/cost information stays N/A. Reported cost is only a subtotal when some calls omit cost. A provider response passing JSON parsing may still be rejected by the later evidence/policy checks; inspect completed outputs as well as API success.

For the dissertation, use a separately prepared human reference dataset, review source-page/year/unit accuracy separately, use the same reports and conditions for conventional and assisted runs, and record unavailable fields and retries. Do not treat the bundled demo's accuracy as measured model performance.

## Tests and reproducibility

```bash
.venv/bin/python -m pytest -q
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python`.

Tests cover every ratio's ordinary, missing-input, zero-denominator, negative-denominator and negative-numerator behavior. They also cover unit scaling, source/year/basis rejection, the review gate, reconciliations, evaluation counts, SQLite round trips, API failures, council resume, synthesis, report evidence links, and the complete Streamlit demo workflow. API tests use mocks and do not spend credits.

`requirements.txt` gives compatible version ranges. `requirements-lock.txt` records the exact versions used for the tested build. Install the lock file instead if you need to recreate that environment.

## Known limitations and deliberate scope boundaries

- No OCR: scanned or image-only pages require external OCR or manual entry. PDF text order and table structure may be imperfect.
- Text chunk selection is heuristic and deliberately visible. Missing pages, lost table headers, unfamiliar terminology, units and comparative columns can cause missing or incorrect proposals. Exact source matching catches unsupported quotations but does not establish semantic correctness.
- No automatic derivation of missing extracted fields. Debt totals, gross profit and EBIT may remain unavailable if not explicitly reported. A human may enter a supported figure with an explanation.
- Currency support is PKR only for monetary ratios. Other currencies are rejected for manual review; no FX conversions are performed.
- The PSX financial reports library is an undocumented service behind PSX's own website. FinSight requests politely (one report per click, at most one request a second, downloads cached in `data/cache/psx/`, an honest User-Agent) and falls back to manual upload with a clear message if the library is unreachable or changes.
- Two years at most: prior-year data covers six key fields, so growth is a single year-on-year change, not a trend. Industry-specific bank/insurance ratios and multi-year trend analysis are not implemented. Runs saved before prior-year support show those fields as unavailable.
- Structured JSON is always parsed and validated locally. `AI_RESPONSE_FORMAT=json_schema` is the recommended Gemini setting. For OpenRouter free endpoints, `json_object` may have broader compatibility; some endpoints reject strict schema requests. The app fails visibly and allows retry rather than accepting unstructured text.
- Prompts and output checks reduce unsupported claims and investment-advice language but cannot prove qualitative correctness or eliminate every possible model error. Human review remains essential.
- Local SQLite snapshots keep the original extraction and latest saved review, not a multi-user revision ledger. Save runs and export audit JSON for experiments. No auto-save or cross-device synchronization.
- PDF export uses a simple Latin-font report layout. Non-Latin scripts in company names or long source quotations are better preserved in Markdown/JSON.
- No live news, broad PSX coverage, portfolio management, price prediction, trading, automatic ratings, price targets, authentication, payments, enterprise deployment, vector database or microservices.

## Troubleshooting

| Problem | What to do |
|---|---|
| `python` or `pip` not found | Install Python 3.12, then use the platform-specific commands at the top. On Windows, try `py -3.12`. |
| `No module named streamlit` | Install requirements using the same environment's Python that runs the app. |
| Missing API key | Copy `.env.example` to `.env`, fill the matching provider key and model, save and restart. The synthetic demo needs neither. |
| HTTP 401 | Check the key and AI_PROVIDER setting. |
| HTTP 402/429 | Check the selected provider's model quota and wait before retrying. Gemini limits are visible in AI Studio. Free availability is not guaranteed. |
| HTTP 403 | Check the key's project, API permissions, account eligibility and supported region. |
| HTTP 400/404 or structured JSON rejected | Choose a compatible available model. For Gemini, use `AI_RESPONSE_FORMAT=json_schema`; for OpenRouter, try `json_object`. A failed response is not accepted as financial data. |
| No extracted values | Inspect page text and selected pages. A scanned report needs OCR externally or manual verified entry. |
| Verification will not save | Decide every row. Edited numbers require evidence and a note; the year must match the run. Use plain numbers such as `12500000`, not `12.5m`. |
| N/A ratio | Read the reason in the Ratios tab. Missing inputs or nonpositive denominators are deliberately not guessed. |
| Can't save locally | Check that the project folder is writable, or set `FINSIGHT_DB_PATH` to a writable file path. |
| Browser refresh loses unsaved work | Use Save run locally after meaningful stages; browser session state is temporary. |
| Port 8501 in use | Run `streamlit run app.py --server.port 8502`. |
| Long AI wait | Each API request has a bounded timeout. Fewer selected pages reduce calls. Complete stages are retained when retrying analysis. |

## API and UI documentation

The integration follows [Google's Gemini compatibility documentation](https://ai.google.dev/gemini-api/docs/openai), [OpenRouter structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs) and [Streamlit's editable-table documentation](https://docs.streamlit.io/develop/api-reference/data/st.data_editor). Provider enforcement differs across endpoints, so Pydantic and evidence checks are always applied locally.

Gemini free-tier eligibility and model prices: [pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), and [available regions](https://ai.google.dev/gemini-api/docs/available-regions).
