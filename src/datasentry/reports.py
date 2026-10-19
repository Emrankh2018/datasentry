"""Stable report serialization; no timestamps or raw records are added."""

import json


def report_json(report: dict) -> str:
    return (
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
