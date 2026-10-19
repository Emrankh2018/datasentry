"""Small local CLI. Exit 0: completed; 2: invalid input; 1: execution/output failure."""

import argparse
import sys
from pathlib import Path

from datasentry.compare import compare_datasets
from datasentry.ingestion import CSVInputError, load_csv_path
from datasentry.profiling import AnalysisConfig, analyze_dataset
from datasentry.reports import report_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="datasentry", description="Inspect CSV quality locally."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "compare"):
        command = subparsers.add_parser(name)
        if name == "analyze":
            command.add_argument("csv", type=Path)
        else:
            command.add_argument("baseline", type=Path)
            command.add_argument("current", type=Path)
        command.add_argument(
            "-o", "--output", type=Path, help="Write JSON; defaults to stdout."
        )
        command.add_argument(
            "--null-token", action="append", default=[], help="Repeatable; exact after strip."
        )
        command.add_argument(
            "--identifier", action="append", default=[], help="Protect a column; repeatable."
        )
        command.add_argument(
            "--duplicate-column", action="append", default=[], help="Check repeated values."
        )
    args = parser.parse_args(argv)
    config = AnalysisConfig(
        tuple(args.null_token), tuple(args.duplicate_column), tuple(args.identifier)
    )
    paths = [args.csv] if args.command == "analyze" else [args.baseline, args.current]
    try:
        if args.output and any(
            args.output.resolve() == path.resolve()
            or (args.output.exists() and path.exists() and args.output.samefile(path))
            for path in paths
        ):
            print("Invalid input: output must not overwrite an input CSV.", file=sys.stderr)
            return 2
    except (OSError, RuntimeError):
        print("Invalid input: a path could not be resolved.", file=sys.stderr)
        return 2
    try:
        frames = [load_csv_path(path) for path in paths]
    except CSVInputError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "Invalid input: a CSV could not be opened. Check its path and permissions.",
            file=sys.stderr,
        )
        return 2
    try:
        report = (
            analyze_dataset(frames[0], config)
            if args.command == "analyze"
            else compare_datasets(*frames, config=config)
        )
        output = report_json(report)
    except ValueError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("Analysis failed unexpectedly. No input data was changed.", file=sys.stderr)
        return 1
    try:
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
    except (OSError, UnicodeError):
        print(
            "Could not write the report. Check the output destination and permissions.",
            file=sys.stderr,
        )
        return 1
    return 0
