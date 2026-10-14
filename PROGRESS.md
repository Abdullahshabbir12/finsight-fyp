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

## October 4: six-report evaluation run (gemini-3.5-flash-lite, free tier)

Reports (non-bank, official company sources): Fauji Cement 2024, Engro Fertilizers 2024, Systems Ltd 2024, Nishat Chunian 2025, Attock Petroleum 2025, Abbott Pakistan 2025. PDFs in `data/` (git-ignored); reports in `output/reports/`; runs saved in the app database.

New problems found and fixed during this run: "Rupees"/"Rs '000"-style units rejected (now mapped, USD and per-share units still rejected); one rejected AI answer stopped extraction of the remaining pages (now only quota/auth/network errors stop it); the model skipped unlabelled subtotals and synonyms such as stock-in-trade (field guidance and subtotal rule added); titles glued to their dates ("positionas at") were not recognised; supplementary "direct method" cash-flow summaries could be suggested. A downloaded "Indus Motor" PDF was an Indian company (lakhs, March year end) and was excluded.

| Company | Proposal precision | Field recall | Strict accuracy | Reviewer additions |
|---|---|---|---|---|
| Fauji Cement 2024 | 100% | 85.7% | 85.7% | 3 |
| Engro Fertilizers 2024 | 100% | 85.7% | 85.7% | 3 |
| Systems Ltd 2024 | 100% | 85.0% | 85.0% | 3 (+1 unavailable: no inventory) |
| Nishat Chunian 2025 | 100% | 90.5% | 90.5% | 2 |
| Attock Petroleum 2025 | 100% | 71.4% | 66.7% | 7 |
| Abbott Pakistan 2025 | 100% | 85.7% | 85.7% | 3 |

Across the six: 105 of 105 AI-proposed numbers correct; 105 of 125 verifiable fields found (84.0%). Misses were concentrated in fields that are unlabelled subtotals or require adding lines (total debt, total liabilities, current liabilities). All 84 ratios matched an independent recalculation from the answer keys, and accounting identities (assets = liabilities + equity, gross profit, profit after tax) held for every key. 75 API calls, all successful.

**Caveat:** verification decisions for these runs were made by Claude from independent answer keys, and every review note says so. For the thesis, a human must confirm each run in the Human verification screen. The manual (conventional analyst) baseline has not been collected.

**196 tests passed.**

## October 4: prior-year key fields

Added prior-year revenue, net profit, operating cash flow, total assets, equity and trade receivables (27 fields in total), growth rates, average-balance ROA/ROE/receivables turnover and the profit-vs-cash-flow growth divergence warning. All six reports were re-run and their saved runs updated in place.

- Prior-year extraction: 35 of 36 values found, all correct (the miss was an unlabelled equity subtotal).
- Across 27 fields: 141 of 141 AI-proposed numbers correct; 141 of 161 verifiable fields found (87.6%).
- All 120 ratios (20 per report) matched an independent recalculation.
- Divergence warning fired for Nishat Chunian and Engro (profit up, operating cash flow negative); Attock's cash-flow growth is N/A because its prior-year cash flow was negative.
- 75 API calls, all successful. **206 tests passed.**

## October 14: fetch annual reports from PSX

New **Get it from PSX** option on the Upload screen: choose a company (about 670, from PSX's financial reports library at financials.psx.com.pk) and a year (annual reports since 2013); FinSight downloads the report, fills in name, ticker and year, and picks the statement basis from the report itself. Manual upload remains, and now switches basis (with a message) when the chosen one is not in the report. Live market prices were not added: PSX's live and delayed feeds require a licence.

Checked live: the Abbott Pakistan 2025 report downloaded from PSX (176 pages, document 273772) produced the same suggested statement pages (106, 107, 108, 110, 111, 121) as the manually downloaded copy. Tests use a fake PSX server and never reach the real site. **226 tests passed.**

**Correction (October 14):** the PSX auto-fetch was removed the same day. PSX's website terms of use prohibit software, robots or other automated tools from navigating or searching PSX websites (financials.psx.com.pk included) and allow only a single personal, non-commercial download. The Upload screen now links to PSX's library for the user to download in their own browser. The repository was made public with an AGPL-3.0 licence, as required for a hosted app that uses PyMuPDF.

## October 15: banks, tested on 10 Pakistani bank reports

Added bank support (company type **Bank**, or detected automatically): a 33-field bank catalogue (27 current-year, 6 prior-year), bank pages (statements plus the advances, deposits and capital adequacy notes found by their note numbers), bank ratios and growth, bank accounting checks and bank rules for the AI analysts. Islamic banks are covered. See **Banks** in the README.

**Test set** (consolidated statements, downloaded from each bank's own website; PDFs in `data/`, git-ignored): MCB 2024, HBL 2024, UBL 2023, NBP 2022, Allied 2025, Bank Alfalah 2022, Bank AL Habib 2022, JS Bank 2024, Meezan 2025 (Islamic), BankIslami 2023 (Islamic). Askari, HabibMetro and Faysal blocked downloads (HTTP 403) and were replaced; Bank Alfalah 2023 (132 MB) is over the upload limit, so 2022 was used. Every one of the 330 values (33 × 10) was read independently from the PDF into an answer key, and accounting identities were checked for each key.

**Extraction, first run versus after fixes** (330 values):

| | First run | After fixes |
|---|---|---|
| Correct | 299 | 310 |
| Wrong | 11 (8 not flagged) | 1 (flagged as a conflict) |
| Missing | 20 | 19 |
| 🟢 Ready values that were wrong | 8 of 274 | 0 of 305 |
| Correct values flagged needlessly | 33 | 3 |

| Bank | Correct | Wrong | Missing |
|---|---|---|---|
| MCB 2024 | 32 | 0 | 1 |
| HBL 2024 | 31 | 0 | 2 |
| UBL 2023 | 32 | 0 | 1 |
| NBP 2022 | 32 | 0 | 1 |
| Allied 2025 | 31 | 0 | 2 |
| Bank Alfalah 2022 | 31 | 0 | 2 |
| Bank AL Habib 2022 | 32 | 0 | 1 |
| JS Bank 2024 | 31 | 1 (flagged) | 1 |
| Meezan 2025 | 26 | 0 | 7 |
| BankIslami 2023 | 32 | 0 | 1 |

Proposal precision 99.7% (310 of 311 proposed numbers correct); field recall 93.9% (96.9% excluding CASA). Missing values: CASA in all 10 (never printed as one figure; the reviewer adds current and savings deposits by design); two non-performing allowances (run before that guidance was sharpened); Allied's lendings (printed "–"); six Meezan balance-sheet lines (model inconsistency: the same page returned all 13 values when run alone). NBP and Bank AL Habib were re-run after the share-count guidance change; the other eight are from the main after-fix run.

Problems found and fixed during this test:

| # | Problem | Fix |
|---|---|---|
| 1 | "Statement of Profit and Loss Account" titles, Islamic banking annexures and graphical pages | Title pattern extended; annexures and graphical pages excluded |
| 2 | Bank notes (advances, deposits, capital adequacy) not suggested; share note missed when it does not repeat "consolidated" | Notes found from note numbers on the balance sheet; share note searched within the chosen section |
| 3 | AI rebuilt quotes without the US-dollar columns, so 14 HBL and 13 JS Bank lines were flagged | The real printed line holding the same label and number is recorded instead, with a note |
| 4 | Equity taken excluding non-controlling interest (HBL, Meezan) | Guidance: NET ASSETS including non-controlling interest |
| 5 | Allowance against non-performing advances taken as the total allowance (UBL, BankIslami) or stored negative | Guidance points to the classification table's Total row; stored positive |
| 6 | "Operating expenses" sub-line taken instead of total non-mark-up expenses (Allied) | Label and guidance name the total line |
| 7 | Provisions sign: a reversal printed without brackets stored positive (Allied); a bracketed charge stored negative (Bank AL Habib) | Python sets the sign from profit before provisions less profit before tax when they match exactly, with a note |
| 8 | Gross advances taken from the Performing column (Allied) or a single line (BankIslami) | Guidance for the Total column; new check: gross advances ≥ net advances + non-performing allowance |
| 9 | Share count read from authorised capital (NBP) or rupee share capital (Bank AL Habib) | Guidance: issued shares only; new check (all companies): net profit ÷ shares must be within half to double reported EPS |

**Ratios:** all 180 bank ratios (18 per bank) matched an independent recalculation from the answer keys. Warnings that fired are genuine: non-performing advances above 10% at UBL and NBP; the profit-before-provisions identity at MCB and Meezan, where share of associates explains the gap (stated in the warning).

**AI council and synthesis** (all 10 completed). Checking the text against the PDFs found, and fixed:

- `metric:net_profit` written for the field `field:net_profit` (HBL, UBL): all three attempts rejected. The prefix is now repaired, because no name is both a field and a metric.
- A value under the wrong label in the synthesis ("total liabilities of" the total assets value, Meezan): new check that a cited field value follows its own label.
- "Provisions increased" with no prior-year provisions figure (Bank AL Habib): direction words are now checked for every line, and rejected when no prior-year value exists.
- "Stable asset quality" without benchmarks (Meezan): stable, sound, resilient, comfortable and prudent added to the evaluative words.
- FinSight's own caveats (benchmarks, bank cash flow) written as uncited facts: relabelled as limitations instead of rejected.
- A capital adequacy figure cited in prose would have shown as "PKR 19" instead of 18.74% (not yet triggered); a provisions reversal now reads "a net reversal of PKR 7.64 billion".

After the fixes, all 680 saved AI claims across the 16 reports (10 banks, 6 companies) pass the current checks. About 450 Gemini free-tier calls were used, all on `gemini-3.5-flash-lite`.

Reports: `output/reports/finsight-bank-*.pdf` and `.md`. Runs saved in the app database.

**Caveat:** verification decisions were made by Claude from independent answer keys, and every review note says so. A human must confirm each run in the Human verification screen before thesis use.
