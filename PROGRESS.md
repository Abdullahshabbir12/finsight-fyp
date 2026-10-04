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
