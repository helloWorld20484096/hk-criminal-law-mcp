import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hk_criminal_law_mcp.db import connect  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    yield connection
    connection.close()
