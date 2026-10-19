import pandas as pd
import pytest

from datasentry import AnalysisConfig, compare_datasets, load_csv, report_json


def test_golden_schema_and_quality_drift(example):
    report = compare_datasets(example("baseline.csv"), example("current.csv"))
    structure = report["structure"]
    assert structure["added_columns"] == ["added"]
    assert structure["removed_columns"] == ["retired"]
    assert structure["common_column_order_changed"] is True
    assert structure["column_sequence_changed"] is True
    assert structure["row_count_change"] == 1
    assert structure["confidence"] == "confirmed"
    assert report["inferred_type_differences"] == [
        {
            "column": "amount",
            "baseline_type": "numeric",
            "current_type": "text",
            "confidence": "heuristic",
            "explanation": "Inferred syntax changed; this is not a verified schema error.",
        }
    ]
    id_change = report["missing_rate_changes"][0]
    assert id_change["column"] == "id"
    assert id_change["baseline_pct"] == 0
    assert id_change["current_pct"] == pytest.approx(33.333333)
    assert id_change["change_percentage_points"] == pytest.approx(33.333333)
    assert id_change["direction"] == "regression"
    duplicate = report["duplicate_row_rate_change"]
    assert duplicate["current_pct"] == pytest.approx(16.666667)
    assert duplicate["direction"] == "regression"
    assert report["current"]["duplicates"]["example_row_positions"] == [6]
    assert "No record-level" in " ".join(report["caveats"])


def test_improvements_are_reversed_rate_changes(example):
    report = compare_datasets(example("current.csv"), example("baseline.csv"))
    assert (
        next(c for c in report["missing_rate_changes"] if c["column"] == "id")["direction"]
        == "improvement"
    )
    assert report["duplicate_row_rate_change"]["direction"] == "improvement"


def test_identical_comparison_is_stable_and_unchanged(example):
    frame = example("clean.csv")
    report = compare_datasets(frame, frame)
    assert report["inferred_type_differences"] == []
    assert not report["structure"]["column_sequence_changed"]
    assert all(c["direction"] == "unchanged" for c in report["missing_rate_changes"])
    assert report_json(report) == report_json(compare_datasets(frame, frame))


def test_added_column_alone_is_not_common_column_reordering():
    report = compare_datasets(load_csv(b"a,b\n1,2"), load_csv(b"a,c,b\n1,3,2"))
    assert report["structure"]["column_sequence_changed"]
    assert not report["structure"]["common_column_order_changed"]


def test_disjoint_schema_and_zero_rows():
    report = compare_datasets(load_csv(b"a\n"), load_csv(b"b\n"))
    assert report["missing_rate_changes"] == []
    assert report["structure"]["added_columns"] == ["b"]
    assert report["structure"]["removed_columns"] == ["a"]
    assert report["duplicate_row_rate_change"]["change_percentage_points"] == 0


def test_small_population_type_changes_are_uncertain():
    report = compare_datasets(
        pd.DataFrame({"amount": ["1"] * 5}), pd.DataFrame({"amount": ["1"]})
    )
    assert report["inferred_type_differences"][0]["confidence"] == "uncertain"


def test_configuration_applies_to_both_sides_including_removed_identifiers():
    left = load_csv(b"a,removed\nNA,1")
    right = load_csv(b"a\nNA")
    report = compare_datasets(
        left, right, AnalysisConfig(null_tokens=("NA",), identifier_columns=("removed",))
    )
    assert report["baseline"]["summary"]["missing_cell_count"] == 1
    assert report["current"]["summary"]["missing_cell_count"] == 1
    with pytest.raises(ValueError):
        compare_datasets(left, right, AnalysisConfig(identifier_columns=("absent",)))
