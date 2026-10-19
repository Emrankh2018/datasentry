# Independent fixture ledger

All records are fictional. Row positions exclude the header. These expectations
are derived by enumerating the CSV records, not by copying engine output.

| File | Independently planted outcome |
| --- | --- |
| clean.csv | 10 rows × 4 columns; no missing cells, repeated rows, type mismatches, text variants, or IQR anomalies. Country legitimately repeats. IDs preserve zeros. |
| missing.csv | 4 × 4 = 16 cells. `a` missing at 2,3; `b` at 1,3; `empty` at 1,2,3,4. Total 8 / 16 = 50%. All 4 rows affected. Per-column rates 0%,50%,50%,100%. |
| duplicates.csv | `(001,A)` at 1,3,6; `(002,B)` at 2,5. 3 repeats after first: 3,5,6 (50%). 5 group members: 1,2,3,5,6. Row 4 is unique. |
| mixed.csv | 9 numeric cells, 1 text at 10; 90% numeric, 1 suspected mismatch. No missing cells. |
| text.csv | Qatar variants at 1,2,3,4: 4 distinct raw variants, one group, 4 affected rows. Oman repeats without variation. |
| outliers.csv | 1…9,100. Inclusive quartiles: Q1=3.25, Q3=7.75, IQR=4.5. Bounds -3.5 and 14.5. One anomaly at 10. |
| golden.csv | 10 × 5 = 50 cells. `empty` is missing on all 10 rows (20% dataset-wide); `NA` is legitimate text. Amount quartiles 12.25 and 16.75, bounds 5.5 and 23.5: anomaly at 10. One country-variant group at 1,2,3,4. Exactly 3 findings, no duplicate records. |
| baseline.csv / current.csv | Rows 5→6. Add `added`, remove `retired`, reorder shared columns id/amount→amount/id. Amount numeric→text (heuristic). ID missing 0/5→2/6 (33.333333 percentage points). Duplicate rate 0/5→1/6 (16.666667 points), repeat at current row 6. No record-identity inference. |
| malformed.csv | Row 1 has 3 fields against a 2-field header: reject the whole file. |

Unsupported encoding, malformed quotes, multiline fields, invalid headers,
empty/header-only files, exact byte boundaries, null tokens, small samples,
zero IQR, nonfinite arithmetic, and privacy cases are constructed in tests.
