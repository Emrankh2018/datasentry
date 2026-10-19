# DATASENTRY-001 verification receipt

Date: 2026-10-19 (Europe/Istanbul, UTC+03:00).
Scope: initial DataSentry MVP in `Desktop/datasentry`. This receipt records
observed checks, not a release audit or tag.

## Local environment

- Windows, CPython 3.11.16, isolated `.venv`.
- pandas 3.0.6, Streamlit 1.66.0, pytest 9.1.1, Ruff 0.17.1.
- No paid APIs, LLM-backed analysis, cloud databases, or keys used by the app.
- Local AST-only graph navigation; CSV data, reports, environments, and secret
  paths excluded. Graph output is ignored by Git. Graph extraction does not
  verify program behavior.

## Executed checks

| Check | Observed result |
| --- | --- |
| Independent golden fixtures | Counts, row positions, rates, and quartile bounds match `examples/EXPECTED.md`. |
| Full pytest suite | **92 passed in 39.75 seconds**, including the final dashboard export-payload regression test. |
| Dashboard AppTest interactions | Upload/clear, malformed upload, example analysis, category filtering, raw-variant opt-in, uploaded comparison, comparison filters. |
| Ruff check | Passed. |
| Ruff formatting check | Passed. |
| Python imports | Engine, CLI, and app import successfully. Bare app import emits Streamlit's expected missing-runtime-context warnings. |
| CLI smoke | Analyze golden CSV and compare baseline/current into valid JSON reports, exit 0. CLI tests verify invalid-input exit 2 and execution/output-failure exit 1. |
| All bundled examples | 9 accepted CSVs analyzed; 9 analysis reports plus a comparison report parse as JSON. The intentionally malformed example is rejected in parser/CLI tests. |
| Streamlit startup | Server started on `127.0.0.1:8501`; health endpoint returned `ok`. This proves startup only. |
| Real Chrome analysis | Uploaded `golden.csv` through file chooser; observed 10 rows, 5 columns, 10 missing cells (20%), 0 duplicate rows, the three planted findings, and expanded IQR explanation at row 10. |
| Real Chrome comparison | Uploaded baseline/current through both file choosers; observed row counts 5→6, one added/removed column, reordered shared columns, ID missingness +33.333333 points, duplicates +16.666667 points, and heuristic numeric→text difference. |
| Browser visuals | Genuine screenshots in `docs/screenshots/`; fictional fixtures only. |
| Browser comparison saving | **Verified artifact**: `datasentry-comparison.json` was saved by the browser (11,741 bytes); its entire parsed content equals the engine's expected comparison. Moved into ignored `reports/`. The download-event notification timed out, so the artifact, not that notification, is the evidence. |
| Browser analysis saving | **Unverified**: download-event wait timed out and the expected saved analysis artifact was not found. No browser console errors were observed. Export serialization and the dashboard's actual analysis download payload are tested separately. |

## Focused correction pass

- Corrected AppTest selectors that depended on sidebar/main widget traversal
  order. Stable widget keys now select the intended controls.
- Prevented a CLI output from overwriting an input through a hard link; a
  regression test checks that input bytes remain intact.
- Added upload/error/export-wiring coverage and completed Ruff formatting.
- No additional product features were introduced during the correction pass.

## Limits

The heuristic limitations in README apply. Results do not certify domain
correctness. Browser analysis file-save completion is not claimed. GitHub CI
status and remote commit identity must be checked after publishing; this local
receipt alone does not establish them. No release tag is authorized by this
mission.

## User-requested checkpoint

Work stopped at the user's explicit request on 2026-10-19. Implementation and
local verification are saved in a local Git checkpoint. Public repository
creation, push, remote-commit verification, and hosted CI have not been
performed. No release tag was created. Resume only on a new user instruction.
