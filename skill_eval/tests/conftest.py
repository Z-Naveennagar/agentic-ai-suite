"""
Shared pytest fixtures for the skills_testing test suite.

The test suite uses an in-memory or temp-file SQLite database so that
nothing it writes touches the production results.db.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skills_testing.core import db_writer


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Path to a temp SQLite file. The file does not exist yet."""
    return tmp_path / "skill_test_results.db"


@pytest.fixture
def tmp_db(tmp_db_path: Path):
    """
    A fresh sqlite3 connection to a temp DB with the production schema
    applied. Rolled back / closed at the end of the test.
    """

    config = {
        "database": {"path": str(tmp_db_path)},
    }
    # init_db reads its own config helpers, so monkey-patch _get_db_path
    # by writing a minimal config inline. Easier: call init_db with our
    # config dict directly (it accepts an optional config arg).
    conn = db_writer.init_db(config)
    try:
        yield conn
    finally:
        conn.close()
