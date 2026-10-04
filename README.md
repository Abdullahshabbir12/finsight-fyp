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

1. **Company & report:** enter the name, ticker, industry, year, statement basis and optional benchmarks. Upload a PDF and click **Process annual report**. Creating a new run replaces the active session; save a run first if you want to keep it.
2. **Document processing:** inspect processing time, page count, sparse-page warnings and the suggested pages. FinSight suggests the primary statements (financial position, profit or loss, cash flows) for your chosen basis plus the share-capital note; it skips analysis, summary and contents pages. Two-page spreads are read as left page then right page. Compare the suggestion with the report's contents page, change it if needed, then click **Extract financial fields**. Selected text goes to the API provider. Limit the selection to the actual statements and relevant notes; processing is limited to 24 bounded text chunks per attempt.
3. **Human verification:** inspect the original number, unit, normalized proposal, source and confidence. For every field, select **accept**, **edit**, or **unavailable**. If editing, enter the final number in the Entry Unit, give evidence text and add a review note. **Unavailable** also needs a note explaining why (for example "not reported as a single line"). If two pages give different values, the Extraction Notes column shows both, with their pages. Page references must exist in this PDF; if an external manual source is used, leave the page blank and identify the source in the note. Use the bulk-accept checkbox only after checking the available values. It never accepts missing or flagged fields. Mark remaining missing fields unavailable, or enter them manually.
4. Click **Save verification**. Unsaved table edits do not change calculations. All rows must be decided. Saving a revised review clears previous calculations and interpretations, so the next analysis uses the new review.
5. **Results & analysis:** review reconciliation warnings and deterministic ratios. Then click **Run AI council & synthesis** (or **Generate demo council & synthesis**). Completed perspectives survive an API failure; retry runs only the missing perspectives and synthesis. If the AI's answer fails a check, FinSight automatically asks again (up to 3 times) and tells the AI what was wrong.
6. Inspect the Overview, Financial Data, Ratios, four analyst tabs, Final Synthesis and Sources / Evidence tabs. References lead back to verified inputs. Use the page viewer and optional original-page image to check context.
7. Download **Markdown**, **PDF**, **full audit JSON**, and **evaluation JSON**. Reports generated before the council finishes are explicitly labeled partial. The PDF and Markdown contain internal evidence links; PDF page references identify pages in the original annual report, which is not embedded in the export.
8. Click **Save run locally** in the sidebar. Use **Open a saved run** later. Saving is explicit, not automatic. The SQLite file is `data/finsight.sqlite3` by default. It contains extracted page text, original proposals, final review records, metrics and analysis; it does not contain API keys or PDF binaries. Original page images are available only while the uploaded PDF remains in that browser session. Reopened runs retain extracted page text and references.

For a report with no usable API response, you can still fill the verification table manually, calculate ratios, export a partial report, and save the run. The demo supports the full council and synthesis offline.

## A two-minute university demo

1. Click **Load synthetic demo**.
2. Open **Human verification**. Read the source examples, then check the bulk-accept box and click **Save verification**.
3. Open **Results & analysis**. The unedited example shows revenue of PKR 1,000 million, net profit of PKR 105 million, ROA of 7%, ROE of about 12.35%, current ratio of 2.00x and debt-to-equity of about 0.47x.
4. Click **Generate demo council & synthesis**, inspect the tabs and download the report.
5. Open **Evaluation** to explain accuracy, completeness and corrections. These are synthetic demonstration metrics, not empirical performance results.

To demonstrate correction tracking, edit revenue to `990000000`, select **edit**, and explain the simulated correction in the review note. Save, recalculate, and inspect the changed ratio and evaluation metrics. Load a fresh synthetic demo to reset the example.

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
