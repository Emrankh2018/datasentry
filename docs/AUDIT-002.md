# DATASENTRY-002 independent audit

Date: 2026-10-19 (Europe/Istanbul, UTC+03:00).

**Release decision: BLOCKED. No v0.1.0 tag.** The required browser JSON download
cannot be captured because Chrome reports: “Your organization blocked this file
because it didn't meet a security policy.” The user supplied a screenshot of
that message. This audit does not bypass the policy or substitute a server
response/serialization test for a completed browser download.

## Baseline and scope

- Existing public repository: https://github.com/Emrankh2018/datasentry
- Initial local and remote main: `b6c853cbd02a5b972c53aa4d319dfcce31725f44`.
  Working tree clean, default branch main, no existing v0.1.0 tag.
- Before source changes: **92 tests passed in 22.84 seconds**, Ruff lint and
  formatting passed. No valid existing test was weakened or removed.
- Architecture confirmed: strict byte ingestion into raw-string pandas frames;
  separate profiling/comparison/JSON modules; argparse CLI; Streamlit display.
  Runtime direct dependencies remain pandas and Streamlit. No product features
  or redesign were added.
- Local AST-only graph and bounded symbol lookup used for source navigation.
  Graph output and CSV/report data remain excluded from indexing/commits.

## Independent accuracy validation

Added **46 adversarial test cases** and three fictional CSV goldens. The manual
[oracle ledger](../tests/fixtures/audit/EXPECTED.md) states counts, denominators,
row positions, quartile calculations, and expected limitations. Expected values
were enumerated independently of the engine. The initial new-test run had 42
passes and four failures, all caused by one arithmetic defect. After correction,
all 46 pass.

| Golden / policy | Independently expected | Observed after correction |
| --- | --- | --- |
| missing.csv, default | 11/16 missing cells, 68.75%; columns 1,3,3,4; all four rows affected; four missingness findings | Exact match, including Unicode whitespace and the explicit all-empty row |
| missing.csv, NA/NULL opt-in | 13/16 missing cells, 81.25%; first, second and empty entirely missing | Exact match; NA/NULL remain text by default |
| duplicates.csv, NA/NULL opt-in | Excess duplicates at 2,7; 2/8=25%; all members 1,2,5,7; eight missing cells; one text-variant group affecting 1–4; four findings | Exact match; whitespace/case/similar missing representations do not become exact duplicates |
| Selected-column repetition | Four eligible rows each; value repeats at 2 (25%), category at 2,3,4 (75%) | Exact match; missing cells excluded from denominators |
| combined.csv | 5/50 missing cells (10%); type mismatch at metric/date row 10; numeric fences −8,8 with anomaly at 9; two text groups, five affected rows; five findings, no duplicate records | Exact match, including confidence labels and raw-value exclusion |

No supported planted detections were missed and no unexpected findings remained
in these golden oracles. This is a bounded fixture result, not a real-world
precision/recall claim. Heuristic suggestions were not counted as confirmed
bad records.

Additional cases cover negative/decimal/scientific numbers, small mixed columns,
phones/postal codes/leading zeros, all-null columns, ambiguous dates, safe IQR
skips, unchanged/disjoint/empty schemas, rate reversals, multiline logical-row
positions, quoted control characters, BOM, CR/LF/CRLF, malformed records, and
the exact multibyte 10 MiB boundary.

### Discrepancy classification

| Finding | Classification / priority | Resolution |
| --- | --- | --- |
| Missing and duplicate rate changes subtracted already-rounded percentages: 1/3→2/3 yielded 33.333334 instead of 33.333333 points | True bug, P2: incorrect final reported decimal | Calculate rates from original counts, subtract before rounding. Four regression cases cover both metrics and directions. |
| pip 24.0 and setuptools 79.0.1 inherited from a fresh Python environment matched advisory records | Build-tool security hygiene, P2; not proof that the running app was exploitable | Upgraded isolated tools to pip 26.2.1/setuptools 84.0.0; documented bootstrap minimums, CI bootstrap and build-backend minimum updated. |
| Analysis browser download had no completed saved artifact | External release-critical verification blocker | Real click starts a download, but organization policy blocks the file. No application export bug has been established and no policy workaround was attempted. |
| Leading-zero measurements can be protected as identifiers; zero-IQR samples can hide isolated extremes; ambiguous uniform dates look like text; NFC/NFD equivalence is not normalized | Expected documented limitations, not new defects | Conservative behavior and skip/uncertainty explanations retained and tested. |

No confirmed P0/P1 implementation defect was found. The mandatory browser-save
gate still blocks release independently of implementation-defect severity.

## Functional and installation verification

- Fresh isolated environment created with `python -m venv`, then the documented
  pip installation. `pip check` found no broken requirements.
- Built a non-editable 0.1.0 wheel and installed it into that environment.
  Imports resolved to installed site-packages; engine, CLI, and app imports
  succeeded. Bare app import emits expected Streamlit context warnings.
- Full installed-wheel suite: **138 passed**. Ruff lint/format passed.
- CLI analysis of the independent combined fixture and baseline/current
  comparison produced valid JSON. Direct subprocess exit codes were 0,0,2 for
  analysis, comparison and malformed input. The installed `datasentry` console
  entry point also passed. The RTK wrapper can normalize nonzero shell status,
  so direct subprocess codes were checked explicitly.
- Original and clean-install Streamlit servers started on loopback. Real Chrome
  upload of combined.csv displayed 10 rows, 5 columns, 5 missing cells (10%)
  and zero repeated rows. Five findings matched the ledger; expanded IQR
  evidence showed data-row position 9. Removing the types category removed its
  two findings while preserving the other three.
- Basic 390×844 responsive check: measured CSS viewport/client/scroll widths
  were all 390; metrics stacked, text wrapped, and the report control fit.
  This is a basic usability smoke check, not exhaustive device certification.
- Analyze button was clicked in the real browser. Chrome DevTools observed
  `Page.downloadWillBegin` with the intended report filename and 10,058 received
  bytes. That is initiation/transfer evidence only. The expected saved JSON
  was not captured. The user first closed the Save As dialog, then reported
  the organization-policy block and supplied the screenshot.
- Analyze browser file capture/parse/privacy validation: **BLOCKED**. Comparison
  browser export was verified in DATASENTRY-001, but **not recaptured and
  validated against this audit's final revision**. Both download payloads are
  covered by automated tests, which do not replace the release's browser gate.
- Chrome internal downloads-page access was rejected by the browser automation
  security policy (HTTP/HTTPS only). Raw CDP download-destination modification
  was unsupported; the supported download-event wait did not complete. No
  browser configuration or security policy was changed.

## Security and privacy findings

- Source review found no application network client, analytics, data execution,
  or upload persistence. The installed Streamlit upload manager holds bytes in
  an in-memory dictionary. Project configuration binds loopback and disables
  usage telemetry. These observations do not establish behavior of every
  possible third-party configuration or deployment.
- Tracked source and new fixtures were reviewed for secret patterns. No secrets
  or private customer data were found in the reviewed material. Fixtures are
  fictional. HTML rendering is restricted to static application CSS/copy;
  CSV values use dataframe/JSON display.
- Parser boundaries, raw-value preservation, input immutability, report privacy,
  deterministic output, and input/output path collision protections are tested.
  No CSV rows or null-token strings are automatically included in JSON.
- A version-specific [OSV batch check](https://google.github.io/osv.dev/post-v1-querybatch/)
  queried 43 installed third-party packages, including tooling. Initially only
  pip/setuptools matched. After isolated tool upgrades, **zero matches** were
  returned, with no pagination. Package/version metadata only was sent; no CSV
  data. This point-in-time database check is not a vulnerability-free guarantee.
- Relevant fixed-version records include [pip package-URL handling](https://osv.dev/vulnerability/GHSA-qwm4-qh6w-59xr)
  (26.2.0) and [setuptools manifest normalization](https://osv.dev/vulnerability/GHSA-h35f-9h28-mq5c)
  (83.0.0). Runtime dependency architecture is unchanged.

## GitHub delivery and release gate

Audit corrections/tests are delivered through the existing repository. Consult
the final commit and [CI runs](https://github.com/Emrankh2018/datasentry/actions/workflows/ci.yml)
for hosted verification. Feature development remains frozen. The repository is
not archived, Git history is not rewritten, and no v0.1.0 tag is created while
the browser gate is blocked.

Remaining release work is limited to using an organization-approved browser
download environment, capturing and validating both real report files against
their displayed state, and then checking final commit CI before an annotated
v0.1.0 tag. Do not disable or bypass security controls to obtain that evidence.
