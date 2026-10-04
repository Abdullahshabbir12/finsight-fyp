# FinSight build log

Built and verified in the requested sequence. No paid API request was made.

| Phase | Implemented | Check before moving on |
|---|---|---|
| 1 | Streamlit shell, upload control, 21-field synthetic dataset, local Python environment | AppTest startup and demo load passed |
| 2 | PyMuPDF page extraction, physical page references, sparse-text warning, page ranking and bounded chunks | PDF extraction, invalid file and chunk tests passed |
| 3 | OpenRouter/OpenAI JSON client, predefined extraction schema, Python unit scaling, evidence/year/basis checks | 17 cumulative tests passed |
| 4 | Editable review table, accept/edit/unavailable decisions, original and reviewed records, strict verification gate | 21 cumulative tests passed |
| 5 | All 14 Decimal-based ratios, N/A reasons and reconciliation warnings | 110 cumulative tests, plus verification-to-results UI smoke passed |
| 6 | Four analyst perspectives, verified reference registry, cited claims and output checks | 118 cumulative tests passed |
| 7 | Eleven-section neutral synthesis, retry after incomplete council | Synthesis and analyst tests passed |
| 8 | Markdown and PDF reports, original/verified values, internal evidence links | Export and PDF-link tests passed |
| 9 | SQLite snapshots, evaluation statistics, API usage, dashboard tabs and non-coder documentation | Full demo AppTest, persistence/evaluation tests, mocked API error/retry tests; live local Streamlit server started |

Final validation details are recorded below after the last checks. Live provider behavior requires a user-supplied API key and an available compatible model. All automated API tests use mocked responses.

## Final checks

- **139 tests passed** on Python 3.12.3, including the complete offline Streamlit workflow and mocked provider failures/retries.
- Python compilation passed for the application, source modules and tests.
- Streamlit started at `http://127.0.0.1:8501`; the browser completed synthetic verification, all ratios, four analyst perspectives and synthesis.
- The final synthetic PDF is 9 pages with 83 internal evidence links. Rendered pages were inspected for readable tables, source references and pagination.
- Dependencies are installed in `.venv/`; exact installed versions are recorded in `requirements-lock.txt`.
- No live API call was attempted without a user-provided key. Configure `.env` to test a real annual report with the selected provider.

## October 1: free-tier provider alternative

- Added Gemini through Google's documented chat-completions compatibility endpoint.
- Recommended setup now uses `AI_PROVIDER=gemini`, `GEMINI_MODEL=gemini-3.8-flash` and structured JSON schema output.
- Prepared local `.env` without overwriting existing credentials; `.env` remains ignored by Git.
- Added actionable access/quota errors and provider isolation tests.
- **146 tests passed**, including the Streamlit demo smoke tests. Gemini request/response checks use mocks; live quota and access still need the user's own key.

## October 4: real-report review (Fauji Cement 2024, Engro Fertilizers 2024)

Two non-bank annual reports were run end to end and every extracted value, ratio and AI claim was checked against an independent reading of the PDF. All ratios were always correct; the problems were in page selection, extraction handling, review usability, evaluation and AI text checks. Fixes:

| # | Problem found | Fix |
|---|---|---|
| 1 | Engro report (34.5 MB) rejected by 30 MB limit | Limit raised to 100 MB (reader and Streamlit config) |
| 2 | Page suggestions contained 0 of the actual statements in both reports | Title-line detection for primary statements, basis matching, untitled continuation pages, share-capital note; analysis/summary/contents/notes pages excluded |
| 3 | Two-page spreads interleaved left and right columns | Landscape spreads read left half then right half |
| 4 | Bracketed expenses stored negative, causing false reconciliation warnings | Cost of sales, finance cost, tax and capex stored positive with a visible note; raw value kept |
| 5 | Conflicts from cash-flow lines (finance cost paid, taxes paid, borrowing proceeds); one wrong value | Prompt rule: each field from its own statement; conflict message shows both values and pages |
| 6 | AI cited the wrong page for a verified quote | Page recorded from the page where the quote was verified, with a note |
| 7 | Verified values typed in base PKR (adding zeros); "unavailable" allowed with no reason | Entry Unit column (defaults to statement unit); unavailable requires a note |
| 8 | Accuracy counted sign fixes, conflict flags and correct abstentions as errors | Per-field outcomes, proposal precision, field recall, per-field CSV, all-runs aggregation |
| 9 | AI stated "total liabilities exceed total assets" (false), used "strong/robust" without benchmarks, copied bank-only rules, placed raw reference IDs in prose, one bad sentence discarded whole output | Comparison/sign contradiction checks and verified comparisons in payload; evaluative-word check; bank rules only for banks; IDs rendered as verified values; malformed IDs rejected; automatic retry with feedback (3 attempts) |
| 10 | Free-tier per-minute limit stopped extraction; daily limit (20 requests/model) gave a vague error | One automatic wait-and-retry for short limits; clear "resets in about N hours" message for daily limits |
| 11 | Formula "(Gross Profit) / Revenue / Sales" read as two divisions; app tests read the real local database | Bracketed labels; tests use a temporary database |

Engro (consolidated, FY2024), same pages, before vs after: clean extracted fields 14 → 18; conflicts 5 → 0; wrong values 1 → 0; proposal precision 89.5% → 100%; field recall 81% → 86% (the remaining 3 were correct abstentions: no EBIT line, debt across several lines, shares in tranches). Post-fix AI text contained no contradicted comparisons and no evaluative words. Note: the post-fix run used `gemini-3.5-flash-lite` for extraction because the `gemini-2.5-flash` daily free quota was exhausted; pages 150–151 were also re-run on `gemini-2.5-flash` with identical clean results.

**183 tests passed** (147 before).
