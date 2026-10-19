"""DataSentry's local Streamlit interface. The engine has no Streamlit dependency."""

from pathlib import Path

import pandas as pd
import streamlit as st

from datasentry import (
    AnalysisConfig,
    CSVInputError,
    analyze_dataset,
    compare_datasets,
    load_csv,
    report_json,
)
from datasentry.profiling import CATEGORIES, detect_text_variants, missing_mask

EXAMPLES = Path(__file__).parent / "examples"

st.set_page_config(page_title="DataSentry · CSV inspector", page_icon="🔎", layout="wide")
st.markdown(
    """<style>
    .stApp { color: #17324D; }
    .block-container { padding-top: 2.4rem; max-width: 1400px; }
    h1 { letter-spacing: -.045em; font-weight: 750 !important; }
    h2 { letter-spacing: -.025em; }
    [data-testid="stMetric"] { border-top: 3px solid #247BA0; padding: .7rem 0; }
    [data-testid="stMetricLabel"] { color: #5C6F7F; }
    [data-testid="stSidebar"] { border-right: 1px solid #DCE6EE; }
    .intro { max-width: 700px; font-size: 1.1rem; color: #5C6F7F; }
    </style>""",
    unsafe_allow_html=True,
)


def read_upload(upload):
    if upload is None:
        return None
    try:
        return load_csv(upload.getvalue())
    except CSVInputError as exc:
        st.error(str(exc))
        return None


def settings(columns: list[str], *, compare: bool = False) -> AnalysisConfig:
    with st.sidebar.expander("Detection settings", expanded=False):
        tokens = st.text_area(
            "Optional null tokens (one per line)",
            help="Case-sensitive after outer whitespace is stripped. NA is text by default.",
        )
        identifiers = st.multiselect(
            "Additional identifier columns",
            columns,
            help="Skip type mismatch, IQR, and text-variant warnings for these columns.",
            key="identifiers",
        )
        duplicate_columns = (
            []
            if compare
            else st.multiselect(
                "Check repeated values in columns",
                columns,
                help="Each column is checked independently. Repetition may be valid.",
                key="duplicate_columns",
            )
        )
    return AnalysisConfig(
        tuple(t for t in tokens.splitlines() if t.strip()),
        tuple(duplicate_columns),
        tuple(identifiers),
    )


def analysis_view(frame: pd.DataFrame, config: AnalysisConfig):
    report = analyze_dataset(frame, config)
    summary = report["summary"]
    metrics = st.columns(4)
    metrics[0].metric("Data rows", f"{summary['row_count']:,}")
    metrics[1].metric("Columns", summary["column_count"])
    metrics[2].metric(
        "Missing cells",
        summary["missing_cell_count"],
        f"{summary['missing_cell_pct']:.2f}%",
        delta_color="off",
    )
    metrics[3].metric(
        "Repeated rows",
        summary["duplicate_row_count"],
        f"{summary['duplicate_row_rate_pct']:.2f}%",
        delta_color="off",
    )
    st.download_button(
        "Download JSON report",
        report_json(report),
        "datasentry-analysis.json",
        "application/json",
    )
    st.caption(
        "Row positions start at 1 after the header. They are not physical CSV line numbers. "
        "Findings may overlap; affected counts must not be added across categories."
    )
    preview, findings, columns_tab = st.tabs(["Data preview", "Findings", "Column profiles"])
    with preview:
        st.subheader("Original values, preserved")
        st.caption(
            "Local preview only. No values are converted, removed, or included in JSON exports."
        )
        displayed = frame.head(50).copy()
        displayed.index = range(1, len(displayed) + 1)
        displayed.index.name = "Data row"
        st.dataframe(displayed, width="stretch")
        st.caption("Showing up to 50 rows.")
    with findings:
        st.subheader("Review the evidence")
        st.caption(
            "Confirmed = observed pattern. Heuristic = plausible concern. "
            "Uncertain = insufficient evidence. A confirmed pattern can still be legitimate."
        )
        categories = st.multiselect(
            "Problem categories", CATEGORIES, default=CATEGORIES, key="categories"
        )
        severity = st.multiselect(
            "Severity", ["warning", "info"], default=["warning", "info"], key="severity"
        )
        visible = [
            i
            for i in report["issues"]
            if i["category"] in categories and i["severity"] in severity
        ]
        if not report["issues"]:
            st.success(
                "No findings under these checks. This does not certify domain correctness."
            )
        elif not visible:
            st.info("No findings match these filters.")
        for item in visible:
            label = (
                f"{item['code']} · {item['column'] or 'Dataset'} · "
                f"{item['affected_row_count']} rows"
            )
            with st.expander(label):
                st.write(f"{item['severity'].capitalize()} / {item['confidence']}")
                st.write(item["explanation"])
                st.write("Example data-row positions:", item["example_row_positions"])
                st.caption("Method: " + item["detection_method"])
                st.write("Suggested action: " + item["suggested_action"])
        st.subheader("Missingness by column")
        chart = pd.DataFrame(
            [{"Column": c["name"], "Missing (%)": c["missing_pct"]} for c in report["columns"]]
        )
        st.bar_chart(chart.set_index("Column"), color="#247BA0")
        st.subheader("Duplicate definition")
        st.write(report["duplicates"]["definition"])
        st.write(
            f"{report['duplicates']['participating_row_count']} rows are in repeated groups; "
            f"{report['duplicates']['count']} are repeats after their first occurrence."
        )
        st.caption("Missing tokens do not normalize raw records for exact-duplicate detection.")
    with columns_tab:
        st.subheader("Column-level evidence")
        rows = [
            {
                "Column": c["name"],
                "Missing": c["missing_count"],
                "Missing (%)": c["missing_pct"],
                "Inferred type": c["inferred_type"],
                "Confidence": c["confidence"],
                "Type mismatches": c["type_mismatch_count"],
                "IQR anomalies": c["outliers"]["count"],
                "Text groups": c["text_variants"]["group_count"],
            }
            for c in report["columns"]
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        selected = st.selectbox("Inspect column", list(frame.columns), key="inspect_column")
        column = next(c for c in report["columns"] if c["name"] == selected)
        st.write(column["reason"])
        st.json(column, expanded=False)
        st.write("IQR check: " + column["outliers"]["reason"])
        if column["text_variants"]["group_count"]:
            if st.checkbox(
                "Show raw text variants locally (may contain sensitive values)",
                key="raw_variants",
            ):
                mask = missing_mask(frame[[selected]], config)[selected]
                valid = [
                    (value, p)
                    for p, (value, absent) in enumerate(
                        zip(frame[selected], mask, strict=True), 1
                    )
                    if not absent
                ]
                groups = detect_text_variants(
                    [v for v, _ in valid], [p for _, p in valid], include_values=True
                )
                st.json(groups)
                st.caption(
                    "Up to 20 groups and 20 variants per group. Counts remain complete. "
                    "Raw variants are excluded from the downloaded report."
                )


def comparison_view(baseline, current, config):
    report = compare_datasets(baseline, current, config)
    structure = report["structure"]
    st.subheader("Schema and population")
    metrics = st.columns(4)
    metrics[0].metric("Baseline rows", len(baseline))
    metrics[1].metric(
        "Current rows", len(current), structure["row_count_change"], delta_color="off"
    )
    metrics[2].metric("Added columns", len(structure["added_columns"]))
    metrics[3].metric("Removed columns", len(structure["removed_columns"]))
    st.download_button(
        "Download comparison JSON",
        report_json(report),
        "datasentry-comparison.json",
        "application/json",
    )
    st.write("Added columns:", structure["added_columns"])
    st.write("Removed columns:", structure["removed_columns"])
    st.write("Column sequence changed:", structure["column_sequence_changed"])
    st.write(
        "Relative order of shared columns changed:", structure["common_column_order_changed"]
    )
    st.caption(
        "Confirmed structural observations. Row-count changes do not establish record identity."
    )
    st.subheader("Missing-value rate changes")
    st.caption(
        "Changes are percentage points. Quality directions assume less missingness is better."
    )
    changes = report["missing_rate_changes"]
    direction = st.multiselect(
        "Show rate changes",
        ["improvement", "regression", "unchanged"],
        default=["improvement", "regression", "unchanged"],
        key="directions",
    )
    filtered = [c for c in changes if c["direction"] in direction]
    if filtered:
        st.dataframe(pd.DataFrame(filtered), hide_index=True, width="stretch")
        chart = pd.DataFrame(filtered).set_index("column")[["baseline_pct", "current_pct"]]
        st.bar_chart(chart, color=["#9CAEBB", "#247BA0"], stack=False)
    else:
        st.info("No shared columns match these filters.")
    st.subheader("Exact-duplicate row rate")
    duplicate = report["duplicate_row_rate_change"]
    st.write(
        f"{duplicate['baseline_pct']:.2f}% → {duplicate['current_pct']:.2f}% "
        f"({duplicate['change_percentage_points']:+.2f} percentage points; "
        f"{duplicate['direction']})"
    )
    st.subheader("Inferred type differences")
    if report["inferred_type_differences"]:
        st.dataframe(
            pd.DataFrame(report["inferred_type_differences"]), hide_index=True, width="stretch"
        )
    else:
        st.info("No inferred type differences in shared columns.")
    st.caption("Type differences are heuristic warnings, not confirmed schema violations.")
    with st.expander("Interpretation and limitations"):
        for caveat in report["caveats"]:
            st.write(caveat)


st.sidebar.title("DataSentry")
st.sidebar.caption("Local CSV quality inspector")
mode = st.sidebar.radio("Workspace", ["Analyze Dataset", "Compare Datasets"], key="workspace")
st.sidebar.divider()
st.sidebar.caption(
    "Your uploads stay in this local process. No analytics, cloud services, or disk cache. "
    "Downloads are created only when you request them."
)
st.title("Know what’s in your CSV.")
st.markdown(
    '<p class="intro">Inspect the evidence before you trust the data. '
    "Find missing cells, repeated records, and patterns that deserve a closer look.</p>",
    unsafe_allow_html=True,
)
st.caption("UTF-8 CSV · 10 MiB per file · Original strings preserved")

if mode == "Analyze Dataset":
    source = st.radio(
        "Data source", ["Upload CSV", "Bundled example"], horizontal=True, key="analysis_source"
    )
    frame = None
    if source == "Upload CSV":
        frame = read_upload(
            st.file_uploader("Choose a CSV", type=["csv"], key="analysis_upload")
        )
    else:
        example = st.selectbox(
            "Example dataset",
            [
                "golden.csv",
                "clean.csv",
                "missing.csv",
                "duplicates.csv",
                "mixed.csv",
                "text.csv",
                "outliers.csv",
            ],
        )
        frame = load_csv((EXAMPLES / example).read_bytes())
        st.info(
            "Fictional bundled data with documented expected outcomes in examples/EXPECTED.md."
        )
    config = settings(list(frame.columns) if frame is not None else [])
    if frame is not None:
        analysis_view(frame, config)
    else:
        st.info("Upload a CSV to begin, or inspect a bundled example with known outcomes.")
else:
    source = st.radio(
        "Data source",
        ["Upload two CSVs", "Bundled comparison"],
        horizontal=True,
        key="comparison_source",
    )
    baseline = current = None
    if source == "Upload two CSVs":
        left, right = st.columns(2)
        with left:
            baseline = read_upload(
                st.file_uploader("Baseline CSV", type=["csv"], key="baseline_upload")
            )
        with right:
            current = read_upload(
                st.file_uploader("Current CSV", type=["csv"], key="current_upload")
            )
    else:
        baseline = load_csv((EXAMPLES / "baseline.csv").read_bytes())
        current = load_csv((EXAMPLES / "current.csv").read_bytes())
    columns = list(
        dict.fromkeys(
            c for frame in (baseline, current) if frame is not None for c in frame.columns
        )
    )
    config = settings(columns, compare=True)
    if baseline is not None and current is not None:
        comparison_view(baseline, current, config)
    else:
        st.info("Choose both CSVs to compare their structure and quality rates.")
