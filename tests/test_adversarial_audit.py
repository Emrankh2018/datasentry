"""Independent DATASENTRY-002 oracles; expectations come from the fixture ledger."""

import csv
import io
import json
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from datasentry import (
    AnalysisConfig,
    CSVInputError,
    analyze_dataset,
    compare_datasets,
    load_csv,
    report_json,
)
from datasentry.ingestion import MAX_BYTES

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def audit_frame(name):
    return load_csv((FIXTURES / name).read_bytes())


def profile(report, name):
    return next(column for column in report["columns"] if column["name"] == name)


def test_independent_missing_fixture_exact_default_counts():
    report = analyze_dataset(audit_frame("missing.csv"))
    assert report["summary"]["missing_cell_count"] == 11
    assert report["summary"]["missing_cell_pct"] == 68.75
    assert report["summary"]["rows_with_missing_examples"] == [1, 2, 3, 4]
    assert [
        (c["missing_count"], c["missing_pct"], c["missing_row_positions"])
        for c in report["columns"]
    ] == [(1, 25, [4]), (3, 75, [1, 2, 4]), (3, 75, [1, 3, 4]), (4, 100, [1, 2, 3, 4])]
    assert len([i for i in report["issues"] if i["category"] == "missing"]) == 4
    assert len(report["issues"]) == 4


def test_independent_null_policy_exact_counts():
    report = analyze_dataset(
        audit_frame("missing.csv"), AnalysisConfig(null_tokens=("NA", "NULL"))
    )
    assert report["summary"]["missing_cell_count"] == 13
    assert report["summary"]["missing_cell_pct"] == 81.25
    assert profile(report, "first")["missing_row_positions"] == [1, 2, 3, 4]
    assert profile(report, "second")["missing_row_positions"] == [1, 2, 3, 4]


@pytest.mark.parametrize(
    "value,missing",
    [
        ("\u00a0", True),
        ("\u2003", True),
        ("\t\r\n", True),
        ("\u202f", True),
        ("\u200b", False),
        ("NA", False),
    ],
)
def test_unicode_missingness_obeys_documented_whitespace_rule(value, missing):
    report = analyze_dataset(pd.DataFrame({"value": [value]}))
    assert report["summary"]["missing_cell_count"] == int(missing)


def test_independent_duplicate_fixture_preserves_raw_equality():
    report = analyze_dataset(
        audit_frame("duplicates.csv"), AnalysisConfig(null_tokens=("NA", "NULL"))
    )
    assert report["duplicates"]["count"] == 2
    assert report["duplicates"]["rate_pct"] == 25
    assert report["duplicates"]["example_row_positions"] == [2, 7]
    assert report["duplicates"]["participating_example_row_positions"] == [1, 2, 5, 7]
    assert report["summary"]["missing_cell_count"] == 8
    assert report["summary"]["missing_cell_pct"] == 50
    assert {(i["code"], i["column"]): i["affected_row_count"] for i in report["issues"]} == {
        ("MISSING_VALUES", "value"): 4,
        ("TEXT_VARIANTS", "value"): 4,
        ("MISSING_VALUES", "category"): 4,
        ("EXACT_DUPLICATE_ROWS", None): 2,
    }


@pytest.mark.parametrize(
    "column,count,positions,rate",
    [
        ("value", 1, [2], 25),
        ("category", 3, [2, 3, 4], 75),
    ],
)
def test_independent_selected_column_denominators(column, count, positions, rate):
    config = AnalysisConfig(null_tokens=("NA", "NULL"), duplicate_columns=(column,))
    (result,) = analyze_dataset(audit_frame("duplicates.csv"), config)["duplicates"][
        "selected_columns"
    ]
    assert result["eligible_row_count"] == 4
    assert result["count"] == count
    assert result["example_row_positions"] == positions
    assert result["rate_pct"] == rate


def test_combined_golden_all_five_planted_findings():
    frame = audit_frame("combined.csv")
    before = frame.copy(deep=True)
    report = analyze_dataset(frame)
    assert report["summary"]["missing_cell_count"] == 5
    assert report["summary"]["missing_cell_pct"] == 10
    assert report["summary"]["duplicate_row_count"] == 0
    assert {
        (i["code"], i["column"]): (i["affected_row_count"], i["example_row_positions"])
        for i in report["issues"]
    } == {
        ("TYPE_MISMATCH", "metric"): (1, [10]),
        ("IQR_ANOMALY", "metric"): (1, [9]),
        ("TYPE_MISMATCH", "event_date"): (1, [10]),
        ("TEXT_VARIANTS", "place"): (5, [1, 2, 3, 4, 5]),
        ("MISSING_VALUES", "optional"): (5, [1, 2, 3, 4, 5]),
    }
    assert len(report["issues"]) == 5
    assert profile(report, "metric")["outliers"]["lower_bound"] == -8
    assert profile(report, "metric")["outliers"]["upper_bound"] == 8
    assert profile(report, "place")["text_variants"]["group_count"] == 2
    assert frame.iloc[0, 0] == "0001"
    assert_frame_equal(frame, before)
    assert report_json(report) == report_json(analyze_dataset(frame))
    serialized = report_json(report)
    for value in ("Doha", "Lusail", "oops", "0001", "02/10/2024"):
        assert value not in serialized
    assert all(
        i["confidence"] == "heuristic" for i in report["issues"] if i["category"] != "missing"
    )


@pytest.mark.parametrize(
    "name,values,inferred",
    [
        ("amount", ["-1.5", "+2.25", ".5", "-0.25", "2e1"], "numeric"),
        ("amount", ["-1", "2", "bad"], "mixed"),
        ("phone_number", ["+97440000000"] * 5, "identifier"),
        ("postal_code", ["10001"] * 5, "identifier"),
        ("amount", ["01", "2", "3", "4", "9999"], "identifier"),
        ("date", ["01/02/2026"] * 5, "text"),
        ("date", ["2026-01-01T12:00:00Z"] * 5, "text"),
        ("amount", [""] * 5, "unknown"),
    ],
)
def test_independent_type_contract_and_known_identifier_tradeoff(name, values, inferred):
    report = analyze_dataset(pd.DataFrame({name: values}))
    assert profile(report, name)["inferred_type"] == inferred
    assert profile(report, name)["type_mismatch_count"] == 0


@pytest.mark.parametrize(
    "values,status,positions,bounds",
    [
        ([str(n) for n in range(8)], "checked", [], (-3.5, 10.5)),
        ([str(n) for n in range(-5, 4)] + ["100"], "checked", [10], (-9.5, 8.5)),
        (["1", "2", "999"], "skipped", [], (None, None)),
        (["5"] * 10, "skipped", [], (None, None)),
        (["5"] * 9 + ["999"], "skipped", [], (None, None)),
        (["", "0", "1", "2", "3", "4", "5", "6", "100"], "checked", [9], (-3.5, 10.5)),
    ],
)
def test_independent_iqr_oracles(values, status, positions, bounds):
    report = analyze_dataset(pd.DataFrame({"amount": values}))
    outliers = profile(report, "amount")["outliers"]
    assert outliers["status"] == status
    assert outliers["example_row_positions"] == positions
    assert (outliers["lower_bound"], outliers["upper_bound"]) == bounds
    assert outliers["count"] == len(positions)


@pytest.mark.parametrize(
    "values,groups,affected",
    [
        (
            ["North  Bay", " north bay ", "NORTH\tBAY", "South Bay", "Southbay", "North-Bay"],
            1,
            3,
        ),
        (["Café", "Cafe\u0301", "Different"], 0, 0),
        (["a", "a", "b", "b"], 0, 0),
        (["A", " a ", "B", " b ", "c"], 2, 4),
    ],
)
def test_independent_text_groups_exclude_legitimate_distinctions(values, groups, affected):
    result = profile(analyze_dataset(pd.DataFrame({"place": values})), "place")["text_variants"]
    assert result["group_count"] == groups
    assert result["affected_row_count"] == affected


@pytest.mark.parametrize("reverse", [False, True])
def test_missing_rate_change_rounds_exact_difference_once(reverse):
    before = load_csv(b"id,value\n1,\n2,x\n3,x\n")
    after = load_csv(b"id,value\n1,\n2,\n3,x\n")
    if reverse:
        before, after = after, before
    result = next(
        c
        for c in compare_datasets(before, after)["missing_rate_changes"]
        if c["column"] == "value"
    )
    assert result["change_percentage_points"] == (-33.333333 if reverse else 33.333333)


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_rate_change_rounds_exact_difference_once(reverse):
    before = load_csv(b"value\na\na\nb\n")
    after = load_csv(b"value\na\na\na\n")
    if reverse:
        before, after = after, before
    result = compare_datasets(before, after)["duplicate_row_rate_change"]
    assert result["change_percentage_points"] == (-33.333333 if reverse else 33.333333)


@pytest.mark.parametrize(
    "before,after,added,removed,order,rows",
    [
        (b"a,b\n", b"b,a,c\n2,1,3\n", ["c"], [], True, 1),
        (b"a,b\n1,2\n", b"a\n", [], ["b"], False, -1),
        (b"a,b\n", b"a,b\n", [], [], False, 0),
    ],
)
def test_independent_structure_and_empty_comparisons(
    before, after, added, removed, order, rows
):
    report = compare_datasets(load_csv(before), load_csv(after))
    assert report["structure"]["added_columns"] == added
    assert report["structure"]["removed_columns"] == removed
    assert report["structure"]["common_column_order_changed"] == order
    assert report["structure"]["row_count_change"] == rows
    assert "record_additions" not in report
    json.loads(report_json(report))


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_csv_roundtrip_with_quoted_controls_and_bom(ending):
    # csv.writer is an independent producer; its quoted payload must survive exactly.
    records = [
        ["id", "payload", "empty"],
        ["0007", 'comma,quote"\r\nnext line', ""],
        ["0008", "\t fictional sentinel \u00a0", "NA"],
    ]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator=ending, quoting=csv.QUOTE_ALL)
    writer.writerows(records)
    actual = load_csv(output.getvalue().encode("utf-8-sig"))
    assert actual.values.tolist() == records[1:]
    assert list(actual.columns) == records[0]


@pytest.mark.parametrize(
    "content",
    [
        b'"a",a\n1,2',
        b'a,b\n1,"value" suffix',
        b'a,b\n1,"unclosed\n',
        b'a,b\n1,"multi\nline"\n2\n',
    ],
)
def test_independent_malformed_csv_never_returns_partial_data(content):
    with pytest.raises(CSVInputError):
        load_csv(content)


def test_multibyte_csv_exact_byte_limit_not_character_limit():
    content = b"a\n" + "é".encode() * ((MAX_BYTES - 2) // 2)
    assert len(content) == MAX_BYTES
    assert len(load_csv(content)) == 1
    with pytest.raises(CSVInputError, match="limit"):
        load_csv(content + "é".encode())


def test_multiline_fixture_positions_are_logical_not_physical():
    frame = load_csv(b'id,note,value\n001,"line one\nline two",x\n002,normal,\n')
    assert profile(analyze_dataset(frame), "value")["missing_row_positions"] == [2]
