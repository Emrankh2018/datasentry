import json
import subprocess
import sys
from pathlib import Path

import pytest

from datasentry.cli import main

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "datasentry", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_analyzes_to_stdout():
    result = cli("analyze", "examples/golden.csv")
    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["missing_cell_count"] == 10


def test_cli_compares_to_file(tmp_path):
    target = tmp_path / "report.json"
    result = cli("compare", "examples/baseline.csv", "examples/current.csv", "-o", target)
    assert result.returncode == 0
    assert result.stdout == ""
    assert json.loads(target.read_text(encoding="utf-8"))["structure"]["row_count_change"] == 1


@pytest.mark.parametrize(
    "args",
    [
        ["analyze", "does-not-exist.csv"],
        ["analyze", "examples/malformed.csv"],
        ["analyze", "examples/clean.csv", "--identifier", "absent"],
        ["analyze"],
        ["unknown"],
    ],
)
def test_cli_invalid_input_exit_2(args):
    result = cli(*args)
    assert result.returncode == 2
    assert result.stderr
    assert result.stdout == ""


def test_cli_output_failure_exit_1(tmp_path):
    result = cli("analyze", "examples/clean.csv", "-o", tmp_path / "missing" / "report.json")
    assert result.returncode == 1
    assert "write" in result.stderr


def test_cli_cannot_overwrite_input(tmp_path):
    path = tmp_path / "source.csv"
    original = b"a\n1\n"
    path.write_bytes(original)
    result = cli("analyze", path, "-o", path)
    assert result.returncode == 2
    assert path.read_bytes() == original


def test_cli_cannot_overwrite_hard_link_to_input(tmp_path):
    path = tmp_path / "source.csv"
    target = tmp_path / "report.json"
    original = b"a\n1\n"
    path.write_bytes(original)
    target.hardlink_to(path)
    result = cli("analyze", path, "-o", target)
    assert result.returncode == 2
    assert path.read_bytes() == original


def test_cli_custom_null_tokens_and_column_checks(tmp_path):
    path = tmp_path / "source.csv"
    path.write_bytes(b"a\nNA\nNA\n")
    result = cli("analyze", path, "--null-token", "NA", "--duplicate-column", "a")
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["summary"]["missing_cell_count"] == 2
    assert report["duplicates"]["selected_columns"][0]["count"] == 0


def test_cli_execution_failure_exit_1_without_exposing_raw_data(monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError("FICTIONAL_PRIVATE_DATA")

    monkeypatch.setattr("datasentry.cli.analyze_dataset", fail)
    assert main(["analyze", str(ROOT / "examples/clean.csv")]) == 1
    error = capsys.readouterr().err
    assert "failed unexpectedly" in error
    assert "FICTIONAL_PRIVATE_DATA" not in error
