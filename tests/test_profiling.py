import json

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from datasentry import AnalysisConfig, analyze_dataset, load_csv, report_json
from datasentry.profiling import EXAMPLE_LIMIT, classify, detect_text_variants


def column(report, name):
    return next(c for c in report["columns"] if c["name"] == name)


def test_clean_dataset_has_no_findings(example):
    report = analyze_dataset(example("clean.csv"))
    assert report["issues"] == []
    assert report["summary"]["row_count"] == 10
    assert report["summary"]["missing_cell_count"] == 0
    assert column(report, "recorded")["inferred_type"] == "iso_date"
    assert column(report, "id")["inferred_type"] == "identifier"


def test_exact_missing_counts_percentages_positions_and_no_double_count(example):
    report = analyze_dataset(example("missing.csv"))
    summary = report["summary"]
    assert summary["missing_cell_count"] == 8
    assert summary["missing_cell_pct"] == 50
    assert summary["rows_with_missing_count"] == 4
    assert summary["rows_with_missing_examples"] == [1, 2, 3, 4]
    assert [
        (c["name"], c["missing_count"], c["missing_pct"], c["missing_row_positions"])
        for c in report["columns"]
    ] == [
        ("id", 0, 0, []),
        ("a", 2, 50, [2, 3]),
        ("b", 2, 50, [1, 3]),
        ("empty", 4, 100, [1, 2, 3, 4]),
    ]
    missing_issues = [i for i in report["issues"] if i["category"] == "missing"]
    assert len(missing_issues) == 3
    assert sum(i["affected_row_count"] for i in missing_issues) == 8
    assert column(report, "empty")["inferred_type"] == "unknown"


def test_default_na_text_and_opt_in_null_tokens():
    frame = load_csv(b'value\nNA\n NA \nna\nnull\n""\n" \t "\n')
    default = analyze_dataset(frame)
    configured = analyze_dataset(frame, AnalysisConfig(null_tokens=("NA", " null ")))
    assert column(default, "value")["missing_row_positions"] == [5, 6]
    assert column(configured, "value")["missing_row_positions"] == [1, 2, 4, 5, 6]
    assert column(configured, "value")["missing_pct"] == pytest.approx(83.333333)
    assert "NA" not in report_json(configured)


def test_exact_duplicate_definition_counts_excess_and_all_group_members(example):
    report = analyze_dataset(example("duplicates.csv"))
    duplicates = report["duplicates"]
    assert duplicates["count"] == 3
    assert duplicates["rate_pct"] == 50
    assert duplicates["example_row_positions"] == [3, 5, 6]
    assert duplicates["participating_row_count"] == 5
    assert duplicates["participating_example_row_positions"] == [1, 2, 3, 5, 6]
    issue = next(i for i in report["issues"] if i["code"] == "EXACT_DUPLICATE_ROWS")
    assert issue["affected_row_count"] == 3


def test_duplicate_strings_are_not_normalized_and_missing_selected_values_excluded():
    frame = load_csv(b"a,b\nX,1\nx,1\n X ,1\n,1\n ,1\nX,2\n")
    report = analyze_dataset(frame, AnalysisConfig(duplicate_columns=("a", "a")))
    assert report["duplicates"]["count"] == 0
    (selected,) = report["duplicates"]["selected_columns"]
    assert selected["count"] == 1
    assert selected["example_row_positions"] == [6]
    assert selected["participating_row_count"] == 2
    assert selected["eligible_row_count"] == 4
    assert selected["rate_pct"] == 25


def test_repeated_nonunique_country_is_only_a_potential_concern(example):
    report = analyze_dataset(
        example("clean.csv"), AnalysisConfig(duplicate_columns=("country",))
    )
    assert report["duplicates"]["count"] == 0
    assert report["duplicates"]["selected_columns"][0]["count"] == 8
    (issue,) = report["issues"]
    assert issue["code"] == "REPEATED_COLUMN_VALUES"
    assert issue["severity"] == "info"
    assert "not an invalid record" in issue["explanation"]


def test_numeric_mismatch_at_exact_threshold(example):
    report = analyze_dataset(example("mixed.csv"))
    amount = column(report, "amount")
    assert amount["inferred_type"] == "numeric"
    assert amount["dominant_share_pct"] == 90
    assert amount["type_mismatch_count"] == 1
    assert amount["type_mismatch_row_positions"] == [10]
    assert (
        next(i for i in report["issues"] if i["code"] == "TYPE_MISMATCH")["confidence"]
        == "heuristic"
    )


@pytest.mark.parametrize(
    "values,expected",
    [
        (["1", "2", "3", "4"], "unknown"),
        (["1", "2", "3", "4", "5"], "numeric"),
        (["1", "2", "3", "4", "5", "6", "7", "8", "bad", "other"], "mixed"),
        (["1", "2", "3", "4", "bad"], "mixed"),
        (["01/02/2026"] * 5, "text"),
        (["2026-02-30"] * 5, "text"),
        (["2026-02-01"] * 5, "iso_date"),
        (["NaN", "Inf", "-Infinity", "NA", "null"], "text"),
    ],
)
def test_type_evidence_boundaries(values, expected):
    report = analyze_dataset(pd.DataFrame({"value": values}))
    assert column(report, "value")["inferred_type"] == expected
    assert not any(i["code"] == "TYPE_MISMATCH" for i in report["issues"])


def test_iso_dates_calendar_validation_and_mismatch_positions():
    values = [f"2024-02-{i:02}" for i in range(1, 10)] + ["2024-02-30"]
    report = analyze_dataset(pd.DataFrame({"recorded": values}))
    assert column(report, "recorded")["type_mismatch_row_positions"] == [10]
    assert classify("2024-02-29") == "iso_date"
    assert classify("2023-02-29") == "text"
    assert classify("2024-2-01") == "text"


@pytest.mark.parametrize(
    "name,values",
    [
        ("customer_id", [str(n) for n in range(10)]),
        ("customerId", [str(n) for n in range(10)]),
        ("phone", ["+97440000000"] * 10),
        ("postal code", ["12345"] * 10),
        ("SKU", ["part", "PART"] * 5),
        ("value", ["001", "1", "2", "3", "4"]),
        ("value", ["123456789012"] * 5),
    ],
)
def test_identifiers_are_protected_from_type_iqr_and_text_warnings(name, values):
    report = analyze_dataset(pd.DataFrame({name: values}))
    profile = column(report, name)
    assert profile["inferred_type"] == "identifier"
    assert profile["type_mismatch_count"] == 0
    assert profile["outliers"]["status"] == "skipped"
    assert profile["text_variants"]["status"] == "skipped"


def test_explicit_identifier_override():
    frame = pd.DataFrame({"reference_number": ["1", "2", "3", "4", "5"]})
    report = analyze_dataset(frame, AnalysisConfig(identifier_columns=("reference_number",)))
    assert column(report, "reference_number")["reason"].startswith("Explicitly")


def test_iqr_exact_bounds_and_positions(example):
    report = analyze_dataset(example("outliers.csv"))
    outlier = column(report, "amount")["outliers"]
    assert outlier["count"] == 1
    assert outlier["example_row_positions"] == [10]
    assert outlier["lower_bound"] == -3.5
    assert outlier["upper_bound"] == 14.5
    assert outlier["numeric_sample_size"] == 10
    assert (
        next(i for i in report["issues"] if i["code"] == "IQR_ANOMALY")["confidence"]
        == "heuristic"
    )


@pytest.mark.parametrize(
    "values,reason",
    [
        (["1", "2", "3", "4", "5", "6", "100"], "At least 8"),
        (["1"] * 9 + ["100"], "IQR is zero"),
        (["1e308", "-1e308"] * 4, "finite-float"),
    ],
)
def test_iqr_unsuitable_population_skips_explicitly(values, reason):
    report = analyze_dataset(pd.DataFrame({"amount": values}))
    outlier = column(report, "amount")["outliers"]
    assert outlier["status"] == "skipped"
    assert outlier["count"] == 0
    assert reason in outlier["reason"]
    json.loads(report_json(report))


def test_iqr_minimum_is_eight_and_missing_values_are_excluded():
    report = analyze_dataset(
        pd.DataFrame({"amount": ["1", "2", "3", "4", "5", "6", "7", "100", ""]})
    )
    outlier = column(report, "amount")["outliers"]
    assert outlier["status"] == "checked"
    assert outlier["numeric_sample_size"] == 8
    assert outlier["example_row_positions"] == [8]


def test_overflow_and_underflow_report_uncertainty():
    report = analyze_dataset(pd.DataFrame({"amount": ["1e9999", "1e-9999"]}))
    assert column(report, "amount")["inferred_type"] == "unknown"
    (issue,) = report["issues"]
    assert issue["code"] == "NUMERIC_RANGE"
    assert issue["confidence"] == "uncertain"
    assert issue["example_row_positions"] == [1, 2]


def test_text_variant_groups_counts_and_private_report(example):
    report = analyze_dataset(example("text.csv"))
    text = column(report, "country")["text_variants"]
    assert text["group_count"] == 1
    assert text["affected_row_count"] == 4
    assert text["example_row_positions"] == [1, 2, 3, 4]
    (group,) = text["example_groups"]
    assert group["variant_count"] == 4
    assert [v["count"] for v in group["variants"]] == [1, 1, 1, 1]
    assert "Qatar" not in report_json(report)
    local = detect_text_variants(["Qatar", "qatar", "Qatar"], [1, 2, 3], include_values=True)
    assert local["example_groups"][0]["variants"][0] == {
        "value": "Qatar",
        "count": 2,
        "example_row_positions": [1, 3],
    }


def test_whitespace_collapse_unicode_casefold_and_nonvariant_repeat():
    result = detect_text_variants(
        ["New  Town", "new\ttown", "New  Town", "Oman", "Oman"], list(range(1, 6))
    )
    assert result["group_count"] == 1
    assert result["affected_row_count"] == 3
    assert result["example_groups"][0]["variants"][0]["count"] == 2
    assert detect_text_variants(["Straße", "STRASSE"], [1, 2])["group_count"] == 1


def test_caps_keep_total_counts_and_correct_positions():
    frame = pd.DataFrame({"empty": [""] * 51, "country": ["Qatar", "qatar"] * 25 + ["Qatar"]})
    report = analyze_dataset(frame)
    assert column(report, "empty")["missing_count"] == 51
    assert column(report, "empty")["missing_row_positions"] == list(range(1, EXAMPLE_LIMIT + 1))
    text = column(report, "country")["text_variants"]
    assert text["affected_row_count"] == 51
    assert len(text["example_row_positions"]) == EXAMPLE_LIMIT
    assert report["duplicates"]["count"] == 49
    assert len(report["duplicates"]["example_row_positions"]) == EXAMPLE_LIMIT


def test_group_and_variant_caps_do_not_reduce_totals():
    values = [value for n in range(30) for value in (f"town{n}", f"TOWN{n}")]
    result = detect_text_variants(values, list(range(1, 61)))
    assert result["group_count"] == 30
    assert result["affected_row_count"] == 60
    assert len(result["example_groups"]) == 20


def test_header_only_and_all_null_have_no_division_errors():
    report = analyze_dataset(load_csv(b"a,b\n"))
    assert report["summary"]["row_count"] == 0
    assert report["summary"]["missing_cell_pct"] == 0
    assert report["issues"] == []
    report = analyze_dataset(load_csv(b"a,b\n,\n,\n"))
    assert report["summary"]["missing_cell_count"] == 4
    assert report["summary"]["missing_cell_pct"] == 100
    assert report["duplicates"]["count"] == 1
    assert [c["inferred_type"] for c in report["columns"]] == ["unknown", "unknown"]


def test_report_determinism_no_mutation_and_index_independent_positions(example):
    frame = example("missing.csv")
    frame.index = [42, 9, 101, -1]
    original = frame.copy(deep=True)
    first = report_json(analyze_dataset(frame))
    assert first == report_json(analyze_dataset(frame))
    assert json.loads(first)["columns"][1]["missing_row_positions"] == [2, 3]
    assert_frame_equal(frame, original)


def test_report_does_not_include_raw_data_or_null_token_values():
    secret = "FICTIONAL_PRIVATE_SENTINEL"
    frame = pd.DataFrame(
        {"payload": [secret, secret.lower(), "Other"], "amount": ["42", "43", "44"]}
    )
    report = report_json(
        analyze_dataset(frame, AnalysisConfig(null_tokens=("DO_NOT_EXPORT_ME",)))
    )
    for value in (secret, secret.lower(), "Other", "DO_NOT_EXPORT_ME"):
        assert value not in report
    assert '"raw_values_included": false' in report


@pytest.mark.parametrize(
    "frame,config",
    [
        (pd.DataFrame({"a": [1]}), AnalysisConfig()),
        (pd.DataFrame([["1", "2"]], columns=["a", "a"]), AnalysisConfig()),
        (pd.DataFrame({"a": ["1"]}), AnalysisConfig(duplicate_columns=("missing",))),
        (pd.DataFrame({"a": ["1"]}), AnalysisConfig(identifier_columns=("missing",))),
        (pd.DataFrame({" ": ["1"]}), AnalysisConfig()),
    ],
)
def test_engine_rejects_invalid_input_contract(frame, config):
    with pytest.raises(ValueError):
        analyze_dataset(frame, config)


def test_golden_fixture_matches_independent_ledger(example):
    report = analyze_dataset(example("golden.csv"))
    assert report["summary"] == {
        "row_count": 10,
        "column_count": 5,
        "cell_count": 50,
        "missing_cell_count": 10,
        "missing_cell_pct": 20,
        "rows_with_missing_count": 10,
        "rows_with_missing_examples": list(range(1, 11)),
        "duplicate_row_count": 0,
        "duplicate_row_rate_pct": 0,
        "issue_count": 3,
    }
    assert [
        (i["code"], i["column"], i["affected_row_count"], i["example_row_positions"])
        for i in report["issues"]
    ] == [
        ("IQR_ANOMALY", "amount", 1, [10]),
        ("TEXT_VARIANTS", "country", 4, [1, 2, 3, 4]),
        ("EMPTY_COLUMN", "empty", 10, list(range(1, 11))),
    ]
    assert column(report, "amount")["outliers"]["lower_bound"] == 5.5
    assert column(report, "amount")["outliers"]["upper_bound"] == 23.5
    assert column(report, "status")["missing_count"] == 0
