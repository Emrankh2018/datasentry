from pathlib import Path

import pytest

from datasentry import load_csv

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def example():
    def load(name):
        return load_csv((EXAMPLES / name).read_bytes())

    return load
