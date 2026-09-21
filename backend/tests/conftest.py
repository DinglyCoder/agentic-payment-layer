import os
from pathlib import Path

import pytest

TEST_DATABASE = Path(__file__).parent / "paradime-test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DATABASE}"
os.environ["SIMULATION_MODE"] = "true"
os.environ["SEED_DEMO_DATA"] = "false"


@pytest.fixture(autouse=True)
def clean_database_file():
    TEST_DATABASE.unlink(missing_ok=True)
    yield
    TEST_DATABASE.unlink(missing_ok=True)
