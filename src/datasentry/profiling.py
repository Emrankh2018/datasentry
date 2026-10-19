"""Deterministic, conservative quality checks on raw-string data frames."""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import quantiles

import pandas as pd

EXAMPLE_LIMIT = 20
MIN_TYPE_SAMPLE = 5
DOMINANT_THRESHOLD = 0.9
MIN_OUTLIER_SAMPLE = 8
NUMERIC = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$", re.ASCII)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
LEADING_ZERO = re.compile(r"^[+-]?0\d+$", re.ASCII)
IDENTIFIER_WORDS = {
    "id",
    "ids",
    "identifier",
    "sku",
    "phone",
    "telephone",
    "mobile",
    "postal",
    "postcode",
    "zip",
    "zipcode",
    "code",
    "isbn",
    "uuid",
    "barcode",
    "iban",
    "account",
    "reference",
    "ean",
    "ssn",
}
CATEGORIES = ["missing", "duplicates", "types", "outliers", "text"]


@dataclass(frozen=True)
class AnalysisConfig:
    """Null tokens are exact, case-sensitive matches after stripping outer whitespace."""

    null_tokens: tuple[str, ...] = ()
    duplicate_columns: tuple[str, ...] = ()
    identifier_columns: tuple[str, ...] = ()


def percentage(count: int, total: int) -> float:
    return round(100 * count / total, 6) if total else 0.0


def row_examples(mask) -> list[int]:
    """Position-based, independent of the pandas index label."""
    result = []
    for position, affected in enumerate(mask, 1):
        if affected:
            result.append(position)
            if len(result) == EXAMPLE_LIMIT:
                break
    return result


def issue(
    code,
    category,
    severity,
    column,
    count,
    rows,
    explanation,
    method,
    action,
    confidence="confirmed",
) -> dict:
    return {
        "code": code,
        "category": category,
        "severity": severity,
        "scope": "column" if column is not None else "dataset",
        "column": column,
        "affected_row_count": int(count),
        "example_row_positions": rows[:EXAMPLE_LIMIT],
        "explanation": explanation,
        "detection_method": method,
        "suggested_action": action,
        "confidence": confidence,
    }


def missing_mask(frame: pd.DataFrame, config: AnalysisConfig) -> pd.DataFrame:
    tokens = {token.strip() for token in config.null_tokens}
    return frame.apply(
        lambda col: col.map(lambda value: not value.strip() or value.strip() in tokens)
    )


def identifier_reason(name: str, values: list[str], forced: tuple[str, ...] = ()) -> str | None:
    if name in forced:
        return "Explicitly marked as an identifier."
    split_name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    words = set(re.findall(r"[a-z0-9]+", split_name.casefold()))
    if words & IDENTIFIER_WORDS:
        return "Column name suggests an identifier."
    if any(LEADING_ZERO.fullmatch(value.strip()) for value in values):
        return "An integer-like value has leading zeros."
    long_digits = sum(bool(re.fullmatch(r"\+?[0-9]{12,}", value.strip())) for value in values)
    if values and long_digits / len(values) >= DOMINANT_THRESHOLD:
        return "Most values are long digit sequences; they may be identifiers."
    return None


def classify(value: str) -> str:
    value = value.strip()
    if NUMERIC.fullmatch(value):
        number = float(value)
        # Underflow and overflow cannot safely participate in finite-float statistics.
        nonzero_literal = any(c in "123456789" for c in value.lower().split("e")[0])
        if not math.isfinite(number) or (number == 0 and nonzero_literal):
            return "unsupported_numeric"
        return "numeric"
    if ISO_DATE.fullmatch(value):
        try:
            date.fromisoformat(value)
            return "iso_date"
        except ValueError:
            pass
    return "text"


def profile_type(name: str, values: list[str], config: AnalysisConfig) -> dict:
    reason = identifier_reason(name, values, config.identifier_columns)
    counts = dict(sorted(Counter(classify(value) for value in values).items()))
    if reason:
        return {
            "inferred_type": "identifier",
            "confidence": "heuristic",
            "reason": reason,
            "class_counts": counts,
            "dominant_share_pct": None,
        }
    if not values:
        return {
            "inferred_type": "unknown",
            "confidence": "uncertain",
            "reason": "No non-missing values.",
            "class_counts": {},
            "dominant_share_pct": None,
        }
    dominant = max(counts, key=counts.get)
    support = counts[dominant]
    reliable = (
        len(values) >= MIN_TYPE_SAMPLE
        and support >= MIN_TYPE_SAMPLE
        and support / len(values) >= DOMINANT_THRESHOLD
        and dominant != "unsupported_numeric"
    )
    inferred = dominant if reliable else "mixed" if len(counts) > 1 else "unknown"
    return {
        "inferred_type": inferred,
        "confidence": "heuristic" if reliable else "uncertain",
        "reason": (
            "At least 5 matching values and 90% agreement among non-missing cells."
            if reliable
            else "Insufficient evidence for a reliable dominant type."
        ),
        "class_counts": counts,
        "dominant_share_pct": percentage(support, len(values)),
    }


def detect_outliers(values: list[str], positions: list[int], profile: dict) -> dict:
    """Tukey fences using linearly interpolated quartiles (inclusive quantiles)."""
    result = {
        "status": "skipped",
        "reason": "",
        "count": 0,
        "example_row_positions": [],
        "lower_bound": None,
        "upper_bound": None,
        "numeric_sample_size": 0,
    }
    if profile["inferred_type"] != "numeric":
        result["reason"] = "No reliable numeric type, or the column is identifier-like."
        return result
    samples = [
        (float(v.strip()), p)
        for v, p in zip(values, positions, strict=True)
        if classify(v) == "numeric"
    ]
    result["numeric_sample_size"] = len(samples)
    if len(samples) < MIN_OUTLIER_SAMPLE:
        result["reason"] = "At least 8 finite numeric observations are required."
        return result
    q1, _, q3 = quantiles([v for v, _ in samples], n=4, method="inclusive")
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    if not all(math.isfinite(v) for v in (q1, q3, iqr, lower, upper)):
        result["reason"] = "Numeric range exceeds safe finite-float IQR arithmetic."
        return result
    if iqr == 0:
        result["reason"] = (
            "IQR is zero; fences would overstate certainty. Review the distribution."
        )
        return result
    affected = [p for value, p in samples if value < lower or value > upper]
    result.update(
        status="checked",
        reason="1.5 × IQR fences; statistical anomalies, not errors.",
        count=len(affected),
        example_row_positions=affected[:EXAMPLE_LIMIT],
        lower_bound=lower,
        upper_bound=upper,
    )
    return result


def detect_text_variants(
    values: list[str], positions: list[int], *, include_values: bool = False
) -> dict:
    """Group by collapsed Unicode whitespace + casefold; retain raw variants locally."""
    groups = defaultdict(lambda: defaultdict(list))
    for value, position in zip(values, positions, strict=True):
        canonical = " ".join(value.split()).casefold()
        groups[canonical][value].append(position)
    count = 0
    affected = []
    examples = []
    group_count = 0
    for variants in groups.values():
        if len(variants) < 2:
            continue
        group_count += 1
        group_rows = sorted(p for rows in variants.values() for p in rows)
        count += len(group_rows)
        affected.extend(group_rows)
        if len(examples) < EXAMPLE_LIMIT:
            details = []
            for value, rows in list(variants.items())[:EXAMPLE_LIMIT]:
                variant = {"count": len(rows), "example_row_positions": rows[:EXAMPLE_LIMIT]}
                if include_values:
                    variant["value"] = value
                details.append(variant)
            examples.append(
                {
                    "variant_count": len(variants),
                    "affected_row_count": len(group_rows),
                    "example_row_positions": group_rows[:EXAMPLE_LIMIT],
                    "variants": details,
                }
            )
    return {
        "status": "checked",
        "group_count": group_count,
        "affected_row_count": count,
        "example_row_positions": sorted(affected)[:EXAMPLE_LIMIT],
        "example_groups": examples,
    }


def _validate_frame(frame: pd.DataFrame, config: AnalysisConfig) -> None:
    if not len(frame.columns) or not frame.columns.is_unique:
        raise ValueError("Analysis requires at least one uniquely named column.")
    if any(not isinstance(name, str) or not name.strip() for name in frame.columns):
        raise ValueError("Analysis requires nonblank string column names.")
    for column in frame.columns:
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(
                "Analysis requires raw strings. Use load_csv to preserve CSV values."
            )
    unknown = (set(config.duplicate_columns) | set(config.identifier_columns)) - set(
        frame.columns
    )
    if unknown:
        raise ValueError("A configured column does not exist in the dataset.")


def analyze_dataset(frame: pd.DataFrame, config: AnalysisConfig | None = None) -> dict:
    """Return aggregate, JSON-safe metrics; never mutate or export raw input cells."""
    config = config or AnalysisConfig()
    _validate_frame(frame, config)
    missing = missing_mask(frame, config)
    rows, columns = frame.shape
    issues = []
    profiles = []
    for column in frame.columns:
        mask = missing[column]
        missing_count = int(mask.sum())
        valid = [
            (value, pos)
            for pos, (value, is_missing) in enumerate(zip(frame[column], mask, strict=True), 1)
            if not is_missing
        ]
        values = [value for value, _ in valid]
        positions = [pos for _, pos in valid]
        profile = profile_type(column, values, config)
        outliers = detect_outliers(values, positions, profile)
        text = (
            {
                "status": "skipped",
                "reason": "Identifier-like column.",
                "group_count": 0,
                "affected_row_count": 0,
                "example_row_positions": [],
                "example_groups": [],
            }
            if profile["inferred_type"] == "identifier"
            else detect_text_variants(values, positions)
        )
        mismatch_positions = []
        if profile["inferred_type"] in ("numeric", "iso_date"):
            mismatch_positions = [
                p for v, p in valid if classify(v) != profile["inferred_type"]
            ]
        entry = {
            "name": column,
            "missing_count": missing_count,
            "missing_pct": percentage(missing_count, rows),
            "missing_row_positions": row_examples(mask),
            "non_missing_count": len(values),
            **profile,
            "type_mismatch_count": len(mismatch_positions),
            "type_mismatch_row_positions": mismatch_positions[:EXAMPLE_LIMIT],
            "outliers": outliers,
            "text_variants": text,
        }
        profiles.append(entry)
        if missing_count:
            issues.append(
                issue(
                    "EMPTY_COLUMN" if missing_count == rows else "MISSING_VALUES",
                    "missing",
                    "warning",
                    column,
                    missing_count,
                    row_examples(mask),
                    "Cells are empty, whitespace-only, or match an explicit null token.",
                    "Blank/whitespace check plus optional exact stripped null-token matching.",
                    "Confirm whether these cells are required; repair at the source if needed.",
                )
            )
        if mismatch_positions:
            issues.append(
                issue(
                    "TYPE_MISMATCH",
                    "types",
                    "warning",
                    column,
                    len(mismatch_positions),
                    mismatch_positions,
                    "Values differ from a conservatively inferred dominant type.",
                    "At least 5 supporting values and 90% non-missing agreement.",
                    "Review the listed positions against your column's intended meaning.",
                    "heuristic",
                )
            )
        elif profile["inferred_type"] == "mixed":
            issues.append(
                issue(
                    "MIXED_TYPES",
                    "types",
                    "info",
                    column,
                    len(values),
                    positions,
                    "Multiple value syntaxes; no reliable dominant type was inferred.",
                    "Finite decimal numbers, strict ISO dates, and other text.",
                    "Supply domain expectations before treating any value as invalid.",
                    "uncertain",
                )
            )
        unsupported = [p for v, p in valid if classify(v) == "unsupported_numeric"]
        if unsupported:
            issues.append(
                issue(
                    "NUMERIC_RANGE",
                    "types",
                    "info",
                    column,
                    len(unsupported),
                    unsupported,
                    "Numeric literals exceed safe finite-float representation.",
                    "Finite float and nonzero-underflow checks.",
                    "Review with a domain-specific arbitrary-precision tool.",
                    "uncertain",
                )
            )
        if outliers["count"]:
            issues.append(
                issue(
                    "IQR_ANOMALY",
                    "outliers",
                    "warning",
                    column,
                    outliers["count"],
                    outliers["example_row_positions"],
                    "Values fall outside statistical IQR fences; they may be legitimate.",
                    "1.5 × IQR; inclusive, linearly interpolated quartiles; minimum 8.",
                    "Check the source and distribution before changing any value.",
                    "heuristic",
                )
            )
        if text["group_count"]:
            issues.append(
                issue(
                    "TEXT_VARIANTS",
                    "text",
                    "info",
                    column,
                    text["affected_row_count"],
                    text["example_row_positions"],
                    "Distinct raw values coincide after whitespace normalization and casefold.",
                    "Collapse Unicode whitespace and casefold; skip identifier-like columns.",
                    "Review local variants before defining a normalization policy.",
                    "heuristic",
                )
            )
    repeated = frame.duplicated(keep="first")
    members = frame.duplicated(keep=False)
    duplicate_count = int(repeated.sum())
    duplicates = {
        "definition": (
            "Raw string equality across all columns; count repeats after the first occurrence."
        ),
        "count": duplicate_count,
        "rate_pct": percentage(duplicate_count, rows),
        "example_row_positions": row_examples(repeated),
        "participating_row_count": int(members.sum()),
        "participating_example_row_positions": row_examples(members),
        "selected_columns": [],
    }
    if duplicate_count:
        issues.append(
            issue(
                "EXACT_DUPLICATE_ROWS",
                "duplicates",
                "warning",
                None,
                duplicate_count,
                row_examples(repeated),
                "Identical raw records repeat after their first occurrence.",
                duplicates["definition"],
                "Confirm whether repeated records are expected; nothing was removed.",
            )
        )
    for column in dict.fromkeys(config.duplicate_columns):
        eligible = frame.loc[~missing[column], column]
        repeat = eligible.duplicated(keep="first")
        member = eligible.duplicated(keep=False)
        positions = [p for p, ok in enumerate(~missing[column], 1) if ok]
        examples = [p for p, flag in zip(positions, repeat, strict=True) if flag]
        selected = {
            "column": column,
            "count": int(repeat.sum()),
            "example_row_positions": examples[:EXAMPLE_LIMIT],
            "participating_row_count": int(member.sum()),
            "eligible_row_count": len(eligible),
            "rate_pct": percentage(int(repeat.sum()), len(eligible)),
        }
        duplicates["selected_columns"].append(selected)
        if selected["count"]:
            issues.append(
                issue(
                    "REPEATED_COLUMN_VALUES",
                    "duplicates",
                    "info",
                    column,
                    selected["count"],
                    examples,
                    "Repeated raw values. Repetition alone is not an invalid record.",
                    "Per column; count repeats after the first; exclude missing cells.",
                    "Only investigate as an error if this column is required to be unique.",
                )
            )
    total_missing = sum(p["missing_count"] for p in profiles)
    affected_missing = missing.any(axis=1)
    return {
        "report_version": "1.0",
        "kind": "analysis",
        "row_position_convention": (
            "One-based data-row positions, excluding the header; not CSV line numbers."
        ),
        "policy": {
            "null_token_count": len(set(t.strip() for t in config.null_tokens)),
            "blank_is_missing": True,
            "example_limit": EXAMPLE_LIMIT,
            "minimum_type_sample": MIN_TYPE_SAMPLE,
            "dominant_threshold": DOMINANT_THRESHOLD,
            "minimum_outlier_sample": MIN_OUTLIER_SAMPLE,
            "raw_values_included": False,
        },
        "summary": {
            "row_count": rows,
            "column_count": columns,
            "cell_count": rows * columns,
            "missing_cell_count": total_missing,
            "missing_cell_pct": percentage(total_missing, rows * columns),
            "rows_with_missing_count": int(affected_missing.sum()),
            "rows_with_missing_examples": row_examples(affected_missing),
            "duplicate_row_count": duplicate_count,
            "duplicate_row_rate_pct": duplicates["rate_pct"],
            "issue_count": len(issues),
        },
        "columns": profiles,
        "duplicates": duplicates,
        "issues": issues,
    }
