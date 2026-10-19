"""Schema facts and cautious aggregate-quality comparisons; no row identity inference."""

import pandas as pd

from datasentry.profiling import AnalysisConfig, analyze_dataset


def _delta(before: float, after: float) -> dict:
    change = round(after - before, 6)
    return {
        "baseline_pct": before,
        "current_pct": after,
        "change_percentage_points": change,
        "direction": "regression"
        if change > 0
        else "improvement"
        if change < 0
        else "unchanged",
        "confidence": "confirmed",
        "interpretation": "Domain-dependent quality indicator.",
    }


def compare_datasets(
    baseline: pd.DataFrame, current: pd.DataFrame, config: AnalysisConfig | None = None
) -> dict:
    config = config or AnalysisConfig()
    # Explicit identifier overrides may apply to a column present in only one side.
    all_names = set(baseline.columns) | set(current.columns)
    if (set(config.identifier_columns) | set(config.duplicate_columns)) - all_names:
        raise ValueError("A configured column does not exist in either dataset.")

    def analyze(frame):
        return analyze_dataset(
            frame,
            AnalysisConfig(
                null_tokens=config.null_tokens,
                identifier_columns=tuple(
                    c for c in config.identifier_columns if c in frame.columns
                ),
                duplicate_columns=tuple(
                    c for c in config.duplicate_columns if c in frame.columns
                ),
            ),
        )

    before, after = analyze(baseline), analyze(current)
    left, right = list(baseline.columns), list(current.columns)
    common = [c for c in left if c in right]
    left_profiles = {c["name"]: c for c in before["columns"]}
    right_profiles = {c["name"]: c for c in after["columns"]}
    type_changes = []
    for name in common:
        a, b = left_profiles[name], right_profiles[name]
        if a["inferred_type"] != b["inferred_type"]:
            type_changes.append(
                {
                    "column": name,
                    "baseline_type": a["inferred_type"],
                    "current_type": b["inferred_type"],
                    "confidence": "uncertain"
                    if "uncertain" in (a["confidence"], b["confidence"])
                    else "heuristic",
                    "explanation": (
                        "Inferred syntax changed; this is not a verified schema error."
                    ),
                }
            )
    return {
        "report_version": "1.0",
        "kind": "comparison",
        "raw_values_included": False,
        "row_position_convention": before["row_position_convention"],
        "structure": {
            "confidence": "confirmed",
            "added_columns": [c for c in right if c not in left],
            "removed_columns": [c for c in left if c not in right],
            "column_sequence_changed": left != right,
            "common_column_order_changed": common != [c for c in right if c in left],
            "baseline_column_order": left,
            "current_column_order": right,
            "baseline_row_count": len(baseline),
            "current_row_count": len(current),
            "row_count_change": len(current) - len(baseline),
        },
        "inferred_type_differences": type_changes,
        "missing_rate_changes": [
            {
                "column": c,
                **_delta(left_profiles[c]["missing_pct"], right_profiles[c]["missing_pct"]),
            }
            for c in common
        ],
        "duplicate_row_rate_change": _delta(
            before["summary"]["duplicate_row_rate_pct"],
            after["summary"]["duplicate_row_rate_pct"],
        ),
        "caveats": [
            "Rates describe observed datasets; lower missingness or repetition "
            "is not always better.",
            "Duplicate rates use each dataset's full schema; "
            "column changes can affect comparability.",
            "No record-level additions or deletions are inferred "
            "without an explicit unique key.",
            "Type inference is heuristic and depends on population size and column contents.",
        ],
        "baseline": before,
        "current": after,
    }
