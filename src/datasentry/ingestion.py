"""Strict UTF-8 CSV ingestion; every accepted cell remains an unmodified string."""

import csv
import io
from pathlib import Path

import pandas as pd

MAX_BYTES = 10 * 1024 * 1024
# csv's default 128 KiB field limit is smaller than our documented upload limit.
csv.field_size_limit(MAX_BYTES)


class CSVInputError(ValueError):
    """An input cannot be safely interpreted as supported CSV."""


def _validate_quotes(text: str) -> None:
    """Reject bare quotes, which Python's strict reader otherwise accepts."""
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                raise CSVInputError("Invalid CSV quoting after a closing quote.")
        elif char == '"':
            if state != "start":
                raise CSVInputError(
                    "Invalid CSV: quotes must start at the beginning of a field."
                )
            state = "quoted"
        elif char in ",\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise CSVInputError("Invalid CSV: a quoted field was not closed.")


def load_csv(content: bytes) -> pd.DataFrame:
    """Parse up to 10 MiB; reject invalid headers/records before constructing pandas."""
    if len(content) > MAX_BYTES:
        raise CSVInputError("The CSV exceeds the 10 MiB (10,485,760 byte) limit.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVInputError(
            "Unsupported encoding. Save the CSV as UTF-8 and try again."
        ) from exc
    if not text.strip():
        raise CSVInputError("The file is empty. Include a header row and CSV data.")
    if "\x00" in text:
        raise CSVInputError("The file contains null bytes and is not supported UTF-8 CSV.")
    _validate_quotes(text)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = next(reader)
        if not headers or any(not name.strip() for name in headers):
            raise CSVInputError("Column names cannot be blank or whitespace-only.")
        # Treat outer-whitespace collisions as ambiguous, but preserve accepted names.
        names = [name.strip() for name in headers]
        if len(set(names)) != len(names):
            raise CSVInputError(
                "Duplicate column names, including outer-whitespace collisions."
            )
        rows = []
        for position, row in enumerate(reader, 1):
            if len(row) != len(headers):
                raise CSVInputError(
                    f"Data row {position} has {len(row)} fields; expected {len(headers)}. "
                    "Add explicit empty cells or fix separators. No records were dropped."
                )
            rows.append(row)
    except (csv.Error, StopIteration) as exc:
        raise CSVInputError(
            "Invalid CSV structure. Check quoting and record separators."
        ) from exc
    return pd.DataFrame(rows, columns=headers, dtype=object)


def load_csv_path(path: str | Path) -> pd.DataFrame:
    """Bound the read even if the file grows after opening."""
    with Path(path).open("rb") as stream:
        return load_csv(stream.read(MAX_BYTES + 1))
