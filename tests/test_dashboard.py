import json
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_dashboard_analyzes_example_and_filters():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    app.radio(key="analysis_source").set_value("Bundled example").run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["10", "5", "10", "0"]
    assert any("EMPTY_COLUMN" in exp.label for exp in app.expander)
    app.multiselect(key="categories").set_value(["outliers"]).run()
    assert not app.exception
    assert any("IQR_ANOMALY" in exp.label for exp in app.expander)
    assert not any("EMPTY_COLUMN" in exp.label for exp in app.expander)
    app.selectbox(key="inspect_column").set_value("country").run()
    app.checkbox(key="raw_variants").check().run()
    assert not app.exception
    assert any("Qatar" in element.value for element in app.json)


def test_dashboard_compares_example_and_filters():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="workspace").set_value("Compare Datasets").run()
    app.radio(key="comparison_source").set_value("Bundled comparison").run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["5", "6", "1", "1"]
    app.multiselect(key="directions").set_value(["improvement"]).run()
    assert not app.exception
    assert any("No shared columns" in item.value for item in app.info)


def test_dashboard_uploads_and_clears_csv():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader(key="analysis_upload").set_value(
        ("sample.csv", b"id,a\n001,\n002,x\n", "text/csv")
    ).run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["2", "2", "1", "0"]
    assert app.dataframe[0].value.iloc[0, 0] == "001"
    app.file_uploader(key="analysis_upload").clear().run()
    assert not app.exception
    assert not app.metric


def test_dashboard_handles_malformed_upload_without_traceback():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader(key="analysis_upload").set_value(
        ("bad.csv", b"a,b\n1,2,3\n", "text/csv")
    ).run()
    assert not app.exception
    assert "Data row 1" in app.error[0].value
    assert not app.metric


def test_dashboard_compares_uploaded_files():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="workspace").set_value("Compare Datasets").run()
    app.file_uploader(key="baseline_upload").set_value(
        ("before.csv", b"a,b\n1,2\n", "text/csv")
    ).run()
    app.file_uploader(key="current_upload").set_value(
        ("after.csv", b"b,a,c\n2,1,3\n", "text/csv")
    ).run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["1", "1", "1", "0"]


def test_dashboard_download_payloads_are_valid_private_reports(monkeypatch):
    captured = []
    original = st.download_button

    def capture(label, data, file_name, mime, **kwargs):
        captured.append((data, file_name, mime))
        return original(label, data, file_name, mime, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio(key="analysis_source").set_value("Bundled example").run()
    assert not app.exception
    payload, name, mime = captured[-1]
    assert name == "datasentry-analysis.json"
    assert mime == "application/json"
    assert json.loads(payload)["summary"]["missing_cell_count"] == 10
    assert "Qatar" not in payload
    app.radio(key="workspace").set_value("Compare Datasets").run()
    app.radio(key="comparison_source").set_value("Bundled comparison").run()
    assert not app.exception
    payload, name, mime = captured[-1]
    assert name == "datasentry-comparison.json"
    assert mime == "application/json"
    assert json.loads(payload)["structure"]["row_count_change"] == 1
    assert '"new"' not in payload
