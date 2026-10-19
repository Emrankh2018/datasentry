"""Local CSV quality inspection. No network, telemetry, or storage in the engine."""

from datasentry.compare import compare_datasets
from datasentry.ingestion import CSVInputError, load_csv, load_csv_path
from datasentry.profiling import AnalysisConfig, analyze_dataset
from datasentry.reports import report_json

__all__ = [
    "AnalysisConfig",
    "CSVInputError",
    "analyze_dataset",
    "compare_datasets",
    "load_csv",
    "load_csv_path",
    "report_json",
]
