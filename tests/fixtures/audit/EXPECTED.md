# Independently enumerated audit oracles

All data is fictional. These expectations were derived before running the new
audit tests. Positions count logical CSV data records, not physical lines.

| Dataset | Manual expected observations |
| --- | --- |
| missing.csv | 4 rows × 4 columns = 16 cells. `key`: row 4 (1). `first`: 1,2,4 (3). `second`: 1,3,4 (3). `empty`: 1,2,3,4 (4). 11 missing cells = 68.75%, 4 affected rows. Column rates 25%,75%,75%,100%. NBSP, em-space and tab are whitespace; NA and NULL are text. With explicit NULL and NA tokens: first adds row 3, second adds row 2; total 13/16 = 81.25%. Explicit row 4 is entirely missing and remains a record. |
| duplicates.csv | 8 rows. Raw `(A,1)` at 1,2 and `('',NULL)` at 5,7. Excess duplicates 2,7 (2/8 = 25%); all members 1,2,5,7. Whitespace and case variants are distinct. Under NULL/NA missing policy, each column is missing at 5,6,7,8: 8/16 missing cells = 50%. Value variants A/space-A/a form one heuristic group at 1,2,3,4. Exactly four findings without selected-column checks: two missingness findings, one variant finding, one exact-duplicate finding. `value` has 4 eligible rows and one repeat at 2 (25%); `category` has four eligible rows, repeats at 2,3,4 (75%). Empty/space/null-token combinations are not normalized for full-row equality. |
| combined.csv | 10 rows × 5 columns = 50 cells. Five missing optional cells at 1–5: 10% overall, 50% of optional. `NA` at 6–10 remains text. Metric: nine numbers, one mismatch at 10 (90% support). Sorted numeric sample −4,−3,−2,−1,0,1,2,3,40: inclusive Q1=−2, Q3=2, IQR=4, fences −8,8; one anomaly at 9. Dates: nine valid ISO dates, ambiguous string at 10 (suspected mismatch). Place variants: Doha at 1,2,3 and Al Wakrah at 4,5; two groups, 5 affected rows. Unique zero-padded order IDs. Exactly five findings; no duplicate rows. |

Additional constructed oracles:

- Missingness increasing 1/3→2/3 is exactly +100/3 percentage points, rounded
  once to **33.333333**, not the difference between two rounded display values.
  Reversing the datasets gives **−33.333333**.
- Duplicate excess increasing 1/3→2/3 has the same exact rate-change oracle.
- Samples 0…7 have Q1=1.75, Q3=5.25 and fences −3.5,10.5; no anomalies.
- Samples −5…3 plus 100 have Q1=−2.75, Q3=1.75 and fences −9.5,8.5;
  only position 10 is an anomaly.
- NFC/NFD accent equivalence is not promised: only casefold and Unicode
  whitespace collapse are applied. A zero-width space is not whitespace under
  Python's strip/split rule. Neither is counted as an unimplemented defect.
- A column containing `01` is protected as identifier-like. This can hide a
  measurement anomaly; that is the explicitly documented conservative tradeoff.
